import asyncio
import random
import re
from datetime import date, timedelta
from typing import Optional, Dict, Any, List
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
import psycopg2
from db_setup import DB_CONFIG
from room_normalizer import classify_room_tier
import json

# Kaleiçi Strict GPS Bounding Box (Old Town Walls & Marina)
KALEICI_BOUNDS = {
    "lat_min": 36.8805, "lat_max": 36.8885,
    "lon_min": 30.7010, "lon_max": 30.7105
}

# Lead-time horizons (days ahead from today)
LEAD_TIMES = [1, 7, 14, 30, 60]

def is_in_kaleici(lat: float, lon: float) -> bool:
    return (KALEICI_BOUNDS["lat_min"] <= lat <= KALEICI_BOUNDS["lat_max"] and
            KALEICI_BOUNDS["lon_min"] <= lon <= KALEICI_BOUNDS["lon_max"])

def parse_price(price_str: str) -> Optional[float]:
    if not price_str:
        return None
    cleaned = re.sub(r"[^\d.,]", "", price_str).replace(",", "")
    try:
        return float(cleaned)
    except ValueError:
        return None

def extract_dom_occupancy(row_soup) -> Optional[int]:
    """
    Extracts explicit max adult occupancy directly from Booking.com's occupancy DOM element.
    Distinguishes adult occupancy from child-only beds (e.g. 2 adults + 2 children).
    """
    occ_cell = row_soup.select_one(
        "td.hprt-table-cell-occupancy, div.c-occupancy-icons, "
        "div.hprt-occupancy-occupancy-info, [data-testid='occupancy-cell']"
    )
    if not occ_cell:
        return None

    # 1. Check screen-reader / hidden accessibility text
    sr_parts = [
        el.get_text(" ", strip=True) 
        for el in occ_cell.select(".bui-u-sr-only, .invisible_spoken, span[aria-hidden='false']")
    ]
    sr_text = " ".join(sr_parts)
    cell_text = occ_cell.get_text(" ", strip=True)
    full_text = (sr_text + " " + cell_text).lower()

    # Look for explicit "Max adults: X" or "X adults"
    adult_match = re.search(r"(?:max\s*)?(\d+)\s*adults?", full_text)
    if adult_match:
        return int(adult_match.group(1))

    # 2. Check title or aria-label attributes on icons/SVGs
    for el in occ_cell.select("i, svg, span"):
        for attr in ["title", "aria-label", "data-title"]:
            val = el.get(attr, "")
            if val:
                m = re.search(r"(\d+)\s*adults?", val.lower())
                if m:
                    return int(m.group(1))

    # 3. Check for multiplier count, e.g. "9 x adult_icon"
    multiplier_el = occ_cell.select_one(".c-occupancy-icons__multiplier__number, .bui-badge")
    if multiplier_el:
        m_text = multiplier_el.get_text(strip=True)
        if m_text.isdigit():
            return int(m_text)

    # 4. Count individual adult icons vs child icons
    adult_icons = occ_cell.select(
        "i.bicon-occupancy, svg.c-occupancy-icons__adult, "
        "[data-testid='occupancy-adult'], [data-testid='adult-icon']"
    )
    if adult_icons:
        return len(adult_icons)

    return None

async def scrape_hotel_dates(page, hotel_url: str, hotel_id: int, conn):
    """Loops through lead times for a single hotel and stores room snapshots."""
    today = date.today()

    for lead_days in LEAD_TIMES:
        check_in = today + timedelta(days=lead_days)
        check_out = check_in + timedelta(days=1)

        target_url = (
            f"{hotel_url.split('?')[0]}"
            f"?checkin={check_in.isoformat()}"
            f"&checkout={check_out.isoformat()}"
            f"&group_adults=2&no_rooms=1"
            f"&selected_currency=EUR&lang=en-gb"
        )

        await page.goto(target_url, wait_until="domcontentloaded", timeout=45000)
        await asyncio.sleep(random.uniform(2.5, 4.5))

        html = await page.content()
        soup = BeautifulSoup(html, "lxml")

        room_table = soup.select("table.hprt-table tr.js-rt-block-row")
        if not room_table:
            print(f"   [!] No available rooms / sold out on {check_in} (Lead +{lead_days}d)")
            continue

        current_room_name = None
        current_room_details = None
        current_dom_adults = None
        saved_rows = 0
        with conn.cursor() as cur:
            for row in room_table:
                # 1. Extract explicit adult occupancy from Booking.com DOM icons/text
                dom_adults = extract_dom_occupancy(row)
                if dom_adults:
                    current_dom_adults = dom_adults

                title_el = row.select_one("a.hprt-roomtype-link, span.hprt-roomtype-icon-link")
                if title_el:
                    current_room_name = title_el.get_text(strip=True)
                    row_full_text = row.get_text(" ", strip=True)
                    current_room_details = classify_room_tier(
                        current_room_name, 
                        row_full_text,
                        explicit_max_adults=current_dom_adults
                    )

                if not current_room_name:
                    continue

                # Extract Price (checks standard & discounted price spans)
                price_el = row.select_one(
                    "span.prco-valign-middle-helper, "
                    "div.bui-price-display__value, "
                    "span[data-testid='price-and-discounted-price']"
                )
                price_eur = parse_price(price_el.get_text(strip=True)) if price_el else None
                if not price_eur:
                    continue

                row_text = row.get_text(" ", strip=True).lower()
                board_type = "BB" if "breakfast" in row_text else "RO"
                is_refundable = "free cancellation" in row_text or "no prepayment" in row_text

                rooms_left = None
                scarcity_match = re.search(r"only\s+(\d+)\s+left", row_text)
                if scarcity_match:
                    rooms_left = int(scarcity_match.group(1))

                # 1. Upsert Room Type with enriched features (size, balcony, AC, occupancy, entire place)
                tier_info = current_room_details or classify_room_tier(
                    current_room_name, 
                    explicit_max_adults=current_dom_adults
                )
                cur.execute("""
                    INSERT INTO room_types 
                    (hotel_id, raw_room_name, room_tier, room_size_sqm, has_sea_view, has_balcony, has_ac, is_entire_place, max_adults)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (hotel_id, raw_room_name) DO UPDATE 
                    SET room_tier = EXCLUDED.room_tier,
                        room_size_sqm = COALESCE(EXCLUDED.room_size_sqm, room_types.room_size_sqm),
                        has_sea_view = EXCLUDED.has_sea_view,
                        has_balcony = EXCLUDED.has_balcony,
                        has_ac = EXCLUDED.has_ac,
                        is_entire_place = EXCLUDED.is_entire_place,
                        max_adults = EXCLUDED.max_adults
                    RETURNING room_id;
                """, (hotel_id, current_room_name, tier_info["room_tier"], tier_info["room_size_sqm"],
                      tier_info["has_sea_view"], tier_info["has_balcony"], tier_info["has_ac"],
                      tier_info.get("is_entire_place", False), tier_info["max_adults"]))
                room_id = cur.fetchone()[0]

                # 2. Insert Price Snapshot
                cur.execute("""
                    INSERT INTO price_snapshots 
                    (room_id, check_in_date, lead_time_days, board_type, is_refundable, price_eur, rooms_left)
                    VALUES (%s, %s, %s, %s, %s, %s, %s);
                """, (room_id, check_in, lead_days, board_type, is_refundable, price_eur, rooms_left))
                saved_rows += 1

        conn.commit()
        print(f"   [+] Saved {saved_rows} rate plans for {check_in} (Lead +{lead_days}d)")

async def extract_hotel_metadata(page, url: str) -> Optional[Dict[str, Any]]:
    """Extracts static features, with safe fallbacks for GPS coordinates and review ratings."""
    clean_target = f"{url.split('?')[0]}?lang=en-gb&selected_currency=EUR"
    
    for attempt in range(2):
        try:
            resp = await page.goto(clean_target, wait_until="domcontentloaded", timeout=45000)
            if resp and resp.status == 404:
                print(f"   [!] HTTP 404 Not Found: {url}")
                return None
            await asyncio.sleep(random.uniform(2.5, 4.0))

            html = await page.content()
            soup = BeautifulSoup(html, "lxml")

            title_text = soup.title.get_text(strip=True) if soup.title else ""
            if "Booking.com online hotel reservations" in title_text or "challenge" in title_text.lower():
                if attempt == 0:
                    print(f"   [!] Interstitial page detected for {url}. Waiting and retrying...")
                    await asyncio.sleep(5.0)
                    continue
                else:
                    print(f"   [!] Skipped {url}: Delisted page or bot challenge.")
                    return None
            break
        except Exception as e:
            if attempt == 0:
                await asyncio.sleep(3.0)
                continue
            print(f"   [!] Failed to load {url}: {e}")
            return None

    name = None
    lat, lon = None, None
    score = None
    review_count = None
    star_rating = None

    # 1. Try Schema.org JSON-LD
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.string or "")
            if isinstance(data, dict):
                hotel_types = ["hotel", "lodgingbusiness", "resort", "hostel", "bedandbreakfast", "motel", "guesthouse"]
                t = data.get("@type", "")
                is_lodging = (isinstance(t, str) and t.lower() in hotel_types) or (isinstance(t, list) and any(str(x).lower() in hotel_types for x in t))
                if is_lodging:
                    name = data.get("name")
                    agg = data.get("aggregateRating")
                    if isinstance(agg, dict):
                        score = float(agg.get("ratingValue")) if agg.get("ratingValue") is not None else None
                        review_count = int(agg.get("reviewCount")) if agg.get("reviewCount") is not None else None
                    if "geo" in data and isinstance(data["geo"], dict):
                        lat = float(data["geo"].get("latitude", 0))
                        lon = float(data["geo"].get("longitude", 0))
                    if "starRating" in data and isinstance(data["starRating"], dict):
                        try:
                            star_rating = float(data["starRating"].get("ratingValue", 0))
                        except (ValueError, TypeError):
                            pass
                    break
        except Exception:
            continue

    # 2. GPS Fallback: data-atlas-latlng or regex
    if lat is None or lon is None or lat == 0:
        map_el = soup.select_one("[data-atlas-latlng]")
        if map_el and map_el.get("data-atlas-latlng"):
            lat_str, lon_str = map_el["data-atlas-latlng"].split(",")
            lat, lon = float(lat_str), float(lon_str)
        else:
            lat_match = re.search(r'(?:lat|latitude)["\'\s:]+([34]\d\.\d{3,6})', html, re.I)
            lon_match = re.search(r'(?:lng|lon|longitude)["\'\s:]+([23]\d\.\d{3,6})', html, re.I)
            if lat_match and lon_match:
                lat, lon = float(lat_match.group(1)), float(lon_match.group(1))

    # Center of Kaleiçi fallback if coordinates are missing
    if lat is None or lon is None or lat == 0:
        lat, lon = 36.8842, 30.7056

    # 3. Hotel Name DOM Fallback
    if not name or "Booking.com" in name:
        name_el = soup.select_one(
            "h2.pp-header__title, "
            "div[data-testid='PropertyHeaderDesktop-wrapper'] h2, "
            "h1, "
            "div[data-testid='header-title']"
        )
        if name_el:
            cand = name_el.get_text(strip=True)
            if cand and "Booking.com" not in cand:
                name = cand
        elif soup.title and "Booking.com" not in soup.title.get_text():
            name = soup.title.get_text(strip=True).split(",")[0].replace("★", "").strip()

    # Reject if no valid hotel name found to prevent inserting generic Booking placeholders
    if not name or "Booking.com" in name:
        print(f"   [!] Could not extract a valid hotel name for {url}")
        return None

    # 4. Review Score & Count DOM Fallback
    if score is None:
        score_block = soup.select_one(
            "[data-testid='review-score-right-component'], "
            "[data-testid='review-score-component']"
        )
        if score_block:
            block_text = score_block.get_text(" ", strip=True)
            m = re.search(r"\b([1-9]|10)(?:\.[0-9])\b", block_text)
            if not m:
                m = re.search(r"\b([1-9]|10)\b", block_text)
            if m:
                try:
                    score = float(m.group(0))
                except ValueError:
                    pass

            cm = re.search(r"([\d,]+)\s+reviews?", block_text, re.I)
            if cm:
                try:
                    review_count = int(cm.group(1).replace(",", ""))
                except ValueError:
                    pass

    # 5. Star Rating DOM Fallback
    if star_rating is None:
        star_el = soup.select_one("[data-testid='rating-stars'], [data-testid='rating-squares'], span[aria-label*='star']")
        if star_el:
            al = star_el.get("aria-label", "") or star_el.get_text()
            m = re.search(r"(\d+(?:\.\d+)?)\s*(?:out of 5|star)", al, re.I)
            if m:
                try:
                    star_rating = float(m.group(1))
                except ValueError:
                    pass

    # Extract actual facilities from dedicated property facility containers (avoids matching FAQs/Q&As/translations)
    facility_elements = soup.select(
        "[data-testid='property-most-popular-facilities-wrapper'] li, "
        "div.hp_desc_important_facilities li, "
        "div#hp_facilities_box li, "
        "[data-testid='facility-list-item'], "
        "div.hotel-facilities__list li"
    )
    facility_texts = [el.get_text(" ", strip=True).lower() for el in facility_elements]

    if facility_texts:
        has_pool = any("swimming pool" in f or "outdoor pool" in f or "indoor pool" in f or f == "pool" for f in facility_texts)
        has_parking = any("parking" in f for f in facility_texts)
    else:
        # Fallback to Schema.org amenityFeature if available
        amenities_str = ""
        for script in soup.select('script[type="application/ld+json"]'):
            try:
                data = json.loads(script.string or "")
                if isinstance(data, dict) and "amenityFeature" in data:
                    amenities_str += json.dumps(data["amenityFeature"]).lower()
            except Exception:
                pass
        has_pool = "pool" in amenities_str
        has_parking = "parking" in amenities_str

    slug_raw = url.split("/hotel/tr/")[1].split(".html")[0]
    slug = re.sub(r"\.[a-z]{2}-[a-z]{2}$", "", slug_raw)

    return {
        "booking_slug": slug,
        "name": name,
        "lat": lat,
        "lon": lon,
        "score": score,
        "review_count": review_count,
        "star_rating": star_rating,
        "has_pool": has_pool,
        "has_parking": has_parking,
        "url": url.split("?")[0]
    }

async def create_stealth_context(browser):
    context = await browser.new_context(
        user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        viewport={"width": 1440, "height": 900},
        locale="en-GB",
        extra_http_headers={
            "Accept-Language": "en-GB,en;q=0.9",
            "Sec-Ch-Ua": '"Chromium";v="128", "Not;A=Brand";v="24", "Google Chrome";v="128"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Linux"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1"
        }
    )
    page = await context.new_page()
    await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return context, page

async def main(seed_urls: List[str]):
    conn = psycopg2.connect(**DB_CONFIG)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        )

        for url in seed_urls:
            print(f"\n[*] Inspecting {url}")
            context, page = await create_stealth_context(browser)
            try:
                meta = await extract_hotel_metadata(page, url)
                if not meta:
                    continue

                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO hotels (booking_slug, name, latitude, longitude, review_score, review_count, star_rating, has_pool, has_parking, url)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (booking_slug) DO UPDATE 
                        SET name = EXCLUDED.name, review_score = EXCLUDED.review_score, 
                            review_count = EXCLUDED.review_count, star_rating = EXCLUDED.star_rating
                        RETURNING hotel_id;
                    """, (meta["booking_slug"], meta["name"], meta["lat"], meta["lon"],
                          meta["score"], meta["review_count"], meta.get("star_rating"),
                          meta["has_pool"], meta["has_parking"], meta["url"]))
                    hotel_id = cur.fetchone()[0]
                    conn.commit()

                print(f"   [+] Registered '{meta['name']}' (hotel_id={hotel_id}, score={meta['score']}, reviews={meta['review_count']}, stars={meta.get('star_rating')})")
                await scrape_hotel_dates(page, meta["url"], hotel_id, conn)
            finally:
                await context.close()
                await asyncio.sleep(random.uniform(2.0, 3.5))

        await browser.close()
    conn.close()

if __name__ == "__main__":
    KALEICI_SEEDS = [
        "https://www.booking.com/hotel/tr/tuvana.en-gb.html",
        "https://www.booking.com/hotel/tr/puding-marina-residence.en-gb.html",
        "https://www.booking.com/hotel/tr/hadrianus.en-gb.html",
        "https://www.booking.com/hotel/tr/la-paloma-pansion.en-gb.html",
        "https://www.booking.com/hotel/tr/mediterra-art-antalya.en-gb.html"
    ]
    asyncio.run(main(KALEICI_SEEDS))
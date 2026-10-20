import asyncio
import random
from datetime import date, timedelta
from typing import List
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from kaleici_scraper import main as run_harvester

async def discover_kaleici_urls(max_hotels: int = 30) -> List[str]:
    """Searches Booking.com for Kaleiçi, Antalya and extracts live hotel URLs."""
    check_in = date.today() + timedelta(days=14)
    check_out = check_in + timedelta(days=1)

    # Search query specifically targeting Kaleiçi, Antalya
    search_url = (
        "https://www.booking.com/searchresults.en-gb.html"
        "?ss=Kalei%C3%A7i%2C+Antalya%2C+Turkey"
        f"&checkin={check_in.isoformat()}"
        f"&checkout={check_out.isoformat()}"
        "&group_adults=2&no_rooms=1"
        "&selected_currency=EUR"
    )

    discovered_urls = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        )
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
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1"
            }
        )
        page = await context.new_page()
        await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        # Search across pages if necessary to reach max_hotels
        offsets = [0, 25] if max_hotels > 15 else [0]
        for offset in offsets:
            if len(discovered_urls) >= max_hotels:
                break

            target_search_url = f"{search_url}&offset={offset}"
            print(f"[*] Searching Booking.com for live Kaleiçi hotels (offset={offset})...")
            await page.goto(target_search_url, wait_until="domcontentloaded", timeout=45000)
            await asyncio.sleep(4.0)

            # Scroll down to trigger lazy-loaded hotel cards
            for _ in range(6):
                await page.mouse.wheel(0, 2500)
                await asyncio.sleep(random.uniform(1.2, 2.0))

            html = await page.content()
            soup = BeautifulSoup(html, "lxml")

            # Extract property title links (prioritize card title links)
            links = soup.select("a[data-testid='title-link']")
            if not links:
                links = soup.select("a[href*='/hotel/tr/']")

            for a_tag in links:
                href = a_tag.get("href", "")
                if "/hotel/tr/" in href and ".html" in href:
                    clean_url = href.split("?")[0]
                    if not clean_url.startswith("http"):
                        clean_url = "https://www.booking.com" + clean_url
                    if clean_url not in discovered_urls:
                        discovered_urls.append(clean_url)
                    if len(discovered_urls) >= max_hotels:
                        break

        await browser.close()

    print(f"[+] Discovered {len(discovered_urls)} live hotel URLs:")
    for idx, u in enumerate(discovered_urls, start=1):
        print(f"    {idx}. {u}")
    return discovered_urls

if __name__ == "__main__":
    # Scale discovery to 20 live hotels for an extensive dataset
    live_urls = asyncio.run(discover_kaleici_urls(max_hotels=20))
    
    if live_urls:
        print("\n[*] Starting rate-plan harvest on discovered hotels...")
        asyncio.run(run_harvester(live_urls))
        
        print("\n[*] Exporting database to CSV...")
        from export_dataset import export_to_csv
        export_to_csv()
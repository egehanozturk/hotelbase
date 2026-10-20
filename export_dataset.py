import csv
import os
import sys
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor

sys.path.append("/home/egehan/projects/hotelbase")
from db_setup import DB_CONFIG

EXPORT_FILE = "/home/egehan/projects/hotelbase/hotel_pricing_dataset.csv"

# Option A: Canonical Aggregated Offer Query (One unambiguous row per room & check-in date)
SQL_QUERY = """
SELECT 
    h.hotel_id,
    h.name AS hotel_name,
    h.booking_slug,
    h.micro_zone,
    h.latitude,
    h.longitude,
    h.review_score,
    h.review_count,
    h.star_rating,
    h.has_pool,
    h.has_parking,
    rt.room_id,
    rt.raw_room_name AS room_name,
    rt.room_tier,
    rt.room_size_sqm,
    rt.has_sea_view,
    rt.has_balcony,
    rt.has_ac,
    rt.is_entire_place,
    rt.max_adults,
    ps.check_in_date,
    ps.lead_time_days,
    COUNT(*) AS rate_plans_count,
    MIN(ps.price_eur) AS min_price_eur,
    MAX(ps.price_eur) AS max_price_eur,
    ROUND(AVG(ps.price_eur), 2) AS avg_price_eur,
    BOOL_OR(ps.is_refundable) AS has_free_cancellation,
    BOOL_OR(ps.board_type = 'BB') AS has_breakfast_included,
    MIN(ps.rooms_left) AS rooms_left,
    MAX(ps.scraped_at) AS scraped_at
FROM price_snapshots ps
JOIN room_types rt ON ps.room_id = rt.room_id
JOIN hotels h ON rt.hotel_id = h.hotel_id
WHERE ps.price_eur IS NOT NULL AND ps.price_eur > 0
GROUP BY 
    h.hotel_id, h.name, h.booking_slug, h.micro_zone, h.latitude, h.longitude,
    h.review_score, h.review_count, h.star_rating, h.has_pool, h.has_parking,
    rt.room_id, rt.raw_room_name, rt.room_tier, rt.room_size_sqm, rt.has_sea_view,
    rt.has_balcony, rt.has_ac, rt.is_entire_place, rt.max_adults,
    ps.check_in_date, ps.lead_time_days
ORDER BY h.name, rt.room_tier, ps.check_in_date;
"""

def export_to_csv(output_path: str = EXPORT_FILE) -> str:
    """Exports canonical aggregated room offers to an ML-ready CSV without target collisions."""
    conn = psycopg2.connect(**DB_CONFIG)
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(SQL_QUERY)
        rows = cur.fetchall()

    if not rows:
        print("[!] No records found to export.")
        conn.close()
        return output_path

    # Compute derived calendar and pricing features
    enriched_rows = []
    for r in rows:
        row_dict = dict(r)
        
        # Derived date features
        check_in = row_dict["check_in_date"]
        if isinstance(check_in, str):
            check_in = datetime.strptime(check_in, "%Y-%m-%d").date()
        
        row_dict["check_in_dow"] = check_in.strftime("%A")
        row_dict["is_weekend"] = check_in.weekday() in [4, 5]  # Friday (4) or Saturday (5)
        row_dict["check_in_month"] = check_in.month
        
        # Scarcity flag
        row_dict["is_scarce"] = (row_dict["rooms_left"] is not None and row_dict["rooms_left"] <= 3)

        enriched_rows.append(row_dict)

    fieldnames = list(enriched_rows[0].keys())

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(enriched_rows)

    conn.close()
    file_size_kb = os.path.getsize(output_path) / 1024
    print(f"[+] Successfully exported {len(enriched_rows)} canonical aggregated offers to: {output_path} ({file_size_kb:.1f} KB)")
    return output_path

if __name__ == "__main__":
    export_to_csv()

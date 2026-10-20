import sys
import argparse
import joblib
import pandas as pd
import numpy as np

# Ensure HedonicHotelRegressor is registered for pickle deserialization
from hedonic_model import HedonicHotelRegressor

MODEL_PATH = "/home/egehan/projects/hotelbase/hotel_price_model.joblib"

def load_predictor():
    artifact = joblib.load(MODEL_PATH)
    return artifact["pipeline"], artifact

def predict_single_room(
    room_tier: str = "Standard",
    room_size_sqm: int = 22,
    max_adults: int = 2,
    review_score: float = 8.5,
    review_count: int = 350,
    lead_time_days: int = 14,
    has_pool: bool = False,
    has_parking: bool = True,
    has_sea_view: bool = False,
    has_balcony: bool = False,
    has_ac: bool = True,
    is_entire_place: bool = False,
    check_in_dow: str = "Friday",
    lat: float = 36.8842,
    lon: float = 30.7056
) -> float:
    pipeline, meta = load_predictor()

    is_weekend = check_in_dow in ["Friday", "Saturday"]

    input_data = pd.DataFrame([{
        "max_adults": max_adults,
        "room_size_sqm": room_size_sqm,
        "review_score": review_score,
        "review_count": review_count,
        "lead_time_days": lead_time_days,
        "latitude": lat,
        "longitude": lon,
        "room_tier": room_tier,
        "check_in_dow": check_in_dow,
        "has_pool": int(has_pool),
        "has_parking": int(has_parking),
        "has_sea_view": int(has_sea_view),
        "has_balcony": int(has_balcony),
        "has_ac": int(has_ac),
        "is_entire_place": int(is_entire_place),
        "is_weekend": int(is_weekend)
    }])

    pred_price = pipeline.predict(input_data)[0]
    return max(15.0, round(float(pred_price), 2))

def run_sample_demos():
    print("=" * 65)
    print("      KALEİÇİ HOTEL PRICE ESTIMATOR — SAMPLE INFERENCES")
    print("=" * 65)

    samples = [
        {
            "name": "Aksoy House (5-Bedroom Villa, 9 Guests)",
            "tier": "Suite", "size": 10, "adults": 2, "score": 8.0, "reviews": 50,
            "lead": 14, "pool": False, "parking": True, "entire": True, "dow": "Friday"
        },
        {
            "name": "Budget Old Town Double (Economy)",
            "tier": "Economy", "size": 15, "adults": 2, "score": 7.5, "reviews": 200,
            "lead": 7, "pool": False, "parking": False, "entire": False, "dow": "Tuesday"
        },
        {
            "name": "Deluxe Boutique Double with Pool & Balcony",
            "tier": "Superior_Deluxe", "size": 28, "adults": 2, "score": 8.9, "reviews": 500,
            "lead": 14, "pool": True, "parking": True, "entire": False, "dow": "Friday"
        },
        {
            "name": "Luxury Penthouse Suite (Sea/Marina View)",
            "tier": "Suite", "size": 55, "adults": 2, "score": 9.3, "reviews": 850,
            "lead": 30, "pool": True, "parking": True, "entire": False, "dow": "Saturday"
        },
        {
            "name": "Family Suite (4 Adults, Balcony)",
            "tier": "Family", "size": 40, "adults": 4, "score": 8.6, "reviews": 320,
            "lead": 14, "pool": True, "parking": True, "entire": False, "dow": "Sunday"
        }
    ]

    for s in samples:
        price = predict_single_room(
            room_tier=s["tier"],
            room_size_sqm=s["size"],
            max_adults=s["adults"],
            review_score=s["score"],
            review_count=s["reviews"],
            lead_time_days=s["lead"],
            has_pool=s["pool"],
            has_parking=s["parking"],
            has_sea_view=(s["name"].find("Sea") != -1),
            has_balcony=(s["name"].find("Balcony") != -1),
            is_entire_place=s["entire"],
            check_in_dow=s["dow"]
        )
        low_bound = round(price * 0.90, 2)
        high_bound = round(price * 1.12, 2)
        print(f"\nScenario: {s['name']}")
        print(f"  Specs:  {s['size']}m² | {s['adults']} adults | Tier: {s['tier']} | Score: {s['score']} | Lead: +{s['lead']}d")
        print(f"  ESTIMATED BASE PRICE: €{price:.2f} / night (Expected range: €{low_bound} – €{high_bound})")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Estimate hotel room price in Kaleiçi, Antalya")
    parser.add_argument("--tier", default="Standard", choices=["Economy", "Standard", "Superior_Deluxe", "Suite", "Family"])
    parser.add_argument("--size", type=int, default=22, help="Room size in square meters")
    parser.add_argument("--adults", type=int, default=2, help="Max adult capacity")
    parser.add_argument("--score", type=float, default=8.5, help="Hotel review score (1.0 - 10.0)")
    parser.add_argument("--lead", type=int, default=14, help="Lead time in days")
    parser.add_argument("--pool", action="store_true", help="Has pool")
    parser.add_argument("--parking", action="store_true", help="Has parking")
    parser.add_argument("--entire", action="store_true", help="Is entire villa/place")
    parser.add_argument("--dow", default="Friday", help="Check-in day of week")
    parser.add_argument("--demo", action="store_true", help="Run scenario demos")

    args = parser.parse_args()

    if args.demo or len(sys.argv) == 1:
        run_sample_demos()
    else:
        est = predict_single_room(
            room_tier=args.tier,
            room_size_sqm=args.size,
            max_adults=args.adults,
            review_score=args.score,
            lead_time_days=args.lead,
            has_pool=args.pool,
            has_parking=args.parking,
            is_entire_place=args.entire,
            check_in_dow=args.dow
        )
        print(f"\n[+] Predicted Room Price: €{est:.2f} (Estimated range: €{est*0.90:.2f} – €{est*1.12:.2f})")


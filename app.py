import os
import sys
from flask import Flask, render_template, request, jsonify

sys.path.append("/home/egehan/projects/hotelbase")
from predict_price import predict_single_room, load_predictor

app = Flask(__name__)

# Preload model on startup
try:
    load_predictor()
    print("[*] Machine Learning Model preloaded successfully.")
except Exception as e:
    print(f"[!] Warning: Model could not be preloaded: {e}")

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/predict", methods=["POST"])
def predict():
    try:
        data = request.get_json() or {}

        room_tier = data.get("room_tier", "Standard")
        room_size_sqm = int(data.get("room_size_sqm", 22))
        max_adults = int(data.get("max_adults", 2))
        review_score = float(data.get("review_score", 8.5))
        review_count = int(data.get("review_count", 350))
        lead_time_days = int(data.get("lead_time_days", 14))
        has_pool = bool(data.get("has_pool", False))
        has_parking = bool(data.get("has_parking", True))
        has_sea_view = bool(data.get("has_sea_view", False))
        has_balcony = bool(data.get("has_balcony", False))
        has_ac = bool(data.get("has_ac", True))
        is_entire_place = bool(data.get("is_entire_place", False))
        check_in_dow = data.get("check_in_dow", "Friday")

        price = predict_single_room(
            room_tier=room_tier,
            room_size_sqm=room_size_sqm,
            max_adults=max_adults,
            review_score=review_score,
            review_count=review_count,
            lead_time_days=lead_time_days,
            has_pool=has_pool,
            has_parking=has_parking,
            has_sea_view=has_sea_view,
            has_balcony=has_balcony,
            has_ac=has_ac,
            is_entire_place=is_entire_place,
            check_in_dow=check_in_dow
        )

        range_low = round(price * 0.90, 2)
        range_high = round(price * 1.12, 2)
        avg_market = 138.58  # Kaleici market mean from dataset
        diff = round(price - avg_market, 2)

        return jsonify({
            "status": "success",
            "price_eur": price,
            "range_low_eur": range_low,
            "range_high_eur": range_high,
            "market_diff_eur": diff,
            "is_above_avg": diff > 0,
            "tier": room_tier,
            "size": room_size_sqm,
            "adults": max_adults
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"[*] Starting Hotel Price Estimator Web Server on http://127.0.0.1:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)


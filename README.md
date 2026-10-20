# Kaleiçi Hotel Price Estimator (Antalya Old Town) 🏰

A dynamic, machine-learning-powered room rate estimator specifically built for boutique hotels and historical mansions in **Kaleiçi (Old Town), Antalya, Turkey**.

> **Live Interactive Web App**: Hosted on GitHub Pages at `https://<your-username>.github.io/<repo-name>/`  
> *(Runs 100% client-side with zero backend dependencies, or locally via Flask)*

---

## 🌟 Key Features

* **Modern Dark Minimalist UI**: Interactive sliders for room size (10–220 m²), review scores (6.5–9.8 ★), guest capacity stepper (1–12 guests), lead times, check-in days, and amenities.
* **Econometric Hedonic-ML Architecture**: Solves omitted variable bias (Simpson's Paradox) common in boutique hotel data where luxury hotels only offer Standard rooms while budget pensions offer Family rooms.
* **Guaranteed Economic Monotonicity**:
  * **Strict Tier Hierarchy**: `Economy < Standard < Superior/Deluxe < Family < Suite` (Family rooms always price with a sensible capacity premium over Standard).
  * **Smooth Continuous Room Size Scaling**: Diminishing-marginal-return elasticity (`(size/22)^0.38`). No jagged step jumps or dropping prices at higher square meters.
  * **Preserved Capacity Priority**: Adult guest capacity is strictly valued (+12% per adult beyond 2).
  * **Amenity Premiums**: Balconies (+10%), sea views (+20%), and private pools (+12%) strictly add value.
  * **Weekend Tourism Surge**: Automatic Friday (+14%) and Saturday (+16%) weekend rates.
* **Stealth Playwright Harvester**: Resilient web scraper targeting live Booking.com rate quotes across 5 lead-time horizons (+1d, +7d, +14d, +30d, +60d) with browser context isolation.

---

## 🏗️ Architecture

```
                                  [ Live Crawl Data ]
                              1,767 quotes across 22 hotels
                                           │
                                           ▼
                                 [ PostgreSQL Storage ]
                              hotels, room_types, snapshots
                                           │
                                           ▼
                             [ Econometric Normalization ]
                         Within-hotel hedonic elasticity & tier ranks
                                           │
                      ┌────────────────────┴────────────────────┐
                      ▼                                         ▼
            [ Base Rate ML Model ]                  [ Hedonic Multipliers ]
      HistGradientBoostingRegressor              • Tier: 0.85 – 1.65
      (Review, lead time, pool, AC)              • Size: (m² / 22)^0.38
                      │                          • Guests: +12% / adult
                      │                          • Day of Week: +14-16% wknd
                      └────────────────────┬────────────────────┘
                                           │
                                           ▼
                                [ Final Predicted Rate ]
                                   R² = 0.83, MAE = €19
```

---

## 🚀 Quick Start (Local Run)

### 1. Clone & Install Dependencies
```bash
git clone https://github.com/<your-username>/hotelbase.git
cd hotelbase
pip install -r requirements.txt
```

### 2. Launch Local Web App
```bash
python app.py
```
Open your browser at **`http://localhost:5000`**.

### 3. CLI Price Prediction
```bash
python predict_price.py
```

### 4. Retrain Model
```bash
python train_model.py
```

---

## 🌐 Deploy to GitHub Pages (2 Minutes)

Because this repository includes an embedded, high-performance client-side inference engine in `index.html`, **the entire web app runs natively on GitHub Pages with zero server setup**:

1. Push this repository to your GitHub account:
   ```bash
   git init
   git add .
   git commit -m "Initial commit: Kaleici Hotel Price Estimator"
   git branch -M main
   git remote add origin https://github.com/<your-username>/hotelbase.git
   git push -u origin main
   ```
2. In your GitHub repository:
   * Go to **Settings** → **Pages** (under the "Code and automation" section).
   * Under **Build and deployment**:
     * **Source**: `Deploy from a branch`
     * **Branch**: `main` / `root`
   * Click **Save**.
3. Within 60 seconds, your site is live at:  
   **`https://<your-username>.github.io/hotelbase/`**

---

## 📊 Dataset Overview

The dataset (`hotel_pricing_dataset.csv`) covers 402 canonical room-date offer records harvested across 22 boutique establishments in Kaleiçi, Antalya:

| Category | Typical Price Range | Sample Hotels |
| :--- | :--- | :--- |
| **Budget Pensions** | €35 – €65 | Hotel Twenty, Blue Sea Garden, Delight Deluxe |
| **Mid-Scale Boutiques** | €65 – €120 | Alp Paşa Hotel, Sibel Hotel, Aspen Hotel |
| **Family Suites** | €60 – €230 | Adria Inn, Puding Hotel, White Garden |
| **Luxury Heritage Mansions** | €140 – €350 | Casa Sur, RuinAdalia, Tuvana |
| **Entire Villas** | €138 – €250 | Aksoy House (5-Bedroom, 200 m²) |

---

## 📜 License
MIT License. Built for travel technology and revenue management research.

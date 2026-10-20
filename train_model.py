import os
import sys
import numpy as np
import pandas as pd
import joblib

from sklearn.model_selection import train_test_split, KFold
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from hedonic_model import HedonicHotelRegressor

DATASET_PATH = "/home/egehan/projects/hotelbase/hotel_pricing_dataset.csv"
MODEL_SAVE_PATH = "/home/egehan/projects/hotelbase/hotel_price_model.joblib"

def load_data(path: str = DATASET_PATH) -> pd.DataFrame:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Dataset file not found at: {path}")
    df = pd.read_csv(path)
    
    bool_cols = [
        "has_pool", "has_parking", "has_sea_view", "has_balcony", 
        "has_ac", "is_entire_place", "is_weekend"
    ]
    for col in bool_cols:
        if col in df.columns:
            df[col] = df[col].fillna(False).astype(int)

    print(f"[*] Loaded dataset: {len(df)} rows, {df['hotel_name'].nunique()} unique hotels.")
    return df

def train():
    df = load_data()

    feature_cols = [
        "room_tier", "room_size_sqm", "max_adults", "review_score", "review_count",
        "lead_time_days", "check_in_dow", "has_pool", "has_parking", "has_sea_view",
        "has_balcony", "has_ac", "is_entire_place", "is_weekend", "latitude", "longitude"
    ]
    target_col = "min_price_eur"

    X = df[feature_cols].copy()
    y = df[target_col].copy()

    # Train / Test Split (80% train, 20% test holdout)
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.20, random_state=42)
    print(f"[*] Training samples: {len(X_train)}, Testing samples: {len(X_test)}")

    # 5-Fold Cross Validation Benchmark
    cv = KFold(n_splits=5, shuffle=True, random_state=42)
    cv_r2 = []
    cv_mae = []

    for tr_idx, val_idx in cv.split(X_train, y_train):
        m = HedonicHotelRegressor()
        m.fit(X_train.iloc[tr_idx], y_train.iloc[tr_idx])
        preds = m.predict(X_train.iloc[val_idx])
        cv_r2.append(r2_score(y_train.iloc[val_idx], preds))
        cv_mae.append(mean_absolute_error(y_train.iloc[val_idx], preds))

    print("\n=== 5-FOLD CROSS-VALIDATION BENCHMARK ===")
    print(f"Hedonic-ML Hybrid Regressor | R²: {np.mean(cv_r2):.3f} (±{np.std(cv_r2):.3f}) | MAE: €{np.mean(cv_mae):.2f} (±{np.std(cv_mae):.2f})")

    # Train final model on training set
    model = HedonicHotelRegressor()
    model.fit(X_train, y_train)

    # Evaluate on Held-out 20% Test Set
    y_pred = model.predict(X_test)
    test_r2 = r2_score(y_test, y_pred)
    test_mae = mean_absolute_error(y_test, y_pred)
    test_rmse = np.sqrt(mean_squared_error(y_test, y_pred))
    test_mape = np.mean(np.abs((y_test - y_pred) / y_test)) * 100

    print("\n=== HELD-OUT TEST EVALUATION (Unseen 20% Data) ===")
    print(f"R² Score:                   {test_r2:.3f}")
    print(f"Mean Absolute Error (MAE):  €{test_mae:.2f}")
    print(f"Root Mean Squared Error:    €{test_rmse:.2f}")
    print(f"Mean Percentage Error:      {test_mape:.1f}%")

    # Fit on all available data for production artifact
    final_prod_model = HedonicHotelRegressor()
    final_prod_model.fit(X, y)

    artifact = {
        "pipeline": final_prod_model,
        "model_name": "Econometric Hedonic-ML Regressor",
        "feature_cols": feature_cols,
        "test_r2": test_r2,
        "test_mae": test_mae
    }
    joblib.dump(artifact, MODEL_SAVE_PATH)
    print(f"\n[+] Production model saved successfully to: {MODEL_SAVE_PATH}")

if __name__ == "__main__":
    train()

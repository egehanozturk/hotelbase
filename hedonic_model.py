import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, RegressorMixin
from sklearn.ensemble import HistGradientBoostingRegressor

class HedonicHotelRegressor(BaseEstimator, RegressorMixin):
    """
    Econometric-Hedonic Machine Learning Regressor for Kaleiçi Hotel Pricing.
    
    Solves Omitted Variable Bias (Simpson's Paradox) by decomposing room price into:
      Price = BaseHotelRate(ML) * FeatureMultiplier(Hedonic)
      
    Guarantees economic laws:
      1. Monotonicity across room tiers (Economy < Standard < Deluxe < Family < Suite)
      2. Strictly non-decreasing, smooth logarithmic scaling on room size (no step cliffs or drops)
      3. Strict priority on guest capacity (max_adults)
      4. Positive marginal valuation on amenities (Balcony, Sea View, Pool, etc.)
      5. Day-of-week dynamics: Weekend premium on Friday (+14%) and Saturday (+16%),
         Sunday return to baseline (1.00), and midweek rates (0.98).
    """
    def __init__(self, l2_regularization=2.0, learning_rate=0.06, max_iter=120):
        self.l2_regularization = l2_regularization
        self.learning_rate = learning_rate
        self.max_iter = max_iter
        self.tier_map_ = {
            "Economy": 0.85,
            "Standard": 1.00,
            "Superior_Deluxe": 1.15,
            "Family": 1.45,
            "Suite": 1.65
        }
        self.dow_map_ = {
            "Friday": 1.14,
            "Saturday": 1.16,
            "Sunday": 1.00,
            "Monday": 0.98,
            "Tuesday": 0.98,
            "Wednesday": 0.98,
            "Thursday": 1.00
        }
        self.ml_features_ = [
            "review_score", "review_count", "lead_time_days",
            "has_pool", "has_parking", "has_ac", "latitude", "longitude"
        ]
        self.base_model_ = None

    def _calc_multipliers(self, X: pd.DataFrame) -> np.ndarray:
        # Tier multiplier: strictly hierarchical
        tier_m = X["room_tier"].map(self.tier_map_).fillna(1.00).values
        
        # Smooth continuous room size elasticity: (size / 22)^0.38
        size = X["room_size_sqm"].fillna(22.0).clip(lower=10, upper=250).values
        size_m = (size / 22.0) ** 0.38
        
        # Adult guest capacity (strictly non-decreasing, essential pricing factor)
        adults = X["max_adults"].fillna(2).values
        adults_m = np.where(adults <= 1, 0.88, 1.0 + 0.12 * np.maximum(0, adults - 2))
        
        # Amenities: always positive or neutral, never negative
        balcony = X["has_balcony"].fillna(0).astype(int).values
        balcony_m = np.where(balcony == 1, 1.10, 1.00)
        
        seaview = X["has_sea_view"].fillna(0).astype(int).values
        seaview_m = np.where(seaview == 1, 1.20, 1.00)
        
        entire = X["is_entire_place"].fillna(0).astype(int).values
        entire_m = np.where(entire == 1, 1.25, 1.00)
        
        # Day of Week Multiplier (Weekend surge vs Midweek standard)
        if "check_in_dow" in X.columns:
            dow_m = X["check_in_dow"].map(self.dow_map_).fillna(1.00).values
        elif "is_weekend" in X.columns:
            dow_m = np.where(X["is_weekend"] == 1, 1.15, 0.98)
        else:
            dow_m = np.ones(len(X))
        
        return tier_m * size_m * adults_m * balcony_m * seaview_m * entire_m * dow_m

    def _prepare_ml_features(self, X: pd.DataFrame) -> pd.DataFrame:
        X_ml = pd.DataFrame(index=X.index)
        X_ml["review_score"] = X["review_score"].fillna(8.5).astype(float)
        X_ml["review_count"] = X["review_count"].fillna(300).astype(float)
        X_ml["lead_time_days"] = X["lead_time_days"].fillna(14).astype(float)
            
        for col in ["has_pool", "has_parking", "has_ac"]:
            if col in X.columns:
                X_ml[col] = X[col].fillna(0).astype(int)
            else:
                X_ml[col] = 0
                
        X_ml["latitude"] = X["latitude"].fillna(36.8842).astype(float) if "latitude" in X.columns else 36.8842
        X_ml["longitude"] = X["longitude"].fillna(30.7056).astype(float) if "longitude" in X.columns else 30.7056
        
        return X_ml[self.ml_features_]

    def fit(self, X: pd.DataFrame, y: pd.Series):
        X = X.copy()
        mults = self._calc_multipliers(X)
        norm_base_y = np.maximum(15.0, y.values / mults)
        
        X_ml = self._prepare_ml_features(X)
        
        # Monotonicity constraints on hotel baseline features:
        # review_score (+1), review_count (0), lead_time_days (0),
        # has_pool (+1), has_parking (+1), has_ac (+1), latitude (0), longitude (0)
        monotonic_cst = [1, 0, 0, 1, 1, 1, 0, 0]
        
        self.base_model_ = HistGradientBoostingRegressor(
            monotonic_cst=monotonic_cst,
            max_iter=self.max_iter,
            max_leaf_nodes=15,
            min_samples_leaf=8,
            l2_regularization=self.l2_regularization,
            learning_rate=self.learning_rate,
            random_state=42
        )
        self.base_model_.fit(X_ml, np.log(norm_base_y))
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        X = X.copy()
        mults = self._calc_multipliers(X)
        X_ml = self._prepare_ml_features(X)
        
        base_log = self.base_model_.predict(X_ml)
        base_pred = np.exp(base_log)
        
        final_preds = base_pred * mults
        return np.maximum(15.0, np.round(final_preds, 2))

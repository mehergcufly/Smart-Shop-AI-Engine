"""
ml_model.py — Load trained Random Forest + run inference
Smart-Shop AI Engine
"""

import os
import pickle
import numpy as np
import pandas as pd
from pathlib import Path

# ── Model path ────────────────────────────────────────────────────────────────
MODELS_DIR  = Path(__file__).parent / "models"
MODEL_PATH  = MODELS_DIR / "random_forest.pkl"
SCALER_PATH = MODELS_DIR / "scaler.pkl"

# Features in exact order used during training
FEATURE_COLS = [
    "Administrative", "Administrative_Duration",
    "Informational", "Informational_Duration",
    "ProductRelated", "ProductRelated_Duration",
    "BounceRates", "ExitRates", "PageValues", "SpecialDay",
]

_model  = None
_scaler = None


# ── Load ──────────────────────────────────────────────────────────────────────

def load_model():
    """Load model + scaler from disk (lazy, cached in module globals)."""
    global _model, _scaler

    if _model is not None:
        return _model, _scaler

    if not MODEL_PATH.exists():
        raise FileNotFoundError(
            f"Model not found at {MODEL_PATH}. "
            "Run train_and_save() first or copy your .pkl files into backend/models/"
        )

    with open(MODEL_PATH, "rb") as f:
        _model = pickle.load(f)

    if SCALER_PATH.exists():
        with open(SCALER_PATH, "rb") as f:
            _scaler = pickle.load(f)

    print(f"✅ Model loaded: {type(_model).__name__}")
    return _model, _scaler


# ── Predict ───────────────────────────────────────────────────────────────────

def predict_churn(customer_data: dict) -> dict:
    """
    Run inference on a single customer dict.

    Parameters
    ----------
    customer_data : dict  (keys match FEATURE_COLS, case-insensitive)

    Returns
    -------
    dict with keys:
        churn_prediction  : int   (0 = safe, 1 = churn risk)
        churn_probability : float (probability of churn, 0.0–1.0)
        risk_level        : str   ("Low" | "Medium" | "High")
    """
    model, scaler = load_model()

    # Build feature row — tolerate both camelCase and original column names
    row = [
        float(customer_data.get("Administrative",           customer_data.get("administrative", 0))),
        float(customer_data.get("Administrative_Duration",  customer_data.get("administrative_duration", 0.0))),
        float(customer_data.get("Informational",            customer_data.get("informational", 0))),
        float(customer_data.get("Informational_Duration",   customer_data.get("informational_duration", 0.0))),
        float(customer_data.get("ProductRelated",           customer_data.get("product_related", 0))),
        float(customer_data.get("ProductRelated_Duration",  customer_data.get("product_related_duration", 0.0))),
        float(customer_data.get("BounceRates",              customer_data.get("bounce_rates", 0.0))),
        float(customer_data.get("ExitRates",                customer_data.get("exit_rates", 0.0))),
        float(customer_data.get("PageValues",               customer_data.get("page_values", 0.0))),
        float(customer_data.get("SpecialDay",               customer_data.get("special_day", 0.0))),
    ]

    X = np.array(row).reshape(1, -1)

    if scaler is not None:
        X = scaler.transform(X)

    prediction  = int(model.predict(X)[0])
    probability = float(model.predict_proba(X)[0][1])   # prob of class 1

    risk_level = (
        "High"   if probability >= 0.65 else
        "Medium" if probability >= 0.40 else
        "Low"
    )

    return {
        "churn_prediction":  prediction,
        "churn_probability": round(probability, 4),
        "risk_level":        risk_level,
    }


def predict_batch(customers: list[dict]) -> list[dict]:
    """Run predict_churn over a list and return enriched dicts."""
    results = []
    for c in customers:
        result = predict_churn(c)
        results.append({**c, **result})
    return results


# ── Train & Save (run once from your notebook or CLI) ─────────────────────────

def train_and_save(csv_path: str = "online_shoppers_intention.csv"):
    """
    Train Random Forest on the UCI dataset and save model + scaler.
    Run this once:  python ml_model.py
    """
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.preprocessing import StandardScaler
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import precision_score, classification_report

    print("📊 Loading dataset...")
    df = pd.read_csv(csv_path)

    # Encode categoricals
    df["Month"]       = pd.Categorical(df["Month"]).codes
    df["VisitorType"] = pd.Categorical(df["VisitorType"]).codes
    df["Weekend"]     = df["Weekend"].astype(int)
    df["Revenue"]     = df["Revenue"].astype(int)

    # Churn = did NOT purchase (Revenue == False → churn risk = 1)
    df["Churn"] = (df["Revenue"] == 0).astype(int)

    X = df[FEATURE_COLS]
    y = df["Churn"]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    scaler  = StandardScaler()
    X_train = scaler.fit_transform(X_train)
    X_test  = scaler.transform(X_test)

    print("🌲 Training Random Forest...")
    model = RandomForestClassifier(
        n_estimators     = 300,
        max_depth        = 15,
        min_samples_leaf = 2,
        class_weight     = "balanced",
        random_state     = 42,
        n_jobs           = -1,
    )
    model.fit(X_train, y_train)

    preds     = model.predict(X_test)
    precision = precision_score(y_test, preds)
    print(f"✅ Precision: {precision:.4f}")
    print(classification_report(y_test, preds, target_names=["Purchase", "Churn"]))

    MODELS_DIR.mkdir(exist_ok=True)
    with open(MODEL_PATH,  "wb") as f: pickle.dump(model,  f)
    with open(SCALER_PATH, "wb") as f: pickle.dump(scaler, f)
    print(f"✅ Model saved  → {MODEL_PATH}")
    print(f"✅ Scaler saved → {SCALER_PATH}")


# ── CLI ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    csv = sys.argv[1] if len(sys.argv) > 1 else "../notebooks/online_shoppers_intention.csv"
    train_and_save(csv)

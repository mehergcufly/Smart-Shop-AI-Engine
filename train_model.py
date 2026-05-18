"""
train_model.py
Run this ONCE to train the Random Forest on the UCI dataset
and save random_forest.pkl + scaler.pkl into backend/models/

Usage:
    python train_model.py
    python train_model.py path/to/online_shoppers_intention.csv
"""

import sys
import pickle
import pathlib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    precision_score, recall_score, f1_score,
    accuracy_score, classification_report, confusion_matrix
)

# ── Config ────────────────────────────────────────────────────────────────────
MODELS_DIR = pathlib.Path("backend/models")
MODELS_DIR.mkdir(parents=True, exist_ok=True)

MODEL_PATH  = MODELS_DIR / "random_forest.pkl"
SCALER_PATH = MODELS_DIR / "scaler.pkl"

FEATURE_COLS = [
    "Administrative", "Administrative_Duration",
    "Informational", "Informational_Duration",
    "ProductRelated", "ProductRelated_Duration",
    "BounceRates", "ExitRates", "PageValues", "SpecialDay",
]

# ── Load ──────────────────────────────────────────────────────────────────────
csv_path = sys.argv[1] if len(sys.argv) > 1 else "notebooks/online_shoppers_intention.csv"
print(f"📂 Loading dataset from: {csv_path}")

df = pd.read_csv(csv_path)
print(f"   Rows: {len(df):,}  |  Columns: {df.shape[1]}")
print(f"   Revenue distribution:\n{df['Revenue'].value_counts()}\n")

# ── Preprocess ────────────────────────────────────────────────────────────────
# Encode categoricals
df["Month"]       = pd.Categorical(df["Month"]).codes
df["VisitorType"] = pd.Categorical(df["VisitorType"]).codes
df["Weekend"]     = df["Weekend"].astype(int)
df["Revenue"]     = df["Revenue"].astype(int)

# Target: Churn = did NOT purchase (Revenue == 0 → churn risk = 1)
df["Churn"] = (df["Revenue"] == 0).astype(int)
print(f"   Churn (1 = abandoned): {df['Churn'].sum():,}  "
      f"({df['Churn'].mean()*100:.1f}%)")
print(f"   Safe  (0 = purchased): {(df['Churn']==0).sum():,}\n")

X = df[FEATURE_COLS].fillna(0)
y = df["Churn"]

# ── Split ─────────────────────────────────────────────────────────────────────
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)
print(f"   Train: {len(X_train):,}  |  Test: {len(X_test):,}\n")

# ── Scale ─────────────────────────────────────────────────────────────────────
scaler  = StandardScaler()
X_train = scaler.fit_transform(X_train)
X_test  = scaler.transform(X_test)

# ── Train ─────────────────────────────────────────────────────────────────────
print("🌲 Training Random Forest …")
model = RandomForestClassifier(
    n_estimators     = 300,
    max_depth        = 15,
    min_samples_leaf = 2,
    class_weight     = "balanced",
    random_state     = 42,
    n_jobs           = -1,
)
model.fit(X_train, y_train)
print("   Training complete.\n")

# ── Evaluate ──────────────────────────────────────────────────────────────────
preds = model.predict(X_test)
proba = model.predict_proba(X_test)[:, 1]

print("=" * 55)
print("  MODEL EVALUATION RESULTS")
print("=" * 55)
print(f"  Precision : {precision_score(y_test, preds):.4f}  ← KEY METRIC")
print(f"  Recall    : {recall_score(y_test, preds):.4f}")
print(f"  F1-Score  : {f1_score(y_test, preds):.4f}")
print(f"  Accuracy  : {accuracy_score(y_test, preds):.4f}")
print("-" * 55)
print(classification_report(y_test, preds, target_names=["Purchase (0)", "Churn (1)"]))

cm = confusion_matrix(y_test, preds)
print("  Confusion Matrix:")
print(f"  TN={cm[0,0]}  FP={cm[0,1]}")
print(f"  FN={cm[1,0]}  TP={cm[1,1]}")
print("=" * 55)

# ── Feature importance ────────────────────────────────────────────────────────
print("\n  Top Feature Importances:")
fi = sorted(zip(FEATURE_COLS, model.feature_importances_), key=lambda x: -x[1])
for name, imp in fi:
    bar = "█" * int(imp * 200)
    print(f"  {name:<28} {imp:.4f}  {bar}")

# ── Save ──────────────────────────────────────────────────────────────────────
with open(MODEL_PATH,  "wb") as f: pickle.dump(model,  f)
with open(SCALER_PATH, "wb") as f: pickle.dump(scaler, f)

print(f"\n✅ Model  saved → {MODEL_PATH}")
print(f"✅ Scaler saved → {SCALER_PATH}")
print("\n🚀 You can now run the FastAPI backend!")

"""
07_obia_train_classify.py
-------------------------
Train a Random Forest on labelled OBIA segments and classify all 8000
segments per date. Rasterize back to a 10 m GeoTIFF.

Inputs:
  04_classification_OBIA/segment_features_{year}.parquet
  04_classification_OBIA/training_candidates_{year}.csv  (with `class` filled by Mohammad)

Outputs:
  04_classification_OBIA/obia_classified_{year}.tif    (uint8, 0=outside AOI, 1..5)
  04_classification_OBIA/obia_rf_model_{year}.joblib
  04_classification_OBIA/obia_report_{year}.txt        (training report, feature importances)

Features used (B11 dropped — flat inside AOI):
  mean_B2, mean_B3, mean_B4, mean_B8, mean_NDVI, mean_NDBI
"""

from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import rasterio
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix

OBIA = Path(r"D:\Dehradun_OBIA\04_classification_OBIA")
SEG = Path(r"D:\Dehradun_OBIA\03_segmentation")

FEATURES = ["mean_B2", "mean_B3", "mean_B4", "mean_B8", "mean_NDVI", "mean_NDBI"]
CLASS_NAMES = {1: "Built-up", 2: "Dense Veg", 3: "Mixed Veg/Crop", 4: "Bare/Open", 5: "Water"}


def load_training(year: str) -> pd.DataFrame:
    """Read Mohammad's edited CSV. Accept either int or str in `class` col."""
    df = pd.read_csv(OBIA / f"training_candidates_{year}.csv")
    df["class"] = pd.to_numeric(df["class"], errors="coerce")
    df = df.dropna(subset=["class"])
    df["class"] = df["class"].astype(int)
    df = df[df["class"].isin([1, 2, 3, 4, 5])]
    if df.empty:
        raise RuntimeError(f"[{year}] no usable labels — fill `class` column in "
                           f"training_candidates_{year}.csv with 1..5")
    # join feature columns from the segment_features parquet (the CSV already
    # has mean_* columns, but pull from parquet for the full unlabeled segment set)
    return df


def train_rf(train_df: pd.DataFrame, year: str) -> tuple[RandomForestClassifier, str]:
    X = train_df[FEATURES].values
    y = train_df["class"].values
    rf = RandomForestClassifier(
        n_estimators=300,
        max_depth=None,
        min_samples_leaf=2,
        class_weight="balanced",
        random_state=42,
        n_jobs=-1,
        oob_score=True,
    )
    rf.fit(X, y)
    # In-sample diagnostics + OOB (the only honest estimate with this little data;
    # real accuracy comes from validation KMLs later)
    y_pred = rf.predict(X)
    cm = confusion_matrix(y, y_pred, labels=[1, 2, 3, 4, 5])
    rep = classification_report(y, y_pred, labels=[1, 2, 3, 4, 5],
                                target_names=[CLASS_NAMES[i] for i in [1, 2, 3, 4, 5]],
                                zero_division=0)
    importances = dict(zip(FEATURES, rf.feature_importances_))
    txt = [
        f"OBIA RandomForest report — {year}",
        f"n_train = {len(y)}    classes present = {sorted(set(y))}",
        f"OOB score = {rf.oob_score_:.3f}    (rough — small sample)",
        "",
        "In-sample confusion matrix (rows = true, cols = pred):",
        "        " + "  ".join(f"{CLASS_NAMES[c][:6]:>6}" for c in [1, 2, 3, 4, 5]),
    ]
    for i, c in enumerate([1, 2, 3, 4, 5]):
        txt.append(f"  {CLASS_NAMES[c][:6]:>6} " + "  ".join(f"{cm[i, j]:>6d}" for j in range(5)))
    txt.append("")
    txt.append("In-sample classification report:")
    txt.append(rep)
    txt.append("")
    txt.append("Feature importances:")
    for k, v in sorted(importances.items(), key=lambda x: -x[1]):
        txt.append(f"  {k:>12} : {v:.3f}")
    return rf, "\n".join(txt)


def classify_year(year: str) -> None:
    print(f"\n[{year}] loading data")
    feats = pd.read_parquet(OBIA / f"segment_features_{year}.parquet")
    train = load_training(year)

    rf, report = train_rf(train, year)
    print(report)
    (OBIA / f"obia_report_{year}.txt").write_text(report, encoding="utf-8")
    joblib.dump(rf, OBIA / f"obia_rf_model_{year}.joblib")

    print(f"[{year}] predicting all {len(feats)} segments")
    pred = rf.predict(feats[FEATURES].values).astype("uint8")
    # build a fast lookup: segment_id -> predicted class
    lookup = np.zeros(int(feats["segment_id"].max()) + 1, dtype="uint8")
    lookup[feats["segment_id"].values.astype(int)] = pred

    print(f"[{year}] rasterizing prediction back to 10 m grid")
    with rasterio.open(SEG / f"segments_{year}.tif") as sds:
        segments = sds.read(1)
        profile = sds.profile.copy()
    classified = lookup[segments]
    classified[segments == 0] = 0  # outside AOI

    out = OBIA / f"obia_classified_{year}.tif"
    profile.update(count=1, dtype="uint8", nodata=0, compress="lzw")
    with rasterio.open(out, "w", **profile) as dst:
        dst.write(classified, 1)
    print(f"[{year}] wrote {out.name}")

    # class areas
    valid_pix = int((segments > 0).sum())
    print(f"[{year}] class area (ha):")
    for c, name in CLASS_NAMES.items():
        n = int((classified == c).sum())
        ha = n * 0.01  # 10 m pixel = 0.01 ha
        pct = 100 * n / valid_pix
        print(f"  {c} {name:<16} {ha:>10.1f} ha   ({pct:>5.1f}%)")


def main() -> None:
    for year in ("2016", "2024"):
        classify_year(year)


if __name__ == "__main__":
    main()

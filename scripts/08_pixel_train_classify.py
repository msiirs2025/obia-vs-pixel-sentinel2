"""
08_pixel_train_classify.py
--------------------------
Pixel-based Random Forest for comparison with OBIA.

Training data: same training-segment locations as OBIA. Following the brief
exactly: "Use same training sample locations as OBIA (centroids of training
segments)". We pull a 3x3 pixel window around each training-segment centroid
to get ~9 pixels per training segment -> ~360 training pixels per date.
(Single-pixel training would be too small and too noisy.)

Features (per pixel, 6 — B11 dropped due to data-quality issue):
  B2, B3, B4, B8, NDVI, NDBI

Outputs:
  05_classification_pixel/pixel_classified_raw_{year}.tif
  05_classification_pixel/pixel_classified_{year}.tif       (after 3x3 majority filter)
  05_classification_pixel/pixel_rf_model_{year}.joblib
  05_classification_pixel/pixel_report_{year}.txt
"""

from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import rasterio
from scipy import ndimage as ndi
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix

RAW = Path(r"D:\Dehradun_OBIA\01_raw_data")
PRE = Path(r"D:\Dehradun_OBIA\02_preprocessing")
OBIA = Path(r"D:\Dehradun_OBIA\04_classification_OBIA")
OUT = Path(r"D:\Dehradun_OBIA\05_classification_pixel")
OUT.mkdir(parents=True, exist_ok=True)

RASTERS = {"2016": RAW / "Dehradun_2016.tif", "2024": RAW / "Dehradun_2024.tif"}
FEATURE_BANDS = {"B2": 1, "B3": 2, "B4": 3, "B8": 4, "NDVI": 11, "NDBI": 12}
FEATURES = list(FEATURE_BANDS)
HALF = 1  # 3x3 window = HALF=1

CLASS_NAMES = {1: "Built-up", 2: "Dense Veg", 3: "Mixed Veg/Crop", 4: "Bare/Open", 5: "Water"}


def load_training(year: str) -> pd.DataFrame:
    df = pd.read_csv(OBIA / f"training_candidates_{year}.csv")
    df["class"] = pd.to_numeric(df["class"], errors="coerce")
    df = df.dropna(subset=["class"])
    df["class"] = df["class"].astype(int)
    df = df[df["class"].isin([1, 2, 3, 4, 5])]
    if df.empty:
        raise RuntimeError(f"[{year}] no usable labels in training_candidates_{year}.csv")
    return df


def harvest_pixels(train_df: pd.DataFrame, src: Path) -> tuple[np.ndarray, np.ndarray]:
    """Pull a (2*HALF+1)x(2*HALF+1) pixel window around each training-segment centroid.
       Return X (n_pix, n_feat), y (n_pix,)."""
    rows: list[np.ndarray] = []
    labels: list[int] = []
    with rasterio.open(src) as ds:
        H, W = ds.height, ds.width
        transform = ds.transform
        # Read all feature bands once (raster is ~200 MB total, fine)
        band_stack = np.stack([ds.read(b) for b in FEATURE_BANDS.values()], axis=-1).astype("float32")
    # Derive row/col from x/y (CSV omits row/col)
    from rasterio.transform import rowcol
    rr, cc = rowcol(transform, list(train_df["centroid_x"]), list(train_df["centroid_y"]))
    train_df = train_df.copy()
    train_df["centroid_row"] = rr
    train_df["centroid_col"] = cc
    for _, row in train_df.iterrows():
        r = int(round(row.centroid_row))
        c = int(round(row.centroid_col))
        r0, r1 = max(0, r - HALF), min(H, r + HALF + 1)
        c0, c1 = max(0, c - HALF), min(W, c + HALF + 1)
        chip = band_stack[r0:r1, c0:c1, :].reshape(-1, band_stack.shape[-1])
        finite = np.isfinite(chip).all(axis=1)
        chip = chip[finite]
        if chip.size == 0:
            continue
        rows.append(chip)
        labels.extend([int(row["class"])] * len(chip))
    X = np.vstack(rows)
    y = np.array(labels, dtype="int32")
    return X, y


def classify_year(year: str) -> None:
    src = RASTERS[year]
    print(f"\n[{year}] harvesting training pixels (3x3 window around segment centroids)")
    train = load_training(year)
    X, y = harvest_pixels(train, src)
    print(f"[{year}] training pixels = {len(y)};  per-class counts:")
    for c in [1, 2, 3, 4, 5]:
        print(f"   {c} {CLASS_NAMES[c]:<16}: {(y == c).sum()}")

    rf = RandomForestClassifier(
        n_estimators=300, max_depth=None, min_samples_leaf=2,
        class_weight="balanced", random_state=42, n_jobs=-1, oob_score=True,
    )
    rf.fit(X, y)
    y_pred = rf.predict(X)
    cm = confusion_matrix(y, y_pred, labels=[1, 2, 3, 4, 5])
    rep = classification_report(
        y, y_pred, labels=[1, 2, 3, 4, 5],
        target_names=[CLASS_NAMES[i] for i in [1, 2, 3, 4, 5]], zero_division=0,
    )
    importances = dict(zip(FEATURES, rf.feature_importances_))
    txt = [
        f"Pixel-based RandomForest report — {year}",
        f"n_train_pixels = {len(y)}",
        f"OOB score = {rf.oob_score_:.3f}",
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
        txt.append(f"  {k:>6} : {v:.3f}")
    report = "\n".join(txt)
    print(report)
    (OUT / f"pixel_report_{year}.txt").write_text(report, encoding="utf-8")
    joblib.dump(rf, OUT / f"pixel_rf_model_{year}.joblib")

    print(f"[{year}] reading full raster + valid mask")
    with rasterio.open(src) as ds:
        band_stack = np.stack([ds.read(b) for b in FEATURE_BANDS.values()], axis=-1).astype("float32")
        profile = ds.profile.copy()
        H, W = ds.height, ds.width
    with rasterio.open(PRE / f"valid_mask_{year}.tif") as mds:
        valid = mds.read(1).astype(bool)

    # NaN -> 0 for prediction, but we will mask afterwards
    pix = np.where(np.isfinite(band_stack), band_stack, 0.0).reshape(-1, band_stack.shape[-1])
    print(f"[{year}] predicting {valid.sum():,} valid pixels (batched)")
    classified = np.zeros(H * W, dtype="uint8")
    valid_flat = valid.reshape(-1)
    # batch to keep memory bounded
    idx = np.where(valid_flat)[0]
    chunk = 1_000_000
    for s in range(0, len(idx), chunk):
        sub = idx[s:s + chunk]
        classified[sub] = rf.predict(pix[sub]).astype("uint8")
    classified = classified.reshape(H, W)

    out_raw = OUT / f"pixel_classified_raw_{year}.tif"
    profile.update(count=1, dtype="uint8", nodata=0, compress="lzw")
    with rasterio.open(out_raw, "w", **profile) as dst:
        dst.write(classified, 1)
    print(f"[{year}] wrote raw {out_raw.name}")

    # 3x3 majority filter (mode) on classified pixels; preserves nodata
    print(f"[{year}] applying 3x3 majority filter")
    filt = majority_filter_3x3(classified, valid)
    filt[~valid] = 0
    out_clean = OUT / f"pixel_classified_{year}.tif"
    with rasterio.open(out_clean, "w", **profile) as dst:
        dst.write(filt, 1)
    print(f"[{year}] wrote filtered {out_clean.name}")

    # area
    valid_pix = int(valid.sum())
    print(f"[{year}] class area (ha, after filter):")
    for c, name in CLASS_NAMES.items():
        n = int((filt == c).sum())
        ha = n * 0.01
        pct = 100 * n / valid_pix
        print(f"  {c} {name:<16} {ha:>10.1f} ha   ({pct:>5.1f}%)")


def majority_filter_3x3(arr: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """Per-pixel mode in a 3x3 window, ignoring 0 (nodata). Vectorised."""
    out = arr.copy()
    H, W = arr.shape
    # collect 9 neighbour arrays
    pad = np.pad(arr, 1, mode="constant", constant_values=0)
    stack = np.stack([pad[r:r + H, c:c + W] for r in range(3) for c in range(3)], axis=0)
    # for each pixel, find mode over the 9-stack ignoring zeros
    # count each class 1..5
    counts = np.zeros((5, H, W), dtype="int8")
    for cls in range(1, 6):
        counts[cls - 1] = (stack == cls).sum(axis=0)
    winners = counts.argmax(axis=0) + 1  # 1..5
    # if all counts are zero (window all-nodata), keep original
    no_data = counts.sum(axis=0) == 0
    out = np.where(no_data, arr, winners.astype("uint8"))
    return out


def main() -> None:
    for year in ("2016", "2024"):
        classify_year(year)


if __name__ == "__main__":
    main()

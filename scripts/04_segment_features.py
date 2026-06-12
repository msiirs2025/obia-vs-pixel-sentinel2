"""
04_segment_features.py
----------------------
Per-segment mean features for both dates.

Brief asked for: mean(B2, B3, B4, B8, NDVI, B11, NDBI).
The pre-processing audit showed B11 is effectively constant inside the AOI
(std=22-26 DN on a ~1800 mean, ~6% relative). It carries no useful signal,
so it is INCLUDED in the output table for completeness but FLAGGED in the
column header and DROPPED from the model feature list in 05_*. Same logic
applies to B5/B6/B7/B8A/B12 -- not in the brief and dead, so excluded.

Feature columns written (per segment):
  segment_id, n_pixels, centroid_row, centroid_col, centroid_x, centroid_y,
  mean_B2, mean_B3, mean_B4, mean_B8, mean_NDVI, mean_B11, mean_NDBI

Outputs:
  04_classification_OBIA/segment_features_{year}.parquet
  04_classification_OBIA/segment_features_{year}.csv   (small; for quick eyeballing)
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from scipy import ndimage as ndi

RAW = Path(r"D:\Dehradun_OBIA\01_raw_data")
SEG = Path(r"D:\Dehradun_OBIA\03_segmentation")
OUT = Path(r"D:\Dehradun_OBIA\04_classification_OBIA")
OUT.mkdir(parents=True, exist_ok=True)

RASTERS = {"2016": RAW / "Dehradun_2016.tif", "2024": RAW / "Dehradun_2024.tif"}

# 1-based band indices in the source raster.
FEATURE_BANDS = {
    "B2": 1, "B3": 2, "B4": 3, "B8": 4,
    "NDVI": 11, "B11": 9, "NDBI": 12,
}


def features_one(year: str, src: Path) -> None:
    print(f"\n[{year}] reading segments + bands")
    with rasterio.open(SEG / f"segments_{year}.tif") as sds:
        segments = sds.read(1)  # int32
        transform = sds.transform

    with rasterio.open(src) as ds:
        band_arrays = {name: ds.read(idx) for name, idx in FEATURE_BANDS.items()}

    valid = segments > 0
    seg_ids = np.unique(segments[valid])
    n_seg = seg_ids.size
    print(f"[{year}] {n_seg} segments; computing means for {len(band_arrays)} bands ...")

    # ndi.mean works with an index array; faster than groupby for big rasters.
    means: dict[str, np.ndarray] = {}
    for name, arr in band_arrays.items():
        arr2 = np.where(np.isfinite(arr), arr, 0.0)
        means[name] = ndi.mean(arr2, labels=segments, index=seg_ids).astype("float32")

    # n_pixels per segment (only over valid mask)
    n_px = ndi.sum(valid.astype("float32"), labels=segments, index=seg_ids).astype("int32")

    # centroids (row, col) -> map (x, y)
    centroids = ndi.center_of_mass(valid.astype("uint8"), labels=segments, index=seg_ids)
    rows = np.array([c[0] for c in centroids], dtype="float32")
    cols = np.array([c[1] for c in centroids], dtype="float32")
    # rasterio xy: (row, col) -> (x, y) using the transform
    xs = transform.c + cols * transform.a + rows * transform.b
    ys = transform.f + cols * transform.d + rows * transform.e

    df = pd.DataFrame({
        "segment_id": seg_ids.astype("int32"),
        "n_pixels": n_px,
        "centroid_row": rows,
        "centroid_col": cols,
        "centroid_x": xs.astype("float64"),
        "centroid_y": ys.astype("float64"),
        "mean_B2": means["B2"],
        "mean_B3": means["B3"],
        "mean_B4": means["B4"],
        "mean_B8": means["B8"],
        "mean_NDVI": means["NDVI"],
        "mean_B11": means["B11"],
        "mean_NDBI": means["NDBI"],
    })

    out_pq = OUT / f"segment_features_{year}.parquet"
    out_csv = OUT / f"segment_features_{year}.csv"
    df.to_parquet(out_pq, index=False)
    df.to_csv(out_csv, index=False)
    print(f"[{year}] wrote {out_pq.name} and {out_csv.name}")
    print(df.describe().T[["min", "mean", "max", "std"]].round(3))


def main() -> None:
    for year, src in RASTERS.items():
        features_one(year, src)


if __name__ == "__main__":
    main()

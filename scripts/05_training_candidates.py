"""
05_training_candidates.py
-------------------------
Stratified random training-segment candidates for BOTH dates.

Stratification heuristic (uses ONLY segment-mean NDVI / NDBI / B8 — no
manual seeds). The heuristic just gets us _candidates_ that are likely
to belong to each class; Mohammad confirms the actual label.

Pool definitions:
  1 = Built-up                 NDBI >  0.00 AND NDVI < 0.30
  2 = Dense Vegetation         NDVI >  0.65
  3 = Mixed Veg / Cropland     0.30 <= NDVI <= 0.55
  4 = Bare / Open Land         NDVI <  0.20 AND -0.10 <= NDBI <= 0.10  AND mean_B8 > 1500
  5 = Water                    mean_B8 < 1500 AND NDVI < 0.25
                               (fallback: lowest-NIR 200 segments if pool < 8)

Outputs per year (year in {2016, 2024}):
  04_classification_OBIA/training_candidates_{year}.csv     <-- Mohammad fills `class`
  04_classification_OBIA/training_candidates_{year}.gpkg    (point geometries, EPSG:32644)
  04_classification_OBIA/training_overview_{year}.png       (overview map with numbered candidates)
  04_classification_OBIA/chips_{year}/seg_{id}.png          (RGB chips per candidate)

Reproducibility: numpy seed fixed so the same candidates come back on re-run.
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio
from rasterio.windows import Window
from shapely.geometry import Point

RAW = Path(r"D:\Dehradun_OBIA\01_raw_data")
SEG = Path(r"D:\Dehradun_OBIA\03_segmentation")
OBIA = Path(r"D:\Dehradun_OBIA\04_classification_OBIA")
OBIA.mkdir(parents=True, exist_ok=True)

RASTERS = {"2016": RAW / "Dehradun_2016.tif", "2024": RAW / "Dehradun_2024.tif"}
N_PER_CLASS = 8
RNG = np.random.default_rng(42)

CLASS_NAMES = {
    1: "Built-up",
    2: "Dense Vegetation",
    3: "Mixed Veg / Cropland",
    4: "Bare / Open Land",
    5: "Water",
}
CLASS_COLORS = {1: "#d7191c", 2: "#1a9850", 3: "#a6d96a",
                4: "#fdae61", 5: "#2c7bb6"}


def stratify(df: pd.DataFrame) -> dict[int, pd.DataFrame]:
    pools: dict[int, pd.DataFrame] = {}
    # Built-up
    pools[1] = df[(df.mean_NDBI > 0.00) & (df.mean_NDVI < 0.30)]
    # Dense vegetation
    pools[2] = df[df.mean_NDVI > 0.65]
    # Mixed veg / cropland
    pools[3] = df[(df.mean_NDVI >= 0.30) & (df.mean_NDVI <= 0.55)]
    # Bare / open
    pools[4] = df[(df.mean_NDVI < 0.20) & (df.mean_NDBI.between(-0.10, 0.10)) & (df.mean_B8 > 1500)]
    # Water  (pure water rare at 12-ha segments; use NIR + NDVI; fallback below)
    water_strict = df[(df.mean_B8 < 1500) & (df.mean_NDVI < 0.25)]
    if len(water_strict) < N_PER_CLASS:
        # fallback: 200 segments with lowest NIR, then sample
        water_strict = df.nsmallest(200, "mean_B8")
    pools[5] = water_strict
    return pools


def sample_candidates(pools: dict[int, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for cls, pool in pools.items():
        n = min(N_PER_CLASS, len(pool))
        if n == 0:
            print(f"  !! class {cls} ({CLASS_NAMES[cls]}): EMPTY POOL — please label some manually")
            continue
        picks = pool.sample(n=n, random_state=int(RNG.integers(0, 1_000_000)))
        picks = picks.assign(class_hint=cls, class_hint_name=CLASS_NAMES[cls])
        rows.append(picks)
        print(f"  class {cls} ({CLASS_NAMES[cls]}): pool={len(pool):4d}  sampled={n}")
    out = pd.concat(rows, ignore_index=True)
    out = out.sort_values("class_hint").reset_index(drop=True)
    out["label_id"] = range(1, len(out) + 1)
    return out


def write_chips(df: pd.DataFrame, year: str, src: Path) -> None:
    chips_dir = OBIA / f"chips_{year}"
    chips_dir.mkdir(exist_ok=True)
    half = 25  # 25 px = 250 m half-window
    with rasterio.open(src) as ds:
        H, W = ds.height, ds.width
        for _, row in df.iterrows():
            r = int(row.centroid_row)
            c = int(row.centroid_col)
            r0, r1 = max(0, r - half), min(H, r + half)
            c0, c1 = max(0, c - half), min(W, c + half)
            win = Window(c0, r0, c1 - c0, r1 - r0)
            b234 = np.stack([ds.read(b, window=win) for b in (3, 2, 1)], axis=-1)  # R G B
            arr = np.where(np.isfinite(b234), b234, 0.0)
            lo, hi = np.percentile(arr[arr > 0], [2, 98]) if (arr > 0).any() else (0, 1)
            rgb = np.clip((arr - lo) / (hi - lo + 1e-9), 0, 1)
            fig, ax = plt.subplots(figsize=(2.2, 2.2), dpi=110)
            ax.imshow(rgb)
            # crosshair on segment centroid
            ax.axhline(r - r0, color="yellow", lw=0.6)
            ax.axvline(c - c0, color="yellow", lw=0.6)
            ax.set_title(f"#{int(row.label_id)}  seg {int(row.segment_id)}\nhint: {row.class_hint_name}",
                         fontsize=7)
            ax.axis("off")
            fig.tight_layout(pad=0.2)
            fig.savefig(chips_dir / f"label_{int(row.label_id):03d}_seg{int(row.segment_id)}.png",
                        bbox_inches="tight")
            plt.close(fig)
    print(f"[{year}] wrote {len(df)} chips -> {chips_dir}")


def overview_map(df: pd.DataFrame, year: str, src: Path) -> None:
    with rasterio.open(src) as ds:
        # downsample factor for overview
        ds_factor = 4
        b234 = np.stack(
            [ds.read(b, out_shape=(ds.height // ds_factor, ds.width // ds_factor)) for b in (3, 2, 1)],
            axis=-1
        )
    arr = np.where(np.isfinite(b234), b234, 0.0)
    valid = arr[..., 0] > 0
    if valid.any():
        lo, hi = np.percentile(arr[valid], [2, 98])
    else:
        lo, hi = 0, 1
    rgb = np.clip((arr - lo) / (hi - lo + 1e-9), 0, 1)
    fig, ax = plt.subplots(figsize=(14, 8), dpi=140)
    ax.imshow(rgb)
    # rasterio pixel coords -> downsampled coords
    px_r = df.centroid_row.values / ds_factor
    px_c = df.centroid_col.values / ds_factor
    for _, row in df.iterrows():
        col = CLASS_COLORS[int(row.class_hint)]
        ax.scatter(row.centroid_col / ds_factor, row.centroid_row / ds_factor,
                   s=70, facecolors="none", edgecolors=col, lw=1.4)
        ax.text(row.centroid_col / ds_factor + 6, row.centroid_row / ds_factor - 4,
                f"{int(row.label_id)}", color=col, fontsize=7, weight="bold")
    handles = [mpatches.Patch(color=CLASS_COLORS[c], label=f"{c} {CLASS_NAMES[c]}")
               for c in sorted(CLASS_NAMES)]
    ax.legend(handles=handles, loc="lower right", fontsize=8, framealpha=0.85)
    ax.set_title(f"Training candidates — {year}  (RGB B4-B3-B2, numbers = label_id)")
    ax.axis("off")
    out = OBIA / f"training_overview_{year}.png"
    fig.tight_layout()
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    print(f"[{year}] overview map -> {out.name}")


def process(year: str, src: Path) -> None:
    print(f"\n[{year}] loading segment features")
    df = pd.read_parquet(OBIA / f"segment_features_{year}.parquet")
    print(f"[{year}] stratifying...")
    pools = stratify(df)
    cand = sample_candidates(pools)
    cand["class"] = ""  # to fill in
    cand["year"] = year

    cols = ["label_id", "year", "segment_id", "class_hint", "class_hint_name",
            "class",
            "centroid_x", "centroid_y", "mean_B2", "mean_B3", "mean_B4",
            "mean_B8", "mean_NDVI", "mean_NDBI", "mean_B11"]
    cand[cols].to_csv(OBIA / f"training_candidates_{year}.csv", index=False)

    geo = gpd.GeoDataFrame(
        cand[["label_id", "year", "segment_id", "class_hint", "class_hint_name", "class"]].copy(),
        geometry=[Point(xy) for xy in zip(cand.centroid_x, cand.centroid_y)],
        crs="EPSG:32644",
    )
    geo.to_file(OBIA / f"training_candidates_{year}.gpkg", layer=f"train_{year}", driver="GPKG")

    write_chips(cand, year, src)
    overview_map(cand, year, src)


def main() -> None:
    for year, src in RASTERS.items():
        process(year, src)


if __name__ == "__main__":
    main()

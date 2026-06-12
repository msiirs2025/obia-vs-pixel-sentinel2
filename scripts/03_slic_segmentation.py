"""
03_slic_segmentation.py
-----------------------
SLIC superpixel segmentation on both dates.

Settings (per the brief):
  - n_segments = 8000  (over the full raster; effective in-AOI count ~ 4000)
  - compactness = 10
  - features = B2, B3, B4, B8  (visible + NIR)

Notes / decisions baked in:
  - We segment over a 4-channel stack (B2 B3 B4 B8). Per-channel min-max
    normalization to [0, 1] is required because SLIC weights spatial vs
    spectral distance using `compactness`; un-normalized DN scales would
    dominate spatial distance.
  - Outside-AOI pixels are masked with `mask` argument to skimage.slic
    (>=0.18) so segments do not bleed into nodata. Outside-AOI ends up
    with label 0 (skimage's convention when mask=...).
  - We do NOT use `slic_zero` — fixed `compactness=10` matches the brief
    and gives more reproducible behaviour.
  - Output segment label raster is INT32 (8k segments fits in uint16 but
    a few extra labels can appear in masked-SLIC; int32 is safe and small
    after LZW compression).

Outputs (per year):
  03_segmentation/segments_{year}.tif      (int32, 1-based labels, 0 = outside AOI)
  03_segmentation/slic_log_{year}.txt      (small summary)
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import rasterio
from skimage.segmentation import slic

RAW = Path(r"D:\Dehradun_OBIA\01_raw_data")
PRE = Path(r"D:\Dehradun_OBIA\02_preprocessing")
OUT = Path(r"D:\Dehradun_OBIA\03_segmentation")
OUT.mkdir(parents=True, exist_ok=True)

RASTERS = {"2016": RAW / "Dehradun_2016.tif", "2024": RAW / "Dehradun_2024.tif"}

# Brief: SLIC on B2, B3, B4, B8 (1-based band indices in the source raster).
SLIC_BANDS = [1, 2, 3, 4]  # B2, B3, B4, B8
N_SEGMENTS = 8000
COMPACTNESS = 10.0


def per_channel_minmax(stack: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """Min-max scale each channel using only in-AOI pixels; nodata -> 0."""
    out = np.zeros_like(stack, dtype="float32")
    for i in range(stack.shape[-1]):
        chan = stack[..., i]
        vals = chan[valid]
        lo, hi = np.percentile(vals, [1, 99])  # robust to outliers
        if hi <= lo:
            hi = lo + 1.0
        scaled = (chan - lo) / (hi - lo)
        scaled = np.clip(scaled, 0.0, 1.0)
        scaled[~valid] = 0.0
        out[..., i] = scaled
    return out


def segment_one(year: str, path: Path) -> None:
    print(f"\n[{year}] reading bands {SLIC_BANDS} from {path.name}")
    t0 = time.time()
    with rasterio.open(path) as ds:
        profile = ds.profile.copy()
        height, width = ds.height, ds.width
        bands = [ds.read(b) for b in SLIC_BANDS]  # each (H, W) float32
    stack = np.stack(bands, axis=-1)  # (H, W, 4)

    with rasterio.open(PRE / f"valid_mask_{year}.tif") as mds:
        valid = mds.read(1).astype(bool)

    # NaN -> 0 for slic input (slic does not accept NaN); mask handles validity
    stack = np.where(np.isfinite(stack), stack, 0.0).astype("float32")

    print(f"[{year}] normalizing (per-channel p1-p99) ...")
    norm = per_channel_minmax(stack, valid)

    print(f"[{year}] running SLIC  n_segments={N_SEGMENTS}  compactness={COMPACTNESS} ...")
    t1 = time.time()
    # channel_axis=-1 because we have (H, W, C). start_label=1 so 0 can mean "outside AOI".
    labels = slic(
        norm,
        n_segments=N_SEGMENTS,
        compactness=COMPACTNESS,
        sigma=0,
        start_label=1,
        mask=valid,
        channel_axis=-1,
        enforce_connectivity=True,
        convert2lab=False,
    )
    t2 = time.time()
    # Outside AOI -> 0 (skimage sets masked area to 0 when mask is provided).
    labels = labels.astype("int32")
    labels[~valid] = 0

    unique = np.unique(labels[valid])
    n_seg = int(unique.size)
    seg_sizes = np.bincount(labels[valid])
    seg_sizes = seg_sizes[seg_sizes > 0]
    print(f"[{year}] SLIC done in {t2 - t1:.1f}s  ->  {n_seg} segments inside AOI")
    print(f"[{year}] segment size (pixels): min={seg_sizes.min()}  median={int(np.median(seg_sizes))}  "
          f"mean={seg_sizes.mean():.1f}  max={seg_sizes.max()}")

    out_path = OUT / f"segments_{year}.tif"
    profile.update(count=1, dtype="int32", nodata=0, compress="lzw")
    with rasterio.open(out_path, "w", **profile) as dst:
        dst.write(labels, 1)
    print(f"[{year}] wrote {out_path}  in {time.time() - t0:.1f}s total")

    log = [
        f"year={year}",
        f"source={path.name}",
        f"slic_bands_1based={SLIC_BANDS}",
        f"n_segments_requested={N_SEGMENTS}",
        f"compactness={COMPACTNESS}",
        f"n_segments_actual={n_seg}",
        f"seg_size_pixels_min={int(seg_sizes.min())}",
        f"seg_size_pixels_median={int(np.median(seg_sizes))}",
        f"seg_size_pixels_mean={float(seg_sizes.mean()):.2f}",
        f"seg_size_pixels_max={int(seg_sizes.max())}",
        f"slic_seconds={t2 - t1:.2f}",
    ]
    (OUT / f"slic_log_{year}.txt").write_text("\n".join(log), encoding="utf-8")


def main() -> None:
    for year, path in RASTERS.items():
        segment_one(year, path)


if __name__ == "__main__":
    main()

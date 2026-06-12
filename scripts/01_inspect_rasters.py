"""
01_inspect_rasters.py
---------------------
Inspect both Sentinel-2 composites before any heavy processing.

Confirms:
  * Band count, dtype, CRS, transform, dimensions, no-data
  * Per-band min/mean/max statistics (sampled, to keep this fast)
  * That the 12-band layout matches the brief:
      [B2, B3, B4, B8, B5, B6, B7, B8A, B11, B12, NDVI, NDBI]
  * NDVI / NDBI ranges look sane (~[-1, 1])
  * Both rasters are co-registered (same CRS, transform, shape)

Output: prints a structured report to stdout and saves it to
        02_preprocessing/raster_inspection.txt
"""

from __future__ import annotations

import sys
from pathlib import Path
from textwrap import indent

import numpy as np
import rasterio
from rasterio.windows import Window

RAW = Path(r"D:\Dehradun_OBIA\01_raw_data")
OUT = Path(r"D:\Dehradun_OBIA\02_preprocessing")
OUT.mkdir(parents=True, exist_ok=True)

BAND_NAMES = ["B2", "B3", "B4", "B8", "B5", "B6", "B7", "B8A", "B11", "B12", "NDVI", "NDBI"]
RASTERS = {
    "2016": RAW / "Dehradun_2016.tif",
    "2024": RAW / "Dehradun_2024.tif",
}

# Sample stride — full read of a 2-3k x 2-3k float32 12-band cube is fine on a laptop,
# but striding gives faster stats and still represents the distribution well.
STRIDE = 4


def describe(path: Path) -> str:
    lines: list[str] = []
    with rasterio.open(path) as ds:
        lines.append(f"file        : {path.name}")
        lines.append(f"driver      : {ds.driver}")
        lines.append(f"crs         : {ds.crs}")
        lines.append(f"transform   : {tuple(round(v, 4) for v in ds.transform[:6])}")
        lines.append(f"size (HxW)  : {ds.height} x {ds.width}")
        lines.append(f"pixel size  : {ds.transform.a:.3f} x {abs(ds.transform.e):.3f} m")
        lines.append(f"bands       : {ds.count}  (expected 12)")
        lines.append(f"dtypes      : {set(ds.dtypes)}")
        lines.append(f"nodata      : {ds.nodatavals}")

        # Approx extent in metres (UTM)
        l, b, r, t = ds.bounds
        lines.append(f"bounds      : L={l:.1f}  R={r:.1f}  B={b:.1f}  T={t:.1f}")
        lines.append(f"extent (km) : {(r - l) / 1000:.2f} x {(t - b) / 1000:.2f}")

        # Per-band stats on a strided sample to keep this snappy.
        sample = ds.read(out_shape=(ds.count, ds.height // STRIDE, ds.width // STRIDE))
        lines.append("")
        lines.append("Per-band stats (strided sample, NaN-aware):")
        lines.append(f"  {'idx':>3}  {'expected':>8}  {'min':>10}  {'mean':>10}  {'max':>10}  {'%nan':>6}")
        for i in range(ds.count):
            b = sample[i].astype("float64")
            n_nan = np.isnan(b).sum()
            if n_nan == b.size:
                mn = mx = mean = float("nan")
            else:
                mn, mx, mean = float(np.nanmin(b)), float(np.nanmax(b)), float(np.nanmean(b))
            label = BAND_NAMES[i] if i < len(BAND_NAMES) else "?"
            lines.append(
                f"  {i + 1:>3}  {label:>8}  {mn:>10.4f}  {mean:>10.4f}  {mx:>10.4f}  {100 * n_nan / b.size:>5.2f}%"
            )

        # Sanity checks
        warnings = []
        if ds.count != 12:
            warnings.append(f"!! expected 12 bands, found {ds.count}")
        if ds.crs is None or ds.crs.to_epsg() != 32644:
            warnings.append(f"!! expected EPSG:32644, found {ds.crs}")
        # NDVI / NDBI range check (last two bands by brief)
        for idx, name in [(10, "NDVI"), (11, "NDBI")]:
            if idx < ds.count:
                b = sample[idx].astype("float64")
                if not np.all(np.isnan(b)):
                    mn, mx = float(np.nanmin(b)), float(np.nanmax(b))
                    if mn < -1.05 or mx > 1.05:
                        warnings.append(f"!! {name} (band {idx + 1}) out of [-1,1] range: [{mn:.3f}, {mx:.3f}]")
        if warnings:
            lines.append("")
            lines.append("WARNINGS:")
            for w in warnings:
                lines.append(f"  {w}")

    return "\n".join(lines)


def compare(p_a: Path, p_b: Path) -> str:
    lines = ["Co-registration check (2016 vs 2024):"]
    with rasterio.open(p_a) as a, rasterio.open(p_b) as b:
        same_crs = a.crs == b.crs
        same_shape = (a.height, a.width) == (b.height, b.width)
        same_tr = tuple(a.transform)[:6] == tuple(b.transform)[:6]
        lines.append(f"  same CRS       : {same_crs}  ({a.crs} vs {b.crs})")
        lines.append(f"  same shape     : {same_shape}  ({a.height}x{a.width} vs {b.height}x{b.width})")
        lines.append(f"  same transform : {same_tr}")
        if not (same_crs and same_shape and same_tr):
            lines.append("  !! 2016 and 2024 rasters are NOT co-registered — reproject/align before classification.")
        else:
            lines.append("  OK — rasters share grid; per-pixel comparisons are safe.")
    return "\n".join(lines)


def main() -> int:
    report: list[str] = []
    report.append("=" * 78)
    report.append("Dehradun S2 composites — pre-processing inspection")
    report.append("=" * 78)
    report.append("")

    for tag, p in RASTERS.items():
        if not p.exists():
            report.append(f"[{tag}] MISSING file: {p}")
            continue
        report.append(f"[{tag}]")
        report.append(indent(describe(p), "  "))
        report.append("")

    if all(p.exists() for p in RASTERS.values()):
        report.append(compare(RASTERS["2016"], RASTERS["2024"]))
        report.append("")

    text = "\n".join(report)
    print(text)
    (OUT / "raster_inspection.txt").write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""
02_build_valid_mask.py
----------------------
Build the AOI valid-pixel mask and verify that every band carries real signal
INSIDE the AOI. The raw inspection showed B5/B6/B7/B8A/B11/B12 with very
narrow ranges in the strided sample. Hypothesis: outside-AOI got filled with
a constant for those six bands, while B2/B3/B4/B8/NDVI/NDBI got NaN. We need
to confirm the bands are usable inside the AOI before segmenting.

Outputs:
  02_preprocessing/valid_mask_2016.tif   (uint8, 1=valid, 0=outside)
  02_preprocessing/valid_mask_2024.tif
  02_preprocessing/inside_aoi_stats.txt
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio

RAW = Path(r"D:\Dehradun_OBIA\01_raw_data")
OUT = Path(r"D:\Dehradun_OBIA\02_preprocessing")
OUT.mkdir(parents=True, exist_ok=True)

BAND_NAMES = ["B2", "B3", "B4", "B8", "B5", "B6", "B7", "B8A", "B11", "B12", "NDVI", "NDBI"]
RASTERS = {"2016": RAW / "Dehradun_2016.tif", "2024": RAW / "Dehradun_2024.tif"}


def main() -> None:
    report: list[str] = []
    report.append("Inside-AOI band statistics")
    report.append("=" * 78)

    for year, path in RASTERS.items():
        with rasterio.open(path) as ds:
            # Use B4 (red) NaN to define the valid mask — it has ~49.6% NaN outside AOI.
            b4 = ds.read(3)  # band index 3 == B4 (1-based)
            valid = np.isfinite(b4)

            mask_path = OUT / f"valid_mask_{year}.tif"
            profile = ds.profile.copy()
            profile.update(count=1, dtype="uint8", nodata=0, compress="lzw")
            with rasterio.open(mask_path, "w", **profile) as dst:
                dst.write(valid.astype("uint8"), 1)
            report.append(f"\n[{year}]  valid pixels: {int(valid.sum()):,} / {valid.size:,} "
                          f"({100 * valid.mean():.2f}%)  -> {mask_path.name}")

            # Read every band and report min/mean/max/std INSIDE the AOI.
            report.append(f"  {'band':>6} {'min':>12} {'mean':>12} {'max':>12} {'std':>12} {'unique-ish':>12}")
            for i, name in enumerate(BAND_NAMES, start=1):
                arr = ds.read(i)
                vals = arr[valid]
                vals = vals[np.isfinite(vals)]
                if vals.size == 0:
                    report.append(f"  {name:>6}   (no finite pixels inside AOI)")
                    continue
                # rough cardinality probe: how many distinct rounded values?
                approx_unique = np.unique(np.round(vals, 2)).size
                report.append(
                    f"  {name:>6} {vals.min():12.3f} {vals.mean():12.3f} {vals.max():12.3f} "
                    f"{vals.std():12.3f} {approx_unique:>12,}"
                )

    text = "\n".join(report)
    print(text)
    (OUT / "inside_aoi_stats.txt").write_text(text, encoding="utf-8")
    print(f"\nReport saved to {OUT / 'inside_aoi_stats.txt'}")


if __name__ == "__main__":
    main()

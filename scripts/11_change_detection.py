"""
11_change_detection.py
----------------------
Cross-tabulate 2016 vs 2024 classifications for both methods, compute
class areas (ha) and an urbanization binary map (became built-up).

Outputs (per method in {obia, pixel}):
  07_change_detection/area_table_{method}.csv     (class areas + change in ha)
  07_change_detection/transition_{method}.csv     (5x5 transition matrix in ha)
  07_change_detection/urbanization_{method}.tif   (uint8; 1=became built-up, 0=other)
  07_change_detection/change_class_{method}.tif   (uint8 code = c2016*10 + c2024)
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import rasterio

OBIA = Path(r"D:\Dehradun_OBIA\04_classification_OBIA")
PIX = Path(r"D:\Dehradun_OBIA\05_classification_pixel")
OUT = Path(r"D:\Dehradun_OBIA\07_change_detection")
OUT.mkdir(parents=True, exist_ok=True)

PIX_HA = 0.01  # 10 m pixel = 100 m^2 = 0.01 ha

CLASS_NAMES = {1: "Built-up", 2: "Dense Veg", 3: "Mixed Veg/Crop", 4: "Bare/Open", 5: "Water"}

METHODS = {
    "obia": (OBIA / "obia_classified_2016.tif", OBIA / "obia_classified_2024.tif"),
    "pixel": (PIX / "pixel_classified_2016.tif", PIX / "pixel_classified_2024.tif"),
}


def process(method: str, p2016: Path, p2024: Path) -> None:
    with rasterio.open(p2016) as ds:
        a = ds.read(1)
        profile = ds.profile.copy()
    with rasterio.open(p2024) as ds:
        b = ds.read(1)
    valid = (a > 0) & (b > 0)
    n_valid = int(valid.sum())

    # Areas per year
    rows = []
    for c in [1, 2, 3, 4, 5]:
        n_a = int(((a == c) & valid).sum())
        n_b = int(((b == c) & valid).sum())
        rows.append({
            "class_id": c,
            "class_name": CLASS_NAMES[c],
            "area_2016_ha": n_a * PIX_HA,
            "area_2024_ha": n_b * PIX_HA,
            "change_ha": (n_b - n_a) * PIX_HA,
            "pct_2016": 100 * n_a / n_valid,
            "pct_2024": 100 * n_b / n_valid,
        })
    pd.DataFrame(rows).to_csv(OUT / f"area_table_{method}.csv", index=False)

    # 5x5 transition matrix in hectares
    tm = np.zeros((5, 5), dtype="int64")
    for i, c2016 in enumerate([1, 2, 3, 4, 5]):
        m_i = (a == c2016) & valid
        if not m_i.any():
            continue
        for j, c2024 in enumerate([1, 2, 3, 4, 5]):
            tm[i, j] = int((m_i & (b == c2024)).sum())
    tm_ha = tm * PIX_HA
    tm_df = pd.DataFrame(
        tm_ha,
        index=[f"2016_{CLASS_NAMES[c]}" for c in [1, 2, 3, 4, 5]],
        columns=[f"2024_{CLASS_NAMES[c]}" for c in [1, 2, 3, 4, 5]],
    )
    tm_df["row_total"] = tm_ha.sum(axis=1)
    tm_df.loc["col_total"] = list(tm_ha.sum(axis=0)) + [tm_ha.sum()]
    tm_df.to_csv(OUT / f"transition_{method}.csv")

    # Urbanization map: was not built-up in 2016, IS built-up in 2024
    urban = ((a != 1) & (b == 1) & valid).astype("uint8")
    profile_u = profile.copy()
    profile_u.update(dtype="uint8", count=1, nodata=255, compress="lzw")
    with rasterio.open(OUT / f"urbanization_{method}.tif", "w", **profile_u) as dst:
        out = np.where(valid, urban, 255).astype("uint8")
        dst.write(out, 1)

    # change-class raster: 2-digit code c16*10 + c24 (so e.g. veg->built = 21)
    change_code = np.zeros_like(a, dtype="uint8")
    change_code[valid] = (a[valid].astype("uint16") * 10 + b[valid].astype("uint16")).astype("uint8")
    with rasterio.open(OUT / f"change_class_{method}.tif", "w", **profile_u) as dst:
        out = np.where(valid, change_code, 0).astype("uint8")
        dst.write(out, 1)

    urban_ha = int(urban.sum()) * PIX_HA
    print(f"[{method}] new built-up 2016->2024 = {urban_ha:.1f} ha "
          f"({urban_ha / 100:.2f} km²)")
    print(f"[{method}] class areas (ha):")
    print(pd.DataFrame(rows)[["class_name", "area_2016_ha", "area_2024_ha", "change_ha"]].to_string(index=False))


def main() -> None:
    for method, (p16, p24) in METHODS.items():
        if not (p16.exists() and p24.exists()):
            print(f"[{method}] missing classified rasters, skipping")
            continue
        process(method, p16, p24)


if __name__ == "__main__":
    main()

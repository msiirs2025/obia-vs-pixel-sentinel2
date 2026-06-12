"""
05b_training_kml.py
-------------------
Export training candidates as KML for visual verification in Google Earth Pro.
Each placemark name = `[hint] L{label_id} seg{segment_id}` so you can sort
in GE Pro by class and just blast through them.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import simplekml
from pyproj import Transformer

OBIA = Path(r"D:\Dehradun_OBIA\04_classification_OBIA")

# UTM 44N (EPSG:32644) -> WGS84 lon/lat (EPSG:4326)
TR = Transformer.from_crs("EPSG:32644", "EPSG:4326", always_xy=True)

CLASS_COLORS_KML = {
    1: simplekml.Color.red,        # Built-up
    2: simplekml.Color.green,      # Dense Vegetation
    3: simplekml.Color.yellowgreen, # Mixed Veg/Crop
    4: simplekml.Color.orange,     # Bare
    5: simplekml.Color.blue,       # Water
}


def export(year: str) -> None:
    df = pd.read_csv(OBIA / f"training_candidates_{year}.csv")
    kml = simplekml.Kml(name=f"training candidates {year}")
    for cls_id, name in [(1, "Built-up"), (2, "Dense Veg"),
                         (3, "Mixed Veg / Crop"), (4, "Bare / Open"), (5, "Water")]:
        folder = kml.newfolder(name=f"{cls_id} {name}")
        sub = df[df.class_hint == cls_id]
        for _, row in sub.iterrows():
            lon, lat = TR.transform(row.centroid_x, row.centroid_y)
            p = folder.newpoint(
                name=f"L{int(row.label_id)}  seg{int(row.segment_id)}  ({row.class_hint_name})",
                coords=[(lon, lat)],
                description=(
                    f"label_id: {int(row.label_id)}\n"
                    f"hint class: {int(row.class_hint)} ({row.class_hint_name})\n"
                    f"NDVI: {row.mean_NDVI:.3f}\n"
                    f"NDBI: {row.mean_NDBI:.3f}\n"
                    f"B8 (NIR): {row.mean_B8:.0f}\n"
                    f"---\n"
                    f"TRUE CLASS = ?\n"
                ),
            )
            p.style.iconstyle.color = CLASS_COLORS_KML[cls_id]
            p.style.iconstyle.scale = 1.1
            p.style.labelstyle.scale = 0.8
    out = OBIA / f"training_candidates_{year}.kml"
    kml.save(str(out))
    print(f"[{year}] wrote {out}")


if __name__ == "__main__":
    for year in ("2016", "2024"):
        export(year)

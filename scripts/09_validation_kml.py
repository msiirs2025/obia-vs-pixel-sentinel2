"""
09_validation_kml.py
--------------------
Generate stratified random validation points for both dates and export
to KML for Google Earth Pro.

Stratification: stratify on the OBIA classified raster (per the brief —
classifier outputs define the strata). 15 points per class per date,
75 per date, 150 total.

Outputs:
  06_validation/validation_points_{year}.gpkg     (geometries + class_obia,
                                                    class_pixel pre-filled)
  06_validation/validation_points_{year}.csv      (Mohammad fills `class_true`)
  06_validation/validation_points_{year}.kml
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import simplekml
from pyproj import Transformer
from shapely.geometry import Point

OBIA = Path(r"D:\Dehradun_OBIA\04_classification_OBIA")
PIX = Path(r"D:\Dehradun_OBIA\05_classification_pixel")
OUT = Path(r"D:\Dehradun_OBIA\06_validation")
OUT.mkdir(parents=True, exist_ok=True)

N_PER_CLASS = 15
RNG = np.random.default_rng(2026)

CLASS_NAMES = {1: "Built-up", 2: "Dense Veg", 3: "Mixed Veg/Crop", 4: "Bare/Open", 5: "Water"}
CLASS_COLORS_KML = {
    1: simplekml.Color.red, 2: simplekml.Color.green,
    3: simplekml.Color.yellowgreen, 4: simplekml.Color.orange, 5: simplekml.Color.blue,
}

TR = Transformer.from_crs("EPSG:32644", "EPSG:4326", always_xy=True)


def generate(year: str) -> None:
    obia_tif = OBIA / f"obia_classified_{year}.tif"
    pix_tif = PIX / f"pixel_classified_{year}.tif"
    with rasterio.open(obia_tif) as ds:
        obia_arr = ds.read(1)
        transform = ds.transform
        H, W = ds.height, ds.width
    with rasterio.open(pix_tif) as ds:
        pix_arr = ds.read(1)

    rows: list[dict] = []
    pid = 1
    for cls in [1, 2, 3, 4, 5]:
        ys, xs = np.where(obia_arr == cls)
        if len(ys) == 0:
            print(f"  !! {year} class {cls} has no pixels in OBIA map — skipping")
            continue
        n = min(N_PER_CLASS, len(ys))
        sel = RNG.choice(len(ys), size=n, replace=False)
        for k in sel:
            r, c = int(ys[k]), int(xs[k])
            x = transform.c + (c + 0.5) * transform.a + (r + 0.5) * transform.b
            y = transform.f + (c + 0.5) * transform.d + (r + 0.5) * transform.e
            lon, lat = TR.transform(x, y)
            rows.append({
                "point_id": pid,
                "year": year,
                "stratum_class": cls,
                "stratum_name": CLASS_NAMES[cls],
                "class_obia": int(obia_arr[r, c]),
                "class_pixel": int(pix_arr[r, c]),
                "class_true": "",
                "x_utm": x,
                "y_utm": y,
                "lon": lon,
                "lat": lat,
                "row": r,
                "col": c,
            })
            pid += 1
    df = pd.DataFrame(rows)
    df.to_csv(OUT / f"validation_points_{year}.csv", index=False)
    gdf = gpd.GeoDataFrame(
        df.drop(columns=["lon", "lat"]),
        geometry=[Point(x, y) for x, y in zip(df.x_utm, df.y_utm)],
        crs="EPSG:32644",
    )
    gdf.to_file(OUT / f"validation_points_{year}.gpkg", layer=f"val_{year}", driver="GPKG")

    kml = simplekml.Kml(name=f"validation {year}")
    for cls in [1, 2, 3, 4, 5]:
        sub = df[df["stratum_class"] == cls]
        folder = kml.newfolder(name=f"{cls} {CLASS_NAMES[cls]}")
        for _, r in sub.iterrows():
            p = folder.newpoint(
                name=f"V{int(r.point_id)}  obia={int(r.class_obia)}  pix={int(r.class_pixel)}",
                coords=[(r.lon, r.lat)],
                description=(
                    f"point_id: {int(r.point_id)}\n"
                    f"year: {year}\n"
                    f"OBIA prediction: {int(r.class_obia)} ({CLASS_NAMES[int(r.class_obia)] if r.class_obia in CLASS_NAMES else '?'})\n"
                    f"Pixel prediction: {int(r.class_pixel)} ({CLASS_NAMES[int(r.class_pixel)] if r.class_pixel in CLASS_NAMES else '?'})\n"
                    f"---\n"
                    f"TRUE CLASS = ?  (prepend digit 1..5 to placemark name)\n"
                ),
            )
            p.style.iconstyle.color = CLASS_COLORS_KML[cls]
            p.style.iconstyle.scale = 1.0
            p.style.labelstyle.scale = 0.7
    kml_path = OUT / f"validation_points_{year}.kml"
    kml.save(str(kml_path))
    print(f"[{year}] {len(df)} validation points -> {kml_path.name}")


def main() -> None:
    for year in ("2016", "2024"):
        generate(year)


if __name__ == "__main__":
    main()

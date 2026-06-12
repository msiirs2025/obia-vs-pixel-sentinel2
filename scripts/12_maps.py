"""
12_maps.py
----------
Matplotlib maps + area chart for the slide deck:

  * obia_map_{year}.png       — OBIA classified map per year
  * pixel_map_{year}.png      — pixel classified map per year
  * change_map_{method}.png   — urbanization (red) + persistent built-up (grey)
  * area_chart.png            — class area 2016 vs 2024 for both methods
  * obia_vs_pixel_2024.png    — side-by-side classified comparison

Maps share a fixed 5-class colormap matching the slide deck convention.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio
from matplotlib.colors import ListedColormap

OBIA = Path(r"D:\Dehradun_OBIA\04_classification_OBIA")
PIX = Path(r"D:\Dehradun_OBIA\05_classification_pixel")
CHG = Path(r"D:\Dehradun_OBIA\07_change_detection")
OUT = Path(r"D:\Dehradun_OBIA\08_maps_final")
OUT.mkdir(parents=True, exist_ok=True)

CLASS_NAMES = {1: "Built-up", 2: "Dense Veg", 3: "Mixed Veg/Crop", 4: "Bare/Open", 5: "Water"}
CLASS_COLORS = {
    0: "#ffffff",          # nodata / outside AOI -> white
    1: "#d7191c",          # built-up — red
    2: "#1a9850",          # dense veg — dark green
    3: "#a6d96a",          # mixed veg — light green
    4: "#fdae61",          # bare — orange
    5: "#2c7bb6",          # water — blue
}
CMAP = ListedColormap([CLASS_COLORS[i] for i in range(6)])


def _imshow(ax, arr):
    ax.imshow(arr, cmap=CMAP, vmin=0, vmax=5, interpolation="nearest")
    ax.axis("off")


def _legend_outside(ax_or_fig, where="ax"):
    """Place class legend OUTSIDE the map axes so it never covers data.
       For single-axes maps: legend hung off the right margin.
       For figure-level: bottom-center, single row."""
    handles = [mpatches.Patch(color=CLASS_COLORS[c], label=f"{c} {CLASS_NAMES[c]}")
               for c in [1, 2, 3, 4, 5]]
    if where == "ax":
        ax_or_fig.legend(handles=handles, loc="upper left",
                         bbox_to_anchor=(1.01, 1.0),
                         fontsize=10, framealpha=1.0,
                         title="Land cover", title_fontsize=11,
                         borderpad=0.6)
    else:
        ax_or_fig.legend(handles=handles, loc="lower center",
                         ncol=5, fontsize=10, frameon=False,
                         bbox_to_anchor=(0.5, -0.02))


def classified_map(tif: Path, title: str, out: Path) -> None:
    with rasterio.open(tif) as ds:
        arr = ds.read(1)
    # extra width to host the right-margin legend without overlapping data
    fig, ax = plt.subplots(figsize=(13, 6.5), dpi=160)
    _imshow(ax, arr)
    ax.set_title(title, fontsize=12)
    _legend_outside(ax, where="ax")
    fig.tight_layout()
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)


def side_by_side(tif_a: Path, tif_b: Path, title_a: str, title_b: str, out: Path) -> None:
    with rasterio.open(tif_a) as ds:
        a = ds.read(1)
    with rasterio.open(tif_b) as ds:
        b = ds.read(1)
    fig, axes = plt.subplots(1, 2, figsize=(15, 6.8), dpi=160)
    _imshow(axes[0], a); axes[0].set_title(title_a)
    _imshow(axes[1], b); axes[1].set_title(title_b)
    _legend_outside(fig, where="fig")
    fig.tight_layout(rect=(0, 0.07, 1, 1))
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)


def urbanization_map(method: str) -> None:
    tif = CHG / f"urbanization_{method}.tif"
    with rasterio.open(OBIA / f"obia_classified_2024.tif" if method == "obia"
                       else PIX / f"pixel_classified_2024.tif") as ds:
        bu_2024 = ds.read(1) == 1
    with rasterio.open(OBIA / f"obia_classified_2016.tif" if method == "obia"
                       else PIX / f"pixel_classified_2016.tif") as ds:
        bu_2016 = ds.read(1) == 1
    with rasterio.open(tif) as ds:
        urban = ds.read(1)
    persistent = bu_2016 & bu_2024
    new_urban = urban == 1
    # 0 nodata white, 1 persistent grey, 2 new urban red, 3 background light
    disp = np.zeros_like(urban, dtype="uint8")
    valid = (urban != 255)
    disp[valid] = 3                     # background
    disp[persistent & valid] = 1        # persistent BU
    disp[new_urban] = 2                 # new BU

    palette = ListedColormap(["#ffffff", "#666666", "#d7191c", "#f0f0f0"])
    fig, ax = plt.subplots(figsize=(13, 6.5), dpi=160)
    ax.imshow(disp, cmap=palette, vmin=0, vmax=3, interpolation="nearest")
    ax.axis("off")
    new_ha = int(new_urban.sum()) * 0.01
    pers_ha = int(persistent.sum()) * 0.01
    ax.set_title(f"Urbanization 2016 → 2024 ({method.upper()})\n"
                 f"new built-up = {new_ha:,.0f} ha    persistent built-up = {pers_ha:,.0f} ha",
                 fontsize=12)
    handles = [
        mpatches.Patch(color="#d7191c", label="New built-up (2016 → 2024)"),
        mpatches.Patch(color="#666666", label="Persistent built-up"),
        mpatches.Patch(color="#f0f0f0", label="Other / unchanged"),
    ]
    # legend in the right margin, outside the map
    ax.legend(handles=handles, loc="upper left",
              bbox_to_anchor=(1.01, 1.0),
              fontsize=10, framealpha=1.0,
              title="Change class", title_fontsize=11,
              borderpad=0.6)
    fig.tight_layout()
    fig.savefig(OUT / f"change_map_{method}.png", bbox_inches="tight")
    plt.close(fig)


def area_chart() -> None:
    obia = pd.read_csv(CHG / "area_table_obia.csv")
    pix = pd.read_csv(CHG / "area_table_pixel.csv")
    # one solid colour per year — legend swatches now match the bars exactly.
    COL_2016 = "#4C78A8"   # blue
    COL_2024 = "#F58518"   # orange
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.0), dpi=160, sharey=True)
    width = 0.38
    for ax, df, name in zip(axes, [obia, pix], ["OBIA", "Pixel-based"]):
        x = np.arange(len(df))
        ax.bar(x - width / 2, df["area_2016_ha"], width, label="2016",
               color=COL_2016, edgecolor="black", lw=0.5)
        ax.bar(x + width / 2, df["area_2024_ha"], width, label="2024",
               color=COL_2024, edgecolor="black", lw=0.5)
        ax.set_xticks(x)
        ax.set_xticklabels(df["class_name"], rotation=20, ha="right", fontsize=10)
        ax.set_title(name, fontsize=12)
        ax.set_ylabel("Area (ha)")
        # annotate change (Δ in ha)
        for i, row in df.iterrows():
            ch = row["change_ha"]
            ax.annotate(f"{ch:+,.0f}", (i, max(row["area_2016_ha"], row["area_2024_ha"])),
                        ha="center", va="bottom", fontsize=9,
                        color="#1a9850" if ch < 0 else "#d7191c",
                        fontweight="bold")
        ax.grid(axis="y", alpha=0.3)
    handles = [mpatches.Patch(color=COL_2016, label="2016"),
               mpatches.Patch(color=COL_2024, label="2024")]
    fig.legend(handles=handles, loc="upper right", fontsize=11, frameon=True,
               bbox_to_anchor=(0.99, 0.97))
    fig.suptitle("Class area 2016 vs 2024  (Δ in ha annotated)", fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(OUT / "area_chart.png", bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    print("[maps] classified per-year maps...")
    classified_map(OBIA / "obia_classified_2016.tif", "OBIA classified — 2016", OUT / "obia_map_2016.png")
    classified_map(OBIA / "obia_classified_2024.tif", "OBIA classified — 2024", OUT / "obia_map_2024.png")
    classified_map(PIX / "pixel_classified_2016.tif", "Pixel-based classified — 2016", OUT / "pixel_map_2016.png")
    classified_map(PIX / "pixel_classified_2024.tif", "Pixel-based classified — 2024", OUT / "pixel_map_2024.png")
    print("[maps] OBIA vs pixel 2024 side-by-side...")
    side_by_side(OBIA / "obia_classified_2024.tif", PIX / "pixel_classified_2024.tif",
                 "OBIA — 2024", "Pixel-based — 2024", OUT / "obia_vs_pixel_2024.png")
    print("[maps] change maps...")
    urbanization_map("obia")
    urbanization_map("pixel")
    print("[maps] area chart...")
    area_chart()
    print(f"[maps] all PNGs -> {OUT}")


if __name__ == "__main__":
    main()

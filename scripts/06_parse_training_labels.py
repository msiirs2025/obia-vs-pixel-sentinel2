"""
06_parse_training_labels.py
---------------------------
Parse Mohammad's labeled KMZ files back into a training table.

Convention: he prepended the true class digit (1..5) to each placemark name.
e.g. original "L5 seg2341 (Built-up)" -> "1 L5 seg2341 (Built-up)".

We:
  * unzip KMZ -> KML
  * parse placemark names with a regex looking for leading "[1-5] L<id>"
    OR a label in the description, falling back to the original label_id
  * join back to training_candidates_{year}.csv on label_id
  * write training_labeled_{year}.csv with `class` filled

If any placemarks didn't get a leading class digit, we print them so Mohammad
can spot-fix in the CSV.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pandas as pd

OBIA = Path(r"D:\Dehradun_OBIA\04_classification_OBIA")
NS = {"kml": "http://www.opengis.net/kml/2.2"}

NAME_RE = re.compile(r"^\s*(?P<cls>[1-5])\b.*?L\s*(?P<lid>\d+)", re.IGNORECASE)
FALLBACK_LID_RE = re.compile(r"L\s*(?P<lid>\d+)", re.IGNORECASE)


def kmz_to_kml_bytes(kmz: Path) -> bytes:
    with zipfile.ZipFile(kmz) as z:
        kml_names = [n for n in z.namelist() if n.lower().endswith(".kml")]
        if not kml_names:
            raise RuntimeError(f"No .kml inside {kmz}")
        with z.open(kml_names[0]) as f:
            return f.read()


def parse_kml(kml_bytes: bytes) -> list[dict]:
    root = ET.fromstring(kml_bytes)
    out = []
    for pm in root.iter("{http://www.opengis.net/kml/2.2}Placemark"):
        name_el = pm.find("kml:name", NS)
        desc_el = pm.find("kml:description", NS)
        name = (name_el.text or "").strip() if name_el is not None else ""
        desc = (desc_el.text or "").strip() if desc_el is not None else ""
        m = NAME_RE.match(name)
        if m:
            out.append({"label_id": int(m.group("lid")),
                        "class": int(m.group("cls")),
                        "raw_name": name})
            continue
        # fall back: maybe class is in the name but elsewhere; try first digit anywhere
        m_lid = FALLBACK_LID_RE.search(name)
        if m_lid:
            # look for any leading "true_class=" style hint in description (none for us,
            # but Mohammad might have edited it)
            m_cls_desc = re.search(r"true\s*class\s*[:=]\s*([1-5])", desc, re.IGNORECASE)
            cls_val = int(m_cls_desc.group(1)) if m_cls_desc else None
            out.append({"label_id": int(m_lid.group("lid")),
                        "class": cls_val,
                        "raw_name": name})
    return out


def process(year: str) -> None:
    kmz = OBIA / f"training_candidates_{year}_labeled.kmz"
    cand = pd.read_csv(OBIA / f"training_candidates_{year}.csv")
    parsed = parse_kml(kmz_to_kml_bytes(kmz))
    p_df = pd.DataFrame(parsed)
    if p_df.empty:
        raise RuntimeError(f"[{year}] parsed zero placemarks — check KMZ contents")

    merged = cand.drop(columns=["class"]).merge(p_df, on="label_id", how="left")
    missing = merged[merged["class"].isna()]
    bad_cls = merged[~merged["class"].isin([1, 2, 3, 4, 5]) & merged["class"].notna()]

    print(f"\n[{year}]  placemarks parsed = {len(p_df)}  /  candidates = {len(cand)}")
    if len(missing) > 0:
        print(f"[{year}]  !! {len(missing)} candidates have no class — placemark names that didn't match:")
        print(missing[["label_id", "class_hint", "class_hint_name"]].to_string(index=False))
    if len(bad_cls) > 0:
        print(f"[{year}]  !! {len(bad_cls)} candidates have invalid class values")
        print(bad_cls[["label_id", "class"]].to_string(index=False))
    # confusion-with-hint count
    agree = (merged["class"] == merged["class_hint"]).sum()
    print(f"[{year}]  hint == labelled: {agree}/{len(merged)} ({100*agree/len(merged):.0f}%)")

    # Class distribution
    print(f"[{year}]  labelled class counts:")
    print(merged["class"].value_counts().sort_index().to_string())

    out_csv = OBIA / f"training_labeled_{year}.csv"
    cols = ["label_id", "year", "segment_id", "class", "class_hint", "class_hint_name",
            "centroid_x", "centroid_y", "mean_B2", "mean_B3", "mean_B4",
            "mean_B8", "mean_NDVI", "mean_NDBI", "mean_B11", "raw_name"]
    merged[cols].to_csv(out_csv, index=False)
    print(f"[{year}]  wrote {out_csv.name}")


def main() -> None:
    for year in ("2016", "2024"):
        process(year)


if __name__ == "__main__":
    main()

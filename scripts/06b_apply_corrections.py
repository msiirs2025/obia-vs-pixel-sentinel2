"""
06b_apply_corrections.py
------------------------
Apply Mohammad's hand-corrected labels on top of the hint-as-truth baseline.

Default class = class_hint, then overwrite the listed L-IDs.
Writes back to training_candidates_{year}.csv (which 07_/08_ read directly).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

OBIA = Path(r"D:\Dehradun_OBIA\04_classification_OBIA")

CORRECTIONS = {
    "2016": {1: 3, 17: 2, 19: 1, 20: 1, 30: 1, 34: 1, 36: 1, 39: 3, 40: 1},
    "2024": {2: 4, 5: 4, 22: 1, 25: 1, 28: 1, 31: 1, 35: 1, 36: 4, 38: 1},
}

CLASS_NAMES = {1: "Built-up", 2: "Dense Veg", 3: "Mixed Veg/Crop", 4: "Bare/Open", 5: "Water"}


def main() -> None:
    for year, corrs in CORRECTIONS.items():
        df = pd.read_csv(OBIA / f"training_candidates_{year}.csv")
        df["class"] = df["class_hint"].astype(int)  # default
        applied = 0
        for lid, new_cls in corrs.items():
            mask = df["label_id"] == lid
            if mask.any():
                old = int(df.loc[mask, "class"].iloc[0])
                df.loc[mask, "class"] = int(new_cls)
                print(f"[{year}] L{lid:>2}: {old} ({CLASS_NAMES[old]}) -> {new_cls} ({CLASS_NAMES[new_cls]})")
                applied += 1
            else:
                print(f"[{year}] L{lid}: NOT FOUND in candidates — skipping")
        df.to_csv(OBIA / f"training_candidates_{year}.csv", index=False)
        df.to_csv(OBIA / f"training_labeled_{year}.csv", index=False)
        print(f"[{year}] applied {applied}/{len(corrs)} corrections")
        print(f"[{year}] final class counts: {df['class'].value_counts().sort_index().to_dict()}")
        print()


if __name__ == "__main__":
    main()

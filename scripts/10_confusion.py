"""
10_confusion.py
---------------
Compute confusion matrices, overall accuracy, kappa, and per-class
producer/user accuracy for both methods on both dates.

Reads Mohammad's labelled validation CSVs (`class_true` filled with 1..5)
and the OBIA + pixel classified rasters (the predictions are already in
the CSV as class_obia and class_pixel).

Outputs:
  06_validation/accuracy_summary.csv         (one row per method x year)
  06_validation/confusion_{method}_{year}.csv
  06_validation/confusion_{method}_{year}.png
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import cohen_kappa_score, confusion_matrix

OUT = Path(r"D:\Dehradun_OBIA\06_validation")
CLASS_IDS = [1, 2, 3, 4, 5]
CLASS_NAMES = {1: "Built-up", 2: "Dense Veg", 3: "Mixed Veg/Crop", 4: "Bare/Open", 5: "Water"}


def per_method(year: str, method: str, df: pd.DataFrame) -> dict:
    pred_col = "class_obia" if method == "obia" else "class_pixel"
    sub = df.dropna(subset=["class_true"])
    sub = sub[sub["class_true"].isin(CLASS_IDS)]
    if sub.empty:
        raise RuntimeError(f"[{year}/{method}] no usable rows with class_true in 1..5")
    y_true = sub["class_true"].astype(int).values
    y_pred = sub[pred_col].astype(int).values
    cm = confusion_matrix(y_true, y_pred, labels=CLASS_IDS)
    oa = (y_true == y_pred).mean()
    kappa = cohen_kappa_score(y_true, y_pred, labels=CLASS_IDS)

    # producer & user accuracy
    pa = np.zeros(5, dtype=float)
    ua = np.zeros(5, dtype=float)
    f1 = np.zeros(5, dtype=float)
    for i, c in enumerate(CLASS_IDS):
        tp = cm[i, i]
        row = cm[i, :].sum()  # actual class i
        col = cm[:, i].sum()  # predicted class i
        pa[i] = tp / row if row else 0.0
        ua[i] = tp / col if col else 0.0
        f1[i] = 2 * pa[i] * ua[i] / (pa[i] + ua[i]) if (pa[i] + ua[i]) else 0.0

    # write CSV of confusion matrix
    cm_df = pd.DataFrame(cm,
                         index=[f"true_{CLASS_NAMES[c]}" for c in CLASS_IDS],
                         columns=[f"pred_{CLASS_NAMES[c]}" for c in CLASS_IDS])
    cm_df["PA"] = pa
    cm_df.loc["UA"] = list(ua) + [np.nan]
    cm_df.loc["F1"] = list(f1) + [np.nan]
    cm_df.to_csv(OUT / f"confusion_{method}_{year}.csv")

    # PNG
    fig, ax = plt.subplots(figsize=(5.4, 4.5), dpi=140)
    im = ax.imshow(cm, cmap="Blues")
    ax.set_xticks(range(5))
    ax.set_yticks(range(5))
    ax.set_xticklabels([CLASS_NAMES[c] for c in CLASS_IDS], rotation=30, ha="right")
    ax.set_yticklabels([CLASS_NAMES[c] for c in CLASS_IDS])
    ax.set_xlabel("Predicted")
    ax.set_ylabel("Reference (true)")
    for i in range(5):
        for j in range(5):
            ax.text(j, i, cm[i, j], ha="center", va="center",
                    color="black" if cm[i, j] < cm.max() / 2 else "white", fontsize=9)
    method_name = "OBIA" if method == "obia" else "Pixel-based"
    ax.set_title(f"{method_name} confusion — {year}\n"
                 f"OA={oa:.2%}   κ={kappa:.2f}   n={len(sub)}")
    fig.tight_layout()
    fig.savefig(OUT / f"confusion_{method}_{year}.png", bbox_inches="tight")
    plt.close(fig)

    return {
        "year": year,
        "method": method_name,
        "n_val": int(len(sub)),
        "OA": float(oa),
        "Kappa": float(kappa),
        **{f"PA_{CLASS_NAMES[c]}": float(pa[i]) for i, c in enumerate(CLASS_IDS)},
        **{f"UA_{CLASS_NAMES[c]}": float(ua[i]) for i, c in enumerate(CLASS_IDS)},
        **{f"F1_{CLASS_NAMES[c]}": float(f1[i]) for i, c in enumerate(CLASS_IDS)},
    }


def main() -> None:
    summary: list[dict] = []
    for year in ("2016", "2024"):
        df = pd.read_csv(OUT / f"validation_points_{year}.csv")
        df["class_true"] = pd.to_numeric(df["class_true"], errors="coerce")
        for method in ("obia", "pixel"):
            row = per_method(year, method, df)
            summary.append(row)
            print(f"[{year} / {row['method']:>11}]  OA={row['OA']:.2%}   kappa={row['Kappa']:.2f}   n={row['n_val']}")
    pd.DataFrame(summary).to_csv(OUT / "accuracy_summary.csv", index=False)
    print(f"\nWrote {OUT / 'accuracy_summary.csv'}")


if __name__ == "__main__":
    main()

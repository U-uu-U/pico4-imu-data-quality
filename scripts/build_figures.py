"""Publication figures regenerated from the current evidence, in grayscale."""
from pathlib import Path
from collections import defaultdict
import csv
import argparse
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, FancyArrowPatch

ROOT = Path(__file__).resolve().parents[1]
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                     "svg.fonttype": "none", "pdf.fonttype": 42})


def save(fig, name):
    folder = ROOT / "figures"
    folder.mkdir(exist_ok=True)
    for ext in ("png", "svg", "pdf"):
        fig.savefig(folder / f"{name}.{ext}", dpi=360, facecolor="white")
    plt.close(fig)


def workflow():
    fig, ax = plt.subplots(figsize=(6.82, 2.72))
    fig.subplots_adjust(left=.008, right=.992, top=.98, bottom=.02)
    ax.set(xlim=(0, 14), ylim=(0, 5.4))
    ax.axis("off")
    xs = [0.08, 3.64, 7.20, 10.76]
    w, h = 3.15, 1.04
    rows = [
        (3.6, ["30 CSV exports\n29 retained sessions", "Audit timestamps\nand numeric fields",
               "2.0 s histories\nReset after long gaps", "Six-rule outputs\nChannel-gated audit"]),
        (1.12, ["19 video candidates\n10 selected sessions", "Read rater labels\nand saved offsets",
               "Join 661 shared\none-second intervals", "Three-group\nagreement"]),
    ]
    for y, labels in rows:
        for x, label in zip(xs, labels):
            ax.add_patch(Rectangle((x, y), w, h, facecolor="#F5F5F5", edgecolor="#454545", linewidth=.8))
            ax.text(x+w/2, y+h/2, label, ha="center", va="center", fontsize=9.4, linespacing=1.4)
        for x in xs[:-1]:
            ax.add_patch(FancyArrowPatch((x+w+.02, y+h/2), (x+3.56-.03, y+h/2),
                                        arrowstyle="-|>", mutation_scale=10, color="#454545", linewidth=.9))
    x = xs[2]+w/2
    ax.add_patch(FancyArrowPatch((x, 3.57), (x, 2.19), arrowstyle="-|>", mutation_scale=11,
                                color="#454545", linewidth=.9))
    ax.text(x+.2, 2.9, "Separate\ngyro-based rules", ha="left", va="center", fontsize=9)
    ax.text(.08, 5.08, "NUMERIC EXPORT ANALYSIS", fontsize=9, weight="bold", va="center")
    ax.text(.08, 2.6, "ANNOTATION RECORDS", fontsize=9, weight="bold", va="center")
    ax.text(7, .32, "Post hoc timing groups: 27 ADB-like + 2 browser-compatible; historical source not retained.",
            ha="center", va="center", fontsize=8.6)
    save(fig, "figure1_reanalysis_workflow")


def composition():
    with (ROOT / "evidence" / "exact_output_counts.csv").open(encoding="utf-8-sig") as f:
        rows = [r for r in csv.DictReader(f) if r["taxonomy"] == "six"]
    keys = ["rapid_turn_rule", "smooth_turn_rule", "moderate_turn_rule", "acceleration_excursion_rule",
            "low_motion_rule", "residual_rule_output"]
    labels = ["Rapid-turn", "Smooth-turn*", "Moderate-turn", "Acceleration-excursion",
              "Euler-conditioned\nlow-motion*", "Residual output"]
    fig, ax = plt.subplots(figsize=(6.82, 3.48))
    fig.subplots_adjust(left=.30, right=.98, bottom=.17, top=.78)
    specs = [("ADB-like", "ADB-like: 27 sessions; 40,119 samples", "o", "#222222", -.17),
             ("S001", "S001: 3,000 samples", "s", "#999999", 0),
             ("S009", "S009: 2,441 samples", "^", "white", .17)]
    for group, legend, marker, color, shift in specs:
        vals = []
        for key in keys:
            selected = [r for r in rows if r["output"] == key and
                        (r["path_group"] == group if group == "ADB-like" else r["session_id"] == group)]
            vals.append(100*sum(int(r["assigned_count"]) for r in selected)/sum(int(r["session_samples"]) for r in selected))
        ax.scatter(vals, [i+shift for i in range(6)], marker=marker, s=32, facecolors=color,
                   edgecolors="#222222", linewidths=.8, label=legend, zorder=3)
    ax.set(yticks=range(6), yticklabels=labels, xlim=(-1, 80), ylim=(5.5, -.6))
    ax.set_xlabel("Fraction of retained exported samples (%)", fontsize=10)
    ax.tick_params(axis="both", labelsize=10)
    ax.grid(axis="x", color="#DEDEDE", linewidth=.6)
    ax.set_axisbelow(True)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(loc="lower left", bbox_to_anchor=(-.04, 1.01), frameon=False, fontsize=9.5,
              handletextpad=.65, borderaxespad=0, labelspacing=.4)
    save(fig, "figure2_output_composition")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, default=ROOT)
    args = parser.parse_args()
    ROOT = args.output_root
    workflow()
    composition()

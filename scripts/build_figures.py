#!/usr/bin/env python3
"""Build publication-ready figures from the audited evidence tables.

PNG files are used by the manuscript builder. SVG companions are written for
later vector editing in Illustrator or another graphics editor.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Patch


BLUE = "#3D607A"
GOLD = "#B28728"
TEAL = "#71808D"
RED = "#6F7780"
INK = "#263442"
MUTED = "#71808D"
GRID = "#E3E9EE"
PALE_BLUE = "#EAF0F4"
PALE_GOLD = "#F5F0E5"
PALE_TEAL = "#EEF1F3"
USABLE = "#D7E0E6"
FROZEN = "#7D8790"
WHITE = "#FFFFFF"

GROUP_COLORS = {"ADB-like": BLUE, "browser-compatible": GOLD}
RULE_LABELS = {
    "rapid_turn_rule": "Rapid turn",
    "smooth_turn_rule": "Smooth turn",
    "moderate_turn_rule": "Moderate turn",
    "acceleration_excursion_rule": "Acceleration excursion",
    "low_motion_rule": "Low motion",
    "residual_rule_output": "Residual output",
}
RULE_COLORS = [INK, BLUE, BLUE, TEAL, MUTED, INK]

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 9,
    "axes.titlesize": 11,
    "axes.labelsize": 9,
    "axes.edgecolor": MUTED,
    "axes.linewidth": 0.8,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "text.color": INK,
    "savefig.facecolor": WHITE,
    "figure.facecolor": WHITE,
})


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def session_sort(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return sorted(rows, key=lambda r: int(r["session_id"][1:]))


def style_axis(ax, title: str, subtitle: str | None = None):
    ax.set_title(title, loc="left", fontweight="bold", pad=15, color=INK)
    if subtitle:
        ax.text(0, 1.015, subtitle, transform=ax.transAxes, color=MUTED, va="bottom", fontsize=8)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def panel_label(ax, label: str):
    # Panel letters are included in the sub-panel titles to prevent clipping.
    return None


def save_figure(fig, out: Path, stem: str):
    fig.savefig(out / f"{stem}.png", dpi=420, bbox_inches="tight", pad_inches=0.12)
    fig.savefig(out / f"{stem}.svg", format="svg", bbox_inches="tight", pad_inches=0.12)
    plt.close(fig)


def figure1(out: Path):
    fig, ax = plt.subplots(figsize=(12, 6.2))
    ax.set_xlim(0, 12); ax.set_ylim(0, 7.0); ax.axis("off")
    fig.suptitle("Archived acquisition implementations and evidence boundary", x=0.055, y=0.98,
                 ha="left", fontsize=15, fontweight="bold", color=INK)
    ax.plot([0, 12], [6.58, 6.58], color=GRID, linewidth=1.2)

    def box(x, y, w, h, title, body, color, fill=WHITE):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.05",
                                    facecolor=fill, edgecolor=color, linewidth=1.7))
        ax.add_patch(FancyBboxPatch((x, y + h - 0.38), w, 0.38,
                                    boxstyle="round,pad=0.02,rounding_size=0.05",
                                    facecolor=color, edgecolor=color, linewidth=0))
        ax.text(x + 0.16, y + h - 0.24, title, color=WHITE, fontsize=9, fontweight="bold", va="center")
        ax.text(x + w / 2, y + h / 2 - 0.08, body, ha="center", va="center", fontsize=8.3, color=INK)

    ax.text(0.05, 6.22, "Archived implementation layer", fontsize=10.5, fontweight="bold", color=MUTED)
    box(0.05, 4.55, 2.45, 1.2, "ADB implementation", "sensorservice parser\nand Python sender", BLUE, PALE_BLUE)
    box(0.05, 2.95, 2.45, 1.2, "Browser implementation", "WebXR or DeviceMotion\nbrowser sender", GOLD, PALE_GOLD)
    box(3.45, 3.55, 2.55, 1.55, "Computer bridge", "WebSocket relay,\ndata mapper, dashboard", TEAL, PALE_TEAL)
    box(6.95, 3.55, 2.25, 1.55, "CSV archive", "timestamps, magnitudes,\nEuler fields, stored labels", INK, "#F2F4F6")
    box(10.0, 3.55, 1.95, 1.55, "Audit", "QC, recomputation,\nsensitivity, agreement", MUTED, "#F2F4F6")

    def arrow(x1, y1, x2, y2, color):
        ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=13,
                                     linewidth=1.8, color=color))

    arrow(2.5, 5.15, 3.45, 4.65, BLUE)
    arrow(2.5, 3.55, 3.45, 4.0, GOLD)
    arrow(6.0, 4.32, 6.95, 4.32, TEAL)
    arrow(9.2, 4.32, 10.0, 4.32, RED)

    ax.text(6.05, 2.70, "Timing groups assigned after export", ha="center", color=MUTED,
            fontsize=9.5, fontweight="bold")
    # The branch line terminates at the centers of the two output boxes.
    ax.plot([8.08, 8.08], [3.54, 2.35], color=INK, linewidth=1.4)
    ax.plot([3.55, 8.60], [2.35, 2.35], color=INK, linewidth=1.4)
    ax.plot([3.55, 3.55], [2.35, 1.92], color=INK, linewidth=1.4)
    ax.plot([8.60, 8.60], [2.35, 1.92], color=INK, linewidth=1.4)
    ax.add_patch(FancyArrowPatch((8.08, 2.7), (8.08, 2.38), arrowstyle="-|>", mutation_scale=12,
                                 linewidth=1.4, color=INK))
    box(1.95, 0.55, 3.2, 1.35, "ADB-like", "27 retained files;\nsource not recorded", BLUE, PALE_BLUE)
    box(7.0, 0.55, 3.2, 1.35, "Browser-compatible", "2 retained files;\nbranch not recoverable", GOLD, PALE_GOLD)
    fig.subplots_adjust(left=0.02, right=0.98, top=0.9, bottom=0.04)
    save_figure(fig, out, "figure1_compatibility_architecture")


def figure2(out: Path):
    fig = plt.figure(figsize=(12, 5.85))
    gs = fig.add_gridspec(1, 2, width_ratios=[1.08, 0.92], wspace=0.20)
    ax1 = fig.add_subplot(gs[0, 0]); ax2 = fig.add_subplot(gs[0, 1])
    fig.suptitle("Exported field semantics and channel-gated rule outputs", x=0.055, y=0.98,
                 ha="left", fontsize=15, fontweight="bold", color=INK)

    ax1.axis("off"); panel_label(ax1, "A")
    ax1.set_title("A. Exported fields do not preserve source semantics", loc="left", fontweight="bold", pad=11)
    columns = ["Timing group", "Field", "Interpretation in the audit"]
    rows = [
        ["ADB-like", "gyroMag", "Lower-rate timing; source field not retained"],
        ["Browser-\ncompatible", "gyroMag", "Higher-rate timing;\nbrowser branch not recoverable"],
        ["All exports", "accMag", "Magnitude retained;\nraw acceleration axes absent"],
        ["All exports", "roll / pitch /\nyaw", "Frozen in 28 of 29 retained sessions"],
    ]
    table = ax1.table(cellText=rows, colLabels=columns, cellLoc="center", colLoc="center",
                      colWidths=[0.27, 0.18, 0.55], bbox=[0.0, 0.24, 1.0, 0.66])
    table.auto_set_font_size(False); table.set_fontsize(8.65)
    for (r, c), cell in table.get_celld().items():
        cell.set_edgecolor("#CCD5DC"); cell.set_linewidth(0.75); cell.PAD = 0.20
        if r == 0:
            cell.set_facecolor(INK); cell.get_text().set_color(WHITE); cell.get_text().set_weight("bold")
        else:
            cell.set_facecolor(PALE_BLUE if r % 2 else WHITE)
            if c == 0:
                cell.get_text().set_color(BLUE if r == 1 else GOLD if r == 2 else MUTED)
                cell.get_text().set_weight("bold")
    ax1.text(0.0, 0.20, "Cross-group physical equivalence is not assumed.", color=MUTED,
             fontsize=9.2, fontweight="bold")
    ax1.text(0.0, 0.11, "Timing groups remain separate when outputs are interpreted.",
             color=MUTED, fontsize=8.3)

    ax2.axis("off"); panel_label(ax2, "B")
    ax2.set_title("B. Deterministic priority with channel gates", loc="left", fontweight="bold", pad=11)
    rules = [
        ("1", "Rapid turn", "gyro > 1.5 or window SD > 0.8"),
        ("2", "Smooth turn", "requires usable Euler fields"),
        ("3", "Moderate turn", "0.3 <= gyro <= 1.5"),
        ("4", "Acceleration excursion", "disabled when accMag is frozen"),
        ("5", "Low motion", "requires usable Euler fields"),
        ("6", "Residual output", "fallback; not true idle"),
    ]
    y_positions = np.linspace(0.84, 0.14, len(rules))
    for (num, name, note), y, color in zip(rules, y_positions, RULE_COLORS):
        ax2.add_patch(FancyBboxPatch((0.0, y - 0.050), 1.0, 0.096,
                                     boxstyle="round,pad=0.01,rounding_size=0.012",
                                     facecolor=WHITE, edgecolor="#CCD5DC", linewidth=0.8))
        ax2.add_patch(FancyBboxPatch((0.0, y - 0.050), 0.16, 0.096,
                                     boxstyle="round,pad=0.01,rounding_size=0.012",
                                     facecolor=color, edgecolor=color, linewidth=0))
        ax2.text(0.08, y, num, ha="center", va="center", color=WHITE, fontsize=10, fontweight="bold")
        ax2.text(0.21, y + 0.014, name, va="center", fontsize=8.8, fontweight="bold")
        ax2.text(0.21, y - 0.020, note, va="center", fontsize=7.9, color=MUTED)
    fig.text(0.055, 0.025, "Rule outputs are deterministic labels generated after channel gating; they are not validated behavior classes.",
             color=MUTED, fontsize=7.9)
    fig.subplots_adjust(left=0.055, right=0.98, top=0.87, bottom=0.10)
    save_figure(fig, out, "figure2_field_semantics_and_rules")


def figure3(evidence: Path, out: Path):
    qc = session_sort([r for r in read_csv(evidence / "session_qc.csv") if r["included"] == "true"])
    sessions = [r["session_id"] for r in qc]
    x = np.arange(len(qc))
    rates = np.array([float(r["median_export_rate_hz"]) for r in qc])
    colors = [GROUP_COLORS[r["path_group"]] for r in qc]

    fig, ax = plt.subplots(figsize=(12, 4.25))
    fig.suptitle("Export-timing heterogeneity across retained sessions", x=0.055, y=0.98,
                 ha="left", fontsize=15, fontweight="bold", color=INK)
    panel_label(ax, "A"); style_axis(ax, "A. Median export rate by retained session", "Hz; derived from positive timestamp intervals")
    ax.scatter(x, rates, s=62, c=colors, edgecolor=WHITE, linewidth=0.8, zorder=3)
    ax.vlines(x, 0, rates, colors=colors, alpha=0.28, linewidth=2.2)
    ax.set_ylim(0, max(22, rates.max() * 1.14)); ax.set_ylabel("Export rate (Hz)")
    ax.set_xlim(-0.75, len(qc) - 0.25)
    # Keep every session in the data series but label alternating ticks for legibility.
    labels = [s[1:] if i % 2 == 0 or i in (len(sessions) - 1,) else "" for i, s in enumerate(sessions)]
    ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=8.0)
    ax.tick_params(axis="x", length=3, pad=4)
    ax.legend(handles=[Patch(color=BLUE, label="ADB-like (n=27)"), Patch(color=GOLD, label="Browser-compatible (n=2)")],
              loc="upper right", frameon=False, ncol=2, fontsize=8)
    fig.text(0.055, 0.025, "Timing groups are export-pattern groups; they do not establish hardware sampling rates or physical equivalence.",
             color=MUTED, fontsize=7.8)
    fig.subplots_adjust(left=0.075, right=0.985, top=0.84, bottom=0.22)
    save_figure(fig, out, "figure3_export_timing_heterogeneity")


def figure4(evidence: Path, out: Path):
    qc = session_sort([r for r in read_csv(evidence / "session_qc.csv") if r["included"] == "true"])
    summary = read_csv(evidence / "rule_distribution_summary.csv")
    fig = plt.figure(figsize=(12, 7.0))
    gs = fig.add_gridspec(1, 2, width_ratios=[0.88, 1.12], wspace=0.30)
    ax1 = fig.add_subplot(gs[0, 0]); ax2 = fig.add_subplot(gs[0, 1])
    fig.suptitle("Channel availability and rule outputs by timing group", x=0.055, y=0.98,
                 ha="left", fontsize=15, fontweight="bold", color=INK)

    panel_label(ax1, "A"); ax1.set_title("A. Channel-usability audit (A = ADB-like; B = browser-compatible)", loc="left", fontweight="bold", pad=12)
    vals = np.array([[r["gyro_usable"] == "true", r["acc_usable_for_excursion_rule"] == "true",
                      r["euler_usable_for_window_rules"] == "true"] for r in qc], dtype=int)
    ax1.imshow(vals, aspect="auto", interpolation="none",
               cmap=plt.matplotlib.colors.ListedColormap([FROZEN, USABLE]), vmin=0, vmax=1)
    ax1.set_xticks([0, 1, 2], ["Gyro", "Acceleration", "Euler"])
    ax1.set_yticks(np.arange(len(qc)), [r["session_id"] for r in qc], fontsize=7.3)
    ax1.tick_params(length=0, pad=3); ax1.set_xlabel("Channel gate")
    ax1.set_xticks(np.arange(-.5, 3, 1), minor=True); ax1.set_yticks(np.arange(-.5, len(qc), 1), minor=True)
    ax1.grid(which="minor", color=WHITE, linewidth=1.6); ax1.tick_params(which="minor", bottom=False, left=False)
    for y, r in enumerate(qc):
        ax1.text(3.1, y, "B" if r["path_group"] == "browser-compatible" else "A", ha="center", va="center",
                 fontsize=7.5, fontweight="bold", color=GROUP_COLORS[r["path_group"]])
    ax1.set_xlim(-0.5, 3.55)
    ax1.legend(handles=[Patch(color=USABLE, label="usable"), Patch(color=FROZEN, label="frozen / unavailable")],
               loc="lower left", bbox_to_anchor=(0, -0.18), frameon=False, ncol=2, fontsize=7.7)

    panel_label(ax2, "B"); ax2.set_title("B. Time-sample-weighted rule-output fractions", loc="left", fontweight="bold", pad=12)
    groups = ["ADB-like", "browser-compatible"]
    lookup = {(r["path_group"], r["output"]): float(r["time_sample_weighted_fraction"]) * 100 for r in summary}
    y = np.arange(len(RULE_LABELS))
    height = 0.33
    a = np.array([lookup[(groups[0], key)] for key in RULE_LABELS])
    b = np.array([lookup[(groups[1], key)] for key in RULE_LABELS])
    ax2.barh(y - height / 2, a, height=height, color=BLUE, label="ADB-like (n=27)")
    ax2.barh(y + height / 2, b, height=height, color=GOLD, label="Browser-compatible (n=2)")
    ax2.set_yticks(y, list(RULE_LABELS.values())); ax2.invert_yaxis(); ax2.set_xlabel("Fraction of exported time samples (%)")
    ax2.set_xlim(0, max(80, max(a.max(), b.max()) * 1.16)); ax2.grid(axis="x", color=GRID, linewidth=0.8); ax2.set_axisbelow(True)
    ax2.spines["top"].set_visible(False); ax2.spines["right"].set_visible(False)
    for yi, value in zip(y - height / 2, a): ax2.text(value + 0.7, yi, f"{value:.1f}", va="center", fontsize=7.5, color=BLUE)
    for yi, value in zip(y + height / 2, b): ax2.text(value + 0.7, yi, f"{value:.1f}", va="center", fontsize=7.5, color=GOLD)
    ax2.legend(frameon=False, loc="upper right", fontsize=8)
    fig.text(0.055, 0.015, "A/B are timing-compatible groups assigned from export intervals; residual output is a fallback, not true idle behavior.", color=MUTED, fontsize=7.8)
    fig.subplots_adjust(left=0.08, right=0.98, top=0.89, bottom=0.12)
    save_figure(fig, out, "figure4_channel_quality_and_compatibility_outputs")


def figure5(evidence: Path, out: Path):
    rows = read_csv(evidence / "ablation_summary.csv")
    configs = [
        ("no_window", "No window"), ("legacy_21_samples", "21 samples"),
        ("time_window_0.5s", "0.5 s"), ("time_window_1s", "1.0 s"),
        ("time_window_4s", "4.0 s"), ("priority_moderate_before_smooth", "Priority swap"),
    ]
    lookup = {(r["configuration"], r["path_group"]): float(r["weighted_output_change_fraction_vs_2s"]) * 100 for r in rows}
    fig, ax = plt.subplots(figsize=(12, 5.9))
    fig.suptitle("Window and priority ablations", x=0.055, y=0.985, ha="left", fontsize=15,
                 fontweight="bold", color=INK)
    panel_label(ax, "A")
    style_axis(ax, "A. Output changes relative to the primary 2.0 s rules", "Weighted across exported samples within each timing group")
    y = np.arange(len(configs))
    a = np.array([lookup[(key, "ADB-like")] for key, _ in configs])
    b = np.array([lookup[(key, "browser-compatible")] for key, _ in configs])
    ax.hlines(y, 0, np.maximum(a, b), color=GRID, linewidth=1.3, zorder=0)
    ax.scatter(a, y - 0.12, s=68, color=BLUE, edgecolor=WHITE, linewidth=0.7, label="ADB-like (n=27)", zorder=3)
    ax.scatter(b, y + 0.12, s=68, color=GOLD, edgecolor=WHITE, linewidth=0.7, label="Browser-compatible (n=2)", zorder=3)
    ax.axvline(0, color=MUTED, linewidth=0.8)
    ax.set_yticks(y, [label for _, label in configs]); ax.invert_yaxis()
    ax.set_xlabel("Changed outputs (%)"); ax.set_xlim(0, max(60, b.max() * 1.15)); ax.grid(axis="x", color=GRID, linewidth=0.8)
    for yi, value in zip(y - 0.12, a): ax.text(value + 0.8, yi, f"{value:.1f}", va="center", fontsize=8, color=BLUE)
    for yi, value in zip(y + 0.12, b): ax.text(value + 0.8, yi, f"{value:.1f}", va="center", fontsize=8, color=GOLD)
    ax.legend(frameon=False, loc="lower right", ncol=2, fontsize=8)
    fig.text(0.055, 0.02, "Higher values indicate greater sensitivity of the deterministic software output; they are not accuracy estimates.",
             color=MUTED, fontsize=7.8)
    fig.subplots_adjust(left=0.16, right=0.98, top=0.87, bottom=0.14)
    save_figure(fig, out, "figure5_window_and_priority_ablation")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    evidence, out = args.output_root / "evidence", args.output_root / "figures"
    out.mkdir(parents=True, exist_ok=True)
    for stale in ("figure1_route_aware_architecture", "figure4_channel_quality_and_path_outputs",
                  "figure3_sampling_and_window_normalization",
                  "figure6_annotation_agreement", "contact_sheet"):
        for suffix in (".png", ".svg"):
            (out / f"{stale}{suffix}").unlink(missing_ok=True)
    figure1(out); figure2(out); figure3(evidence, out); figure4(evidence, out); figure5(evidence, out)
    print("Generated 5 figures and SVG editing companions")


if __name__ == "__main__":
    main()

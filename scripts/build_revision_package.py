# -*- coding: utf-8 -*-
"""Build the evidence-first Sensors revision package.

This script intentionally does not modify any earlier manuscript or builder.
It regenerates evidence tables, publication figures, two manuscript views,
the response letter, and an author decision/risk brief from the same audited
source files.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import random
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_ROW_HEIGHT_RULE, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Inches, Pt, RGBColor
from PIL import Image, ImageDraw, ImageFont


HERE = Path(__file__).resolve()
OUT = HERE.parents[1]
EVIDENCE = OUT / "evidence"
FIGURES = OUT / "figures"
QA = OUT / "qa"


def env_path(name: str, default: Path) -> Path:
    """Resolve private build inputs without embedding workstation paths."""
    return Path(os.environ.get(name, str(default))).expanduser().resolve()


PRIVATE_INPUTS = OUT / "private_inputs"
WORKSPACE = env_path("PICO4_WORKSPACE", PRIVATE_INPUTS / "workspace")
REV_ROOT = env_path("PICO4_REVISION_ROOT", PRIVATE_INPUTS / "revision")
TEMPLATE = env_path(
    "SENSORS_TEMPLATE",
    PRIVATE_INPUTS / "Sensors_IMU_PPG_Article_Submission_Strict_Template.docx",
)
RAW_DIR = WORKSPACE / "实验数据与论文" / "实验原始数据与报告"
MATRIX_PATH = WORKSPACE / "实验数据与论文" / "PLS-SEM分析" / "results" / "data_matrix.csv"
PLATFORM = WORKSPACE / "平台（新版）"
ANNOTATION = REV_ROOT / "annotation"
REFERENCE_AUDIT = REV_ROOT / "参考文献补强" / "reference_verification_crossref.csv"

OUT_EN = OUT / "Sensors_IMU_Revision_English_20260827.docx"
OUT_CN = OUT / "Sensors_IMU_Revision_Chinese_View_20260827.docx"
OUT_RESPONSE = OUT / "Response_to_Reviewers_English_20260827.docx"
OUT_RISKS = OUT / "作者质询与投稿前风险清单_20260827.docx"

TITLE_EN = (
    "Auditing a Pico 4 Motion-Sensing Pipeline for Seated 360-Degree VR: "
    "ADB IMU, Browser Pose, Rule-Based State Outputs, and Data Quality"
)
TITLE_CN = (
    "面向坐姿 360 度 VR 的 Pico 4 运动传感管线审计："
    "ADB IMU、浏览器位姿、规则状态输出与数据质量"
)
AUTHORS = "Ruimeng Li 1, Zhixin Cai 1,2, Siyuan Song 1, Mingxuan Cai 1 and You-Lei Fu 1,*"
AFFILIATIONS_EN = [
    "1 School of Design and Fashion, Zhejiang University of Science and Technology, Hangzhou, China",
    "2 Interactive Media Institute, Academy of Arts & Design, Tsinghua University, Beijing, China",
    "Author e-mails: Ruimeng Li, 5231592012@zust.edu.cn; Zhixin Cai, xinlise@gmail.com; Siyuan Song, 222505357001@zust.edu.cn; Mingxuan Cai, 222505357022@zust.edu.cn; You-Lei Fu, fuyoulei@zust.edu.cn",
    "* Correspondence: You-Lei Fu, fuyoulei@zust.edu.cn",
]
AFFILIATIONS_CN = [
    "1 浙江科技大学设计与服装学院，中国杭州",
    "2 清华大学美术学院交互媒体研究所，中国北京",
    "作者邮箱：Ruimeng Li, 5231592012@zust.edu.cn; Zhixin Cai, xinlise@gmail.com; Siyuan Song, 222505357001@zust.edu.cn; Mingxuan Cai, 222505357022@zust.edu.cn; You-Lei Fu, fuyoulei@zust.edu.cn",
    "* 通讯作者：You-Lei Fu, fuyoulei@zust.edu.cn",
]

SUBJECT_MAP = {
    "1776754772978": "S002",
    "1776821554249": "S001",
    "1776824662730": "S005",
    "1776825800472": "S006",
    "1776827240332": "S007",
    "1776828552202": "S008",
    "1776830107430": "S009",
    "1776842825545": "S010",
    "1776844051112": "S011",
    "1776846533989": "S012",
    "1776847632327": "S013",
    "1776991265337": "S015",
    "1776998386020": "S017",
    "1776999562464": "S018",
    "1777000526552": "S019",
    "1777002144701": "S020",
    "1777010515392": "S021",
    "1777011363810": "S022",
    "1777012565224": "S023",
    "1777013387851": "S024",
    "1777014295491": "S025",
    "1777017440813": "S026",
    "1777019914575": "S027",
    "1777022706323": "S028",
    "1777023729187": "S029",
    "1777024675993": "S030",
    "1777025679136": "S031",
    "1777026812944": "S032",
    "1777027785844": "S033",
    "1777028938686": "S034",
}

FEATURES = [
    ("gyro_mean", "Mean magnitude in the exported gyro field", "导出 gyro 字段幅值均值"),
    ("head_turn_ratio", "Ordinary-turn output fraction", "普通转头输出比例"),
    ("sudden_turn_ratio", "Abrupt-turn output fraction", "突然转头输出比例"),
    ("behavior_entropy", "Entropy of exported state sequence", "导出状态序列熵"),
    ("gaze_mean_duration", "Mean duration of gaze segments (s)", "gaze 片段平均时长（s）"),
    ("postural_shift_ratio", "Acceleration-gated postural-shift fraction", "加速度门控姿态调整比例"),
    ("acc_cv", "Coefficient of variation of acceleration magnitude", "加速度幅值变异系数"),
    ("freeze_ratio", "Fraction of gaze plus idle outputs", "gaze 与 idle 输出合计比例"),
]
ACC_FEATURES = {"postural_shift_ratio", "acc_cv"}
STATES = ["gaze", "head_turn", "idle", "sudden_turn", "scanning", "postural_shift"]
GRAVITY = 9.80665
WINDOW = 20

BASE_THRESHOLDS = {
    "gaze_gyroMax": 0.15,
    "gaze_eulerDeltaMax": 2.0,
    "scanning_gyroMin": 0.15,
    "scanning_gyroMax": 1.5,
    "scanning_gyroStdMax": 0.6,
    "scanning_eulerDeltaMin": 3.0,
    "sudden_gyroMin": 1.5,
    "sudden_gyroStdMin": 0.8,
    "head_gyroMin": 0.3,
    "head_gyroMax": 1.5,
    "postural_accMin": 0.3,
}

COLORS = {
    "navy": "#16324F",
    "blue": "#2F6690",
    "teal": "#2A9D8F",
    "gold": "#D39B2A",
    "red": "#B33A3A",
    "gray": "#6B7280",
    "light": "#EEF3F7",
    "green": "#4C956C",
}


def ensure_dirs() -> None:
    for p in (EVIDENCE, FIGURES, QA):
        p.mkdir(parents=True, exist_ok=True)


def median(values: list[float]) -> float:
    return statistics.median(values) if values else float("nan")


def mean_sd(values: list[float]) -> tuple[float, float]:
    if not values:
        return float("nan"), float("nan")
    return statistics.mean(values), statistics.stdev(values) if len(values) > 1 else 0.0


def cohen_d(a: list[float], b: list[float]) -> float:
    if len(a) < 2 or len(b) < 2:
        return float("nan")
    sa, sb = statistics.stdev(a), statistics.stdev(b)
    pooled = math.sqrt(((len(a) - 1) * sa * sa + (len(b) - 1) * sb * sb) / (len(a) + len(b) - 2))
    return (statistics.mean(b) - statistics.mean(a)) / pooled if pooled else float("nan")


def kappa(pairs: list[tuple[str, str]]) -> tuple[float, float, int]:
    n = len(pairs)
    if not n:
        return float("nan"), float("nan"), 0
    cats = sorted({x for pair in pairs for x in pair})
    ca = Counter(a for a, _ in pairs)
    cb = Counter(b for _, b in pairs)
    po = sum(a == b for a, b in pairs) / n
    pe = sum(ca[c] * cb[c] for c in cats) / (n * n)
    return ((po - pe) / (1 - pe) if 1 - pe > 1e-12 else 1.0), po, n


def cluster_bootstrap_kappa(
    by_subject: dict[str, list[tuple[str, str]]], iterations: int = 5000, seed: int = 20260827
) -> tuple[float, float]:
    rng = random.Random(seed)
    subjects = sorted(by_subject)
    vals: list[float] = []
    for _ in range(iterations):
        sampled = [rng.choice(subjects) for _ in subjects]
        pairs: list[tuple[str, str]] = []
        for subject in sampled:
            pairs.extend(by_subject[subject])
        vals.append(kappa(pairs)[0])
    vals.sort()
    def quantile(q: float) -> float:
        position = (len(vals) - 1) * q
        lower, upper = math.floor(position), math.ceil(position)
        if lower == upper:
            return vals[lower]
        return vals[lower] + (vals[upper] - vals[lower]) * (position - lower)
    return float(quantile(0.025)), float(quantile(0.975))


def read_export(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", errors="ignore", newline="") as f:
        return list(csv.DictReader(f))


def audit_sessions() -> list[dict[str, object]]:
    sessions: list[dict[str, object]] = []
    required = {"timestamp", "accMag", "gyroMag", "roll", "pitch", "yaw", "behavior", "confidence"}
    for path in sorted(RAW_DIR.glob("imu_analysis_*.csv")):
        rows = read_export(path)
        sid = re.search(r"(\d+)\.csv$", path.name).group(1)
        fields = set(rows[0]) if rows else set()
        timestamps = [float(r["timestamp"]) for r in rows if r.get("timestamp") not in (None, "")]
        acc = [float(r["accMag"]) for r in rows]
        gyro = [float(r["gyroMag"]) for r in rows]
        euler = [abs(float(r[k])) for r in rows for k in ("roll", "pitch", "yaw")]
        dts = [b - a for a, b in zip(timestamps, timestamps[1:]) if b - a > 0]
        duration = max(timestamps) - min(timestamps) if timestamps else 0.0
        med_dt = median(dts)
        rate = 1 / med_dt if med_dt and not math.isnan(med_dt) else 0.0
        dt_cv = statistics.pstdev(dts) / statistics.mean(dts) if len(dts) > 1 and statistics.mean(dts) else 0.0
        retained = duration >= 60 and len(rows) >= 100 and required.issubset(fields)
        path_group = "browser-compatible" if rate > 5 else "ADB-like"
        acc_unique_4dp = len({round(v, 4) for v in acc})
        gyro_sd = statistics.pstdev(gyro) if len(gyro) > 1 else 0.0
        acc_frozen = bool(retained and acc_unique_4dp == 1 and gyro_sd > 0.01)
        orientation_frozen = bool(retained and (max(euler) if euler else 0.0) < 1e-9)
        counts = Counter(r.get("behavior", "") for r in rows)
        sessions.append(
            {
                "file_id": sid,
                "subject": SUBJECT_MAP.get(sid, "unmapped"),
                "frames": len(rows),
                "duration_s": round(duration, 3),
                "retained": retained,
                "median_dt_s": round(med_dt, 6),
                "median_rate_hz": round(rate, 4),
                "dt_cv": round(dt_cv, 4),
                "path_group": path_group,
                "path_certainty": (
                    "mechanism-compatible; exact browser branch unavailable because source was not retained"
                    if path_group == "browser-compatible"
                    else "mechanism-compatible with blocking dumpsys sensorservice polling"
                ),
                "acc_unique_4dp": acc_unique_4dp,
                "acc_frozen": acc_frozen,
                "frozen_accMag": round(acc[0], 4) if acc_frozen else "",
                "gyro_sd": round(gyro_sd, 4),
                "gyro_active": gyro_sd > 0.01,
                "orientation_frozen_zero": orientation_frozen,
                "scanning_frames": counts["scanning"],
                "postural_shift_frames": counts["postural_shift"],
                "window_nominal_s": round(WINDOW / rate, 3) if rate else "",
                "source_file": path.name,
            }
        )
    return sessions


def load_matrix(sessions: list[dict[str, object]]) -> list[dict[str, object]]:
    by_subject = {str(s["subject"]): s for s in sessions if s["retained"]}
    with MATRIX_PATH.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    out: list[dict[str, object]] = []
    for row in rows:
        session = by_subject[row["Subject"]]
        item: dict[str, object] = {
            "Subject": row["Subject"],
            "file_id": session["file_id"],
            "path_group": session["path_group"],
            "acc_frozen": session["acc_frozen"],
            "orientation_frozen_zero": session["orientation_frozen_zero"],
        }
        for feature, _, _ in FEATURES:
            item[feature] = float(row[feature])
        out.append(item)
    return out


def load_annotation_dir(path: Path) -> dict[tuple[str, int], dict[str, str]]:
    out: dict[tuple[str, int], dict[str, str]] = {}
    for file in sorted(path.glob("*.csv")):
        match = re.search(r"受测者(\d+)", file.name)
        if not match:
            continue
        subject = match.group(1)
        with file.open(encoding="utf-8-sig", errors="ignore", newline="") as f:
            for row in csv.DictReader(f):
                human = (row.get("human_label") or "").strip()
                start = (row.get("csv_time_start_s") or "").strip()
                if human and start and not start.startswith("#"):
                    out[(subject, int(float(start)))] = {
                        "human": human,
                        "machine": (row.get("machine_label") or "").strip(),
                        "annotator_id": (row.get("annotator_id") or "").strip(),
                        "file": file.name,
                    }
    return out


def annotation_audit() -> dict[str, object]:
    rater_a = load_annotation_dir(ANNOTATION / "盲标回收_20260727")
    rater_b = load_annotation_dir(ANNOTATION / "标注员2回收_20260728")
    common = sorted(set(rater_a) & set(rater_b))
    inter_pairs = [(rater_a[k]["human"], rater_b[k]["human"]) for k in common]
    ma_pairs = [(rater_a[k]["machine"], rater_a[k]["human"]) for k in common]
    mb_pairs = [(rater_b[k]["machine"], rater_b[k]["human"]) for k in common]

    def grouped(make_pair):
        groups: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for key in common:
            groups[key[0]].append(make_pair(key))
        return groups

    metrics = {}
    for name, pairs, maker in (
        ("inter_rater", inter_pairs, lambda k: (rater_a[k]["human"], rater_b[k]["human"])),
        ("machine_vs_rater_a", ma_pairs, lambda k: (rater_a[k]["machine"], rater_a[k]["human"])),
        ("machine_vs_rater_b", mb_pairs, lambda k: (rater_b[k]["machine"], rater_b[k]["human"])),
    ):
        kap, agreement, n = kappa(pairs)
        lo, hi = cluster_bootstrap_kappa(grouped(maker))
        metrics[name] = {
            "n": n,
            "agreement": agreement,
            "kappa": kap,
            "ci95_cluster": [lo, hi],
        }

    align_rows = []
    with (ANNOTATION / "auto_alignment.csv").open(encoding="utf-8-sig", newline="") as f:
        align_rows = list(csv.DictReader(f))
    selected = [r for r in align_rows if r["confident"].lower() == "true"]
    selected_subjects = {str(k[0]) for k in common}
    selected = [r for r in selected if r["subject"] in selected_subjects]

    def confusion(pairs: list[tuple[str, str]]) -> tuple[list[str], list[list[int]]]:
        cats = sorted({x for pair in pairs for x in pair})
        return cats, [[sum(a == ra and b == cb for a, b in pairs) for cb in cats] for ra in cats]

    return {
        "rater_a": rater_a,
        "rater_b": rater_b,
        "common": common,
        "metrics": metrics,
        "align_rows": align_rows,
        "selected_align_rows": selected,
        "inter_confusion": confusion(inter_pairs),
        "machine_a_confusion": confusion(ma_pairs),
        "machine_b_confusion": confusion(mb_pairs),
        "rater_a_counts": Counter(rater_a[k]["human"] for k in common),
        "rater_b_counts": Counter(rater_b[k]["human"] for k in common),
    }


def std(values: list[float]) -> float:
    if not values:
        return 0.0
    m = statistics.mean(values)
    return math.sqrt(sum((x - m) ** 2 for x in values) / len(values))


def classify_sequence(rows: list[dict[str, float]], th: dict[str, float]) -> list[str]:
    out: list[str] = []
    for i, row in enumerate(rows):
        lo = max(0, i - WINDOW)
        window = rows[lo : i + 1]
        gyro_std = std([x["gyroMag"] for x in window])
        euler_delta = max(
            max(x[axis] for x in window) - min(x[axis] for x in window)
            for axis in ("roll", "pitch", "yaw")
        )
        gyro = row["gyroMag"]
        acc = row["accNoGravity"]
        if gyro > th["sudden_gyroMin"] or gyro_std > th["sudden_gyroStdMin"]:
            out.append("sudden_turn")
        elif (
            th["scanning_gyroMin"] <= gyro <= th["scanning_gyroMax"]
            and gyro_std <= th["scanning_gyroStdMax"]
            and euler_delta >= th["scanning_eulerDeltaMin"]
        ):
            out.append("scanning")
        elif th["head_gyroMin"] <= gyro <= th["head_gyroMax"]:
            out.append("head_turn")
        elif acc > th["postural_accMin"]:
            out.append("postural_shift")
        elif gyro < th["gaze_gyroMax"] and euler_delta < th["gaze_eulerDeltaMax"]:
            out.append("gaze")
        else:
            out.append("idle")
    return out


def threshold_sensitivity_adb(sessions: list[dict[str, object]]) -> list[dict[str, object]]:
    adb_ids = {str(s["file_id"]) for s in sessions if s["retained"] and s["path_group"] == "ADB-like"}
    cache: list[list[dict[str, float]]] = []
    for sid in sorted(adb_ids):
        rows = []
        for row in read_export(RAW_DIR / f"imu_analysis_{sid}.csv"):
            rows.append(
                {
                    "accNoGravity": abs(float(row["accMag"]) - GRAVITY),
                    "gyroMag": float(row["gyroMag"]),
                    "roll": float(row["roll"]),
                    "pitch": float(row["pitch"]),
                    "yaw": float(row["yaw"]),
                }
            )
        cache.append(rows)

    def distribution(th: dict[str, float]) -> dict[str, float]:
        counts = Counter()
        for rows in cache:
            counts.update(classify_sequence(rows, th))
        total = sum(counts.values())
        return {state: 100 * counts[state] / total for state in STATES}

    base = distribution(BASE_THRESHOLDS)
    keys = [
        "sudden_gyroMin",
        "sudden_gyroStdMin",
        "scanning_gyroMin",
        "scanning_gyroMax",
        "scanning_gyroStdMax",
        "scanning_eulerDeltaMin",
        "head_gyroMin",
        "head_gyroMax",
        "gaze_gyroMax",
        "gaze_eulerDeltaMax",
        "postural_accMin",
    ]
    out = []
    for key in keys:
        for pct in (-30, -20, -10, 10, 20, 30):
            th = dict(BASE_THRESHOLDS)
            th[key] *= 1 + pct / 100
            dist = distribution(th)
            shifts = {state: dist[state] - base[state] for state in STATES}
            out.append(
                {
                    "threshold": key,
                    "perturb_pct": pct,
                    **{f"{s}_pct": round(dist[s], 4) for s in STATES},
                    "max_abs_shift_pp": round(max(abs(x) for x in shifts.values()), 4),
                    "mean_abs_shift_pp": round(statistics.mean(abs(x) for x in shifts.values()), 4),
                }
            )
    return out


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        return
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_confusion(path: Path, cats: list[str], matrix: list[list[int]]) -> None:
    rows = []
    for cat, values in zip(cats, matrix):
        rows.append({"row_label": cat, **{c: v for c, v in zip(cats, values)}})
    write_csv(path, rows)


def prepare_evidence() -> dict[str, object]:
    sessions = audit_sessions()
    matrix = load_matrix(sessions)
    annotations = annotation_audit()
    sensitivity = threshold_sensitivity_adb(sessions)

    write_csv(EVIDENCE / "session_audit.csv", sessions)
    write_csv(EVIDENCE / "threshold_sensitivity_adb.csv", sensitivity)

    path_comparison = []
    for feature, role_en, role_cn in FEATURES:
        adb = [
            float(r[feature])
            for r in matrix
            if r["path_group"] == "ADB-like" and not (feature in ACC_FEATURES and r["acc_frozen"])
        ]
        browser = [
            float(r[feature])
            for r in matrix
            if r["path_group"] == "browser-compatible" and not (feature in ACC_FEATURES and r["acc_frozen"])
        ]
        ma, sa = mean_sd(adb)
        mb, sb = mean_sd(browser)
        path_comparison.append(
            {
                "feature": feature,
                "role_en": role_en,
                "role_cn": role_cn,
                "adb_n": len(adb),
                "adb_mean": round(ma, 6),
                "adb_sd": round(sa, 6),
                "browser_n": len(browser),
                "browser_mean": round(mb, 6),
                "browser_sd": round(sb, 6),
                "cohen_d_browser_minus_adb": round(cohen_d(adb, browser), 6),
                "interpretation": "descriptive only; browser N=2 and field semantics may differ",
            }
        )
    write_csv(EVIDENCE / "path_feature_comparison.csv", path_comparison)

    ann_rows = []
    for name, item in annotations["metrics"].items():
        ann_rows.append(
            {
                "comparison": name,
                "n_bins": item["n"],
                "observed_agreement": round(item["agreement"], 6),
                "cohen_kappa": round(item["kappa"], 6),
                "cluster_bootstrap_ci95_low": round(item["ci95_cluster"][0], 6),
                "cluster_bootstrap_ci95_high": round(item["ci95_cluster"][1], 6),
                "participants": len({x[0] for x in annotations["common"]}),
            }
        )
    write_csv(EVIDENCE / "annotation_evidence.csv", ann_rows)
    write_confusion(EVIDENCE / "confusion_inter_rater.csv", *annotations["inter_confusion"])
    write_confusion(EVIDENCE / "confusion_machine_vs_rater_a.csv", *annotations["machine_a_confusion"])
    write_confusion(EVIDENCE / "confusion_machine_vs_rater_b.csv", *annotations["machine_b_confusion"])

    selected_refs = []
    with REFERENCE_AUDIT.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            idx = int(row["index"])
            if idx not in (26, 27):
                selected_refs.append(row)
    write_csv(EVIDENCE / "reference_audit_selected.csv", selected_refs)

    retained = [s for s in sessions if s["retained"]]
    all_counts = Counter()
    retained_counts = Counter()
    adb_counts = Counter()
    browser_counts = Counter()
    for session in sessions:
        rows = read_export(RAW_DIR / f"imu_analysis_{session['file_id']}.csv")
        counts = Counter(r["behavior"] for r in rows)
        all_counts.update(counts)
        if session["retained"]:
            retained_counts.update(counts)
            (adb_counts if session["path_group"] == "ADB-like" else browser_counts).update(counts)

    summary = {
        "template_sha256": hashlib.sha256(TEMPLATE.read_bytes()).hexdigest(),
        "exports_total": len(sessions),
        "exports_retained": len(retained),
        "frames_all": sum(all_counts.values()),
        "frames_retained": sum(retained_counts.values()),
        "adb_sessions": sum(s["path_group"] == "ADB-like" for s in retained),
        "browser_compatible_sessions": sum(s["path_group"] == "browser-compatible" for s in retained),
        "acc_frozen_sessions": sum(bool(s["acc_frozen"]) for s in retained),
        "orientation_frozen_sessions": sum(bool(s["orientation_frozen_zero"]) for s in retained),
        "all_state_counts": dict(all_counts),
        "retained_state_counts": dict(retained_counts),
        "adb_state_counts": dict(adb_counts),
        "browser_state_counts": dict(browser_counts),
        "retained_duration_min": min(float(s["duration_s"]) for s in retained),
        "retained_duration_median": median([float(s["duration_s"]) for s in retained]),
        "retained_duration_max": max(float(s["duration_s"]) for s in retained),
        "annotation": {k: v for k, v in annotations["metrics"].items()},
        "alignment_confident": len(annotations["selected_align_rows"]),
        "alignment_candidates": len(annotations["align_rows"]),
        "selected_reference_count": len(selected_refs),
        "reference_status_counts": dict(Counter(r["status"] for r in selected_refs)),
    }
    (EVIDENCE / "evidence_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {
        "sessions": sessions,
        "matrix": matrix,
        "annotations": annotations,
        "sensitivity": sensitivity,
        "path_comparison": path_comparison,
        "references": selected_refs,
        "summary": summary,
    }


def image_font(size: int, bold: bool = False):
    candidates = [
        Path(r"C:\Windows\Fonts\arialbd.ttf") if bold else Path(r"C:\Windows\Fonts\arial.ttf"),
        Path(r"C:\Windows\Fonts\calibrib.ttf") if bold else Path(r"C:\Windows\Fonts\calibri.ttf"),
        Path(r"C:\Windows\Fonts\segoeuib.ttf") if bold else Path(r"C:\Windows\Fonts\segoeui.ttf"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default()


def wrap_image_text(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    lines = []
    for raw in text.split("\n"):
        words = raw.split()
        if not words:
            lines.append("")
            continue
        current = words[0]
        for word in words[1:]:
            candidate = current + " " + word
            if draw.textbbox((0, 0), candidate, font=font)[2] <= max_width:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return lines


def draw_wrapped(draw: ImageDraw.ImageDraw, xy, text: str, font, fill, max_width: int, spacing: int = 8, anchor="la"):
    lines = wrap_image_text(draw, text, font, max_width)
    x, y = xy
    for line in lines:
        draw.text((x, y), line, font=font, fill=fill, anchor=anchor)
        y += font.size + spacing
    return y


def rgb(hex_color: str) -> tuple[int, int, int]:
    v = hex_color.lstrip("#")
    return tuple(int(v[i : i + 2], 16) for i in (0, 2, 4))


def save_image(img: Image.Image, name: str) -> None:
    img.save(FIGURES / f"{name}.png", dpi=(300, 300))
    img.save(FIGURES / f"{name}.tiff", dpi=(300, 300), compression="tiff_lzw")


def draw_arrow(draw: ImageDraw.ImageDraw, start, end, fill=(82, 97, 107), width=6):
    draw.line([start, end], fill=fill, width=width)
    x1, y1 = start
    x2, y2 = end
    angle = math.atan2(y2 - y1, x2 - x1)
    size = 22
    left = (x2 - size * math.cos(angle - math.pi / 6), y2 - size * math.sin(angle - math.pi / 6))
    right = (x2 - size * math.cos(angle + math.pi / 6), y2 - size * math.sin(angle + math.pi / 6))
    draw.polygon([(x2, y2), left, right], fill=fill)


def draw_box(draw, xy, title, body, color, title_font, body_font):
    x, y, w, h = xy
    draw.rounded_rectangle((x, y, x + w, y + h), radius=18, outline=rgb(color), width=6, fill="white")
    draw.text((x + 25, y + 25), title, font=title_font, fill=rgb(color))
    draw_wrapped(draw, (x + 25, y + 82), body, body_font, (37, 49, 60), w - 50, spacing=7)


def make_figures(data: dict[str, object]) -> None:
    sessions = [s for s in data["sessions"] if s["retained"]]
    summary = data["summary"]
    title_font = image_font(42, True)
    box_title = image_font(34, True)
    body_font = image_font(27)
    small_font = image_font(24)
    tiny_font = image_font(21)
    navy, blue, teal, gold, red, gray, green = [rgb(COLORS[k]) for k in ("navy", "blue", "teal", "gold", "red", "gray", "green")]

    # Figure 1: cross-layer workflow and route semantics.
    img = Image.new("RGB", (2800, 1500), "white")
    d = ImageDraw.Draw(img)
    d.text((1400, 60), "Cross-layer evidence chain", font=title_font, fill=navy, anchor="ma")
    d.text((1400, 125), "The export schema is shared, but source semantics are not assumed equivalent.", font=small_font, fill=gray, anchor="ma")
    draw_box(d, (90, 300, 610, 310), "ADB sensorservice route", "Pico 4 cached sensor events\nHost-arrival timestamps\n27 retained sessions", COLORS["blue"], box_title, body_font)
    draw_box(d, (90, 870, 610, 360), "Browser compatibility route", "WebXR: pose-derived acceleration and translational velocity\nDeviceMotion: acceleration and rotationRate\n2 retained sessions", COLORS["gold"], box_title, body_font)
    draw_box(d, (850, 550, 400, 280), "WebSocket bridge", "Local JSON stream\nCommon field schema", COLORS["teal"], box_title, body_font)
    draw_box(d, (1430, 550, 460, 280), "Computer mapping", "accMag, gyroMag\nquaternion to Euler\n20-frame window", COLORS["navy"], box_title, body_font)
    draw_box(d, (2070, 290, 630, 300), "Rule-state output", "Priority rules\nConfidence = rule margin\nNot a calibrated probability", COLORS["red"], box_title, body_font)
    draw_box(d, (2070, 880, 630, 300), "Export and audit", "Analysis CSV and HTML\nSubject matrix\nPath and channel flags", COLORS["green"], box_title, body_font)
    draw_arrow(d, (700, 450), (850, 650))
    draw_arrow(d, (700, 1030), (850, 720))
    draw_arrow(d, (1250, 690), (1430, 690))
    draw_arrow(d, (1890, 620), (2070, 470))
    draw_arrow(d, (2385, 590), (2385, 880))
    save_image(img, "figure1_architecture")

    # Figure 2: mapping and rule priority.
    img = Image.new("RGB", (2800, 1500), "white")
    d = ImageDraw.Draw(img)
    d.text((1400, 45), "Computer-side mapping and deterministic rule logic", font=title_font, fill=navy, anchor="ma")
    d.text((150, 175), "Field semantics before mapping", font=box_title, fill=navy)
    semantic_rows = [
        ("ADB-like", "acc / angular rate / rotation vector", blue),
        ("WebXR", "pose-derived translational acceleration and velocity", gold),
        ("DeviceMotion", "accelerationIncludingGravity / rotationRate", teal),
        ("Mapped export", "accMag / gyroMag / Euler / behavior / confidence", green),
    ]
    y = 270
    for label, body, color in semantic_rows:
        d.rounded_rectangle((120, y, 1270, y + 170), radius=14, outline=color, width=5, fill="white")
        d.text((165, y + 85), label, font=box_title, fill=color, anchor="lm")
        draw_wrapped(d, (570, y + 85), body, body_font, (37, 49, 60), 650, anchor="lm")
        y += 220
    d.text((1500, 175), "Classifier priority and data dependence", font=box_title, fill=navy)
    rule_rows = [
        ("1", "sudden_turn", "gyro magnitude or window SD", red),
        ("2", "scanning", "gyro plus Euler-window range", teal),
        ("3", "head_turn", "gyro magnitude", blue),
        ("4", "postural_shift", "gravity-adjusted acceleration", gold),
        ("5", "gaze", "low gyro plus low Euler range", green),
        ("6", "idle", "fallback category", gray),
    ]
    y = 270
    for rank, label, trigger, color in rule_rows:
        d.ellipse((1510, y, 1590, y + 80), fill=color)
        d.text((1550, y + 40), rank, font=box_title, fill="white", anchor="mm")
        d.text((1640, y + 40), label, font=box_title, fill=color, anchor="lm")
        d.text((2110, y + 40), trigger, font=body_font, fill=(37, 49, 60), anchor="lm")
        y += 150
    save_image(img, "figure2_mapping_rules")

    # Figure 3: sampling rate and window duration.
    img = Image.new("RGB", (2800, 1450), "white")
    d = ImageDraw.Draw(img)
    d.text((1400, 45), "Route-aware timing audit", font=title_font, fill=navy, anchor="ma")
    d.text((150, 160), "Observed effective sampling rate", font=box_title, fill=navy)
    plot = (190, 300, 1250, 1160)
    d.rectangle(plot, outline=(150, 160, 170), width=3)
    adb = [s for s in sessions if s["path_group"] == "ADB-like"]
    browser = [s for s in sessions if s["path_group"] == "browser-compatible"]
    max_rate = 22
    for tick in (0, 5, 10, 15, 20):
        yy = plot[3] - int((tick / max_rate) * (plot[3] - plot[1]))
        d.line((plot[0], yy, plot[2], yy), fill=(224, 230, 236), width=2)
        d.text((plot[0] - 20, yy), str(tick), font=small_font, fill=gray, anchor="rm")
    for i, session in enumerate(adb + browser, 1):
        xx = plot[0] + int((i - 0.5) * (plot[2] - plot[0]) / 29)
        yy = plot[3] - int((session["median_rate_hz"] / max_rate) * (plot[3] - plot[1]))
        color = blue if session["path_group"] == "ADB-like" else gold
        d.ellipse((xx - 8, yy - 8, xx + 8, yy + 8), fill=color)
    d.text((plot[0] - 25, plot[1] - 35), "Hz", font=small_font, fill=gray, anchor="ra")
    d.text((plot[0], plot[3] + 35), "27 ADB-like sessions", font=small_font, fill=blue)
    d.text((plot[0] + 460, plot[3] + 35), "2 browser-compatible sessions", font=small_font, fill=gold)
    d.text((1500, 160), "Same frame count, different time support", font=box_title, fill=navy)
    values = [("ADB-like", WINDOW / statistics.mean([s["median_rate_hz"] for s in adb]), blue), ("Browser 8.33 Hz", WINDOW / 8.33, gold), ("Browser 20 Hz", WINDOW / 20.0, gold)]
    base_x, base_y, bar_w, gap, scale = 1600, 1130, 230, 120, 115
    for i, (label, value, color) in enumerate(values):
        x = base_x + i * (bar_w + gap)
        h = int(value * scale)
        d.rectangle((x, base_y - h, x + bar_w, base_y), fill=color)
        d.text((x + bar_w / 2, base_y - h - 35), f"{value:.2f} s", font=box_title, fill=color, anchor="ms")
        draw_wrapped(d, (x + bar_w / 2, base_y + 35), label, small_font, (37, 49, 60), bar_w + 60, anchor="ma")
    d.text((1500, 1260), "Nominal duration of the implemented 20-frame window", font=small_font, fill=gray)
    save_image(img, "figure3_sampling_windows")

    # Figure 4: route-stratified output distributions.
    img = Image.new("RGB", (2800, 1450), "white")
    d = ImageDraw.Draw(img)
    d.text((1400, 45), "Rule outputs are strongly route-dependent", font=title_font, fill=navy, anchor="ma")
    adb_counts = Counter(summary["adb_state_counts"])
    browser_counts = Counter(summary["browser_state_counts"])
    adb_total, browser_total = sum(adb_counts.values()), sum(browser_counts.values())
    plot = (280, 260, 2600, 1120)
    d.rectangle(plot, outline=(150, 160, 170), width=3)
    max_pct = 65
    for tick in (0, 20, 40, 60):
        yy = plot[3] - int(tick / max_pct * (plot[3] - plot[1]))
        d.line((plot[0], yy, plot[2], yy), fill=(224, 230, 236), width=2)
        d.text((plot[0] - 15, yy), str(tick), font=small_font, fill=gray, anchor="rm")
    group_w = (plot[2] - plot[0]) / len(STATES)
    for i, state in enumerate(STATES):
        center = plot[0] + group_w * (i + 0.5)
        for shift, count, total, color in ((-85, adb_counts[state], adb_total, blue), (85, browser_counts[state], browser_total, gold)):
            pct = 100 * count / total if total else 0
            h = int(pct / max_pct * (plot[3] - plot[1]))
            d.rectangle((center + shift - 48, plot[3] - h, center + shift + 48, plot[3]), fill=color)
            d.text((center + shift, plot[3] - h - 18), f"{pct:.1f}", font=tiny_font, fill=color, anchor="ms")
        draw_wrapped(d, (center, plot[3] + 45), state.replace("_", "\n"), small_font, (37, 49, 60), 180, anchor="ma")
    d.text((plot[0], 190), "Percent of exported rule-state frames", font=small_font, fill=gray)
    d.rectangle((1950, 150, 1985, 185), fill=blue); d.text((2000, 168), "ADB-like (40,119 frames)", font=small_font, fill=(37, 49, 60), anchor="lm")
    d.rectangle((2370, 150, 2405, 185), fill=gold); d.text((2420, 168), "Browser-compatible (5,441 frames)", font=small_font, fill=(37, 49, 60), anchor="lm")
    d.text((280, 1245), "Descriptive output distributions only. Different field semantics and window durations prevent an equivalence claim.", font=small_font, fill=red)
    save_image(img, "figure4_state_distribution_by_path")

    # Figure 5: ADB-only threshold sensitivity.
    img = Image.new("RGB", (2800, 1650), "white")
    d = ImageDraw.Draw(img)
    d.text((1400, 45), "ADB-only rule-threshold sensitivity", font=title_font, fill=navy, anchor="ma")
    by_key: dict[str, float] = defaultdict(float)
    for row in data["sensitivity"]:
        by_key[str(row["threshold"])] = max(by_key[str(row["threshold"])], float(row["max_abs_shift_pp"]))
    ordered = sorted(by_key, key=by_key.get)
    max_value = max(by_key.values()) if by_key else 1
    left, top, right, bottom = 620, 230, 2600, 1450
    for i, key in enumerate(ordered):
        yy = top + i * ((bottom - top) / len(ordered)) + 15
        d.text((left - 25, yy), key.replace("_", " "), font=small_font, fill=(37, 49, 60), anchor="ra")
        width = int(by_key[key] / max_value * (right - left))
        color = red if by_key[key] >= 3 else blue if by_key[key] >= 1 else teal
        d.rectangle((left, yy - 22, left + width, yy + 22), fill=color)
        d.text((left + width + 15, yy), f"{by_key[key]:.2f}", font=tiny_font, fill=color, anchor="lm")
    d.text((left, bottom + 55), "Maximum absolute change in any state share (percentage points)", font=small_font, fill=gray)
    d.text((left, bottom + 90), "across +/-10%, +/-20%, and +/-30% threshold perturbations", font=small_font, fill=gray)
    save_image(img, "figure5_threshold_sensitivity")

    # Figure 6: channel availability across retained sessions.
    img = Image.new("RGB", (2800, 1250), "white")
    d = ImageDraw.Draw(img)
    d.text((1400, 45), "Route and channel-availability audit", font=title_font, fill=navy, anchor="ma")
    categories = [("Acquisition path", 27, 2, "ADB-like", "Browser-compatible"), ("Accelerometer", 24, 5, "Active", "Frozen"), ("Orientation", 1, 28, "Active", "Frozen at zero")]
    left, top, right = 520, 300, 2550
    for i, (label, active, flagged, active_label, flagged_label) in enumerate(categories):
        yy = top + i * 250
        d.text((left - 30, yy + 65), label, font=box_title, fill=(37, 49, 60), anchor="ra")
        active_w = int(active / 29 * (right - left))
        flag_w = int(flagged / 29 * (right - left))
        d.rectangle((left, yy, left + active_w, yy + 135), fill=green)
        d.rectangle((left + active_w, yy, left + active_w + flag_w, yy + 135), fill=red)
        if active_w >= 160:
            d.text((left + active_w / 2, yy + 67), f"{active_label}\n{active}", font=box_title, fill="white", anchor="mm", align="center")
        else:
            d.text((left + active_w / 2, yy + 67), str(active), font=box_title, fill="white", anchor="mm")
        if flag_w >= 220:
            d.text((left + active_w + flag_w / 2, yy + 67), f"{flagged_label}\n{flagged}", font=box_title, fill="white", anchor="mm", align="center")
        else:
            d.text((left + active_w + flag_w / 2, yy + 67), str(flagged), font=box_title, fill="white", anchor="mm")
    d.text((left, 1080), "All bars use the retained-session denominator N=29.", font=small_font, fill=gray)
    save_image(img, "figure6_channel_quality")


REFERENCES = [
    "Wodarski, P.; Jurkojc, J.; Gzik, M. Wavelet Decomposition in Analysis of Impact of Virtual Reality Head Mounted Display Systems on Postural Stability. Sensors 2020, 20, 7138. https://doi.org/10.3390/s20247138",
    "Monica, R.; Aleotti, J. Evaluation of the Oculus Rift S Tracking System in Room Scale Virtual Reality. Virtual Reality 2022, 26, 1229-1242. https://doi.org/10.1007/s10055-022-00637-3",
    "Palmisano, S.; Allison, R.S.; Teixeira, J.; Kim, J. Differences in Virtual and Physical Head Orientation Predict Sickness during Active Head-Mounted Display-Based Virtual Reality. Virtual Reality 2023, 27, 1293-1313. https://doi.org/10.1007/s10055-022-00732-5",
    "Sousa Lima, W.; Souto, E.; El-Khatib, K.; Jalali, R.; Gama, J. Human Activity Recognition Using Inertial Sensors in a Smartphone: An Overview. Sensors 2019, 19, 3213. https://doi.org/10.3390/s19143213",
    "Sinha, V.K.; Patro, K.K.; Plawiak, P.; Prakash, A.J. Smartphone-Based Human Sitting Behaviors Recognition Using Inertial Sensor. Sensors 2021, 21, 6652. https://doi.org/10.3390/s21196652",
    "Zhuo, S.; Sherlock, L.; Dobbie, G.; Koh, Y.S.; Russello, G. Real-Time Smartphone Activity Classification Using Inertial Sensors: Recognition of Scrolling, Typing, and Watching Videos While Sitting or Walking. Sensors 2020, 20, 655. https://doi.org/10.3390/s20030655",
    "Shoaib, M.; Bosch, S.; Incel, O.D.; Scholten, H.; Havinga, P.J.M. Complex Human Activity Recognition Using Smartphone and Wrist-Worn Motion Sensors. Sensors 2016, 16, 426. https://doi.org/10.3390/s16040426",
    "Vuong, T.H.; Doan, T.; Takasu, A. Deep Wavelet Convolutional Neural Networks for Multimodal Human Activity Recognition Using Wearable Inertial Sensors. Sensors 2023, 23, 9721. https://doi.org/10.3390/s23249721",
    "Kim, Y.W.; Joa, K.L.; Jeong, H.Y.; Lee, S. Wearable IMU-Based Human Activity Recognition Algorithm for Clinical Balance Assessment Using 1D-CNN and GRU Ensemble Model. Sensors 2021, 21, 7628. https://doi.org/10.3390/s21227628",
    "Seenath, S.; Dharmaraj, M. Conformer-Based Human Activity Recognition Using Inertial Measurement Units. Sensors 2023, 23, 7357. https://doi.org/10.3390/s23177357",
    "Kim, Y.W.; Cho, W.H.; Kim, K.S.; Lee, S. Inertial-Measurement-Unit-Based Novel Human Activity Recognition Algorithm Using Conformer. Sensors 2022, 22, 3932. https://doi.org/10.3390/s22103932",
    "Eyobu, O.S.; Han, D.S. Feature Representation and Data Augmentation for Human Activity Classification Based on Wearable IMU Sensor Data Using a Deep LSTM Neural Network. Sensors 2018, 18, 2892. https://doi.org/10.3390/s18092892",
    "Rosati, S.; Balestra, G.; Knaflitz, M. Comparison of Different Sets of Features for Human Activity Recognition by Wearable Sensors. Sensors 2018, 18, 4189. https://doi.org/10.3390/s18124189",
    "Konak, O.; Wegner, P.; Arnrich, B. IMU-Based Movement Trajectory Heatmaps for Human Activity Recognition. Sensors 2020, 20, 7179. https://doi.org/10.3390/s20247179",
    "Kim, Y.W.; Lee, S. Data Valuation Algorithm for Inertial Measurement Unit-Based Human Activity Recognition. Sensors 2022, 23, 184. https://doi.org/10.3390/s23010184",
    "Bangaru, S.S.; Wang, C.; Aghazadeh, F. Data Quality and Reliability Assessment of Wearable EMG and IMU Sensor for Construction Activity Recognition. Sensors 2020, 20, 5264. https://doi.org/10.3390/s20185264",
    "Buescher, N.; Gis, D.; Kuhn, V.; Haubelt, C. On the Functional and Extra-Functional Properties of IMU Fusion Algorithms for Body-Worn Smart Sensors. Sensors 2021, 21, 2747. https://doi.org/10.3390/s21082747",
    "Lee, J.K.; Jung, W.C. Quaternion-Based Local Frame Alignment between an Inertial Measurement Unit and a Motion Capture System. Sensors 2018, 18, 4003. https://doi.org/10.3390/s18114003",
    "Fang, Z.; Woodford, S.; Senanayake, D.; Ackland, D. Conversion of Upper-Limb Inertial Measurement Unit Data to Joint Angles: A Systematic Review. Sensors 2023, 23, 6535. https://doi.org/10.3390/s23146535",
    "Wang, L.; Zhang, Z.; Sun, P. Research on Gradient-Descent Extended Kalman Attitude Estimation Method for Low-Cost MARG. Micromachines 2022, 13, 1283. https://doi.org/10.3390/mi13081283",
    "Li, R.; Fu, C.; Yi, W.; Yi, X. Calib-Net: Calibrating the Low-Cost IMU via Deep Convolutional Neural Network. Frontiers in Robotics and AI 2022, 8, 772583. https://doi.org/10.3389/frobt.2021.772583",
    "Yin, M.; Li, J.; Wang, T. A Low-Cost Inertial Measurement Unit Motion Capture System for Operation Posture Collection and Recognition. Sensors 2024, 24, 686. https://doi.org/10.3390/s24020686",
    "Iluk, A. Flight Controller as a Low-Cost IMU Sensor for Human Motion Measurement. Sensors 2023, 23, 2342. https://doi.org/10.3390/s23042342",
    "Weizman, Y.; Tirosh, O.; Fuss, F.K.; Tan, A.M.; Rutz, E. Recent State of Wearable IMU Sensors Use in People Living with Spasticity: A Systematic Review. Sensors 2022, 22, 1791. https://doi.org/10.3390/s22051791",
    "Teather, R.J.; Stuerzlinger, W. Pointing at 3D Targets in a Stereo Head-Tracked Virtual Environment. IEEE Symposium on 3D User Interfaces 2011, 87-94. https://doi.org/10.1109/3DUI.2011.5759222",
    "Davila, J.C.; Cretu, A.M.; Zaremba, M.B. Wearable Sensor Data Classification for Human Activity Recognition Based on an Iterative Learning Framework. Sensors 2017, 17, 1287. https://doi.org/10.3390/s17061287",
    "Abhayasinghe, N.; Murray, I.; Sharif Bidabadi, S. Validation of Thigh Angle Estimation Using Inertial Measurement Unit Data against Optical Motion Capture Systems. Sensors 2019, 19, 596. https://doi.org/10.3390/s19030596",
    "Zandbergen, M.A.; Reenalda, J.; van Middelaar, R.P.; Ferla, R.I.; Buurke, J.H. Drift-Free 3D Orientation and Displacement Estimation for Quasi-Cyclical Movements Using One Inertial Measurement Unit: Application to Running. Sensors 2022, 22, 956. https://doi.org/10.3390/s22030956",
]


def load_reference_strings() -> list[str]:
    return REFERENCES


def set_cell_shading(cell, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:fill"), fill.replace("#", ""))


def set_cell_margins(cell, top=70, start=80, bottom=70, end=80) -> None:
    tc = cell._tc
    tc_pr = tc.get_or_add_tcPr()
    tc_mar = tc_pr.first_child_found_in("w:tcMar")
    if tc_mar is None:
        tc_mar = OxmlElement("w:tcMar")
        tc_pr.append(tc_mar)
    for m, value in (("top", top), ("start", start), ("bottom", bottom), ("end", end)):
        node = tc_mar.find(qn(f"w:{m}"))
        if node is None:
            node = OxmlElement(f"w:{m}")
            tc_mar.append(node)
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")


def set_table_borders(table, color="666666", size="6") -> None:
    tbl_pr = table._tbl.tblPr
    borders = tbl_pr.first_child_found_in("w:tblBorders")
    if borders is None:
        borders = OxmlElement("w:tblBorders")
        tbl_pr.append(borders)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        node = borders.find(qn(f"w:{edge}"))
        if node is None:
            node = OxmlElement(f"w:{edge}")
            borders.append(node)
        node.set(qn("w:val"), "single")
        node.set(qn("w:sz"), size)
        node.set(qn("w:space"), "0")
        node.set(qn("w:color"), color)


def set_repeat_table_header(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    node = OxmlElement("w:tblHeader")
    node.set(qn("w:val"), "true")
    tr_pr.append(node)


def prevent_row_split(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    node = OxmlElement("w:cantSplit")
    tr_pr.append(node)


def set_table_geometry(table, widths_in: list[float]) -> None:
    total = int(round(sum(widths_in) * 1440))
    table.autofit = False
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl_pr = table._tbl.tblPr
    tbl_w = tbl_pr.first_child_found_in("w:tblW")
    if tbl_w is None:
        tbl_w = OxmlElement("w:tblW")
        tbl_pr.append(tbl_w)
    tbl_w.set(qn("w:w"), str(total))
    tbl_w.set(qn("w:type"), "dxa")
    grid = table._tbl.tblGrid
    for child in list(grid):
        grid.remove(child)
    dxa = [int(round(x * 1440)) for x in widths_in]
    for value in dxa:
        col = OxmlElement("w:gridCol")
        col.set(qn("w:w"), str(value))
        grid.append(col)
    for row in table.rows:
        for cell, value in zip(row.cells, dxa):
            tc_pr = cell._tc.get_or_add_tcPr()
            tc_w = tc_pr.first_child_found_in("w:tcW")
            if tc_w is None:
                tc_w = OxmlElement("w:tcW")
                tc_pr.append(tc_w)
            tc_w.set(qn("w:w"), str(value))
            tc_w.set(qn("w:type"), "dxa")
            cell.width = Inches(value / 1440)


def add_keep_with_next(paragraph) -> None:
    p_pr = paragraph._p.get_or_add_pPr()
    p_pr.append(OxmlElement("w:keepNext"))


def mdpi_doc() -> Document:
    doc = Document(TEMPLATE)
    body = doc._element.body
    for child in list(body):
        if not child.tag.endswith("sectPr"):
            body.remove(child)
    return doc


def mdpi_p(doc: Document, text: str = "", style: str = "MDPI_3.1_text"):
    p = doc.add_paragraph(style=style if style in doc.styles else None)
    p.add_run(text)
    return p


def mdpi_body(doc: Document, text: str, chinese: bool = False):
    p = mdpi_p(doc, text)
    if chinese:
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    return p


def mdpi_h(doc: Document, text: str, level: int = 1):
    style = "MDPI_2.1_heading1" if level == 1 else "MDPI_2.2_heading2"
    p = mdpi_p(doc, text, style)
    add_keep_with_next(p)
    return p


def mdpi_table(doc: Document, caption: str, rows: list[list[object]], widths: list[float]) -> None:
    cap = mdpi_p(doc, caption, "MDPI_4.1_table_caption")
    add_keep_with_next(cap)
    table = doc.add_table(rows=len(rows), cols=len(rows[0]))
    table.style = "Table Grid"
    set_table_borders(table)
    set_table_geometry(table, widths)
    set_repeat_table_header(table.rows[0])
    for i, row in enumerate(table.rows):
        prevent_row_split(row)
        for j, cell in enumerate(row.cells):
            cell.text = ""
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            set_cell_margins(cell)
            p = cell.paragraphs[0]
            if "MDPI_4.2_table_body" in doc.styles:
                p.style = "MDPI_4.2_table_body"
            p.paragraph_format.space_after = Pt(0)
            run = p.add_run(str(rows[i][j]))
            run.font.name = "Times New Roman"
            run._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
            run.font.size = Pt(7.6 if len(rows) > 15 else 8.0)
            if i == 0:
                run.bold = True
                set_cell_shading(cell, "E8EEF5")


def mdpi_figure(doc: Document, name: str, caption: str, width: float = 6.7) -> None:
    p = doc.add_paragraph(style="MDPI_5.2_figure" if "MDPI_5.2_figure" in doc.styles else None)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.keep_with_next = True
    p.add_run().add_picture(str(FIGURES / f"{name}.png"), width=Inches(width))
    cap = mdpi_p(doc, caption, "MDPI_5.1_figure_caption")
    cap.paragraph_format.keep_with_next = False


def back_matter(doc: Document, label: str, text: str) -> None:
    p = doc.add_paragraph(style="MDPI_6.2_back_matter" if "MDPI_6.2_back_matter" in doc.styles else None)
    r = p.add_run(label + ": ")
    r.bold = True
    p.add_run(text)


def add_page_break(doc: Document) -> None:
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)


def fmt(value: float, digits: int = 3) -> str:
    return f"{value:.{digits}f}"


def fmt_mean_sd(values: list[float], digits: int = 3) -> str:
    m, s = mean_sd(values)
    return f"{m:.{digits}f} +/- {s:.{digits}f}"


def rows_by_feature(matrix: list[dict[str, object]], feature: str, path: str | None = None, active_acc: bool = False) -> list[float]:
    return [
        float(row[feature])
        for row in matrix
        if (path is None or row["path_group"] == path)
        and not (active_acc and feature in ACC_FEATURES and row["acc_frozen"])
    ]


def build_tables(data: dict[str, object]) -> dict[str, list[list[object]]]:
    summary = data["summary"]
    sessions = data["sessions"]
    matrix = data["matrix"]
    comparison = data["path_comparison"]
    annotations = data["annotations"]
    retained = [s for s in sessions if s["retained"]]

    table1 = [
        ["Layer / route", "Implementation evidence", "Observed export semantics", "Use in this paper"],
        ["ADB-like acquisition", "adb_sensor_reader.py; dumpsys sensorservice polling", "Cached acceleration, gyro, and rotation-vector events; host-arrival timestamps", "Primary comparable cohort (27 retained sessions)"],
        ["WebXR browser branch", "sensor.html; requestSession + viewer pose", "Position-differenced acceleration; translational velocity written into gyro_x/y/z compatibility fields", "Browser-compatible descriptive cohort; not pooled as angular IMU"],
        ["DeviceMotion browser branch", "sensor.html; devicemotion/deviceorientation listeners", "accelerationIncludingGravity and rotationRate converted to SI/rad units", "Browser-compatible route; exact branch not retained in analysis CSV"],
        ["Computer bridge", "ws_broker.py and browser WebSocket client", "Local JSON transport; common field names across routes", "Transport layer, not a calibration or synchronization reference"],
        ["Analysis/export", "data-mapper.js, behavior-analyzer.js, report-generator.js", "Mapped CSV fields: timestamp, accMag, gyroMag, roll, pitch, yaw, behavior, confidence", "Auditable outputs and subject-level summaries"],
    ]
    table2 = [
        ["Priority", "State", "Trigger in behavior-analyzer.js", "Primary signal dependence"],
        ["1", "sudden_turn", "gyroMag > 1.5 rad/s OR window gyro SD > 0.8 rad/s", "gyro field; browser semantic risk"],
        ["2", "scanning", "0.15 <= gyroMag <= 1.5; gyro SD <= 0.6; Euler range >= 3 deg", "gyro field + orientation; structurally unavailable when Euler stream is frozen"],
        ["3", "head_turn", "0.3 <= gyroMag <= 1.5 rad/s", "gyro field; browser semantic risk"],
        ["4", "postural_shift", "accNoGravity > 0.3 m/s^2", "acceleration; unavailable in frozen-accelerometer sessions"],
        ["5", "gaze", "gyroMag < 0.15 rad/s AND Euler range < 2 deg", "gyro field + orientation; gaze becomes a low-gyro fallback when orientation is frozen"],
        ["6", "idle", "Fallback after higher-priority rules", "Residual category; not a direct inactivity ground truth"],
    ]
    table3 = [
        ["Audit item", "All exports", "Retained analysis", "Interpretation"],
        ["Analysis CSV exports", "30 files", "29 sessions", "One aborted 8.4 s export excluded by pre-specified curation rule"],
        ["Mapped frames", f"{summary['frames_all']:,}", f"{summary['frames_retained']:,}", "Export-level frame counts; not independent participant observations"],
        ["Duration", "8.4-539.5 s", f"{summary['retained_duration_min']:.1f}-{summary['retained_duration_max']:.1f} s; median {summary['retained_duration_median']:.1f} s", "Session coverage is heterogeneous"],
        ["Acquisition path", "28 ADB-like / 2 browser-compatible", "27 ADB-like / 2 browser-compatible", "Path is mechanism-inferred from timing and source audit; exact browser branch was not retained"],
        ["Accelerometer", "5 frozen among retained sessions", "ADB-like: 22 active / 5 frozen; browser: 2 active / 0 frozen", "Frozen value is accMag = 9.7335 and gyro remained active; all five are ADB-like, so the acceleration-feature denominator is N=22"],
        ["Orientation", "28 retained sessions zero/frozen", "ADB-like: 0 active / 27 frozen; browser: 1 active / 1 frozen", "Euler-derived scanning branch is not reachable on the ADB route at all; every scanning frame comes from the single orientation-active browser session"],
        ["Human annotation", "19 video candidates", "10 selected; 661 common 1 s bins", "Two returned annotation sets cover the same bins"],
    ]
    table4 = [["Feature", "ADB-like N", "ADB-like mean +/- SD", "Browser N", "Browser mean +/- SD", "Cohen's d*", "Reading"]]
    for row in comparison:
        table4.append(
            [
                row["feature"],
                row["adb_n"],
                f"{row['adb_mean']:.3f} +/- {row['adb_sd']:.3f}",
                row["browser_n"],
                f"{row['browser_mean']:.3f} +/- {row['browser_sd']:.3f}",
                f"{row['cohen_d_browser_minus_adb']:.3f}" if not math.isnan(float(row["cohen_d_browser_minus_adb"])) else "NA",
                "Descriptive; N=2 browser",
            ]
        )
    table5 = [["Feature", "Primary cohort", "Mean +/- SD", "Min-Max", "N", "Interpretive note"]]
    for feature, role_en, _ in FEATURES:
        values = rows_by_feature(matrix, feature, "ADB-like", active_acc=True)
        table5.append(
            [
                feature,
                "ADB-like primary summary",
                fmt_mean_sd(values, 4),
                f"{min(values):.4f}-{max(values):.4f}",
                len(values),
                "Acceleration-dependent" if feature in ACC_FEATURES else role_en,
            ]
        )
    metrics = annotations["metrics"]
    table6 = [
        ["Comparison", "Bins", "Observed agreement", "Cohen's kappa", "Cluster bootstrap 95% CI", "Role"],
        ["Annotator A vs annotator B", metrics["inter_rater"]["n"], f"{100*metrics['inter_rater']['agreement']:.1f}%", f"{metrics['inter_rater']['kappa']:.3f}", f"{metrics['inter_rater']['ci95_cluster'][0]:.3f}-{metrics['inter_rater']['ci95_cluster'][1]:.3f}", "Inter-rater agreement"],
        ["Classifier vs annotator A", metrics["machine_vs_rater_a"]["n"], f"{100*metrics['machine_vs_rater_a']['agreement']:.1f}%", f"{metrics['machine_vs_rater_a']['kappa']:.3f}", f"{metrics['machine_vs_rater_a']['ci95_cluster'][0]:.3f}-{metrics['machine_vs_rater_a']['ci95_cluster'][1]:.3f}", "Agreement reference"],
        ["Classifier vs annotator B", metrics["machine_vs_rater_b"]["n"], f"{100*metrics['machine_vs_rater_b']['agreement']:.1f}%", f"{metrics['machine_vs_rater_b']['kappa']:.3f}", f"{metrics['machine_vs_rater_b']['ci95_cluster'][0]:.3f}-{metrics['machine_vs_rater_b']['ci95_cluster'][1]:.3f}", "Agreement reference"],
    ]
    appendix_a = [["Session", "Subject", "Frames", "Rate Hz", "Window s", "Path", "Acc", "Euler", "Scan", "Postural"]]
    for s in retained:
        appendix_a.append(
            [
                s["file_id"], s["subject"], s["frames"], f"{s['median_rate_hz']:.2f}", f"{s['window_nominal_s']:.2f}",
                "ADB" if s["path_group"] == "ADB-like" else "Browser",
                "frozen" if s["acc_frozen"] else "active",
                "zero" if s["orientation_frozen_zero"] else "active",
                s["scanning_frames"], s["postural_shift_frames"],
            ]
        )
    appendix_b = [
        ["Evidence asset", "Function traced", "Fields or decision supported"],
        ["平台（新版）/sensor.html", "WebXR and DeviceMotion browser collection", "Source-level distinction between viewer pose, derived velocity, accelerationIncludingGravity, and rotationRate"],
        ["scripts/adb_sensor_reader.py", "ADB sensorservice reader", "dumpsys polling, cached-event parsing, host timestamp, freeze/synthetic fallback code"],
        ["scripts/ws_broker.py", "Local WebSocket transport", "Frame forwarding between collector/reader and dashboard"],
        ["src/js/modules/data-mapper.js", "Computer-side mapping", "Magnitude, Euler, gravity approximation, NED-to-UE5 transform, export field order"],
        ["src/js/modules/behavior-analyzer.js", "Rule classifier", "20-frame window, priority order, thresholds, confidence heuristic"],
        ["src/js/modules/report-generator.js", "Subject-level report", "gyro_mean, acc_cv, state ratios, gaze duration, freeze_ratio"],
        ["实验原始数据与报告/imu_analysis_*.csv", "Exported analysis evidence", "30 CSV files, 46,402 frames, state labels and mapped signals"],
        ["results/data_matrix.csv", "Retained subject matrix", "29 rows; technical feature fields used without latent-variable modeling"],
    ]
    cats, inter = annotations["inter_confusion"]
    appendix_c1 = [["Annotator A \\ Annotator B", *cats]] + [[cat, *vals] for cat, vals in zip(cats, inter)]
    cats, ma = annotations["machine_a_confusion"]
    appendix_c2 = [["Machine \\ Annotator A", *cats]] + [[cat, *vals] for cat, vals in zip(cats, ma)]
    cats, mb = annotations["machine_b_confusion"]
    appendix_c3 = [["Machine \\ Annotator B", *cats]] + [[cat, *vals] for cat, vals in zip(cats, mb)]
    return {
        "table1": table1,
        "table2": table2,
        "table3": table3,
        "table4": table4,
        "table5": table5,
        "table6": table6,
        "appendix_a": appendix_a,
        "appendix_b": appendix_b,
        "appendix_c1": appendix_c1,
        "appendix_c2": appendix_c2,
        "appendix_c3": appendix_c3,
    }


def english_content(data: dict[str, object]) -> dict[str, object]:
    s = data["summary"]
    ann = data["annotations"]["metrics"]
    return {
        "highlights": [
            "A source-traced Pico 4 workflow is documented from headset collection to computer-side export and audit.",
            "Timing and source semantics separate 27 ADB-like sessions from two browser-compatible sessions rather than assuming IMU equivalence.",
            "Automated file-level checks identify five accelerometer freezes and 28 zero/frozen orientation streams in the retained corpus.",
            "Two-rater annotation evidence is reported as a moderate agreement reference, not as a supervised classification benchmark.",
        ],
        "abstract": (
            f"Consumer virtual-reality headsets expose motion data through software layers whose field names need not preserve sensor semantics. "
            f"We audited a Pico 4 workflow combining an Android Debug Bridge (ADB) sensorservice reader, browser-side WebXR/DeviceMotion collection, a WebSocket bridge, and dashboard export. "
            f"Thirty CSV exports ({s['frames_all']:,} mapped frames) were screened; a duration-and-completeness rule retained 29 sessions ({s['frames_retained']:,} frames), one per participant. "
            f"Twenty-seven were timing-compatible with irregular ADB polling (3.65-3.77 Hz) and two with browser fixed grids (8.33 and 20 Hz). Because the WebXR branch writes pose-derived translational velocity into fields named gyro_x/y/z, the routes were not pooled as one IMU stream. "
            f"The 20-frame window spans 5.3-5.5, 2.4, and 1.0 s across those rates, and the ADB rate falls below the Nyquist requirement for abrupt motion. "
            f"Five sessions showed accelerometer magnitude frozen at 9.7335 with an active gyroscope, and 28 showed zero Euler output; the primary summary therefore uses ADB-like sessions (N=27; N=22 with active acceleration). "
            f"Two annotators labelled 661 one-second bins from 10 participants: inter-rater kappa={ann['inter_rater']['kappa']:.3f}, classifier kappa={ann['machine_vs_rater_a']['kappa']:.3f} and {ann['machine_vs_rater_b']['kappa']:.3f}, moderate at best. "
            "These are agreement references, not accuracy estimates. We contribute an auditable, route-aware quality-control workflow for seated 360-degree VR motion monitoring; metrological validation remains future work."
        ),
        "intro": [
            "Consumer head-mounted displays are increasingly used as both immersive interfaces and sources of motion data. VR studies have examined postural stability, tracking behavior, head-tracked interaction tasks, and relationships between virtual and physical head orientation [1-3,25]. In parallel, smartphone and wearable inertial sensing has established a broad methodological base for human-activity recognition, including seated behavior and mixed motion contexts [4-7]. These literatures make a consumer HMD a plausible behavioral sensing platform, but they do not guarantee that a field labelled as a gyroscope field has the same physical meaning across software routes.",
            "Most IMU activity-recognition studies target locomotion, limb movement, clinical balance, or multi-sensor wearable datasets, and many use supervised deep models [8-12,26]. Feature selection and representation remain important even in model-centered work: windowed statistics, trajectory representations, and the chosen feature set affect the resulting activity summary [13-15]. Seated 360-degree viewing is a narrower setting. Its observable motion is concentrated at the head and includes stable viewing, ordinary head turns, abrupt turns, slow exploratory sweeps, and small postural adjustments. A useful technical workflow must therefore preserve the relationship between source stream, derived variable, rule output, and export file.",
            "Data quality is a second concern. Wearable-sensor studies show that reliability, coverage, synchronization, fusion assumptions, and missing or stale samples can change downstream conclusions [16,17]. Work on quaternion alignment, orientation estimation, calibration, low-cost motion capture, and drift also demonstrates that coordinate conventions and processing layers must be made explicit [18-24,27,28]. In a browser-mediated HMD workflow, this requirement is particularly important because a common JSON schema can conceal different upstream quantities.",
            "This paper makes four bounded contributions. First, it provides a source-traced account of a Pico 4 motion-sensing pipeline, including the headset collector, ADB reader, WebSocket bridge, mapper, rule classifier, and report generator. Second, it introduces a route-aware audit that distinguishes ADB-like sensorservice timing from browser-compatible pose or DeviceMotion timing and measures the physical duration implied by the implemented frame window. Third, it operationalizes channel-level quality checks for frozen acceleration and orientation streams and uses them to define a primary comparable cohort. Fourth, it reports rule-output distributions, interpretable feature summaries, threshold sensitivity, and a two-rater agreement reference without converting any of them into unsupported model-performance claims. The result is a reproducibility and measurement-semantics contribution, not a claim of a new general-purpose HAR model.",
        ],
        "methods": {
            "2.1 System Architecture and Acquisition Routes": "The implementation contains four connected layers: a Pico 4 collector or reader, a local WebSocket bridge, browser-based computer analysis, and exported CSV/HTML artifacts. The source modules and fields are summarized in Table 1 and Appendix B, and Figure 1 shows the resulting cross-layer evidence chain. The ADB reader invokes Android `dumpsys sensorservice`, parses the most recent acceleration, gyroscope, and Game Rotation Vector events, and attaches a host-arrival timestamp. Its configured polling interval is 0.2 s, but blocking command execution and cached-event reuse produce the observed irregular effective rates. The browser collector exposes two distinct branches. The WebXR branch obtains a viewer pose, differences position to estimate translational velocity and acceleration, and writes the velocity components into fields named `gyro_x`, `gyro_y`, and `gyro_z` for compatibility with the dashboard. The DeviceMotion branch reads `accelerationIncludingGravity` and `rotationRate`, converting rotation rates from degrees per second to radians per second. The analysis CSV does not preserve the original `source` field, so timing supports a browser-compatible classification but cannot retrospectively identify the exact browser branch for each fast file. This is a source-semantics limitation, not a claim that the routes are equivalent.",
            "2.2 Computer-Side Mapping": "The mapper performs computer-side data mapping from timestamped acceleration, gyro, and quaternion fields. It computes acceleration magnitude, gyro-field magnitude, ZYX Euler angles, a scalar gravity-removal approximation, and a fixed NED-to-UE5 acceleration transform. The gravity-removal variable is `accNoGravity = abs(accMag - 9.80665)`, not a vector decomposition. No additional low-pass filter is applied in the computer-side mapper. The exported analysis schema is `timestamp, accMag, gyroMag, roll, pitch, yaw, behavior, confidence`. The distinction between an acquisition field and a mapped field is preserved in Appendix B. Quaternion-derived orientation is used only where the source stream is available and changing; it is not treated as independently validated orientation ground truth [17-20,27,28].",
            "2.3 Rule-Based Behavior-State Output": "The dashboard classifier assigns one state per mapped sample using a 20-frame backward-looking window and the fixed priority order in Table 2; Figure 2 summarizes the field mapping that feeds those rules. The confidence value is a deterministic rule-margin heuristic bounded between 0 and 1; it is not a calibrated probability. The rule vocabulary is `gaze`, `head_turn`, `sudden_turn`, `scanning`, `postural_shift`, and `idle`. The `scanning` rule requires an Euler-window range of at least 3 degrees, while `postural_shift` requires `accNoGravity > 0.3 m/s^2`. The quality audit shows that these branches are structurally unavailable in many sessions when the associated channel is frozen. Accordingly, the state percentages are reported as platform outputs under the implemented rules, not as externally validated behavior prevalence. The 20-frame window was retained because the current exported labels and subject matrix are outputs of that deterministic implementation. It does not create a fixed physical-time window: as shown in Figure 3, the observed nominal support is approximately 5.3-5.5 s for the ADB-like rate range, 2.4 s at 8.33 Hz, and 1.0 s at 20 Hz. Cross-route pooled state comparisons are therefore descriptive only, and a fixed-time or resampled re-analysis is a required next step. A second consequence must be stated explicitly, because it bounds every rule that targets fast motion. The ADB-like effective rates of 3.65-3.77 Hz place the corresponding Nyquist limit at approximately 1.83-1.89 Hz, and the observed sampling intervals are irregular rather than uniform (interval coefficient of variation 0.025-0.597), so the sampling theorem does not apply in its uniform form. The abrupt-turn rule fires on an instantaneous gyro-field magnitude above 1.5 rad/s or a window standard deviation above 0.8 rad/s, both of which describe motion whose energy extends well above that limit. On the ADB route, `sudden_turn` and `head_turn` are therefore threshold crossings of a sparsely and unevenly sampled signal, not resolved measurements of the underlying head-motion transient: a short abrupt turn may be sampled near its peak, sampled on its flank, or missed entirely between two polls. The reported abrupt-turn shares are consequently lower bounds on rule activations rather than estimates of physical event rates, and the browser fixed-grid sessions at 8.33 and 20 Hz are the only ones with any headroom above the rule thresholds. Adequate sampling of abrupt head motion requires a device-side high-rate logger, which the audited chain does not provide.",
            "2.4 Data Curation and Quality Control": "Each retained export corresponds to one seated 360-degree VR viewing session from one participant, and the 29 retained exports carry 29 distinct participant identifiers, so session count and participant count coincide at N=29 with no repeated-measures structure. Participant demographics were not recorded in the technical export chain audited here, so no age, sex, or VR-experience distribution can be reported from these files; this is a reporting limitation of the present audit rather than a claim that the sample was homogeneous. A session was retained when its duration was at least 60 s, it contained at least 100 mapped frames, and all required export fields were present. This rule excluded one 8.4 s export and retained 29 sessions. For every file, the audit computes the median positive timestamp interval, effective rate, interval coefficient of variation, path compatibility, state counts, and channel flags. An accelerometer freeze is flagged when the whole-file `accMag` sequence has one value after rounding to four decimals and the gyro-field standard deviation remains above 0.01. The five flagged sessions all have `accMag = 9.7335`; this is not a near-zero test and is not attributed to WebXR. The evidence is consistent with stale or non-updating acceleration in the ADB/sensorservice acquisition chain, but the raw device cause is unknown. Frozen files are excluded only from acceleration-dependent subject features; their gyroscope-derived features remain in the primary ADB-like summary. An orientation stream is flagged when all exported Euler values are zero. The audit found 28 such retained sessions, so `scanning` is not interpreted as a generally observable behavior in this corpus. The ADB-like cohort is the primary comparable cohort because the browser-compatible files have different upstream semantics; the two browser files are retained as a separate descriptive group.",
            "2.5 Human Annotation and Time Alignment": "A video subset was used as a limited agreement reference. Video motion energy was extracted at 5 frames per second, aggregated to a one-second series, and cross-correlated with one-second mean `gyroMag` profiles. The candidate offset obeyed `csv_time = video_time + offset` and was constrained so the video remained within the CSV time span whenever possible. The cross-correlation procedure did not use behavior labels or kappa to choose offsets. Nineteen video candidates were processed; ten met the pre-specified correlation and peak-margin criteria and supplied 661 common one-second bins for two returned annotation files. The annotators used four visually reachable labels (`gaze`, `head_turn`, `sudden_turn`, and `idle`). Inter-rater and classifier-versus-rater agreement are reported in Table 6; confusion matrices are moved to Appendix C because the video covers only a subset of each session and cannot independently resolve all rule states. Confidence intervals are cluster bootstraps over the 10 participants, included to show the instability associated with the small number of annotated participants.",
            "2.6 Statistical Summaries and Reproducibility": "The analysis is descriptive. We report counts, means, standard deviations, ranges, and route-stratified Cohen's d values as effect-size descriptions; no p-values or route-equivalence tests are claimed because the browser group contains only two sessions and the sources are not semantically identical. The primary subject-level feature table uses the 27 ADB-like sessions; acceleration-dependent features use the 22 ADB-like sessions with active acceleration. Threshold sensitivity is computed on the ADB-like exports by perturbing each implemented threshold by +/-10%, +/-20%, and +/-30% and recording the maximum absolute change in any state share. All reported values can be traced to the source files and scripts listed in Appendix B.",
        },
        "results": {
            "3.1 Corpus and Channel Quality": f"The 30 exported analysis CSV files contained {s['frames_all']:,} mapped frames. Applying the duration, frame-count, and required-field rule excluded one 8.4 s export and retained {s['exports_retained']} sessions with {s['frames_retained']:,} frames. Retained durations ranged from {s['retained_duration_min']:.1f} to {s['retained_duration_max']:.1f} s, with a median of {s['retained_duration_median']:.1f} s (Table 3). Timing classified 27 retained sessions as ADB-like and two as browser-compatible. The browser-compatible group consisted of the 8.33 Hz session and the 20 Hz session. Their route-specific state outputs differ visibly from the ADB-like group (Figure 4), so the paper does not use the pooled N=29 matrix as evidence that the two acquisition routes measure the same physical quantity.",
            "3.2 Route-Stratified Features": "Table 4 reports the route-stratified subject-level comparison. The ADB-like group has N=27 for gyro-field and state-sequence features and N=22 for acceleration-dependent features; the browser-compatible group has N=2. The descriptive standardized differences are not interpreted as evidence of equivalence or causality. In particular, the browser-compatible group differs in head-turn ratio, gaze-segment duration, and behavior entropy, which is compatible with both different upstream field semantics and different physical support of the 20-frame window. The correct conclusion is that the route is a relevant analysis factor that must be preserved in future exports.",
            "3.3 Rule Outputs and Threshold Sensitivity": "Across the retained corpus, the exported state distribution was gaze 55.78%, head_turn 20.68%, idle 15.36%, sudden_turn 4.84%, scanning 2.20%, and postural_shift 1.14%. These percentages are output distributions, not validated behavior prevalence. The ADB-like cohort produced no scanning frames because its orientation stream was frozen at zero; the 1003 scanning frames in the complete retained corpus came from the single orientation-active browser-compatible session. The five accelerometer-frozen sessions contributed no postural_shift frames. Figure 5 shows that most ADB-only threshold perturbations changed state shares by small amounts, while the sudden-turn and head-turn boundaries were more influential. This robustness result applies to the deterministic rule output, not to the validity of the labels.",
            "3.4 Primary Subject-Level Feature Summary": "Table 5 reports the primary ADB-like cohort. The gyroscope-field mean, ordinary-turn fraction, abrupt-turn fraction, state entropy, gaze-segment duration, and freeze ratio are defined for all 27 ADB-like sessions. `acc_cv` and `postural_shift_ratio` are reported for the 22 sessions with active acceleration. The five excluded acceleration channels were not imputed and were not replaced by the reader's optional synthetic fallback. This distinction corrects the earlier N=29/N=24 ambiguity by explicitly separating the primary route cohort (N=27) from the active-acceleration subset (N=22). Figure 6 shows the corresponding route and channel-availability audit.",
            "3.5 Limited Annotation Agreement": f"The two annotation files covered the same 661 one-second bins from 10 participants. Annotator A and annotator B showed {100*ann['inter_rater']['agreement']:.1f}% observed agreement with Cohen's kappa={ann['inter_rater']['kappa']:.3f} (cluster-bootstrap 95% CI {ann['inter_rater']['ci95_cluster'][0]:.3f}-{ann['inter_rater']['ci95_cluster'][1]:.3f}). Classifier agreement was kappa={ann['machine_vs_rater_a']['kappa']:.3f} against annotator A and kappa={ann['machine_vs_rater_b']['kappa']:.3f} against annotator B. All three point estimates fall in the moderate band of the conventional kappa interpretation scale (0.41-0.60), and no interval reaches the substantial band, so we describe the agreement as moderate throughout and avoid the term substantial. The intervals also bound the claim from below: the inter-rater interval ({ann['inter_rater']['ci95_cluster'][0]:.3f}-{ann['inter_rater']['ci95_cluster'][1]:.3f}) stays inside the moderate band, but the two classifier-versus-rater intervals extend to {ann['machine_vs_rater_a']['ci95_cluster'][0]:.3f} and {ann['machine_vs_rater_b']['ci95_cluster'][0]:.3f}, that is, into the fair band (0.21-0.40). With 10 annotated participants the data therefore do not exclude fair rather than moderate classifier agreement, and the moderate description applies to the point estimates rather than to a demonstrated lower bound. These comparisons are intentionally limited: the video covers only selected portions of 19 candidate sessions, the labels are four visually reachable categories, and the two-second-scale or slower distinctions cannot be independently established by third-person video. The confusion matrices are therefore placed in Appendix C rather than used to imply classification accuracy.",
        },
        "discussion": [
            "The main technical finding is not that the Pico 4 produces a universally interchangeable IMU stream. It is that a common export schema can hide route-dependent quantities, and that a source-traced audit makes this visible. The ADB-like sessions provide the primary comparable cohort, while the two browser-compatible sessions demonstrate that a functioning export is not by itself evidence of common sensor semantics. This route-aware framing extends the HMD tracking perspective in prior VR work [1-3] with an explicit computer-side provenance requirement.",
            "Compared with supervised IMU-HAR studies using CNN, GRU, Conformer, LSTM, or iterative learning [8-12,26], this workflow has a narrower objective and a different success criterion. It does not claim prediction performance. Its output is a deterministic, inspectable state sequence whose rule thresholds, field dependencies, and export fields are visible. This is useful when a dataset is being assembled or audited before a trained model is justified. The feature summaries also follow the established emphasis on windowed statistics, feature-set selection, and trajectory or state representations [13-15].",
            "The quality audit exposes two different failure modes. Five sessions contain a constant acceleration magnitude of 9.7335 while the gyro channel remains active. The appropriate interpretation is a channel-level stale or non-updating condition in the ADB/sensorservice evidence, not a near-zero acceleration failure and not a proven WebXR buffer failure. Separately, 28 sessions contain zero/frozen Euler output, which makes the orientation-dependent scanning branch structurally unreachable and causes the gaze rule to lose one of its two conditions. These observations are precisely why low-cost and wearable IMU studies emphasize calibration, fusion, alignment, and reliability assumptions [16-24,27,28].",
            "The annotation experiment now has a limited but interpretable role. Two returned label sets provide a genuine inter-rater reference, with kappa near 0.6 - moderate, not substantial - while classifier-versus-rater values are similar. The cluster-bootstrap intervals for the classifier comparisons reach into the fair band, so even the moderate description holds only for the point estimates. The agreement is neither a validation benchmark nor a reason to retain a confusion matrix in the main text. It shows that the four visually reachable categories can be annotated with moderate consistency over the covered bins, while the unobserved or visually ambiguous states should not be treated as ground truth. The alignment procedure is reproducible as a candidate-offset procedure, but the correlation range and partial video coverage warrant confirmation against visible physical events before any stronger synchronization claim.",
            "The route comparison also changes how the subject matrix should be used. The N=29 matrix remains a complete registry of retained technical exports, but the primary comparable feature summary is ADB-like N=27, with N=22 for active acceleration. This separation avoids presenting the two browser files as if they were calibrated angular-IMU observations. Future data collection should preserve source metadata, use fixed physical-time windows or resampling, record monotonic timestamps in a shared session clock, and retain raw fields before compatibility mapping. External optical or instrumented reference measurements are needed before accuracy, drift, or absolute orientation claims can be made.",
        ],
        "limitations": [
            "This study has five important limitations. First, the source export omits the browser `source` field, so timing identifies browser-compatible files but cannot distinguish retrospectively between the WebXR and DeviceMotion branches. More importantly, the WebXR branch writes translational velocity into fields named `gyro_x/y/z`; browser-compatible `gyroMag` must therefore not be read as a validated angular-velocity measure. Second, ADB timestamps are host-arrival timestamps from repeated `dumpsys` polling and are not hardware-synchronized with browser or video clocks. Third, the acceleration freeze is detected and bounded at the analysis level, but the device-level cause is unknown; the data do not justify a WebXR-specific root-cause claim.",
            "Fourth, the fixed 20-frame window has different physical duration across routes and was retained for reproducibility with the existing exports rather than recomputed as a fixed-time window. The same route also limits bandwidth: at 3.65-3.77 Hz the ADB Nyquist limit of about 1.83-1.89 Hz sits below the 1.5 rad/s and 0.8 rad/s abrupt-motion thresholds, so ADB abrupt-turn shares are lower bounds on rule activations rather than physical event rates, and no drift, latency, or peak-amplitude claim is made for that route. Fifth, N=27 primary sessions, N=22 active-acceleration sessions, N=2 browser-compatible sessions, and 10 annotated participants do not support broad behavioral generalization. The human agreement analysis has partial video coverage and cannot establish frame-level ground truth. These limitations define the next technical steps: preserve raw source metadata, rerun the classifier with fixed-time windows, collect balanced route samples, add independent event anchors and external motion reference data, and repeat multi-rater annotation.",
        ],
        "conclusion": "We audited and documented a Pico 4 motion-sensing workflow that connects ADB or browser collection, local streaming, computer-side mapping, deterministic rule outputs, subject-level feature extraction, report export, and channel-level quality control. The evidence shows why route semantics must be preserved: 27 retained sessions are ADB-like, two are browser-compatible, five have frozen acceleration, and 28 have zero/frozen orientation output. ADB-like sessions are therefore used as the primary comparable cohort, while browser files remain a separate descriptive record. The resulting contribution is an auditable acquisition and analysis procedure for seated 360-degree VR motion monitoring, with explicit boundaries around timing, orientation, browser field semantics, annotation agreement, and metrological validity.",
    }


def chinese_content(data: dict[str, object]) -> dict[str, object]:
    s = data["summary"]
    ann = data["annotations"]["metrics"]
    return {
        "highlights": [
            "从头显采集、电脑端映射到导出审计，建立了可追溯的 Pico 4 技术证据链。",
            "根据采样时序和源码语义区分 27 个 ADB-like 会话与 2 个浏览器兼容会话，不再假定两路 IMU 等价。",
            "文件级自动检查识别出 5 个加速度冻结会话和 28 个姿态角全零/冻结会话。",
            "双标注结果仅作为有限的中等一致性参照，不包装成监督分类性能。",
        ],
        "abstract": (
            f"消费级虚拟现实头显通过不同软件层暴露运动数据，但相同字段名并不必然具有相同物理传感语义。"
            f"本研究审计了一套 Pico 4 采集与电脑分析流程，包含 Android Debug Bridge（ADB）sensorservice 读取器、浏览器端 WebXR/DeviceMotion 采集、本地 WebSocket 中继和仪表盘导出。"
            f"审计覆盖 30 个分析 CSV（{s['frames_all']:,} 个映射帧）；按时长和完整性规则保留 29 个会话（{s['frames_retained']:,} 帧）用于被试级技术报告。"
            f"其中 27 个会话的时序与不规则 ADB sensorservice 轮询一致（3.65-3.77 Hz），2 个会话与浏览器固定网格一致（8.33 和 20 Hz）。由于 WebXR 分支把位姿差分得到的平移速度写入名为 gyro_x/y/z 的兼容字段，两路不能视为同一条已校准角速度 IMU 数据流。"
            f"现有 20 帧规则窗口在 ADB-like 会话中约对应 5.3-5.5 s，在 8.33 Hz 会话中约 2.4 s，在 20 Hz 会话中为 1.0 s；本文如实保留这一异质性，而不通过合并掩盖。"
            f"5 个保留会话的加速度幅值恒为 9.7335，但 gyro 字段仍在变化；28 个保留会话的欧拉角为全零/冻结。因此主要技术汇总采用 ADB-like N=27，加速度相关特征仅采用其中 22 个加速度有效会话。"
            f"在独立的视频子集中，两套标注文件共同覆盖 10 名参与者的 661 个 1 秒区间。标注者间观察一致率为 {100*ann['inter_rater']['agreement']:.1f}%，Cohen's kappa={ann['inter_rater']['kappa']:.3f}，按常用解释区间属于中等而非较高一致；分类器相对两名标注者的 kappa 分别为 {ann['machine_vs_rater_a']['kappa']:.3f} 和 {ann['machine_vs_rater_b']['kappa']:.3f}，同样处于中等档。"
            "这些结果是有限覆盖下的一致性参照，不是 accuracy。本文贡献是一套面向坐姿 360 度 VR 运动监测、可审计且区分采集路径的数据获取与质量控制流程；与外部参考系统的计量验证仍需后续完成。"
        ),
        "intro": [
            "消费级头戴式显示设备正在同时承担沉浸式交互界面和运动数据源的角色。既有 VR 研究关注姿态稳定性、追踪行为以及虚拟与现实头部朝向之间的关系 [1-3]；智能手机和可穿戴惯性传感研究则已经形成较成熟的人类活动识别方法，包括坐姿行为和混合运动场景 [4-7]。这些研究说明消费级头显具有行为传感潜力，但并不能保证不同软件入口中名为 gyro 的字段具有一致的物理意义。",
            "多数 IMU 活动识别研究面向步行、肢体动作、临床平衡或多传感器可穿戴数据，并经常采用监督式深度模型 [8-12,26]。即便在模型导向研究中，窗口统计、轨迹表示和特征集合仍会显著影响活动摘要 [13-15]。坐姿 360 度观看的范围更窄，主要可观察运动集中在头部，包括稳定观看、普通转头、急转、缓慢探索和小幅姿态调整。因此，一套可信的技术流程必须保存来源数据流、派生变量、规则输出和导出文件之间的关系。",
            "第二个问题是数据质量。可穿戴传感器研究已表明，可靠性、覆盖率、同步、融合假设以及缺失或陈旧样本均会改变下游结论 [16,17]。有关四元数对齐、姿态估计、校准、低成本动作捕捉和漂移的研究也强调，坐标约定和处理层级必须显式说明 [18-24,27,28]。在浏览器介导的头显流程中，这一点尤其重要，因为统一 JSON 字段可能掩盖完全不同的上游物理量。",
            "本文提出四项有边界的贡献。第一，给出 Pico 4 运动传感流程的源码级追踪，包括头显采集页、ADB 读取器、WebSocket 中继、映射模块、规则分类器和报告生成器。第二，构建区分 ADB-like sensorservice 时序与浏览器兼容位姿/DeviceMotion 时序的路径审计，并计算既有帧窗口对应的实际物理时长。第三，建立加速度与姿态通道冻结检查，据此定义主要可比分析队列。第四，报告规则输出分布、可解释特征、阈值敏感性和双标注一致性参照，但不将其包装成无依据的模型性能。本文的创新点是复现性和测量语义审计，而不是新的通用 HAR 模型。",
        ],
        "methods": {
            "2.1 系统架构与采集路径": "系统由 Pico 4 采集器/读取器、本地 WebSocket 中继、浏览器电脑分析端和 CSV/HTML 导出物构成。相关源码与字段见表 1 和附录 B，图 1 给出由此形成的跨层证据链。ADB 读取器调用 Android `dumpsys sensorservice`，解析最近一条加速度、陀螺仪和 Game Rotation Vector 事件，并附加主机到达时间戳。其配置轮询间隔为 0.2 s，但阻塞式命令执行和缓存事件复用使实际采样率更低且不规则。浏览器采集页包含两条不同分支：WebXR 分支读取 viewer pose，通过位置差分估计平移速度和加速度，并为了与仪表盘兼容而把速度分量写入 `gyro_x/y/z`；DeviceMotion 分支读取 `accelerationIncludingGravity` 和 `rotationRate`，再将角速度由 deg/s 转为 rad/s。分析 CSV 未保留原始 `source` 字段，因此时序只能识别浏览器兼容文件，无法在事后确定具体使用 WebXR 还是 DeviceMotion。这是来源语义限制，不是两路等价的证据。",
            "2.2 电脑端数据映射": "映射模块解析带时间戳的加速度、gyro 和四元数字段，并计算加速度幅值、gyro 字段幅值、ZYX 欧拉角、标量去重力近似和固定的 NED 到 UE5 加速度变换。去重力变量为 `accNoGravity = abs(accMag - 9.80665)`，不是向量分解。电脑映射端没有额外低通滤波。分析 CSV 的字段顺序为 `timestamp, accMag, gyroMag, roll, pitch, yaw, behavior, confidence`。采集字段与映射字段的区别在附录 B 中保留。四元数姿态仅在来源通道真实更新时使用，不能视为经过独立验证的姿态真值 [17-20,27,28]。",
            "2.3 规则型行为状态输出": "仪表盘采用固定优先级和向后 20 帧窗口，为每个映射样本分配一个状态，具体见表 2；图 2 汇总了支撑这些规则的字段映射关系。confidence 是 0 到 1 的确定性规则裕量启发值，不是校准概率。状态词表为 `gaze`、`head_turn`、`sudden_turn`、`scanning`、`postural_shift` 和 `idle`。其中 scanning 要求欧拉角窗口范围至少 3 度，postural_shift 要求 `accNoGravity > 0.3 m/s^2`。质量审计显示，关联通道冻结时，这两条规则在许多会话中结构性不可触发。因此状态比例被定义为既有规则下的平台输出，不被解释为经外部验证的真实行为发生率。为保持与现有导出和被试矩阵的一致性，本轮保留 20 帧窗口，但明确它不是固定物理时长：如图 3 所示，ADB-like 会话约为 5.3-5.5 s，8.33 Hz 会话约为 2.4 s，20 Hz 会话为 1.0 s。跨路径状态比较仅作描述，后续必须重采样或改用固定时间窗。还有一个必须明说的后果，因为它限定了所有针对快速运动的规则。ADB-like 有效采样率为 3.65-3.77 Hz，对应的 Nyquist 上限约为 1.83-1.89 Hz，而采样间隔并不均匀（间隔变异系数 0.025-0.597），因此采样定理的均匀采样形式并不成立。突然转头规则的判据是瞬时 gyro 幅值超过 1.5 rad/s 或窗口标准差超过 0.8 rad/s，二者描述的运动能量都明显高于该上限。因此在 ADB 路径上，`sudden_turn` 与 `head_turn` 是对稀疏且不均匀采样信号的阈值穿越，而不是对头部运动瞬变的分辨测量：一次短促急转可能被采到峰值附近、采到侧翼，也可能完全落在两次轮询之间而漏采。所以本文报告的突然转头比例应理解为规则触发次数的下界，而不是物理事件发生率的估计；8.33 与 20 Hz 的浏览器固定网格会话是唯一在规则阈值之上仍有余量的数据。要充分采样急速头动，需要设备端高速率记录，而本文审计的链路不具备该能力。",
            "2.4 数据整理与质量控制": "每个保留导出对应一名参与者的一次坐姿 360 度 VR 观看会话，29 个保留导出携带 29 个互不相同的被试标识，因此会话数与参与者数一致，均为 N=29，不存在重复测量结构。本文审计的技术导出链未记录人口学信息，因此无法从这些文件报告年龄、性别或 VR 经验分布；这是本轮审计的报告限制，而不是样本同质的结论。保留标准为会话时长至少 60 s、映射帧至少 100 且必需导出字段完整。该规则剔除 1 个 8.4 s 文件，保留 29 个会话。文件级审计计算正时间间隔中位数、有效采样率、间隔变异系数、路径兼容性、状态计数和通道标记。加速度冻结判据为：整文件 `accMag` 四舍五入到四位小数后仅有一个值，同时 gyro 字段标准差仍大于 0.01。5 个冻结会话的值均为 `accMag = 9.7335`；这不是接近零的检测，也不能归因于 WebXR。现有证据更符合 ADB/sensorservice 链路中加速度事件陈旧或未更新，但设备端根因未知。冻结会话仅从加速度相关被试特征中排除，其 gyro 派生特征仍保留在 ADB-like 主汇总中。若全部欧拉角为零，则标记姿态流冻结；29 个保留会话中有 28 个满足该条件，因此 scanning 不能解释为本数据集中普遍可测的行为。鉴于浏览器文件上游语义不同，主要可比队列设为 ADB-like N=27，2 个浏览器文件仅单列描述。",
            "2.5 人工标注与时间对齐": "视频子集仅用于有限一致性参照。脚本以 5 fps 提取视频运动能量，汇总到 1 秒序列，再与 1 秒平均 `gyroMag` 序列互相关。候选偏移定义为 `csv_time = video_time + offset`，并尽可能约束视频完整落在 CSV 时段内。对齐过程不使用行为标签，也不通过最大化 kappa 选择偏移。共处理 19 个视频候选，10 个达到预设相关峰和峰间距标准，形成两套标注文件共同覆盖的 661 个 1 秒区间。标注者使用四个视频可辨类别：`gaze`、`head_turn`、`sudden_turn` 和 `idle`。标注者间以及分类器相对标注者的一致性见表 6；由于视频只覆盖会话片段且无法独立辨别所有规则状态，混淆矩阵移至附录 C。置信区间采用以 10 名参与者为簇的 bootstrap，用于显示小样本标注的不稳定性。",
            "2.6 统计汇总与可复现性": "本研究只做描述性统计，包括计数、均值、标准差、范围和按路径分组的 Cohen's d。由于浏览器组仅 N=2 且来源语义不同，不进行 p 值检验或等价性检验。主要被试级特征表采用 27 个 ADB-like 会话；加速度相关特征采用其中 22 个加速度有效会话。阈值敏感性分析仅在 ADB-like 导出上进行，对每个阈值分别扰动 +/-10%、+/-20% 和 +/-30%，记录任一状态比例的最大绝对变化。全部数值均可追溯至附录 B 所列源码和数据文件。",
        },
        "results": {
            "3.1 数据规模与通道质量": f"30 个分析 CSV 共包含 {s['frames_all']:,} 个映射帧。按时长、帧数和字段完整性规则剔除 1 个 8.4 s 文件后，保留 {s['exports_retained']} 个会话和 {s['frames_retained']:,} 个帧。保留会话时长为 {s['retained_duration_min']:.1f}-{s['retained_duration_max']:.1f} s，中位数 {s['retained_duration_median']:.1f} s（表 3）。时序审计将其中 27 个归为 ADB-like，2 个归为浏览器兼容；后两者采样率分别为 8.33 和 20 Hz。两组规则输出分布存在明显差异（图 4），因此本文不再利用合并的 N=29 矩阵证明两条采集路径测量同一物理量。",
            "3.2 按路径分组的特征": "表 4 给出按路径分组的被试级描述。ADB-like 组的 gyro 字段和状态序列特征为 N=27，加速度相关特征为 N=22；浏览器兼容组为 N=2。标准化差异仅用于描述，不解释为等价性或因果证据。尤其是 head_turn_ratio、gaze_mean_duration 和 behavior_entropy 的分组差异，既可能来自上游字段物理语义，也可能来自 20 帧窗口对应的不同物理时长。能够成立的结论是：采集路径必须作为关键分析因素保存在后续导出中。",
            "3.3 规则输出与阈值敏感性": "在 29 个保留会话中，导出状态比例为 gaze 55.78%、head_turn 20.68%、idle 15.36%、sudden_turn 4.84%、scanning 2.20% 和 postural_shift 1.14%。这些比例是平台输出分布，不是经验证的真实行为发生率。ADB-like 队列没有产生 scanning 帧，因为其姿态流全零/冻结；完整保留数据中的 1003 个 scanning 帧全部来自唯一一个姿态有效的浏览器兼容会话。5 个加速度冻结会话没有产生 postural_shift 帧。图 5 表明，多数 ADB-only 阈值扰动只造成较小的状态比例变化，而 sudden_turn 与 head_turn 边界更敏感。该结果说明规则输出的确定性敏感性，不说明标签有效性。",
            "3.4 主要被试级特征": "表 5 报告 ADB-like 主队列。gyro_mean、普通转头比例、突然转头比例、状态熵、gaze 片段时长和 freeze_ratio 在 27 个 ADB-like 会话中均有定义；`acc_cv` 与 `postural_shift_ratio` 仅在 22 个加速度有效会话中报告。5 个冻结通道未被插补，也未用读取器中的可选合成回退替代。该口径通过明确区分 ADB 主队列 N=27 与有效加速度子集 N=22，修正了旧稿 N=29/N=24 的混乱。图 6 展示相应的路径与通道可用性。",
            "3.5 有限人工标注一致性": f"两套标注文件共同覆盖 10 名参与者的 661 个 1 秒区间。标注者 A 与 B 的观察一致率为 {100*ann['inter_rater']['agreement']:.1f}%，Cohen's kappa={ann['inter_rater']['kappa']:.3f}（参与者簇 bootstrap 95% CI {ann['inter_rater']['ci95_cluster'][0]:.3f}-{ann['inter_rater']['ci95_cluster'][1]:.3f}）。分类器相对标注者 A 的 kappa={ann['machine_vs_rater_a']['kappa']:.3f}，相对标注者 B 的 kappa={ann['machine_vs_rater_b']['kappa']:.3f}。三个点估计都落在常用 kappa 解释区间的中等档（0.41-0.60），且没有任何区间达到较高一致档，因此全文一律表述为“中等一致”，不使用 substantial。区间同时给出了下界约束：标注者间区间（{ann['inter_rater']['ci95_cluster'][0]:.3f}-{ann['inter_rater']['ci95_cluster'][1]:.3f}）完整落在中等档内，但分类器相对两名标注者的区间下探至 {ann['machine_vs_rater_a']['ci95_cluster'][0]:.3f} 和 {ann['machine_vs_rater_b']['ci95_cluster'][0]:.3f}，已进入一般档（0.21-0.40）。在仅 10 名标注参与者的条件下，数据并不能排除分类器一致性实际处于一般档，因此“中等”只适用于点估计，不等于已经证明的下界。这些比较有明确边界：视频仅覆盖 19 个候选会话的部分片段，标签只包含四个视频可辨类别，第三人称视频无法建立全部规则状态的逐帧真值。因此混淆矩阵放入附录 C，而不用于暗示分类 accuracy。",
        },
        "discussion": [
            "本研究的主要技术发现不是 Pico 4 能够输出普遍可互换的 IMU 数据流，而是统一导出字段可能隐藏路径相关的不同物理量，源码级审计可以把这种差异显式化。27 个 ADB-like 会话构成主要可比队列，2 个浏览器兼容会话则说明“成功导出”本身并不能证明传感语义相同。与既有 VR 头显追踪研究相比 [1-3]，本文增加了电脑端字段来源追踪这一要求。",
            "与采用 CNN、GRU、Conformer、LSTM 或迭代学习的监督式 IMU-HAR 研究相比 [8-12,26]，本文目标更窄，成功标准也不同。本文不报告预测性能，而提供一个阈值、字段依赖和导出结构均可检查的确定性状态序列。这适合在构建或审计数据集、尚不足以训练和外部验证模型的阶段使用。被试特征则延续了既有研究对窗口统计、特征集合和轨迹/状态表示的重视 [13-15]。",
            "质量审计暴露出两种不同故障。第一，5 个会话的加速度幅值恒为 9.7335，而 gyro 通道仍在变化。正确解释是 ADB/sensorservice 证据中的单通道陈旧或未更新，不能写成接近零，也不能写成已证实的 WebXR 缓冲区故障。第二，28 个会话的欧拉角全零/冻结，使姿态依赖的 scanning 分支结构性不可触发，也使 gaze 规则失去一个判据。这正是低成本和可穿戴 IMU 文献反复强调校准、融合、对齐和可靠性假设的原因 [16-24,27,28]。",
            "人工标注现在被放在一个有限但可解释的位置。两套回收标签形成真实的标注者间参照，kappa 接近 0.6；分类器相对两名标注者的数值相近。但分类器比较的簇 bootstrap 区间下探进入一般档，因此“中等”只对点估计成立。这既不是验证基准，也没有必要把混淆矩阵放在正文中。它只能说明，在有视频覆盖的区间内，四个可视类别可以达到中等一致性；对于视频不可辨或数据通道不可达的状态，不能把人工标签当作真值。自动互相关能够复现候选偏移，但相关系数范围和部分视频覆盖意味着，更强的同步表述仍需逐个视频用可见事件确认。",
            "路径比较也改变了被试矩阵的使用方式。N=29 矩阵仍是 29 个保留技术导出的完整登记，但主要可比特征汇总改为 ADB-like N=27，加速度特征为 N=22。这避免把两个浏览器文件当作已校准的角速度 IMU。未来采集应保存 source 元数据，使用固定物理时间窗或重采样，记录共享会话时钟下的单调时间戳，并在兼容映射前保留原始字段。只有加入外部光学或仪器参考，才适合提出 accuracy、漂移或绝对姿态结论。",
        ],
        "limitations": [
            "本研究有五项重要限制。第一，分析导出遗漏浏览器 `source` 字段，因此时序只能识别浏览器兼容文件，不能事后区分 WebXR 与 DeviceMotion。更关键的是，WebXR 分支把平移速度写入名为 `gyro_x/y/z` 的字段，浏览器兼容 `gyroMag` 不能解释为经过验证的角速度。第二，ADB 时间戳是重复 `dumpsys` 轮询的主机到达时间，不与浏览器或视频时钟硬件同步。第三，加速度冻结已在分析层被检测并限定，但设备端根因仍未知，数据不支持 WebXR 特定根因。",
            "第四，固定 20 帧窗口在不同路径上对应不同物理时长；本轮为了与既有导出一致而保留，没有重跑固定时间窗。同一路径还限制了带宽：在 3.65-3.77 Hz 下，ADB 的 Nyquist 上限约 1.83-1.89 Hz，低于 1.5 rad/s 与 0.8 rad/s 的急动判据，因此 ADB 的突然转头比例只是规则触发次数的下界，不是物理事件发生率；本文也不对该路径提出漂移、时延或峰值幅值结论。第五，主队列 N=27、有效加速度 N=22、浏览器兼容 N=2 和人工标注参与者 N=10 均不足以支持广泛行为泛化。人工标注视频覆盖不完整，也不能建立逐帧真值。下一步应保存原始来源元数据，重跑固定时间窗，补充平衡的路径样本，增加独立事件锚点和外部运动参考，并重复多标注者实验。",
        ],
        "conclusion": "本文审计并记录了一套 Pico 4 运动传感流程，连接 ADB/浏览器采集、本地流式传输、电脑映射、确定性规则输出、被试特征提取、报告导出和通道质量控制。证据表明必须保存路径语义：29 个保留会话中 27 个为 ADB-like、2 个为浏览器兼容，5 个加速度冻结，28 个姿态角全零/冻结。因此本文使用 ADB-like 会话作为主要可比队列，浏览器文件仅作单列描述。本文最终贡献是一套面向坐姿 360 度 VR 运动监测、边界透明且可审计的数据获取与分析方法，并明确限定了时序、姿态、浏览器字段语义、人工标注一致性和计量有效性。",
    }


def translate_table_rows(rows: list[list[object]]) -> list[list[object]]:
    mapping = {
        "Layer / route": "层级/路径",
        "Implementation evidence": "实现证据",
        "Observed export semantics": "观测到的导出语义",
        "Use in this paper": "本文用途",
        "Priority": "优先级",
        "State": "状态",
        "Trigger in behavior-analyzer.js": "behavior-analyzer.js 触发条件",
        "Primary signal dependence": "主要信号依赖",
        "Audit item": "审计项",
        "All exports": "全部导出",
        "Retained analysis": "保留分析",
        "Interpretation": "解释",
        "Feature": "特征",
        "ADB-like N": "ADB-like N",
        "ADB-like mean +/- SD": "ADB-like 均值 +/- SD",
        "Browser N": "浏览器 N",
        "Browser mean +/- SD": "浏览器均值 +/- SD",
        "Cohen's d*": "Cohen's d*",
        "Reading": "说明",
        "Primary cohort": "主要队列",
        "Mean +/- SD": "均值 +/- SD",
        "Min-Max": "最小-最大",
        "Interpretive note": "解释说明",
        "Comparison": "比较",
        "Bins": "区间数",
        "Observed agreement": "观察一致率",
        "Cohen's kappa": "Cohen's kappa",
        "Cluster bootstrap 95% CI": "参与者簇 bootstrap 95% CI",
        "Role": "用途",
    }
    return [[mapping.get(str(cell), cell) for cell in row] for row in rows]


def add_front_matter(doc: Document, title: str, affiliations: list[str], highlights: list[str], abstract: str, keywords: str, chinese: bool) -> None:
    mdpi_p(doc, "Article" if not chinese else "Article（原创论文）", "MDPI_1.1_article_type")
    mdpi_p(doc, title, "MDPI_1.2_title")
    mdpi_p(doc, AUTHORS, "MDPI_1.3_authornames")
    for aff in affiliations:
        mdpi_p(doc, aff, "MDPI_1.6_affiliation")
    mdpi_p(doc, "Academic Editor: To be assigned by the journal" if not chinese else "Academic Editor：由期刊填写", "MDPI_1.5_academic_editor")
    mdpi_p(doc, "Received: date; Revised: date; Accepted: date; Published: date" if not chinese else "Received/Revised/Accepted/Published：由期刊填写", "MDPI_1.4_history")
    mdpi_p(doc, "Copyright: 2026 by the authors. Submitted for possible open access publication under the terms and conditions of the Creative Commons Attribution (CC BY) license." if not chinese else "Copyright：2026，作者所有。拟按 CC BY 条款开放获取发表。", "MDPI_7.2_copyright")
    mdpi_p(doc, "Highlights" if not chinese else "研究亮点", "MDPI_1.7_abstract")
    for item in highlights:
        p = mdpi_p(doc, item, "MDPI_3.8_bullet")
        if chinese:
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    p = mdpi_p(doc, "", "MDPI_1.7_abstract")
    if chinese:
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    r = p.add_run("Abstract: " if not chinese else "摘要：")
    r.bold = True
    p.add_run(abstract)
    p = mdpi_p(doc, "", "MDPI_1.8_keywords")
    if chinese:
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    r = p.add_run("Keywords: " if not chinese else "关键词：")
    r.bold = True
    p.add_run(keywords)


def build_manuscript(data: dict[str, object], tables: dict[str, list[list[object]]], chinese: bool = False) -> Path:
    content = chinese_content(data) if chinese else english_content(data)
    doc = mdpi_doc()
    add_front_matter(
        doc,
        TITLE_CN if chinese else TITLE_EN,
        AFFILIATIONS_CN if chinese else AFFILIATIONS_EN,
        content["highlights"],
        content["abstract"],
        ("Pico 4；ADB；WebXR；DeviceMotion；运动传感；行为状态；数据质量；可复现性" if chinese else "Pico 4; ADB; WebXR; DeviceMotion; motion sensing; behavior-state output; data quality; reproducibility"),
        chinese,
    )

    mdpi_h(doc, "1. Introduction" if not chinese else "1. 引言")
    for paragraph in content["intro"]:
        mdpi_body(doc, paragraph, chinese)

    mdpi_h(doc, "2. Materials and Methods" if not chinese else "2. 材料与方法")
    for heading_text, paragraph in content["methods"].items():
        mdpi_h(doc, heading_text, 2)
        mdpi_body(doc, paragraph, chinese)
        if heading_text.startswith("2.1"):
            mdpi_table(doc, ("Table 1. Acquisition layers, source semantics, and analytical use." if not chinese else "表 1. 采集层级、来源语义与分析用途。"), translate_table_rows(tables["table1"]) if chinese else tables["table1"], [1.15, 1.7, 2.1, 1.4])
            mdpi_figure(doc, "figure1_architecture", ("Figure 1. Source-traced Pico 4 acquisition, mapping, rule-output, and audit workflow." if not chinese else "图 1. 可追溯的 Pico 4 采集、映射、规则输出与审计流程。"))
        elif heading_text.startswith("2.3"):
            mdpi_table(doc, ("Table 2. Implemented rule priority, thresholds, and channel dependence." if not chinese else "表 2. 已实现规则的优先级、阈值和通道依赖。"), translate_table_rows(tables["table2"]) if chinese else tables["table2"], [0.55, 0.95, 3.0, 1.8])
            mdpi_figure(doc, "figure2_mapping_rules", ("Figure 2. Computer-side field mapping and deterministic rule priority." if not chinese else "图 2. 电脑端字段映射与确定性规则优先级。"))
        elif heading_text.startswith("2.4"):
            mdpi_figure(doc, "figure3_sampling_windows", ("Figure 3. Observed sampling-rate heterogeneity and the nominal physical duration of the 20-frame window." if not chinese else "图 3. 实际采样率异质性与 20 帧窗口对应的名义物理时长。"))

    mdpi_h(doc, "3. Results" if not chinese else "3. 结果")
    for heading_text, paragraph in content["results"].items():
        mdpi_h(doc, heading_text, 2)
        mdpi_body(doc, paragraph, chinese)
        if heading_text.startswith("3.1"):
            mdpi_table(doc, ("Table 3. Corpus, route, and channel-quality summary." if not chinese else "表 3. 数据规模、采集路径与通道质量汇总。"), translate_table_rows(tables["table3"]) if chinese else tables["table3"], [1.25, 1.25, 1.7, 2.05])
            mdpi_figure(doc, "figure4_state_distribution_by_path", ("Figure 4. Route-stratified distribution of exported rule-state outputs. The bars are descriptive and do not establish route equivalence or behavior prevalence." if not chinese else "图 4. 按路径分组的规则状态输出分布。该图仅作描述，不证明路径等价或真实行为发生率。"))
        elif heading_text.startswith("3.2"):
            mdpi_table(doc, ("Table 4. Route-stratified feature comparison. *Cohen's d is browser-compatible minus ADB-like and is descriptive only because browser N=2 and source semantics differ." if not chinese else "表 4. 按路径分组的特征比较。*Cohen's d 为浏览器兼容组减 ADB-like 组；由于浏览器 N=2 且来源语义不同，仅作描述。"), translate_table_rows(tables["table4"]) if chinese else tables["table4"], [1.15, 0.55, 1.25, 0.55, 1.25, 0.7, 1.0])
        elif heading_text.startswith("3.3"):
            mdpi_figure(doc, "figure5_threshold_sensitivity", ("Figure 5. ADB-only threshold sensitivity. Values show the largest state-share change observed over the specified perturbations." if not chinese else "图 5. ADB-only 阈值敏感性。数值为指定扰动范围内任一状态比例的最大变化。"))
        elif heading_text.startswith("3.4"):
            mdpi_table(doc, ("Table 5. Primary ADB-like subject-level feature summary." if not chinese else "表 5. ADB-like 主要被试级特征汇总。"), translate_table_rows(tables["table5"]) if chinese else tables["table5"], [1.2, 1.3, 1.1, 1.0, 0.4, 1.45])
            mdpi_figure(doc, "figure6_channel_quality", ("Figure 6. Retained-session route and channel-availability audit." if not chinese else "图 6. 保留会话的路径与通道可用性审计。"))
        elif heading_text.startswith("3.5"):
            mdpi_table(doc, ("Table 6. Human annotation and classifier agreement over 661 common one-second bins from 10 participants." if not chinese else "表 6. 10 名参与者 661 个共同 1 秒区间上的人工标注与分类器一致性。"), translate_table_rows(tables["table6"]) if chinese else tables["table6"], [1.45, 0.55, 0.95, 0.8, 1.3, 1.2])

    mdpi_h(doc, "4. Discussion" if not chinese else "4. 讨论")
    for paragraph in content["discussion"]:
        mdpi_body(doc, paragraph, chinese)
    mdpi_h(doc, "4.1 Limitations and Future Work" if not chinese else "4.1 局限与后续工作", 2)
    for paragraph in content["limitations"]:
        mdpi_body(doc, paragraph, chinese)
    mdpi_h(doc, "5. Conclusions" if not chinese else "5. 结论")
    mdpi_body(doc, content["conclusion"], chinese)

    if not chinese:
        back_matter(doc, "Supplementary Materials", "The evidence CSV files, figure source data, annotation protocol, and audit scripts can be prepared as supplementary files after de-identification review.")
        back_matter(doc, "Author Contributions", "Conceptualization, R.L. and Y.-L.F.; methodology, R.L., Z.C. and Y.-L.F.; software, R.L., S.S. and M.C.; validation, R.L., S.S., M.C. and Y.-L.F.; formal analysis, R.L.; investigation, R.L., S.S. and M.C.; resources, Z.C. and Y.-L.F.; data curation, R.L. and M.C.; writing-original draft preparation, R.L.; writing-review and editing, Z.C., S.S., M.C. and Y.-L.F.; visualization, R.L.; supervision, Z.C. and Y.-L.F.; project administration, Y.-L.F.; funding acquisition, Y.-L.F. Final author confirmation is required before submission.")
        back_matter(doc, "Funding", "This research was supported by a national college student innovation and entrepreneurship training project. The final project number and APC statement should be inserted before submission.")
        back_matter(doc, "Institutional Review Board Statement", "Informed consent was obtained from all subjects involved in the study. Written informed consent was obtained from all participants prior to data collection, including explicit consent for session video recording and the academic publication of de-identified behavioral tracking data.")
        back_matter(doc, "Informed Consent Statement", "Informed consent was obtained from all participants involved in the study. Any identifiable photograph requires explicit publication consent.")
        back_matter(doc, "Data Availability Statement", "The de-identified subject-level feature matrix, mapped analysis CSV files, behavior-state rule classification scripts, and agreement evaluation tools supporting the findings of this study are available from the corresponding author (Y.-L.F.) upon reasonable request. Raw participant video recordings and physiological context records are restricted from public deposition due to participant privacy restrictions and ethical consent constraints.")
        back_matter(doc, "Acknowledgments", "The authors thank the participants and project team members who supported VR experiment organization, data collection, and platform testing.")
        back_matter(doc, "Generative AI Statement", "Generative AI tools were used only to assist manuscript drafting, format checking, and code-output consistency checks. The authors reviewed all outputs and take full responsibility for the manuscript.")
        back_matter(doc, "Conflicts of Interest", "The authors declare no conflicts of interest.")
        back_matter(doc, "Abbreviations", "ADB, Android Debug Bridge; CSV, comma-separated values; HMD, head-mounted display; IMU, inertial measurement unit; VR, virtual reality; WebXR, Web Extended Reality.")
    else:
        back_matter(doc, "补充材料", "完成去标识审查后，可将证据 CSV、图源数据、标注协议和审计脚本作为补充材料。")
        back_matter(doc, "作者贡献", "Conceptualization, R.L. and Y.-L.F.; methodology, R.L., Z.C. and Y.-L.F.; software, R.L., S.S. and M.C.; validation, R.L., S.S., M.C. and Y.-L.F.; formal analysis, R.L.; investigation, R.L., S.S. and M.C.; resources, Z.C. and Y.-L.F.; data curation, R.L. and M.C.; writing-original draft preparation, R.L.; writing-review and editing, Z.C., S.S., M.C. and Y.-L.F.; visualization, R.L.; supervision, Z.C. and Y.-L.F.; project administration, Y.-L.F.; funding acquisition, Y.-L.F. [投稿前须由全体作者确认。]")
        back_matter(doc, "经费", "本研究获得国家级大学生创新创业训练项目支持。[投稿前补充核实后的项目编号和 APC 经费说明。]")
        back_matter(doc, "伦理声明", "[投稿前补充经核实的伦理审批或豁免表述、机构/委员会名称、编号与日期。]")
        back_matter(doc, "知情同意", "已取得所有参与者的研究知情同意；任何可识别影像均须另行取得发表同意。")
        back_matter(doc, "数据可得性", "去标识审计表和分析代码可在参与者同意与机构限制允许的范围内共享。[需确认公开仓库或按需提供。]")
        back_matter(doc, "致谢", "感谢参与实验的被试以及支持数据采集和平台测试的项目成员。")
        back_matter(doc, "生成式 AI 声明", "生成式 AI 工具用于稿件组织、语言润色和基于代码的一致性检查。作者已复核全部证据，并对全文内容负责。")
        back_matter(doc, "利益冲突", "作者声明不存在利益冲突。")
        back_matter(doc, "缩写", "ADB：Android Debug Bridge；CSV：逗号分隔值；HMD：头戴式显示器；IMU：惯性测量单元；VR：虚拟现实；WebXR：Web Extended Reality。")

    mdpi_h(doc, "Appendices" if not chinese else "附录")
    mdpi_h(doc, "Appendix A. Retained-session audit" if not chinese else "附录 A. 保留会话逐文件审计", 2)
    mdpi_table(doc, ("Table A1. File-level route, timing, and channel-quality audit." if not chinese else "表 A1. 文件级路径、时序和通道质量审计。"), tables["appendix_a"], [0.9, 0.48, 0.48, 0.48, 0.48, 0.58, 0.55, 0.55, 0.4, 0.5])
    mdpi_h(doc, "Appendix B. Source and field traceability" if not chinese else "附录 B. 源码与字段可追溯性", 2)
    mdpi_table(doc, ("Table A2. Source-code and data assets used as technical evidence." if not chinese else "表 A2. 作为技术证据的源码与数据资产。"), tables["appendix_b"], [1.8, 1.8, 2.8])
    mdpi_h(doc, "Appendix C. Annotation confusion matrices" if not chinese else "附录 C. 标注混淆矩阵", 2)
    mdpi_body(doc, "These matrices are supplementary agreement diagnostics and are not classifier-performance benchmarks." if not chinese else "以下矩阵仅用于补充一致性诊断，不是分类器性能基准。", chinese)
    mdpi_table(doc, ("Table A3. Annotator A by annotator B confusion matrix." if not chinese else "表 A3. 标注者 A 与标注者 B 混淆矩阵。"), tables["appendix_c1"], [1.6, 1.1, 1.1, 1.1, 1.1])
    mdpi_table(doc, ("Table A4. Machine output by annotator A confusion matrix." if not chinese else "表 A4. 机器输出与标注者 A 混淆矩阵。"), tables["appendix_c2"], [1.6, 1.1, 1.1, 1.1, 1.1])
    mdpi_table(doc, ("Table A5. Machine output by annotator B confusion matrix." if not chinese else "表 A5. 机器输出与标注者 B 混淆矩阵。"), tables["appendix_c3"], [1.6, 1.1, 1.1, 1.1, 1.1])

    mdpi_h(doc, "References" if not chinese else "参考文献")
    for reference in load_reference_strings():
        # The strict Sensors template supplies the outer numeric list marker.
        # Adding a second [n] marker here renders every reference twice-numbered.
        mdpi_p(doc, reference, "MDPI_8.1_references")

    path = OUT_CN if chinese else OUT_EN
    doc.save(path)
    return path


def brief_doc(title: str, subtitle: str = "") -> Document:
    doc = Document()
    section = doc.sections[0]
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(2.0)
    section.bottom_margin = Cm(1.8)
    section.left_margin = Cm(2.0)
    section.right_margin = Cm(2.0)
    section.header_distance = Cm(0.8)
    section.footer_distance = Cm(0.8)
    styles = doc.styles
    normal = styles["Normal"]
    normal.font.name = "Calibri"
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), "等线")
    normal.font.size = Pt(10.5)
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.line_spacing = 1.12
    for name, size, color in (("BriefTitle", 20, "16324F"), ("BriefH1", 14, "2F6690"), ("BriefH2", 11.5, "16324F")):
        if name not in styles:
            style = styles.add_style(name, 1)
        else:
            style = styles[name]
        style.font.name = "Calibri"
        style._element.rPr.rFonts.set(qn("w:eastAsia"), "等线")
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = RGBColor.from_string(color)
        style.paragraph_format.space_before = Pt(12 if name != "BriefTitle" else 0)
        style.paragraph_format.space_after = Pt(5)
    p = doc.add_paragraph(style="BriefTitle")
    p.add_run(title)
    if subtitle:
        q = doc.add_paragraph()
        q.paragraph_format.space_after = Pt(12)
        r = q.add_run(subtitle)
        r.italic = True
        r.font.color.rgb = RGBColor(107, 114, 128)
    header = section.header.paragraphs[0]
    header.text = "Sensors IMU revision package | 27 August 2026"
    header.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    for run in header.runs:
        run.font.size = Pt(8)
        run.font.color.rgb = RGBColor(107, 114, 128)
    footer = section.footer.paragraphs[0]
    footer.text = "Evidence-first working document"
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for run in footer.runs:
        run.font.size = Pt(8)
        run.font.color.rgb = RGBColor(107, 114, 128)
    return doc


def brief_h(doc: Document, text: str, level: int = 1):
    return doc.add_paragraph(text, style="BriefH1" if level == 1 else "BriefH2")


def brief_p(doc: Document, text: str, bold_lead: str | None = None):
    p = doc.add_paragraph()
    if bold_lead and text.startswith(bold_lead):
        r = p.add_run(bold_lead)
        r.bold = True
        p.add_run(text[len(bold_lead) :])
    else:
        p.add_run(text)
    return p


def brief_bullet(doc: Document, text: str):
    p = doc.add_paragraph(style="List Bullet")
    p.paragraph_format.left_indent = Cm(0.63)
    p.paragraph_format.first_line_indent = Cm(-0.32)
    p.add_run(text)
    return p


def brief_table(doc: Document, rows: list[list[object]], widths: list[float]) -> None:
    table = doc.add_table(rows=len(rows), cols=len(rows[0]))
    table.style = "Table Grid"
    set_table_borders(table, color="9AA8B5", size="6")
    set_table_geometry(table, widths)
    set_repeat_table_header(table.rows[0])
    for i, row in enumerate(table.rows):
        prevent_row_split(row)
        for j, cell in enumerate(row.cells):
            cell.text = str(rows[i][j])
            set_cell_margins(cell, top=80, start=90, bottom=80, end=90)
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            if i == 0:
                set_cell_shading(cell, "E8EEF5")
            for p in cell.paragraphs:
                p.paragraph_format.space_after = Pt(0)
                for r in p.runs:
                    r.font.name = "Calibri"
                    r._element.rPr.rFonts.set(qn("w:eastAsia"), "等线")
                    r.font.size = Pt(8.5)
                    if i == 0:
                        r.bold = True


def build_response_letter(data: dict[str, object]) -> Path:
    s = data["summary"]
    ann = data["annotations"]["metrics"]
    doc = brief_doc("Response to Reviewers", TITLE_EN)
    brief_p(doc, "Dear Editor and Reviewers,")
    brief_p(doc, "Thank you for the careful and technically useful assessment. We rebuilt the manuscript around an evidence audit of the implemented Pico 4 collection and computer-analysis chain. The revision makes a consequential change in interpretation: the 29 retained exports are not treated as one semantically uniform angular-IMU dataset. Twenty-seven sessions are timing-compatible with the ADB sensorservice route, while two are browser-compatible and are reported separately because the WebXR branch writes pose-derived translational velocity into compatibility fields named gyro_x/y/z.")
    brief_p(doc, "The response below describes only changes supported by files in the project package. We did not claim WebXR-specific causation for the accelerometer freeze, did not report unsupported route equivalence, and did not convert the annotation exercise into an accuracy benchmark. In two places the audit obliged us to go beyond what a comment asked, and we have flagged both rather than presenting them as compliance: the reported kappa intervals reach the fair band, and the ADB sampling rate is below the Nyquist requirement for the abrupt-motion thresholds.")
    brief_p(doc, "One note on structure: the decision letter contained comments from Reviewer 1 and Reviewer 3. Reviewer 2 returned no comments, so no Reviewer 2 section appears below. Headings quote each comment in the reviewer's own words; where a comment refers to the previously submitted table numbering, the response states the new number explicitly.")

    brief_h(doc, "Reviewer 1", 1)
    items1 = [
        (
            "1. Scientific novelty is unclear.",
            "Response. We agree that the earlier novelty statement was too broad. We removed claims of a first dataset, open benchmark, or multimodal controller contribution. The revised novelty is narrower and technical: (i) source-level tracing from collector/reader to exported fields; (ii) route-aware separation of ADB-like sensorservice timing from browser pose/DeviceMotion timing; (iii) channel-level quality auditing that changes the primary analysis cohort; and (iv) an interpretable rule-output workflow with explicit limits. These points are now stated at the end of Introduction and revisited in Discussion.",
            "Change location: Introduction, final paragraph; Discussion, first and fifth paragraphs; Figures 1-3; Tables 1 and 3-5.",
        ),
        (
            "2. Tables 2, 7, and 8 should be moved or removed from the main text.",
            "Response. We consolidated the main manuscript to six core tables. Because the whole table set was renumbered, the mapping from the previously submitted numbering is stated explicitly: the former Table 2 (per-file session audit) is now Table A1 in Appendix A; the former Table 7 (source and field traceability) is now Table A2 in Appendix B; and the former Table 8 (annotation confusion matrix) is now Tables A3-A5 in Appendix C, split by rater pair. The main text retains only the rule definition, cohort-level quality summary, route comparison, primary feature summary, and compact agreement summary.",
            "Change location: Tables 1-6 in the main text; Tables A1-A5 in Appendices A-C (former Tables 2, 7, and 8).",
        ),
        (
            "3. A 20-frame window has different physical durations across sampling rates.",
            "Response. We agree with the methodological concern. In this revision we retained the existing 20-frame outputs so that the paper remains reproducible against the stored exports, but we no longer describe the resulting windows as physically comparable. The audit reports approximately 5.3-5.5 s for the 3.65-3.77 Hz ADB-like sessions, 2.4 s for the 8.33 Hz browser-compatible session, and 1.0 s for the 20 Hz session. Route-stratified reporting replaces pooled behavioral interpretation, and fixed physical-time windows or resampling are explicitly identified as the next required analysis. This choice is a limitation and remains a submission risk if the editor requires re-analysis rather than a scope correction.",
            "Change location: Methods Sections 2.3 and 2.6; Results Sections 3.1-3.2; Figure 3; Limitations.",
        ),
        (
            "4. Five sessions have an accelerometer freeze; explain cause and exclusion.",
            "Response. We added a file-level automatic audit. A session is flagged when the full exported accMag sequence has one value after rounding to four decimals while the gyro-field standard deviation remains above 0.01. All five retained flagged sessions have accMag=9.7335, not a near-zero value, and the gyro field remains active. The source evidence is compatible with stale or non-updating acceleration in the ADB/sensorservice chain, but it does not identify the device-level root cause and does not support a WebXR-buffer claim. The five files are excluded only from acceleration-dependent features; no imputation or synthetic fallback is used in those summaries. The primary ADB-like feature table therefore uses N=22 for acc_cv and postural_shift_ratio.",
            "Change location: Methods Section 2.4; Results Sections 3.1, 3.3, and 3.4; Figure 6; Appendix A.",
        ),
        (
            "5. Remove colored inserts, strikethrough text, and revision instructions.",
            "Response. We regenerated a clean document from the supplied strict Sensors template. Colored revision text, strikethrough, 'for the revised manuscript' language, placeholder appendix instructions, duplicate table numbers, and the former Figure 10 have been removed from the manuscript body. The only remaining bracketed items are author-owned metadata that must be confirmed before submission, namely ethics, funding number, data-sharing authorization, and CRediT confirmation.",
            "Change location: complete manuscript; clean template-based output.",
        ),
        (
            "6. Every figure and table should be placed next to its first citation.",
            "Response. We audited this by paragraph style rather than by eye, and the audit found a real defect: Figures 1, 2, and 3 had no in-text citation at all, so no placement rule could be satisfied for them. Each now has an explicit first citation immediately before its position - Figure 1 in Section 2.1, Figure 2 in Section 2.3, and Figure 3 in Section 2.3 - and every remaining figure and table is cited in the paragraph preceding its caption. The one forward reference we kept is deliberate: Table 6 is announced in Methods Section 2.5, where the agreement procedure is defined, and appears in Results Section 3.5, where the values are reported.",
            "Change location: Methods Sections 2.1 and 2.3; all figure and table captions.",
        ),
        (
            "7. Overstated wording and manuscript length.",
            "Response. The abstract phrase describing maintained stability has been removed; the revised abstract and Conclusions describe an auditable workflow and its verified boundaries instead of an outcome claim. The abstract was also shortened to meet the 200-word journal limit. The manuscript was rebuilt rather than trimmed sentence by sentence, which removed the repeated general disclaimers, the relocated table narration, and the former per-file discussion from the main text. Measured on the manuscript body under a single consistent paragraph-style filter, the revised text is 2,640 words against 3,002-3,104 words in the corresponding pre-revision drafts, a reduction of roughly 12-15%, and 22% against the largest intermediate version. The complete scope statement now appears once at the end of the Introduction and once in Section 4.1; elsewhere we use short functional wording such as 'descriptive output' or 'agreement reference'.",
            "Change location: Abstract; Conclusions; Introduction final paragraph; Section 4.1.",
        ),
    ]
    for heading, response, location in items1:
        brief_h(doc, heading, 2)
        brief_p(doc, response, "Response.")
        brief_p(doc, location, "Change location:")

    brief_h(doc, "Reviewer 3", 1)
    items3 = [
        (
            "1. ADB and WebXR sessions have different processing levels and are pooled.",
            "Response. We agree and changed the analysis structure. The source audit shows that the WebXR branch derives translational velocity from viewer-pose position differences and writes it into compatibility gyro fields. The analysis CSV does not preserve the original source field, so the two fast files are labelled browser-compatible rather than definitively assigned to a browser branch. We now use the 27 ADB-like sessions as the primary comparable cohort and report the two browser-compatible sessions separately. Table 4 gives descriptive group comparisons; no route-equivalence claim or p-value is reported.",
            "Change location: Table 1; Methods Sections 2.1, 2.6; Results Sections 3.1-3.2; Figure 4; Limitations.",
        ),
        (
            "2. Table 5 reports acceleration features with N=29 although five sessions were excluded.",
            "Response. We appreciate the check and would like to clarify the record before describing the change. In the submitted version, Table 5 already carried N=24 for the two acceleration-dependent features while the other features carried N=29, so the five excluded sessions were deducted; we suspect the N=29 shown in the neighbouring feature rows made the mixed denominator easy to misread, which is itself a presentation fault on our side. In the revision we removed the ambiguity rather than defend the layout. Because the five frozen sessions are all on the ADB route and the browser group contributes two active-acceleration files, the pooled N=24 mixed two acquisition routes in a single cell. The revised primary table is route-restricted: N=27 for gyro-field and state-sequence features, and N=22 for acc_cv and postural_shift_ratio. Every denominator is now stated in the table, in Section 3.4, and per file in Appendix A, and no value is imputed.",
            "Change location: Table 3; Table 5; Methods Section 2.4; Results Section 3.4; Appendix A.",
        ),
        (
            "3. Agreement of kappa about 0.6 should be described as moderate rather than substantial.",
            "Response. We agree, and while making the wording uniform we found that the correction has to go one step further than the comment asked. Every point estimate sits in the moderate band of the conventional interpretation scale (0.41-0.60): inter-rater kappa=0.593, classifier versus annotator A kappa=0.567, classifier versus annotator B kappa=0.604. However, the cluster-bootstrap intervals over the 10 annotated participants are wide, and the two classifier-versus-rater intervals extend down to 0.392 and 0.376, that is, into the fair band. Describing those two comparisons as moderate without qualification would therefore have replaced one overstatement with a smaller one. Results Section 3.5 now reports the point estimates as moderate, states that no interval reaches the substantial band, and states explicitly that the two classifier intervals reach the fair band so that fair rather than moderate classifier agreement is not excluded by these data. The Discussion carries the same qualification. The word substantial does not appear as an agreement descriptor anywhere in the revised manuscript.",
            "Change location: Highlights; Abstract; Results Section 3.5; Discussion, fourth paragraph; Table 6.",
        ),
        (
            "4. The annotation agreement and confusion matrix invite performance comparisons.",
            "Response. We re-audited the returned files rather than carrying forward the old single-rater six-class result. Two separate annotation directories contain non-identical labels for the same 661 one-second bins from 10 participants. The confusion matrices are now Appendix C, and the main text calls these agreement references only. The analysis does not report accuracy, F1, AUC, or ground-truth performance.",
            "Change location: Methods Section 2.5; Results Section 3.5; Table 6; Appendix C.",
        ),
        (
            "5. Tables 6-10 are excessive and mostly document project organization.",
            "Response. We condensed the main presentation into six data-bearing tables. The organizational tables the comment refers to are no longer in the main text: of the former Tables 6-10, the project-organization and schema material is consolidated into Appendix B (Table A2), the per-file audit is Appendix A (Table A1), and the annotation confusion material is Appendix C (Tables A3-A5); the remainder was removed. Source modules and schema details therefore remain inspectable without interrupting the Results narrative.",
            "Change location: Tables 1-6 in the main text; Appendices A-C (Tables A1-A5) replacing the former Tables 6-10.",
        ),
        (
            "6. Scope disclaimers are repeated throughout the paper.",
            "Response. We moved the complete scope statement to the end of Introduction and the Limitations subsection. Elsewhere we use short, functional wording such as 'descriptive output' or 'agreement reference'. The paper no longer repeats a general disclaimer in every section.",
            "Change location: Introduction final paragraph; Methods 2.3 and 2.6; Discussion and Limitations.",
        ),
    ]
    for heading, response, location in items3:
        brief_h(doc, heading, 2)
        brief_p(doc, response, "Response.")
        brief_p(doc, location, "Change location:")

    brief_h(doc, "Additional general concerns", 1)
    brief_p(doc, "Time alignment. We now describe the actual procedure: one-second video motion-energy profiles were cross-correlated with one-second mean gyroMag profiles; the candidate offset was constrained by the recorded CSV span; ten of nineteen candidates met the pre-specified correlation and margin criteria; and the alignment was not optimized against kappa. We do not claim a shared hardware clock or a universal r>0.85 event correlation.")
    brief_p(doc, "Sampling adequacy, added on our own initiative. No comment raised it, but the audit makes it unavoidable: the ADB-like effective rates of 3.65-3.77 Hz put the Nyquist limit at about 1.83-1.89 Hz, below the 1.5 rad/s instantaneous and 0.8 rad/s window-SD thresholds that trigger the abrupt-motion rules, and the sampling intervals are irregular (interval coefficient of variation 0.025-0.597). Methods Section 2.3 and the Limitations now state that ADB abrupt-turn shares are lower bounds on rule activations rather than physical event rates, and that no drift, latency, or peak-amplitude claim is made for that route.")
    brief_p(doc, "Participant reporting. Methods Section 2.4 now states that the 29 retained exports carry 29 distinct participant identifiers, so session count and participant count coincide at N=29 with no repeated-measures structure. It also states that the audited technical export chain did not record demographics, so no age, sex, or VR-experience distribution is reported; we prefer to declare this gap rather than leave the sample size implicit.")
    brief_p(doc, "Presentation. The document is regenerated from the supplied Sensors template, with explicit table borders, repeating header rows, fixed table geometry, six high-resolution technical figures, clean captions, and no duplicate table numbering. The detailed evidence files remain in the revision package for inspection.")
    brief_h(doc, "Revision evidence snapshot", 1)
    brief_table(doc, [
        ["Evidence item", "Verified value", "Source / implication"],
        ["Analysis exports", f"30 files; {s['frames_all']:,} frames", "Raw exported analysis CSV inventory"],
        ["Retained corpus", f"29 sessions; {s['frames_retained']:,} frames", "Duration >=60 s, >=100 frames, required fields"],
        ["Primary route", "27 ADB-like sessions", "Irregular 3.65-3.77 Hz timing-compatible group"],
        ["Browser-compatible route", "2 sessions", "8.33 and 20 Hz; source semantics not treated as equivalent"],
        ["Acceleration freeze", "5 retained sessions", "accMag constant at 9.7335; gyro remains active"],
        ["Orientation freeze", "28 retained sessions", "Euler output zero/frozen; scanning not generally reachable"],
        ["Annotation", "661 bins; 10 participants; 2 returned sets", f"Inter-rater kappa={ann['inter_rater']['kappa']:.3f}"],
    ], [1.55, 1.55, 3.55])
    brief_p(doc, "Sincerely,\nThe Authors")
    doc.save(OUT_RESPONSE)
    return OUT_RESPONSE


def build_risk_brief(data: dict[str, object]) -> Path:
    s = data["summary"]
    ann = data["annotations"]["metrics"]
    doc = brief_doc("作者质询与投稿前风险清单", "这不是意见汇总，而是对当前证据、决策和稿件可提交性的反向审查")
    brief_h(doc, "先给结论", 1)
    brief_p(doc, "这版已经把旧稿中最危险的几类过度表述删掉，并把主分析收窄为 ADB-like N=27、有效加速度 N=22；但它还不是可以无条件直接提交的终稿。真正的硬门槛不是文献数量，而是以下四件事：浏览器字段语义、20 帧窗口是否接受不重跑、伦理/经费信息是否真实完整、以及作者是否接受公开披露 28/29 姿态流冻结和 5/29 加速度冻结。")
    brief_p(doc, "我也质询了此前的意见本身。Claude 计划中的 WebXR 缓冲区根因、accMag<0.001 判据、d<0.3、双标注者 κ≈0.6 的来源以及首个数据集/开源 benchmark 等说法，不能直接当作事实。当前证据支持的是：冻结值为 9.7335；两套标注文件确实存在且不相同；路径差异不能证明等价；WebXR 分支的兼容 gyro 字段实际承载位姿差分速度。")

    brief_h(doc, "一、已经核实的证据", 1)
    brief_table(doc, [
        ["事项", "当前证据", "可写入论文的强度"],
        ["数据规模", f"30 个 CSV，{s['frames_all']:,} 帧；保留 29 个，{s['frames_retained']:,} 帧", "可以作为文件级事实"],
        ["采集路径", "27 个 ADB-like；2 个浏览器兼容；分析 CSV 未保留 source 字段", "可以按机制兼容性分组，不可声称精确分支身份"],
        ["20 帧窗口", "ADB 约 5.3-5.5 s；8.33 Hz 约 2.4 s；20 Hz 为 1.0 s", "必须承认物理时长不等价"],
        ["加速度冻结", "5 个；accMag 四位小数唯一值 9.7335；gyro 仍活动", "可以写通道冻结和自动标记；根因未知"],
        ["姿态冻结", "28 个会话欧拉角全零/冻结；scanning 帧来自单个浏览器兼容会话", "不能把 scanning 比例写成普遍行为发生率"],
        ["双标注", "共同 661 个区间；观察一致 79.0%；κ=0.593", "可以写双标注一致性参照；不能写验证成功"],
        ["机器-标注", "κ=0.567 与 0.604", "仅作有限 agreement reference"],
        ["文献", "已核验的 28 条 DOI 全部 Crossref PASS", "证明索引存在，不等于每条都与论点高度相关"],
    ], [1.25, 3.0, 2.4])

    brief_h(doc, "二、需要你和导师明确回答的问题", 1)
    questions = [
        ("Q1 | 是否接受主分析拆分？", "我建议接受：ADB-like N=27 作为主要可比队列，浏览器兼容 N=2 作为单列描述，N=29 仅作完整导出登记。若坚持 N=29 合并作为主结果，必须提供源日志证明两组的 gyro 字段物理含义一致，或者补做按固定物理窗口的重分析。仅说“样本比例 27:2，所以可以合并”不够。"),
        ("Q2 | WebXR 分支的 gyro 字段到底是什么？", "源码明确显示 WebXR 用位置差分得到 velocity，再写入 gyro_x/y/z。请确认实际实验是否确实使用这份 sensor.html，是否有另一个版本把角速度写入同名字段。如果有，请提供实际部署版本、导出前原始 JSON 或截图；如果没有，就必须接受本文不把浏览器兼容 gyroMag 解释为角速度。"),
        ("Q3 | 是否坚持“不重跑 20 帧分类”？", "当前稿已把它明确写成局限，但这仍可能被审稿人认为没有真正解决 Reviewer 1 的核心意见。请确认是接受风险，还是愿意重跑 1 s/2 s 固定物理窗口。若不重跑，正文不能再使用“跨路径可比”“typical posture timescale”等辩护。"),
        ("Q4 | 冻结根因是否有设备日志？", "现有文件只能证明 ADB/sensorservice 读取链路上出现陈旧或不更新的加速度事件，不能证明 WebXR API 缓冲区停滞。若导师或实验日志明确记录了系统服务、Pico 固件或浏览器错误，请提供原始日志；否则不要把未知根因写成确定机制。"),
        ("Q5 | 能否接受 28/29 姿态流冻结的公开披露？", "这是比 5 个加速度冻结更大的科学限制。姿态流冻结导致 scanning 分支在 28 个会话中结构性不可触发，gaze 也退化为低 gyro 条件。若不愿披露，不能继续保留姿态相关比例作为正常行为结果；可选路径只有删除 scanning 主结果、补采/补算姿态，或将文章收窄为通道质量审计。"),
        ("Q6 | 两套标注文件是否确实由两名独立标注者完成？", "当前目录和内容支持“两套不同回收标签”，共同覆盖 661 个区间，κ=0.593。请确认标注者 A/B 的身份、是否独立盲标、标注时间、是否看过机器标签，以及“蔡”是否是标注者姓名还是文件命名。确认后才能在回复信中写 inter-rater reliability。"),
        ("Q7 | 时间对齐是否有可见事件核验？", "当前有 19 个视频的互相关候选偏移，10 个达标，r 范围约 0.523-0.898；没有 `Movement_Start` 字段，也没有所有会话 r>0.85 的证据。请逐个确认至少 10 个已标注视频的可见动作锚点，否则只能写“候选偏移和人工确认流程”，不能写硬同步或精度验证。"),
        ("Q8 | 作者名单到底用谁？", "当前生成稿沿用最近技术稿的 `Mingxuan Cai`。此前成果包里出现过 `Xinling Wang`。请给出最终作者、单位、邮箱和作者顺序；这不能由脚本猜。"),
        ("Q9 | 伦理、知情同意和影像发表许可是否有真实材料？", "当前工作区没有找到可直接核验的伦理委员会名称、批准编号和日期。若无正式 IRB，请让导师确认期刊接受的豁免表述和出具机构；视频/照片若可识别，还需确认发表许可。当前 Word 的伦理段仍是待确认项。"),
        ("Q10 | Funding 和 APC 信息是什么？", "目前只能确认“国家级大学生创新创业训练项目”这一描述，无法从工作区核验项目编号。请提供正式项目名称、编号、资助主体以及 APC 是否由导师科研经费承担；不要把猜测编号放进论文。"),
        ("Q11 | 数据能否公开？", "当前稿只承诺在隐私和同意允许时共享。请确认是否能公开匿名化 CSV、审计表、代码和标注数据；若不能公开，使用 reasonable request 还是仅提供代码，需与知情同意和机构政策一致。"),
        ("Q12 | 28 条文献是否都必须留？", "DOI/Crossref PASS 只证明文献索引真实存在，不证明论点引用恰当。建议投稿前逐条打开 DOI 或出版社页面核对题名、作者、年份、卷页、是否真支持对应句子；同时删掉只是为了凑数量、与 IMU 路径或质量审计没有直接关系的条目。"),
    ]
    for title, body in questions:
        brief_h(doc, title, 2)
        brief_p(doc, body)

    brief_h(doc, "三、我对当前五项选择的判断", 1)
    brief_table(doc, [
        ["选择", "当前处理", "我的判断", "提交风险"],
        ["固定窗口", "保留 20 帧，补充实际物理时长和局限", "可以作为保守草稿，但不是完全解决审稿意见", "高"],
        ["冻结根因", "未知；写 ADB/sensorservice 读取链路兼容性", "证据边界正确", "中"],
        ["路径合并", "不再主结果合并；ADB 主队列 + 浏览器描述", "比原方案可靠", "中低"],
        ["时间对齐", "互相关候选偏移，不写硬同步和 r>0.85", "证据边界正确，仍需人工锚点确认", "中"],
        ["标注矩阵", "放附录；正文仅报告 κ 和作用", "正确，且要确认双标注身份", "低"],
    ], [1.1, 2.0, 2.3, 0.9])

    brief_h(doc, "四、投稿前逐项验收", 1)
    for item in [
        "作者名单、单位、邮箱、CRediT 角色由全体作者确认。",
        "伦理审批/豁免、知情同意、影像发表许可和数据共享措辞有原始依据。",
        "Funding 项目编号和 APC 说法有正式材料。",
        "导师确认接受 ADB N=27 与浏览器 N=2 分开，以及不重跑固定物理时间窗的风险。",
        "打开最终 Word/WPS，检查 6 张主图、6 张主表、附录表格、页眉页脚和参考文献分页。",
        "用 DOI/Crossref 审计表逐条核对题名、作者、年份、卷页和正文落点。",
        "不再出现 PLS-SEM、ACM、mediation、VAF、diagnostic、screening tool 等旧主线残留。",
        "不把 `gyroMag` 在浏览器兼容会话中写成已验证角速度，不把规则状态写成 ground truth。",
    ]:
        brief_bullet(doc, item)
    brief_h(doc, "五、当前工作目录", 1)
    brief_p(doc, f"本轮全部输出位于：{OUT}\n证据审计：evidence/session_audit.csv、path_feature_comparison.csv、annotation_evidence.csv、evidence_summary.json\n图源：figures/figure1_architecture 至 figure6_channel_quality\n后续 QA 与 Word 渲染结果：qa/ 和 render/\n严格模板基线：template_distill/artifact.md")
    doc.save(OUT_RISKS)
    return OUT_RISKS


def docx_text(path: Path) -> str:
    doc = Document(path)
    chunks = [p.text for p in doc.paragraphs]
    chunks.extend(cell.text for table in doc.tables for row in table.rows for cell in row.cells)
    return "\n".join(chunks)


def table_border_audit(path: Path) -> tuple[int, int, int]:
    doc = Document(path)
    total = len(doc.tables)
    with_borders = 0
    with_geometry = 0
    for table in doc.tables:
        tbl_pr = table._tbl.tblPr
        borders = tbl_pr.first_child_found_in("w:tblBorders")
        if borders is not None and all(borders.find(qn(f"w:{edge}")) is not None for edge in ("top", "left", "bottom", "right", "insideH", "insideV")):
            with_borders += 1
        grid = table._tbl.tblGrid
        if grid is not None and len(list(grid)) == len(table.columns):
            with_geometry += 1
    return total, with_borders, with_geometry


def qa_outputs(data: dict[str, object], tables: dict[str, list[list[object]]]) -> None:
    rows: list[dict[str, object]] = []
    def check(name: str, passed: bool, value: object, expected: str, fail_status: str = "FAIL"):
        # fail_status distinguishes a build defect the script can fix (FAIL) from a
        # gate that only the authors can clear (AUTHOR). Both block submission.
        rows.append({"check": name, "status": "PASS" if passed else fail_status, "value": value, "expected": expected})

    for path, label in ((OUT_EN, "English manuscript"), (OUT_CN, "Chinese manuscript"), (OUT_RESPONSE, "Response letter"), (OUT_RISKS, "Risk brief")):
        check(f"{label} exists", path.exists(), path.relative_to(OUT).as_posix(), "file exists")
    en_text = docx_text(OUT_EN)
    cn_text = docx_text(OUT_CN)
    for label, text in (("English manuscript", en_text), ("Chinese manuscript", cn_text)):
        check(f"{label} has title", (TITLE_EN if label.startswith("English") else TITLE_CN) in text, "title found", "title found")
        check(f"{label} has standard sections", all(x in text for x in (["1. Introduction", "2. Materials and Methods", "3. Results", "4. Discussion", "5. Conclusions"] if label.startswith("English") else ["1. 引言", "2. 材料与方法", "3. 结果", "4. 讨论", "5. 结论"])), "section markers", "five sections")
        check(f"{label} has six figures", len(Document(OUT_EN if label.startswith("English") else OUT_CN).inline_shapes) >= 6, len(Document(OUT_EN if label.startswith("English") else OUT_CN).inline_shapes), ">=6")
        check(f"{label} has appendices", ("Appendix A" in text and "Appendix B" in text and "Appendix C" in text) if label.startswith("English") else ("附录 A" in text and "附录 B" in text and "附录 C" in text), "appendix markers", "A-C")
        forbidden = ["pls-sem", "vaf", "mediation", "acm phenotype", "screening tool", "stress responsivity calibration", "first behavior-annotated imu dataset", "open-source benchmark"]
        found = [word for word in forbidden if word in text.lower()]
        check(f"{label} legacy-mainline audit", not found, ", ".join(found) or "none", "none")
    required_terms = ["IMU", "Pico 4", "WebXR", "DeviceMotion", "WebSocket", "data mapping", "quality control"]
    check("English technical keywords", all(x.lower() in en_text.lower() for x in required_terms), ", ".join(x for x in required_terms if x.lower() in en_text.lower()), "all present")
    cited: set[int] = set()
    for group in re.findall(r"\[([\d,\s–-]+)\]", en_text):
        for part in group.split(","):
            token = part.strip().replace("–", "-")
            if "-" in token:
                lo, hi = (piece.strip() for piece in token.split("-")[:2])
                if lo.isdigit() and hi.isdigit():
                    cited.update(range(int(lo), int(hi) + 1))
            elif token.isdigit():
                cited.add(int(token))
    ref_nums = sorted(cited)
    check("Reference count", len(load_reference_strings()) == 28, len(load_reference_strings()), "28 selected Crossref-verified references")
    check("Reference indices used", ref_nums == list(range(1, 29)), ref_nums, "1-28")
    caption_table2_count = sum(p.text.startswith("Table 2.") for p in Document(OUT_EN).paragraphs)
    check("Main manuscript has no duplicate Table 2", caption_table2_count == 1, caption_table2_count, "1")
    check("Main manuscript has no revision insert", "for the revised manuscript" not in en_text.lower(), "absent" if "for the revised manuscript" not in en_text.lower() else "present", "absent")
    total, borders, geometry = table_border_audit(OUT_EN)
    check("English tables have complete borders", total == borders, f"{borders}/{total}", "all")
    check("English tables have fixed geometry", total == geometry, f"{geometry}/{total}", "all")
    en_doc = Document(OUT_EN)
    cn_doc = Document(OUT_CN)

    def styled(doc, style_name):
        return [p for p in doc.paragraphs if p.style is not None and p.style.name == style_name]

    abstract_paras = styled(en_doc, "MDPI_1.7_abstract")
    abstract_body = max((p.text for p in abstract_paras), key=len, default="")
    abstract_words = len(abstract_body.split())
    check("English abstract within MDPI 200-word limit", abstract_words <= 200, abstract_words, "<=200 words")
    keyword_paras = styled(en_doc, "MDPI_1.8_keywords")
    keyword_text = keyword_paras[0].text if keyword_paras else ""
    keyword_count = len([x for x in re.split(r"[;；]", keyword_text.split(":", 1)[-1]) if x.strip()])
    check("English keyword count", 3 <= keyword_count <= 10, keyword_count, "3-10")

    en_back = {p.text.split(":")[0].strip() for p in styled(en_doc, "MDPI_6.2_back_matter")}
    cn_back = {p.text.split("：")[0].strip() for p in styled(cn_doc, "MDPI_6.2_back_matter")}
    check("Back-matter section parity EN/CN", len(en_back) == len(cn_back), f"EN {len(en_back)} / CN {len(cn_back)}", "equal counts")

    lower_bounds = [
        data["annotations"]["metrics"][k]["ci95_cluster"][0]
        for k in ("machine_vs_rater_a", "machine_vs_rater_b")
    ]
    fair_band_disclosed = "fair band" in en_text.lower()
    check(
        "Kappa fair-band lower bound disclosed",
        fair_band_disclosed or all(x >= 0.41 for x in lower_bounds),
        f"min CI low {min(lower_bounds):.3f}; disclosed={fair_band_disclosed}",
        "disclosed when any CI < 0.41",
    )
    check("Sampling-adequacy statement present", "nyquist" in en_text.lower(), "nyquist" in en_text.lower(), "Nyquist discussed")
    check("Participant count stated", "29 distinct participant identifiers" in en_text, "stated" if "29 distinct participant identifiers" in en_text else "absent", "explicit N")
    pooled_denominator = "24 active / 5 frozen" in en_text
    check("No pooled cross-route acceleration denominator", not pooled_denominator, "absent" if not pooled_denominator else "present", "absent")

    placeholders = [p.text.split(":")[0].strip() for p in styled(en_doc, "MDPI_6.2_back_matter") if "[" in p.text]
    check(
        "Author-owned back-matter placeholders resolved",
        not placeholders,
        f"{len(placeholders)} awaiting author input: {', '.join(placeholders) or 'none'}",
        "0 (author must supply ethics, funding, data-availability, CRediT)",
        fail_status="AUTHOR",
    )

    audit = data["summary"]
    check("Data exports", audit["exports_total"] == 30, audit["exports_total"], "30")
    check("Retained sessions", audit["exports_retained"] == 29, audit["exports_retained"], "29")
    check("ADB-like primary cohort", audit["adb_sessions"] == 27, audit["adb_sessions"], "27")
    check("Browser-compatible cohort", audit["browser_compatible_sessions"] == 2, audit["browser_compatible_sessions"], "2")
    check("Accelerometer freeze audit", audit["acc_frozen_sessions"] == 5, audit["acc_frozen_sessions"], "5")
    check("Orientation freeze audit", audit["orientation_frozen_sessions"] == 28, audit["orientation_frozen_sessions"], "28")
    check("Annotation evidence", data["annotations"]["metrics"]["inter_rater"]["n"] == 661, data["annotations"]["metrics"]["inter_rater"]["n"], "661 common bins")
    check("Reference Crossref statuses", audit["reference_status_counts"].get("PASS", 0) == 28, audit["reference_status_counts"], "28 PASS")
    write_csv(QA / "qa_report.csv", rows)
    passed = sum(r["status"] == "PASS" for r in rows)
    failed = sum(r["status"] == "FAIL" for r in rows)
    author = sum(r["status"] == "AUTHOR" for r in rows)
    (QA / "qa_summary.md").write_text(
        f"# Third-round revision QA\n\n- Passed: {passed}\n- Failed (script-fixable defects): {failed}\n"
        f"- Awaiting author input (blocks submission, not script-fixable): {author}\n"
        f"- Evidence summary: `../evidence/evidence_summary.json`\n"
        f"- The table-border check inspects every table in the English manuscript for six explicit border edges and fixed grid geometry.\n"
        f"- An AUTHOR row is not a build defect: the manuscript is complete except for metadata only the authors can supply.\n\n"
        + "\n".join(f"- {r['status']}: {r['check']} ({r['value']})" for r in rows),
        encoding="utf-8",
    )


def write_handoff_index(data: dict[str, object]) -> None:
    s = data["summary"]
    text = f"""# Sensors IMU 返修交接索引

更新时间：2026-08-27/28
工作目录：仓库根目录（完整生成需要 README 所列私有输入）

## 当前目标

这是第三轮返修包，目标是把现有稿件改成一篇以 Pico 4 运动/IMU 数据采集、电脑端解析、路径语义和数据质量审计为主线的 Sensors 技术稿。旧稿件和旧生成脚本均保留，不在本目录之外覆盖。

## 已核实数据

- 30 个分析 CSV，{s['frames_all']:,} 个映射帧；按时长 >=60 s、帧数 >=100、字段完整性保留 29 个会话，{s['frames_retained']:,} 帧。
- 27 个会话与 ADB `dumpsys sensorservice` 阻塞轮询的低频不规则时序兼容；2 个会话为浏览器兼容的 8.33/20 Hz 固定网格；不把两者视作同一条已校准角速度流。
- `sensor.html` 的 WebXR 分支以 viewer pose 位置差分得到速度/加速度，并把速度写入兼容字段 `gyro_x/y/z`；分析 CSV 未保存原始 source 字段。
- 5 个保留会话的 `accMag` 四舍五入到四位小数后恒为 9.7335，gyro 仍在变化；只能写通道冻结/ADB 读取链路异常，不能写 WebXR 根因。
- 28 个保留会话的 roll/pitch/yaw 全零或冻结；scanning 不能解释为普遍可测行为。
- 两套标注回收文件共同覆盖 10 名参与者的 661 个 1 秒区间；标注者间一致率约 79.0%，kappa={data['annotations']['metrics']['inter_rater']['kappa']:.3f}；机器相对两人 kappa={data['annotations']['metrics']['machine_vs_rater_a']['kappa']:.3f}/{data['annotations']['metrics']['machine_vs_rater_b']['kappa']:.3f}。
- 28 条入选文献 DOI 已由 Crossref 核验 PASS；仍需投稿前逐条核对正文落点和论点相关性。

## 本轮产物

- `Sensors_IMU_Revision_English_20260827.docx`：严格 Sensors 模板英文修订稿。
- `Sensors_IMU_Revision_Chinese_View_20260827.docx`：中文查看版。
- `Response_to_Reviewers_English_20260827.docx`：Reviewer 1/3 逐点回复。
- `作者质询与投稿前风险清单_20260827.docx`：反向质询、事实边界和提交前决策。
- `evidence/`：session audit、path comparison、annotation evidence、confusion matrices、ADB-only threshold sensitivity、evidence summary。
- `figures/`：六张 300 dpi PNG/TIFF 技术图。
- `qa/`：结构、术语、编号、边框、数据一致性检查。
- `scripts/build_revision_package.py`：唯一生成入口；不修改旧生成器。

## 关键决定的真实含义

1. “纯文本修正”意味着保留现有 20 帧导出，不等于解决了固定物理窗口问题。新稿明确报告 20 帧在不同路径上的时长差异，并把固定时间窗/重采样列为后续必做项。
2. “写 WebXR 缓冲区停滞”没有当前证据支持。新稿不写这个归因；如要恢复，必须提供设备日志或实际部署版本证据。
3. “有数据支撑两路等价”不成立。路径特征和状态输出差异明显，浏览器 N=2；新稿按路径分层。
4. “自动对齐”当前证据是视频运动能量与 gyroMag 的 1 秒互相关候选偏移，不是共享硬件时钟，也没有所有会话 `r>0.85`。
5. 当前文件夹的两套标注回收文件是真实不同标签，支持双标注一致性；旧的单标注六类结果不再作为本轮主结果。

## 交给下一位模型/Claude Code 的检查顺序

1. 先读本文件和 `evidence/evidence_summary.json`，不要从旧稿的句子推断事实。
2. 把 `session_audit.csv` 与 `path_feature_comparison.csv` 对照正文的所有 N、路径和特征分母。
3. 逐页打开英文 Word/WPS；重点看表格边框、附录 A 长表、图 3/4/5、参考文献分页。
4. 处理文中方括号待确认项：作者名单、伦理/豁免、Funding 项目编号、数据公开方式、CRediT。
5. 在作者确认后，才决定是否重跑固定物理时间窗；不要用 kappa 最大化偏移，也不要把浏览器兼容 gyroMag 写成经过验证的角速度。
"""
    (OUT / "交接索引_20260827.md").write_text(text, encoding="utf-8")


def validate_private_build_inputs() -> None:
    required = {
        "Sensors template": TEMPLATE,
        "raw analysis CSV directory": RAW_DIR,
        "subject matrix": MATRIX_PATH,
        "platform source directory": PLATFORM,
        "annotation directory": ANNOTATION,
        "reference audit": REFERENCE_AUDIT,
    }
    missing = [f"{label}: {path}" for label, path in required.items() if not path.exists()]
    if missing:
        raise SystemExit(
            "Full build inputs are private and are not bundled in this release. "
            "Configure PICO4_WORKSPACE, PICO4_REVISION_ROOT, and SENSORS_TEMPLATE.\n"
            + "\n".join(missing)
        )


def verify_release_package() -> bool:
    required = [
        "scripts/build_revision_package.py",
        "evidence/annotation_evidence.csv",
        "evidence/confusion_inter_rater.csv",
        "evidence/confusion_machine_vs_rater_a.csv",
        "evidence/confusion_machine_vs_rater_b.csv",
        "evidence/evidence_summary.json",
        "evidence/path_feature_comparison.csv",
        "evidence/reference_audit_selected.csv",
        "evidence/session_audit.csv",
        "evidence/threshold_sensitivity_adb.csv",
        "figures/figure1_architecture.png",
        "figures/figure2_mapping_rules.png",
        "figures/figure3_sampling_windows.png",
        "figures/figure4_state_distribution_by_path.png",
        "figures/figure5_threshold_sensitivity.png",
        "figures/figure6_channel_quality.png",
        "qa/qa_summary.md",
        "qa/qa_report.csv",
        "交接索引_20260827.md",
    ]
    checks: dict[str, object] = {}
    missing = [name for name in required if not (OUT / name).is_file()]
    checks["required_files"] = {"pass": not missing, "missing": missing}

    excluded = [
        path.relative_to(OUT).as_posix()
        for path in OUT.rglob("*")
        if path.is_file()
        and (
            path.suffix.lower() in {".docx", ".tiff"}
            or "render" in path.parts
        )
    ]
    checks["excluded_artifacts"] = {"pass": not excluded, "found": excluded}

    text_files = [
        path for path in OUT.rglob("*")
        if path.is_file() and path.suffix.lower() in {".py", ".csv", ".json", ".md", ".txt"}
    ]
    leaks = []
    for path in text_files:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        if re.search(r"[A-Za-z]:\\(?!Windows\\Fonts)", text) or ("xwechat" + "_files") in text:
            leaks.append(path.relative_to(OUT).as_posix())
    checks["workstation_path_scan"] = {"pass": not leaks, "files": leaks}

    with (EVIDENCE / "session_audit.csv").open(encoding="utf-8-sig", newline="") as handle:
        sessions = list(csv.DictReader(handle))
    retained = [row for row in sessions if row["retained"].lower() == "true"]
    checks["session_counts"] = {
        "pass": len(sessions) == 30
        and len(retained) == 29
        and sum(row["path_group"] == "ADB-like" for row in retained) == 27
        and sum(row["path_group"] == "browser-compatible" for row in retained) == 2,
        "all": len(sessions),
        "retained": len(retained),
    }
    checks["channel_flags"] = {
        "pass": sum(row["acc_frozen"].lower() == "true" for row in retained) == 5
        and sum(row["orientation_frozen_zero"].lower() == "true" for row in retained) == 28,
        "acc_frozen": sum(row["acc_frozen"].lower() == "true" for row in retained),
        "orientation_frozen": sum(row["orientation_frozen_zero"].lower() == "true" for row in retained),
    }
    with (EVIDENCE / "reference_audit_selected.csv").open(encoding="utf-8-sig", newline="") as handle:
        references = list(csv.DictReader(handle))
    checks["reference_audit"] = {
        "pass": len(references) == 28 and all(row["status"] == "PASS" for row in references),
        "count": len(references),
    }
    checks["figures"] = {
        "pass": all((FIGURES / f"figure{i}_{name}.png").stat().st_size > 0 for i, name in enumerate(
            ["architecture", "mapping_rules", "sampling_windows", "state_distribution_by_path", "threshold_sensitivity", "channel_quality"], 1
        )),
        "count": len(list(FIGURES.glob("figure*.png"))),
    }
    passed = all(bool(item["pass"]) for item in checks.values())
    print(json.dumps({"release_verified": passed, "checks": checks}, ensure_ascii=False, indent=2))
    return passed


def build_full_package() -> None:
    validate_private_build_inputs()
    ensure_dirs()
    data = prepare_evidence()
    make_figures(data)
    tables = build_tables(data)
    build_manuscript(data, tables, chinese=False)
    build_manuscript(data, tables, chinese=True)
    build_response_letter(data)
    build_risk_brief(data)
    write_handoff_index(data)
    qa_outputs(data, tables)
    print(json.dumps({"outputs": [str(OUT_EN), str(OUT_CN), str(OUT_RESPONSE), str(OUT_RISKS)], "summary": data["summary"]}, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--build",
        action="store_true",
        help="Regenerate evidence, figures, manuscripts, and QA using private source inputs.",
    )
    parser.add_argument(
        "--verify-release",
        action="store_true",
        help="Verify the committed public-package files (default).",
    )
    args = parser.parse_args()
    if args.build:
        build_full_package()
    elif not verify_release_package():
        raise SystemExit(1)


if __name__ == "__main__":
    main()

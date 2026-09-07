#!/usr/bin/env python3
"""Rebuild the reviewer 1-4 revision evidence from raw exports and annotations.

The analysis intentionally reads only timestamp, accMag, gyroMag, roll, pitch,
and yaw from the exported CSV files. Stored behavior/confidence values are not
used for any revised result.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import re
import statistics
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Iterable, Sequence


GRAVITY = 9.80665
WINDOWS_S = (0.5, 1.0, 2.0, 4.0)
PRIMARY_WINDOW_S = 2.0
THRESHOLD_PERTURBATIONS = (-0.30, -0.20, -0.10, 0.0, 0.10, 0.20, 0.30)
RULE_ORDER = (
    "rapid_turn_rule",
    "smooth_turn_rule",
    "moderate_turn_rule",
    "acceleration_excursion_rule",
    "low_motion_rule",
)
ALL_RULE_OUTPUTS = RULE_ORDER + ("residual_rule_output",)
COARSE_OUTPUTS = ("low_head_motion", "ordinary_head_motion", "rapid_head_motion")
RESIDUAL_REASON_ORDER = (
    "euler_unavailable_gyro_below_0.15",
    "euler_unavailable_gyro_0.15_to_0.30",
    "euler_available_low_motion_range_not_met",
    "euler_available_smooth_conditions_not_met_below_moderate",
    "other",
)
FIELDS = ("timestamp", "accMag", "gyroMag", "roll", "pitch", "yaw")

# Mapping reconstructed from export epochs and the dated PDF/HTML report files.
# S012 has a report but no CSV. The two later exports map to S013 and S014.
EXPORT_TO_SESSION = {
    "1776754772978": "S002",
    "1776821554249": "S001",
    "1776824662730": "S005",
    "1776825800472": "S006",
    "1776827240332": "S007",
    "1776828552202": "S008",
    "1776830107430": "S009",
    "1776842825545": "S010",
    "1776844051112": "S011",
    "1776846533989": "S013",
    "1776847632327": "S014",
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

EXCLUDED = {
    "S002": "CSV export incomplete (8.410 s)",
    "S003": "No analysis CSV export retained",
    "S004": "No analysis CSV export retained",
    "S012": "Dated PDF report retained, but no corresponding analysis CSV",
    "S016": "No analysis CSV export retained",
}

# The consent forms are held privately and are intentionally excluded from the
# replication package. This count comes from the author-provided consent
# inventory; the evidence rebuild can reconcile identifiers but cannot inspect
# or publish participant identities.
AUTHOR_REPORTED_SIGNED_CONSENT_RECORDS = 34
CONSENT_EVIDENCE_BASIS = (
    "Author-provided private consent inventory; source forms are not included in the replication package"
)

THRESHOLDS = {
    "low_gyro_max": 0.15,
    "low_euler_delta_max": 2.0,
    "smooth_gyro_min": 0.15,
    "smooth_gyro_max": 1.5,
    "smooth_gyro_std_max": 0.6,
    "smooth_euler_delta_min": 3.0,
    "rapid_gyro_min": 1.5,
    "rapid_gyro_std_min": 0.8,
    "moderate_gyro_min": 0.3,
    "moderate_gyro_max": 1.5,
    "acc_excursion_min": 0.3,
}


@dataclass
class SessionData:
    session_id: str
    export_id: str
    source_file: Path
    timestamp: list[float]
    acc_mag: list[float]
    gyro_mag: list[float]
    roll: list[float]
    pitch: list[float]
    yaw: list[float]

    @property
    def n(self) -> int:
        return len(self.timestamp)


def fmt(value, digits: int = 6):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        if math.isnan(value):
            return ""
        return f"{value:.{digits}f}".rstrip("0").rstrip(".")
    return value


def write_csv(path: Path, rows: Sequence[dict], fieldnames: Sequence[str] | None = None):
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        fieldnames = list(rows[0].keys()) if rows else []
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: fmt(row.get(k)) for k in fieldnames})


def read_export(path: Path, session_id: str) -> SessionData:
    cols = {name: [] for name in FIELDS}
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        missing = set(FIELDS) - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{path.name}: missing columns {sorted(missing)}")
        for row in reader:
            # Deliberately do not access row['behavior'] or row['confidence'].
            for name in FIELDS:
                try:
                    value = float(row[name])
                except (TypeError, ValueError) as exc:
                    raise ValueError(
                        f"{path.name}: non-numeric or missing value in {name}"
                    ) from exc
                if not math.isfinite(value):
                    raise ValueError(f"{path.name}: non-finite value in {name}")
                cols[name].append(value)
    export_id = re.search(r"(\d+)", path.stem).group(1)
    return SessionData(
        session_id=session_id,
        export_id=export_id,
        source_file=path,
        timestamp=cols["timestamp"],
        acc_mag=cols["accMag"],
        gyro_mag=cols["gyroMag"],
        roll=cols["roll"],
        pitch=cols["pitch"],
        yaw=cols["yaw"],
    )


def percentile(values: Sequence[float], p: float) -> float:
    vals = sorted(values)
    if not vals:
        return math.nan
    if len(vals) == 1:
        return vals[0]
    pos = (len(vals) - 1) * p
    lo, hi = math.floor(pos), math.ceil(pos)
    if lo == hi:
        return vals[lo]
    return vals[lo] * (hi - pos) + vals[hi] * (pos - lo)


def median_iqr(values: Sequence[float]) -> tuple[float, float, float]:
    vals = [v for v in values if not math.isnan(v)]
    if not vals:
        return math.nan, math.nan, math.nan
    return statistics.median(vals), percentile(vals, 0.25), percentile(vals, 0.75)


def cluster_bootstrap_median_ci(
    values: Sequence[float], iterations: int = 5000, seed: int = 4505577
) -> tuple[float, float]:
    vals = [v for v in values if not math.isnan(v)]
    if not vals:
        return math.nan, math.nan
    rng = random.Random(seed + len(vals))
    estimates = [statistics.median(rng.choices(vals, k=len(vals))) for _ in range(iterations)]
    return percentile(estimates, 0.025), percentile(estimates, 0.975)


def pop_std(values: Sequence[float]) -> float:
    if not values:
        return math.nan
    mean = sum(values) / len(values)
    return math.sqrt(sum((v - mean) ** 2 for v in values) / len(values))


def channel_frozen(values: Sequence[float], tolerance: float = 1e-6) -> bool:
    return bool(values) and max(values) - min(values) <= tolerance


def classify_path(median_dt: float) -> tuple[str, str]:
    if median_dt <= 0.12 + 1e-9:
        return (
            "browser-compatible",
            "Export timing is compatible with the higher-rate browser examples in the archived architecture; source was not retained.",
        )
    return (
        "ADB-like",
        "Export timing is compatible with blocking Android sensorservice polling in the archived architecture; source was not retained.",
    )


def qc_row(data: SessionData) -> dict:
    dt_all = [b - a for a, b in zip(data.timestamp, data.timestamp[1:])]
    dt_pos = [d for d in dt_all if d > 0]
    median_dt = statistics.median(dt_pos) if dt_pos else math.nan
    mean_dt = statistics.mean(dt_pos) if dt_pos else math.nan
    dt_cv = pop_std(dt_pos) / mean_dt if dt_pos and mean_dt else math.nan
    gap_threshold = max(1.0, 5.0 * median_dt) if dt_pos else math.nan
    gaps = [d for d in dt_pos if d > gap_threshold]
    acc_frozen = channel_frozen(data.acc_mag)
    gyro_frozen = channel_frozen(data.gyro_mag)
    euler_ranges = [max(v) - min(v) for v in (data.roll, data.pitch, data.yaw)]
    euler_frozen = all(r <= 1e-6 for r in euler_ranges)
    euler_zero = euler_frozen and all(abs(v[0]) <= 1e-6 for v in (data.roll, data.pitch, data.yaw))
    exported_channels = (data.acc_mag, data.gyro_mag, data.roll, data.pitch, data.yaw)
    repeated_value_pairs = sum(
        all(channel[i] == channel[i - 1] for channel in exported_channels)
        for i in range(1, data.n)
    )
    path_group, path_note = classify_path(median_dt)
    duration = data.timestamp[-1] - data.timestamp[0] if data.n else 0.0
    observed_span = sum(d for d in dt_pos if d <= gap_threshold) if dt_pos else 0.0
    return {
        "session_id": data.session_id,
        "export_id": data.export_id,
        "included": data.session_id not in EXCLUDED,
        "row_count": data.n,
        "first_timestamp_s": data.timestamp[0] if data.n else math.nan,
        "last_timestamp_s": data.timestamp[-1] if data.n else math.nan,
        "duration_s": duration,
        "median_dt_s": median_dt,
        "median_export_rate_hz": 1.0 / median_dt if median_dt else math.nan,
        "dt_iqr_s": percentile(dt_pos, 0.75) - percentile(dt_pos, 0.25) if dt_pos else math.nan,
        "dt_cv": dt_cv,
        "duplicate_timestamp_count": sum(d == 0 for d in dt_all),
        "nonmonotonic_timestamp_count": sum(d < 0 for d in dt_all),
        "consecutive_identical_export_value_pair_count": repeated_value_pairs,
        "consecutive_identical_export_value_pair_fraction": (
            repeated_value_pairs / (data.n - 1) if data.n > 1 else math.nan
        ),
        "long_gap_threshold_s": gap_threshold,
        "long_gap_count": len(gaps),
        "maximum_gap_s": max(dt_pos) if dt_pos else math.nan,
        "gap_excluded_span_s": max(0.0, duration - observed_span),
        "path_group": path_group,
        "path_assignment_note": path_note,
        "acc_range": max(data.acc_mag) - min(data.acc_mag),
        "acc_unique_4dp": len({round(v, 4) for v in data.acc_mag}),
        "acc_frozen": acc_frozen,
        "acc_frozen_value": data.acc_mag[0] if acc_frozen else None,
        "acc_usable_for_excursion_rule": not acc_frozen,
        "gyro_range": max(data.gyro_mag) - min(data.gyro_mag),
        "gyro_unique_4dp": len({round(v, 4) for v in data.gyro_mag}),
        "gyro_frozen": gyro_frozen,
        "gyro_usable": not gyro_frozen,
        "roll_range_deg": euler_ranges[0],
        "pitch_range_deg": euler_ranges[1],
        "yaw_range_deg": euler_ranges[2],
        "euler_frozen": euler_frozen,
        "euler_frozen_zero": euler_zero,
        "euler_usable_for_window_rules": not euler_frozen,
        "source_file": data.source_file.name,
    }


def scaled_thresholds(scale: float = 1.0) -> dict[str, float]:
    return {key: value * scale for key, value in THRESHOLDS.items()}


def circular_range_deg(values: Sequence[float]) -> float:
    """Return the shortest circular arc containing the supplied angles."""
    if len(values) < 2:
        return 0.0
    ordered = sorted(value % 360.0 for value in values)
    gaps = [b - a for a, b in zip(ordered, ordered[1:])]
    gaps.append(ordered[0] + 360.0 - ordered[-1])
    return 360.0 - max(gaps)


def window_bounds(timestamp: Sequence[float], window_s: float, gap_threshold: float) -> tuple[list[int], list[int], list[bool]]:
    """Return inclusive trailing windows, resetting after a long gap."""
    starts: list[int] = []
    segments: list[int] = []
    reset_flags: list[bool] = []
    left = 0
    segment_start = 0
    segment_id = 0
    for i, t in enumerate(timestamp):
        reset = i > 0 and timestamp[i] - timestamp[i - 1] > gap_threshold
        if reset:
            segment_id += 1
            segment_start = i
            left = i
        while left < i and (left < segment_start or timestamp[left] < t - window_s):
            left += 1
        starts.append(left)
        segments.append(segment_id)
        reset_flags.append(reset)
    return starts, segments, reset_flags


def _conditions(
    acc_excursion: float,
    gyro: float,
    gyro_std: float,
    euler_delta: float,
    acc_usable: bool,
    euler_usable: bool,
    threshold: dict[str, float],
) -> dict[str, bool]:
    return {
        "rapid_turn_rule": gyro > threshold["rapid_gyro_min"] or gyro_std > threshold["rapid_gyro_std_min"],
        "smooth_turn_rule": (
            euler_usable
            and threshold["smooth_gyro_min"] <= gyro <= threshold["smooth_gyro_max"]
            and gyro_std <= threshold["smooth_gyro_std_max"]
            and euler_delta >= threshold["smooth_euler_delta_min"]
        ),
        "moderate_turn_rule": threshold["moderate_gyro_min"] <= gyro <= threshold["moderate_gyro_max"],
        "acceleration_excursion_rule": acc_usable and acc_excursion > threshold["acc_excursion_min"],
        "low_motion_rule": (
            euler_usable
            and gyro < threshold["low_gyro_max"]
            and euler_delta < threshold["low_euler_delta_max"]
        ),
    }


def classify_session(
    data: SessionData,
    qc: dict,
    window_s: float | None,
    threshold_scale: float = 1.0,
    priority: Sequence[str] = RULE_ORDER,
    legacy_21_samples: bool = False,
    threshold_overrides: dict[str, float] | None = None,
    circular_euler: bool = False,
) -> list[dict]:
    threshold = scaled_thresholds(threshold_scale)
    if threshold_overrides:
        threshold.update(threshold_overrides)
    if legacy_21_samples:
        starts = [max(0, i - 20) for i in range(data.n)]
        segments = [0] * data.n
        reset_flags = [False] * data.n
    elif window_s is None:
        starts = list(range(data.n))
        segments = [0] * data.n
        reset_flags = [False] * data.n
    else:
        starts, segments, reset_flags = window_bounds(
            data.timestamp, window_s, float(qc["long_gap_threshold_s"])
        )

    out = []
    for i, start in enumerate(starts):
        gyro_window = data.gyro_mag[start : i + 1]
        gyro_std = pop_std(gyro_window)
        if qc["euler_usable_for_window_rules"]:
            window_angles = (
                data.roll[start : i + 1],
                data.pitch[start : i + 1],
                data.yaw[start : i + 1],
            )
            if circular_euler:
                euler_delta = max(circular_range_deg(values) for values in window_angles)
            else:
                euler_delta = max(max(values) - min(values) for values in window_angles)
        else:
            euler_delta = math.nan
        acc_excursion = abs(data.acc_mag[i] - GRAVITY)
        cond = _conditions(
            acc_excursion,
            data.gyro_mag[i],
            gyro_std,
            euler_delta,
            bool(qc["acc_usable_for_excursion_rule"]),
            bool(qc["euler_usable_for_window_rules"]),
            threshold,
        )
        label = next((name for name in priority if cond[name]), "residual_rule_output")
        # Primary observable taxonomy uses only exported gyro magnitude.
        if cond["rapid_turn_rule"]:
            coarse = "rapid_head_motion"
        elif data.gyro_mag[i] >= threshold["low_gyro_max"]:
            coarse = "ordinary_head_motion"
        else:
            coarse = "low_head_motion"
        out.append(
            {
                "session_id": data.session_id,
                "export_id": data.export_id,
                "sample_index": i,
                "timestamp_s": data.timestamp[i],
                "path_group": qc["path_group"],
                "window_definition": "legacy_21_samples" if legacy_21_samples else ("no_window" if window_s is None else f"trailing_{window_s:g}s"),
                "window_start_index": start,
                "window_sample_count": i - start + 1,
                "segment_id": segments[i],
                "gap_reset": reset_flags[i],
                "acc_channel_usable": qc["acc_usable_for_excursion_rule"],
                "euler_channel_usable": qc["euler_usable_for_window_rules"],
                "acc_excursion_m_s2": acc_excursion,
                "gyro_magnitude_exported": data.gyro_mag[i],
                "window_gyro_std": gyro_std,
                "window_euler_delta_deg": euler_delta,
                "euler_range_method": "circular" if circular_euler else "arithmetic_max_minus_min",
                "condition_count": sum(cond.values()),
                "matched_conditions": "|".join(k for k, v in cond.items() if v),
                "rule_output": label,
                "coarse_head_motion_output": coarse,
            }
        )
    return out


def output_change(reference: Sequence[dict], candidate: Sequence[dict], key: str = "rule_output") -> float:
    if len(reference) != len(candidate):
        raise ValueError("Output lengths differ")
    if not reference:
        return math.nan
    return sum(a[key] != b[key] for a, b in zip(reference, candidate)) / len(reference)


def participant_flow(raw_root: Path, report_root: Path) -> list[dict]:
    export_for_session = {session: export for export, session in EXPORT_TO_SESSION.items()}
    report_files = list(report_root.glob("IMU_S*_行为分析报告_*"))
    rows = []
    for number in range(1, 35):
        sid = f"S{number:03d}"
        export_id = export_for_session.get(sid, "")
        reports = sorted(p.name for p in report_files if re.search(rf"IMU_{sid}_", p.name))
        included = sid not in EXCLUDED
        rows.append(
            {
                "session_id": sid,
                "consent_recorded": True,
                "consent_evidence_basis": CONSENT_EVIDENCE_BASIS,
                "analysis_csv_available": bool(export_id),
                "export_id": export_id,
                "dated_report_available": bool(reports),
                "report_file_count": len(reports),
                "included_in_session_analysis": included,
                "exclusion_reason": EXCLUDED.get(sid, ""),
                "mapping_evidence": (
                    "Export epoch matched to dated report time; S013/S014 correction applied"
                    if export_id
                    else "No corresponding analysis CSV export"
                ),
                "report_files": "|".join(reports),
            }
        )
    return rows


def software_version_audit(platform_root: Path) -> list[dict]:
    """Separate archived-package versions from unrecorded acquisition versions."""

    project_config = platform_root / "project.config.json"
    project_version = "not available"
    if project_config.exists():
        project_version = str(json.loads(project_config.read_text(encoding="utf-8-sig")).get("version", "not available"))

    embedded_python = platform_root / "runtime" / "python-embed" / "python.exe"
    python_version = "not available"
    websockets_version = "not available"
    if embedded_python.exists():
        try:
            python_version = subprocess.run(
                [str(embedded_python), "--version"],
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            ).stdout.strip().removeprefix("Python ")
            websockets_version = subprocess.run(
                [str(embedded_python), "-c", "import websockets; print(websockets.__version__)"],
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            ).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            pass

    return [
        {
            "scope": "acquisition",
            "component": "Headset model",
            "value": "Pico 4 Pro",
            "status": "AUTHOR_CONFIRMED",
            "evidence": "Author confirmation; retain a non-identifying device record before submission",
        },
        {
            "scope": "acquisition",
            "component": "PICO OS build",
            "value": "not retained",
            "status": "NOT_RETAINED",
            "evidence": "No contemporaneous screenshot, device log, or build record in archive",
        },
        {
            "scope": "acquisition",
            "component": "ADB client/platform-tools version",
            "value": "not retained",
            "status": "NOT_RETAINED",
            "evidence": "No contemporaneous adb version output or installation record in archive",
        },
        {
            "scope": "acquisition",
            "component": "Browser engine and WebXR runtime",
            "value": "not retained",
            "status": "NOT_RETAINED",
            "evidence": "No contemporaneous About page, User-Agent, or remote-debug record in archive",
        },
        {
            "scope": "archived revision package",
            "component": "Platform code",
            "value": project_version,
            "status": "VERIFIED_FROM_ARCHIVE" if project_version != "not available" else "NOT_AVAILABLE",
            "evidence": "platform/project.config.json",
        },
        {
            "scope": "archived revision package",
            "component": "Embedded Python",
            "value": python_version,
            "status": "VERIFIED_FROM_ARCHIVE" if python_version != "not available" else "NOT_AVAILABLE",
            "evidence": "platform/runtime/python-embed/python.exe --version",
        },
        {
            "scope": "archived revision package",
            "component": "Python websockets",
            "value": websockets_version,
            "status": "VERIFIED_FROM_ARCHIVE" if websockets_version != "not available" else "NOT_AVAILABLE",
            "evidence": "embedded Python import of websockets.__version__",
        },
    ]


def summarize_paths(qc_rows: Sequence[dict]) -> list[dict]:
    retained = [r for r in qc_rows if r["included"]]
    rows = []
    for group in ("all", "ADB-like", "browser-compatible"):
        selected = retained if group == "all" else [r for r in retained if r["path_group"] == group]
        for metric in (
            "duration_s",
            "median_export_rate_hz",
            "dt_cv",
            "maximum_gap_s",
            "gap_excluded_span_s",
        ):
            values = [float(r[metric]) for r in selected]
            med, q1, q3 = median_iqr(values)
            ci_low, ci_high = cluster_bootstrap_median_ci(values)
            rows.append(
                {
                    "path_group": group,
                    "n_sessions": len(selected),
                    "metric": metric,
                    "median": med,
                    "q1": q1,
                    "q3": q3,
                    "bootstrap_median_ci_low": ci_low,
                    "bootstrap_median_ci_high": ci_high,
                    "minimum": min(values) if values else math.nan,
                    "maximum": max(values) if values else math.nan,
                }
            )
        rows.append(
            {
                "path_group": group,
                "n_sessions": len(selected),
                "metric": "acc_frozen_session_fraction",
                "median": sum(bool(r["acc_frozen"]) for r in selected) / len(selected) if selected else math.nan,
                "q1": "",
                "q3": "",
                "bootstrap_median_ci_low": "",
                "bootstrap_median_ci_high": "",
                "minimum": "",
                "maximum": "",
            }
        )
    return rows


def session_rule_distribution(main_outputs: dict[str, list[dict]]) -> list[dict]:
    rows = []
    for sid, outputs in sorted(main_outputs.items()):
        counts = Counter(r["rule_output"] for r in outputs)
        coarse = Counter(r["coarse_head_motion_output"] for r in outputs)
        row = {
            "session_id": sid,
            "path_group": outputs[0]["path_group"],
            "n_samples": len(outputs),
            "conflict_sample_fraction": sum(r["condition_count"] > 1 for r in outputs) / len(outputs),
        }
        for name in ALL_RULE_OUTPUTS:
            row[f"{name}_fraction"] = counts[name] / len(outputs)
        for name in COARSE_OUTPUTS:
            row[f"{name}_fraction"] = coarse[name] / len(outputs)
        rows.append(row)
    return rows


def summarize_rule_distribution(session_rows: Sequence[dict]) -> list[dict]:
    rows = []
    for group in ("all", "ADB-like", "browser-compatible"):
        selected = list(session_rows) if group == "all" else [r for r in session_rows if r["path_group"] == group]
        total = sum(int(r["n_samples"]) for r in selected)
        for label in ALL_RULE_OUTPUTS + COARSE_OUTPUTS:
            key = f"{label}_fraction"
            values = [float(r[key]) for r in selected]
            med, q1, q3 = median_iqr(values)
            ci_low, ci_high = cluster_bootstrap_median_ci(values)
            weighted = (
                sum(float(r[key]) * int(r["n_samples"]) for r in selected) / total if total else math.nan
            )
            rows.append(
                {
                    "path_group": group,
                    "n_sessions": len(selected),
                    "output": label,
                    "session_median_fraction": med,
                    "session_q1_fraction": q1,
                    "session_q3_fraction": q3,
                    "session_minimum_fraction": min(values),
                    "session_maximum_fraction": max(values),
                    "bootstrap_session_median_ci_low": ci_low,
                    "bootstrap_session_median_ci_high": ci_high,
                    "time_sample_weighted_fraction": weighted,
                }
            )
    return rows


def residual_reason(row: dict) -> str:
    """Describe why a primary-rule row reached the residual fallback."""
    gyro = float(row["gyro_magnitude_exported"])
    euler_usable = bool(row["euler_channel_usable"])
    if not euler_usable and gyro < THRESHOLDS["low_gyro_max"]:
        return "euler_unavailable_gyro_below_0.15"
    if not euler_usable and gyro < THRESHOLDS["moderate_gyro_min"]:
        return "euler_unavailable_gyro_0.15_to_0.30"
    if euler_usable and gyro < THRESHOLDS["low_gyro_max"]:
        return "euler_available_low_motion_range_not_met"
    if euler_usable and gyro < THRESHOLDS["moderate_gyro_min"]:
        return "euler_available_smooth_conditions_not_met_below_moderate"
    return "other"


def summarize_residual_outputs(main_outputs: dict[str, list[dict]]) -> list[dict]:
    rows = []
    for group in ("all", "ADB-like", "browser-compatible"):
        selected = [
            row
            for outputs in main_outputs.values()
            for row in outputs
            if group == "all" or row["path_group"] == group
        ]
        residual = [row for row in selected if row["rule_output"] == "residual_rule_output"]
        reasons = Counter(residual_reason(row) for row in residual)
        sessions = defaultdict(set)
        for row in residual:
            sessions[residual_reason(row)].add(row["session_id"])
        for reason in RESIDUAL_REASON_ORDER:
            count = reasons[reason]
            rows.append(
                {
                    "path_group": group,
                    "reason": reason,
                    "n_sessions_with_reason": len(sessions[reason]),
                    "residual_sample_count": count,
                    "fraction_of_group_residual_samples": count / len(residual) if residual else 0.0,
                    "fraction_of_group_all_samples": count / len(selected) if selected else 0.0,
                }
            )
    return rows


def summarize_transitions(
    main_outputs: dict[str, list[dict]],
) -> tuple[list[dict], list[dict]]:
    """Summarize adjacent exported-sample outputs without crossing gap resets."""
    matrix_rows = []
    group_rows = []
    for group in ("all", "ADB-like", "browser-compatible"):
        selected = {
            sid: outputs
            for sid, outputs in main_outputs.items()
            if group == "all" or outputs[0]["path_group"] == group
        }
        counts = Counter()
        sessions_with_source = defaultdict(set)
        sessions_with_pair = defaultdict(set)
        per_session_change = []
        total_pairs = 0
        changed_pairs = 0
        for sid, outputs in selected.items():
            session_pairs = 0
            session_changes = 0
            for left, right in zip(outputs, outputs[1:]):
                if left["segment_id"] != right["segment_id"]:
                    continue
                source = left["rule_output"]
                target = right["rule_output"]
                counts[(source, target)] += 1
                sessions_with_source[source].add(sid)
                sessions_with_pair[(source, target)].add(sid)
                session_pairs += 1
                session_changes += source != target
            if session_pairs:
                per_session_change.append(session_changes / session_pairs)
                total_pairs += session_pairs
                changed_pairs += session_changes
        med, q1, q3 = median_iqr(per_session_change)
        group_rows.append(
            {
                "path_group": group,
                "n_sessions": len(selected),
                "n_adjacent_pairs": total_pairs,
                "n_changed_pairs": changed_pairs,
                "weighted_changed_pair_fraction": changed_pairs / total_pairs if total_pairs else math.nan,
                "session_median_changed_pair_fraction": med,
                "session_q1_changed_pair_fraction": q1,
                "session_q3_changed_pair_fraction": q3,
            }
        )
        for source in ALL_RULE_OUTPUTS:
            source_total = sum(counts[(source, target)] for target in ALL_RULE_OUTPUTS)
            for target in ALL_RULE_OUTPUTS:
                pair_count = counts[(source, target)]
                matrix_rows.append(
                    {
                        "path_group": group,
                        "from_output": source,
                        "to_output": target,
                        "transition_count": pair_count,
                        "from_output_pair_count": source_total,
                        "row_fraction": pair_count / source_total if source_total else 0.0,
                        "n_sessions_with_from_output": len(sessions_with_source[source]),
                        "n_sessions_with_transition": len(sessions_with_pair[(source, target)]),
                    }
                )
    return matrix_rows, group_rows


def run_ablation(
    sessions: dict[str, SessionData], qc_by_sid: dict[str, dict], main_outputs: dict[str, list[dict]]
) -> tuple[list[dict], list[dict], list[dict]]:
    configs = [
        ("no_window", None, 1.0, RULE_ORDER, False),
        ("legacy_21_samples", None, 1.0, RULE_ORDER, True),
        *[(f"time_window_{w:g}s", w, 1.0, RULE_ORDER, False) for w in WINDOWS_S],
        (
            "priority_moderate_before_smooth",
            PRIMARY_WINDOW_S,
            1.0,
            ("rapid_turn_rule", "moderate_turn_rule", "smooth_turn_rule", "acceleration_excursion_rule", "low_motion_rule"),
            False,
        ),
        (
            "priority_low_before_acceleration",
            PRIMARY_WINDOW_S,
            1.0,
            ("rapid_turn_rule", "smooth_turn_rule", "moderate_turn_rule", "low_motion_rule", "acceleration_excursion_rule"),
            False,
        ),
        (
            "circular_euler_range",
            PRIMARY_WINDOW_S,
            1.0,
            RULE_ORDER,
            False,
        ),
    ]
    ablation_rows = []
    threshold_rows = []
    for name, window_s, scale, priority, legacy in configs:
        per_session = []
        candidate_by_sid = {}
        for sid, data in sessions.items():
            candidate = classify_session(
                data,
                qc_by_sid[sid],
                window_s,
                scale,
                priority,
                legacy,
                circular_euler=name == "circular_euler_range",
            )
            candidate_by_sid[sid] = candidate
            per_session.append(output_change(main_outputs[sid], candidate))
        for group in ("all", "ADB-like", "browser-compatible"):
            sids = list(sessions) if group == "all" else [sid for sid in sessions if qc_by_sid[sid]["path_group"] == group]
            changes = [output_change(main_outputs[sid], candidate_by_sid[sid]) for sid in sids]
            med, q1, q3 = median_iqr(changes)
            n_total = sum(len(main_outputs[sid]) for sid in sids)
            n_changed = sum(
                sum(a["rule_output"] != b["rule_output"] for a, b in zip(main_outputs[sid], candidate_by_sid[sid]))
                for sid in sids
            )
            conflicts = sum(sum(r["condition_count"] > 1 for r in candidate_by_sid[sid]) for sid in sids)
            ablation_rows.append(
                {
                    "configuration": name,
                    "path_group": group,
                    "n_sessions": len(sids),
                    "n_samples": n_total,
                    "weighted_output_change_fraction_vs_2s": n_changed / n_total if n_total else math.nan,
                    "session_median_change_fraction": med,
                    "session_q1_change_fraction": q1,
                    "session_q3_change_fraction": q3,
                    "conflict_sample_fraction": conflicts / n_total if n_total else math.nan,
                }
            )

    for perturbation in THRESHOLD_PERTURBATIONS:
        scale = 1.0 + perturbation
        candidate_by_sid = {
            sid: classify_session(data, qc_by_sid[sid], PRIMARY_WINDOW_S, scale)
            for sid, data in sessions.items()
        }
        for group in ("all", "ADB-like", "browser-compatible"):
            sids = list(sessions) if group == "all" else [sid for sid in sessions if qc_by_sid[sid]["path_group"] == group]
            n_total = sum(len(main_outputs[sid]) for sid in sids)
            n_changed = sum(
                sum(a["rule_output"] != b["rule_output"] for a, b in zip(main_outputs[sid], candidate_by_sid[sid]))
                for sid in sids
            )
            counts = Counter(r["rule_output"] for sid in sids for r in candidate_by_sid[sid])
            for output in ALL_RULE_OUTPUTS:
                threshold_rows.append(
                    {
                        "threshold_perturbation_percent": round(perturbation * 100),
                        "threshold_scale": scale,
                        "path_group": group,
                        "n_sessions": len(sids),
                        "n_samples": n_total,
                        "output": output,
                        "output_fraction": counts[output] / n_total if n_total else math.nan,
                        "weighted_change_fraction_vs_nominal": n_changed / n_total if n_total else math.nan,
                    }
                )
    one_at_a_time_rows = []
    for threshold_name, nominal_value in THRESHOLDS.items():
        for perturbation in (p for p in THRESHOLD_PERTURBATIONS if p != 0.0):
            perturbed_value = nominal_value * (1.0 + perturbation)
            candidate_by_sid = {
                sid: classify_session(
                    data,
                    qc_by_sid[sid],
                    PRIMARY_WINDOW_S,
                    threshold_overrides={threshold_name: perturbed_value},
                )
                for sid, data in sessions.items()
            }
            for group in ("all", "ADB-like", "browser-compatible"):
                sids = (
                    list(sessions)
                    if group == "all"
                    else [sid for sid in sessions if qc_by_sid[sid]["path_group"] == group]
                )
                changes = [output_change(main_outputs[sid], candidate_by_sid[sid]) for sid in sids]
                med, q1, q3 = median_iqr(changes)
                n_total = sum(len(main_outputs[sid]) for sid in sids)
                n_changed = sum(
                    sum(
                        a["rule_output"] != b["rule_output"]
                        for a, b in zip(main_outputs[sid], candidate_by_sid[sid])
                    )
                    for sid in sids
                )
                one_at_a_time_rows.append(
                    {
                        "threshold_name": threshold_name,
                        "nominal_value": nominal_value,
                        "perturbation_percent": round(perturbation * 100),
                        "perturbed_value": perturbed_value,
                        "path_group": group,
                        "n_sessions": len(sids),
                        "n_samples": n_total,
                        "weighted_output_change_fraction_vs_nominal": (
                            n_changed / n_total if n_total else math.nan
                        ),
                        "session_median_change_fraction": med,
                        "session_q1_change_fraction": q1,
                        "session_q3_change_fraction": q3,
                    }
                )
    return ablation_rows, threshold_rows, one_at_a_time_rows


def summarize_euler_range_sensitivity(
    sessions: dict[str, SessionData],
    qc_by_sid: dict[str, dict],
    main_outputs: dict[str, list[dict]],
) -> list[dict]:
    """Separate angle-wrap effects on window ranges from effects on rule outputs."""
    rows = []
    for sid, data in sessions.items():
        circular = classify_session(
            data,
            qc_by_sid[sid],
            PRIMARY_WINDOW_S,
            1.0,
            RULE_ORDER,
            False,
            circular_euler=True,
        )
        arithmetic = main_outputs[sid]
        arithmetic_ranges = [float(row["window_euler_delta_deg"]) for row in arithmetic]
        circular_ranges = [float(row["window_euler_delta_deg"]) for row in circular]
        differences = [
            abs(left - right)
            if math.isfinite(left) and math.isfinite(right)
            else 0.0
            for left, right in zip(arithmetic_ranges, circular_ranges)
        ]
        changed_ranges = sum(value > 1e-9 for value in differences)
        changed_outputs = sum(
            left["rule_output"] != right["rule_output"]
            for left, right in zip(arithmetic, circular)
        )
        rows.append(
            {
                "session_id": sid,
                "path_group": qc_by_sid[sid]["path_group"],
                "n_samples": len(arithmetic),
                "euler_channel_usable": qc_by_sid[sid][
                    "euler_usable_for_window_rules"
                ],
                "range_changed_sample_count": changed_ranges,
                "range_changed_sample_fraction": changed_ranges / len(arithmetic),
                "maximum_arithmetic_range_deg": max(
                    (value for value in arithmetic_ranges if math.isfinite(value)),
                    default=math.nan,
                ),
                "maximum_circular_range_deg": max(
                    (value for value in circular_ranges if math.isfinite(value)),
                    default=math.nan,
                ),
                "maximum_range_reduction_deg": max(differences),
                "rule_output_changed_count": changed_outputs,
                "rule_output_changed_fraction": changed_outputs / len(arithmetic),
            }
        )
    return rows


def parse_annotation_subject(path: Path) -> str:
    numbers = re.findall(r"(\d+)", path.stem)
    if not numbers:
        raise ValueError(f"Cannot identify subject from {path.name}")
    return f"S{int(numbers[-1]):03d}"


def read_annotations(directory: Path, rater: str) -> list[dict]:
    rows = []
    for path in sorted(directory.glob("*.csv")):
        sid = parse_annotation_subject(path)
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                label = (row.get("human_label") or "").strip()
                if not label:
                    continue
                rows.append(
                    {
                        "session_id": sid,
                        "start_s": float(row["csv_time_start_s"]),
                        "end_s": float(row["csv_time_end_s"]),
                        "human_label": label,
                        "rater": rater,
                        "source_file": f"source_annotations/{rater}/{sid}.csv",
                    }
                )
    return rows


def mode_label(labels: Sequence[str], precedence: Sequence[str]) -> str | None:
    if not labels:
        return None
    counts = Counter(labels)
    max_count = max(counts.values())
    tied = {label for label, count in counts.items() if count == max_count}
    return next((label for label in precedence if label in tied), sorted(tied)[0])


def aggregate_machine_bin(outputs: Sequence[dict], start_s: float, end_s: float, key: str, precedence: Sequence[str]) -> str | None:
    labels = [r[key] for r in outputs if start_s <= float(r["timestamp_s"]) < end_s]
    return mode_label(labels, precedence)


def neutral_human_label(label: str) -> str:
    mapping = {
        "gaze": "low_motion_rule",
        "idle": "residual_rule_output",
        "head_turn": "moderate_turn_rule",
        "scanning": "smooth_turn_rule",
        "scan/turn": "smooth_turn_rule",
        "sudden_turn": "rapid_turn_rule",
        "postural_shift": "acceleration_excursion_rule",
    }
    return mapping.get(label, label)


def coarse_human_label(label: str) -> str:
    if label in {"gaze", "idle"}:
        return "low_head_motion"
    if label == "sudden_turn":
        return "rapid_head_motion"
    return "ordinary_head_motion"


def cohen_kappa(a: Sequence[str], b: Sequence[str]) -> float:
    if len(a) != len(b) or not a:
        return math.nan
    labels = sorted(set(a) | set(b))
    n = len(a)
    po = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[label] * cb[label] for label in labels) / (n * n)
    return (po - pe) / (1 - pe) if pe < 1 else (1.0 if po == 1 else math.nan)


def cluster_bootstrap_ci(records: Sequence[dict], left: str, right: str, iterations: int = 5000, seed: int = 4505577) -> tuple[float, float, int]:
    by_session = defaultdict(list)
    for row in records:
        by_session[row["session_id"]].append(row)
    sessions = sorted(by_session)
    rng = random.Random(seed)
    values = []
    for _ in range(iterations):
        sampled = [rng.choice(sessions) for _ in sessions]
        rows = [row for sid in sampled for row in by_session[sid]]
        value = cohen_kappa([r[left] for r in rows], [r[right] for r in rows])
        if not math.isnan(value):
            values.append(value)
    return percentile(values, 0.025), percentile(values, 0.975), len(values)


def confusion_long(records: Sequence[dict], left: str, right: str, pair: str, taxonomy: str) -> list[dict]:
    labels = sorted({r[left] for r in records} | {r[right] for r in records})
    counts = Counter((r[left], r[right]) for r in records)
    return [
        {
            "pair": pair,
            "taxonomy": taxonomy,
            "reference_label": ref,
            "comparison_label": comp,
            "count": counts[(ref, comp)],
        }
        for ref in labels
        for comp in labels
    ]


def annotation_analysis(main_outputs: dict[str, list[dict]], ann_root: Path) -> tuple[list[dict], list[dict], list[dict]]:
    a_rows = read_annotations(ann_root / "盲标回收_20260727", "A")
    b_rows = read_annotations(ann_root / "标注员2回收_20260728", "B")
    a_key = {(r["session_id"], r["start_s"], r["end_s"]): r for r in a_rows}
    b_key = {(r["session_id"], r["start_s"], r["end_s"]): r for r in b_rows}
    common = sorted(set(a_key) & set(b_key))
    if len(common) != 661:
        raise AssertionError(f"Expected 661 common annotation bins, found {len(common)}")
    detailed = []
    for key in common:
        sid, start_s, end_s = key
        machine_coarse = aggregate_machine_bin(
            main_outputs[sid], start_s, end_s, "coarse_head_motion_output", COARSE_OUTPUTS[::-1]
        )
        machine_six = aggregate_machine_bin(
            main_outputs[sid], start_s, end_s, "rule_output", ALL_RULE_OUTPUTS
        )
        if machine_coarse is None or machine_six is None:
            continue
        detailed.append(
            {
                "session_id": sid,
                "start_s": start_s,
                "end_s": end_s,
                "rater_a_original": a_key[key]["human_label"],
                "rater_b_original": b_key[key]["human_label"],
                "rater_a_coarse": coarse_human_label(a_key[key]["human_label"]),
                "rater_b_coarse": coarse_human_label(b_key[key]["human_label"]),
                "machine_coarse": machine_coarse,
                "rater_a_neutral_six": neutral_human_label(a_key[key]["human_label"]),
                "rater_b_neutral_six": neutral_human_label(b_key[key]["human_label"]),
                "machine_neutral_six": machine_six,
            }
        )

    comparisons = [
        ("inter-rater A vs B", "coarse_3", "rater_a_coarse", "rater_b_coarse"),
        ("rule output vs rater A", "coarse_3", "rater_a_coarse", "machine_coarse"),
        ("rule output vs rater B", "coarse_3", "rater_b_coarse", "machine_coarse"),
        ("inter-rater A vs B", "neutral_6", "rater_a_neutral_six", "rater_b_neutral_six"),
        ("rule output vs rater A", "neutral_6", "rater_a_neutral_six", "machine_neutral_six"),
        ("rule output vs rater B", "neutral_6", "rater_b_neutral_six", "machine_neutral_six"),
    ]
    summaries = []
    confusion = []
    for pair, taxonomy, left, right in comparisons:
        left_values = [r[left] for r in detailed]
        right_values = [r[right] for r in detailed]
        kappa = cohen_kappa(left_values, right_values)
        ci_low, ci_high, valid_boot = cluster_bootstrap_ci(detailed, left, right)
        summaries.append(
            {
                "pair": pair,
                "taxonomy": taxonomy,
                "n_bins": len(detailed),
                "n_sessions": len({r["session_id"] for r in detailed}),
                "percent_agreement": 100 * sum(a == b for a, b in zip(left_values, right_values)) / len(detailed),
                "cohen_kappa": kappa,
                "cluster_bootstrap_ci_low": ci_low,
                "cluster_bootstrap_ci_high": ci_high,
                "bootstrap_iterations_requested": 5000,
                "bootstrap_valid_iterations": valid_boot,
                "bootstrap_cluster": "session",
            }
        )
        confusion.extend(confusion_long(detailed, left, right, pair, taxonomy))
    return summaries, confusion, detailed


def annotation_sensitivity(
    main_outputs: dict[str, list[dict]], records: Sequence[dict]
) -> list[dict]:
    """Check whether coarse agreement is driven by one session or S021's manual offset."""

    comparisons = (
        ("rule output vs rater A", "rater_a_coarse"),
        ("rule output vs rater B", "rater_b_coarse"),
    )
    rows = []

    def append_scenario(
        scenario: str,
        selected: Sequence[dict],
        *,
        omitted_session: str = "",
        s021_time_shift_s: float = 0.0,
        missing_machine_bins: int = 0,
    ) -> None:
        for pair, human_key in comparisons:
            human = [row[human_key] for row in selected]
            machine = [row["machine_coarse"] for row in selected]
            rows.append(
                {
                    "scenario": scenario,
                    "comparison": pair,
                    "omitted_session": omitted_session,
                    "s021_time_shift_s": s021_time_shift_s,
                    "n_bins": len(selected),
                    "n_sessions": len({row["session_id"] for row in selected}),
                    "missing_machine_bins": missing_machine_bins,
                    "percent_agreement": 100
                    * sum(a == b for a, b in zip(human, machine))
                    / len(selected),
                    "cohen_kappa": cohen_kappa(human, machine),
                }
            )

    append_scenario("primary_manual_offsets", records)
    for sid in sorted({row["session_id"] for row in records}):
        append_scenario(
            "leave_one_session_out",
            [row for row in records if row["session_id"] != sid],
            omitted_session=sid,
        )

    # Archived annotations use 68 s for S021, 3 s later than the automatic
    # 65 s candidate. Shift only the machine lookup back by 3 s to quantify
    # the effect of using the unadjusted automatic offset.
    automatic_offset_rows = []
    missing_machine_bins = 0
    for row in records:
        shifted = dict(row)
        if row["session_id"] == "S021":
            shifted["machine_coarse"] = aggregate_machine_bin(
                main_outputs["S021"],
                float(row["start_s"]) - 3.0,
                float(row["end_s"]) - 3.0,
                "coarse_head_motion_output",
                COARSE_OUTPUTS[::-1],
            )
        if shifted["machine_coarse"] is None:
            missing_machine_bins += 1
            continue
        automatic_offset_rows.append(shifted)
    append_scenario(
        "s021_automatic_offset",
        automatic_offset_rows,
        s021_time_shift_s=-3.0,
        missing_machine_bins=missing_machine_bins,
    )
    return rows


def annotation_prevalence(records: Sequence[dict]) -> list[dict]:
    rows = []
    sources = (
        ("annotator A", "rater_a_coarse"),
        ("annotator B", "rater_b_coarse"),
        ("coarse rule output", "machine_coarse"),
    )
    total = len(records)
    for source, field in sources:
        counts = Counter(r[field] for r in records)
        for label in COARSE_OUTPUTS:
            count = counts[label]
            rows.append(
                {
                    "taxonomy": "coarse_3",
                    "source": source,
                    "label": label,
                    "count": count,
                    "total_bins": total,
                    "fraction": count / total,
                }
            )
    return rows


def annotation_alignment_audit(ann_root: Path, annotation_detail: Sequence[dict]) -> list[dict]:
    used = sorted({r["session_id"] for r in annotation_detail})
    selected_start = {
        sid: min(float(r["start_s"]) for r in annotation_detail if r["session_id"] == sid)
        for sid in used
    }
    auto_by_sid = {}
    with (ann_root / "auto_alignment.csv").open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            auto_by_sid[f"S{int(row['subject']):03d}"] = row
    rows = []
    for sid in used:
        auto = auto_by_sid[sid]
        chosen = selected_start[sid]
        automatic = float(auto["offset_s"])
        rows.append(
            {
                "session_id": sid,
                "used_in_agreement_analysis": True,
                "automatic_offset_s": automatic,
                "selected_annotation_start_s": chosen,
                "offset_difference_s": chosen - automatic,
                "cross_correlation_r": float(auto["r"]),
                "peak_margin": float(auto["margin"]),
                "overlap_s": float(auto["overlap_s"]),
                "automatic_confident_flag": auto["confident"],
                "interpretation": "Alignment aid only; correlation is not classification validity evidence.",
            }
        )
    return rows


def annotation_interface_audit(ann_root: Path, annotation_detail: Sequence[dict]) -> list[dict]:
    """Verify the settings visible in the archived first-pass annotation pages."""
    rows = []
    for sid in sorted({r["session_id"] for r in annotation_detail}):
        number = int(sid[1:])
        path = ann_root / "标注工具" / f"标注_受测者{number}.html"
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        review_mode_false = bool(re.search(r"const\s+REVIEW\s*=\s*false", text))
        machine_columns_conditional = "if (REVIEW)" in text and 'className = "mach"' in text
        alignment_panel_hidden = 'alignPanel").style.display = alignOK ? "none"' in text
        rows.append(
            {
                "session_id": sid,
                "interface_file_present": path.exists(),
                "review_mode": "false" if review_mode_false else "not verified",
                "machine_and_prior_label_columns_visible": not (
                    review_mode_false and machine_columns_conditional
                ),
                "alignment_panel_hidden_after_confirmation": alignment_panel_hidden,
                "interpretation": (
                    "Archived interface settings masked machine/prior-label columns during first-pass labeling; "
                    "embedded machine values remained in the page source and export schema."
                ),
            }
        )
    return rows


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def public_manifest_path(
    path: Path,
    raw_root: Path,
    report_root: Path,
    annotation_root: Path,
    platform_root: Path,
) -> str:
    path = path.resolve()
    raw_root = raw_root.resolve()
    annotation_root = annotation_root.resolve()
    platform_root = platform_root.resolve()
    if path.is_relative_to(raw_root):
        return (Path("source_exports") / path.relative_to(raw_root)).as_posix()
    if path.is_relative_to(report_root):
        return (Path("source_reports") / path.relative_to(report_root)).as_posix()
    if path.is_relative_to(annotation_root):
        relative = path.relative_to(annotation_root)
        if relative.parts and relative.parts[0] in {"盲标回收_20260727", "标注员2回收_20260728"}:
            participant_numbers = re.findall(r"\d+", path.stem)
            if not participant_numbers:
                raise ValueError(f"Cannot derive anonymous session ID for manifest entry: {path.name}")
            rater = "rater_a" if relative.parts[0] == "盲标回收_20260727" else "rater_b"
            return f"source_annotations/{rater}/S{int(participant_numbers[-1]):03d}.csv"
        annotation_names = {
            "auto_alignment.csv": "auto_alignment.csv",
            "锚点核对表.csv": "anchor_audit.csv",
        }
        return f"source_annotations/{annotation_names.get(path.name, path.name)}"
    if path.is_relative_to(platform_root):
        return (Path("platform") / path.relative_to(platform_root)).as_posix()
    if path == Path(__file__).resolve():
        return "scripts/rebuild_evidence.py"
    return f"source_files/{path.name}"


def build_manifest(
    paths: Iterable[Path],
    raw_root: Path,
    report_root: Path,
    annotation_root: Path,
    platform_root: Path,
) -> list[dict]:
    rows = []
    seen_display_paths = set()
    for path in sorted(set(p.resolve() for p in paths if p.exists())):
        display = public_manifest_path(path, raw_root, report_root, annotation_root, platform_root)
        if display in seen_display_paths:
            raise ValueError(f"Duplicate public manifest path: {display}")
        seen_display_paths.add(display)
        rows.append({"path": display, "bytes": path.stat().st_size, "sha256": sha256(path)})
    return sorted(rows, key=lambda row: row["path"])


def qa_checks(
    flow: Sequence[dict],
    qc: Sequence[dict],
    annotation: Sequence[dict],
    prevalence: Sequence[dict],
    outputs: Sequence[dict],
    transition_matrix: Sequence[dict],
    transition_groups: Sequence[dict],
    interface_audit: Sequence[dict],
    annotation_sensitivity_rows: Sequence[dict],
    software_versions: Sequence[dict],
    ablation_rows: Sequence[dict],
    threshold_one_at_a_time_rows: Sequence[dict],
    euler_range_rows: Sequence[dict],
    residual_reason_rows: Sequence[dict],
) -> list[dict]:
    retained = [r for r in qc if r["included"]]
    report_extensions = Counter()
    for row in flow:
        for name in row["report_files"].split("|") if row["report_files"] else []:
            report_extensions[Path(name).suffix.lower()] += 1
    output_groups = defaultdict(list)
    for row in outputs:
        output_groups[row["session_id"]].append(row)
    expected_adjacent_pairs = sum(
        len(rows) - len({row["segment_id"] for row in rows})
        for rows in output_groups.values()
    )
    all_transition_count = sum(
        int(row["transition_count"])
        for row in transition_matrix
        if row["path_group"] == "all"
    )
    split_transition_count = sum(
        int(row["transition_count"])
        for row in transition_matrix
        if row["path_group"] != "all"
    )
    all_residual_rows = [r for r in residual_reason_rows if r["path_group"] == "all"]
    split_residual_count = sum(
        int(r["residual_sample_count"])
        for r in residual_reason_rows
        if r["path_group"] != "all"
    )
    observed_residual_count = sum(r["rule_output"] == "residual_rule_output" for r in outputs)
    checks = [
        ("flow_has_34_unique_ids", len(flow) == 34 and len({r["session_id"] for r in flow}) == 34),
        (
            "author_reported_34_consent_records_mapped_to_ids",
            len(flow) == AUTHOR_REPORTED_SIGNED_CONSENT_RECORDS
            and all(r["consent_recorded"] for r in flow)
            and all(r["consent_evidence_basis"] == CONSENT_EVIDENCE_BASIS for r in flow),
        ),
        ("thirty_csv_exports", sum(r["analysis_csv_available"] for r in flow) == 30),
        ("twenty_nine_retained_sessions", len(retained) == 29),
        (
            "duration_completeness_gate_reconciles_s002",
            next(r for r in qc if r["session_id"] == "S002")["duration_s"] < 60
            and all(r["duration_s"] >= 60 for r in retained),
        ),
        ("correct_exclusion_set", {r["session_id"] for r in flow if not r["included_in_session_analysis"]} == set(EXCLUDED)),
        ("s012_has_report_without_csv", next(r for r in flow if r["session_id"] == "S012")["dated_report_available"] and not next(r for r in flow if r["session_id"] == "S012")["analysis_csv_available"]),
        ("s013_mapping_correct", next(r for r in flow if r["session_id"] == "S013")["export_id"] == "1776846533989"),
        ("s014_mapping_correct", next(r for r in flow if r["session_id"] == "S014")["export_id"] == "1776847632327"),
        ("report_inventory_20_html_16_pdf", report_extensions == Counter({".html": 20, ".pdf": 16})),
        ("path_split_27_2", Counter(r["path_group"] for r in retained) == Counter({"ADB-like": 27, "browser-compatible": 2})),
        ("five_acc_frozen_sessions", sum(r["acc_frozen"] for r in retained) == 5),
        ("twenty_eight_euler_frozen_sessions", sum(r["euler_frozen"] for r in retained) == 28),
        ("annotation_has_661_bins", all(int(r["n_bins"]) == 661 for r in annotation)),
        (
            "annotation_prevalence_complete",
            len(prevalence) == 9
            and all(
                abs(sum(float(r["fraction"]) for r in prevalence if r["source"] == source) - 1.0) < 1e-9
                for source in ("annotator A", "annotator B", "coarse rule output")
            ),
        ),
        ("main_outputs_cover_all_retained_rows", len(outputs) == sum(int(r["row_count"]) for r in retained)),
        ("timestamps_are_monotonic", sum(int(r["nonmonotonic_timestamp_count"]) for r in retained) == 0),
        ("transition_pairs_exclude_gap_boundaries", all_transition_count == expected_adjacent_pairs),
        ("transition_path_counts_reconcile", all_transition_count == split_transition_count),
        ("transition_groups_complete", {r["path_group"] for r in transition_groups} == {"all", "ADB-like", "browser-compatible"}),
        (
            "annotation_interfaces_mask_machine_columns",
            len(interface_audit) == 10
            and all(r["interface_file_present"] for r in interface_audit)
            and all(r["review_mode"] == "false" for r in interface_audit)
            and not any(r["machine_and_prior_label_columns_visible"] for r in interface_audit),
        ),
        (
            "annotation_interfaces_hide_alignment_panel_after_confirmation",
            len(interface_audit) == 10
            and all(r["alignment_panel_hidden_after_confirmation"] for r in interface_audit),
        ),
        (
            "annotation_sensitivity_has_primary_s021_and_leave_one_out",
            {r["scenario"] for r in annotation_sensitivity_rows}
            == {"primary_manual_offsets", "leave_one_session_out", "s021_automatic_offset"}
            and sum(r["scenario"] == "leave_one_session_out" for r in annotation_sensitivity_rows)
            == 20
            and all(
                int(r["n_bins"]) == 660 and int(r["missing_machine_bins"]) == 1
                for r in annotation_sensitivity_rows
                if r["scenario"] == "s021_automatic_offset"
            ),
        ),
        (
            "evidence_paths_are_portable",
            not any(re.match(r"^[A-Za-z]:\\", str(r.get("source_file", ""))) for r in qc),
        ),
        (
            "historical_versions_remain_not_retained",
            all(
                r["value"] == "not retained" and r["status"] == "NOT_RETAINED"
                for r in software_versions
                if r["component"]
                in {
                    "PICO OS build",
                    "ADB client/platform-tools version",
                    "Browser engine and WebXR runtime",
                }
            ),
        ),
        (
            "archived_package_versions_are_separately_verified",
            {(r["component"], r["value"]) for r in software_versions}
            >= {
                ("Platform code", "2.3"),
                ("Embedded Python", "3.12.8"),
                ("Python websockets", "16.0"),
            },
        ),
        (
            "circular_euler_range_ablation_present",
            sum(r["configuration"] == "circular_euler_range" for r in ablation_rows) == 3,
        ),
        (
            "one_at_a_time_threshold_sensitivity_complete",
            len(threshold_one_at_a_time_rows)
            == len(THRESHOLDS) * (len(THRESHOLD_PERTURBATIONS) - 1) * 3
            and {r["threshold_name"] for r in threshold_one_at_a_time_rows}
            == set(THRESHOLDS),
        ),
        (
            "euler_range_sensitivity_covers_retained_sessions",
            len(euler_range_rows) == len(retained)
            and {r["session_id"] for r in euler_range_rows}
            == {r["session_id"] for r in retained},
        ),
        (
            "circular_euler_output_change_reconciles",
            sum(int(r["rule_output_changed_count"]) for r in euler_range_rows)
            == round(
                next(
                    float(r["weighted_output_change_fraction_vs_2s"])
                    * int(r["n_samples"])
                    for r in ablation_rows
                    if r["configuration"] == "circular_euler_range"
                    and r["path_group"] == "all"
                )
            ),
        ),
        (
            "residual_reason_counts_reconcile",
            sum(int(r["residual_sample_count"]) for r in all_residual_rows)
            == observed_residual_count
            == split_residual_count,
        ),
        (
            "residual_reason_fractions_reconcile",
            abs(
                sum(float(r["fraction_of_group_residual_samples"]) for r in all_residual_rows)
                - 1.0
            )
            < 1e-9,
        ),
        (
            "residual_reason_other_is_empty",
            next(r for r in all_residual_rows if r["reason"] == "other")[
                "residual_sample_count"
            ]
            == 0,
        ),
    ]
    return [{"check": name, "status": "PASS" if passed else "FAIL"} for name, passed in checks]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument(
        "--report-root",
        type=Path,
        help="Directory containing dated HTML/PDF reports; defaults to --raw-root.",
    )
    parser.add_argument("--annotation-root", type=Path, required=True)
    parser.add_argument("--platform-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    report_root = args.report_root or args.raw_root

    evidence_dir = args.output_root / "evidence"
    qa_dir = args.output_root / "qa"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    qa_dir.mkdir(parents=True, exist_ok=True)

    raw_files = sorted(args.raw_root.glob("imu_analysis_*.csv"))
    observed_ids = {re.search(r"(\d+)", p.stem).group(1) for p in raw_files}
    if observed_ids != set(EXPORT_TO_SESSION):
        raise AssertionError("Raw export set does not match the locked 30-file mapping")

    all_sessions = {}
    qc_rows = []
    for path in raw_files:
        export_id = re.search(r"(\d+)", path.stem).group(1)
        data = read_export(path, EXPORT_TO_SESSION[export_id])
        all_sessions[data.session_id] = data
        qc_rows.append(qc_row(data))
    qc_rows.sort(key=lambda r: r["session_id"])
    qc_by_sid = {r["session_id"]: r for r in qc_rows}
    retained_sessions = {
        sid: data for sid, data in sorted(all_sessions.items()) if sid not in EXCLUDED
    }

    flow_rows = participant_flow(args.raw_root, report_root)
    software_versions = software_version_audit(args.platform_root)
    write_csv(evidence_dir / "participant_flow.csv", flow_rows)
    write_csv(evidence_dir / "software_version_audit.csv", software_versions)
    write_csv(evidence_dir / "session_qc.csv", qc_rows)
    write_csv(evidence_dir / "path_comparison.csv", summarize_paths(qc_rows))

    main_outputs = {
        sid: classify_session(data, qc_by_sid[sid], PRIMARY_WINDOW_S)
        for sid, data in retained_sessions.items()
    }
    flat_main = [r for sid in sorted(main_outputs) for r in main_outputs[sid]]
    write_csv(evidence_dir / "time_window_outputs.csv", flat_main)

    session_dist = session_rule_distribution(main_outputs)
    write_csv(evidence_dir / "rule_distribution_by_session.csv", session_dist)
    write_csv(evidence_dir / "rule_distribution_summary.csv", summarize_rule_distribution(session_dist))
    residual_reason_rows = summarize_residual_outputs(main_outputs)
    write_csv(evidence_dir / "residual_output_audit.csv", residual_reason_rows)
    transition_matrix, transition_groups = summarize_transitions(main_outputs)
    write_csv(evidence_dir / "transition_matrix.csv", transition_matrix)
    write_csv(evidence_dir / "transition_group_summary.csv", transition_groups)

    ablation, threshold, threshold_one_at_a_time = run_ablation(
        retained_sessions, qc_by_sid, main_outputs
    )
    euler_range_rows = summarize_euler_range_sensitivity(
        retained_sessions, qc_by_sid, main_outputs
    )
    write_csv(evidence_dir / "ablation_summary.csv", ablation)
    write_csv(evidence_dir / "threshold_sensitivity.csv", threshold)
    write_csv(
        evidence_dir / "threshold_one_at_a_time.csv", threshold_one_at_a_time
    )
    write_csv(evidence_dir / "euler_range_sensitivity.csv", euler_range_rows)

    agreement, confusion, annotation_detail = annotation_analysis(main_outputs, args.annotation_root)
    prevalence = annotation_prevalence(annotation_detail)
    annotation_sensitivity_rows = annotation_sensitivity(main_outputs, annotation_detail)
    write_csv(evidence_dir / "annotation_agreement.csv", agreement)
    write_csv(evidence_dir / "annotation_confusion_long.csv", confusion)
    write_csv(evidence_dir / "annotation_bin_outputs.csv", annotation_detail)
    write_csv(evidence_dir / "annotation_prevalence.csv", prevalence)
    write_csv(evidence_dir / "annotation_sensitivity.csv", annotation_sensitivity_rows)
    alignment_rows = annotation_alignment_audit(args.annotation_root, annotation_detail)
    write_csv(evidence_dir / "annotation_alignment_audit.csv", alignment_rows)
    interface_rows = annotation_interface_audit(args.annotation_root, annotation_detail)
    write_csv(evidence_dir / "annotation_interface_audit.csv", interface_rows)

    checks = qa_checks(
        flow_rows,
        qc_rows,
        agreement,
        prevalence,
        flat_main,
        transition_matrix,
        transition_groups,
        interface_rows,
        annotation_sensitivity_rows,
        software_versions,
        ablation,
        threshold_one_at_a_time,
        euler_range_rows,
        residual_reason_rows,
    )
    write_csv(qa_dir / "evidence_qa.csv", checks)
    failed = [r["check"] for r in checks if r["status"] != "PASS"]

    input_paths = raw_files
    input_paths += list(report_root.glob("IMU_S*_行为分析报告_*"))
    input_paths += list((args.annotation_root / "盲标回收_20260727").glob("*.csv"))
    input_paths += list((args.annotation_root / "标注员2回收_20260728").glob("*.csv"))
    input_paths += [args.annotation_root / "auto_alignment.csv", args.annotation_root / "锚点核对表.csv"]
    input_paths += [args.annotation_root / "Annotation_Protocol.md"]
    input_paths += [
        args.annotation_root / "标注工具" / f"标注_受测者{int(sid[1:])}.html"
        for sid in sorted({row["session_id"] for row in annotation_detail})
    ]
    input_paths += [
        args.annotation_root.parent / "scripts" / "auto_align_videos.py",
        args.annotation_root.parent / "scripts" / "build_annotation_tool.py",
    ]
    input_paths += [
        args.platform_root / "sensor.html",
        args.platform_root / "scripts" / "adb_sensor_reader.py",
        args.platform_root / "scripts" / "ws_broker.py",
        args.platform_root / "src" / "js" / "modules" / "data-mapper.js",
        args.platform_root / "src" / "js" / "modules" / "behavior-analyzer.js",
        args.platform_root / "src" / "js" / "modules" / "report-generator.js",
        args.platform_root / "project.config.json",
        args.platform_root / "runtime" / "python-embed" / "python.exe",
        args.platform_root / "runtime" / "python-embed" / "Lib" / "websockets-16.0.dist-info" / "METADATA",
        Path(__file__),
    ]
    manifest = build_manifest(
        input_paths,
        args.raw_root,
        report_root,
        args.annotation_root,
        args.platform_root,
    )
    write_csv(evidence_dir / "sha256_source_manifest.csv", manifest)

    retained_qc = [r for r in qc_rows if r["included"]]
    report_extensions = Counter(
        Path(name).suffix.lower()
        for row in flow_rows
        for name in (row["report_files"].split("|") if row["report_files"] else [])
    )
    all_transition = next(r for r in transition_groups if r["path_group"] == "all")
    largest_oat = max(
        (r for r in threshold_one_at_a_time if r["path_group"] == "all"),
        key=lambda r: r["weighted_output_change_fraction_vs_nominal"],
    )
    circular_all = next(
        r
        for r in ablation
        if r["configuration"] == "circular_euler_range" and r["path_group"] == "all"
    )
    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "signed_consent_records_author_reported": AUTHOR_REPORTED_SIGNED_CONSENT_RECORDS,
        "consent_evidence_basis": CONSENT_EVIDENCE_BASIS,
        "software_version_audit": software_versions,
        "csv_exports": 30,
        "dated_report_files": sum(report_extensions.values()),
        "dated_report_files_by_format": {
            "html": report_extensions[".html"],
            "pdf": report_extensions[".pdf"],
        },
        "retained_sessions": 29,
        "excluded_sessions": sorted(EXCLUDED),
        "path_counts": dict(Counter(r["path_group"] for r in retained_qc)),
        "acc_frozen_sessions": [r["session_id"] for r in retained_qc if r["acc_frozen"]],
        "euler_frozen_sessions": [r["session_id"] for r in retained_qc if r["euler_frozen"]],
        "total_retained_samples": len(flat_main),
        "retained_first_to_last_span_s": sum(float(r["duration_s"]) for r in retained_qc),
        "retained_long_gap_span_s": sum(float(r["gap_excluded_span_s"]) for r in retained_qc),
        "retained_long_gap_count": sum(int(r["long_gap_count"]) for r in retained_qc),
        "retained_sessions_with_long_gaps": sum(
            int(r["long_gap_count"]) > 0 for r in retained_qc
        ),
        "consecutive_identical_export_value_pairs": sum(
            int(r["consecutive_identical_export_value_pair_count"]) for r in retained_qc
        ),
        "annotation_bins": len(annotation_detail),
        "annotation_alignment_r_range": [
            min(r["cross_correlation_r"] for r in alignment_rows),
            max(r["cross_correlation_r"] for r in alignment_rows),
        ],
        "annotation_interfaces_review_mode_false": sum(
            row["review_mode"] == "false" for row in interface_rows
        ),
        "adjacent_export_sample_pairs": int(all_transition["n_adjacent_pairs"]),
        "weighted_changed_output_pair_fraction": all_transition["weighted_changed_pair_fraction"],
        "session_median_changed_output_pair_fraction": all_transition[
            "session_median_changed_pair_fraction"
        ],
        "largest_one_at_a_time_threshold_effect": largest_oat,
        "circular_euler_range_weighted_output_change_fraction": circular_all[
            "weighted_output_change_fraction_vs_2s"
        ],
        "euler_range_sensitivity": {
            "sessions_with_changed_window_range": sum(
                int(r["range_changed_sample_count"]) > 0 for r in euler_range_rows
            ),
            "samples_with_changed_window_range": sum(
                int(r["range_changed_sample_count"]) for r in euler_range_rows
            ),
            "maximum_range_reduction_deg": max(
                float(r["maximum_range_reduction_deg"]) for r in euler_range_rows
            ),
            "rule_outputs_changed": sum(
                int(r["rule_output_changed_count"]) for r in euler_range_rows
            ),
        },
        "residual_output_audit": [
            row for row in residual_reason_rows if row["path_group"] == "all"
        ],
        "annotation_agreement": agreement,
        "annotation_s021_automatic_offset_sensitivity": [
            row
            for row in annotation_sensitivity_rows
            if row["scenario"] == "s021_automatic_offset"
        ],
        "annotation_leave_one_session_out_kappa_range": {
            pair: [
                min(
                    row["cohen_kappa"]
                    for row in annotation_sensitivity_rows
                    if row["scenario"] == "leave_one_session_out"
                    and row["comparison"] == pair
                ),
                max(
                    row["cohen_kappa"]
                    for row in annotation_sensitivity_rows
                    if row["scenario"] == "leave_one_session_out"
                    and row["comparison"] == pair
                ),
            ]
            for pair in ("rule output vs rater A", "rule output vs rater B")
        },
        "qa_failed": failed,
        "analysis_constraints": [
            "Stored behavior and confidence columns were not read for revised analyses.",
            "Browser-compatible and ADB-like streams were stratified; source was not retained in exports.",
            "Acceleration-excursion and Euler-dependent rules were disabled when their channels were frozen.",
            "Rule outputs are deterministic software outputs, not externally validated behavioral ground truth.",
        ],
    }
    (evidence_dir / "evidence_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    qa_lines = ["# Evidence QA", "", f"Status: {'FAIL' if failed else 'PASS'}", ""]
    qa_lines.extend(f"- {r['status']}: {r['check']}" for r in checks)
    (qa_dir / "evidence_qa.md").write_text("\n".join(qa_lines) + "\n", encoding="utf-8")
    if failed:
        raise SystemExit("Evidence QA failed: " + ", ".join(failed))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

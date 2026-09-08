"""Rebuild the September revision from controlled originals, then extend its audit."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import re
import subprocess
import sys
from bisect import bisect_left
from collections import Counter, defaultdict
from dataclasses import replace
from pathlib import Path

import rebuild_evidence as a


ROOT = Path(__file__).resolve().parents[1]


def read_csv(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def gap_matched_legacy(data, qc):
    """Keep full-session eligibility while restarting sample history at gaps."""
    starts = [0] + [i for i in range(1, data.n)
                    if data.timestamp[i] - data.timestamp[i - 1] > qc["long_gap_threshold_s"]]
    result = []
    fields = ("timestamp", "acc_mag", "gyro_mag", "roll", "pitch", "yaw")
    for segment_id, (lo, hi) in enumerate(zip(starts, starts[1:] + [data.n])):
        part = replace(data, **{name: getattr(data, name)[lo:hi] for name in fields})
        rows = a.classify_session(part, qc, None, legacy_21_samples=True)
        for j, row in enumerate(rows):
            row.update(sample_index=lo + j, window_start_index=lo + row["window_start_index"],
                       segment_id=segment_id, gap_reset=lo > 0 and j == 0,
                       window_definition="legacy_21_samples_gap_reset")
        result.extend(rows)
    return result


def footer_record(path, rater):
    text = path.read_text(encoding="utf-8-sig")
    matches = [line for line in text.splitlines() if line.startswith("# video_anchor_seconds=")]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one alignment footer: {path.name}")
    fields = dict(item.strip().split("=", 1) for item in matches[0][2:].split(";") if "=" in item)
    method = fields["align_method"].split("|")
    return {"session_id": a.parse_annotation_subject(path), "rater": rater,
            "final_offset_s": -float(fields["video_anchor_seconds"]),
            "manual_nudge_recorded": "nudge" in method,
            "nudge_token_count": method.count("nudge"),
            "alignment_confirmed": "confirmed" in method,
            "blind_mode_exported": fields.get("blind_mode", ""),
            "saw_machine_self_report": fields.get("saw_machine", ""),
            "independent_self_report": fields.get("independent", ""),
            "source_sha256": a.sha256(path)}


def extend(raw_root, annotation_root, output_root=ROOT):
    evidence = output_root / "evidence"
    sessions, qc, primary = {}, {}, {}
    for path in sorted(raw_root.glob("imu_analysis_*.csv")):
        sid = a.EXPORT_TO_SESSION[re.search(r"(\d+)", path.stem).group(1)]
        if sid in a.EXCLUDED:
            continue
        sessions[sid] = a.read_export(path, sid)
        qc[sid] = a.qc_row(sessions[sid])
        primary[sid] = a.classify_session(sessions[sid], qc[sid], 2.0)

    matched, session_comparison = {}, []
    for sid, data in sessions.items():
        old = a.classify_session(data, qc[sid], None, legacy_21_samples=True)
        matched[sid] = gap_matched_legacy(data, qc[sid])
        session_comparison.append({
            "session_id": sid, "path_group": qc[sid]["path_group"], "n_samples": data.n,
            "legacy_vs_primary_count": sum(x["rule_output"] != y["rule_output"] for x, y in zip(old, primary[sid])),
            "matched_vs_primary_count": sum(x["rule_output"] != y["rule_output"] for x, y in zip(matched[sid], primary[sid])),
            "reset_only_change_count": sum(x["rule_output"] != y["rule_output"] for x, y in zip(old, matched[sid])),
        })
    a.write_csv(evidence / "gap_matched_legacy_by_session.csv", session_comparison)
    a.write_csv(evidence / "gap_matched_legacy_outputs.csv", [r for sid in sorted(matched) for r in matched[sid]])
    ablation = [row for row in read_csv(evidence / "ablation_summary.csv")
                if row["configuration"] != "legacy_21_samples_gap_reset"]
    matched_summary = []
    for group in ("all", "ADB-like", "browser-compatible"):
        selected = [r for r in session_comparison if group == "all" or r["path_group"] == group]
        n = sum(r["n_samples"] for r in selected)
        change = sum(r["matched_vs_primary_count"] for r in selected)
        med, q1, q3 = a.median_iqr([r["matched_vs_primary_count"] / r["n_samples"] for r in selected])
        conflict = sum(row["condition_count"] > 1 for r in selected for row in matched[r["session_id"]])
        row = {"configuration": "legacy_21_samples_gap_reset", "path_group": group,
               "n_sessions": len(selected), "n_samples": n,
               "weighted_output_change_fraction_vs_2s": change / n,
               "session_median_change_fraction": med, "session_q1_change_fraction": q1,
               "session_q3_change_fraction": q3, "conflict_sample_fraction": conflict / n}
        ablation.append(row)
        matched_summary.append({**row, "changed_count": change,
                                "reset_only_change_count": sum(r["reset_only_change_count"] for r in selected)})
    a.write_csv(evidence / "ablation_summary.csv", ablation)
    a.write_csv(evidence / "gap_matched_legacy_summary.csv", matched_summary)

    bins = read_csv(evidence / "annotation_bin_outputs.csv")
    bins_by_session = defaultdict(list)
    for row in bins:
        bins_by_session[row["session_id"]].append(row)
    returns = []
    for directory, rater in (("盲标回收_20260727", "A"), ("标注员2回收_20260728", "B")):
        for path in sorted((annotation_root / directory).glob("*.csv")):
            if a.parse_annotation_subject(path) in bins_by_session:
                returns.append(footer_record(path, rater))
    a.write_csv(evidence / "annotation_return_metadata.csv", returns)
    return_lookup = {(r["session_id"], r["rater"]): r for r in returns}
    candidates = []
    for row in read_csv(annotation_root / "auto_alignment.csv"):
        sid = f"S{int(row['subject']):03d}"
        selected = row["confident"].lower() == "true"
        reason = "retained" if selected else ("correlation_below_0.45" if float(row["r"]) < .45 else "peak_margin_below_0.08")
        rec = {"session_id": sid, "automatic_offset_s": row["offset_s"],
               "correlation_r": row["r"], "peak_margin": row["margin"],
               "automatic_overlap_s": row["overlap_s"], "selected": selected, "selection_reason": reason,
               "paired_bins": len(bins_by_session[sid])}
        for rater in ("A", "B"):
            ret = return_lookup.get((sid, rater))
            rec[f"confirmed_offset_{rater}_s"] = ret["final_offset_s"] if ret else ""
        candidates.append(rec)
    a.write_csv(evidence / "annotation_candidate_selection.csv", candidates)

    coverage = []
    for sid, intervals in sorted(bins_by_session.items()):
        ts = sessions[sid].timestamp
        covered = set()
        for interval in intervals:
            covered.update(range(bisect_left(ts, float(interval["start_s"])), bisect_left(ts, float(interval["end_s"]))))
        coverage.append({"session_id": sid, "paired_bins": len(intervals), "covered_exported_samples": len(covered),
                         "session_samples": len(ts), "sample_coverage_fraction": len(covered) / len(ts)})
    a.write_csv(evidence / "annotation_sample_coverage.csv", coverage)

    counts, eligible = [], []
    for sid, outputs in sorted(primary.items()):
        for taxonomy, key in (("six", "rule_output"), ("three", "coarse_head_motion_output")):
            counter = Counter(r[key] for r in outputs)
            labels = a.ALL_RULE_OUTPUTS if taxonomy == "six" else a.COARSE_OUTPUTS
            for label in labels:
                counts.append({"session_id": sid, "path_group": qc[sid]["path_group"], "taxonomy": taxonomy,
                               "output": label, "assigned_count": counter[label], "session_samples": len(outputs)})
    for group in ("all", "ADB-like", "browser-compatible"):
        sids = [sid for sid in sessions if group == "all" or qc[sid]["path_group"] == group]
        total = sum(sessions[sid].n for sid in sids)
        for label, channel in (("smooth_turn_rule", "euler_usable_for_window_rules"),
                               ("acceleration_excursion_rule", "acc_usable_for_excursion_rule"),
                               ("low_motion_rule", "euler_usable_for_window_rules")):
            valid = [sid for sid in sids if qc[sid][channel]]
            valid_n = sum(sessions[sid].n for sid in valid)
            assigned = sum(r["rule_output"] == label for sid in sids for r in primary[sid])
            eligible.append({"path_group": group, "output": label, "all_sessions": len(sids), "all_samples": total,
                             "eligible_sessions": len(valid), "eligible_samples": valid_n, "assigned_count": assigned,
                             "all_sample_fraction": assigned / total,
                             "eligible_sample_fraction": assigned / valid_n if valid_n else ""})
    a.write_csv(evidence / "exact_output_counts.csv", counts)
    a.write_csv(evidence / "channel_eligible_denominators.csv", eligible)

    # Retain the engine unchanged; normalize reporting terminology at the output boundary.
    for name in ("path_comparison.csv", "rule_distribution_summary.csv"):
        rows = read_csv(evidence / name)
        for row in rows:
            if "time_sample_weighted_fraction" in row:
                row["sample_count_weighted_fraction"] = row.pop("time_sample_weighted_fraction")
            if row.get("n_sessions") == "2":
                for key in row:
                    if "bootstrap" in key and "ci" in key:
                        row[key] = ""
        a.write_csv(evidence / name, rows)

    # Replace the earlier first-bin-derived field with separately evidenced offsets.
    alignment = []
    for rec in candidates:
        if not rec["selected"]:
            continue
        sid = rec["session_id"]
        alignment.append({**rec, "earliest_evaluated_bin_s": min(float(r["start_s"]) for r in bins_by_session[sid]),
                          "offset_evidence": "original_return_footer", "not_independent_alignment_validation": True})
    a.write_csv(evidence / "annotation_alignment_audit.csv", alignment)
    summary = json.loads((evidence / "evidence_summary.json").read_text(encoding="utf-8"))
    summary.update(revision_date="2026-09-08", execution_python=platform.python_version(),
                   all_sensitivity_and_annotation_intervals_recomputed=True,
                   video_cross_correlation_rerun=False,
                   annotation_covered_samples=sum(r["covered_exported_samples"] for r in coverage),
                   annotation_covered_sample_fraction=sum(r["covered_exported_samples"] for r in coverage) / len([x for r in primary.values() for x in r]),
                   candidate_selection=candidates, gap_matched_legacy=matched_summary)
    (evidence / "evidence_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    checks = {"nineteen_candidates": len(candidates) == 19,
              "ten_selected_candidates": sum(r["selected"] for r in candidates) == 10,
              "twenty_original_return_footers": len(returns) == 20,
              "selection_matches_paired_sessions": {r["session_id"] for r in candidates if r["selected"]} == {sid for sid, rows in bins_by_session.items() if rows},
              "s021_confirmed_offset_68": all(return_lookup[("S021", r)]["final_offset_s"] == 68 for r in "AB"),
              "s021_nudge_trace": all(return_lookup[("S021", r)]["manual_nudge_recorded"] for r in "AB"),
              "annotation_samples_2400": summary["annotation_covered_samples"] == 2400,
              "matched_primary_adb_changes_974": next(r for r in matched_summary if r["path_group"] == "ADB-like")["changed_count"] == 974,
              "reset_only_adb_changes_59": next(r for r in matched_summary if r["path_group"] == "ADB-like")["reset_only_change_count"] == 59,
              "all_current_evidence_passed": not summary["qa_failed"]}
    a.write_csv(output_root / "qa" / "extension_qa.csv", [{"check": k, "status": "PASS" if v else "FAIL"} for k, v in checks.items()])
    if not all(checks.values()):
        raise AssertionError(checks)
    print(json.dumps({"retained_samples": summary["total_retained_samples"], "annotation_samples": summary["annotation_covered_samples"],
                      "gap_matched": matched_summary, "checks": checks}, indent=2))


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--annotation-root", type=Path, required=True)
    parser.add_argument("--platform-root", type=Path, required=True)
    parser.add_argument("--report-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    cmd = [sys.executable, str(ROOT / "scripts" / "rebuild_evidence.py"),
           "--raw-root", str(args.raw_root), "--annotation-root", str(args.annotation_root),
           "--platform-root", str(args.platform_root), "--output-root", str(args.output_root),
           "--report-root", str(args.report_root)]
    subprocess.run(cmd, check=True)
    extend(args.raw_root, args.annotation_root, args.output_root)


if __name__ == "__main__":
    main()

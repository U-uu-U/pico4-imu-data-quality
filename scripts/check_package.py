"""Verify the public derivative snapshot using only the Python standard library."""
import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE_FOLDERS = ("scripts", "tests", "evidence", "figures", "references")
CORE_FILES = ("README.md", "DATA_DICTIONARY.md", "requirements.txt",
              "study_metadata.json", ".gitignore", ".gitattributes")


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def package_files(root=ROOT):
    files = [root / name for name in CORE_FILES]
    for folder in CORE_FOLDERS:
        files.extend(path for path in (root / folder).rglob("*") if path.is_file()
                     and "__pycache__" not in path.parts and path.suffix != ".pyc")
    return sorted(files)


def manifest_matches(manifest, root=ROOT):
    expected = {row["path"]: row["sha256"] for row in manifest}
    actual = {path.relative_to(root).as_posix(): path for path in package_files(root)}
    return (len(expected) == len(manifest) and set(expected) == set(actual)
            and all(path.is_file() and digest(path) == expected[name]
                    for name, path in actual.items()))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-manifest", action="store_true")
    args = parser.parse_args()
    evidence = ROOT / "evidence"
    checks = {}
    qc = [row for row in read(evidence / "session_qc.csv") if row["included"] == "true"]
    totals = {row["session_id"]: int(row["row_count"]) for row in qc}
    checks["29_sessions_45560_samples"] = len(totals) == 29 and sum(totals.values()) == 45560
    facts = json.loads((ROOT / "study_metadata.json").read_text(encoding="utf-8"))
    checks["34_distinct_participants_once"] = facts["distinct_participants"] == 34 and facts["sessions_per_participant"] == 1
    checks["retrospective_completeness_gate"] = facts["completeness_threshold_timing"] == "retrospective; not preregistered"
    flow = {row["session_id"]: row for row in read(evidence / "participant_flow.csv")}
    checks["corrected_session_mapping"] = (len(flow) == 34 and flow["S012"]["analysis_csv_available"] == "false"
        and flow["S013"]["export_id"] == "1776846533989" and flow["S014"]["export_id"] == "1776847632327")
    actual = Counter()
    conflicts = 0
    for row in read(evidence / "time_window_outputs.csv"):
        conflicts += int(row["condition_count"]) > 1
        actual[(row["session_id"], "six", row["rule_output"])] += 1
        actual[(row["session_id"], "three", row["coarse_head_motion_output"])] += 1
    exact = read(evidence / "exact_output_counts.csv")
    checks["261_exact_components_match_outputs"] = len(exact) == 261 and all(
        actual[(row["session_id"], row["taxonomy"], row["output"])] == int(row["assigned_count"]) for row in exact)
    checks["each_taxonomy_closes_per_session"] = all(
        sum(int(row["assigned_count"]) for row in exact if row["session_id"] == sid and row["taxonomy"] == tax) == total
        for sid, total in totals.items() for tax in ("six", "three"))
    checks["conflict_fraction_3073_45560_6_74_percent"] = conflicts == 3073 and f"{100*conflicts/45560:.2f}" == "6.74"
    checks["eligible_denominators_and_fractions"] = all(
        int(row["assigned_count"]) <= int(row["eligible_samples"]) <= int(row["all_samples"])
        and abs(float(row["all_sample_fraction"]) - int(row["assigned_count"])/int(row["all_samples"])) < 1e-6
        and (not row["eligible_sample_fraction"] or
             abs(float(row["eligible_sample_fraction"]) - int(row["assigned_count"])/int(row["eligible_samples"])) < 1e-6)
        for row in read(evidence / "channel_eligible_denominators.csv"))
    for name in ("path_comparison.csv", "rule_distribution_summary.csv"):
        checks["n2_ci_suppressed_" + name] = all(not row[key] for row in read(evidence / name)
            if row["n_sessions"] == "2" for key in row if "bootstrap" in key and "ci" in key)
    confusion = read(evidence / "annotation_confusion_long.csv")
    for agreement in read(evidence / "annotation_agreement.csv"):
        cells = [row for row in confusion if row["pair"] == agreement["pair"] and row["taxonomy"] == agreement["taxonomy"]]
        total = sum(int(row["count"]) for row in cells)
        diagonal = sum(int(row["count"]) for row in cells if row["reference_label"] == row["comparison_label"])
        rows, cols = Counter(), Counter()
        for row in cells:
            rows[row["reference_label"]] += int(row["count"])
            cols[row["comparison_label"]] += int(row["count"])
        expected = sum(rows[key]*cols[key] for key in rows)/total**2
        kappa = (diagonal/total - expected)/(1 - expected)
        checks[agreement["pair"] + "_" + agreement["taxonomy"]] = total == 661 and abs(kappa - float(agreement["cohen_kappa"])) < 1e-6
    candidates = read(evidence / "annotation_candidate_selection.csv")
    checks["19_candidates_10_selected"] = len(candidates) == 19 and sum(row["selected"] == "true" for row in candidates) == 10
    returns = read(evidence / "annotation_return_metadata.csv")
    s021 = [row for row in returns if row["session_id"] == "S021"]
    checks["20_return_records_and_saved_s021_adjustment"] = len(returns) == 20 and len(s021) == 2 and all(
        float(row["final_offset_s"]) == 68 and row["manual_nudge_recorded"] == "true" and row["alignment_confirmed"] == "true" for row in s021)
    coverage = read(evidence / "annotation_sample_coverage.csv")
    checks["661_bins_cover_2400_samples"] = sum(int(row["paired_bins"]) for row in coverage) == 661 and sum(int(row["covered_exported_samples"]) for row in coverage) == 2400
    matched = read(evidence / "gap_matched_legacy_by_session.csv")
    checks["matched_counts_by_timing_group"] = all(
        sum(int(row["matched_vs_primary_count"]) for row in matched if row["path_group"] == group) == count
        for group, count in (("ADB-like", 974), ("browser-compatible", 47)))
    checks["reset_only_59_changes"] = sum(int(row["reset_only_change_count"]) for row in matched) == 59
    residual = [row for row in read(evidence / "residual_output_audit.csv") if row["path_group"] == "all"]
    checks["residual_breakdown_closes"] = sum(int(row["residual_sample_count"]) for row in residual) == 32660
    checks["two_current_figures_with_sources"] = {path.name for path in (ROOT / "figures").iterdir() if path.is_file()} == {
        f"{name}.{extension}" for name in ("figure1_reanalysis_workflow", "figure2_output_composition")
        for extension in ("png", "svg", "pdf")}

    manifest = ROOT / "qa" / "public_release_sha256.csv"
    manifest.parent.mkdir(exist_ok=True)
    if args.write_manifest:
        with manifest.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=["path", "sha256"])
            writer.writeheader()
            writer.writerows({"path": path.relative_to(ROOT).as_posix(), "sha256": digest(path)} for path in package_files())
    checks["exact_manifest_members_and_hashes"] = manifest.exists() and manifest_matches(read(manifest))
    with (ROOT / "qa" / "derived_qa.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["check", "status"])
        writer.writeheader()
        writer.writerows({"check": key, "status": "PASS" if value else "FAIL"} for key, value in checks.items())
    print(json.dumps({"passed": sum(checks.values()), "total": len(checks), "failed": [key for key, value in checks.items() if not value]}, indent=2))
    if not all(checks.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()

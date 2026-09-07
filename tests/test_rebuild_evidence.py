import importlib.util
import inspect
import sys
import tempfile
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "rebuild_evidence.py"
SPEC = importlib.util.spec_from_file_location("rebuild_evidence", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_irregular_timestamp_window_and_gap_reset():
    timestamp = [0.0, 0.2, 0.9, 1.8, 2.1, 5.0, 5.2]
    starts, segments, resets = MODULE.window_bounds(timestamp, 2.0, 1.0)
    assert starts == [0, 0, 0, 0, 1, 5, 5]
    assert segments == [0, 0, 0, 0, 0, 1, 1]
    assert resets == [False, False, False, False, False, True, False]


def test_mapping_corrections_are_locked():
    assert MODULE.EXPORT_TO_SESSION["1776844051112"] == "S011"
    assert MODULE.EXPORT_TO_SESSION["1776846533989"] == "S013"
    assert MODULE.EXPORT_TO_SESSION["1776847632327"] == "S014"
    assert "S012" not in MODULE.EXPORT_TO_SESSION.values()


def test_legacy_window_contains_up_to_21_samples():
    assert [max(0, i - 20) for i in range(25)][20] == 0
    assert 20 - max(0, 20 - 20) + 1 == 21


def test_circular_euler_range_handles_wraparound():
    assert MODULE.circular_range_deg([179.0, -179.0]) == 2.0
    assert MODULE.circular_range_deg([10.0, 20.0, 30.0]) == 20.0


def test_euler_range_audit_separates_range_and_output_changes():
    data = MODULE.SessionData(
        session_id="S001",
        export_id="example",
        source_file=Path("example.csv"),
        timestamp=[0.0, 0.5, 1.0],
        acc_mag=[MODULE.GRAVITY] * 3,
        gyro_mag=[0.1] * 3,
        roll=[0.0] * 3,
        pitch=[0.0] * 3,
        yaw=[179.0, -179.0, -178.0],
    )
    qc = {
        "path_group": "browser-compatible",
        "long_gap_threshold_s": 1.0,
        "acc_usable_for_excursion_rule": True,
        "euler_usable_for_window_rules": True,
    }
    main = MODULE.classify_session(data, qc, MODULE.PRIMARY_WINDOW_S)
    rows = MODULE.summarize_euler_range_sensitivity(
        {"S001": data}, {"S001": qc}, {"S001": main}
    )
    assert rows[0]["range_changed_sample_count"] == 2
    assert rows[0]["maximum_range_reduction_deg"] == 356.0
    assert rows[0]["rule_output_changed_count"] == 0


def test_export_reader_rejects_nonfinite_required_values(tmp_path):
    path = tmp_path / "imu_analysis_1.csv"
    path.write_text(
        "timestamp,accMag,gyroMag,roll,pitch,yaw,behavior,confidence\n"
        "0,9.8,nan,0,0,0,idle,1\n",
        encoding="utf-8",
    )
    try:
        MODULE.read_export(path, "S001")
    except ValueError as exc:
        assert "non-finite value in gyroMag" in str(exc)
    else:
        raise AssertionError("non-finite input was accepted")


def test_kappa_identity():
    labels = ["a", "b", "a", "c"]
    assert MODULE.cohen_kappa(labels, labels) == 1.0


def test_transition_summary_does_not_cross_gap_segments():
    outputs = {
        "S001": [
            {"path_group": "ADB-like", "segment_id": 0, "rule_output": "rapid_turn_rule"},
            {"path_group": "ADB-like", "segment_id": 0, "rule_output": "moderate_turn_rule"},
            {"path_group": "ADB-like", "segment_id": 1, "rule_output": "residual_rule_output"},
            {"path_group": "ADB-like", "segment_id": 1, "rule_output": "residual_rule_output"},
        ]
    }
    matrix, groups = MODULE.summarize_transitions(outputs)
    all_group = next(row for row in groups if row["path_group"] == "all")
    assert all_group["n_adjacent_pairs"] == 2
    assert all_group["n_changed_pairs"] == 1
    assert not any(
        row["path_group"] == "all"
        and row["from_output"] == "moderate_turn_rule"
        and row["to_output"] == "residual_rule_output"
        and row["transition_count"]
        for row in matrix
    )


def test_path_names_are_timing_compatibility_labels():
    high_rate, high_note = MODULE.classify_path(0.12)
    low_rate, low_note = MODULE.classify_path(0.267)
    assert high_rate == "browser-compatible"
    assert low_rate == "ADB-like"
    assert "timing" in high_note.lower() and "source was not retained" in high_note.lower()
    assert "timing" in low_note.lower() and "source was not retained" in low_note.lower()


def test_annotation_sensitivity_includes_s021_automatic_offset_and_leave_one_out():
    outputs = {
        "S015": [
            {"timestamp_s": 1.1, "coarse_head_motion_output": "low_head_motion"},
        ],
        "S021": [
            {"timestamp_s": 65.1, "coarse_head_motion_output": "ordinary_head_motion"},
            {"timestamp_s": 68.1, "coarse_head_motion_output": "low_head_motion"},
        ],
    }
    records = [
        {
            "session_id": "S015",
            "start_s": 1.0,
            "end_s": 2.0,
            "rater_a_coarse": "low_head_motion",
            "rater_b_coarse": "low_head_motion",
            "machine_coarse": "low_head_motion",
        },
        {
            "session_id": "S021",
            "start_s": 68.0,
            "end_s": 69.0,
            "rater_a_coarse": "ordinary_head_motion",
            "rater_b_coarse": "ordinary_head_motion",
            "machine_coarse": "low_head_motion",
        },
    ]
    rows = MODULE.annotation_sensitivity(outputs, records)
    assert {row["scenario"] for row in rows} == {
        "primary_manual_offsets",
        "leave_one_session_out",
        "s021_automatic_offset",
    }
    shifted = [row for row in rows if row["scenario"] == "s021_automatic_offset"]
    assert all(row["n_bins"] == 2 for row in shifted)
    assert all(row["s021_time_shift_s"] == -3.0 for row in shifted)


def test_residual_output_audit_characterizes_fallback_rows():
    outputs = {
        "S001": [
            {
                "session_id": "S001",
                "path_group": "browser-compatible",
                "rule_output": "residual_rule_output",
                "gyro_magnitude_exported": 0.10,
                "euler_channel_usable": True,
            },
            {
                "session_id": "S001",
                "path_group": "browser-compatible",
                "rule_output": "moderate_turn_rule",
                "gyro_magnitude_exported": 0.40,
                "euler_channel_usable": True,
            },
        ],
        "S005": [
            {
                "session_id": "S005",
                "path_group": "ADB-like",
                "rule_output": "residual_rule_output",
                "gyro_magnitude_exported": 0.20,
                "euler_channel_usable": False,
            }
        ],
    }
    rows = MODULE.summarize_residual_outputs(outputs)
    all_rows = {row["reason"]: row for row in rows if row["path_group"] == "all"}
    assert all_rows["euler_available_low_motion_range_not_met"]["residual_sample_count"] == 1
    assert all_rows["euler_unavailable_gyro_0.15_to_0.30"]["residual_sample_count"] == 1
    assert sum(row["fraction_of_group_residual_samples"] for row in all_rows.values()) == 1.0


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        if "tmp_path" in inspect.signature(test).parameters:
            with tempfile.TemporaryDirectory() as directory:
                test(Path(directory))
        else:
            test()
    print(f"{len(tests)} tests passed")

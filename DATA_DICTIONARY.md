# Evidence data dictionary

All study identifiers are pseudonyms. Unless stated otherwise, session-level
summaries treat a retained session as the statistical unit. Per-sample rows are
not treated as independent participants. The author confirmed 34 distinct
participants, each participating once; each of the 29 retained sessions
corresponds to a different participant. The 60 s completeness criterion is
retrospective, not prespecified. Public study facts are in `study_metadata.json`.

| File | Unit | Purpose |
|---|---|---|
| `participant_flow.csv` | study identifier | Consent-inventory status, export/report availability, inclusion, exclusion, and mapping evidence |
| `session_qc.csv` | session | Row count, duration, export timing, gap checks, channel ranges, frozen-channel flags, and timing-compatibility group |
| `time_window_outputs.csv` | exported sample | Trailing 2 s window bounds, channel availability, derived magnitudes/ranges, matched rules, deterministic output, and coarse comparison output |
| `path_comparison.csv` | timing group and metric | Session-level median, quartiles, range, and bootstrap interval for export-timing and quality metrics |
| `rule_distribution_by_session.csv` | session | Fractions of deterministic rule and coarse outputs within each session |
| `rule_distribution_summary.csv` | timing group and output | Distribution of session fractions plus sample-count-weighted fractions; n=2 bootstrap intervals are blank |
| `ablation_summary.csv` | configuration and timing group | Output changes for time windows, legacy sample window, no-window baseline, and rule-priority perturbations |
| `threshold_sensitivity.csv` | threshold scale, group, and output | Joint threshold perturbation results from -30% to +30% |
| `threshold_one_at_a_time.csv` | threshold and timing group | One-at-a-time threshold perturbation results |
| `euler_range_sensitivity.csv` | session | Arithmetic versus circular Euler-range differences and resulting rule-output changes |
| `residual_output_audit.csv` | timing group and reason | Composition of the heterogeneous residual rule output |
| `transition_group_summary.csv` | timing group | Adjacent exported-sample transition counts without crossing long-gap boundaries |
| `transition_matrix.csv` | timing group and output pair | Full adjacent-sample transition matrix |
| `annotation_bin_outputs.csv` | one-second annotation bin | Paired rater labels and aligned deterministic outputs for 10 sessions |
| `annotation_agreement.csv` | rater/rule comparison and taxonomy | Agreement, Cohen's kappa, and session-cluster bootstrap interval |
| `annotation_confusion_long.csv` | label pair | Long-form confusion counts |
| `annotation_prevalence.csv` | source and label | Label prevalence for three- and six-category taxonomies |
| `annotation_alignment_audit.csv` | annotated session | Saved final offsets from original return footers, automatic candidate, and earliest evaluated bin reported separately |
| `annotation_interface_audit.csv` | annotated session | Archived annotation-interface masking and review-mode checks |
| `annotation_sensitivity.csv` | sensitivity scenario and comparison | Saved-offset reference, S021 machine-lookup shift of -3 s, and leave-one-session-out results; human labels are unchanged |
| `software_version_audit.csv` | software component | Distinguishes archived-package evidence from unretained acquisition-time versions |
| `reference_claim_audit.csv` | reference | DOI/official-page verification, source excerpt, and semantic-review status |
| `sha256_source_manifest.csv` | controlled source file | Portable source path, byte size, and SHA-256 hash; source files are not public |
| `evidence_summary.json` | package | Machine-readable headline counts and analysis summaries |
| `exact_output_counts.csv` | session, taxonomy, output | Exact assigned counts and complete session denominator for six- and three-group outputs |
| `channel_eligible_denominators.csv` | timing group and dependent rule | Whole-output and channel-eligible session/sample denominators; assignments are after priority resolution |
| `gap_matched_legacy_outputs.csv` | exported sample | Added 21-sample history with the primary long-gap resets and unchanged full-session channel gates |
| `gap_matched_legacy_by_session.csv` | session | Exact historical, reset-matched, and reset-only changed counts |
| `gap_matched_legacy_summary.csv` | timing group | Reset-matched differences, pooled counts, session summaries, and condition-conflict fraction |
| `annotation_candidate_selection.csv` | candidate session | All 19 saved candidates, correlation/margin decisions, offsets, overlap seconds, and paired-bin support |
| `annotation_return_metadata.csv` | session and rater | Anonymous saved final offsets, nudge/confirmation traces, interface/self-report flags, and original-file hashes |
| `annotation_sample_coverage.csv` | annotated session | Paired bins, covered exported samples, and sample-coverage fraction |

The `ADB-like` and `browser-compatible` values are post hoc timing-compatibility
labels. They do not prove which acquisition implementation produced a given
export.

All-sample fractions describe software-output composition. Channel-eligible
fractions condition on different inputs and do not form a common six-part
composition. The residual breakdown sums to 32,660 samples. The 661 paired bins
contain 2,400 samples; seconds divided by sample count is not frame coverage.
Saved rater flags are not proof of monitored blinding or independently chosen
alignment. Approximately two hours per rater is labeling effort, not training.

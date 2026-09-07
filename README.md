# Pico 4 Pro Motion Export Quality Audit

Public derived-data and analysis package for the Sensors manuscript:

**A Quality Audit of Pico 4 Pro Motion Exports and Time-Based Rule Outputs**

This repository contains the de-identified evidence tables, analysis code,
reference audit, and publication figures used for the September 2026 revision.
It replaces the superseded August snapshot.

## Verified snapshot

- 34 anonymized study identifiers are represented in the participant-flow audit.
- 30 CSV exports were inventoried; 29 sessions passed the prespecified completeness gate.
- The retained data contain 45,560 exported samples.
- Timing compatibility separates 27 `ADB-like` sessions from 2
  `browser-compatible` sessions. These are post hoc timing labels, not verified
  acquisition routes.
- Five retained sessions have a frozen `accMag` channel and 28 have frozen
  Euler-angle fields.
- The annotation subset contains 661 one-second bins from 10 sessions.
- Three-class inter-rater agreement is 86.08% with Cohen's kappa 0.698
  (session-cluster bootstrap 95% CI 0.615-0.777).

Rule outputs are deterministic software outputs, not validated behavior labels.
The exported browser-compatible `gyro` fields are not claimed to be calibrated
angular-velocity measurements.

## Contents

| Path | Description |
|---|---|
| `scripts/rebuild_evidence.py` | Rebuilds session QC, time-window outputs, ablations, annotation agreement, and source hashes from authorized source files |
| `scripts/build_figures.py` | Recreates the five manuscript figures from committed evidence tables |
| `scripts/verify_references.py` | Rechecks bibliographic metadata and writes Zotero-compatible BibTeX/RIS exports |
| `evidence/` | De-identified participant-flow, session-QC, per-sample derived outputs, sensitivity analyses, annotation results, and source-manifest records |
| `figures/` | Five publication figures in PNG format |
| `references/` | Verified bibliography, claim audit summary, BibTeX, and RIS exports |
| `tests/` | Unit tests for timestamp windows, gap resets, mapping corrections, circular Euler ranges, transitions, and reference metadata |
| `qa/` | Machine-readable and human-readable evidence QA results |

See `DATA_DICTIONARY.md` for the role and statistical unit of each evidence
file.

## Install and verify

Python 3.12 or later is recommended.

```bash
python -m pip install -r requirements.txt
python -m pytest -q
python scripts/build_figures.py --output-root .
```

The committed evidence snapshot is independently checkable without access to
participant source files. A full evidence rebuild requires authorized local
access to the original CSV exports, dated reports, annotation archive, and
platform source:

```bash
python scripts/rebuild_evidence.py \
  --raw-root <raw-csv-directory> \
  --report-root <dated-report-directory> \
  --annotation-root <annotation-directory> \
  --platform-root <platform-source-directory> \
  --output-root .
```

The report directory must be supplied separately and is not inferred from the
CSV directory. Historical acquisition-time PICO OS, ADB client, browser engine,
and WebXR runtime versions were not retained; archived-package versions are
reported separately in `evidence/software_version_audit.csv`.

## Data-release boundary

The repository contains pseudonymous derived tables. It does **not** contain
participant names, consent-form images, identifiable video, questionnaires,
raw motion-export CSVs, or the original annotation files. Exact source files
remain controlled by the authors because their release requires separate
ethics, consent, and license review. Consequently, the committed tables support
verification of reported summaries but do not permit an independent rebuild
from raw participant data.

`evidence/sha256_source_manifest.csv` records portable paths, sizes, and hashes
for provenance checking; the source files themselves are not committed.

## QA

The public snapshot passed the evidence checks listed in
`qa/evidence_qa.md`. The release check also scans tracked content for local
absolute paths and common direct identifiers. See `qa/qa_summary.md`.

## License

No reuse license is granted at this time. Copyright remains with the authors
until the author group approves explicit code, data, and figure licenses.

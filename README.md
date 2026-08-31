# Pico 4 IMU Data Quality Control

Evidence and figure package for the manuscript:

**"Auditing a Pico 4 Motion-Sensing Pipeline for Seated 360-Degree VR: ADB IMU, Browser Pose, Rule-Based State Outputs, and Data Quality"**

Working package for the third revision dated 2026-08-27. The repository focuses on acquisition-route semantics, deterministic rule outputs, and channel-level quality control. It does not present the browser-compatible and ADB-like exports as one calibrated angular-IMU dataset.

## Contents

| Path | Description |
|---|---|
| `scripts/build_revision_package.py` | Release verifier and sole full-build entry point |
| `evidence/` | Session audit, route-stratified features, annotation agreement, confusion matrices, threshold sensitivity, and Crossref DOI audit |
| `figures/` | Six publication figures in PNG format |
| `qa/` | QA report and summary from the private full-build run |
| `交接索引_20260827.md` | Chinese evidence and handoff index |

## Verified snapshot

- 30 analysis exports and 46,402 mapped frames were audited.
- 29 sessions and 45,560 frames met the duration, frame-count, and required-field criteria.
- The primary comparable cohort contains 27 ADB-like sessions; two browser-compatible sessions are reported separately.
- Five retained sessions have a frozen accelerometer-magnitude channel at `accMag = 9.7335` while the exported gyro field remains active.
- Twenty-eight retained sessions have zero/frozen Euler output.
- Two annotation returns cover 661 common one-second bins from 10 participants; inter-rater Cohen's kappa is 0.593.
- All 28 selected DOI records passed Crossref lookup. A PASS confirms bibliographic identity, not the relevance of every citation to a manuscript claim.

## Verify this release

Python 3.10 or later is recommended.

```bash
python -m pip install -r requirements.txt
python scripts/build_revision_package.py --verify-release
```

The verifier checks the committed inventory, scans for workstation-path leakage, reconciles session and channel counts, confirms the 28 Crossref PASS records, and checks the six PNG figures.

## Full private build

The committed evidence and figures are a verification snapshot, not a raw-data release. Regenerating the manuscripts and evidence requires private inputs that are intentionally excluded from Git:

- the original analysis CSV exports and subject matrix;
- the platform source tree;
- both returned annotation directories and alignment table;
- the full reference-verification table; and
- the Sensors Word template.

Configure the private locations before running the full build:

```powershell
$env:PICO4_WORKSPACE = "C:/private/pico4-workspace"
$env:PICO4_REVISION_ROOT = "C:/private/revision-assets"
$env:SENSORS_TEMPLATE = "C:/private/Sensors_template.docx"
python scripts/build_revision_package.py --build
```

The full build writes generated Word files to the repository working directory. They remain excluded by `.gitignore`.

## Interpretation boundaries

- The browser-compatible CSV files do not retain the original `source` field, so the exact WebXR versus DeviceMotion branch cannot be recovered retrospectively.
- In the inspected WebXR branch, pose-derived translational velocity is written into compatibility fields named `gyro_x/y/z`; browser-compatible `gyroMag` must not be interpreted as validated angular velocity.
- The fixed 20-frame rule window represents different physical durations at the observed sampling rates.
- The annotation statistics are agreement references, not accuracy, F1, AUC, or frame-level ground-truth performance.
- The accelerometer freeze is an observed channel condition; the available evidence does not establish a WebXR buffer-stall root cause.

## Data availability

Raw frame-level IMU exports, videos, source annotation files, and direct participant-level source records are not included. Public data sharing remains subject to author confirmation, participant consent, and institutional requirements.

## License

No reuse license has been selected yet. Copyright remains with the authors. Add a license only after all authors approve the code and data-sharing terms.

# Pico 4 Pro Motion Export Quality Audit

Public derived-data and analysis package for the Sensors manuscript
**A Quality Audit of Pico 4 Pro Motion Exports and Time-Based Rule Outputs**.

This snapshot implements the 8 September 2026 scientific revision, published on
9 September. It supersedes the 7 September snapshot
`a55072a2ede03ff4d785b261e0997ad3995faffa`, which remains available in Git history.
The repository contains current derived evidence, analysis code, two main
figures and editable sources, tests, and the retained reference audit. It does
not contain the private manuscript-editing package.

The downloadable public reproduction package is available in
[Release v2026.09.08](https://github.com/U-uu-U/pico4-imu-data-quality/releases/tag/v2026.09.08).
Download `Pico4_IMU_Public_Reproduction_20260908.zip` and its `.sha256`
checksum file. The accompanying `.verification.json` records checks performed
on the isolated archive. See [RELEASE.md](RELEASE.md) for the exact public scope,
verification commands, and source-version relationship. This is a separate
public package, not the author-held manuscript revision ZIP.

## Verified findings

- Thirty-four distinct participants each took part once, as confirmed by the
  study author. Thirty CSV exports are available; the retrospective 60 s
  completeness criterion retains 29 sessions and 45,560 samples.
- The post hoc timing groups contain 27 ADB-like sessions and two
  browser-compatible sessions. They are not verified acquisition routes.
- Five retained accMag series and 28 Euler-field sets are session-wide constant.
- Matching long-gap resets in the 21-sample comparator gives 974/40,119 changed
  ADB-like outputs (2.428%) and 47/5,441 higher-rate outputs (0.864%). The older
  no-reset branch remains a separate comparison; adding resets changes 59 outputs.
- All 19 saved alignment candidates and both raters' anonymous return metadata
  are represented. S021 records a final 68 s offset after the 65 s automatic
  candidate; this establishes a saved adjustment, not timing accuracy.
- The 661 paired one-second bins cover 2,400 exported samples, or 5.27% of the
  retained samples. Inter-rater kappa is 0.698 (95% cluster CI 0.615-0.777).
- Before priority resolution, 3,073/45,560 samples satisfy multiple enabled
  conditions (6.74%). Output changes are not classification error rates.

Session and participant clusters coincide. Fractions pooled by sample count
are not elapsed-time exposure fractions. No group-level precision interval is
reported for the two higher-rate sessions. Deterministic outputs are not
validated behavior labels, and mapped gyro fields are not assumed to be
calibrated angular velocity.

## Contents

| Path | Description |
| --- | --- |
| `scripts/reanalyse_revision.py` | Current full source-reanalysis entry point, including all September additions |
| `scripts/rebuild_evidence.py` | Retained base analysis engine; used by the current entry point |
| `scripts/check_package.py` | Standard-library verification of packaged derivatives and file hashes |
| `scripts/build_public_reproduction.py` | Build and verify the public-only release ZIP from a clean committed snapshot |
| `scripts/build_figures.py` | Current two figures in PNG, SVG, and PDF formats |
| `scripts/verify_references.py` | Retained bibliographic verification and BibTeX/RIS export tooling |
| `study_metadata.json` | Public study facts needed to interpret participants, clusters, and labeling effort |
| `evidence/` | Pseudonymous quality, rule, sensitivity, annotation, and source-hash tables |
| `figures/` | Two current figures; superseded figures remain only in Git history |
| `references/` | Retained bibliography and reference audit |
| `tests/` | Base-analysis, matched-window, entry-point, and reference tests |
| `qa/` | Evidence checks, public snapshot QA, and the file-hash manifest |

See `DATA_DICTIONARY.md` for the unit and meaning of each evidence table.

## Verify without participant originals

Python 3.12 is supported. The derivative check and window tests need only the
standard library:

```sh
python -B -S scripts/check_package.py
python -B -S -m unittest discover -s tests -p 'test_gap_matched.py' -v
```

For all tests and figure regeneration:

```sh
python -m pip install -r requirements.txt
python -m pytest -q
python scripts/build_figures.py --output-root .
```

The manifest is `qa/public_release_sha256.csv`. It covers exact file bytes,
excluding generated QA reports and itself; `.gitattributes` prevents automatic
newline conversion during checkout. Regenerating figures or evidence can
change file hashes, including PDF metadata. After a verified intentional
rebuild, refresh the manifest with `python scripts/check_package.py --write-manifest`.

## Rebuild from controlled originals

Use the current entry point, not the base engine alone, to include the matched
window comparator, full candidate inventory, saved offsets, coverage, and
exact eligible denominators:

```sh
python scripts/reanalyse_revision.py \
  --raw-root <raw-csv-directory> \
  --report-root <dated-report-directory> \
  --annotation-root <annotation-directory> \
  --platform-root <platform-source-directory> \
  --output-root .
```

Reports must be supplied explicitly, even if they share the CSV directory.
The annotation archive includes both original rater-return directories, saved
alignment candidates, and archived interface tools. Historical video
cross-correlation is reconstructed from the saved log and source code, not
rerun; no new annotation or external synchronization validation is claimed.
Historical PICO OS, ADB, browser, and WebXR build records remain unavailable.

The published tables support independent arithmetic and software checks.
They cannot establish the provenance of inaccessible originals or replace a
source-level rebuild. The separate author-held package contains the Word
builders and private baselines; these are not prerequisites for public checks.

## Data release and license

Published study identifiers are pseudonyms. Raw motion CSVs, participant names,
consent forms, identifiable video, original rater returns, platform source,
internal author-confirmation records, reviewer correspondence, and private
Word baselines are not included. Source manifests use portable aliases and
hashes, not local absolute paths. Original data are available from the
corresponding author on reasonable request, subject to participant consent,
privacy protection, and institutional ethics requirements.

No reuse license is granted at this time. Copyright remains with the authors
until the author group approves explicit code, data, and figure licenses.

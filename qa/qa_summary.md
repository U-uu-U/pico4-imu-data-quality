# Public release QA

Status: PASS

Scientific revision: 2026-09-08. Public synchronization: 2026-09-09.

## Evidence reconciliation

- PASS: 34 distinct participants, each participating once, recorded in public study metadata
- PASS: 30 inventoried CSV exports and 29 retained sessions
- PASS: 45,560 retained exported samples
- PASS: exclusion set is S002, S003, S004, S012, and S016
- PASS: corrected S011, S013, and S014 export mapping
- PASS: timing-compatibility split is 27 ADB-like and 2 browser-compatible sessions
- PASS: 5 retained sessions with frozen `accMag`
- PASS: 28 retained sessions with frozen Euler fields
- PASS: 661 paired one-second bins across 10 sessions cover 2,400 samples
- PASS: all 19 alignment candidates and 20 anonymous return-footer records are included
- PASS: matched-reset 21-sample changes are 974 ADB-like and 47 higher-rate outputs
- PASS: adding gap resets changes 59 historical-branch outputs
- PASS: whole-output and eligible-channel denominators are separately checked
- PASS: 3,073/45,560 samples satisfy multiple enabled conditions (6.74%)
- PASS: main time-window outputs cover every retained row
- PASS: transition counts do not cross detected long-gap boundaries
- PASS: historical acquisition-time software versions remain marked as not retained

## Public-package checks

- PASS: no raw motion CSV, video, consent form, questionnaire, DOCX, render, or TIFF is tracked
- PASS: no local absolute workstation path was found in the release files
- PASS: no private author-confirmation file, internal editing log, or email-address pattern was found in the release files
- PASS: all committed evidence CSV paths are portable
- PASS: two current figures and their PNG/SVG/PDF sources are present
- PASS: regenerating both figures reproduces the released PNG pixels exactly
- PASS: all 30 current derived CSV tables and the evidence summary match the verified local revision after newline normalization
- PASS: 24 standard-library derived-evidence and exact-manifest checks
- PASS: 20 tests covering the base analysis, matched window, current entry point, manifest failures, and reference metadata

The 60 s completeness criterion is retrospective, not prespecified. The two
higher-rate sessions have no group-level bootstrap precision interval.
Participant and session clusters coincide; labeling effort is not training.

`public_release_sha256.csv` covers exact core file bytes and excludes all QA
reports and itself. Git checkout preserves those bytes using `.gitattributes`.
The retained base engine is byte-equivalent to the engine used in the local
reanalysis; the current entry point adds the September extensions. No new
scientific reanalysis or external experiment is claimed by this release pass.

Detailed evidence checks are recorded in `evidence_qa.csv` and
`evidence_qa.md`.

The private manuscript-editing package is not published. Minimal study facts
needed to interpret cluster units are in `study_metadata.json`; ethics
correspondence, author signoff records, and manuscript baselines remain local.
The prior reference audit and its unresolved semantic-review flags are retained;
this update does not claim a fresh online or full-text reference audit.

## Scope boundary

This is a public derived-data snapshot. The controlled source exports and
original annotation files are intentionally absent, so the source-level audit
cannot be rebuilt independently from this repository alone.

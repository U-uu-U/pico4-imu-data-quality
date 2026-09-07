# Public release QA

Status: PASS

Release date: 2026-09-07

## Evidence reconciliation

- PASS: 34 unique pseudonymous study identifiers in the flow audit
- PASS: 30 inventoried CSV exports and 29 retained sessions
- PASS: 45,560 retained exported samples
- PASS: exclusion set is S002, S003, S004, S012, and S016
- PASS: corrected S011, S013, and S014 export mapping
- PASS: timing-compatibility split is 27 ADB-like and 2 browser-compatible sessions
- PASS: 5 retained sessions with frozen `accMag`
- PASS: 28 retained sessions with frozen Euler fields
- PASS: 661 one-second annotation bins across 10 sessions
- PASS: main time-window outputs cover every retained row
- PASS: transition counts do not cross detected long-gap boundaries
- PASS: historical acquisition-time software versions remain marked as not retained

## Public-package checks

- PASS: no raw motion CSV, video, consent form, questionnaire, DOCX, render, or TIFF is tracked
- PASS: no local absolute workstation path was found in the release files
- PASS: no participant name, phone number, email address, WeChat identifier, or consent-form image was found
- PASS: all committed evidence CSV paths are portable
- PASS: five current PNG figures are present
- PASS: unit tests for evidence logic and reference metadata pass

Detailed evidence checks are recorded in `evidence_qa.csv` and
`evidence_qa.md`.

## Scope boundary

This is a public derived-data snapshot. The controlled source exports and
original annotation files are intentionally absent, so the source-level audit
cannot be rebuilt independently from this repository alone.

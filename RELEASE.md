# Public Reproduction Release

Release `v2026.09.08` provides the public derived-data reproduction package for
the 8 September 2026 Sensors scientific revision. It is published separately
from the private author-review package.

## Public Scope

The package contains the analysis entry point and base engine, derivative
checks, figure and reference tools, all current pseudonymous derived evidence,
two figures in PNG/SVG/PDF, reference-audit exports, tests, pinned or bounded
dependencies, the data dictionary, minimal study metadata, and public QA
records. `qa/archive_contents_sha256.csv` lists every packaged file and its
SHA-256, except the manifest itself.

It does not contain participant names, raw motion exports, consent or ethics
records, identifiable images or video, original rater returns, questionnaires,
acquisition-platform source, author-confirmation originals, reviewer
correspondence, Word builders, manuscript files or baselines, internal editing
logs, local previews, credentials, or runtime installations.

The package supports arithmetic checks of the published derivatives, automated
software tests, and regeneration of figures from those derivatives. A full
source-level rebuild still requires the controlled originals described in
`README.md`. No original video processing, new annotation, or external sensor
validation was performed for this packaging release.

## Version Identity

Scientific results remain those of commit
`23c30dc17887a19fb4de14d9d87c4b3330ba60df`, which is cited in the manuscript.
The release adds public packaging, documentation, and archive tests without
changing the scientific evidence or figures. The release tag identifies the
packaging commit; `release_metadata.json` inside the ZIP records both commits.
The earlier `v2026.09.07` release remains available as a historical version.

## Download and Verify

The release assets are:

- `Pico4_IMU_Public_Reproduction_20260908.zip`
- `Pico4_IMU_Public_Reproduction_20260908.zip.sha256`
- `Pico4_IMU_Public_Reproduction_20260908.verification.json`

Compare the ZIP hash with the adjacent checksum file before extraction. On
PowerShell, use:

```powershell
Get-FileHash Pico4_IMU_Public_Reproduction_20260908.zip -Algorithm SHA256
```

After extracting the ZIP into its own directory, run these commands there
with Python 3.12:

```sh
python -B -S scripts/check_package.py
python -B -S -m unittest discover -s tests -p 'test_gap_matched.py' -v
```

To run the full test suite and regenerate the figures:

```sh
python -m pip install -r requirements.txt
python -B -m pytest -q -p no:cacheprovider
python -B scripts/build_figures.py --output-root .
```

Figure regeneration can change PDF metadata and therefore file hashes. Keep
the downloaded archive unchanged as the release reference.

From a checkout or extracted copy, the archive verifier can also check every
ZIP member and run the standard-library checks in a temporary directory:

```sh
python -B -S scripts/build_public_reproduction.py --verify <path-to-release-zip>
```

## Maintainer Build

The builder requires Git and a clean committed checkout with a current
`qa/public_release_sha256.csv`. It checks the complete tracked file set against
the public package scope, takes file bytes from `git archive HEAD`, creates a
deterministic ZIP, and verifies it before writing the checksum and receipt.
Uncommitted working files and ignored local materials are never archive inputs.

```sh
python -B scripts/build_public_reproduction.py --all-tests
```

The three release assets are written to ignored `dist/`. The external receipt
records the archive hash and executed checks; it is not included in its own
archive. Temporary verification directories are removed automatically.

## Access and License

Public visibility does not change the existing reuse terms. No reuse license
is granted at this time; copyright remains with the authors. Controlled
original data remain available only from the corresponding author on
reasonable request, subject to participant consent, privacy protection, and
institutional ethics requirements. This release does not claim final author
signoff on the manuscript.

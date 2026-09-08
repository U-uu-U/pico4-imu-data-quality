"""Build a public-only, hash-verified ZIP from a clean committed snapshot."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import stat
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from check_package import ROOT, digest, manifest_matches, package_files, read

ARCHIVE_NAME = "Pico4_IMU_Public_Reproduction_20260908.zip"
TAG = "v2026.09.08"
SCIENTIFIC_COMMIT = "23c30dc17887a19fb4de14d9d87c4b3330ba60df"
MANIFEST = "qa/archive_contents_sha256.csv"
METADATA = "release_metadata.json"
QA_FILES = ("derived_qa.csv", "evidence_qa.csv", "evidence_qa.md",
            "extension_qa.csv", "public_release_sha256.csv", "qa_summary.md")


def safe_name(name):
    path = PurePosixPath(name)
    if (not name or path.is_absolute() or path.as_posix() != name
            or any(part in {".", ".."} for part in name.split("/"))
            or "\\" in name or ":" in name or "\x00" in name):
        raise ValueError(f"Nonportable archive path: {name!r}")


def write_archive(path, payload):
    if MANIFEST in payload:
        raise ValueError("Archive manifest is generated, not an input")
    for name in payload:
        safe_name(name)
    content = io.StringIO(newline="")
    writer = csv.DictWriter(content, fieldnames=["path", "sha256"], lineterminator="\n")
    writer.writeheader()
    writer.writerows({"path": name, "sha256": hashlib.sha256(data).hexdigest()}
                     for name, data in sorted(payload.items()))
    members = dict(payload, **{MANIFEST: content.getvalue().encode("utf-8")})
    with ZipFile(path, "w", ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(members.items()):
            info = ZipInfo(name, date_time=(2026, 9, 8, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, data, compress_type=ZIP_DEFLATED, compresslevel=9)


def checked_members(path):
    with ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("Duplicate archive members")
        for info in archive.infolist():
            safe_name(info.filename)
            mode = stat.S_IFMT(info.external_attr >> 16)
            if info.is_dir() or mode not in (0, stat.S_IFREG):
                raise ValueError(f"Nonregular archive member: {info.filename}")
        rows = list(csv.DictReader(io.StringIO(archive.read(MANIFEST).decode("utf-8"))))
        expected = {row["path"]: row["sha256"] for row in rows}
        if len(expected) != len(rows) or set(names) != set(expected) | {MANIFEST} or MANIFEST in expected:
            raise ValueError("Exact archive member manifest mismatch")
        for name, sha256 in expected.items():
            if hashlib.sha256(archive.read(name)).hexdigest() != sha256:
                raise ValueError(f"Archive hash mismatch: {name}")
        if archive.testzip() is not None:
            raise ValueError("ZIP integrity failure")
        metadata = json.loads(archive.read(METADATA))
    return {"entries": len(names), "member_hashes_checked": len(expected),
            "exact_member_hash_verification": "PASS", "zip_integrity": "PASS",
            "release_metadata": metadata}


def verify_archive(path, all_tests=False):
    result = checked_members(path)
    commands = [["-S", "scripts/check_package.py"],
                ["-S", "-m", "unittest", "discover", "-s", "tests",
                 "-p", "test_gap_matched.py", "-v"]]
    if all_tests:
        commands.append(["-m", "pytest", "-q", "-p", "no:cacheprovider"])
    results = []
    with tempfile.TemporaryDirectory(prefix="pico4_public_reproduction_") as temporary:
        with ZipFile(path) as archive:
            archive.extractall(temporary)
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1")
        env.pop("PYTHONPATH", None)
        for arguments in commands:
            run = subprocess.run([sys.executable, "-B", *arguments], cwd=temporary,
                                 env=env, capture_output=True, text=True,
                                 encoding="utf-8", timeout=120)
            record = {"arguments": arguments, "exit_code": run.returncode,
                      "stdout": run.stdout, "stderr": run.stderr}
            results.append(record)
            if run.returncode:
                raise RuntimeError(json.dumps(record))
    result.update({"isolated_checks": results, "temporary_extraction_removed": True})
    return result


def committed_payload(root=ROOT):
    def git(*arguments):
        return subprocess.check_output(["git", *arguments], cwd=root)

    if git("status", "--porcelain", "--untracked-files=no").strip():
        raise ValueError("Commit reviewed changes before building a public release")
    if not manifest_matches(read(root / "qa" / "public_release_sha256.csv"), root):
        raise ValueError("Public core manifest is stale")
    expected = {path.relative_to(root).as_posix() for path in package_files(root)}
    expected.update(f"qa/{name}" for name in QA_FILES)
    with ZipFile(io.BytesIO(git("archive", "--format=zip", "HEAD"))) as source:
        files = [info for info in source.infolist() if not info.is_dir()]
        if {info.filename for info in files} != expected or len(files) != len(expected):
            raise ValueError("Committed files differ from the public release scope")
        for info in files:
            if stat.S_IFMT(info.external_attr >> 16) not in (0, stat.S_IFREG):
                raise ValueError(f"Nonregular source member: {info.filename}")
        payload = {info.filename: source.read(info) for info in files}
    metadata = {
        "repository": "https://github.com/U-uu-U/pico4-imu-data-quality",
        "tag": TAG, "packaging_commit": git("rev-parse", "HEAD").decode().strip(),
        "scientific_commit": SCIENTIFIC_COMMIT, "scientific_revision_date": "2026-09-08",
        "scope": "Public analysis code, derived evidence, figures, references, tests, minimal study metadata, and public QA",
        "controlled_originals_included": False, "private_author_package_included": False,
        "reuse_license": "No reuse license granted; existing author-reserved terms retained",
    }
    payload[METADATA] = (json.dumps(metadata, indent=2) + "\n").encode("utf-8")
    return payload


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist")
    parser.add_argument("--verify", type=Path, help="Verify an existing ZIP without Git")
    parser.add_argument("--all-tests", action="store_true", help="Also run pytest in isolation")
    args = parser.parse_args()
    if args.verify:
        print(json.dumps(verify_archive(args.verify, args.all_tests), indent=2))
        return
    payload = committed_payload()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    target = args.output_dir / ARCHIVE_NAME
    staged = target.with_suffix(".zip.tmp")
    try:
        write_archive(staged, payload)
        receipt = verify_archive(staged, args.all_tests)
        staged.replace(target)
    finally:
        staged.unlink(missing_ok=True)
    receipt.update({"verified_at_utc": datetime.now(timezone.utc).isoformat(),
                    "archive": target.name, "sha256": digest(target),
                    "bytes": target.stat().st_size, "python_version": sys.version.split()[0]})
    target.with_suffix(".zip.sha256").write_text(
        f"{receipt['sha256']}  {target.name}\n", encoding="utf-8")
    target.with_suffix(".verification.json").write_text(
        json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()

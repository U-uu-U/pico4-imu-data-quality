import json
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile, ZipInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_public_reproduction as release


class PublicArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "public.zip"
        self.payload = {"README.md": b"Public fixture\n",
                        release.METADATA: json.dumps({"tag": release.TAG}).encode()}
        release.write_archive(self.path, self.payload)

    def rewrite(self, transform):
        with ZipFile(self.path) as archive:
            members = {name: archive.read(name) for name in archive.namelist()}
        transform(members)
        with ZipFile(self.path, "w") as archive:
            for name, data in members.items():
                archive.writestr(name, data)

    def test_deterministic_bytes_and_complete_manifest(self):
        other = self.path.with_name("second.zip")
        release.write_archive(other, dict(reversed(list(self.payload.items()))))
        self.assertEqual(self.path.read_bytes(), other.read_bytes())
        result = release.checked_members(self.path)
        self.assertEqual(result["entries"], 3)
        self.assertEqual(result["member_hashes_checked"], 2)

    def test_tampered_member_rejected(self):
        self.rewrite(lambda members: members.update({"README.md": b"changed"}))
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            release.checked_members(self.path)

    def test_extra_member_rejected(self):
        self.rewrite(lambda members: members.update({"unexpected.txt": b"extra"}))
        with self.assertRaisesRegex(ValueError, "member manifest mismatch"):
            release.checked_members(self.path)

    def test_missing_member_rejected(self):
        self.rewrite(lambda members: members.pop("README.md"))
        with self.assertRaisesRegex(ValueError, "member manifest mismatch"):
            release.checked_members(self.path)

    def test_duplicate_manifest_row_rejected(self):
        def duplicate(members):
            rows = members[release.MANIFEST].splitlines(keepends=True)
            members[release.MANIFEST] += rows[1]
        self.rewrite(duplicate)
        with self.assertRaisesRegex(ValueError, "member manifest mismatch"):
            release.checked_members(self.path)

    def test_traversal_rejected_by_writer_and_verifier(self):
        with self.assertRaisesRegex(ValueError, "Nonportable archive path"):
            release.write_archive(self.path, {"../outside.txt": b"no"})
        self.rewrite(lambda members: members.update({"../outside.txt": b"no"}))
        with self.assertRaisesRegex(ValueError, "Nonportable archive path"):
            release.checked_members(self.path)

    def test_symlink_rejected_before_extraction(self):
        with ZipFile(self.path, "a") as archive:
            info = ZipInfo("link")
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(info, "../outside.txt")
        with self.assertRaisesRegex(ValueError, "Nonregular archive member"):
            release.checked_members(self.path)


if __name__ == "__main__":
    unittest.main()

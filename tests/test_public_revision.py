import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import check_package
import reanalyse_revision


def test_current_entry_point_forwards_explicit_roots(tmp_path):
    paths = {name: tmp_path / name for name in ("raw", "report", "annotation", "platform", "output")}
    arguments = [part for name, path in paths.items() for part in (f"--{name}-root", str(path))]
    with patch.object(reanalyse_revision.subprocess, "run") as run, patch.object(reanalyse_revision, "extend") as extend:
        reanalyse_revision.main(arguments)
    command = run.call_args.args[0]
    assert Path(command[1]).name == "rebuild_evidence.py"
    for name, path in paths.items():
        assert command[command.index(f"--{name}-root") + 1] == str(path)
    assert run.call_args.kwargs == {"check": True}
    extend.assert_called_once_with(paths["raw"], paths["annotation"], paths["output"])


def test_current_entry_point_requires_report_root():
    with pytest.raises(SystemExit) as error:
        reanalyse_revision.main(["--raw-root", "raw", "--annotation-root", "annotation", "--platform-root", "platform"])
    assert error.value.code == 2


def test_manifest_rejects_missing_duplicate_and_changed_members(tmp_path):
    for name in check_package.CORE_FILES:
        (tmp_path / name).write_text("fixture\n", encoding="utf-8")
    manifest = [{"path": path.relative_to(tmp_path).as_posix(), "sha256": check_package.digest(path)}
                for path in check_package.package_files(tmp_path)]
    assert check_package.manifest_matches(manifest, tmp_path)
    assert not check_package.manifest_matches(manifest[:-1], tmp_path)
    assert not check_package.manifest_matches(manifest + manifest[:1], tmp_path)
    (tmp_path / "README.md").write_text("changed\n", encoding="utf-8")
    assert not check_package.manifest_matches(manifest, tmp_path)

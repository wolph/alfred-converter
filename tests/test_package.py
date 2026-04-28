import subprocess
import zipfile
from pathlib import Path
from shutil import copy2, copytree, ignore_patterns


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_INPUTS = (
    "Makefile",
    "converter",
    "icons",
    "icon.png",
    "info.plist",
    "poscUnits22.xml",
    "README.rst",
)


def copy_workflow_source(tmp_path):
    source_root = tmp_path / "source"
    source_root.mkdir()

    for name in WORKFLOW_INPUTS:
        source = REPO_ROOT / name
        destination = source_root / name
        if source.is_dir():
            copytree(
                source,
                destination,
                ignore=ignore_patterns(
                    "__pycache__",
                    "*.pyc",
                    "*.tmp",
                    "*.tmp.*",
                    ".DS_Store",
                    "units.pickle",
                ),
            )
        else:
            copy2(source, destination)

    return source_root


def test_workflow_archive_excludes_generated_artifacts(tmp_path):
    source_root = copy_workflow_source(tmp_path)
    (source_root / "compiled.pyc").write_bytes(b"")
    (source_root / "leak.tmp").write_text("")
    (source_root / "rates.tmp.json").write_text("")
    (source_root / "converter" / "__pycache__").mkdir()
    (source_root / "converter" / "__pycache__" / "main.pyc").write_bytes(b"")
    (source_root / "converter" / "compiled.pyc").write_bytes(b"")
    (source_root / "converter" / "units.pickle").write_bytes(b"")
    (source_root / "converter" / "leak.tmp").write_text("")
    (source_root / "converter" / "rates.tmp.json").write_text("")
    (source_root / "icons" / ".DS_Store").write_bytes(b"")
    outfile = tmp_path / "unit_converter.alfredworkflow"

    subprocess.run(
        ["make", f"OUTFILE={outfile}"],
        cwd=source_root,
        check=True,
    )

    with zipfile.ZipFile(outfile) as archive:
        names = set(archive.namelist())

    assert "info.plist" in names
    assert "converter/main.py" in names
    assert "poscUnits22.xml" in names
    assert all("__pycache__" not in name for name in names)
    assert all(not name.endswith(".pyc") for name in names)
    assert all(not name.endswith(".tmp") for name in names)
    assert all(".tmp." not in name for name in names)
    assert all(not name.endswith(".DS_Store") for name in names)
    assert all(not name.endswith("units.pickle") for name in names)
    assert "tests/test_calculations.py" not in names

import importlib.util
import plistlib
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "scripts" / "release_workflow.py"


def load_release_workflow():
    spec = importlib.util.spec_from_file_location(
        "release_workflow", MODULE_PATH
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_assign_tags_suffixes_duplicate_dates():
    release_workflow = load_release_workflow()
    versions = [
        release_workflow.WorkflowVersion(
            date="2021-03-20",
            commit="1" * 40,
            blob="a" * 40,
            subject="first workflow build",
        ),
        release_workflow.WorkflowVersion(
            date="2021-03-20",
            commit="2" * 40,
            blob="b" * 40,
            subject="second workflow build",
        ),
        release_workflow.WorkflowVersion(
            date="2021-04-04",
            commit="3" * 40,
            blob="c" * 40,
            subject="third workflow build",
        ),
    ]

    assert release_workflow.assign_tags(versions) == {
        versions[0]: "v2021.03.20",
        versions[1]: "v2021.03.20.2",
        versions[2]: "v2021.04.04",
    }


def test_unique_versions_keeps_first_commit_for_each_archive_blob():
    release_workflow = load_release_workflow()
    duplicate_blob = "a" * 40
    versions = [
        release_workflow.WorkflowVersion(
            date="2021-03-20",
            commit="1" * 40,
            blob=duplicate_blob,
            subject="first workflow build",
        ),
        release_workflow.WorkflowVersion(
            date="2021-03-21",
            commit="2" * 40,
            blob=duplicate_blob,
            subject="same archive later",
        ),
        release_workflow.WorkflowVersion(
            date="2021-03-22",
            commit="3" * 40,
            blob="c" * 40,
            subject="new archive",
        ),
    ]

    assert release_workflow.unique_versions(versions) == [
        versions[0],
        versions[2],
    ]


def test_update_info_plist_version_only_changes_top_level_version(tmp_path):
    release_workflow = load_release_workflow()
    plist_path = tmp_path / "info.plist"
    plist_path.write_bytes(
        plistlib.dumps(
            {
                "name": "Unit converter",
                "version": "",
                "objects": [
                    {
                        "config": {"version": "preserve nested version"},
                    }
                ],
            },
            sort_keys=False,
        )
    )

    release_workflow.update_info_plist_version(plist_path, "v2026.06.15")

    updated = plistlib.loads(plist_path.read_bytes())
    assert updated["version"] == "v2026.06.15"
    assert updated["objects"][0]["config"]["version"] == (
        "preserve nested version"
    )


def test_tracked_dirty_entries_ignore_untracked_files():
    release_workflow = load_release_workflow()
    status = "\n".join(
        [
            " M README.rst",
            "M  info.plist",
            "?? scratch.py",
            "?? .worktrees/release-automation/",
            "",
        ]
    )

    assert release_workflow.tracked_dirty_entries(status) == [
        " M README.rst",
        "M  info.plist",
    ]

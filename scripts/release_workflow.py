#!/usr/bin/env python3
"""Build and publish Alfred Converter workflow releases."""

from __future__ import annotations

import argparse
import dataclasses
import os
import plistlib
import re
import subprocess
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_FILE = "unit_converter.alfredworkflow"
VERSION_RE = re.compile(r"^v\d{4}\.\d{2}\.\d{2}(?:\.\d+)?$")


@dataclasses.dataclass(frozen=True)
class WorkflowVersion:
    date: str
    commit: str
    blob: str
    subject: str


def run_read(args, cwd=REPO_ROOT):
    result = subprocess.run(
        args,
        cwd=cwd,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout


def tracked_dirty_entries(status):
    return [
        line
        for line in status.splitlines()
        if line and not line.startswith("??")
    ]


def require_clean_tracked_tree():
    dirty = tracked_dirty_entries(
        run_read(["git", "status", "--porcelain"])
    )
    if dirty:
        raise SystemExit(
            "Tracked working tree changes must be committed first:\n"
            + "\n".join(dirty)
        )


def validate_version_tag(version):
    if not VERSION_RE.match(version):
        raise SystemExit(
            "Version must use date-tag format, e.g. v2026.06.15"
        )


def date_tag(date, count):
    base = "v" + date.replace("-", ".")
    if count == 1:
        return base
    return f"{base}.{count}"


def assign_tags(versions):
    counts = {}
    tags = {}
    for version in versions:
        counts[version.date] = counts.get(version.date, 0) + 1
        tags[version] = date_tag(version.date, counts[version.date])
    return tags


def unique_versions(versions):
    seen_blobs = set()
    unique = []
    for version in versions:
        if version.blob in seen_blobs:
            continue
        seen_blobs.add(version.blob)
        unique.append(version)
    return unique


def discover_workflow_versions():
    commits = run_read(
        ["git", "rev-list", "--reverse", "HEAD", "--", WORKFLOW_FILE]
    ).splitlines()
    versions = []
    for commit in commits:
        tree_line = run_read(
            ["git", "ls-tree", commit, WORKFLOW_FILE]
        ).strip()
        if not tree_line:
            continue
        blob = tree_line.split()[2]
        date = run_read(
            ["git", "show", "-s", "--format=%ad", "--date=short", commit]
        ).strip()
        subject = run_read(
            ["git", "show", "-s", "--format=%s", commit]
        ).strip()
        versions.append(
            WorkflowVersion(
                date=date,
                commit=commit,
                blob=blob,
                subject=subject,
            )
        )
    return unique_versions(versions)


def update_info_plist_version(path, version):
    with path.open("rb") as handle:
        info = plistlib.load(handle)
    info["version"] = version
    with path.open("wb") as handle:
        plistlib.dump(info, handle, sort_keys=False)


def command_text(args):
    return " ".join(subprocess.list2cmdline([str(arg)]) for arg in args)


class ReleaseCommands:
    def __init__(self, execute):
        self.execute = execute

    def write(self, args, **kwargs):
        if not self.execute:
            print("DRY-RUN:", command_text(args))
            return None
        return subprocess.run(args, cwd=REPO_ROOT, check=True, **kwargs)


def current_branch():
    return run_read(["git", "branch", "--show-current"]).strip()


def tag_commit(tag):
    result = subprocess.run(
        ["git", "rev-list", "-n", "1", tag],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode:
        return None
    return result.stdout.strip()


def release_exists(tag):
    result = subprocess.run(
        ["gh", "release", "view", tag, "--json", "tagName"],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.returncode == 0


def ensure_tag(commands, tag, commit):
    existing = tag_commit(tag)
    if existing:
        if existing != commit:
            raise SystemExit(
                f"Tag {tag} points at {existing}, expected {commit}"
            )
        print(f"Tag {tag} already exists at {commit}")
    else:
        commands.write(
            [
                "git",
                "tag",
                "-a",
                tag,
                commit,
                "-m",
                f"Alfred Converter {tag}",
            ]
        )
    commands.write(["git", "push", "origin", tag])


def backfill_notes(version, tag):
    return (
        "Historical Alfred workflow archive backfill.\n\n"
        f"- Tag: {tag}\n"
        f"- Date: {version.date}\n"
        f"- Commit: {version.commit}\n"
        f"- Source change: {version.subject}\n"
    )


def current_release_notes(version):
    return (
        "## Highlights\n\n"
        "- Added cached currency conversion with daily rates.\n"
        "- Added currency icons, configurable default targets, and "
        "`currency-update`.\n"
        "- Improved conversion ordering by result magnitude.\n"
        "- Filtered rare time units that produced awkward results.\n"
        "- Documented `log()` as natural logarithm and `log10()` for "
        "base-10 logarithms.\n\n"
        f"Workflow version: `{version}`\n"
    )


def extract_workflow_archive(commit, destination):
    with destination.open("wb") as handle:
        subprocess.run(
            ["git", "show", f"{commit}:{WORKFLOW_FILE}"],
            cwd=REPO_ROOT,
            check=True,
            stdout=handle,
        )


def create_release(commands, tag, title, notes, asset, latest):
    if release_exists(tag):
        print(f"Release {tag} already exists")
        return
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", suffix=".md", delete=False
    ) as handle:
        handle.write(notes)
        notes_path = handle.name
    try:
        args = [
            "gh",
            "release",
            "create",
            tag,
            str(asset),
            "--title",
            title,
            "--notes-file",
            notes_path,
            "--verify-tag",
        ]
        args.append("--latest" if latest else "--latest=false")
        commands.write(args)
    finally:
        with contextlib_suppress_file_not_found():
            os.unlink(notes_path)


class contextlib_suppress_file_not_found:
    def __enter__(self):
        return None

    def __exit__(self, exc_type, exc, _traceback):
        return exc_type is FileNotFoundError


def backfill(args):
    commands = ReleaseCommands(args.execute)
    if args.execute:
        commands.write(["git", "fetch", "--tags", "origin"])
    versions = discover_workflow_versions()
    tags = assign_tags(versions)
    print(f"Workflow versions: {len(versions)}")
    for version in versions:
        tag = tags[version]
        ensure_tag(commands, tag, version.commit)
        if args.execute:
            with tempfile.TemporaryDirectory() as tmp_dir:
                asset = Path(tmp_dir) / WORKFLOW_FILE
                extract_workflow_archive(version.commit, asset)
                create_release(
                    commands,
                    tag,
                    f"Alfred Converter {tag}",
                    backfill_notes(version, tag),
                    asset,
                    latest=False,
                )
        else:
            print(
                "DRY-RUN: extract",
                f"{version.commit}:{WORKFLOW_FILE}",
                "and create release",
                tag,
            )


def run_verification(commands):
    commands.write(["python", "-m", "pytest", "-q"])
    commands.write(["python", "-m", "flake8", "converter", "tests", "scripts"])


def publish_current(args):
    validate_version_tag(args.version)
    commands = ReleaseCommands(args.execute)
    branch = current_branch()
    if args.execute and branch != "master":
        raise SystemExit("publish-current must run from master")
    if not args.execute:
        print(f"Current branch: {branch}")
        print(f"DRY-RUN: update info.plist version to {args.version}")
        commands.write(["make"])
        run_verification(commands)
        commands.write(["git", "add", "info.plist", WORKFLOW_FILE])
        commands.write(
            ["git", "commit", "-m", f"chore: release {args.version}"]
        )
        commands.write(["git", "push", "origin", "HEAD:master"])
        print(f"DRY-RUN: tag HEAD as {args.version}")
        print(f"DRY-RUN: create latest release {args.version}")
        return

    require_clean_tracked_tree()
    update_info_plist_version(REPO_ROOT / "info.plist", args.version)
    commands.write(["make"])
    run_verification(commands)
    commands.write(["git", "add", "info.plist", WORKFLOW_FILE])
    commands.write(["git", "commit", "-m", f"chore: release {args.version}"])
    commit = run_read(["git", "rev-parse", "HEAD"]).strip()
    commands.write(["git", "push", "origin", "HEAD:master"])
    ensure_tag(commands, args.version, commit)
    create_release(
        commands,
        args.version,
        f"Alfred Converter {args.version}",
        current_release_notes(args.version),
        REPO_ROOT / WORKFLOW_FILE,
        latest=True,
    )


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description="Publish Alfred Converter workflow releases"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    backfill_parser = subparsers.add_parser(
        "backfill",
        help="Backfill releases for historical workflow archives",
    )
    backfill_parser.add_argument(
        "--execute",
        action="store_true",
        help="create tags and releases instead of printing a dry-run",
    )
    backfill_parser.set_defaults(func=backfill)

    current_parser = subparsers.add_parser(
        "publish-current",
        help="Build, tag, and publish the current workflow release",
    )
    current_parser.add_argument("version")
    current_parser.add_argument(
        "--execute",
        action="store_true",
        help="commit, push, tag, and release instead of printing a dry-run",
    )
    current_parser.set_defaults(func=publish_current)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv or sys.argv[1:])
    args.func(args)


if __name__ == "__main__":
    main()

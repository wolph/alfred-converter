# Release process

Releases are published with `scripts/release_workflow.py`. The script uses
date-based tags such as `v2026.06.15`; historical same-day workflow builds get
deterministic suffixes such as `v2021.03.20.2`.

Run dry-runs first:

```bash
python scripts/release_workflow.py publish-current v2026.06.15
python scripts/release_workflow.py backfill
```

Publish the current workflow from `master`:

```bash
python scripts/release_workflow.py publish-current v2026.06.15 --execute
```

This command requires a clean tracked working tree, updates the top-level
`info.plist` workflow version, rebuilds `unit_converter.alfredworkflow`, runs
the test and lint gates, commits the release artifact, pushes `master`, creates
the annotated tag, and publishes the GitHub release with the workflow asset.

Backfill historical workflow assets:

```bash
python scripts/release_workflow.py backfill --execute
```

Backfill discovers every unique historical tracked version of
`unit_converter.alfredworkflow`, extracts the archived file from the matching
commit, creates an annotated tag at that commit, and publishes a non-latest
GitHub release with the extracted workflow. Existing matching tags and releases
are skipped; a tag that already points at a different commit aborts the run.

# Alfred Converter Modernization Design

Date: 2026-04-26

## Purpose

Modernize the Alfred Unit Converter workflow while preserving broad runtime
compatibility. The release targets Python 3.8+ and current Alfred workflow
expectations, fixes the currently open issues, and incorporates the currently
open pull requests.

## Scope

This release includes:

- Issue #1: add currency conversion.
- Issue #57: keep `log()` as natural logarithm and document `log10()` for
  base-10 expectations.
- PR #58: sort conversion results by useful result magnitude.
- PR #59: hide rarely useful time units by default.
- Workflow modernization: JSON Script Filter output, cleaner archive packaging,
  updated Python tooling, updated tests, and refreshed docs.

This release does not rewrite the converter engine or replace the POSC unit
data source. Refactoring is limited to boundaries needed for the changes above.

## Runtime Compatibility

The supported Python baseline is 3.8+. The workflow must avoid syntax and
standard-library behavior that requires newer Python versions. Test and lint
configuration must reflect the 3.8+ target instead of the current obsolete
Python 2-era configuration.

## Architecture

The workflow keeps the existing unit and math conversion path as the primary
synchronous path:

```text
Alfred query -> command routing -> Units.convert -> output renderer
```

Currency conversion is a separate subsystem:

```text
Alfred currency query -> currency parser -> cache lookup -> output renderer
                                      -> optional background refresh
```

Normal math and unit conversions must not instantiate currency fetching logic,
acquire currency locks, read currency cache files, or perform network I/O.

The output layer must be centralized behind a small result model and Alfred
JSON renderer. Unit conversion and currency conversion must both produce the
same result objects so command routing remains simple and tests can assert the
output shape directly.

## Currency Conversion

Currency conversion supports queries such as:

- `2000 isk eur`
- `2000 isk to eur`
- `2000 isk in eur`

The rate source is the free daily JSON data from
`fawazahmed0/exchange-api`. The primary URL pattern is
`https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/{currency}.json`.
The fallback URL pattern is
`https://latest.currency-api.pages.dev/v1/currencies/{currency}.json`.

Currency conversion uses cached data only during Script Filter queries:

- If cache is fresh, return the conversion immediately.
- On the first currency use of a new rate day, return the stale conversion
  immediately, label it with the rate date, and start a background refresh.
- If no cache exists, return a non-error Alfred item explaining that rates are
  updating and start a background refresh.
- If cache is corrupt, ignore or rotate it, return the same "rates updating"
  response, and start a background refresh.

The workflow also provides a manual update command, `currency-update`, which
runs the update synchronously because the user explicitly requested it. The
command reports success, source date, number of currencies, or a failure
message.

## Stampede Protection

Automatic refresh must be guarded by a lock in Alfred's workflow cache
directory. The lock must use an atomic operation, such as creating a lock
directory, so concurrent Alfred invocations cannot all start update jobs.

The lock records enough metadata to detect stale locks. If an update process
crashes, a later invocation can recover after the configured lock timeout.

Background refresh is opportunistic. Failure to start or complete a refresh
must not break regular conversions or block Alfred results.

## Sorting And Unit Filtering

PR #58 must be integrated as a tested behavior: conversion results are sorted
to surface values closest to a useful magnitude, with identity conversions and
invalid sort inputs placed behind more useful conversions.

PR #59 must be integrated as a tested default filter: rarely useful time
annotations such as `cs`, `hs`, and `100ka` must not appear in normal
conversion results.

Sorting must use Alfred JSON's `skipknowledge` behavior for result sets where
manual order is important. Stable `uid` values remain present so selected items
can still be copied and identified consistently. The workflow must emit a
useful default order for first use and for users who clear Alfred knowledge.

## Math Behavior And Documentation

`log()` remains the natural logarithm, matching Python and common scientific
calculator behavior. `ln()` remains an alias for natural logarithm. Documentation
and examples must explicitly mention `log10()` when users expect base-10
logarithms. Issue #57 is resolved by documentation and tests that prevent a
regression in the existing behavior.

## Alfred Workflow Modernization

The Script Filter output must move from legacy XML to Alfred JSON. Result
items must include the fields needed for copy-to-clipboard behavior, icons,
validity, stable identifiers, and subtitles.

The workflow must use Alfred-provided cache/data locations where available,
especially `alfred_workflow_cache` for currency cache and locks. It may fall
back to a local cache path only when running outside Alfred tests or development
commands.

The packaged `.alfredworkflow` archive must include only source code,
workflow metadata, icons, static unit data, and README content needed at
runtime. It must exclude generated Python artifacts, `__pycache__`, `.pyc`,
temporary files, coverage output, local caches, and test-only files.

## Error Handling

Network failures never affect normal unit or math conversion.

Currency failures are reported as Alfred items only for currency queries or the
manual update command. Existing stale cache remains usable. Missing or corrupt
cache returns a clear updating/unavailable item and triggers a guarded refresh.

Unexpected exceptions in Script Filter routing must still produce a valid
Alfred response instead of malformed output.

## Testing Strategy

Implementation must use TDD. Start with failing tests before production code
for each behavior slice:

- Currency query parsing.
- Fresh cache conversion.
- Stale cache fallback plus background refresh trigger.
- Missing cache response plus background refresh trigger.
- Manual `currency-update` success and failure output.
- Stampede protection preventing concurrent auto-refresh launches.
- Regular unit/math conversions do not touch currency cache, locks, or network.
- Alfred JSON output shape.
- Magnitude sorting from PR #58.
- Rare time unit filtering from PR #59.
- `log()`, `ln()`, and `log10()` documented behavior.
- Workflow archive excludes generated artifacts.

Network tests must mock HTTP access. Background refresh tests must mock process
launching or isolate updater functions so tests remain deterministic.

## Documentation

README and Alfred workflow readme content must describe:

- Python 3.8+ support.
- Example unit, math, and currency queries.
- The `currency-update` command.
- Daily cache behavior and offline/stale-rate behavior.
- `log()` as natural log and `log10()` as base-10 log.
- Relevant workflow configuration variables.

## References

- Alfred JSON Script Filter documentation:
  https://www.alfredapp.com/help/workflows/inputs/script-filter/json/
- Alfred workflow script environment variables:
  https://www.alfredapp.com/help/workflows/script-environment-variables/
- Exchange API project:
  https://github.com/fawazahmed0/exchange-api

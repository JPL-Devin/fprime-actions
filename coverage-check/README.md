# nasa/fprime-actions/coverage-check

Composite action that compares the per-module + global gcovr coverage
produced by [`coverage-common`](../coverage-common/) (or
[`coverage-integration-common`](../coverage-integration-common/)) on a
**pull request** against the matching baseline branch
(`coverage/<base_ref>`) and **uploads the resulting comment body as a
workflow artifact**.

A companion [`coverage-comment`](../coverage-comment/) action,
triggered from a `workflow_run` job, downloads the artifact and posts
the sticky PR comment. This two-stage split is the GitHub-recommended
pattern for commenting on pull requests opened from forks, since
GitHub strips write permissions from `GITHUB_TOKEN` on fork-triggered
`pull_request` events.

This action never pushes to any branch and never writes to the pull
request. Pair it with [`coverage-update`](../coverage-update/) for the
push side and [`coverage-comment`](../coverage-comment/) for the
comment-posting side.

## Prerequisites

The caller must have:

1. Generated and built the UT cache (for unit test coverage) or built with
   coverage flags and run integration tests (for integration coverage).
2. Generated coverage with `coverage-common` or
   `coverage-integration-common` &mdash; pass its `modules-jsonl` output
   into this action.

### Unit test coverage example

```yaml
- uses: nasa/fprime-actions/run-unit-tests@devel
  with: { run-check: 'false', jobs: random }
- uses: nasa/fprime-actions/coverage-common@devel
  id: cov
- uses: nasa/fprime-actions/coverage-check@devel
  with:
    modules-jsonl: ${{ steps.cov.outputs.modules-jsonl }}
    coverage-kind: ut
```

### Integration coverage example

```yaml
- uses: nasa/fprime-actions/coverage-integration-common@devel
  id: cov
  with:
    build-cache: build-fprime-automatic-native-coverage
- uses: nasa/fprime-actions/coverage-check@devel
  with:
    modules-jsonl: ${{ steps.cov.outputs.modules-jsonl }}
    coverage-kind: integration
```

gcovr is provided by `fprime-tools`'s pip dependencies (via the `setup`
action).

## Required permissions

```yaml
permissions:
  contents: read
```

`pull-requests: write` is **not** required here &mdash; the comment is
posted by the companion `coverage-comment` workflow, which runs on
`workflow_run` and is the only stage that needs write permissions.

## What it does

1. Fetches the baseline branch `<baseline-branch-prefix>/<base_ref>` (e.g.
   `coverage/devel`). If the branch does not exist yet, the PR comment
   says so and no regressions are flagged.
2. Computes per-module line/function/branch deltas (using outputs produced by
   `coverage-common` or `coverage-integration-common`) and writes a markdown
   comment with the worst regressions first. The header shows whether this
   is a unit test or integration coverage report.
3. Uploads `comment.md`, `regressions.json`, `pr-number.txt`, and
   `comment-marker.txt` as a workflow artifact named `artifact-name`
   for the companion `coverage-comment` workflow to consume.
4. Writes the comment body to the job step summary so reviewers can
   still see the data on the Actions run page even if the comment
   workflow has not yet been deployed.

## Inputs

| Input                      | Default                              | Description                                                                                          |
|----------------------------|--------------------------------------|------------------------------------------------------------------------------------------------------|
| `working-directory`        | `.`                                  | Directory the coverage outputs were produced in (should match `coverage-common`).                    |
| `modules-jsonl`            | (required)                           | Path to the JSON-Lines file produced by `coverage-common` (`modules-jsonl` output).                  |
| `coverage-kind`            | `ut`                                 | Coverage kind: `ut` (unit test) or `integration`. Controls baseline subdirectory and comment marker. |
| `baseline-branch-prefix`   | `coverage`                           | Prefix applied to `<base_ref>` to form the baseline branch (`<prefix>/<base_ref>`).                  |
| `regression-threshold`     | `0.5`                                | Percentage points of line-coverage drop tolerated per module.                                         |
| `fail-on-regression`       | `false`                              | If `true`, the action exits non-zero when any module regresses beyond the threshold.                 |
| `comment-marker`           | (auto from kind)                     | Hidden HTML marker used to find and edit the sticky PR comment. Auto: `<!-- fprime-coverage-comment -->` for ut, `<!-- fprime-integration-coverage-comment -->` for integration. |
| `artifact-name`            | (auto from kind)                     | Workflow-artifact name. Auto: `fprime-coverage-comment` for ut, `fprime-integration-coverage-comment` for integration. |
| `artifact-retention-days`  | `7`                                  | Days to retain the uploaded artifact (max 90).                                                       |

## Outputs

| Output                  | Description                                              |
|-------------------------|----------------------------------------------------------|
| `comment-path`          | Path to the markdown PR comment.                         |
| `regressions-json-path` | Path to a JSON list of regressing modules.               |

## Usage

### Unit test coverage (PR side)

```yaml
name: "Coverage Check"
on:
  pull_request:
    branches: [devel, release/**]

permissions:
  contents: read

jobs:
  coverage:
    runs-on: ubuntu-24.04
    timeout-minutes: 90
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0, submodules: true }
      - uses: nasa/fprime-actions/setup@devel
      - uses: nasa/fprime-actions/run-unit-tests@devel
        with: { run-check: 'false', jobs: random }
      - uses: nasa/fprime-actions/coverage-common@devel
        id: cov
      - uses: nasa/fprime-actions/coverage-check@devel
        with:
          modules-jsonl: ${{ steps.cov.outputs.modules-jsonl }}
          coverage-kind: ut
```

### Integration coverage (PR side)

```yaml
      # ... (after building with coverage flags and running integration tests)
      - uses: nasa/fprime-actions/coverage-integration-common@devel
        id: intcov
        with:
          build-cache: build-fprime-automatic-native-coverage
      - uses: nasa/fprime-actions/coverage-check@devel
        with:
          modules-jsonl: ${{ steps.intcov.outputs.modules-jsonl }}
          coverage-kind: integration
```

Both UT and integration checks use **separate comment markers**, so their
sticky PR comments do not collide.

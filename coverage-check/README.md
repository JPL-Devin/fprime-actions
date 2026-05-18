# nasa/fprime-actions/coverage-check

Composite action that generates per-module + global gcovr coverage on a
**pull request** and compares it against the matching baseline branch
(`coverage/<base_ref>`). Posts a sticky per-module delta comment to the
PR.

This action never pushes to any branch. Pair it with
[`coverage-update`](../coverage-update/) for the push side.

## Prerequisites

The caller must have already generated and built the UT cache. Use
`run-unit-tests` with `run-check: 'false'` before calling this action:

```yaml
- uses: nasa/fprime-actions/run-unit-tests@devel
  with:
    run-check: 'false'
    jobs: random
- uses: nasa/fprime-actions/coverage-check@devel
```

gcovr is provided by `fprime-tools`'s pip dependencies (via the `setup`
action).

## Required permissions

```yaml
permissions:
  contents: read
  pull-requests: write
```

`pull-requests: write` is needed to post or update the sticky comment.

## What it does

1. Calls [`coverage-common`](../coverage-common/) to discover modules and
   generate global + per-module coverage.
2. Fetches the baseline branch `<baseline-branch-prefix>/<base_ref>` (e.g.
   `coverage/devel`). If the branch does not exist yet, the PR comment
   says so and no regressions are flagged.
3. Computes per-module line/branch deltas and writes a markdown comment
   with the worst regressions first.
4. Posts the comment to the PR. If a previous comment matching
   `comment-marker` exists, it is updated in place; otherwise a new
   comment is created.

## Inputs

| Input                    | Default                              | Description                                                                                   |
|--------------------------|--------------------------------------|-----------------------------------------------------------------------------------------------|
| `working-directory`      | `.`                                  | Directory to run `fprime-util` from.                                                           |
| `target-platform`        | `""`                                 | Target platform/toolchain passed to `fprime-util`.                                             |
| `jobs`                   | `""`                                 | Parallel job count for check. `random` picks 1-32; empty omits `-j`.                          |
| `baseline-branch-prefix` | `coverage`                           | Prefix applied to `<base_ref>` to form the baseline branch (`<prefix>/<base_ref>`).           |
| `coverage-subdirectory`  | `coverage`                           | Subdirectory inside each module's baseline-branch entry. Set to `""` to flatten.              |
| `regression-threshold`   | `0.5`                                | Percentage points of line-coverage drop tolerated per module.                                  |
| `fail-on-regression`     | `false`                              | If `true`, the action exits non-zero when any module regresses beyond the threshold.          |
| `comment-marker`         | `<!-- fprime-coverage-comment -->`   | Hidden HTML marker used to find and edit the sticky PR comment.                               |

## Outputs

| Output                  | Description                                              |
|-------------------------|----------------------------------------------------------|
| `comment-path`          | Path to the markdown PR comment.                         |
| `regressions-json-path` | Path to a JSON list of regressing modules.               |

## Usage

```yaml
name: "Coverage"
on:
  pull_request:
    branches: [devel, release/**]

jobs:
  coverage-check:
    runs-on: ubuntu-22.04
    permissions:
      contents: read
      pull-requests: write
    timeout-minutes: 90
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0, submodules: true }
      - uses: nasa/fprime-actions/setup@devel
      - uses: nasa/fprime-actions/run-unit-tests@devel
        with: { run-check: 'false', jobs: random }
      - uses: nasa/fprime-actions/coverage-check@devel
```

To enable the regression gate later, flip a single input:

```yaml
      - uses: nasa/fprime-actions/coverage-check@devel
        with:
          fail-on-regression: 'true'
```

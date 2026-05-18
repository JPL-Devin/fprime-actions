# nasa/fprime-actions/coverage-update

Composite action that generates per-module + global gcovr coverage on a
**push** event (or `workflow_dispatch`) and writes the results to a
per-base-branch orphan branch named `<baseline-branch-prefix>/<ref-name>`
(e.g. `coverage/devel`, `coverage/release/v4.2.0`, `coverage/v4.2.0`).

This action does **not** comment on pull requests. Pair it with
[`coverage-check`](../coverage-check/) for the PR side.

## Prerequisites

The caller must have already generated and built the UT cache. Use
`run-unit-tests` with `run-check: 'false'` before calling this action:

```yaml
- uses: nasa/fprime-actions/run-unit-tests@devel
  with:
    run-check: 'false'
    jobs: random
- uses: nasa/fprime-actions/coverage-update@devel
```

gcovr is provided by `fprime-tools`'s pip dependencies (via the `setup`
action).

## Required permissions

```yaml
permissions:
  contents: write
```

`contents: write` is needed to push commits to the baseline branch.

## What it does

1. Calls [`coverage-common`](../coverage-common/) to discover modules and
   generate global + per-module coverage.
2. Resolves the baseline branch as `<baseline-branch-prefix>/<ref-name>`
   from `github.ref_name` (tags use their tag name verbatim).
3. Fetches or creates the baseline branch as a worktree (orphan branch on
   first push).
4. Mirrors the per-module + global outputs into the worktree, writes
   placeholder pages for modules with no coverage, generates a top-level
   folder-tree `index.html` and a machine-readable `catalog.json`.
5. Commits and pushes if there are changes.

Forks are skipped automatically (no push from forks).

## Inputs

| Input                    | Default      | Description                                                                                          |
|--------------------------|--------------|------------------------------------------------------------------------------------------------------|
| `working-directory`      | `.`          | Directory to run `fprime-util` from.                                                                  |
| `target-platform`        | `""`         | Target platform/toolchain passed to `fprime-util`.                                                    |
| `jobs`                   | `""`         | Parallel job count for check. `random` picks 1-32; empty omits `-j`.                                  |
| `baseline-branch-prefix` | `coverage`   | Prefix applied to `<ref-name>` to form the baseline branch (`<prefix>/<ref-name>`).                  |
| `coverage-subdirectory`  | `coverage`   | Subdirectory inside each module's baseline-branch entry. Set to `""` to flatten the shadow folder.   |

## Outputs

| Output            | Description                                                       |
|-------------------|-------------------------------------------------------------------|
| `catalog-path`    | Absolute path to the generated `catalog.json`.                    |
| `baseline-branch` | Name of the baseline branch written (e.g. `coverage/devel`).      |

## Baseline branch layout (default `coverage-subdirectory: "coverage"`)

```
<prefix>/<ref-name>            (orphan branch, e.g. coverage/devel)
├── catalog.json                       machine-readable module list
├── index.html                         folder-tree catalog
├── coverage/                          global --all run
│   ├── summary.json
│   ├── coverage-all.html              gcovr's native global report
│   └── coverage.*.html                gcovr per-source detail siblings
├── Svc/CmdDispatcher/coverage/
│   ├── summary.json
│   ├── index.html                     was coverage.html
│   └── coverage.*.html
├── Drv/LinuxGpio/coverage/
│   └── index.html                     placeholder: "no coverage recorded"
└── ...                                one entry per discovered module
```

With `coverage-subdirectory: ""` the per-module artifacts land directly
in the module's directory (no shadow folder); the global run still lives
in a top-level `coverage/` because that's where gcovr writes it.

## `catalog.json` schema

See [`coverage-common/README.md`](../coverage-common/README.md) and
`scripts/catalog.py`.

## Usage

```yaml
name: "Coverage"
on:
  push:
    branches: [devel, release/**]
    tags:     ['v*']
  workflow_dispatch:

jobs:
  coverage-update:
    runs-on: ubuntu-22.04
    permissions:
      contents: write
    timeout-minutes: 90
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0, submodules: true }
      - uses: nasa/fprime-actions/setup@devel
      - uses: nasa/fprime-actions/run-unit-tests@devel
        with: { run-check: 'false', jobs: random }
      - uses: nasa/fprime-actions/coverage-update@devel
```

## Bootstrapping

The first time the workflow runs against a new branch or tag, the
baseline branch does not yet exist. This action creates it on demand
(as an orphan branch).

To seed manually before opening any PRs, run the workflow via
`workflow_dispatch` on the base branch (e.g. `devel`).

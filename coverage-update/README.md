# nasa/fprime-actions/coverage-update

Composite action that mirrors coverage outputs onto the
`coverage/<ref>` orphan branch.  Call `coverage-common` (for unit test
coverage) or `coverage-integration-common` (for integration test
coverage) first to produce the outputs, then pass its `modules-jsonl`
output into this action.

This action only writes the `coverage-<kind>/` subdirectories for the
current kind.  The other kind's data is **preserved** on the branch, so
both unit test and integration coverage share the same baseline branch.
The combined landing page (`index.html`) always includes both.

This action does **not** comment on pull requests. Pair it with
[`coverage-check`](../coverage-check/) for the PR side.

## Prerequisites

The caller must have generated coverage with `coverage-common` or
`coverage-integration-common` before calling this action.

### Unit test coverage

```yaml
- uses: nasa/fprime-actions/run-unit-tests@devel
  with: { run-check: 'false', jobs: random }
- uses: nasa/fprime-actions/coverage-common@devel
  id: cov
- uses: nasa/fprime-actions/coverage-update@devel
  with:
    modules-jsonl: ${{ steps.cov.outputs.modules-jsonl }}
    coverage-kind: ut
```

### Integration coverage

```yaml
# ... (after building with coverage flags and running integration tests)
- uses: nasa/fprime-actions/coverage-integration-common@devel
  id: intcov
  with:
    build-cache: build-fprime-automatic-native-coverage
- uses: nasa/fprime-actions/coverage-update@devel
  with:
    modules-jsonl: ${{ steps.intcov.outputs.modules-jsonl }}
    coverage-kind: integration
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

1. Resolves the baseline branch as `<baseline-branch-prefix>/<ref-name>`
   from `github.ref_name` (tags use their tag name verbatim).
2. Fetches or creates the baseline branch as a worktree (orphan branch on
   first push).
3. Mirrors the per-module + global outputs for the current `coverage-kind`
   into the worktree (`coverage-ut/` or `coverage-integration/`
   subdirectories). The other kind's data is untouched.
4. Regenerates the combined landing page (`index.html`) and machine-readable
   `catalog.json` — both reflect whatever UT and integration data are
   present on the branch.
5. Commits and pushes if there are changes.

Forks are skipped automatically (no push from forks).

## Inputs

| Input                    | Default      | Description                                                                                          |
|--------------------------|--------------|------------------------------------------------------------------------------------------------------|
| `working-directory`      | `.`          | Directory the coverage outputs were produced in (should match `coverage-common`).                     |
| `modules-jsonl`          | (required)   | Path to the JSON-Lines file produced by `coverage-common` (`modules-jsonl` output).                  |
| `coverage-kind`          | `ut`         | Coverage kind: `ut` (unit test) or `integration`. Controls the subdirectory name on the baseline branch. |
| `baseline-branch-prefix` | `coverage`   | Prefix applied to `<ref-name>` to form the baseline branch (`<prefix>/<ref-name>`).                  |
| `ref`                    | `github.ref_name` | The git ref whose coverage is being recorded (e.g. `devel`).                                   |

## Baseline branch layout

```
<prefix>/<ref-name>                  (orphan branch, e.g. coverage/devel)
├── catalog.json                     machine-readable (schema v2, both kinds)
├── index.html                       combined landing page (UT + integration)
├── coverage-ut/                     global UT --all run
│   ├── summary.json
│   ├── coverage-all.html
│   └── coverage.*.html
├── coverage-integration/            global integration run
│   ├── summary.json
│   ├── coverage-all.html
│   └── coverage.*.html
├── Svc/CmdDispatcher/
│   ├── coverage-ut/
│   │   ├── summary.json
│   │   ├── coverage.html            gcovr's native per-module report
│   │   └── coverage.*.html
│   └── coverage-integration/
│       ├── summary.json
│       ├── coverage.html
│       └── coverage.*.html
├── Drv/LinuxGpio/
│   ├── coverage-ut/
│   │   └── coverage.html            placeholder: "no coverage recorded"
│   └── coverage-integration/
│       └── coverage.html            placeholder
└── ...
```

Each module has up to two subdirectories.  The combined `index.html` at
the root shows **two rows per module** (one for unit test, one for
integration) with line/function/branch percentages and links to each
specific report.

## `catalog.json` schema (v2)

See [`coverage-common/README.md`](../coverage-common/README.md) and
`scripts/catalog.py`.  Schema version was bumped to `2` to reflect the
per-kind structure:

```json
{
  "schema": 2,
  "overall": {
    "ut": { "line_pct": 98.0, ... },
    "integration": { "line_pct": 42.1, ... }
  },
  "modules": [
    {
      "path": "Svc/CmdDispatcher",
      "has_ut": true,
      "ut": { "has_coverage": true, "line_pct": 98.0, ... },
      "integration": { "has_coverage": true, "line_pct": 45.2, ... }
    }
  ]
}
```

## Usage

```yaml
name: "Coverage"
on:
  push:
    branches: [devel, release/**]
    tags:     ['v*']
  workflow_dispatch:

jobs:
  ut-coverage:
    runs-on: ubuntu-24.04
    permissions: { contents: write }
    timeout-minutes: 90
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0, submodules: true }
      - uses: nasa/fprime-actions/setup@devel
      - uses: nasa/fprime-actions/run-unit-tests@devel
        with: { run-check: 'false', jobs: random }
      - uses: nasa/fprime-actions/coverage-common@devel
        id: cov
      - uses: nasa/fprime-actions/coverage-update@devel
        with:
          modules-jsonl: ${{ steps.cov.outputs.modules-jsonl }}
          coverage-kind: ut

  integration-coverage:
    runs-on: ubuntu-24.04
    permissions: { contents: write }
    timeout-minutes: 120
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0, submodules: true }
      - uses: nasa/fprime-actions/setup@devel
      - uses: nasa/fprime-actions/build@devel
        with:
          deployment: Ref
          generate-args: >-
            -DCMAKE_CXX_FLAGS="--coverage"
            -DCMAKE_C_FLAGS="--coverage"
            -DCMAKE_EXE_LINKER_FLAGS="--coverage"
      # Run all integration test suites (multiple invocations accumulate .gcda)
      - uses: nasa/fprime-actions/run-integration-tests@devel
        with:
          deployment: Ref
          test-path: Ref/test/int/test_basic.py
      - uses: nasa/fprime-actions/run-integration-tests@devel
        with:
          deployment: Ref
          test-path: Ref/test/int/test_advanced.py
      # Post-process
      - uses: nasa/fprime-actions/coverage-integration-common@devel
        id: intcov
        with:
          build-cache: build-fprime-automatic-native-coverage
      - uses: nasa/fprime-actions/coverage-update@devel
        with:
          modules-jsonl: ${{ steps.intcov.outputs.modules-jsonl }}
          coverage-kind: integration
```

## Bootstrapping

The first time the workflow runs against a new branch or tag, the
baseline branch does not yet exist. This action creates it on demand
(as an orphan branch).

To seed manually before opening any PRs, run the workflow via
`workflow_dispatch` on the base branch (e.g. `devel`).

# nasa/fprime-actions/coverage

Composite action that generates per-module and global gcovr coverage for an F´
project, stores it in a per-base-branch orphan branch (`coverage/<ref>`), and
posts a per-module delta comment on pull requests.

## What it does

On every run:

1. Generates and builds the unit-test build cache (`fprime-util generate --ut`
   then `fprime-util build --all --ut`).
2. Discovers F´ modules by grepping every `CMakeLists.txt` under
   `working-directory` for `register_fprime_module(`. Modules that also call
   `register_fprime_ut(` are eligible for coverage.
3. Runs `fprime-util check --all --coverage` once for the global headline
   number, then `fprime-util check --coverage` in each discovered module.
   gcovr's `--json-summary` is captured at each location.
4. Renames each module's `coverage.html` to `index.html`. The global
   `coverage-all.html` is **not** renamed.
5. Modules that produced no coverage data (no UT, or gcovr emitted nothing)
   get a placeholder `index.html` so catalog links never 404.

On **push events** (`devel`, `release/**`, tags), additionally:

6. Writes/updates an orphan branch `<baseline-branch-prefix>/<ref-name>` (e.g.
   `coverage/devel`, `coverage/release/v4.2.0`, `coverage/v4.2.0`) containing
   the per-module + global outputs mirrored to the same directory layout as
   the working tree, plus a top-level `index.html` folder-tree catalog and a
   machine-readable `catalog.json`.

On **pull-request events**, additionally:

6. Fetches the baseline branch matching the PR's base (`coverage/<base_ref>`),
   computes per-module line/branch deltas, and posts a sticky PR comment
   sorted by worst regression first. If the baseline branch does not exist
   yet (no push to the base branch has seeded it), the comment explicitly
   says so and emits no regression rows.

The PR job never pushes to any baseline branch.

## Inputs

| Input                     | Default                                 | Description                                                                                                  |
|---------------------------|-----------------------------------------|--------------------------------------------------------------------------------------------------------------|
| `working-directory`       | `.`                                     | Directory to run `fprime-util` from.                                                                         |
| `generate-args`           | `""`                                    | Extra flags passed to `fprime-util generate --ut`.                                                            |
| `target-platform`         | `""`                                    | Target platform/toolchain passed to `fprime-util`.                                                            |
| `jobs`                    | `""`                                    | Parallel job count for build/check. `random` picks 1-32 each run; empty omits `-j`.                          |
| `baseline-branch-prefix`  | `coverage`                              | Prefix applied to `<ref-name>` to form the baseline branch (`<prefix>/<ref>`).                               |
| `coverage-subdirectory`   | `coverage`                              | Subdirectory inside each module's baseline-branch entry. Set to `""` to flatten (drop the shadow folder).    |
| `regression-threshold`    | `0.5`                                   | Percentage points of line-coverage drop tolerated per module on PRs.                                          |
| `fail-on-regression`      | `false`                                 | If `true`, the PR job exits non-zero when any module regresses beyond `regression-threshold`.                |
| `comment-marker`          | `<!-- fprime-coverage-comment -->`      | Hidden HTML marker used to find and edit the sticky PR comment.                                              |
| `install-gcovr`           | `true`                                  | If `true`, the action runs `pip install --upgrade gcovr` before generating coverage.                          |

## Outputs

| Output                  | Description                                                              |
|-------------------------|--------------------------------------------------------------------------|
| `catalog-path`          | Path to the generated `catalog.json` (set on push events).               |
| `comment-path`          | Path to the markdown PR comment (set on `pull_request` events).          |
| `regressions-json-path` | Path to a JSON list of regressing modules (set on `pull_request` events). |

## Baseline branch layout (default `coverage-subdirectory: "coverage"`)

```
<prefix>/<ref>            (orphan branch, e.g. coverage/devel)
├── catalog.json                       machine-readable module list
├── index.html                         folder-tree catalog
├── coverage/                          global --all run
│   ├── summary.json
│   ├── coverage-all.html              gcovr's native global report (kept as-is)
│   └── coverage.*.html                gcovr per-source detail siblings
├── Svc/CmdDispatcher/coverage/
│   ├── summary.json
│   ├── index.html                     was coverage.html
│   └── coverage.*.html
├── Drv/LinuxGpio/coverage/
│   └── index.html                     placeholder: "no coverage recorded"
└── ...                                one entry per discovered module
```

With `coverage-subdirectory: ""` the per-module artifacts land directly in
the module's directory (no shadow folder); the global run still lives in a
top-level `coverage/` because that's where gcovr writes it.

## `catalog.json` schema

```jsonc
{
  "schema": 1,
  "ref": "devel",
  "ref_type": "branch",                 // "branch" | "tag"
  "commit": "<source-sha>",
  "generated_at": "2026-05-18T17:30:00Z",
  "overall": {
    "line_pct": 92.14, "line_covered": ..., "line_total": ...,
    "branch_pct": 78.51, "branch_covered": ..., "branch_total": ...,
    "report": "coverage/coverage-all.html"
  },
  "modules": [
    {
      "path": "Svc/CmdDispatcher",
      "has_ut": true, "has_coverage": true,
      "line_pct": 96.84, "line_covered": ..., "line_total": ...,
      "branch_pct": 80.68, "branch_covered": ..., "branch_total": ...,
      "report": "Svc/CmdDispatcher/coverage/index.html",
      "summary": "Svc/CmdDispatcher/coverage/summary.json"
    },
    {
      "path": "Drv/LinuxGpio",
      "has_ut": false, "has_coverage": false,
      "report": "Drv/LinuxGpio/coverage/index.html"
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
  pull_request:
    branches: [devel, release/**]
  workflow_dispatch:

permissions:
  contents: write          # to push to coverage/<ref>
  pull-requests: write     # to post the PR comment

jobs:
  coverage:
    runs-on: ubuntu-22.04
    timeout-minutes: 60
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0, submodules: true }
      - uses: nasa/fprime-actions/setup@devel
      - uses: nasa/fprime-actions/coverage@devel
        # All defaults: regression-threshold=0.5, fail-on-regression=false (comment-only)
```

To enable the regression gate later, flip a single input:

```yaml
      - uses: nasa/fprime-actions/coverage@devel
        with:
          fail-on-regression: 'true'
```

## Bootstrapping

The first time the workflow runs against a new branch or tag, the baseline
branch does not yet exist. The push job creates it on demand (as an orphan
branch); the PR job's comment will note "no baseline" until the first push
seeds it.

To seed manually before opening any PRs, run the workflow via
`workflow_dispatch` on the base branch (e.g. `devel`).

## Development

The action ships three Python helpers under `coverage/scripts/`:

* `discover.py` &mdash; emits JSON-Lines of `{path, has_ut}` for each
  module under the working directory.
* `mirror.py` &mdash; copies coverage outputs into the baseline worktree,
  writes placeholder pages for modules without coverage, and invokes
  `catalog.py`.
* `catalog.py` &mdash; produces `catalog.json` plus the top-level folder-tree
  `index.html`.
* `compare.py` &mdash; PR-side diff that emits the sticky comment markdown.

Run the unit tests with:

```bash
python3 coverage/tests/test_coverage.py
```

No external dependencies; the test runner exits non-zero on the first failure.

# nasa/fprime-actions/codeql-publish

Composite action that publishes **per-module CodeQL findings** (file, line,
rule, severity, message) onto the same per-base-branch baseline branch used
for coverage (`<baseline-branch-prefix>/<ref-name>`, e.g. `coverage/devel`),
and regenerates the checklist landing page.

It consumes **already-filtered SARIF files** produced by an existing CodeQL
analysis job — **no CodeQL re-scan is performed**. Pair it with the
run-for-record scan workflow: after `github/codeql-action/analyze` (with
`upload: never`) and any SARIF filtering, hand the SARIF files to this
action on push events.

## Prerequisites

* A repository checkout at `working-directory` (modules are discovered from
  `CMakeLists.txt` files via `register_fprime_module()`, exactly like the
  coverage actions).
* One or more SARIF files on disk (e.g. downloaded from an artifact of the
  analyze job).

## Required permissions

```yaml
permissions:
  contents: write
```

`contents: write` is needed to push commits to the baseline branch.

## Conflict avoidance

Multiple publishers (coverage, codeql, future int-coverage) write to the
same baseline branch. Give every publisher job the same repo-wide
concurrency group so runs serialize across workflows:

```yaml
concurrency:
  group: baseline-publish-${{ github.ref }}
  cancel-in-progress: false
```

As a second layer, the shared publish helper retries on non-fast-forward
pushes: it re-fetches the branch and re-mirrors only this writer's subtree
(subtrees are disjoint, and the checklist page regenerates from whatever
`summary.json` files exist on the branch, so retries are clean overlays).

## What it does

1. Discovers modules with `coverage-common/scripts/discover.py`.
2. Parses the SARIF files, normalizing severities to error / medium / low
   (CodeQL `security-severity` >= 7.0 is error, >= 4.0 medium, else low;
   otherwise SARIF level error/warning/note maps to error/medium/low).
3. Maps each finding to its owning module by longest-prefix path match;
   findings outside every module appear only on the global page.
4. Writes `<mod>/codeql/index.html` (findings table with source deep links)
   and `<mod>/codeql/summary.json` for every module (clean modules get a
   "clean" page), plus a global `codeql/` entry.
5. Regenerates the top-level checklist `index.html` + `catalog.json`
   (schema v2) with platinum/gold/silver/bronze badges.
6. Commits and pushes via the shared retrying publish helper.

## Badge tiers

* **Coverage** (line percent, same metric as the delta detector):
  platinum >= `tier-platinum`, gold >= `tier-gold`, silver >= `tier-silver`,
  bronze below. No coverage data is bronze.
* **CodeQL**: no findings -> platinum; worst finding low -> silver;
  medium or error -> bronze.

## Inputs

| Input                    | Default    | Description                                                        |
|--------------------------|------------|--------------------------------------------------------------------|
| `working-directory`      | `.`        | Repository checkout root.                                          |
| `sarif-files`            | (required) | Newline-separated list of filtered SARIF files.                    |
| `baseline-branch-prefix` | `coverage` | Prefix applied to `<ref-name>` to form the baseline branch.        |
| `codeql-subdirectory`    | `codeql`   | Subdirectory under each module holding CodeQL findings.            |
| `tier-platinum`          | `95`       | Line-coverage percent for the platinum tier (checklist rendering). |
| `tier-gold`              | `90`       | Line-coverage percent for the gold tier.                           |
| `tier-silver`            | `80`       | Line-coverage percent for the silver tier.                         |

## Outputs

| Output            | Description                                                  |
|-------------------|--------------------------------------------------------------|
| `baseline-branch` | Name of the baseline branch written (e.g. `coverage/devel`). |

## Usage

```yaml
  publish-findings:
    needs: analyze
    if: github.event_name == 'push'
    runs-on: ubuntu-22.04
    permissions:
      contents: write
    concurrency:
      group: baseline-publish-${{ github.ref }}
      cancel-in-progress: false
    steps:
      - uses: actions/checkout@v4
      - uses: actions/download-artifact@v4
        with:
          pattern: codeql-sarif-*
          path: sarif-results
          merge-multiple: true
      - uses: nasa/fprime-actions/codeql-publish@devel
        with:
          sarif-files: |
            sarif-results/cpp.sarif
            sarif-results/python.sarif
```

## Baseline branch layout contribution

```
coverage/devel
├── index.html                 checklist landing page (regenerated)
├── catalog.json               schema v2 (regenerated)
├── codeql/                    global findings page + summary.json
├── Svc/CmdDispatcher/
│   ├── coverage/              (written by coverage-update)
│   └── codeql/                index.html + summary.json (this action)
└── ...
```

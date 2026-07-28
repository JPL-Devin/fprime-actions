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
  security-events: read
```

`contents: write` is needed to push commits to the baseline branch;
`security-events: read` lets the action fetch alerts dismissed in the
GitHub UI so they are excluded from the published tables (omit it, or set
`github-token: ""`, to skip dismissal filtering).

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
3. Fetches alerts **dismissed in the GitHub UI** (one paginated
   code-scanning API call per publish, `state=dismissed`) and subtracts
   them from the active findings, matched on rule + path with a small
   line-drift tolerance. Dismissed findings are listed in a separate table
   (file, line, rule, dismissal reason, comment) and counted in
   `summary.json` as `dismissed`; tiers use active findings only. API
   failures degrade gracefully to unfiltered SARIF with a warning.
4. Maps each finding to its owning module by longest-prefix path match;
   findings outside every module appear only on the global page.
5. Writes `<mod>/codeql/index.html` (findings table with source deep links)
   and `<mod>/codeql/summary.json` for every module (clean modules get a
   "clean" page), plus a global `codeql/` entry.
6. Regenerates the top-level checklist `index.html` + `catalog.json`
   (schema v2) with platinum/gold/silver/bronze badges.
7. Commits and pushes via the shared retrying publish helper.

## Badge tiers

* **Coverage** (line percent, same metric as the delta detector):
  thresholds come from the repo's checklist config file (see below);
  defaults are platinum >= 95, gold >= 90, silver >= 80, bronze below.
  No coverage data is bronze.
* **CodeQL**: no findings -> platinum; worst finding low -> silver;
  medium or error -> bronze.

## Checklist configuration

Tier thresholds (and future reporting settings) are read from a config
file versioned in the repository, by default `.github/module-checklist.yml`:

```yaml
coverage:
  tiers:
    platinum: 95
    gold: 90
    silver: 80
```

All keys are optional; defaults apply when the file or key is absent.
Unknown keys are ignored so future settings can be added without breaking
older action versions.

## Inputs

| Input                    | Default    | Description                                                        |
|--------------------------|------------|--------------------------------------------------------------------|
| `working-directory`      | `.`        | Repository checkout root.                                          |
| `sarif-files`            | (required) | Newline-separated list of filtered SARIF files.                    |
| `baseline-branch-prefix` | `coverage` | Prefix applied to `<ref-name>` to form the baseline branch.        |
| `codeql-subdirectory`    | `codeql`   | Subdirectory under each module holding CodeQL findings.            |
| `config-file`            | `.github/module-checklist.yml` | Checklist config file in the repo. Defaults apply when missing. |
| `github-token`           | `${{ github.token }}` | Token for fetching dismissed alerts (`security-events: read`). Empty skips dismissal filtering. |

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
      security-events: read
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

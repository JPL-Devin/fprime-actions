# coverage-integration-aggregate

Merges multiple per-deployment gcovr JSON tracefiles and produces unified
per-module coverage reports.  Designed to run after a matrix of
`coverage-integration-collect` jobs.

## Usage

```yaml
- uses: actions/download-artifact@v4
  with:
    path: traces
    pattern: integration-trace-*
    merge-multiple: true

- uses: nasa/fprime-actions/coverage-integration-aggregate@main
  id: intcov
  with:
    working-directory: ${{ github.workspace }}
    tracefile-pattern: "traces/integration-trace-*.json"

- uses: nasa/fprime-actions/coverage-update@main
  with:
    working-directory: ${{ github.workspace }}
    modules-jsonl: ${{ steps.intcov.outputs.modules-jsonl }}
    coverage-kind: ${{ steps.intcov.outputs.coverage-kind }}
```

## How it works

1. Discovers F' modules via `discover.py`.
2. Merges all tracefiles using `gcovr --add-tracefile` — line hit counts
   are summed, branch arcs unioned, functions merged.  This produces the
   **union** of coverage across all deployments.
3. Runs per-module gcovr with `--filter <module-dir>` against the merged
   data to produce HTML + summary.json for each module.
4. Outputs `modules-jsonl` and `coverage-kind` for `coverage-update`.

Uses `--merge-mode-functions=merge-use-line-min` to handle minor
line-number differences when the same function is compiled into different
deployments with slightly different inlining.

## Inputs

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `working-directory` | no | `.` | F' source root (same as collect step) |
| `tracefile-pattern` | **yes** | — | Glob pattern for downloaded tracefiles |
| `suffix` | no | `linux` | Coverage kind suffix |
| `strict` | no | `false` | Fail on per-module errors |
| `enable-fw-assert-branch-coverage` | no | `false` | Include FW_ASSERT branches |
| `debug` | no | `false` | Verbose gcovr output |

## Outputs

| Output | Description |
|--------|-------------|
| `modules-jsonl` | Path to discovered modules list |
| `coverage-kind` | Resolved kind slug (e.g. `integration-linux`) |

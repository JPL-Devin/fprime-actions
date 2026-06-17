# coverage-integration-collect

Collects a gcovr JSON tracefile from a single deployment's integration test
coverage data.  Designed to run in a **matrix job** — one per deployment.

The tracefile is later merged by `coverage-integration-aggregate` to produce
unified per-module reports that union coverage across all deployments.

## Usage

```yaml
- uses: nasa/fprime-actions/coverage-integration-collect@main
  with:
    working-directory: ${{ github.workspace }}
    build-cache: MyDeploy/build-fprime-automatic-native
    deployment-name: MyDeploy
```

## How it works

1. Runs `gcovr --json` against the build cache to produce a single JSON
   tracefile containing all line/branch/function hit data relative to
   `working-directory`.
2. The tracefile is named `integration-trace-<deployment-name>.json`.
3. Branch cleanup flags (`--exclude-throw-branches`,
   `--exclude-unreachable-branches`, FW_ASSERT pattern) are applied
   during collection so the tracefile already excludes noise.

## Inputs

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `working-directory` | no | `.` | F' source root (must be consistent across matrix jobs) |
| `build-cache` | **yes** | — | Path to build cache with .gcno/.gcda files |
| `deployment-name` | **yes** | — | Short slug (e.g. `Ref`) for naming the tracefile |
| `enable-fw-assert-branch-coverage` | no | `false` | Include FW_ASSERT branches |
| `debug` | no | `false` | Verbose gcovr output |

## Outputs

| Output | Description |
|--------|-------------|
| `tracefile` | Absolute path to the generated JSON tracefile |

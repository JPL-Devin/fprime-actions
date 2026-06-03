# nasa/fprime-actions/coverage-integration-common

Post-process **integration test** coverage for all F´ modules.

Integration tests exercise a single deployment binary, so there is one
set of `.gcda` files produced by the run(s).  This action runs `gcovr`
once per module using `--filter <source-dir>` to attribute coverage to
each component individually, matching the per-module structure that
[`coverage-common`](../coverage-common/) produces for unit tests.

The outputs can be fed directly to
[`coverage-check`](../coverage-check/) (PR) or
[`coverage-update`](../coverage-update/) (push) using the
`coverage-kind` output (e.g. `integration-linux`, `integration-hil-arm`).

## Prerequisites

The caller must have already:

1. **Built** the deployment with GCC coverage flags.  For example,
   using `nasa/fprime-actions/build` with:
   ```yaml
   generate-args: >-
     -DCMAKE_CXX_FLAGS="--coverage"
     -DCMAKE_C_FLAGS="--coverage"
     -DCMAKE_EXE_LINKER_FLAGS="--coverage"
   ```
   **Do not** enable sanitizers — they are incompatible with coverage
   instrumentation.

2. **Run all integration test suites** so that `.gcda` files reflect
   the cumulative coverage from every test.  Multiple pytest
   invocations / test files are fine — `.gcda` counters accumulate
   across runs as long as the same build directory is reused.  For
   example:
   ```yaml
   - uses: nasa/fprime-actions/run-integration-tests@devel
     with:
       deployment: Ref
       test-path: Ref/test/int/test_basic.py
   - uses: nasa/fprime-actions/run-integration-tests@devel
     with:
       deployment: Ref
       test-path: Ref/test/int/test_advanced.py
   ```
   The FSW binary must exit cleanly (SIGTERM → atexit handlers) so that
   the runtime flushes `.gcda` counters to disk.

gcovr is provided by `fprime-tools`'s pip dependencies (via the `setup`
action).

## What it does

1. Discovers F´ modules by grepping every `CMakeLists.txt` under
   `working-directory` for `register_fprime_module(`.
2. Runs `gcovr` globally against the build cache (no filter) for
   headline numbers.
3. Runs `gcovr` per-module with `--filter <module-source-dir>` to
   attribute coverage to each component individually.
4. Writes `summary.json` + HTML reports in the same working-tree
   layout as `coverage-common` (`<module>/coverage/`).

## Inputs

| Input               | Default | Description                                                                          |
|---------------------|---------|--------------------------------------------------------------------------------------|
| `working-directory` | `.`     | Top-level project root (contains `CMakeLists.txt`, `Fw/`, `Svc/`).                   |
| `build-cache`       | (required) | Path to the CMake build cache with `.gcno` / `.gcda` files. **Always required** — the action does not auto-detect. |
| `strict`            | `false` | When `true`, fail the action if any per-module gcovr invocation fails.                |
| `suffix`            | `linux` | Platform/variant suffix appended to the coverage kind slug. E.g. `linux` → `integration-linux`, `hil-arm` → `integration-hil-arm`. |
| `debug`             | `false` | When `true`, pass `-v` to gcovr for verbose output.                                   |

## Outputs

| Output          | Description                                                       |
|-----------------|-------------------------------------------------------------------|
| `modules-jsonl` | Absolute path to the JSON-Lines file listing discovered modules.  |
| `coverage-kind` | Resolved coverage kind slug (e.g. `integration-linux`, `integration-hil-arm`). Pass to `coverage-check`/`coverage-update`. |

## Usage

### Push workflow (update baseline)

```yaml
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
  # Run all integration test suites
  - uses: nasa/fprime-actions/run-integration-tests@devel
    with:
      deployment: Ref
      test-path: Ref/test/int/test_basic.py
  - uses: nasa/fprime-actions/run-integration-tests@devel
    with:
      deployment: Ref
      test-path: Ref/test/int/test_advanced.py
  # Post-process and update baseline
  - uses: nasa/fprime-actions/coverage-integration-common@devel
    id: intcov
    with:
      build-cache: build-fprime-automatic-native-coverage
  - uses: nasa/fprime-actions/coverage-update@devel
    with:
      modules-jsonl: ${{ steps.intcov.outputs.modules-jsonl }}
      coverage-kind: ${{ steps.intcov.outputs.coverage-kind }}
```

### PR workflow (check for regressions)

```yaml
  # ... (same build + integration test steps as above)
  - uses: nasa/fprime-actions/coverage-integration-common@devel
    id: intcov
    with:
      build-cache: build-fprime-automatic-native-coverage
      suffix: linux
  - uses: nasa/fprime-actions/coverage-check@devel
    with:
      modules-jsonl: ${{ steps.intcov.outputs.modules-jsonl }}
      coverage-kind: ${{ steps.intcov.outputs.coverage-kind }}
```

### Multiple platforms (Linux + HIL ARM)

```yaml
  # Job 1: Linux integration
  - uses: nasa/fprime-actions/coverage-integration-common@devel
    id: linux
    with:
      build-cache: build-fprime-automatic-native-coverage
      suffix: linux
  - uses: nasa/fprime-actions/coverage-update@devel
    with:
      modules-jsonl: ${{ steps.linux.outputs.modules-jsonl }}
      coverage-kind: ${{ steps.linux.outputs.coverage-kind }}

  # Job 2: HIL ARM integration
  - uses: nasa/fprime-actions/coverage-integration-common@devel
    id: hil
    with:
      build-cache: build-fprime-automatic-arm-coverage
      suffix: hil-arm
  - uses: nasa/fprime-actions/coverage-update@devel
    with:
      modules-jsonl: ${{ steps.hil.outputs.modules-jsonl }}
      coverage-kind: ${{ steps.hil.outputs.coverage-kind }}
```

## Relationship to other coverage actions

| Action                        | Purpose                                              |
|-------------------------------|------------------------------------------------------|
| `coverage-common`             | Generate UT coverage (via `fprime-util check`)       |
| **`coverage-integration-common`** | Generate integration coverage (via `gcovr`)      |
| `coverage-check`              | Compare PR vs baseline, produce PR comment           |
| `coverage-update`             | Mirror to baseline branch                            |
| `coverage-comment`            | Post sticky PR comment (from `workflow_run`)          |

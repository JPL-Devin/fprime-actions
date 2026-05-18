# nasa/fprime-actions/run-unit-tests

The `run-unit-tests` action generates, builds, and runs F´ unit tests.

## Inputs

| Input               | Default  | Description                                                                                                                                                                |
|---------------------|----------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `working-directory` | `.`      | Directory to run `fprime-util` from.                                                                                                                                       |
| `generate-args`     | `""`     | Extra flags passed to `fprime-util generate --ut` (e.g. `-DFPRIME_ENABLE_FRAMEWORK_UTS=OFF`).                                                                              |
| `target-platform`   | `""`     | Target platform/toolchain passed to `fprime-util` (e.g. `native`, `aarch64-linux`).                                                                                        |
| `jobs`              | `""`     | Parallel job count: a number, `random` (1-32), or empty to omit `-j`.                                                                                                      |
| `run-check`         | `"true"` | If `"true"`, run the unit tests after generating and building. Set to `"false"` to only generate and build &mdash; useful when a follow-on step (e.g. [`coverage-common`](../coverage-common/)) needs to run the tests itself under gcovr. |

## Usage

```yaml
- uses: nasa/fprime-actions/run-unit-tests@devel
  with:
    jobs: random
```

To generate and build only (no test run), e.g. as a prelude to the
coverage actions:

```yaml
- uses: nasa/fprime-actions/run-unit-tests@devel
  with:
    run-check: 'false'
    jobs: random
- uses: nasa/fprime-actions/coverage-common@devel
  id: cov
- uses: nasa/fprime-actions/coverage-check@devel
  with:
    modules-jsonl: ${{ steps.cov.outputs.modules-jsonl }}
```

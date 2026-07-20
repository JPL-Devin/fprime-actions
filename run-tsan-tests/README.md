# F Prime TSan Unit Tests

Generate and run F Prime unit tests with [ThreadSanitizer](https://clang.llvm.org/docs/ThreadSanitizer.html) enabled. Other sanitizers (ASan, LSan, UBSan) are explicitly disabled since TSan is incompatible with them.

## Usage

```yaml
- uses: nasa/fprime-actions/run-tsan-tests@devel
  with:
    jobs: 4
    check-targets: "LocklessPriorityQueueTsanTest"
```

## Inputs

| Name | Default | Description |
|------|---------|-------------|
| `working-directory` | `.` | Directory to run `fprime-util` from |
| `generate-args` | `""` | Extra flags for `fprime-util generate --ut` (in addition to the TSan flags) |
| `target-platform` | `""` | Platform/toolchain for `fprime-util` |
| `jobs` | `""` | Parallel job count: a number, `random` (1-32), or empty |
| `tsan-options` | `halt_on_error=1 history_size=5` | `TSAN_OPTIONS` env var |
| `check-timeout` | `600` | Timeout in seconds passed to `ctest` |
| `check-targets` | `""` | Space-separated test target names (joined with `\|` into ctest `-R` regex) |

## What it does

1. `fprime-util generate --ut -DENABLE_SANITIZER_THREAD=ON -DENABLE_SANITIZER_ADDRESS=OFF -DENABLE_SANITIZER_LEAK=OFF -DENABLE_SANITIZER_UNDEFINED_BEHAVIOR=OFF -DFPRIME_ENABLE_UT_COVERAGE=OFF`
2. `fprime-util check --all --pass-through --output-on-failure --timeout <check-timeout> [-R <regex>]`

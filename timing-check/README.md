# F´ Timing (check)

Flags CI jobs that run significantly longer than they normally do, so a
change that makes builds/tests much slower is caught before merge.

## How it works

1. Builds a per-job baseline from the last `baseline-runs` successful
   runs of the **same workflow** on `baseline-branch` (default: the
   repository's default branch), using each job's execution time
   (`started_at` → `completed_at`, so queue time is excluded) and only
   jobs that concluded `success`.
2. For each job name, computes the **median** and **MAD** (median
   absolute deviation) — both robust to the occasional slow runner.
3. Compares each completed job in the current run against its limit:

   ```
   limit = max(median * threshold-ratio,
               median + mad-multiplier * MAD,
               median + min-slowdown-seconds)
   ```

   A job is flagged only when it exceeds **all three** guards, avoiding
   false positives from runner variance (MAD guard) and from short jobs
   whose runtime doubles by a few seconds (absolute guard).
4. Emits `::warning::` annotations (or `::error::` + a failing job with
   `fail-on-regression: true`), writes a markdown table to the step
   summary, and exposes the report and a regressions JSON as outputs.

## Usage

Add a final job that depends on the jobs you want timed:

```yaml
permissions:
  actions: read
  contents: read

jobs:
  # ... existing build/test jobs ...

  timing-check:
    name: "Timing Check"
    runs-on: ubuntu-latest
    needs: [build, unit-tests, integration-tests]
    if: always()          # run even when a job fails
    steps:
      - uses: JPL-Devin/fprime-actions/timing-check@main
        with:
          fail-on-regression: false   # start warn-only; enforce later
```

The job running the action is excluded from the comparison
automatically (it is still in progress).  Jobs that failed in the
current run are still compared if they completed; jobs with no baseline
(new or renamed) are listed but not flagged.

## Inputs

| Input | Default | Description |
| --- | --- | --- |
| `github-token` | `${{ github.token }}` | Needs `actions: read` |
| `baseline-branch` | repo default branch | Branch whose runs form the baseline |
| `baseline-runs` | `20` | Recent successful runs to sample |
| `min-samples` | `3` | Baseline samples required before comparing a job |
| `threshold-ratio` | `1.5` | Flag when current > median × ratio |
| `mad-multiplier` | `3.0` | Also require current > median + n·MAD |
| `min-slowdown-seconds` | `60` | Also require this much absolute slowdown |
| `skip-jobs` | `""` | Newline-separated job names to ignore |
| `fail-on-regression` | `false` | Fail the job on any flagged regression |
| `comment-marker` | `<!-- fprime-timing-check -->` | Marker embedded in the report |

## Outputs

| Output | Description |
| --- | --- |
| `report-path` | Markdown report (also written to the step summary) |
| `regressions-json-path` | JSON list of flagged jobs with timings |
| `regressed` | `"true"` if any job exceeded its limit |

## Caveats

* Matrix jobs are compared by their full rendered job name, so each
  matrix leg gets its own baseline.
* Cache-cold runs (e.g. after a cache key change) will look slow;
  expect occasional warnings after dependency or cache updates.
* Baselines come from the baseline branch, so a slowdown merged to the
  default branch becomes the new normal after ~`baseline-runs` runs.

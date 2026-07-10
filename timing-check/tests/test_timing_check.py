"""Unit tests for the timing-check action's helper script.

Run with:  python3 timing-check/tests/test_timing_check.py

No external dependencies.  Each test prints OK or FAIL and the runner
exits 1 on any failure.
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS_DIR = HERE.parent / "scripts"

sys.path.insert(0, str(SCRIPTS_DIR))

import timing_check  # noqa: E402


def _job(name, started, completed, conclusion="success", status="completed"):
    return {
        "name": name,
        "started_at": started,
        "completed_at": completed,
        "conclusion": conclusion,
        "status": status,
    }


def test_job_duration_seconds():
    job = _job("build", "2026-07-10T00:00:00Z", "2026-07-10T00:10:00Z")
    assert timing_check.job_duration_seconds(job) == 600.0
    assert timing_check.job_duration_seconds({"name": "x"}) is None
    negative = _job("x", "2026-07-10T00:10:00Z", "2026-07-10T00:00:00Z")
    assert timing_check.job_duration_seconds(negative) is None


def test_collect_baseline_durations_skips_non_success():
    runs = [
        [
            _job("build", "2026-07-10T00:00:00Z", "2026-07-10T00:10:00Z"),
            _job("build", "2026-07-10T01:00:00Z", "2026-07-10T01:30:00Z",
                 conclusion="failure"),
        ],
        [_job("build", "2026-07-10T02:00:00Z", "2026-07-10T02:12:00Z")],
    ]
    durations = timing_check.collect_baseline_durations(runs)
    assert durations == {"build": [600.0, 720.0]}


def test_compute_baselines_min_samples():
    durations = {"build": [600.0, 620.0, 580.0], "rare": [100.0]}
    baselines = timing_check.compute_baselines(durations, min_samples=3)
    assert "rare" not in baselines
    assert baselines["build"].median == 600.0
    assert baselines["build"].mad == 20.0
    assert baselines["build"].samples == 3


def test_compare_flags_regression():
    baselines = {"build": timing_check.Baseline(median=600.0, mad=20.0, samples=10)}
    slow = _job("build", "2026-07-10T00:00:00Z", "2026-07-10T00:20:00Z")  # 1200s
    comparisons = timing_check.compare_jobs(
        [slow], baselines, threshold_ratio=1.5, mad_multiplier=3.0,
        min_slowdown_seconds=60.0, skip_names=[])
    assert len(comparisons) == 1
    assert comparisons[0].regressed
    assert comparisons[0].delta_percent == 100.0
    # limit = max(900, 660, 660) = 900
    assert comparisons[0].limit == 900.0


def test_compare_respects_absolute_guard():
    # Short job: doubles from 30s to 70s but under the 60s absolute guard limit.
    baselines = {"lint": timing_check.Baseline(median=30.0, mad=2.0, samples=10)}
    job = _job("lint", "2026-07-10T00:00:00Z", "2026-07-10T00:01:10Z")  # 70s
    comparisons = timing_check.compare_jobs(
        [job], baselines, threshold_ratio=1.5, mad_multiplier=3.0,
        min_slowdown_seconds=60.0, skip_names=[])
    # limit = max(45, 36, 90) = 90
    assert not comparisons[0].regressed


def test_compare_skips_named_and_incomplete_jobs():
    baselines = {"build": timing_check.Baseline(median=600.0, mad=20.0, samples=10),
                 "timing-check": timing_check.Baseline(median=10.0, mad=1.0, samples=10)}
    running = _job("build", "2026-07-10T00:00:00Z", None, status="in_progress")
    running["completed_at"] = None
    self_job = _job("timing-check", "2026-07-10T00:00:00Z", "2026-07-10T00:05:00Z")
    comparisons = timing_check.compare_jobs(
        [running, self_job], baselines, threshold_ratio=1.5,
        mad_multiplier=3.0, min_slowdown_seconds=60.0,
        skip_names=["timing-check"])
    assert comparisons == []


def test_render_report_contains_marker_and_rows():
    baselines = timing_check.Baseline(median=600.0, mad=20.0, samples=10)
    comparison = timing_check.Comparison(
        name="build", current=1200.0, baseline=baselines, limit=900.0)
    report = timing_check.render_report(
        [comparison], ["new-job"], "devel", "<!-- marker -->")
    assert "<!-- marker -->" in report
    assert "| build |" in report
    assert "SLOW" in report
    assert "`new-job`" in report


def test_render_report_empty():
    report = timing_check.render_report([], [], "devel", "<!-- marker -->")
    assert "nothing to compare" in report


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failures = 0
    for test in tests:
        try:
            test()
            print(f"OK   {test.__name__}")
        except Exception:
            failures += 1
            print(f"FAIL {test.__name__}")
            traceback.print_exc()
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

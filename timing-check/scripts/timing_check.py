"""Compare the current workflow run's job durations against a baseline.

Baseline construction:
    Query the GitHub Actions API for recent successful runs of the same
    workflow on the baseline branch (typically the default branch).  For
    each job name, collect execution durations (``started_at`` ->
    ``completed_at``, so queue time is excluded) and compute the median
    and MAD (median absolute deviation), which are robust to the odd
    slow runner.

Regression rule:
    A job is flagged when its current duration exceeds both

        median * threshold-ratio         (relative guard)
    and
        median + mad-multiplier * MAD    (statistical guard)

    and the absolute slowdown exceeds ``min-slowdown-seconds`` (so tiny
    jobs whose runtime doubles from 20s to 45s do not trip the check).

Outputs a markdown report, GitHub annotations, and optionally a nonzero
exit code (``--fail-on-regression``).

Only the Python standard library is used.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional


API_VERSION = "2022-11-28"


# ---------------------------------------------------------------------------
# GitHub API access
# ---------------------------------------------------------------------------


class GitHubAPI:
    """Minimal paginated GET client for the GitHub REST API."""

    def __init__(self, api_url: str, repo: str, token: str):
        self.api_url = api_url.rstrip("/")
        self.repo = repo
        self.token = token

    def get(self, path: str, params: Optional[dict] = None) -> dict:
        url = f"{self.api_url}/repos/{self.repo}{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        request = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": API_VERSION,
            },
        )
        with urllib.request.urlopen(request) as response:
            return json.load(response)

    def paginate(self, path: str, key: str, params: Optional[dict] = None,
                 max_items: int = 1000) -> List[dict]:
        items: List[dict] = []
        page = 1
        params = dict(params or {})
        params["per_page"] = 100
        while len(items) < max_items:
            params["page"] = page
            payload = self.get(path, params)
            batch = payload.get(key, [])
            items.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        return items[:max_items]


# ---------------------------------------------------------------------------
# Duration extraction and statistics
# ---------------------------------------------------------------------------


def _parse_time(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")


def job_duration_seconds(job: dict) -> Optional[float]:
    """Execution time of a completed job, excluding queue time."""
    started = job.get("started_at")
    completed = job.get("completed_at")
    if not started or not completed:
        return None
    seconds = (_parse_time(completed) - _parse_time(started)).total_seconds()
    return seconds if seconds >= 0 else None


def collect_baseline_durations(jobs_by_run: List[List[dict]]) -> Dict[str, List[float]]:
    """Map job name -> list of durations across baseline runs.

    Only successful jobs contribute; failed or cancelled jobs have
    unrepresentative durations.
    """
    durations: Dict[str, List[float]] = {}
    for jobs in jobs_by_run:
        for job in jobs:
            if job.get("conclusion") != "success":
                continue
            seconds = job_duration_seconds(job)
            if seconds is None:
                continue
            durations.setdefault(job["name"], []).append(seconds)
    return durations


@dataclass(frozen=True)
class Baseline:
    median: float
    mad: float
    samples: int


def compute_baselines(durations: Dict[str, List[float]],
                      min_samples: int) -> Dict[str, Baseline]:
    baselines: Dict[str, Baseline] = {}
    for name, values in durations.items():
        if len(values) < min_samples:
            continue
        median = statistics.median(values)
        mad = statistics.median(abs(v - median) for v in values)
        baselines[name] = Baseline(median=median, mad=mad, samples=len(values))
    return baselines


@dataclass(frozen=True)
class Comparison:
    name: str
    current: float
    baseline: Baseline
    limit: float

    @property
    def regressed(self) -> bool:
        return self.current > self.limit

    @property
    def delta_percent(self) -> float:
        if self.baseline.median <= 0:
            return 0.0
        return round(100.0 * (self.current - self.baseline.median) / self.baseline.median, 1)


def compare_jobs(current_jobs: List[dict],
                 baselines: Dict[str, Baseline],
                 threshold_ratio: float,
                 mad_multiplier: float,
                 min_slowdown_seconds: float,
                 skip_names: List[str]) -> List[Comparison]:
    """Compare each completed current job against its baseline.

    ``skip_names`` excludes jobs (e.g. the timing-check job itself,
    which is still in progress and has no meaningful duration).
    """
    comparisons: List[Comparison] = []
    for job in current_jobs:
        name = job["name"]
        if name in skip_names:
            continue
        seconds = job_duration_seconds(job)
        if seconds is None or job.get("status") != "completed":
            continue
        baseline = baselines.get(name)
        if baseline is None:
            continue
        limit = max(
            baseline.median * threshold_ratio,
            baseline.median + mad_multiplier * baseline.mad,
            baseline.median + min_slowdown_seconds,
        )
        comparisons.append(Comparison(name=name, current=seconds,
                                      baseline=baseline, limit=limit))
    return sorted(comparisons, key=lambda c: c.delta_percent, reverse=True)


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _fmt(seconds: float) -> str:
    minutes, secs = divmod(int(round(seconds)), 60)
    return f"{minutes}m {secs:02d}s" if minutes else f"{secs}s"


def render_report(comparisons: List[Comparison], unmatched: List[str],
                  baseline_branch: str, marker: str) -> str:
    lines = [marker, "## CI job timing check", ""]
    if not comparisons:
        lines.append("No completed jobs had a usable baseline; nothing to compare.")
        return "\n".join(lines) + "\n"
    lines += [
        f"Baseline: median of recent successful runs on `{baseline_branch}`.",
        "",
        "| Job | Baseline (median) | Current | Δ | Limit | Status |",
        "| --- | ---: | ---: | ---: | ---: | :---: |",
    ]
    for c in comparisons:
        status = "🔺 **SLOW**" if c.regressed else "OK"
        sign = "+" if c.delta_percent >= 0 else ""
        lines.append(
            f"| {c.name} | {_fmt(c.baseline.median)} ({c.baseline.samples} runs) "
            f"| {_fmt(c.current)} | {sign}{c.delta_percent}% | {_fmt(c.limit)} | {status} |"
        )
    if unmatched:
        lines += ["", "Jobs with no baseline (new or renamed): " +
                  ", ".join(f"`{n}`" for n in unmatched)]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, help="owner/repo")
    parser.add_argument("--api-url", default="https://api.github.com")
    parser.add_argument("--run-id", required=True, type=int)
    parser.add_argument("--baseline-branch", required=True)
    parser.add_argument("--baseline-runs", type=int, default=20)
    parser.add_argument("--min-samples", type=int, default=3)
    parser.add_argument("--threshold-ratio", type=float, default=1.5)
    parser.add_argument("--mad-multiplier", type=float, default=3.0)
    parser.add_argument("--min-slowdown-seconds", type=float, default=60.0)
    parser.add_argument("--skip-job", action="append", default=[],
                        help="Job name to exclude (repeatable)")
    parser.add_argument("--comment-marker", default="<!-- fprime-timing-check -->")
    parser.add_argument("--output", required=True,
                        help="Path to write the markdown report")
    parser.add_argument("--regressions-output", required=True,
                        help="Path to write a JSON list of regressed jobs")
    parser.add_argument("--fail-on-regression", action="store_true")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("::error::GITHUB_TOKEN is not set", file=sys.stderr)
        return 2
    api = GitHubAPI(args.api_url, args.repo, token)

    current_run = api.get(f"/actions/runs/{args.run_id}")
    workflow_id = current_run["workflow_id"]

    baseline_runs = api.paginate(
        f"/actions/workflows/{workflow_id}/runs",
        "workflow_runs",
        {"branch": args.baseline_branch, "status": "success",
         "exclude_pull_requests": "true"},
        max_items=args.baseline_runs,
    )
    jobs_by_run = [
        api.paginate(f"/actions/runs/{run['id']}/jobs", "jobs")
        for run in baseline_runs
        if run["id"] != args.run_id
    ]
    baselines = compute_baselines(
        collect_baseline_durations(jobs_by_run), args.min_samples)

    current_jobs = api.paginate(f"/actions/runs/{args.run_id}/jobs", "jobs")
    comparisons = compare_jobs(
        current_jobs, baselines,
        threshold_ratio=args.threshold_ratio,
        mad_multiplier=args.mad_multiplier,
        min_slowdown_seconds=args.min_slowdown_seconds,
        skip_names=args.skip_job,
    )
    unmatched = sorted(
        job["name"] for job in current_jobs
        if job["name"] not in baselines
        and job["name"] not in args.skip_job
        and job.get("status") == "completed"
    )

    report = render_report(comparisons, unmatched,
                           args.baseline_branch, args.comment_marker)
    with open(args.output, "w") as handle:
        handle.write(report)

    regressions = [c for c in comparisons if c.regressed]
    with open(args.regressions_output, "w") as handle:
        json.dump(
            [
                {
                    "job": c.name,
                    "current_seconds": c.current,
                    "baseline_median_seconds": c.baseline.median,
                    "baseline_samples": c.baseline.samples,
                    "limit_seconds": c.limit,
                    "delta_percent": c.delta_percent,
                }
                for c in regressions
            ],
            handle,
            indent=2,
        )

    for c in regressions:
        level = "error" if args.fail_on_regression else "warning"
        print(
            f"::{level}::Job '{c.name}' took {_fmt(c.current)} vs baseline "
            f"median {_fmt(c.baseline.median)} ({c.delta_percent:+}%, "
            f"limit {_fmt(c.limit)})"
        )

    if regressions and args.fail_on_regression:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

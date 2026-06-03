"""Compare PR-head coverage against a baseline branch worktree.

For each module in the discovered module list, read the PR-side
``<source>/<mod>/coverage/summary.json`` and the corresponding
``<baseline>/<mod>/coverage-<kind>/summary.json`` and compute line /
function / branch deltas.

Writes a markdown PR comment to ``--output``.  Exits 0 by default; pass
``--fail-on-regression`` to exit 1 when any module's line coverage drops
by more than ``--threshold`` percentage points.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from _summary import Summary, load_summary

DEFAULT_COMMENT_MARKER = "<!-- fprime-coverage-comment -->"

def _kind_label(kind: str) -> str:
    """Human-readable label for a coverage kind slug."""
    if kind == "ut":
        return "Unit Test"
    if kind.startswith("integration-"):
        suffix = kind[len("integration-"):]
        return f"Integration ({suffix})"
    if kind == "integration":
        return "Integration"
    return kind.replace("-", " ").title()


@dataclass
class ModuleDelta:
    path: str
    has_ut: bool
    pr: Optional[Summary]
    baseline: Optional[Summary]

    @property
    def line_delta(self) -> Optional[float]:
        if self.pr is None or self.baseline is None:
            return None
        return round(self.pr.line.percent - self.baseline.line.percent, 2)

    @property
    def function_delta(self) -> Optional[float]:
        if self.pr is None or self.baseline is None:
            return None
        return round(self.pr.function.percent - self.baseline.function.percent, 2)

    @property
    def branch_delta(self) -> Optional[float]:
        if self.pr is None or self.baseline is None:
            return None
        return round(self.pr.branch.percent - self.baseline.branch.percent, 2)


def _format_delta(delta: Optional[float]) -> str:
    if delta is None:
        return "&mdash;"
    sign = "+" if delta >= 0 else ""
    return f"{sign}{delta:.2f}"


def _format_pct(summary: Optional[Summary], attr: str) -> str:
    if summary is None:
        return "&mdash;"
    value = getattr(summary, attr).percent
    return f"{value:.2f}"


def _row(delta: ModuleDelta) -> str:
    return (
        f"| `{delta.path}` "
        f"| {_format_pct(delta.pr, 'line')} "
        f"| {_format_delta(delta.line_delta)} "
        f"| {_format_pct(delta.pr, 'function')} "
        f"| {_format_delta(delta.function_delta)} "
        f"| {_format_pct(delta.pr, 'branch')} "
        f"| {_format_delta(delta.branch_delta)} |"
    )


def _baseline_path(baseline_root: Path, module_path: str, subdir: str) -> Path:
    return baseline_root / module_path / subdir / "summary.json"


def build_comment(
    *,
    deltas: List[ModuleDelta],
    overall_pr: Optional[Summary],
    overall_baseline: Optional[Summary],
    base_ref: str,
    threshold: float,
    marker: str,
    baseline_missing: bool,
    coverage_kind: str,
) -> tuple[str, List[ModuleDelta]]:
    """Return (markdown, regressions) where regressions are entries below threshold."""
    regressions: list[ModuleDelta] = []
    changed: list[ModuleDelta] = []
    new_mods: list[ModuleDelta] = []
    removed_mods: list[ModuleDelta] = []

    for d in deltas:
        if d.pr is None and d.baseline is None:
            continue
        if d.pr is None and d.baseline is not None:
            removed_mods.append(d)
            continue
        if d.pr is not None and d.baseline is None:
            new_mods.append(d)
            continue
        if d.pr is not None and d.baseline is not None:
            ld = d.line_delta or 0.0
            if abs(ld) >= 0.005:
                changed.append(d)
            if ld < -threshold:
                regressions.append(d)

    changed.sort(key=lambda d: (d.line_delta or 0.0))
    regressions.sort(key=lambda d: (d.line_delta or 0.0))
    new_mods.sort(key=lambda d: d.path)
    removed_mods.sort(key=lambda d: d.path)

    kind_label = _kind_label(coverage_kind)

    overall_line_pr = f"{overall_pr.line.percent:.2f}" if overall_pr else "&mdash;"
    overall_line_base = f"{overall_baseline.line.percent:.2f}" if overall_baseline else "&mdash;"
    if overall_pr and overall_baseline:
        overall_delta = round(overall_pr.line.percent - overall_baseline.line.percent, 2)
        overall_line = f"**Overall (line):** {overall_line_base}% &rarr; {overall_line_pr}% ({_format_delta(overall_delta)})"
    else:
        overall_line = f"**Overall (line):** {overall_line_pr}% (no baseline)"

    lines: list[str] = []
    lines.append(f"### {kind_label} coverage report &mdash; base `{base_ref}`")
    lines.append("")
    if baseline_missing:
        lines.append(
            f"_No baseline branch `coverage/{base_ref}` found. This run becomes the seed once it lands on `{base_ref}`._"
        )
        lines.append("")
    lines.append(overall_line)
    lines.append(f"_Regression threshold: {threshold:.2f}% (line)._")
    lines.append("")

    lines.append("#### Regressions")
    if regressions:
        lines.append("| Module | Line | &Delta; | Function | &Delta; | Branch | &Delta; |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|")
        lines.extend(_row(d) for d in regressions)
    else:
        lines.append("_(none over threshold)_")
    lines.append("")

    lines.append("#### Modules changed")
    if changed:
        lines.append("| Module | Line | &Delta; | Function | &Delta; | Branch | &Delta; |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|")
        lines.extend(_row(d) for d in changed)
    else:
        lines.append("_(no measurable change)_")
    lines.append("")

    if new_mods:
        lines.append("#### New modules")
        lines.append("| Module | Line | Function | Branch |")
        lines.append("|---|---:|---:|---:|")
        for d in new_mods:
            lines.append(
                f"| `{d.path}` | {_format_pct(d.pr, 'line')} | {_format_pct(d.pr, 'function')} | {_format_pct(d.pr, 'branch')} |"
            )
        lines.append("")

    if removed_mods:
        lines.append("#### Removed modules")
        lines.append("| Module | Baseline Line | Baseline Function | Baseline Branch |")
        lines.append("|---|---:|---:|---:|")
        for d in removed_mods:
            lines.append(
                f"| `{d.path}` | {_format_pct(d.baseline, 'line')} | {_format_pct(d.baseline, 'function')} | {_format_pct(d.baseline, 'branch')} |"
            )
        lines.append("")

    lines.append(marker)
    return "\n".join(lines).rstrip() + "\n", regressions


def build_summary_comment(
    *,
    deltas: List[ModuleDelta],
    overall_pr: Optional[Summary],
    coverage_kind: str,
    marker: str,
) -> str:
    """Return a standalone summary markdown with absolute coverage numbers (no deltas)."""
    kind_label = _kind_label(coverage_kind)

    lines: list[str] = []
    lines.append(f"### {kind_label} coverage summary")
    lines.append("")

    if overall_pr is not None:
        lines.append(
            f"**Overall:** {overall_pr.line.percent:.2f}% line, "
            f"{overall_pr.function.percent:.2f}% function, "
            f"{overall_pr.branch.percent:.2f}% branch"
        )
    else:
        lines.append("**Overall:** no coverage data")
    lines.append("")

    covered = [d for d in deltas if d.pr is not None]
    if covered:
        covered.sort(key=lambda d: d.path)
        lines.append("| Module | Line | Function | Branch |")
        lines.append("|---|---:|---:|---:|")
        for d in covered:
            lines.append(
                f"| `{d.path}` "
                f"| {_format_pct(d.pr, 'line')} "
                f"| {_format_pct(d.pr, 'function')} "
                f"| {_format_pct(d.pr, 'branch')} |"
            )
        lines.append("")

    lines.append(marker)
    return "\n".join(lines).rstrip() + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="PR-head working tree")
    parser.add_argument("--baseline", type=Path, required=True, help="Baseline worktree root")
    parser.add_argument("--modules-jsonl", type=Path, required=True)
    parser.add_argument(
        "--coverage-kind",
        default="ut",
        help="Coverage kind slug (e.g. 'ut', 'integration-int', 'integration-hil-arm')",
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=None,
        help="If set, write a standalone summary markdown (absolute numbers, no deltas) to this path",
    )
    parser.add_argument("--base-ref", required=True, help="Base branch name for the comment header")
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--comment-marker", default=DEFAULT_COMMENT_MARKER)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--regressions-output", type=Path, default=None)
    parser.add_argument(
        "--fail-on-regression",
        action="store_true",
        help="Exit 1 if any module's line coverage drops more than --threshold",
    )
    parser.add_argument(
        "--baseline-missing",
        action="store_true",
        help="Caller signals the baseline branch did not exist for this base ref",
    )
    args = parser.parse_args(argv)

    source = args.source.resolve()
    baseline = args.baseline.resolve()
    subdir = f"coverage-{args.coverage_kind}"

    with args.modules_jsonl.open("r", encoding="utf-8") as fh:
        records = [json.loads(line) for line in fh if line.strip()]

    deltas: list[ModuleDelta] = []
    for rec in records:
        path = rec["path"]
        has_ut = bool(rec.get("has_ut", False))
        pr_summary = load_summary(source / path / "coverage" / "summary.json")
        base_summary = (
            None if args.baseline_missing else load_summary(_baseline_path(baseline, path, subdir))
        )
        deltas.append(ModuleDelta(path=path, has_ut=has_ut, pr=pr_summary, baseline=base_summary))

    overall_pr = load_summary(source / "coverage" / "summary.json")
    overall_baseline = (
        None
        if args.baseline_missing
        else load_summary(baseline / subdir / "summary.json")
    )

    markdown, regressions = build_comment(
        deltas=deltas,
        overall_pr=overall_pr,
        overall_baseline=overall_baseline,
        base_ref=args.base_ref,
        threshold=args.threshold,
        marker=args.comment_marker,
        baseline_missing=args.baseline_missing,
        coverage_kind=args.coverage_kind,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(markdown, encoding="utf-8")

    if args.summary_output is not None:
        summary_marker = args.comment_marker.replace("-comment", "-summary-comment")
        summary_md = build_summary_comment(
            deltas=deltas,
            overall_pr=overall_pr,
            coverage_kind=args.coverage_kind,
            marker=summary_marker,
        )
        args.summary_output.parent.mkdir(parents=True, exist_ok=True)
        args.summary_output.write_text(summary_md, encoding="utf-8")

    if args.regressions_output is not None:
        args.regressions_output.parent.mkdir(parents=True, exist_ok=True)
        args.regressions_output.write_text(
            json.dumps(
                [{"path": d.path, "line_delta": d.line_delta} for d in regressions],
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    print(
        f"compare: {len(deltas)} modules, {len(regressions)} regressions (threshold {args.threshold:.2f}%)",
        file=sys.stderr,
    )

    if args.fail_on_regression and regressions:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Generate ``catalog.json`` and the top-level folder-tree ``index.html``.

The catalog reads from the baseline worktree (``--dest``), scanning both
``coverage-ut/`` and ``coverage-integration/`` subdirectories for each
module.  The resulting landing page shows **two rows per module** (one for
unit-test coverage, one for integration-test coverage) so reviewers can
see both at a glance.

Inputs:
    * A list of discovered modules (path, has_ut) from ``discover.py``.
    * The baseline worktree containing per-module
      ``<mod>/coverage-ut/summary.json`` and/or
      ``<mod>/coverage-integration/summary.json``, plus global
      ``coverage-ut/summary.json`` and/or ``coverage-integration/summary.json``.

Outputs (written to ``--dest``):
    * ``catalog.json`` -- machine-readable; see ``schema`` field for version.
    * ``index.html``   -- self-contained folder-tree catalog page.

The HTML page is intentionally a single file with no external assets so the
``coverage/<ref>`` orphan branch is self-hosting.  ``<details>``/``<summary>``
elements provide collapse/expand without JavaScript.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional

from _summary import Summary, Totals, load_summary

SCHEMA_VERSION = 2

COVERAGE_KINDS = ("ut", "integration")
KIND_LABELS = {"ut": "unit test", "integration": "integration"}

CSS = """\
* { box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  margin: 0; padding: 1.5rem; color: #1f2328; background: #ffffff;
}
h1 { margin: 0 0 0.25rem 0; font-size: 1.4rem; }
.meta { color: #57606a; font-size: 0.9rem; margin-bottom: 1rem; }
.overall {
  display: flex; gap: 1rem; align-items: baseline; flex-wrap: wrap;
  padding: 0.75rem 1rem; background: #f6f8fa; border: 1px solid #d0d7de;
  border-radius: 6px; margin-bottom: 1rem;
}
.overall a { color: #0969da; text-decoration: none; }
.overall a:hover { text-decoration: underline; }
.overall-row { display: flex; gap: 0.75rem; align-items: baseline; width: 100%; }
details { border: 1px solid #d0d7de; border-radius: 6px; margin-bottom: 0.5rem; background: #ffffff; }
details > summary {
  cursor: pointer; padding: 0.5rem 0.75rem; font-weight: 600;
  list-style: none;
}
details > summary::-webkit-details-marker { display: none; }
details > summary::before { content: "\\25B6"; display: inline-block; margin-right: 0.4rem; transition: transform 0.1s; }
details[open] > summary::before { transform: rotate(90deg); }
table { width: 100%; border-collapse: collapse; }
table th, table td { padding: 0.35rem 0.75rem; text-align: left; }
table th { font-weight: 500; color: #57606a; font-size: 0.85rem; border-bottom: 1px solid #eaeef2; }
table td.num, table th.num { text-align: right; font-variant-numeric: tabular-nums; width: 6rem; }
table tr.row { border-top: 1px solid #eaeef2; }
table tr.row:hover { background: #f6f8fa; }
table a { color: #0969da; text-decoration: none; }
table a:hover { text-decoration: underline; }
.pct-green  { color: #1a7f37; }
.pct-yellow { color: #9a6700; }
.pct-red    { color: #cf222e; }
.no-ut, .no-cov { color: #6e7781; font-style: italic; }
.kind-label { color: #57606a; font-size: 0.85rem; font-weight: normal; }
.section-title { margin: 1.25rem 0 0.5rem 0; font-size: 1.05rem; }
"""


def _pct_class(pct: float, has_coverage: bool) -> str:
    if not has_coverage:
        return "no-cov"
    if pct >= 90.0:
        return "pct-green"
    if pct >= 80.0:
        return "pct-yellow"
    return "pct-red"


@dataclass
class KindEntry:
    """Coverage data for one module under one kind (ut or integration)."""
    kind: str
    has_coverage: bool
    report: str  # relative URL to the coverage report
    summary_path: Optional[str] = None
    summary: Optional[Summary] = None


@dataclass
class ModuleEntry:
    """One module in the catalog, with coverage data per kind."""
    path: str
    has_ut: bool
    kinds: dict  # kind -> KindEntry  (field(default_factory=dict) below)

    @property
    def top_dir(self) -> str:
        return self.path.split("/", 1)[0] if "/" in self.path else self.path


@dataclass
class Group:
    """Modules grouped by their top-level directory (Fw, Svc, ...)."""
    name: str
    modules: List[ModuleEntry] = field(default_factory=list)

    def rollup(self, kind: str) -> Summary:
        """Sum-weighted rollup across all modules for a given kind."""
        entries = [
            m.kinds[kind].summary
            for m in self.modules
            if kind in m.kinds and m.kinds[kind].summary is not None
        ]
        line = Totals(
            covered=sum(e.line.covered for e in entries),
            total=sum(e.line.total for e in entries),
        )
        function = Totals(
            covered=sum(e.function.covered for e in entries),
            total=sum(e.function.total for e in entries),
        )
        branch = Totals(
            covered=sum(e.branch.covered for e in entries),
            total=sum(e.branch.total for e in entries),
        )
        return Summary(line=line, function=function, branch=branch)


def _group_modules(entries: Iterable[ModuleEntry]) -> List[Group]:
    groups: dict[str, Group] = {}
    for entry in entries:
        groups.setdefault(entry.top_dir, Group(name=entry.top_dir)).modules.append(entry)
    for g in groups.values():
        g.modules.sort(key=lambda m: m.path)
    return [groups[k] for k in sorted(groups.keys())]


def _render_cell_pct(pct: float, has_coverage: bool) -> str:
    if not has_coverage:
        return '<td class="num no-cov">&mdash;</td>'
    return f'<td class="num {_pct_class(pct, True)}">{pct:.2f}%</td>'


def _render_kind_row(mod: ModuleEntry, kind: str) -> str:
    """Render one table row for a module+kind combination."""
    ke = mod.kinds.get(kind)
    path_esc = html.escape(mod.path)
    kind_label = KIND_LABELS.get(kind, kind)

    if ke is not None and ke.has_coverage and ke.summary is not None:
        report_esc = html.escape(ke.report)
        line_html = _render_cell_pct(ke.summary.line.percent, True)
        function_html = _render_cell_pct(ke.summary.function.percent, True)
        branch_html = _render_cell_pct(ke.summary.branch.percent, True)
        name_cell = f'<a href="{report_esc}">{path_esc}</a>'
    elif ke is not None:
        report_esc = html.escape(ke.report)
        line_html = _render_cell_pct(0.0, False)
        function_html = _render_cell_pct(0.0, False)
        branch_html = _render_cell_pct(0.0, False)
        name_cell = f'<a href="{report_esc}">{path_esc}</a>'
    else:
        line_html = _render_cell_pct(0.0, False)
        function_html = _render_cell_pct(0.0, False)
        branch_html = _render_cell_pct(0.0, False)
        name_cell = path_esc

    note = ""
    if kind == "ut" and not mod.has_ut and (ke is None or not ke.has_coverage):
        note = ' <span class="no-ut">(no UT)</span>'

    return (
        f'<tr class="row">'
        f'<td>{name_cell}{note}</td>'
        f'<td class="kind-label">{html.escape(kind_label)}</td>'
        f"{line_html}{function_html}{branch_html}"
        f"</tr>"
    )


def _present_kinds(entries: List[ModuleEntry]) -> List[str]:
    """Return the list of kinds that have at least one module with data."""
    present = set()
    for entry in entries:
        for kind, ke in entry.kinds.items():
            if ke.has_coverage:
                present.add(kind)
    # Return in canonical order
    return [k for k in COVERAGE_KINDS if k in present]


def _render_group(group: Group, kinds: List[str]) -> str:
    open_attr = " open" if group.name in {"Fw", "Svc"} else ""

    # Build a compact summary string for the group header
    parts = [f"<strong>{html.escape(group.name)}/</strong>"]
    for kind in kinds:
        rollup = group.rollup(kind)
        has_cov = rollup.line.total > 0
        label = KIND_LABELS.get(kind, kind)
        if has_cov:
            cls = _pct_class(rollup.line.percent, True)
            parts.append(
                f'<span class="kind-label">{html.escape(label)}:</span> '
                f'<span class="{cls}">{rollup.line.percent:.2f}%</span>'
            )
        else:
            parts.append(
                f'<span class="kind-label">{html.escape(label)}:</span> '
                f'<span class="no-cov">&mdash;</span>'
            )
    header = " &middot; ".join(parts)

    rows: list[str] = []
    for mod in group.modules:
        for kind in kinds:
            rows.append(_render_kind_row(mod, kind))

    return (
        f"<details{open_attr}><summary>{header}</summary>"
        f'<table><thead><tr>'
        f'<th>Module</th><th>Kind</th>'
        f'<th class="num">Line</th><th class="num">Function</th><th class="num">Branch</th>'
        f'</tr></thead>'
        f"<tbody>{''.join(rows)}</tbody></table>"
        f"</details>"
    )


def _render_overall_kind(kind: str, summary: Optional[Summary], report_href: str) -> str:
    """Render one line of the overall section for a given kind."""
    label = KIND_LABELS.get(kind, kind)
    if summary is not None and summary.line.total > 0:
        return (
            f'<div class="overall-row">'
            f'<strong>{html.escape(label).title()}:</strong> '
            f'<span class="{_pct_class(summary.line.percent, True)}">{summary.line.percent:.2f}% line</span>, '
            f'<span class="{_pct_class(summary.function.percent, True)}">{summary.function.percent:.2f}% function</span>, '
            f'<span class="{_pct_class(summary.branch.percent, True)}">{summary.branch.percent:.2f}% branch</span>'
            f' &middot; <a href="{html.escape(report_href)}">full report &rarr;</a>'
            f"</div>"
        )
    return (
        f'<div class="overall-row">'
        f'<strong>{html.escape(label).title()}:</strong> '
        f'<span class="no-cov">no coverage data</span>'
        f"</div>"
    )


def render_index_html(
    *,
    ref: str,
    ref_type: str,
    commit: str,
    generated_at: str,
    overalls: dict,  # kind -> (Optional[Summary], report_href)
    entries: List[ModuleEntry],
) -> str:
    """Render the folder-tree catalog page with both UT and integration coverage."""
    kinds = _present_kinds(entries)
    # If no kind has data yet, show all known kinds so the page isn't empty
    if not kinds:
        kinds = list(COVERAGE_KINDS)

    groups = _group_modules(entries)

    overall_lines = []
    for kind in COVERAGE_KINDS:
        summary, report_href = overalls.get(kind, (None, ""))
        overall_lines.append(_render_overall_kind(kind, summary, report_href))
    overall_html = "\n".join(overall_lines)

    group_html = "\n".join(_render_group(g, kinds) for g in groups)

    return (
        "<!DOCTYPE html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        f"<title>F\u00b4 Coverage \u2014 {html.escape(ref)}</title>"
        f"<style>{CSS}</style></head><body>"
        f"<h1>F\u00b4 Coverage</h1>"
        f'<div class="meta">{html.escape(ref_type)} <code>{html.escape(ref)}</code> '
        f"@ <code>{html.escape(commit[:12])}</code> &middot; generated {html.escape(generated_at)}</div>"
        f'<div class="overall">{overall_html}</div>'
        f'<div class="section-title">Modules</div>'
        f"{group_html}"
        f"</body></html>\n"
    )


def build_catalog(
    *,
    modules: List[ModuleEntry],
    ref: str,
    ref_type: str,
    commit: str,
    generated_at: str,
    overalls: dict,  # kind -> (Optional[Summary], report_href)
) -> dict:
    out_modules = []
    for m in modules:
        entry: dict = {
            "path": m.path,
            "has_ut": m.has_ut,
        }
        for kind in COVERAGE_KINDS:
            ke = m.kinds.get(kind)
            kind_entry: dict = {"has_coverage": False}
            if ke is not None:
                kind_entry["has_coverage"] = ke.has_coverage
                kind_entry["report"] = ke.report
                if ke.summary_path is not None:
                    kind_entry["summary"] = ke.summary_path
                if ke.summary is not None:
                    kind_entry.update(ke.summary.to_catalog_entry())
            entry[kind] = kind_entry
        out_modules.append(entry)

    overall_entries = {}
    for kind in COVERAGE_KINDS:
        summary, report_href = overalls.get(kind, (None, ""))
        if summary is not None and summary.line.total > 0:
            oe = summary.to_catalog_entry()
            oe["report"] = report_href
            overall_entries[kind] = oe
        else:
            overall_entries[kind] = None

    return {
        "schema": SCHEMA_VERSION,
        "ref": ref,
        "ref_type": ref_type,
        "commit": commit,
        "generated_at": generated_at,
        "overall": overall_entries,
        "modules": out_modules,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dest", type=Path, required=True,
        help="Baseline worktree root (read both coverage kinds + write catalog)",
    )
    parser.add_argument(
        "--modules-jsonl",
        type=Path,
        required=True,
        help="JSON-Lines module list from discover.py",
    )
    parser.add_argument("--ref", required=True, help="Source ref name (branch or tag)")
    parser.add_argument("--ref-type", default="branch", choices=("branch", "tag"))
    parser.add_argument("--commit", required=True, help="Source commit SHA")
    parser.add_argument(
        "--generated-at",
        default=None,
        help="ISO8601 timestamp; defaults to now() UTC",
    )
    args = parser.parse_args(argv)

    dest = args.dest.resolve()
    dest.mkdir(parents=True, exist_ok=True)

    generated_at = args.generated_at or dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    entries: list[ModuleEntry] = []
    with args.modules_jsonl.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            path = rec["path"]
            has_ut = bool(rec.get("has_ut", False))

            kinds_dict: dict[str, KindEntry] = {}
            for kind in COVERAGE_KINDS:
                subdir = f"coverage-{kind}"
                summary_file = dest / path / subdir / "summary.json"
                summary = load_summary(summary_file)
                has_coverage = summary is not None and summary.line.total > 0
                report_path = f"{path}/{subdir}/coverage.html"
                summary_rel = f"{path}/{subdir}/summary.json" if has_coverage else None
                kinds_dict[kind] = KindEntry(
                    kind=kind,
                    has_coverage=has_coverage,
                    report=report_path,
                    summary_path=summary_rel,
                    summary=summary,
                )

            entries.append(ModuleEntry(path=path, has_ut=has_ut, kinds=kinds_dict))

    # Load global overalls for each kind
    overalls: dict[str, tuple] = {}
    for kind in COVERAGE_KINDS:
        subdir = f"coverage-{kind}"
        overall_summary = load_summary(dest / subdir / "summary.json")
        report_href = f"{subdir}/coverage-all.html"
        overalls[kind] = (overall_summary, report_href)

    catalog = build_catalog(
        modules=entries,
        ref=args.ref,
        ref_type=args.ref_type,
        commit=args.commit,
        generated_at=generated_at,
        overalls=overalls,
    )
    (dest / "catalog.json").write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")

    html_text = render_index_html(
        ref=args.ref,
        ref_type=args.ref_type,
        commit=args.commit,
        generated_at=generated_at,
        overalls=overalls,
        entries=entries,
    )
    (dest / "index.html").write_text(html_text, encoding="utf-8")

    print(f"catalog: wrote {dest/'catalog.json'} ({len(entries)} modules)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

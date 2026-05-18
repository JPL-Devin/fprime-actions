"""Generate ``catalog.json`` and the top-level folder-tree ``index.html``.

Inputs:
    * A list of discovered modules (path, has_ut) from ``discover.py``.
    * The working-tree root containing per-module ``<mod>/<coverage-subdir>/summary.json``
      and the global ``<coverage-subdir>/summary.json``.

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

SCHEMA_VERSION = 1

CSS = """\
* { box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  margin: 0; padding: 1.5rem; color: #1f2328; background: #ffffff;
}
h1 { margin: 0 0 0.25rem 0; font-size: 1.4rem; }
.meta { color: #57606a; font-size: 0.9rem; margin-bottom: 1rem; }
.overall {
  display: flex; gap: 1rem; align-items: baseline;
  padding: 0.75rem 1rem; background: #f6f8fa; border: 1px solid #d0d7de;
  border-radius: 6px; margin-bottom: 1rem;
}
.overall a { color: #0969da; text-decoration: none; }
.overall a:hover { text-decoration: underline; }
details { border: 1px solid #d0d7de; border-radius: 6px; margin-bottom: 0.5rem; background: #ffffff; }
details > summary {
  cursor: pointer; padding: 0.5rem 0.75rem; font-weight: 600;
  display: grid; grid-template-columns: 1fr 6rem 6rem 6rem; gap: 0.5rem;
  align-items: baseline; list-style: none;
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
class ModuleEntry:
    """One row in the catalog."""

    path: str  # e.g. "Svc/CmdDispatcher"
    has_ut: bool
    has_coverage: bool
    report: str  # relative URL inside the baseline branch
    summary_path: Optional[str] = None  # relative URL to summary.json
    summary: Optional[Summary] = None

    @property
    def top_dir(self) -> str:
        return self.path.split("/", 1)[0] if "/" in self.path else self.path


@dataclass
class Group:
    """Modules grouped by their top-level directory (Fw, Svc, ...)."""

    name: str
    modules: List[ModuleEntry] = field(default_factory=list)

    def rollup(self) -> Summary:
        """Sum-weighted rollup across all modules in the group."""
        line = Totals(
            covered=sum(m.summary.line.covered for m in self.modules if m.summary),
            total=sum(m.summary.line.total for m in self.modules if m.summary),
        )
        branch = Totals(
            covered=sum(m.summary.branch.covered for m in self.modules if m.summary),
            total=sum(m.summary.branch.total for m in self.modules if m.summary),
        )
        return Summary(line=line, branch=branch)


def _group_modules(entries: Iterable[ModuleEntry]) -> List[Group]:
    """Group entries by top-level directory, sorted alphabetically.

    Modules with no top-level component (paths without a ``/``) are placed in
    a synthetic ``"(root)"`` group.
    """
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


def _render_summary_row(label: str, line_pct: float, branch_pct: float, has_coverage: bool) -> str:
    label_esc = html.escape(label)
    line_cell = (
        f'<span class="num {_pct_class(line_pct, has_coverage)}">{line_pct:.2f}%</span>'
        if has_coverage
        else '<span class="num no-cov">&mdash;</span>'
    )
    branch_cell = (
        f'<span class="num {_pct_class(branch_pct, has_coverage)}">{branch_pct:.2f}%</span>'
        if has_coverage
        else '<span class="num no-cov">&mdash;</span>'
    )
    return f"<span>{label_esc}</span>{line_cell}{branch_cell}<span></span>"


def _render_group(group: Group) -> str:
    rollup = group.rollup()
    has_coverage = rollup.line.total > 0
    open_attr = " open" if group.name in {"Fw", "Svc"} else ""
    header = _render_summary_row(group.name + "/", rollup.line.percent, rollup.branch.percent, has_coverage)

    rows: list[str] = []
    for mod in group.modules:
        path_esc = html.escape(mod.path)
        report_esc = html.escape(mod.report)
        if mod.has_coverage and mod.summary is not None:
            line_html = _render_cell_pct(mod.summary.line.percent, True)
            branch_html = _render_cell_pct(mod.summary.branch.percent, True)
            note = ""
        else:
            line_html = _render_cell_pct(0.0, False)
            branch_html = _render_cell_pct(0.0, False)
            note = '<span class="no-ut">(no UT)</span>' if not mod.has_ut else '<span class="no-cov">(no coverage)</span>'
        rows.append(
            f'<tr class="row">'
            f'<td><a href="{report_esc}">{path_esc}</a> {note}</td>'
            f"{line_html}{branch_html}"
            f"</tr>"
        )

    return (
        f"<details{open_attr}><summary>{header}</summary>"
        f'<table><thead><tr><th>Module</th><th class="num">Line</th><th class="num">Branch</th></tr></thead>'
        f"<tbody>{''.join(rows)}</tbody></table>"
        f"</details>"
    )


def render_index_html(
    *,
    ref: str,
    ref_type: str,
    commit: str,
    generated_at: str,
    overall: Optional[Summary],
    overall_report: str,
    entries: List[ModuleEntry],
) -> str:
    """Render the folder-tree catalog page."""
    groups = _group_modules(entries)

    if overall is not None and overall.line.total > 0:
        overall_text = (
            f'<strong>Overall:</strong> '
            f'<span class="{_pct_class(overall.line.percent, True)}">{overall.line.percent:.2f}% line</span>, '
            f'<span class="{_pct_class(overall.branch.percent, True)}">{overall.branch.percent:.2f}% branch</span>'
        )
    else:
        overall_text = '<strong>Overall:</strong> <span class="no-cov">no coverage data</span>'
    overall_link = (
        f'&middot; <a href="{html.escape(overall_report)}">full report &rarr;</a>'
        if overall is not None
        else ""
    )

    group_html = "\n".join(_render_group(g) for g in groups)

    return (
        "<!DOCTYPE html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        f"<title>F\u00b4 Coverage \u2014 {html.escape(ref)}</title>"
        f"<style>{CSS}</style></head><body>"
        f"<h1>F\u00b4 Coverage</h1>"
        f'<div class="meta">{html.escape(ref_type)} <code>{html.escape(ref)}</code> '
        f"@ <code>{html.escape(commit[:12])}</code> &middot; generated {html.escape(generated_at)}</div>"
        f'<div class="overall">{overall_text} {overall_link}</div>'
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
    overall: Optional[Summary],
    overall_report: str,
) -> dict:
    out_modules = []
    for m in modules:
        entry = {
            "path": m.path,
            "has_ut": m.has_ut,
            "has_coverage": m.has_coverage,
            "report": m.report,
        }
        if m.summary_path is not None:
            entry["summary"] = m.summary_path
        if m.summary is not None:
            entry.update(m.summary.to_catalog_entry())
        out_modules.append(entry)

    overall_entry = None
    if overall is not None and overall.line.total > 0:
        overall_entry = overall.to_catalog_entry()
        overall_entry["report"] = overall_report

    return {
        "schema": SCHEMA_VERSION,
        "ref": ref,
        "ref_type": ref_type,
        "commit": commit,
        "generated_at": generated_at,
        "overall": overall_entry,
        "modules": out_modules,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="Working-tree root containing module dirs")
    parser.add_argument("--dest", type=Path, required=True, help="Where to write catalog.json + index.html")
    parser.add_argument(
        "--modules-jsonl",
        type=Path,
        required=True,
        help="JSON-Lines module list from discover.py",
    )
    parser.add_argument(
        "--coverage-subdirectory",
        default="coverage",
        help="Subdirectory under each module holding coverage artifacts; "
        '"" flattens (default: "coverage")',
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

    source = args.source.resolve()
    dest = args.dest.resolve()
    dest.mkdir(parents=True, exist_ok=True)

    subdir = args.coverage_subdirectory
    subdir_segment = f"{subdir}/" if subdir else ""

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
            mod_summary_path = source / path / "coverage" / "summary.json"
            summary = load_summary(mod_summary_path) if has_ut else None
            has_coverage = summary is not None and summary.line.total > 0
            report_path = f"{path}/{subdir_segment}index.html"
            summary_rel = f"{path}/{subdir_segment}summary.json" if has_coverage else None
            entries.append(
                ModuleEntry(
                    path=path,
                    has_ut=has_ut,
                    has_coverage=has_coverage,
                    report=report_path,
                    summary_path=summary_rel,
                    summary=summary,
                )
            )

    overall_summary = load_summary(source / "coverage" / "summary.json")
    overall_report = f"{subdir_segment}coverage-all.html" if subdir else "coverage-all.html"

    catalog = build_catalog(
        modules=entries,
        ref=args.ref,
        ref_type=args.ref_type,
        commit=args.commit,
        generated_at=generated_at,
        overall=overall_summary,
        overall_report=overall_report,
    )
    (dest / "catalog.json").write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")

    html_text = render_index_html(
        ref=args.ref,
        ref_type=args.ref_type,
        commit=args.commit,
        generated_at=generated_at,
        overall=overall_summary,
        overall_report=overall_report,
        entries=entries,
    )
    (dest / "index.html").write_text(html_text, encoding="utf-8")

    print(f"catalog: wrote {dest/'catalog.json'} ({len(entries)} modules)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

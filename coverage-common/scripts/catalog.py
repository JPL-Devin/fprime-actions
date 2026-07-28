"""Generate ``catalog.json`` and the top-level checklist ``index.html``.

Inputs:
    * A list of discovered modules (path, has_ut) from ``discover.py``.
    * The baseline-branch worktree (``--dest``), which holds whatever
      artifact subtrees have been published so far:
          <mod>/<coverage-subdir>/summary.json       UT coverage
          <mod>/<int-coverage-subdir>/summary.json   integration coverage
          <mod>/<codeql-subdir>/summary.json         CodeQL findings

Outputs (written to ``--dest``):
    * ``catalog.json`` -- machine-readable; see ``schema`` field for version.
    * ``index.html``   -- self-contained checklist landing page: one row per
      module with a link + tier badge (platinum/gold/silver/bronze) per
      artifact type.

Because all inputs are read from ``--dest`` (the baseline branch itself),
regeneration is idempotent and order-independent: any publisher (coverage,
int-coverage, codeql) can rerun this script after mirroring its own subtree
and the page reflects the union of everything on the branch.

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

from _config import coverage_thresholds, load_config
from _summary import Summary, Totals, load_summary
from _tiers import CoverageThresholds, codeql_tier, coverage_tier

SCHEMA_VERSION = 2

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
details { border: 1px solid #d0d7de; border-radius: 6px; margin-bottom: 0.5rem; background: #ffffff; }
details > summary {
  cursor: pointer; padding: 0.5rem 0.75rem; font-weight: 600;
  display: grid; grid-template-columns: 1fr 11rem 11rem 11rem; gap: 0.5rem;
  align-items: baseline; list-style: none;
}
details > summary::-webkit-details-marker { display: none; }
details > summary::before { content: "\\25B6"; display: inline-block; margin-right: 0.4rem; transition: transform 0.1s; }
details[open] > summary::before { transform: rotate(90deg); }
table { width: 100%; border-collapse: collapse; }
table th, table td { padding: 0.35rem 0.75rem; text-align: left; }
table th { font-weight: 500; color: #57606a; font-size: 0.85rem; border-bottom: 1px solid #eaeef2; }
table td.cell, table th.cell { width: 11rem; white-space: nowrap; }
table tr.row { border-top: 1px solid #eaeef2; }
table tr.row:hover { background: #f6f8fa; }
table a { color: #0969da; text-decoration: none; }
table a:hover { text-decoration: underline; }
.badge {
  display: inline-block; padding: 0.05rem 0.55rem; border-radius: 2em;
  font-size: 0.78rem; font-weight: 600; border: 1px solid transparent;
  vertical-align: baseline;
}
.badge-platinum { background: #eef1f4; color: #24292f; border-color: #afb8c1; }
.badge-gold     { background: #fff3c4; color: #7d5a00; border-color: #d4af37; }
.badge-silver   { background: #f0f0f0; color: #57606a; border-color: #c0c0c0; }
.badge-bronze   { background: #f5e0d1; color: #8a4412; border-color: #cd7f32; }
.no-ut, .no-cov { color: #6e7781; font-style: italic; font-size: 0.85rem; }
.section-title { margin: 1.25rem 0 0.5rem 0; font-size: 1.05rem; }
"""

TIER_LABELS = {
    "platinum": "Platinum",
    "gold": "Gold",
    "silver": "Silver",
    "bronze": "Bronze",
}


def badge_html(tier: str) -> str:
    return f'<span class="badge badge-{tier}">{TIER_LABELS[tier]}</span>'


def load_codeql_summary(path: Path) -> Optional[dict]:
    """Load a codeql summary.json, returning None on failure."""
    if not path.is_file():
        return None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(doc, dict) or "findings" not in doc:
        return None
    return doc


@dataclass
class ModuleEntry:
    """One row in the catalog."""

    path: str  # e.g. "Svc/CmdDispatcher"
    has_ut: bool
    ut_summary: Optional[Summary]
    ut_report: str
    int_summary: Optional[Summary]
    int_report: str
    codeql_summary: Optional[dict]
    codeql_report: str

    @property
    def top_dir(self) -> str:
        return self.path.split("/", 1)[0] if "/" in self.path else self.path

    @property
    def has_coverage(self) -> bool:
        return self.ut_summary is not None and self.ut_summary.line.total > 0

    @property
    def has_int_coverage(self) -> bool:
        return self.int_summary is not None and self.int_summary.line.total > 0


@dataclass
class Group:
    """Modules grouped by their top-level directory (Fw, Svc, ...)."""

    name: str
    modules: List[ModuleEntry] = field(default_factory=list)

    def rollup(self) -> Summary:
        """Sum-weighted rollup across all modules in the group."""
        line = Totals(
            covered=sum(m.ut_summary.line.covered for m in self.modules if m.ut_summary),
            total=sum(m.ut_summary.line.total for m in self.modules if m.ut_summary),
        )
        function = Totals(
            covered=sum(m.ut_summary.function.covered for m in self.modules if m.ut_summary),
            total=sum(m.ut_summary.function.total for m in self.modules if m.ut_summary),
        )
        branch = Totals(
            covered=sum(m.ut_summary.branch.covered for m in self.modules if m.ut_summary),
            total=sum(m.ut_summary.branch.total for m in self.modules if m.ut_summary),
        )
        return Summary(line=line, function=function, branch=branch)

    def codeql_worst(self) -> tuple[bool, Optional[str]]:
        """(any codeql data present, worst severity across modules)."""
        present = False
        worst_rank = None
        order = {"error": 0, "medium": 1, "low": 2}
        for m in self.modules:
            if m.codeql_summary is None:
                continue
            present = True
            worst = m.codeql_summary.get("worst")
            if worst in order and (worst_rank is None or order[worst] < order[worst_rank]):
                worst_rank = worst
        return present, worst_rank


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


def _coverage_cell(
    summary: Optional[Summary],
    has_coverage: bool,
    report: str,
    thresholds: CoverageThresholds,
    *,
    missing_note: str,
) -> str:
    if not has_coverage:
        tier = coverage_tier(0.0, False, thresholds)
        return f'{badge_html(tier)} <span class="no-cov">{html.escape(missing_note)}</span>'
    tier = coverage_tier(summary.line.percent, True, thresholds)
    return (
        f'{badge_html(tier)} '
        f'<a href="{html.escape(report)}">{summary.line.percent:.2f}%</a>'
    )


def _int_cell(entry: ModuleEntry, thresholds: CoverageThresholds) -> str:
    if entry.int_summary is None:
        return '<span class="no-cov">&mdash;</span>'
    return _coverage_cell(
        entry.int_summary, entry.has_int_coverage, entry.int_report, thresholds,
        missing_note="no coverage",
    )


def _codeql_cell(entry: ModuleEntry) -> str:
    if entry.codeql_summary is None:
        return '<span class="no-cov">&mdash;</span>'
    count = int(entry.codeql_summary.get("findings", 0))
    tier = codeql_tier(entry.codeql_summary.get("worst"))
    label = "clean" if count == 0 else f"{count} finding{'s' if count != 1 else ''}"
    return f'{badge_html(tier)} <a href="{html.escape(entry.codeql_report)}">{label}</a>'


def _render_group_header(group: Group, thresholds: CoverageThresholds) -> str:
    rollup = group.rollup()
    has_coverage = rollup.line.total > 0
    label_esc = html.escape(group.name + "/")
    if has_coverage:
        ut_tier = coverage_tier(rollup.line.percent, True, thresholds)
        ut_html = f"{badge_html(ut_tier)} {rollup.line.percent:.2f}%"
    else:
        ut_html = f'{badge_html("bronze")} <span class="no-cov">&mdash;</span>'
    int_html = '<span class="no-cov">&mdash;</span>'
    present, worst = group.codeql_worst()
    codeql_html = badge_html(codeql_tier(worst)) if present else '<span class="no-cov">&mdash;</span>'
    return f"<span>{label_esc}</span><span>{ut_html}</span><span>{int_html}</span><span>{codeql_html}</span>"


def _render_group(group: Group, thresholds: CoverageThresholds) -> str:
    open_attr = " open" if group.name in {"Fw", "Svc"} else ""
    header = _render_group_header(group, thresholds)

    rows: list[str] = []
    for mod in group.modules:
        path_esc = html.escape(mod.path)
        missing_note = "no UT" if not mod.has_ut else "no coverage"
        ut_html = _coverage_cell(
            mod.ut_summary, mod.has_coverage, mod.ut_report, thresholds,
            missing_note=missing_note,
        )
        rows.append(
            f'<tr class="row">'
            f'<td><a href="{html.escape(mod.ut_report)}">{path_esc}</a></td>'
            f'<td class="cell">{ut_html}</td>'
            f'<td class="cell">{_int_cell(mod, thresholds)}</td>'
            f'<td class="cell">{_codeql_cell(mod)}</td>'
            f"</tr>"
        )

    return (
        f"<details{open_attr}><summary>{header}</summary>"
        f'<table><thead><tr><th>Module</th><th class="cell">UT Coverage</th>'
        f'<th class="cell">INT Coverage</th><th class="cell">CodeQL</th></tr></thead>'
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
    overall_codeql: Optional[dict],
    overall_codeql_report: str,
    entries: List[ModuleEntry],
    thresholds: CoverageThresholds,
) -> str:
    """Render the checklist landing page."""
    groups = _group_modules(entries)

    parts = []
    if overall is not None and overall.line.total > 0:
        tier = coverage_tier(overall.line.percent, True, thresholds)
        parts.append(
            f"<strong>UT coverage:</strong> {badge_html(tier)} "
            f'<a href="{html.escape(overall_report)}">{overall.line.percent:.2f}% line</a> '
            f"({overall.function.percent:.2f}% function, {overall.branch.percent:.2f}% branch)"
        )
    else:
        parts.append('<strong>UT coverage:</strong> <span class="no-cov">no data</span>')
    parts.append('<strong>INT coverage:</strong> <span class="no-cov">no data</span>')
    if overall_codeql is not None:
        count = int(overall_codeql.get("findings", 0))
        tier = codeql_tier(overall_codeql.get("worst"))
        label = "clean" if count == 0 else f"{count} finding{'s' if count != 1 else ''}"
        parts.append(
            f"<strong>CodeQL:</strong> {badge_html(tier)} "
            f'<a href="{html.escape(overall_codeql_report)}">{label}</a>'
        )
    else:
        parts.append('<strong>CodeQL:</strong> <span class="no-cov">no data</span>')
    overall_html = " &middot; ".join(f"<span>{p}</span>" for p in parts)

    group_html = "\n".join(_render_group(g, thresholds) for g in groups)

    return (
        "<!DOCTYPE html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        f"<title>F\u00b4 Module Checklist \u2014 {html.escape(ref)}</title>"
        f"<style>{CSS}</style></head><body>"
        f"<h1>F\u00b4 Module Checklist</h1>"
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
    overall: Optional[Summary],
    overall_report: str,
    overall_codeql: Optional[dict],
    overall_codeql_report: str,
    thresholds: CoverageThresholds,
) -> dict:
    out_modules = []
    for m in modules:
        ut_entry = None
        if m.has_coverage:
            ut_entry = m.ut_summary.to_catalog_entry()
        if ut_entry is not None:
            ut_entry["report"] = m.ut_report
            ut_entry["tier"] = coverage_tier(m.ut_summary.line.percent, True, thresholds)
        int_entry = None
        if m.has_int_coverage:
            int_entry = m.int_summary.to_catalog_entry()
            int_entry["report"] = m.int_report
            int_entry["tier"] = coverage_tier(m.int_summary.line.percent, True, thresholds)
        codeql_entry = None
        if m.codeql_summary is not None:
            codeql_entry = dict(m.codeql_summary)
            codeql_entry["report"] = m.codeql_report
            codeql_entry.setdefault("tier", codeql_tier(m.codeql_summary.get("worst")))
        out_modules.append(
            {
                "path": m.path,
                "has_ut": m.has_ut,
                "has_coverage": m.has_coverage,
                "ut": ut_entry,
                "int": int_entry,
                "codeql": codeql_entry,
                "tiers": {
                    "ut": coverage_tier(
                        m.ut_summary.line.percent if m.has_coverage else 0.0,
                        m.has_coverage,
                        thresholds,
                    ),
                    "int": (
                        coverage_tier(m.int_summary.line.percent, True, thresholds)
                        if m.has_int_coverage
                        else None
                    ),
                    "codeql": (
                        codeql_tier(m.codeql_summary.get("worst"))
                        if m.codeql_summary is not None
                        else None
                    ),
                },
            }
        )

    overall_entry = None
    if overall is not None and overall.line.total > 0:
        overall_entry = overall.to_catalog_entry()
        overall_entry["report"] = overall_report
        overall_entry["tier"] = coverage_tier(overall.line.percent, True, thresholds)

    overall_codeql_entry = None
    if overall_codeql is not None:
        overall_codeql_entry = dict(overall_codeql)
        overall_codeql_entry["report"] = overall_codeql_report

    return {
        "schema": SCHEMA_VERSION,
        "ref": ref,
        "ref_type": ref_type,
        "commit": commit,
        "generated_at": generated_at,
        "thresholds": {
            "platinum": thresholds.platinum,
            "gold": thresholds.gold,
            "silver": thresholds.silver,
        },
        "overall": overall_entry,
        "overall_codeql": overall_codeql_entry,
        "modules": out_modules,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dest", type=Path, required=True,
        help="Baseline worktree root; summaries are read from and outputs written to it",
    )
    parser.add_argument(
        "--modules-jsonl",
        type=Path,
        required=True,
        help="JSON-Lines module list from discover.py",
    )
    parser.add_argument(
        "--coverage-subdirectory",
        default="coverage",
        help="Subdirectory under each module holding UT coverage artifacts; "
        '"" flattens (default: "coverage")',
    )
    parser.add_argument(
        "--int-coverage-subdirectory",
        default="int-coverage",
        help='Subdirectory under each module holding integration coverage (default: "int-coverage")',
    )
    parser.add_argument(
        "--codeql-subdirectory",
        default="codeql",
        help='Subdirectory under each module holding CodeQL findings (default: "codeql")',
    )
    parser.add_argument("--ref", required=True, help="Source ref name (branch or tag)")
    parser.add_argument("--ref-type", default="branch", choices=("branch", "tag"))
    parser.add_argument("--commit", required=True, help="Source commit SHA")
    parser.add_argument(
        "--generated-at",
        default=None,
        help="ISO8601 timestamp; defaults to now() UTC",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Checklist config file (e.g. .github/module-checklist.yml); "
        "defaults apply when omitted or missing",
    )
    args = parser.parse_args(argv)

    dest = args.dest.resolve()
    dest.mkdir(parents=True, exist_ok=True)

    subdir = args.coverage_subdirectory
    subdir_segment = f"{subdir}/" if subdir else ""
    int_subdir = args.int_coverage_subdirectory or "int-coverage"
    codeql_subdir = args.codeql_subdirectory or "codeql"
    thresholds = coverage_thresholds(load_config(args.config))

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
            mod_dir = dest / path
            ut_summary = load_summary(
                (mod_dir / subdir if subdir else mod_dir) / "summary.json"
            )
            int_summary = load_summary(mod_dir / int_subdir / "summary.json")
            codeql_summary = load_codeql_summary(mod_dir / codeql_subdir / "summary.json")
            entries.append(
                ModuleEntry(
                    path=path,
                    has_ut=has_ut,
                    ut_summary=ut_summary,
                    ut_report=f"{path}/{subdir_segment}index.html",
                    int_summary=int_summary,
                    int_report=f"{path}/{int_subdir}/index.html",
                    codeql_summary=codeql_summary,
                    codeql_report=f"{path}/{codeql_subdir}/index.html",
                )
            )

    overall_dir = dest / subdir if subdir else dest
    overall_summary = load_summary(overall_dir / "summary.json")
    overall_report = f"{subdir_segment}coverage-all.html" if subdir else "coverage-all.html"
    overall_codeql = load_codeql_summary(dest / codeql_subdir / "summary.json")
    overall_codeql_report = f"{codeql_subdir}/index.html"

    catalog = build_catalog(
        modules=entries,
        ref=args.ref,
        ref_type=args.ref_type,
        commit=args.commit,
        generated_at=generated_at,
        overall=overall_summary,
        overall_report=overall_report,
        overall_codeql=overall_codeql,
        overall_codeql_report=overall_codeql_report,
        thresholds=thresholds,
    )
    (dest / "catalog.json").write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")

    html_text = render_index_html(
        ref=args.ref,
        ref_type=args.ref_type,
        commit=args.commit,
        generated_at=generated_at,
        overall=overall_summary,
        overall_report=overall_report,
        overall_codeql=overall_codeql,
        overall_codeql_report=overall_codeql_report,
        entries=entries,
        thresholds=thresholds,
    )
    (dest / "index.html").write_text(html_text, encoding="utf-8")

    print(f"catalog: wrote {dest/'catalog.json'} ({len(entries)} modules)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

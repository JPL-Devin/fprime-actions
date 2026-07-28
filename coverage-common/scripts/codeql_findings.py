"""Mirror CodeQL SARIF findings into the baseline worktree, per module.

Consumes one or more (already filtered) SARIF files and the module list
from ``discover.py``, maps each finding to its owning module by
longest-prefix match on the result's file path, and writes:

    <dest>/<mod>/<codeql-subdir>/index.html    findings table (or "clean" page)
    <dest>/<mod>/<codeql-subdir>/summary.json  {"findings": N, "by_severity": ..., "worst": ...}
    <dest>/<codeql-subdir>/index.html          all findings (incl. unmapped paths)
    <dest>/<codeql-subdir>/summary.json        global counts

Severities are normalized to error / medium / low (see ``_tiers.py``).
Findings whose file path does not fall under any discovered module are
kept on the global page only, attributed to ``(other)``.

Alerts dismissed in the GitHub UI (fetched by ``fetch_dismissed_alerts.py``)
are subtracted from the active findings (matched on rule + path, with line
tolerance for drift between the dismissal commit and HEAD) and listed in a
separate "dismissed" table with their dismissal reason and comment.  Tiers
are computed from active findings only.

Like ``mirror.py`` this script is idempotent: it deletes each module's
codeql directory before writing so re-runs cannot leave stale findings.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import shutil
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

from _tiers import codeql_tier, normalize_severity

PAGE_CSS = """\
* { box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  margin: 0; padding: 1.5rem; color: #1f2328; background: #ffffff;
}
h1 { margin: 0 0 0.25rem 0; font-size: 1.2rem; }
.meta { color: #57606a; font-size: 0.9rem; margin-bottom: 1rem; }
table { width: 100%; border-collapse: collapse; }
table th, table td { padding: 0.35rem 0.6rem; text-align: left; vertical-align: top; }
table th { font-weight: 500; color: #57606a; font-size: 0.85rem; border-bottom: 1px solid #eaeef2; }
table tr { border-top: 1px solid #eaeef2; }
table tr:hover { background: #f6f8fa; }
table a { color: #0969da; text-decoration: none; }
table a:hover { text-decoration: underline; }
.sev-error  { color: #cf222e; font-weight: 600; }
.sev-medium { color: #9a6700; font-weight: 600; }
.sev-low    { color: #57606a; }
.clean { padding: 0.75rem 1rem; background: #dafbe1; border: 1px solid #aceebb;
         border-radius: 6px; color: #1a7f37; }
h2 { margin: 1.5rem 0 0.5rem 0; font-size: 1.05rem; }
.dismissed td { color: #57606a; }
"""

SEVERITY_RANK = {"error": 0, "medium": 1, "low": 2}

# Dismissals are matched on rule + path with this much line drift allowed
# (line numbers move between the dismissal commit and the analyzed HEAD).
DISMISS_LINE_TOLERANCE = 5


@dataclass(frozen=True)
class Finding:
    path: str  # repo-relative file path (POSIX)
    line: int
    rule: str
    severity: str  # normalized: error | medium | low
    message: str
    module: Optional[str]  # owning module path, or None for "(other)"


def _rule_index(run: dict) -> dict:
    """Map ruleId -> rule object for a SARIF run."""
    rules = {}
    driver = run.get("tool", {}).get("driver", {})
    for rule in driver.get("rules", []) or []:
        if rule.get("id"):
            rules[rule["id"]] = rule
    for ext in run.get("tool", {}).get("extensions", []) or []:
        for rule in ext.get("rules", []) or []:
            rules.setdefault(rule.get("id"), rule)
    return rules


def _rule_severity(rule: Optional[dict], result_level: str) -> str:
    """Normalized severity for a result, preferring security-severity."""
    security_severity = None
    level = result_level
    if rule:
        props = rule.get("properties", {}) or {}
        raw = props.get("security-severity")
        if raw is not None:
            try:
                security_severity = float(raw)
            except (TypeError, ValueError):
                security_severity = None
        if not level:
            level = (rule.get("defaultConfiguration", {}) or {}).get("level", "")
        if security_severity is None and not level:
            level = props.get("problem.severity", "")
    return normalize_severity(level, security_severity)


def _result_location(result: dict) -> tuple[Optional[str], int]:
    for loc in result.get("locations", []) or []:
        phys = loc.get("physicalLocation", {}) or {}
        uri = (phys.get("artifactLocation", {}) or {}).get("uri")
        if uri:
            line = int((phys.get("region", {}) or {}).get("startLine", 0) or 0)
            return uri.lstrip("/"), line
    return None, 0


@dataclass(frozen=True)
class DismissedAlert:
    path: str
    line: int
    rule: str
    reason: str
    comment: str
    module: Optional[str]


def load_dismissed_alerts(path: Optional[Path], module_paths: List[str]) -> List[DismissedAlert]:
    if path is None or not path.is_file():
        return []
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"codeql_findings: bad dismissed-alerts file {path}: {exc}", file=sys.stderr)
        return []
    dismissed = []
    for e in entries if isinstance(entries, list) else []:
        rule = e.get("rule") or ""
        epath = (e.get("path") or "").lstrip("/")
        if not rule or not epath:
            continue
        dismissed.append(
            DismissedAlert(
                path=epath,
                line=int(e.get("line") or 0),
                rule=rule,
                reason=e.get("reason") or "",
                comment=e.get("comment") or "",
                module=_owning_module(epath, module_paths),
            )
        )
    dismissed.sort(key=lambda d: (d.path, d.line, d.rule))
    return dismissed


def _is_dismissed(finding: "Finding", dismissed: List[DismissedAlert]) -> bool:
    for d in dismissed:
        if d.rule == finding.rule and d.path == finding.path:
            if d.line == 0 or finding.line == 0:
                return True
            if abs(d.line - finding.line) <= DISMISS_LINE_TOLERANCE:
                return True
    return False


def filter_dismissed(
    findings: List[Finding], dismissed: List[DismissedAlert]
) -> List[Finding]:
    """Active findings only: subtract anything matching a dismissed alert."""
    if not dismissed:
        return findings
    return [f for f in findings if not _is_dismissed(f, dismissed)]


def _owning_module(path: str, module_paths: List[str]) -> Optional[str]:
    """Longest-prefix match of a file path onto the module list."""
    best = None
    for mod in module_paths:
        if path == mod or path.startswith(mod + "/"):
            if best is None or len(mod) > len(best):
                best = mod
    return best


def parse_sarif_files(sarif_paths: Iterable[Path], module_paths: List[str]) -> List[Finding]:
    findings: list[Finding] = []
    for sarif_path in sarif_paths:
        doc = json.loads(sarif_path.read_text(encoding="utf-8"))
        for run in doc.get("runs", []) or []:
            rules = _rule_index(run)
            for result in run.get("results", []) or []:
                rule_id = result.get("ruleId", "") or ""
                path, line = _result_location(result)
                if path is None:
                    continue
                severity = _rule_severity(rules.get(rule_id), result.get("level", ""))
                message = (result.get("message", {}) or {}).get("text", "") or ""
                findings.append(
                    Finding(
                        path=path,
                        line=line,
                        rule=rule_id,
                        severity=severity,
                        message=message,
                        module=_owning_module(path, module_paths),
                    )
                )
    findings.sort(key=lambda f: (SEVERITY_RANK[f.severity], f.path, f.line, f.rule))
    return findings


def summarize(findings: List[Finding], dismissed_count: int = 0) -> dict:
    by_severity = {"error": 0, "medium": 0, "low": 0}
    for f in findings:
        by_severity[f.severity] += 1
    worst = None
    for sev in ("error", "medium", "low"):
        if by_severity[sev] > 0:
            worst = sev
            break
    return {
        "findings": len(findings),
        "by_severity": by_severity,
        "worst": worst,
        "tier": codeql_tier(worst),
        "dismissed": dismissed_count,
    }


def _blob_url(repo_url: str, commit: str, path: str, line: int) -> Optional[str]:
    if not repo_url or not commit:
        return None
    anchor = f"#L{line}" if line > 0 else ""
    return f"{repo_url.rstrip('/')}/blob/{commit}/{path}{anchor}"


def _dismissed_table_html(
    dismissed: List[DismissedAlert], repo_url: str, commit: str, show_module_column: bool
) -> str:
    if not dismissed:
        return ""
    module_th = "<th>Module</th>" if show_module_column else ""
    rows = []
    for d in dismissed:
        url = _blob_url(repo_url, commit, d.path, d.line)
        loc = html.escape(d.path)
        loc_html = f'<a href="{html.escape(url)}">{loc}</a>' if url else loc
        module_td = (
            f"<td>{html.escape(d.module or '(other)')}</td>" if show_module_column else ""
        )
        rows.append(
            f'<tr class="dismissed">{module_td}'
            f"<td>{loc_html}</td>"
            f"<td>{d.line if d.line else '&mdash;'}</td>"
            f"<td><code>{html.escape(d.rule)}</code></td>"
            f"<td>{html.escape(d.reason) or '&mdash;'}</td>"
            f"<td>{html.escape(d.comment) or '&mdash;'}</td></tr>"
        )
    return (
        f"<h2>Dismissed findings ({len(dismissed)})</h2>"
        f"<table><thead><tr>{module_th}<th>File</th><th>Line</th><th>Rule</th>"
        "<th>Dismissal reason</th><th>Comment</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def render_findings_html(
    *,
    title: str,
    findings: List[Finding],
    ref: str,
    commit: str,
    generated_at: str,
    repo_url: str,
    show_module_column: bool,
    dismissed: Optional[List[DismissedAlert]] = None,
) -> str:
    head = (
        "<!DOCTYPE html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        f"<title>CodeQL \u2014 {html.escape(title)}</title>"
        f"<style>{PAGE_CSS}</style></head><body>"
        f"<h1>CodeQL findings \u2014 <code>{html.escape(title)}</code></h1>"
        f'<div class="meta"><code>{html.escape(ref)}</code> @ '
        f"<code>{html.escape(commit[:12])}</code> &middot; generated {html.escape(generated_at)}</div>"
    )
    dismissed_html = _dismissed_table_html(
        dismissed or [], repo_url, commit, show_module_column
    )
    if not findings:
        return (
            head
            + '<div class="clean">No active CodeQL findings. Clean.</div>'
            + dismissed_html
            + "</body></html>\n"
        )

    module_th = "<th>Module</th>" if show_module_column else ""
    rows = []
    for f in findings:
        url = _blob_url(repo_url, commit, f.path, f.line)
        loc = f"{html.escape(f.path)}:{f.line}" if f.line else html.escape(f.path)
        loc_html = f'<a href="{html.escape(url)}">{loc}</a>' if url else loc
        module_td = (
            f"<td>{html.escape(f.module or '(other)')}</td>" if show_module_column else ""
        )
        rows.append(
            f"<tr>{module_td}"
            f"<td>{loc_html}</td>"
            f"<td>{f.line if f.line else '&mdash;'}</td>"
            f"<td><code>{html.escape(f.rule)}</code></td>"
            f'<td class="sev-{f.severity}">{f.severity}</td>'
            f"<td>{html.escape(f.message)}</td></tr>"
        )
    return (
        head
        + f"<table><thead><tr>{module_th}<th>File</th><th>Line</th><th>Rule</th>"
        "<th>Severity</th><th>Message</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
        + dismissed_html
        + "</body></html>\n"
    )


def _clean_dir(path: Path) -> None:
    if path.exists():
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink()
    path.mkdir(parents=True, exist_ok=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sarif", type=Path, action="append", required=True,
        help="Filtered SARIF file (repeatable)",
    )
    parser.add_argument("--dest", type=Path, required=True, help="Baseline worktree root")
    parser.add_argument(
        "--modules-jsonl", type=Path, required=True,
        help="JSON-Lines module list from discover.py",
    )
    parser.add_argument("--codeql-subdirectory", default="codeql")
    parser.add_argument("--repo-url", default="", help="e.g. https://github.com/org/repo")
    parser.add_argument(
        "--dismissed-alerts", type=Path, default=None,
        help="JSON list of dismissed alerts from fetch_dismissed_alerts.py",
    )
    parser.add_argument("--ref", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--generated-at", default=None)
    args = parser.parse_args(argv)

    dest = args.dest.resolve()
    dest.mkdir(parents=True, exist_ok=True)
    subdir = args.codeql_subdirectory or "codeql"
    generated_at = args.generated_at or dt.datetime.now(dt.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )

    with args.modules_jsonl.open("r", encoding="utf-8") as fh:
        module_paths = [json.loads(line)["path"] for line in fh if line.strip()]

    sarif_files = [p for p in args.sarif if p.is_file()]
    missing = [str(p) for p in args.sarif if not p.is_file()]
    if missing:
        print(f"codeql_findings: missing SARIF file(s): {missing}", file=sys.stderr)
    if not sarif_files:
        print("codeql_findings: no SARIF files found", file=sys.stderr)
        return 2

    all_findings = parse_sarif_files(sarif_files, module_paths)
    dismissed = load_dismissed_alerts(args.dismissed_alerts, module_paths)
    findings = filter_dismissed(all_findings, dismissed)
    by_module: dict[Optional[str], list[Finding]] = defaultdict(list)
    for f in findings:
        by_module[f.module].append(f)
    dismissed_by_module: dict[Optional[str], list[DismissedAlert]] = defaultdict(list)
    for d in dismissed:
        dismissed_by_module[d.module].append(d)

    for mod in module_paths:
        mod_findings = by_module.get(mod, [])
        mod_dismissed = dismissed_by_module.get(mod, [])
        out_dir = dest / mod / subdir
        _clean_dir(out_dir)
        (out_dir / "summary.json").write_text(
            json.dumps(summarize(mod_findings, len(mod_dismissed)), indent=2) + "\n",
            encoding="utf-8",
        )
        (out_dir / "index.html").write_text(
            render_findings_html(
                title=mod,
                findings=mod_findings,
                ref=args.ref,
                commit=args.commit,
                generated_at=generated_at,
                repo_url=args.repo_url,
                show_module_column=False,
                dismissed=mod_dismissed,
            ),
            encoding="utf-8",
        )

    global_dir = dest / subdir
    _clean_dir(global_dir)
    (global_dir / "summary.json").write_text(
        json.dumps(summarize(findings, len(dismissed)), indent=2) + "\n", encoding="utf-8"
    )
    (global_dir / "index.html").write_text(
        render_findings_html(
            title="all modules",
            findings=findings,
            ref=args.ref,
            commit=args.commit,
            generated_at=generated_at,
            repo_url=args.repo_url,
            show_module_column=True,
            dismissed=dismissed,
        ),
        encoding="utf-8",
    )

    unmapped = len(by_module.get(None, []))
    print(
        f"codeql_findings: {len(findings)} active findings across {len(module_paths)} "
        f"modules ({unmapped} outside any module; "
        f"{len(all_findings) - len(findings)} dismissed)",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

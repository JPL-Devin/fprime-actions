#!/usr/bin/env python3
"""I4 -- Passes static analysis.

Reads the repository's static-analysis results (filtered CodeQL SARIF
files, as produced by the existing CodeQL workflow) and verifies the
module has no findings at or above the configured severity threshold.
Exits non-zero listing each blocking finding.

Severity normalization matches coverage-common/codeql-publish: SARIF
``security-severity`` >= 7.0 is error, >= 4.0 medium, else low; otherwise
SARIF level error->error, warning->medium, note->low.
"""

import json
import sys
from pathlib import Path

from _report import finish, make_parser

_ORDER = {"error": 0, "medium": 1, "low": 2}


def normalize(level: str, security_severity) -> str:
    if security_severity is not None:
        try:
            score = float(security_severity)
        except (TypeError, ValueError):
            score = None
        if score is not None:
            if score >= 7.0:
                return "error"
            if score >= 4.0:
                return "medium"
            return "low"
    level = (level or "").lower()
    if level == "error":
        return "error"
    if level == "warning":
        return "medium"
    return "low"


def iter_findings(sarif_doc: dict):
    for run in sarif_doc.get("runs", []):
        rules = {}
        driver = (run.get("tool") or {}).get("driver") or {}
        for rule in driver.get("rules", []) or []:
            rules[rule.get("id")] = rule
        for result in run.get("results", []) or []:
            rule = rules.get(result.get("ruleId"), {})
            sec = ((rule.get("properties") or {}).get("security-severity"))
            level = result.get("level") or (rule.get("defaultConfiguration") or {}).get("level")
            severity = normalize(level, sec)
            for location in result.get("locations", []) or [{}]:
                phys = (location.get("physicalLocation") or {})
                artifact = ((phys.get("artifactLocation") or {}).get("uri")) or ""
                line = ((phys.get("region") or {}).get("startLine")) or 0
                yield {
                    "rule": result.get("ruleId", "<unknown>"),
                    "severity": severity,
                    "file": artifact,
                    "line": line,
                    "message": ((result.get("message") or {}).get("text")) or "",
                }
                break  # first location only


def main(argv=None) -> int:
    parser = make_parser(__doc__)
    parser.add_argument(
        "--sarif",
        type=Path,
        action="append",
        required=True,
        help="Filtered SARIF file(s) from the static-analysis pipeline (repeatable)",
    )
    parser.add_argument(
        "--severity-threshold",
        choices=("error", "medium", "low"),
        default="medium",
        help="Fail on findings at or above this severity (default: medium)",
    )
    parser.add_argument(
        "--module-path",
        default=None,
        help="Module path prefix as it appears in SARIF URIs (default: --module as given)",
    )
    args = parser.parse_args(argv)

    prefix = (args.module_path or str(args.module)).strip("/") + "/"
    threshold = _ORDER[args.severity_threshold]

    total = 0
    failures = []
    for sarif_path in args.sarif:
        try:
            doc = json.loads(sarif_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            failures.append(f"cannot read SARIF {sarif_path}: {exc}")
            continue
        for finding in iter_findings(doc):
            if not finding["file"].lstrip("/").startswith(prefix):
                continue
            total += 1
            if _ORDER[finding["severity"]] <= threshold:
                failures.append(
                    f"{finding['file']}:{finding['line']}: [{finding['severity']}] "
                    f"{finding['rule']}: {finding['message']}"
                )

    return finish(
        check_id="I4",
        name="Passes static analysis",
        category="implementation",
        module=args.module,
        failures=failures,
        detail=f"{total} finding(s) in module; threshold {args.severity_threshold}",
        json_output=args.json_output,
    )


if __name__ == "__main__":
    sys.exit(main())

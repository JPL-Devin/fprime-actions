#!/usr/bin/env python3
"""U5 -- Sufficient code coverage.

Verifies the component's line coverage meets a configurable threshold.
Either parses an existing gcovr ``--json-summary`` file (``--summary-json``,
e.g. from the coverage baseline branch or a coverage-common run), or runs
``fprime-util check --coverage`` and gcovr locally.  Reports the measured
coverage and exits non-zero when below the threshold.
"""

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from _report import finish, make_parser


def line_percent(doc: dict) -> float:
    total = int(doc.get("line_total", 0) or 0)
    covered = int(doc.get("line_covered", 0) or 0)
    if total > 0:
        return round(100.0 * covered / total, 2)
    return float(doc.get("line_percent", 0.0) or 0.0)


def main(argv=None) -> int:
    parser = make_parser(__doc__)
    parser.add_argument(
        "--threshold", type=float, default=80.0,
        help="Minimum line coverage percent (default: 80)",
    )
    parser.add_argument(
        "--summary-json", type=Path, default=None,
        help="Existing gcovr --json-summary file to evaluate instead of running checks",
    )
    args = parser.parse_args(argv)

    skipped_reason = None
    failures = []
    detail = ""

    summary_path = args.summary_json
    tempdir = None
    if summary_path is None:
        if shutil.which("fprime-util") is None or shutil.which("gcovr") is None:
            skipped_reason = "fprime-util/gcovr not found on PATH and no --summary-json given"
        else:
            proc = subprocess.run(
                ["fprime-util", "check", "--coverage"],
                cwd=args.module, capture_output=True, text=True,
            )
            if proc.returncode != 0:
                failures.append(
                    "'fprime-util check --coverage' failed:\n"
                    + ((proc.stdout or "") + (proc.stderr or ""))[-4000:]
                )
            else:
                tempdir = tempfile.mkdtemp(prefix="cov-check-")
                summary_path = Path(tempdir) / "summary.json"
                proc = subprocess.run(
                    ["gcovr", "-r", ".", "--json-summary", str(summary_path)],
                    cwd=args.module, capture_output=True, text=True,
                )
                if proc.returncode != 0:
                    failures.append(f"gcovr failed:\n{(proc.stderr or proc.stdout)[-4000:]}")
                    summary_path = None

    if skipped_reason is None and not failures and summary_path is not None:
        try:
            doc = json.loads(summary_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            failures.append(f"cannot read coverage summary {summary_path}: {exc}")
        else:
            pct = line_percent(doc)
            detail = f"line coverage {pct:.2f}% (threshold {args.threshold:.2f}%)"
            if pct < args.threshold:
                failures.append(
                    f"line coverage {pct:.2f}% is below the required threshold "
                    f"{args.threshold:.2f}%"
                )

    return finish(
        check_id="U5",
        name="Sufficient code coverage",
        category="unit-testing",
        module=args.module,
        failures=failures,
        skipped_reason=skipped_reason,
        detail=detail,
        json_output=args.json_output,
    )


if __name__ == "__main__":
    sys.exit(main())

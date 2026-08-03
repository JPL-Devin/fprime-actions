"""Shared CLI plumbing and pass/fail reporting for the checklist checks.

Every check script:

    * takes ``--module <dir>`` (the module directory to check),
    * prints one line per problem, prefixed with ``FAIL:``,
    * prints a final ``PASS``/``FAIL`` summary line,
    * exits 0 on pass, 1 on failures, 2 on usage/environment errors,
    * optionally appends a machine-readable record to ``--json-output``
      (JSON-Lines) so ``run_checks.py`` can aggregate results.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional


def make_parser(description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--module", type=Path, required=True, help="Module directory to check"
    )
    parser.add_argument(
        "--requirements",
        type=Path,
        action="append",
        default=None,
        help="Requirements source file(s); defaults to the module's docs/*.md and docs/*.csv",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=None,
        help="Append a JSON-Lines result record to this file",
    )
    return parser


def finish(
    *,
    check_id: str,
    name: str,
    category: str,
    module: Path,
    failures: List[str],
    skipped_reason: Optional[str] = None,
    detail: str = "",
    json_output: Optional[Path] = None,
) -> int:
    """Print the report, optionally record JSON, and return the exit code."""
    module_label = str(module)
    if skipped_reason is not None:
        status = "skip"
        print(f"SKIP [{check_id}] {name}: {module_label}: {skipped_reason}")
    elif failures:
        status = "fail"
        for failure in failures:
            print(f"FAIL [{check_id}] {module_label}: {failure}")
        print(f"FAIL [{check_id}] {name}: {module_label}: {len(failures)} problem(s) found")
    else:
        status = "pass"
        print(f"PASS [{check_id}] {name}: {module_label}{f' ({detail})' if detail else ''}")

    if json_output is not None:
        record = {
            "id": check_id,
            "name": name,
            "category": category,
            "module": module_label,
            "status": status,
            "failures": failures,
            "detail": skipped_reason if skipped_reason is not None else detail,
        }
        json_output.parent.mkdir(parents=True, exist_ok=True)
        with json_output.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")

    return 1 if status == "fail" else 0


def die(message: str) -> int:
    print(f"ERROR: {message}", file=sys.stderr)
    return 2

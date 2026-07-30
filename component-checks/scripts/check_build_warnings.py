#!/usr/bin/env python3
"""I2 -- Compiles without warnings for all targets.

Builds the component with ``fprime-util build`` for each requested target
platform and verifies the build completes with zero compiler warnings.
Exits non-zero listing every warning found (or the build failure).

Alternatively, ``--log`` skips the build and scans an existing build log
for warnings, so this check can post-process the output of a CI build job.
"""

import re
import shutil
import subprocess
import sys
from pathlib import Path

from _report import finish, make_parser

_WARNING_RE = re.compile(r"^.*?:\d+(?::\d+)?:\s+warning:.*$", re.MULTILINE)


def scan_warnings(text: str) -> list[str]:
    return sorted(set(_WARNING_RE.findall(text)))


def main(argv=None) -> int:
    parser = make_parser(__doc__)
    parser.add_argument(
        "--target-platform",
        action="append",
        default=None,
        help="Target platform(s) to build (repeatable); default: native only",
    )
    parser.add_argument(
        "--log",
        type=Path,
        action="append",
        default=None,
        help="Scan existing build log(s) for warnings instead of building",
    )
    parser.add_argument("--jobs", type=int, default=None, help="Parallel build jobs")
    args = parser.parse_args(argv)

    failures: list[str] = []
    skipped_reason = None
    detail = ""

    if args.log:
        text = ""
        for log in args.log:
            text += log.read_text(encoding="utf-8", errors="replace")
        warnings = scan_warnings(text)
        failures.extend(f"compiler warning: {w}" for w in warnings)
        detail = f"{len(args.log)} log(s) scanned"
    elif shutil.which("fprime-util") is None:
        skipped_reason = "fprime-util not found on PATH"
    else:
        platforms = args.target_platform or [None]
        for platform in platforms:
            cmd = ["fprime-util", "build"]
            if platform:
                cmd.append(platform)
            if args.jobs:
                cmd.extend(["-j", str(args.jobs)])
            proc = subprocess.run(cmd, cwd=args.module, capture_output=True, text=True)
            label = platform or "native"
            output = (proc.stdout or "") + (proc.stderr or "")
            if proc.returncode != 0:
                failures.append(f"build failed for target '{label}':\n{output[-4000:]}")
                continue
            failures.extend(
                f"[{label}] compiler warning: {w}" for w in scan_warnings(output)
            )
        detail = f"{len(platforms)} target(s) built"

    return finish(
        check_id="I2",
        name="Compiles without warnings",
        category="implementation",
        module=args.module,
        failures=failures,
        skipped_reason=skipped_reason,
        detail=detail,
        json_output=args.json_output,
    )


if __name__ == "__main__":
    sys.exit(main())

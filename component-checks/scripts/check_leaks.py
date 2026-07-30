#!/usr/bin/env python3
"""U4 -- Memory leak check passes.

Runs ``fprime-util check --leak`` for the component and verifies it passes
with no leaks.  Exits non-zero with the failing output when leaks (or test
failures) are detected.
"""

import re
import shutil
import subprocess
import sys

from _report import finish, make_parser

_LEAK_RE = re.compile(
    r"(definitely lost:\s*[1-9][\d,]*|indirectly lost:\s*[1-9][\d,]*|"
    r"ERROR SUMMARY:\s*[1-9][\d,]*\s+errors)",
    re.IGNORECASE,
)


def main(argv=None) -> int:
    parser = make_parser(__doc__)
    parser.add_argument("--jobs", type=int, default=None, help="Parallel jobs")
    args = parser.parse_args(argv)

    skipped_reason = None
    failures = []

    if shutil.which("fprime-util") is None:
        skipped_reason = "fprime-util not found on PATH"
    elif shutil.which("valgrind") is None:
        skipped_reason = "valgrind not found on PATH"
    else:
        cmd = ["fprime-util", "check", "--leak"]
        if args.jobs:
            cmd.extend(["-j", str(args.jobs)])
        proc = subprocess.run(cmd, cwd=args.module, capture_output=True, text=True)
        output = (proc.stdout or "") + (proc.stderr or "")
        leaks = sorted(set(_LEAK_RE.findall(output)))
        if proc.returncode != 0:
            failures.append(f"'fprime-util check --leak' failed:\n{output[-4000:]}")
        failures.extend(f"leak detected: {leak}" for leak in leaks)

    return finish(
        check_id="U4",
        name="Memory leak check passes",
        category="unit-testing",
        module=args.module,
        failures=failures,
        skipped_reason=skipped_reason,
        json_output=args.json_output,
    )


if __name__ == "__main__":
    sys.exit(main())

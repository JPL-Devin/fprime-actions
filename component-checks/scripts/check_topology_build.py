#!/usr/bin/env python3
"""C1 -- Topology instantiation/connection/compile.

Verifies the component can be instantiated, connected, and compiled within
the topology by building the given deployment(s) with ``fprime-util build``
for all requested target platforms.  Also confirms the component is
actually instantiated in the deployment's topology FPP.  Exits non-zero on
any failure.
"""

import re
import shutil
import subprocess
import sys
from pathlib import Path

from _fpp import strip_comments
from _report import finish, make_parser


def instantiated_in(component: str, topology_text: str) -> bool:
    """True when an ``instance`` declaration in the (comment-stripped)
    topology FPP text instantiates the component."""
    pattern = re.compile(
        rf"\binstance\s+\w+\s*:\s*(?:[\w.]*\.)?{re.escape(component)}\b"
    )
    return pattern.search(strip_comments(topology_text)) is not None


def main(argv=None) -> int:
    parser = make_parser(__doc__)
    parser.add_argument(
        "--deployment", type=Path, action="append", required=True,
        help="Deployment directory containing the topology (repeatable)",
    )
    parser.add_argument(
        "--target-platform", action="append", default=None,
        help="Target platform(s) to build (repeatable); default: native",
    )
    parser.add_argument(
        "--component", default=None,
        help="Component/instance name to verify appears in the topology FPP "
        "(default: module directory name)",
    )
    parser.add_argument("--jobs", type=int, default=None, help="Parallel build jobs")
    args = parser.parse_args(argv)

    component = args.component or args.module.name
    skipped_reason = None
    failures = []

    if shutil.which("fprime-util") is None:
        skipped_reason = "fprime-util not found on PATH"
    else:
        for deployment in args.deployment:
            topology_text = ""
            for fpp in sorted(deployment.rglob("*.fpp")):
                topology_text += fpp.read_text(encoding="utf-8", errors="replace") + "\n"
            if not instantiated_in(component, topology_text):
                failures.append(
                    f"component '{component}' is not instantiated in any topology FPP "
                    f"under {deployment}"
                )
                continue
            for platform in args.target_platform or [None]:
                cmd = ["fprime-util", "build"]
                if platform:
                    cmd.append(platform)
                if args.jobs:
                    cmd.extend(["-j", str(args.jobs)])
                proc = subprocess.run(cmd, cwd=deployment, capture_output=True, text=True)
                if proc.returncode != 0:
                    label = platform or "native"
                    failures.append(
                        f"topology build failed for {deployment} (target '{label}'):\n"
                        + ((proc.stdout or "") + (proc.stderr or ""))[-4000:]
                    )

    return finish(
        check_id="C1",
        name="Topology instantiation and compile",
        category="close-out",
        module=args.module,
        failures=failures,
        skipped_reason=skipped_reason,
        detail=f"{len(args.deployment)} deployment(s) checked for '{component}'",
        json_output=args.json_output,
    )


if __name__ == "__main__":
    sys.exit(main())

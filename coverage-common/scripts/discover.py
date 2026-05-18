"""Discover F´ modules under a working directory.

A module is any directory whose CMakeLists.txt contains a call to
``register_fprime_module(`` (with arbitrary whitespace).  A module is
considered to have unit tests when the same CMakeLists.txt also contains
``register_fprime_ut(``.

Output: one record per discovered module on stdout, JSON-Lines format::

    {"path": "Svc/CmdDispatcher", "has_ut": true}
    {"path": "Drv/LinuxGpio", "has_ut": false}

Use the ``--with-ut-only`` flag to filter to modules with unit tests.
"""

import argparse
import json
import re
import sys
from pathlib import Path

MODULE_RE = re.compile(r"^\s*register_fprime_module\s*\(", re.MULTILINE)
UT_RE = re.compile(r"^\s*register_fprime_ut\s*\(", re.MULTILINE)


def discover(root: Path):
    """Yield (relative_module_path, has_ut) for each module under ``root``.

    The relative path uses POSIX separators (``/``) regardless of host OS.
    """
    for cmake in sorted(root.rglob("CMakeLists.txt")):
        try:
            text = cmake.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if not MODULE_RE.search(text):
            continue
        has_ut = bool(UT_RE.search(text))
        rel = cmake.parent.relative_to(root)
        yield rel.as_posix(), has_ut


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("."),
        help="Working directory to scan (default: current directory)",
    )
    parser.add_argument(
        "--with-ut-only",
        action="store_true",
        help="Emit only modules that declare unit tests",
    )
    args = parser.parse_args(argv)

    root = args.root.resolve()
    if not root.is_dir():
        print(f"discover: not a directory: {root}", file=sys.stderr)
        return 2

    count = 0
    for path, has_ut in discover(root):
        if args.with_ut_only and not has_ut:
            continue
        print(json.dumps({"path": path, "has_ut": has_ut}))
        count += 1

    print(f"discover: found {count} modules under {root}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

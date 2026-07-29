"""Discover F´ modules under a working directory.

A module is any directory whose CMakeLists.txt contains a call to
``register_fprime_module(`` or ``register_fprime_library(`` (with
arbitrary whitespace).  A module is
considered to have unit tests when the same CMakeLists.txt also contains
``register_fprime_ut(``.

A module is considered *autocoder-only* when no hand-written C/C++
source lives in its directory tree (excluding files owned by nested
modules): such modules define only types, ports, or other FPP models and
have no compiled first-party code to cover or scan.  They are excluded
from the output by default; pass ``--include-autocoder-only`` to keep
them.

Output: one record per discovered module on stdout, JSON-Lines format::

    {"path": "Svc/CmdDispatcher", "has_ut": true, "has_cpp": true}
    {"path": "Drv/LinuxGpio", "has_ut": false, "has_cpp": true}

Use the ``--with-ut-only`` flag to filter to modules with unit tests.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

MODULE_RE = re.compile(r"^\s*register_fprime_(module|library)\s*\(", re.MULTILINE)
UT_RE = re.compile(r"^\s*register_fprime_ut\s*\(", re.MULTILINE)

#: File suffixes counted as hand-written C/C++ source when deciding
#: whether a module is autocoder-only.
CPP_SUFFIXES = {".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx"}


def _owning_module(path: str, module_paths: list[str]) -> str | None:
    """Longest-prefix match of a file path onto the module list."""
    best = None
    for mod in module_paths:
        if path == mod or path.startswith(mod + "/"):
            if best is None or len(mod) > len(best):
                best = mod
    return best


def _module_has_cpp(root: Path, module: str, module_paths: list[str]) -> bool:
    """True when the module owns at least one C/C++ source file.

    Files under a nested module's directory belong to that nested module
    (longest-prefix ownership, matching how findings are attributed).
    """
    for candidate in (root / module).rglob("*"):
        if candidate.suffix.lower() not in CPP_SUFFIXES or not candidate.is_file():
            continue
        rel = candidate.parent.relative_to(root).as_posix()
        if _owning_module(rel, module_paths) == module:
            return True
    return False


def discover(root: Path):
    """Yield (relative_module_path, has_ut, has_cpp) for each module under ``root``.

    The relative path uses POSIX separators (``/``) regardless of host OS.
    """
    modules: list[tuple[str, bool]] = []
    for cmake in sorted(root.rglob("CMakeLists.txt")):
        try:
            text = cmake.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if not MODULE_RE.search(text):
            continue
        has_ut = bool(UT_RE.search(text))
        rel = cmake.parent.relative_to(root)
        modules.append((rel.as_posix(), has_ut))
    module_paths = [path for path, _ in modules]
    for path, has_ut in modules:
        yield path, has_ut, _module_has_cpp(root, path, module_paths)


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
    parser.add_argument(
        "--include-autocoder-only",
        action="store_true",
        help="Also emit modules with no hand-written C/C++ source "
        "(types/ports-only modules); excluded by default",
    )
    args = parser.parse_args(argv)

    root = args.root.resolve()
    if not root.is_dir():
        print(f"discover: not a directory: {root}", file=sys.stderr)
        return 2

    count = 0
    skipped = 0
    for path, has_ut, has_cpp in discover(root):
        if args.with_ut_only and not has_ut:
            continue
        if not has_cpp and not args.include_autocoder_only:
            skipped += 1
            continue
        print(json.dumps({"path": path, "has_ut": has_ut, "has_cpp": has_cpp}))
        count += 1

    print(
        f"discover: found {count} modules under {root}"
        f" ({skipped} autocoder-only module(s) excluded)",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Post-process integration test coverage for all discovered F' modules.

Integration tests exercise a single deployment binary, so there is only
one set of ``.gcda`` files produced by the run(s).  This script runs
``gcovr`` once per module using ``--filter <module-source-dir>`` to
attribute coverage to each component individually.  A global (unfiltered)
pass is performed first for headline numbers.

Usage:
    python run_integration_coverage.py \
        --project-root /path/to/fprime-project \
        --build-cache build-fprime-automatic-native-coverage \
        --modules-jsonl modules.jsonl \
        [--debug]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def _run_gcovr(
    *,
    project_root: Path,
    build_cache: Path,
    output_dir: Path,
    output_prefix: str,
    filter_dir: Path | None = None,
    debug: bool = False,
) -> bool:
    """Run gcovr once, writing HTML + JSON summary to output_dir.

    Returns True on success.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        "gcovr",
        "-r", str(project_root),
        str(build_cache),
        "--html-details", str(output_dir / f"{output_prefix}.html"),
        "--json-summary", str(output_dir / "summary.json"),
        "--gcov-ignore-parse-errors=negative_hits.warn_once_per_file",
    ]
    if filter_dir is not None:
        cmd.extend(["--filter", str(filter_dir)])
    if debug:
        cmd.append("-v")

    result = subprocess.run(cmd)
    return result.returncode == 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-root", type=Path, required=True,
        help="Top-level F' project root (contains CMakeLists.txt, Fw/, Svc/, etc.)",
    )
    parser.add_argument(
        "--build-cache", type=Path, required=True,
        help="Path to the build cache directory with .gcno/.gcda files",
    )
    parser.add_argument(
        "--modules-jsonl", type=Path, required=True,
        help="JSON-Lines module list from discover.py",
    )
    parser.add_argument(
        "--strict", action="store_true",
        help="Fail immediately if any per-module gcovr invocation fails",
    )
    parser.add_argument(
        "--debug", action="store_true",
        help="Pass -v to gcovr for verbose output",
    )
    args = parser.parse_args(argv)

    project_root = args.project_root.resolve()
    build_cache = args.build_cache.resolve()

    if not build_cache.is_dir():
        print(f"ERROR: Build cache not found: {build_cache}", file=sys.stderr)
        return 2

    with args.modules_jsonl.open("r", encoding="utf-8") as fh:
        modules = [json.loads(line) for line in fh if line.strip()]

    # --- Global pass (all sources, no filter) ---
    print("[integration-coverage] Global pass (all sources)", flush=True)
    global_ok = _run_gcovr(
        project_root=project_root,
        build_cache=build_cache,
        output_dir=project_root / "coverage",
        output_prefix="coverage-all",
        debug=args.debug,
    )
    if not global_ok:
        print("WARNING: Global gcovr pass failed", file=sys.stderr)
        if args.strict:
            return 1

    # --- Per-module pass (filter to module source dir) ---
    failed: list[str] = []
    for rec in modules:
        mod_path = rec["path"]
        mod_dir = project_root / mod_path
        if not mod_dir.is_dir():
            print(f"[SKIP] {mod_path}: source dir not found", file=sys.stderr)
            continue

        print(f"[integration-coverage] {mod_path}", flush=True)
        ok = _run_gcovr(
            project_root=project_root,
            build_cache=build_cache,
            output_dir=mod_dir / "coverage",
            output_prefix="coverage",
            filter_dir=mod_dir,
            debug=args.debug,
        )
        if not ok:
            print(f"[FAIL] {mod_path}", file=sys.stderr)
            failed.append(mod_path)
            if args.strict:
                return 1

    if failed:
        print(
            f"WARNING: {len(failed)}/{len(modules)} modules failed gcovr",
            file=sys.stderr,
        )

    print(
        f"[integration-coverage] Done: {len(modules) - len(failed)}/{len(modules)} ok",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

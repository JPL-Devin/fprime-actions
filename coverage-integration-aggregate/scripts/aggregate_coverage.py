"""Aggregate integration coverage from multiple gcovr JSON tracefiles.

Merges per-deployment tracefiles using ``gcovr --add-tracefile`` and
produces per-module HTML + summary.json reports from the merged data.

Usage:
    python aggregate_coverage.py \
        --project-root /path/to/fprime \
        --tracefiles traces/integration-trace-*.json \
        --modules-jsonl modules.jsonl \
        [--enable-fw-assert-branch-coverage] \
        [--debug]
"""

from __future__ import annotations

import argparse
import glob
import json
import subprocess
import sys
from pathlib import Path


def _run_gcovr_merge(
    *,
    project_root: Path,
    tracefiles: list[Path],
    output_dir: Path,
    output_prefix: str,
    filter_dir: Path | None = None,
    enable_fw_assert_branch_coverage: bool = False,
    debug: bool = False,
) -> bool:
    """Run gcovr with --add-tracefile to merge and produce reports.

    Returns True on success.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        "gcovr",
        "-r", str(project_root),
    ]

    for tf in tracefiles:
        cmd.extend(["--add-tracefile", str(tf)])

    cmd.extend([
        "--html-details", str(output_dir / f"{output_prefix}.html"),
        "--json-summary", str(output_dir / "summary.json"),
        "--exclude-throw-branches",
        "--exclude-unreachable-branches",
        "--merge-mode-functions=merge-use-line-min",
    ])

    if not enable_fw_assert_branch_coverage:
        cmd.extend(["--exclude-branches-by-pattern", r".*FW_ASSERT\(.*"])
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
        help="F' source root (same --root used during collect)",
    )
    parser.add_argument(
        "--tracefiles", required=True,
        help="Glob pattern matching the gcovr JSON tracefiles to merge",
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
        "--enable-fw-assert-branch-coverage", action="store_true",
        help="Include FW_ASSERT branches in branch coverage (excluded by default)",
    )
    parser.add_argument(
        "--debug", action="store_true",
        help="Pass -v to gcovr for verbose output",
    )
    args = parser.parse_args(argv)

    project_root = args.project_root.resolve()

    # Resolve tracefile glob
    tracefiles = sorted(Path(p) for p in glob.glob(args.tracefiles))
    if not tracefiles:
        print(f"ERROR: No tracefiles matched pattern: {args.tracefiles}", file=sys.stderr)
        return 2

    print(f"[aggregate] Merging {len(tracefiles)} tracefile(s):", flush=True)
    for tf in tracefiles:
        print(f"  - {tf.name}", flush=True)

    with args.modules_jsonl.open("r", encoding="utf-8") as fh:
        modules = [json.loads(line) for line in fh if line.strip()]

    # --- Global merged pass ---
    print("[aggregate] Global pass (all sources, merged)", flush=True)
    global_ok = _run_gcovr_merge(
        project_root=project_root,
        tracefiles=tracefiles,
        output_dir=project_root / "coverage",
        output_prefix="coverage-all",
        enable_fw_assert_branch_coverage=args.enable_fw_assert_branch_coverage,
        debug=args.debug,
    )
    if not global_ok:
        print("WARNING: Global merged gcovr pass failed", file=sys.stderr)
        if args.strict:
            return 1

    # --- Per-module merged pass ---
    failed: list[str] = []
    for rec in modules:
        mod_path = rec["path"]
        mod_dir = project_root / mod_path
        if not mod_dir.is_dir():
            print(f"[SKIP] {mod_path}: source dir not found", file=sys.stderr)
            continue

        print(f"[aggregate] {mod_path}", flush=True)
        ok = _run_gcovr_merge(
            project_root=project_root,
            tracefiles=tracefiles,
            output_dir=mod_dir / "coverage",
            output_prefix="coverage",
            filter_dir=mod_dir,
            enable_fw_assert_branch_coverage=args.enable_fw_assert_branch_coverage,
            debug=args.debug,
        )
        if not ok:
            print(f"[FAIL] {mod_path}", file=sys.stderr)
            failed.append(mod_path)
            if args.strict:
                return 1

    if failed:
        print(
            f"WARNING: {len(failed)}/{len(modules)} modules failed gcovr merge",
            file=sys.stderr,
        )

    print(
        f"[aggregate] Done: {len(modules) - len(failed)}/{len(modules)} ok",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

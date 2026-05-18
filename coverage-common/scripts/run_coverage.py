#!/usr/bin/env python3
"""Run per-module gcovr coverage via fprime-util check --coverage.

Reads the modules.jsonl produced by discover.py, skips modules without
register_fprime_ut(), and runs ``fprime-util check --coverage`` in each
eligible module directory.  After each successful run, renames
``coverage/coverage.html`` to ``coverage/index.html`` when present.

Exit codes:
  0  all modules succeeded (or none were eligible)
  1  one or more modules failed
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def _run_module(mod: str, root: Path, target_platform: str) -> bool:
    """Run coverage for a single module.  Returns True on success."""
    mod_dir = root / mod
    cmd = ["fprime-util", "check", "--coverage"]
    if target_platform:
        cmd.append(target_platform)
    cmd.extend(["--pass-through", "--json-summary", "coverage/summary.json"])

    print(f"[cover] {mod}", flush=True)
    result = subprocess.run(cmd, cwd=str(mod_dir))
    if result.returncode != 0:
        print(f"[FAIL] {mod} (exit {result.returncode})", file=sys.stderr, flush=True)
        return False

    html = mod_dir / "coverage" / "coverage.html"
    if html.is_file():
        html.rename(mod_dir / "coverage" / "index.html")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."),
                        help="Project root (working-directory)")
    parser.add_argument("--modules-jsonl", type=Path, required=True,
                        help="Path to modules.jsonl from discover.py")
    parser.add_argument("--target-platform", default="",
                        help="Target platform forwarded to fprime-util")
    args = parser.parse_args(argv)

    root = args.root.resolve()

    with args.modules_jsonl.open("r", encoding="utf-8") as fh:
        records = [json.loads(line) for line in fh if line.strip()]

    failed = 0
    covered = 0
    skipped = 0
    for rec in records:
        mod = rec["path"]
        has_ut = bool(rec.get("has_ut", False))
        if not has_ut:
            print(f"[skip] {mod} (no register_fprime_ut)")
            skipped += 1
            continue
        if not _run_module(mod, root, args.target_platform):
            failed += 1
        else:
            covered += 1

    print(
        f"run_coverage: {covered} succeeded, {failed} failed, {skipped} skipped",
        file=sys.stderr,
        flush=True,
    )
    return 1 if failed > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())

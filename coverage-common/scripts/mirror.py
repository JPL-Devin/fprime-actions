"""Mirror per-module + global coverage outputs into the baseline worktree.

For each discovered module, copy ``<source>/<mod>/coverage/*`` into the
baseline tree as ``<dest>/<mod>/coverage-<kind>/*``.  If a module produced
no ``summary.json`` (no UT, or gcovr emitted nothing) a placeholder
``index.html`` is written in its place.

The global ``--all`` run lives at ``<source>/coverage/*`` and is copied to
``<dest>/coverage-<kind>/*``.

After mirroring, ``catalog.py`` is invoked to produce ``catalog.json`` and
the top-level ``index.html`` that summarises all coverage kinds (reading
whatever ``coverage-*`` subdirectories are present in the baseline worktree).

This script is idempotent: it deletes the existing per-module coverage
directory for the *current kind* under ``<dest>`` before copying so a
re-run cannot leave stale files behind.  Other kinds' directories are
preserved.
"""

from __future__ import annotations

import argparse
import html as html_mod
import json
import shutil
import sys
from pathlib import Path

import catalog as catalog_mod
from _summary import load_summary

PLACEHOLDER_CSS = (
    "body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; "
    "color: #1f2328; padding: 2rem; max-width: 40rem; }"
    "h1 { margin: 0 0 0.5rem 0; font-size: 1.1rem; }"
    ".meta { color: #57606a; font-size: 0.9rem; }"
)




def _subdir_for_kind(kind: str) -> str:
    """Return the coverage subdirectory name for a given kind."""
    return f"coverage-{kind}"


def _catalog_relative_path(module_path: str, subdir: str) -> str:
    """Relative URL from a module's coverage dir back to the catalog root.

    ``Drv/LinuxGpio`` with ``subdir="coverage-ut"`` -> ``../../../index.html``
    ``Drv/LinuxGpio`` with ``subdir=""``             -> ``../../index.html``
    """
    depth = len([s for s in module_path.split("/") if s])
    if subdir:
        depth += 1
    return "/".join([".."] * depth) + "/index.html"


def placeholder_html(module_path: str, reason: str, catalog_href: str) -> str:
    """Return a one-page HTML notice for a module with no coverage data."""
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        f"<title>No coverage \u2014 {html_mod.escape(module_path)}</title>"
        f"<style>{PLACEHOLDER_CSS}</style></head><body>"
        f"<h1>No coverage recorded for <code>{html_mod.escape(module_path)}</code></h1>"
        f"<p>{html_mod.escape(reason)}</p>"
        f'<p class="meta">'
        f'<a href="{html_mod.escape(catalog_href)}">&larr; back to catalog</a>'
        f"</p>"
        f"</body></html>\n"
    )


def _coverage_dest(dest_root: Path, module_path: str, subdir: str) -> Path:
    """Where this module's coverage artifacts land in the baseline tree."""
    base = dest_root / module_path
    return base / subdir if subdir else base


def _clean_dir(path: Path) -> None:
    """Remove ``path`` if it exists (file or directory) and recreate empty."""
    if path.exists():
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink()
    path.mkdir(parents=True, exist_ok=True)


def _copy_coverage_contents(src_dir: Path, dst_dir: Path) -> None:
    """Copy gcovr outputs from ``src_dir`` to ``dst_dir``.

    ``coverage.html`` is renamed to ``index.html`` so each subfolder is
    directly browsable (no collision since each kind has its own subdir).
    """
    for src in sorted(src_dir.iterdir()):
        if src.is_dir():
            continue
        name = src.name
        if name == "coverage.html":
            name = "index.html"
        shutil.copy2(src, dst_dir / name)


def mirror_module(
    *,
    source: Path,
    dest: Path,
    module_path: str,
    has_ut: bool,
    subdir: str,
    kind: str,
) -> bool:
    """Mirror a single module's coverage outputs.  Returns ``has_coverage``."""
    src_cov = source / module_path / "coverage"
    dst_cov = _coverage_dest(dest, module_path, subdir)
    _clean_dir(dst_cov)

    summary = load_summary(src_cov / "summary.json") if src_cov.is_dir() else None
    has_coverage = summary is not None and summary.line.total > 0

    if has_coverage:
        _copy_coverage_contents(src_cov, dst_cov)
        return True

    if kind == "ut":
        if not has_ut:
            reason = (
                "This module is registered with register_fprime_module() but does not "
                "declare unit tests (no register_fprime_ut() call). No unit test "
                "coverage data is produced for unmeasurable modules."
            )
        else:
            reason = (
                "This module declares unit tests but no coverage data was produced "
                "for this run (gcovr emitted no measurable lines)."
            )
    else:
        reason = (
            "No integration test coverage data was produced for this module "
            "during this run."
        )

    catalog_href = _catalog_relative_path(module_path, subdir)
    (dst_cov / "index.html").write_text(
        placeholder_html(module_path, reason, catalog_href), encoding="utf-8"
    )
    return False


def mirror_global(*, source: Path, dest: Path, subdir: str) -> None:
    """Copy the global ``--all`` outputs."""
    src_cov = source / "coverage"
    if not src_cov.is_dir():
        return
    dst_cov = dest / subdir if subdir else dest
    _clean_dir(dst_cov)
    _copy_coverage_contents(src_cov, dst_cov)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="Working-tree root")
    parser.add_argument("--dest", type=Path, required=True, help="Baseline worktree root")
    parser.add_argument(
        "--modules-jsonl",
        type=Path,
        required=True,
        help="JSON-Lines module list from discover.py",
    )
    parser.add_argument(
        "--coverage-kind",
        default="ut",
        help="Coverage kind slug (e.g. 'ut', 'integration-linux', 'integration-hil-arm')",
    )
    parser.add_argument("--ref", required=True)
    parser.add_argument("--ref-type", default="branch", choices=("branch", "tag"))
    parser.add_argument("--commit", required=True)
    parser.add_argument("--generated-at", default=None)
    args = parser.parse_args(argv)

    source = args.source.resolve()
    dest = args.dest.resolve()
    dest.mkdir(parents=True, exist_ok=True)
    kind = args.coverage_kind
    subdir = _subdir_for_kind(kind)

    if not args.modules_jsonl.is_file():
        print(f"mirror: missing module list {args.modules_jsonl}", file=sys.stderr)
        return 2

    with args.modules_jsonl.open("r", encoding="utf-8") as fh:
        module_records = [json.loads(line) for line in fh if line.strip()]

    mirror_global(source=source, dest=dest, subdir=subdir)

    for rec in module_records:
        mirror_module(
            source=source,
            dest=dest,
            module_path=rec["path"],
            has_ut=bool(rec.get("has_ut", False)),
            subdir=subdir,
            kind=kind,
        )

    # Defer to catalog.py for catalog.json + top-level index.html.
    # Catalog reads from dest (baseline worktree) and merges both coverage
    # kinds (ut + integration) that are present on the branch.
    catalog_argv = [
        "--dest", str(dest),
        "--modules-jsonl", str(args.modules_jsonl),
        "--ref", args.ref,
        "--ref-type", args.ref_type,
        "--commit", args.commit,
    ]
    if args.generated_at:
        catalog_argv += ["--generated-at", args.generated_at]
    rc = catalog_mod.main(catalog_argv)
    if rc != 0:
        return rc

    print(f"mirror: wrote {len(module_records)} modules ({kind}) into {dest}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

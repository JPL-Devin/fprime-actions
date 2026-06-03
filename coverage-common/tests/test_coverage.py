"""Unit tests for the coverage action's helper scripts.

Run with:  python3 -m coverage.tests.test_coverage
or:        python3 coverage/tests/test_coverage.py

No external dependencies.  Each test prints OK or FAIL and the runner
exits 1 on any failure.
"""

from __future__ import annotations

import io
import json
import shutil
import sys
import tempfile
import traceback
from contextlib import redirect_stderr
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS_DIR = HERE.parent / "scripts"
FIXTURES = HERE / "fixtures"

sys.path.insert(0, str(SCRIPTS_DIR))

import discover  # noqa: E402
import compare  # noqa: E402
import mirror  # noqa: E402
import catalog  # noqa: E402
from _summary import Summary, load_summary  # noqa: E402


def _make_module(root: Path, path: str, *, with_ut: bool = True) -> Path:
    """Create a fake F´ module dir with a CMakeLists.txt that triggers discovery."""
    mod_dir = root / path
    mod_dir.mkdir(parents=True, exist_ok=True)
    body = ["set(SOURCE_FILES foo.cpp)", "register_fprime_module()"]
    if with_ut:
        body.append("register_fprime_ut()")
    (mod_dir / "CMakeLists.txt").write_text("\n".join(body) + "\n", encoding="utf-8")
    return mod_dir


def _place_coverage(mod_dir: Path, fixture_name: str) -> None:
    """Drop a sample summary.json + minimal coverage.html under <mod>/coverage/."""
    cov = mod_dir / "coverage"
    cov.mkdir(exist_ok=True)
    shutil.copy2(FIXTURES / fixture_name, cov / "summary.json")
    (cov / "coverage.html").write_text(
        '<html><body>placeholder report '
        '<a href="coverage.123.html">detail</a></body></html>',
        encoding="utf-8",
    )
    (cov / "coverage.123.html").write_text("<html><body>detail</body></html>", encoding="utf-8")


def _modules_jsonl(records: list[dict]) -> Path:
    fh = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8")
    for rec in records:
        fh.write(json.dumps(rec) + "\n")
    fh.close()
    return Path(fh.name)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_discover_finds_modules_and_ut_flag():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_module(root, "Svc/CmdDispatcher", with_ut=True)
        _make_module(root, "Drv/LinuxGpio", with_ut=False)
        _make_module(root, "Fw/Cmd", with_ut=True)
        # Decoy: file with text "register_fprime_module" but commented out.
        (root / "Decoy").mkdir()
        (root / "Decoy" / "CMakeLists.txt").write_text(
            "# register_fprime_module() -- commented out\n", encoding="utf-8"
        )

        result = sorted(discover.discover(root))
        assert ("Drv/LinuxGpio", False) in result, result
        assert ("Svc/CmdDispatcher", True) in result, result
        assert ("Fw/Cmd", True) in result, result
        assert not any(p.startswith("Decoy") for p, _ in result), result


def test_discover_ignores_commented_out_calls():
    # Regression test for the regex: lines starting with `#` must not match.
    text = "# register_fprime_module()\n  register_fprime_ut()"
    assert not discover.MODULE_RE.search(text)
    assert discover.UT_RE.search(text)


def test_summary_load_handles_missing_file_and_zero_total():
    assert load_summary(Path("/nonexistent/path/summary.json")) is None
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "summary.json"
        f.write_text("{}", encoding="utf-8")
        s = load_summary(f)
        assert s is not None
        assert s.line.percent == 0.0
        assert s.line.total == 0


def test_summary_load_parses_gcovr_json():
    s = load_summary(FIXTURES / "summary_high.json")
    assert s is not None
    assert s.line.covered == 392 and s.line.total == 400
    assert s.line.percent == 98.0
    assert s.function.covered == 28 and s.function.total == 30
    assert s.function.percent == 93.33
    assert s.branch.percent == 87.5


def test_mirror_module_renames_coverage_html_to_index():
    """coverage.html IS renamed to index.html (each kind has its own subdir)."""
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "src"
        dest = Path(tmp) / "dest"
        source.mkdir()
        dest.mkdir()
        mod_path = "Svc/CmdDispatcher"
        _place_coverage(_make_module(source, mod_path), "summary_high.json")

        has_cov = mirror.mirror_module(
            source=source, dest=dest, module_path=mod_path, has_ut=True,
            subdir="coverage-ut", kind="ut",
        )
        assert has_cov is True
        dst_cov = dest / mod_path / "coverage-ut"
        assert (dst_cov / "summary.json").is_file()
        assert (dst_cov / "index.html").is_file(), "coverage.html should be renamed to index.html"
        assert not (dst_cov / "coverage.html").exists(), "coverage.html should NOT exist after rename"
        assert (dst_cov / "coverage.123.html").is_file(), "sibling detail file must be preserved"


def test_mirror_module_writes_placeholder_when_no_ut():
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "src"
        dest = Path(tmp) / "dest"
        source.mkdir()
        dest.mkdir()
        mod_path = "Drv/LinuxGpio"
        _make_module(source, mod_path, with_ut=False)

        has_cov = mirror.mirror_module(
            source=source, dest=dest, module_path=mod_path, has_ut=False,
            subdir="coverage-ut", kind="ut",
        )
        assert has_cov is False
        placeholder = dest / mod_path / "coverage-ut" / "index.html"
        assert placeholder.is_file()
        body = placeholder.read_text(encoding="utf-8")
        assert "No coverage recorded" in body
        assert "Drv/LinuxGpio" in body
        # The back-to-catalog link must climb past both the module path and the subdir.
        assert 'href="../../../index.html"' in body, body


def test_mirror_integration_placeholder():
    """Integration coverage placeholder uses different text."""
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "src"
        dest = Path(tmp) / "dest"
        source.mkdir()
        dest.mkdir()
        mod_path = "Svc/Health"
        _make_module(source, mod_path, with_ut=True)

        has_cov = mirror.mirror_module(
            source=source, dest=dest, module_path=mod_path, has_ut=True,
            subdir="coverage-integration-int", kind="integration-int",
        )
        assert has_cov is False
        placeholder = dest / mod_path / "coverage-integration-int" / "index.html"
        assert placeholder.is_file()
        body = placeholder.read_text(encoding="utf-8")
        assert "integration test coverage" in body.lower()


def test_catalog_relative_path_math():
    # Sanity-check the back-link depth calculation for various inputs.
    assert mirror._catalog_relative_path("Drv/LinuxGpio", "coverage-ut") == "../../../index.html"
    assert mirror._catalog_relative_path("Drv/LinuxGpio", "") == "../../index.html"
    assert mirror._catalog_relative_path("Fw/Cmd/Sub", "coverage-integration-int") == "../../../../index.html"
    assert mirror._catalog_relative_path("TopLevel", "coverage-ut") == "../../index.html"
    assert mirror._catalog_relative_path("TopLevel", "") == "../index.html"


def test_mirror_module_is_idempotent():
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "src"
        dest = Path(tmp) / "dest"
        source.mkdir()
        dest.mkdir()
        mod_path = "Svc/CmdDispatcher"
        _place_coverage(_make_module(source, mod_path), "summary_high.json")

        mirror.mirror_module(
            source=source, dest=dest, module_path=mod_path, has_ut=True,
            subdir="coverage-ut", kind="ut",
        )
        # Drop a stale file that should be removed by the second run.
        (dest / mod_path / "coverage-ut" / "stale.html").write_text("stale", encoding="utf-8")

        mirror.mirror_module(
            source=source, dest=dest, module_path=mod_path, has_ut=True,
            subdir="coverage-ut", kind="ut",
        )
        assert not (dest / mod_path / "coverage-ut" / "stale.html").exists()
        assert (dest / mod_path / "coverage-ut" / "summary.json").is_file()


def test_mirror_preserves_other_kind():
    """Mirroring 'ut' must not clobber existing 'integration' data."""
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "src"
        dest = Path(tmp) / "dest"
        source.mkdir()
        dest.mkdir()
        mod_path = "Svc/CmdDispatcher"
        _place_coverage(_make_module(source, mod_path), "summary_high.json")

        # Pre-populate integration coverage on dest (as if a previous run wrote it).
        int_dir = dest / mod_path / "coverage-integration"
        int_dir.mkdir(parents=True)
        (int_dir / "summary.json").write_text('{"line_covered": 10}', encoding="utf-8")
        (int_dir / "coverage.html").write_text("<html>int report</html>", encoding="utf-8")

        # Mirror UT coverage.
        mirror.mirror_module(
            source=source, dest=dest, module_path=mod_path, has_ut=True,
            subdir="coverage-ut", kind="ut",
        )
        # UT data is written.
        assert (dest / mod_path / "coverage-ut" / "summary.json").is_file()
        # Integration data is preserved.
        assert (dest / mod_path / "coverage-integration" / "summary.json").is_file()
        assert (dest / mod_path / "coverage-integration" / "coverage.html").is_file()


def test_catalog_combined_landing_page():
    """Catalog produces a combined index.html with UT and integration data."""
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp)

        # Simulate baseline worktree with both kinds for some modules.
        for mod_path in ["Svc/CmdDispatcher", "Svc/Health", "Drv/I2c"]:
            ut_dir = dest / mod_path / "coverage-ut"
            ut_dir.mkdir(parents=True)
            shutil.copy2(FIXTURES / "summary_high.json", ut_dir / "summary.json")
            (ut_dir / "index.html").write_text("<html>ut report</html>", encoding="utf-8")

        # Integration-int coverage only for some
        for mod_path in ["Svc/CmdDispatcher", "Drv/I2c"]:
            int_dir = dest / mod_path / "coverage-integration-int"
            int_dir.mkdir(parents=True)
            shutil.copy2(FIXTURES / "summary_mid.json", int_dir / "summary.json")
            (int_dir / "index.html").write_text("<html>int report</html>", encoding="utf-8")

        # Module without coverage at all
        (dest / "Drv" / "LinuxGpio" / "coverage-ut").mkdir(parents=True)

        # Global UT
        (dest / "coverage-ut").mkdir(parents=True)
        shutil.copy2(FIXTURES / "summary_high.json", dest / "coverage-ut" / "summary.json")
        (dest / "coverage-ut" / "coverage-all.html").write_text("<html>global ut</html>", encoding="utf-8")

        # Global integration-int
        (dest / "coverage-integration-int").mkdir(parents=True)
        shutil.copy2(FIXTURES / "summary_mid.json", dest / "coverage-integration-int" / "summary.json")
        (dest / "coverage-integration-int" / "coverage-all.html").write_text("<html>global int</html>", encoding="utf-8")

        modules_jsonl = _modules_jsonl([
            {"path": "Svc/CmdDispatcher", "has_ut": True},
            {"path": "Svc/Health", "has_ut": True},
            {"path": "Drv/I2c", "has_ut": True},
            {"path": "Drv/LinuxGpio", "has_ut": False},
        ])

        rc = catalog.main([
            "--dest", str(dest),
            "--modules-jsonl", str(modules_jsonl),
            "--ref", "devel",
            "--ref-type", "branch",
            "--commit", "deadbeefcafe1234",
            "--generated-at", "2026-05-18T17:30:00Z",
        ])
        assert rc == 0

        cat_doc = json.loads((dest / "catalog.json").read_text(encoding="utf-8"))
        assert cat_doc["schema"] == 2
        assert cat_doc["ref"] == "devel"
        assert cat_doc["commit"] == "deadbeefcafe1234"
        assert len(cat_doc["modules"]) == 4

        # Check per-module kind entries (dynamically discovered)
        by_path = {m["path"]: m for m in cat_doc["modules"]}
        assert by_path["Svc/CmdDispatcher"]["ut"]["has_coverage"] is True
        assert by_path["Svc/CmdDispatcher"]["integration-int"]["has_coverage"] is True
        assert by_path["Svc/Health"]["ut"]["has_coverage"] is True
        # Svc/Health has no integration-int dir so no entry expected
        assert by_path["Drv/LinuxGpio"]["ut"]["has_coverage"] is False

        # Overall entries
        assert cat_doc["overall"]["ut"] is not None
        assert cat_doc["overall"]["ut"]["line_pct"] == 98.0
        assert cat_doc["overall"]["integration-int"] is not None

        index_html = (dest / "index.html").read_text(encoding="utf-8")
        assert "<details" in index_html and "Svc/" in index_html and "Drv/" in index_html
        assert "Svc/CmdDispatcher" in index_html
        assert "Drv/LinuxGpio" in index_html
        assert "unit test" in index_html
        assert "integration (int)" in index_html
        assert ">Kind</th>" in index_html
        assert ">Line</th>" in index_html
        assert ">Function</th>" in index_html
        assert ">Branch</th>" in index_html
        assert "pct-green" in index_html


def test_compare_flags_regression_and_new_module():
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "src"
        baseline = Path(tmp) / "baseline"
        source.mkdir()
        baseline.mkdir()

        # PR side: Svc/CmdDispatcher regressed from high -> mid (98 -> 86)
        (source / "Svc" / "CmdDispatcher" / "coverage").mkdir(parents=True)
        shutil.copy2(FIXTURES / "summary_mid.json", source / "Svc/CmdDispatcher/coverage/summary.json")
        # New module on PR
        (source / "Svc" / "Foo" / "coverage").mkdir(parents=True)
        shutil.copy2(FIXTURES / "summary_high.json", source / "Svc/Foo/coverage/summary.json")
        # Global PR
        (source / "coverage").mkdir(exist_ok=True)
        shutil.copy2(FIXTURES / "summary_mid.json", source / "coverage/summary.json")

        # Baseline side: CmdDispatcher had high coverage (in coverage-ut subdir)
        (baseline / "Svc" / "CmdDispatcher" / "coverage-ut").mkdir(parents=True)
        shutil.copy2(FIXTURES / "summary_high.json", baseline / "Svc/CmdDispatcher/coverage-ut/summary.json")
        # Baseline global
        (baseline / "coverage-ut").mkdir(exist_ok=True)
        shutil.copy2(FIXTURES / "summary_high.json", baseline / "coverage-ut/summary.json")

        modules_jsonl = _modules_jsonl([
            {"path": "Svc/CmdDispatcher", "has_ut": True},
            {"path": "Svc/Foo", "has_ut": True},
            {"path": "Drv/LinuxGpio", "has_ut": False},
        ])
        out = Path(tmp) / "comment.md"
        regs = Path(tmp) / "regressions.json"

        rc = compare.main([
            "--source", str(source),
            "--baseline", str(baseline),
            "--modules-jsonl", str(modules_jsonl),
            "--coverage-kind", "ut",
            "--base-ref", "devel",
            "--threshold", "0.5",
            "--output", str(out),
            "--regressions-output", str(regs),
        ])
        assert rc == 0  # threshold ok but fail-on-regression not set
        body = out.read_text(encoding="utf-8")
        assert "Svc/CmdDispatcher" in body
        assert "-12.00" in body  # line delta: 86 - 98 = -12
        assert "-8.33" in body  # function delta: mid(85.0) - high(93.33)
        assert "Svc/Foo" in body
        assert "#### New modules" in body
        # "Modules without UTs" section is removed for all kinds
        assert "Modules without UTs" not in body
        # Kind label in header
        assert "Unit Test coverage report" in body
        regression_list = json.loads(regs.read_text(encoding="utf-8"))
        paths = {r["path"] for r in regression_list}
        assert "Svc/CmdDispatcher" in paths
        # Now with fail-on-regression we expect a nonzero exit
        rc2 = compare.main([
            "--source", str(source),
            "--baseline", str(baseline),
            "--modules-jsonl", str(modules_jsonl),
            "--coverage-kind", "ut",
            "--base-ref", "devel",
            "--threshold", "0.5",
            "--output", str(out),
            "--regressions-output", str(regs),
            "--fail-on-regression",
        ])
        assert rc2 == 1


def test_compare_integration_kind_with_suffix():
    """compare works with --coverage-kind integration-int (with suffix)."""
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "src"
        baseline = Path(tmp) / "baseline"
        source.mkdir()
        baseline.mkdir()

        (source / "Svc" / "CmdDispatcher" / "coverage").mkdir(parents=True)
        shutil.copy2(FIXTURES / "summary_mid.json", source / "Svc/CmdDispatcher/coverage/summary.json")
        (source / "coverage").mkdir(exist_ok=True)
        shutil.copy2(FIXTURES / "summary_mid.json", source / "coverage/summary.json")

        # Baseline uses coverage-integration-int subdir
        (baseline / "Svc" / "CmdDispatcher" / "coverage-integration-int").mkdir(parents=True)
        shutil.copy2(FIXTURES / "summary_high.json", baseline / "Svc/CmdDispatcher/coverage-integration-int/summary.json")
        (baseline / "coverage-integration-int").mkdir(exist_ok=True)
        shutil.copy2(FIXTURES / "summary_high.json", baseline / "coverage-integration-int/summary.json")

        modules_jsonl = _modules_jsonl([
            {"path": "Svc/CmdDispatcher", "has_ut": True},
        ])
        out = Path(tmp) / "comment.md"

        rc = compare.main([
            "--source", str(source),
            "--baseline", str(baseline),
            "--modules-jsonl", str(modules_jsonl),
            "--coverage-kind", "integration-int",
            "--base-ref", "devel",
            "--threshold", "0.5",
            "--output", str(out),
        ])
        assert rc == 0
        body = out.read_text(encoding="utf-8")
        assert "Integration (int) coverage report" in body
        assert "Modules without UTs" not in body


def test_compare_summary_comment_output():
    """--summary-output writes a separate per-module summary markdown."""
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "src"
        baseline = Path(tmp) / "baseline"
        source.mkdir()
        baseline.mkdir()

        (source / "Svc" / "CmdDispatcher" / "coverage").mkdir(parents=True)
        shutil.copy2(FIXTURES / "summary_high.json", source / "Svc/CmdDispatcher/coverage/summary.json")
        (source / "coverage").mkdir(exist_ok=True)
        shutil.copy2(FIXTURES / "summary_high.json", source / "coverage/summary.json")

        modules_jsonl = _modules_jsonl([
            {"path": "Svc/CmdDispatcher", "has_ut": True},
        ])
        out = Path(tmp) / "comment.md"
        summary_out = Path(tmp) / "summary.md"

        rc = compare.main([
            "--source", str(source),
            "--baseline", str(baseline),
            "--modules-jsonl", str(modules_jsonl),
            "--coverage-kind", "ut",
            "--base-ref", "devel",
            "--threshold", "0.5",
            "--output", str(out),
            "--summary-output", str(summary_out),
            "--baseline-missing",
        ])
        assert rc == 0
        body = summary_out.read_text(encoding="utf-8")
        assert "Unit Test coverage summary" in body
        assert "98.00" in body  # line percent from summary_high
        assert "Svc/CmdDispatcher" in body
        assert "<!-- fprime-coverage-summary-comment -->" in body


def test_catalog_with_multiple_suffixes():
    """Catalog discovers multiple integration suffixes dynamically."""
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp)

        mod_path = "Svc/CmdDispatcher"
        # UT coverage
        ut_dir = dest / mod_path / "coverage-ut"
        ut_dir.mkdir(parents=True)
        shutil.copy2(FIXTURES / "summary_high.json", ut_dir / "summary.json")
        (ut_dir / "index.html").write_text("<html>ut report</html>", encoding="utf-8")

        # integration-int coverage
        int_dir = dest / mod_path / "coverage-integration-int"
        int_dir.mkdir(parents=True)
        shutil.copy2(FIXTURES / "summary_mid.json", int_dir / "summary.json")
        (int_dir / "index.html").write_text("<html>int report</html>", encoding="utf-8")

        # integration-hil-arm coverage
        hil_dir = dest / mod_path / "coverage-integration-hil-arm"
        hil_dir.mkdir(parents=True)
        shutil.copy2(FIXTURES / "summary_mid.json", hil_dir / "summary.json")
        (hil_dir / "index.html").write_text("<html>hil-arm report</html>", encoding="utf-8")

        # Global overalls
        (dest / "coverage-ut").mkdir(parents=True)
        shutil.copy2(FIXTURES / "summary_high.json", dest / "coverage-ut" / "summary.json")
        (dest / "coverage-integration-int").mkdir(parents=True)
        shutil.copy2(FIXTURES / "summary_mid.json", dest / "coverage-integration-int" / "summary.json")
        (dest / "coverage-integration-hil-arm").mkdir(parents=True)
        shutil.copy2(FIXTURES / "summary_mid.json", dest / "coverage-integration-hil-arm" / "summary.json")

        modules_jsonl = _modules_jsonl([
            {"path": "Svc/CmdDispatcher", "has_ut": True},
        ])

        rc = catalog.main([
            "--dest", str(dest),
            "--modules-jsonl", str(modules_jsonl),
            "--ref", "devel",
            "--ref-type", "branch",
            "--commit", "abc123",
            "--generated-at", "2026-05-29T00:00:00Z",
        ])
        assert rc == 0

        cat_doc = json.loads((dest / "catalog.json").read_text(encoding="utf-8"))
        by_path = {m["path"]: m for m in cat_doc["modules"]}
        mod = by_path["Svc/CmdDispatcher"]
        assert mod["ut"]["has_coverage"] is True
        assert mod["integration-int"]["has_coverage"] is True
        assert mod["integration-hil-arm"]["has_coverage"] is True

        # Overall entries
        assert cat_doc["overall"]["ut"] is not None
        assert cat_doc["overall"]["integration-int"] is not None
        assert cat_doc["overall"]["integration-hil-arm"] is not None

        index_html = (dest / "index.html").read_text(encoding="utf-8")
        assert "unit test" in index_html
        assert "integration (int)" in index_html
        assert "integration (hil-arm)" in index_html


def test_compare_baseline_missing_reports_no_baseline():
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "src"
        baseline = Path(tmp) / "baseline"
        source.mkdir()
        baseline.mkdir()
        (source / "Svc" / "CmdDispatcher" / "coverage").mkdir(parents=True)
        shutil.copy2(FIXTURES / "summary_high.json", source / "Svc/CmdDispatcher/coverage/summary.json")

        modules_jsonl = _modules_jsonl([
            {"path": "Svc/CmdDispatcher", "has_ut": True},
        ])
        out = Path(tmp) / "comment.md"
        rc = compare.main([
            "--source", str(source),
            "--baseline", str(baseline),
            "--modules-jsonl", str(modules_jsonl),
            "--coverage-kind", "ut",
            "--base-ref", "devel",
            "--threshold", "0.5",
            "--output", str(out),
            "--baseline-missing",
        ])
        assert rc == 0
        body = out.read_text(encoding="utf-8")
        assert "No baseline branch" in body
        # No regressions can be flagged when baseline is missing
        assert "#### Regressions" in body
        assert "_(none over threshold)_" in body


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


TESTS = [
    test_discover_finds_modules_and_ut_flag,
    test_discover_ignores_commented_out_calls,
    test_summary_load_handles_missing_file_and_zero_total,
    test_summary_load_parses_gcovr_json,
    test_mirror_module_renames_coverage_html_to_index,
    test_mirror_module_writes_placeholder_when_no_ut,
    test_mirror_integration_placeholder,
    test_catalog_relative_path_math,
    test_mirror_module_is_idempotent,
    test_mirror_preserves_other_kind,
    test_catalog_combined_landing_page,
    test_compare_flags_regression_and_new_module,
    test_compare_integration_kind_with_suffix,
    test_compare_summary_comment_output,
    test_catalog_with_multiple_suffixes,
    test_compare_baseline_missing_reports_no_baseline,
]


def main() -> int:
    failed = 0
    for t in TESTS:
        buf = io.StringIO()
        try:
            with redirect_stderr(buf):
                t()
            print(f"OK   {t.__name__}")
        except Exception:
            failed += 1
            print(f"FAIL {t.__name__}")
            print(buf.getvalue())
            traceback.print_exc()
    print()
    if failed:
        print(f"{failed} test(s) failed.")
        return 1
    print(f"All {len(TESTS)} tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

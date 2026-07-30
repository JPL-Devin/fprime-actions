"""Unit tests for the component-checks scripts.

Run with:  python3 component-checks/tests/test_checks.py

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
from contextlib import redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS_DIR = HERE.parent / "scripts"
COMMON_SCRIPTS = HERE.parent.parent / "coverage-common" / "scripts"
FIXTURES = HERE / "fixtures"
WIDGET = FIXTURES / "Svc" / "Widget"

sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(COMMON_SCRIPTS))

import _fpp  # noqa: E402
import _requirements  # noqa: E402
import check_build_warnings  # noqa: E402
import check_command_handlers  # noqa: E402
import check_dp_priorities  # noqa: E402
import check_dp_priority_configurable  # noqa: E402
import check_include_dependencies  # noqa: E402
import check_port_handlers  # noqa: E402
import check_req_commands  # noqa: E402
import check_req_design_mapping  # noqa: E402
import check_req_events  # noqa: E402
import check_req_parameters  # noqa: E402
import check_req_parent_trace  # noqa: E402
import check_req_ports  # noqa: E402
import check_req_telemetry  # noqa: E402
import check_req_verification  # noqa: E402
import check_sm_actions  # noqa: E402
import check_static_analysis  # noqa: E402
import check_ut_artifacts  # noqa: E402
import check_ut_include_dependencies  # noqa: E402
import run_checks  # noqa: E402
from _tiers import checks_tier  # noqa: E402

FAILURES: list[str] = []


def check(name: str, condition: bool, extra: str = "") -> None:
    if condition:
        print(f"OK   {name}")
    else:
        print(f"FAIL {name} {extra}")
        FAILURES.append(name)


def run(main, argv) -> tuple[int, str]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = main(argv)
    return code, buf.getvalue()


def test_fpp_parsing() -> None:
    model = _fpp.load_module_model(WIDGET)
    check("fpp: commands", sorted(model.commands) == ["SET_PRIORITY", "START", "STOP"])
    check("fpp: telemetry", model.telemetry == ["WidgetCount"])
    check("fpp: events", sorted(model.events) == ["WidgetError", "WidgetStarted"])
    check("fpp: parameters", model.parameters == ["THRESHOLD"])
    check("fpp: records", model.records == ["WidgetRecord"])
    check(
        "fpp: containers",
        [(c.name, c.has_default_priority) for c in model.containers]
        == [("WidgetContainer", True), ("OrphanContainer", False)],
    )
    check(
        "fpp: input ports",
        [(p.name, p.kind) for p in model.input_ports] == [("run", "async"), ("dataIn", "sync")],
    )
    check("fpp: output ports", [p.name for p in model.output_ports] == ["dataOut"])
    machines = {m.name: m.actions for m in model.state_machines}
    check("fpp: state machine actions", machines.get("DeviceSm") == ["doStart", "doStop"])


def test_requirements_parsing() -> None:
    reqs = _requirements.load_requirements([WIDGET / "docs" / "sdd.md"])
    check("reqs: count", len(reqs) == 7, f"got {len(reqs)}")
    by_id = {r.req_id: r for r in reqs}
    check("reqs: parent parsed", by_id["WID-001"].parent == "SYS-010")
    check("reqs: verification parsed", by_id["WID-004"].verification == "Analysis")
    check("reqs: missing parent empty", by_id["WID-007"].parent == "")


def test_requirement_checks() -> None:
    for name, mod in (
        ("R1 commands", check_req_commands),
        ("R2 telemetry", check_req_telemetry),
        ("R3 events", check_req_events),
        ("R4 parameters", check_req_parameters),
        ("R6 ports", check_req_ports),
    ):
        code, out = run(mod.main, ["--module", str(WIDGET)])
        check(f"{name}: passes", code == 0, out)

    code, out = run(check_req_parent_trace.main, ["--module", str(WIDGET)])
    check("R7: fails on WID-007", code == 1 and "WID-007" in out, out)

    code, out = run(check_req_verification.main, ["--module", str(WIDGET)])
    check("R8: passes", code == 0, out)

    # Remove a requirement reference -> R1 fails
    with tempfile.TemporaryDirectory() as tmp:
        mod_dir = Path(tmp) / "Svc" / "Widget"
        shutil.copytree(WIDGET, mod_dir)
        sdd = mod_dir / "docs" / "sdd.md"
        sdd.write_text(sdd.read_text().replace("START and STOP", "begin and halt"))
        code, out = run(check_req_commands.main, ["--module", str(mod_dir)])
        check("R1: fails on untraced command", code == 1 and "START" in out, out)


def test_design_checks() -> None:
    code, out = run(check_port_handlers.main, ["--module", str(WIDGET)])
    check("D1: passes", code == 0, out)

    code, out = run(check_command_handlers.main, ["--module", str(WIDGET)])
    check("D2: passes", code == 0, out)

    code, out = run(check_sm_actions.main, ["--module", str(WIDGET)])
    check("D3: fails on doStop", code == 1 and "doStop" in out, out)

    code, out = run(check_dp_priorities.main, ["--module", str(WIDGET)])
    check("D4: fails on OrphanContainer", code == 1 and "OrphanContainer" in out, out)

    code, out = run(check_req_design_mapping.main, ["--module", str(WIDGET)])
    check("D5: fails on WID-007", code == 1 and "WID-007" in out, out)

    with tempfile.TemporaryDirectory() as tmp:
        mod_dir = Path(tmp) / "Svc" / "Widget"
        shutil.copytree(WIDGET, mod_dir)
        cpp = mod_dir / "Widget.cpp"
        cpp.write_text(cpp.read_text().replace("STOP_cmdHandler", "IGNORED"))
        code, out = run(check_command_handlers.main, ["--module", str(mod_dir)])
        check("D2: fails on missing handler", code == 1 and "STOP" in out, out)


def test_implementation_checks() -> None:
    code, out = run(check_include_dependencies.main, ["--module", str(WIDGET)])
    check("I1: fails on Fw/Buffer", code == 1 and "Fw/Buffer" in out, out)
    check("I1: Os accepted", "'Os'" not in out, out)

    code, out = run(check_dp_priority_configurable.main, ["--module", str(WIDGET)])
    check("I3: passes via SET_PRIORITY", code == 0, out)

    # I2 in log mode
    with tempfile.TemporaryDirectory() as tmp:
        log = Path(tmp) / "build.log"
        log.write_text("foo.cpp:10:5: warning: unused variable 'x' [-Wunused]\nok\n")
        code, out = run(
            check_build_warnings.main, ["--module", str(WIDGET), "--log", str(log)]
        )
        check("I2: fails on warning in log", code == 1 and "unused variable" in out, out)
        log.write_text("all good\n")
        code, out = run(
            check_build_warnings.main, ["--module", str(WIDGET), "--log", str(log)]
        )
        check("I2: passes on clean log", code == 0, out)


def test_static_analysis_check() -> None:
    sarif = {
        "runs": [
            {
                "tool": {"driver": {"rules": [
                    {"id": "cpp/rule-a", "properties": {"security-severity": "8.0"}},
                    {"id": "cpp/rule-b"},
                ]}},
                "results": [
                    {
                        "ruleId": "cpp/rule-a",
                        "level": "warning",
                        "message": {"text": "bad thing"},
                        "locations": [{"physicalLocation": {
                            "artifactLocation": {"uri": "Svc/Widget/Widget.cpp"},
                            "region": {"startLine": 3},
                        }}],
                    },
                    {
                        "ruleId": "cpp/rule-b",
                        "level": "note",
                        "message": {"text": "minor"},
                        "locations": [{"physicalLocation": {
                            "artifactLocation": {"uri": "Svc/Widget/Widget.cpp"},
                            "region": {"startLine": 4},
                        }}],
                    },
                    {
                        "ruleId": "cpp/rule-b",
                        "level": "error",
                        "message": {"text": "elsewhere"},
                        "locations": [{"physicalLocation": {
                            "artifactLocation": {"uri": "Svc/Other/Other.cpp"},
                            "region": {"startLine": 5},
                        }}],
                    },
                ],
            }
        ]
    }
    with tempfile.TemporaryDirectory() as tmp:
        sarif_path = Path(tmp) / "results.sarif"
        sarif_path.write_text(json.dumps(sarif))
        code, out = run(
            check_static_analysis.main,
            ["--module", "Svc/Widget", "--sarif", str(sarif_path)],
        )
        check("I4: fails on error finding", code == 1 and "rule-a" in out, out)
        check("I4: ignores other module", "Other" not in out, out)
        check("I4: low below threshold", "minor" not in out, out)
        code, out = run(
            check_static_analysis.main,
            ["--module", "Svc/Widget", "--sarif", str(sarif_path),
             "--severity-threshold", "low"],
        )
        check("I4: low threshold catches note", code == 1 and "minor" in out, out)


def test_unit_testing_checks() -> None:
    code, out = run(check_ut_include_dependencies.main, ["--module", str(WIDGET)])
    check("U3: passes (STest covers STest/Pick)", code == 0, out)

    with tempfile.TemporaryDirectory() as tmp:
        artifacts = Path(tmp)
        code, out = run(
            check_ut_artifacts.main,
            ["--module", "Svc/Widget", "--artifacts-dir", str(artifacts)],
        )
        check("U1: fails when missing", code == 1, out)
        target = artifacts / "Svc" / "Widget" / "coverage"
        target.mkdir(parents=True)
        (target / "summary.json").write_text("{}")
        (target / "index.html").write_text("<html></html>")
        code, out = run(
            check_ut_artifacts.main,
            ["--module", "Svc/Widget", "--artifacts-dir", str(artifacts)],
        )
        check("U1: passes when present", code == 0, out)


def test_checks_tier() -> None:
    check("tier: all pass", checks_tier(10, 0) == "platinum")
    check("tier: 90%+", checks_tier(19, 1) == "gold")
    check("tier: 80%+", checks_tier(8, 2) == "silver")
    check("tier: below", checks_tier(1, 9) == "bronze")
    check("tier: none", checks_tier(0, 0) == "bronze")


def test_run_checks_and_catalog() -> None:
    import catalog

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "repo"
        shutil.copytree(FIXTURES, root)
        dest = Path(tmp) / "dest"
        modules_jsonl = Path(tmp) / "modules.jsonl"
        modules_jsonl.write_text(json.dumps({"path": "Svc/Widget", "has_ut": True}) + "\n")

        extra = Path(tmp) / "extra.jsonl"
        extra.write_text(
            json.dumps(
                {
                    "id": "U5",
                    "name": "Sufficient code coverage",
                    "category": "unit-testing",
                    "module": "Svc/Widget",
                    "status": "pass",
                    "failures": [],
                    "detail": "line coverage 91.00% (threshold 80.00%)",
                }
            )
            + "\n"
        )

        code, out = run(
            run_checks.main,
            [
                "--root", str(root),
                "--dest", str(dest),
                "--modules-jsonl", str(modules_jsonl),
                "--extra-results", str(extra),
                "--ref", "devel",
                "--commit", "abc1234def",
            ],
        )
        check("run_checks: exit 0 (publish mode)", code == 0, out)

        summary_path = dest / "Svc" / "Widget" / "checks" / "summary.json"
        check("run_checks: summary written", summary_path.is_file())
        summary = json.loads(summary_path.read_text())
        ids = {c["id"] for c in summary["checks"]}
        check("run_checks: static checks recorded", {"R1", "R7", "D4", "I1", "U3"} <= ids)
        check("run_checks: extra results merged", "U5" in ids)
        check(
            "run_checks: counts",
            summary["failed"] >= 4 and summary["passed"] >= 8,
            json.dumps({"passed": summary["passed"], "failed": summary["failed"]}),
        )
        page = (dest / "Svc" / "Widget" / "checks" / "index.html").read_text()
        check("run_checks: page has fail badge", "status-fail" in page)

        code, _ = run(
            run_checks.main,
            [
                "--root", str(root),
                "--dest", str(dest),
                "--modules-jsonl", str(modules_jsonl),
                "--gate",
            ],
        )
        check("run_checks: --gate exits 1", code == 1)

        # Catalog picks up the checks summary
        code, _ = run(
            catalog.main,
            [
                "--dest", str(dest),
                "--modules-jsonl", str(modules_jsonl),
                "--ref", "devel",
                "--commit", "abc1234def",
            ],
        )
        check("catalog: exit 0", code == 0)
        index = (dest / "index.html").read_text()
        check("catalog: Checks column", "<th class=\"cell\">Checks</th>" in index)
        check("catalog: checks link", "Svc/Widget/checks/index.html" in index)
        cat = json.loads((dest / "catalog.json").read_text())
        entry = cat["modules"][0]
        check("catalog: checks entry", entry["checks"] is not None)
        check("catalog: checks tier", entry["tiers"]["checks"] in ("gold", "silver", "bronze"))
        module_page = (dest / "Svc" / "Widget" / "index.html").read_text()
        check("catalog: module page Checks row", "<td>Checks</td>" in module_page)


def main() -> int:
    tests = [
        test_fpp_parsing,
        test_requirements_parsing,
        test_requirement_checks,
        test_design_checks,
        test_implementation_checks,
        test_static_analysis_check,
        test_unit_testing_checks,
        test_checks_tier,
        test_run_checks_and_catalog,
    ]
    for test in tests:
        try:
            test()
        except Exception:  # noqa: BLE001
            print(f"FAIL {test.__name__} raised:")
            traceback.print_exc()
            FAILURES.append(test.__name__)
    if FAILURES:
        print(f"\n{len(FAILURES)} failure(s): {', '.join(FAILURES)}")
        return 1
    print("\nAll tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

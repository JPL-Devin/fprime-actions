#!/usr/bin/env python3
"""U1 -- Unit-test output/results published.

Verifies the component's unit-test output/results artifacts exist in the
expected published location -- by default the coverage baseline layout
(``<artifacts-dir>/<module>/coverage/summary.json``) written by
nasa/fprime-actions coverage-update.  Exits non-zero when missing.
"""

import sys
from pathlib import Path

from _report import finish, make_parser


def main(argv=None) -> int:
    parser = make_parser(__doc__)
    parser.add_argument(
        "--artifacts-dir",
        type=Path,
        required=True,
        help="Published artifacts root (e.g. a checkout of the coverage/<ref> branch)",
    )
    parser.add_argument(
        "--expect",
        action="append",
        default=None,
        help="Artifact path(s) expected under <artifacts-dir>/<module>/ "
        "(default: coverage/summary.json and coverage/index.html)",
    )
    parser.add_argument(
        "--module-path",
        default=None,
        help="Module path relative to the artifacts dir (default: --module as given)",
    )
    args = parser.parse_args(argv)

    expected = args.expect or ["coverage/summary.json", "coverage/index.html"]
    module_rel = args.module_path or str(args.module)
    base = args.artifacts_dir / module_rel

    failures = [
        f"expected unit-test artifact missing: {base / rel}"
        for rel in expected
        if not (base / rel).is_file()
    ]

    return finish(
        check_id="U1",
        name="Unit-test results published",
        category="unit-testing",
        module=args.module,
        failures=failures,
        detail=f"{len(expected)} artifact(s) checked under {base}",
        json_output=args.json_output,
    )


if __name__ == "__main__":
    sys.exit(main())

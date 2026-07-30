#!/usr/bin/env python3
"""R7 -- Requirement traceability to parents.

Reads the requirements source and verifies every requirement declares a
trace/link to at least one parent requirement (a non-empty Parent/Trace
column).  Exits non-zero listing any requirement missing a parent trace.
"""

import sys

from _report import finish, make_parser
from _requirements import default_requirement_files, load_requirements

_EMPTY = {"", "-", "--", "n/a", "na", "none", "tbd"}


def main(argv=None) -> int:
    parser = make_parser(__doc__)
    args = parser.parse_args(argv)

    req_files = args.requirements or default_requirement_files(args.module)
    reqs = load_requirements(req_files)

    skipped_reason = None
    if not reqs:
        skipped_reason = "no requirements found"

    failures = [
        f"requirement '{r.req_id}' ({r.source}) has no parent trace "
        f"(add a Parent/Trace column entry linking a parent requirement)"
        for r in reqs
        if r.parent.strip().lower() in _EMPTY
    ]

    return finish(
        check_id="R7",
        name="Requirement parent traceability",
        category="requirements",
        module=args.module,
        failures=failures,
        skipped_reason=skipped_reason,
        detail=f"{len(reqs)} requirement(s) checked",
        json_output=args.json_output,
    )


if __name__ == "__main__":
    sys.exit(main())

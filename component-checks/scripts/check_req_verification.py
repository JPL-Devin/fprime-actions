#!/usr/bin/env python3
"""R8 -- Requirement verification method present.

Reads the requirements source and verifies every requirement specifies a
recognized verification method (Test/Analysis/Inspection/Demonstration).
Exits non-zero listing any requirement missing one.
"""

import re
import sys

from _report import finish, make_parser
from _requirements import default_requirement_files, load_requirements

_METHOD_RE = re.compile(
    r"\b(test|unit\s*test|analysis|inspection|demonstration|demo)\b", re.IGNORECASE
)


def main(argv=None) -> int:
    parser = make_parser(__doc__)
    args = parser.parse_args(argv)

    req_files = args.requirements or default_requirement_files(args.module)
    reqs = load_requirements(req_files)

    skipped_reason = None
    if not reqs:
        skipped_reason = "no requirements found"

    failures = [
        f"requirement '{r.req_id}' ({r.source}) has no verification method "
        f"(expected one of Test/Analysis/Inspection/Demonstration, got: '{r.verification or '<empty>'}')"
        for r in reqs
        if not _METHOD_RE.search(r.verification)
    ]

    return finish(
        check_id="R8",
        name="Requirement verification method",
        category="requirements",
        module=args.module,
        failures=failures,
        skipped_reason=skipped_reason,
        detail=f"{len(reqs)} requirement(s) checked",
        json_output=args.json_output,
    )


if __name__ == "__main__":
    sys.exit(main())

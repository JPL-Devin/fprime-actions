#!/usr/bin/env python3
"""D5 -- Requirements mapped to design artifacts.

Verifies every component requirement is traced to at least one design
artifact: either the requirement row carries a non-empty Design column, or
the requirement ID is referenced elsewhere in the module documentation
(e.g. a design section or trace matrix).  Exits non-zero listing any
requirement with no design mapping.
"""

import re
import sys

from _report import finish, make_parser
from _requirements import default_requirement_files, load_requirements

_EMPTY = {"", "-", "--", "n/a", "na", "none", "tbd"}


def main(argv=None) -> int:
    parser = make_parser(__doc__)
    args = parser.parse_args(argv)

    req_files = args.requirements or default_requirement_files(args.module)
    reqs = load_requirements(req_files)

    docs_text = ""
    for path in req_files:
        try:
            docs_text += path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

    skipped_reason = None
    if not reqs:
        skipped_reason = "no requirements found"

    failures = []
    if skipped_reason is None:
        for req in reqs:
            if req.design.strip().lower() not in _EMPTY:
                continue
            # Referenced again outside its own requirement row counts as a
            # design mapping (e.g. mentioned in a design/trace section).
            mentions = len(re.findall(rf"\b{re.escape(req.req_id)}\b", docs_text))
            if mentions <= 1:
                failures.append(
                    f"requirement '{req.req_id}' ({req.source}) is not mapped to any "
                    f"design artifact (add a Design column entry or reference it in a design section)"
                )

    return finish(
        check_id="D5",
        name="Requirements mapped to design artifacts",
        category="design",
        module=args.module,
        failures=failures,
        skipped_reason=skipped_reason,
        detail=f"{len(reqs)} requirement(s) checked",
        json_output=args.json_output,
    )


if __name__ == "__main__":
    sys.exit(main())

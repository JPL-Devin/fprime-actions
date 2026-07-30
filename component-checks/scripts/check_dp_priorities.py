#!/usr/bin/env python3
"""D4 -- Data product containers have a default priority.

Parses the FPP model for all data product containers and verifies each is
assigned a ``default priority``.  Exits non-zero listing any container
missing one.
"""

import sys

from _fpp import load_module_model
from _report import finish, make_parser


def main(argv=None) -> int:
    parser = make_parser(__doc__)
    args = parser.parse_args(argv)

    model = load_module_model(args.module)

    skipped_reason = None
    if not model.fpp_files:
        skipped_reason = "no FPP files found"
    elif not model.containers:
        skipped_reason = "no data product containers declared"

    failures = [
        f"data product container '{c.name}' has no 'default priority' clause"
        for c in model.containers
        if not c.has_default_priority
    ]

    return finish(
        check_id="D4",
        name="Data product containers have default priority",
        category="design",
        module=args.module,
        failures=failures,
        skipped_reason=skipped_reason,
        detail=f"{len(model.containers)} container(s) checked",
        json_output=args.json_output,
    )


if __name__ == "__main__":
    sys.exit(main())

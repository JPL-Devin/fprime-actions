#!/usr/bin/env python3
"""D2 -- Command handlers defined.

Parses the FPP model for all commands and verifies the component
implementation provides a ``<COMMAND>_cmdHandler`` for each.  Exits
non-zero listing any command without a handler.
"""

import re
import sys

from _fpp import load_module_model
from _report import finish, make_parser
from _sources import impl_sources, read_all


def main(argv=None) -> int:
    parser = make_parser(__doc__)
    args = parser.parse_args(argv)

    model = load_module_model(args.module)
    text = read_all(impl_sources(args.module))

    skipped_reason = None
    if not model.fpp_files:
        skipped_reason = "no FPP files found"
    elif not model.commands:
        skipped_reason = "no commands declared"

    failures = []
    if skipped_reason is None:
        for command in model.commands:
            if not re.search(rf"\b{re.escape(command)}_cmdHandler\s*\(", text):
                failures.append(
                    f"command '{command}' has no '{command}_cmdHandler' in the implementation"
                )

    return finish(
        check_id="D2",
        name="Command handlers defined",
        category="design",
        module=args.module,
        failures=failures,
        skipped_reason=skipped_reason,
        detail=f"{len(model.commands)} command(s) checked",
        json_output=args.json_output,
    )


if __name__ == "__main__":
    sys.exit(main())

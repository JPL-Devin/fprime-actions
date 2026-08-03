#!/usr/bin/env python3
"""D3 -- State machine actions defined.

Parses the FPP state machine definitions for all declared actions and
verifies each has an ``action_<name>`` implementation in the component.
Exits non-zero listing any action without an implementation.
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

    actions = [
        (machine.name, action)
        for machine in model.state_machines
        for action in machine.actions
    ]

    skipped_reason = None
    if not model.fpp_files:
        skipped_reason = "no FPP files found"
    elif not model.state_machines:
        skipped_reason = "no state machines declared"
    elif not actions:
        skipped_reason = "state machines declare no actions"

    failures = []
    if skipped_reason is None:
        for machine, action in actions:
            if not re.search(rf"\baction_{re.escape(action)}\s*\(", text):
                failures.append(
                    f"state machine '{machine}' action '{action}' has no "
                    f"'action_{action}' implementation"
                )

    return finish(
        check_id="D3",
        name="State machine actions defined",
        category="design",
        module=args.module,
        failures=failures,
        skipped_reason=skipped_reason,
        detail=f"{len(actions)} action(s) checked",
        json_output=args.json_output,
    )


if __name__ == "__main__":
    sys.exit(main())

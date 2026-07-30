#!/usr/bin/env python3
"""I3 -- Data product priorities configurable.

Parses the FPP model and verifies the priority of each data product
container produced by the component is configurable at runtime via a
command or parameter: either a container-specific knob (name mentions
both the container and "priority") or a module-level priority knob
(any command/parameter mentioning "priority", which satisfies every
container).  Exits non-zero listing any container whose priority cannot
be configured.

Note: F´ ships ``Svc.DpCatalog``/``Svc.DpManager`` style deployments where
priority is managed centrally; use ``--assume-managed`` to pass modules
that only rely on the framework-level mechanism.
"""

import re
import sys

from _fpp import load_module_model
from _report import finish, make_parser


def main(argv=None) -> int:
    parser = make_parser(__doc__)
    parser.add_argument(
        "--assume-managed",
        action="store_true",
        help="Treat priorities as configurable via a framework-level manager",
    )
    args = parser.parse_args(argv)

    model = load_module_model(args.module)

    skipped_reason = None
    if not model.fpp_files:
        skipped_reason = "no FPP files found"
    elif not model.containers:
        skipped_reason = "no data product containers declared"
    elif args.assume_managed:
        skipped_reason = "priorities managed by framework (--assume-managed)"

    knobs = model.commands + model.parameters
    generic_knob = any("priority" in knob.lower() for knob in knobs)
    failures = []
    if skipped_reason is None:
        for container in model.containers:
            specific = re.compile(
                rf"({re.escape(container.name)}.*priority|priority.*{re.escape(container.name)})",
                re.IGNORECASE,
            )
            if not (generic_knob or any(specific.search(knob) for knob in knobs)):
                failures.append(
                    f"container '{container.name}' priority is not configurable: no command or "
                    f"parameter mentioning 'priority' found"
                )

    return finish(
        check_id="I3",
        name="Data product priorities configurable",
        category="implementation",
        module=args.module,
        failures=failures,
        skipped_reason=skipped_reason,
        detail=f"{len(model.containers)} container(s) checked against {len(knobs)} command(s)/parameter(s)",
        json_output=args.json_output,
    )


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""D1 -- Input port handlers defined.

Parses the FPP model for all typed input ports and verifies the component
implementation provides a ``<port>_handler`` override for each.  Exits
non-zero listing any input port without a handler.
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
    elif not model.input_ports:
        skipped_reason = "no typed input ports declared"

    failures = []
    if skipped_reason is None:
        for port in model.input_ports:
            if not re.search(rf"\b{re.escape(port.name)}_handler\s*\(", text):
                failures.append(
                    f"input port '{port.name}' ({port.kind}) has no "
                    f"'{port.name}_handler' override in the implementation"
                )

    return finish(
        check_id="D1",
        name="Input port handlers defined",
        category="design",
        module=args.module,
        failures=failures,
        skipped_reason=skipped_reason,
        detail=f"{len(model.input_ports)} input port(s) checked",
        json_output=args.json_output,
    )


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""R6 -- Requirement per port/interface.

Parses the module's FPP model for all ports and verifies a requirement
exists referencing each one by name.  Exits non-zero listing any port
lacking a requirement.
"""

import sys

from _req_item_check import run_item_check


def main(argv=None) -> int:
    return run_item_check(
        check_id="R6",
        name="Requirement per port/interface",
        kind="port",
        extractor=lambda m: [p.name for p in m.ports],
        argv=argv,
    )


if __name__ == "__main__":
    sys.exit(main())

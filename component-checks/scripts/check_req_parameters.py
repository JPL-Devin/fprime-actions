#!/usr/bin/env python3
"""R4 -- Requirement per parameter.

Parses the module's FPP model for all parameters and verifies a requirement
exists referencing each one by name.  Exits non-zero listing any parameter
lacking a requirement.
"""

import sys

from _req_item_check import run_item_check


def main(argv=None) -> int:
    return run_item_check(
        check_id="R4",
        name="Requirement per parameter",
        kind="parameter",
        extractor=lambda m: m.parameters,
        argv=argv,
    )


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""R1 -- Requirement per command.

Parses the module's FPP model for all commands and verifies a requirement
exists referencing each one by name.  Exits non-zero listing any command
lacking a requirement.
"""

import sys

from _req_item_check import run_item_check


def main(argv=None) -> int:
    return run_item_check(
        check_id="R1",
        name="Requirement per command",
        kind="command",
        extractor=lambda m: m.commands,
        argv=argv,
    )


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""R2 -- Requirement per telemetry channel.

Parses the module's FPP model for all telemetry channels and verifies a requirement
exists referencing each one by name.  Exits non-zero listing any telemetry channel
lacking a requirement.
"""

import sys

from _req_item_check import run_item_check


def main(argv=None) -> int:
    return run_item_check(
        check_id="R2",
        name="Requirement per telemetry channel",
        kind="telemetry channel",
        extractor=lambda m: m.telemetry,
        argv=argv,
    )


if __name__ == "__main__":
    sys.exit(main())

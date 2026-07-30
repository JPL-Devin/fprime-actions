#!/usr/bin/env python3
"""R3 -- Requirement per event.

Parses the module's FPP model for all events and verifies a requirement
exists referencing each one by name.  Exits non-zero listing any event
lacking a requirement.
"""

import sys

from _req_item_check import run_item_check


def main(argv=None) -> int:
    return run_item_check(
        check_id="R3",
        name="Requirement per event",
        kind="event",
        extractor=lambda m: m.events,
        argv=argv,
    )


if __name__ == "__main__":
    sys.exit(main())

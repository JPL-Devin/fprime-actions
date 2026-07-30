#!/usr/bin/env python3
"""R5 -- Requirement per data product.

Parses the module's FPP model for all data products and verifies a requirement
exists referencing each one by name.  Exits non-zero listing any data product
lacking a requirement.
"""

import sys

from _req_item_check import run_item_check


def main(argv=None) -> int:
    return run_item_check(
        check_id="R5",
        name="Requirement per data product",
        kind="data product",
        extractor=lambda m: m.data_products,
        argv=argv,
    )


if __name__ == "__main__":
    sys.exit(main())

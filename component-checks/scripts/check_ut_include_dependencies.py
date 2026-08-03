#!/usr/bin/env python3
"""U3 -- Unit-test source dependencies in CMakeLists.

Parses the unit-test sources for ``#include`` dependencies on other F´
modules and verifies each is declared in the component's CMakeLists.txt
(typically via UT_DEPENDS / DEPENDS or the register_fprime_ut call).
Exits non-zero listing any missing dependency.
"""

import sys

from _report import finish, make_parser
from _sources import includes_of, test_sources
from check_include_dependencies import (
    declared_in_cmake,
    dependency_of,
    is_reportable_dependency,
)


def main(argv=None) -> int:
    parser = make_parser(__doc__)
    parser.add_argument(
        "--cmake",
        default="CMakeLists.txt",
        help="CMake file relative to the module (default: CMakeLists.txt)",
    )
    args = parser.parse_args(argv)

    cmake_path = args.module / args.cmake
    sources = test_sources(args.module)

    skipped_reason = None
    cmake_text = ""
    if not cmake_path.is_file():
        skipped_reason = f"no {args.cmake} found"
    elif not sources:
        skipped_reason = "no unit-test sources found"
    else:
        cmake_text = cmake_path.read_text(encoding="utf-8", errors="replace")
        # Sub-CMake files (e.g. test/ut/CMakeLists.txt) also count.
        for sub in args.module.rglob("CMakeLists.txt"):
            if sub != cmake_path:
                cmake_text += sub.read_text(encoding="utf-8", errors="replace")

    deps_needed = {}
    for include in includes_of(sources):
        dep = dependency_of(include)
        if dep is None:
            continue
        if dep.startswith(("test", "ut")) or not is_reportable_dependency(
            dep, args.module
        ):
            continue
        deps_needed.setdefault(dep, include)

    failures = []
    if skipped_reason is None:
        for dep, example in sorted(deps_needed.items()):
            if not declared_in_cmake(dep, cmake_text):
                failures.append(
                    f"unit-test dependency '{dep}' (from #include \"{example}\") is not "
                    f"declared in the module's CMake files (add it to UT_DEPENDS/DEPENDS)"
                )

    return finish(
        check_id="U3",
        name="Unit-test dependencies in CMakeLists",
        category="unit-testing",
        module=args.module,
        failures=failures,
        skipped_reason=skipped_reason,
        detail=f"{len(deps_needed)} dependency module(s) checked",
        json_output=args.json_output,
    )


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""I1 -- Source dependencies listed in CMakeLists.

Parses the component's non-test sources for ``#include`` dependencies on
other F´ modules and verifies each dependency module is declared in the
component's CMakeLists.txt (e.g. via DEPENDS or an explicit target name).
Exits non-zero listing any missing dependency.

Heuristics: an include of ``Fw/Types/Assert.hpp`` depends on module
``Fw/Types``.  System headers (no directory component), system/platform
headers under a lowercase top-level directory (``sys/socket.h``,
``arpa/inet.h``, ``linux/gpio.h``, ``mach/mach.h``, ``openssl/evp.h``,
...; F´ module directories are CapitalCase), the module's own headers
(including its test helpers), generated autocode headers
(``*Ac.hpp``/``*Ac.h``), and ``config``/``Fpp`` headers are skipped.
"""

import re
import sys
from pathlib import PurePosixPath

from _report import finish, make_parser
from _sources import TEST_DIR_NAMES, impl_sources, includes_of

_SKIP_TOP_DIRS = {"config", "fpp", "gtest", "gmock"}


def dependency_of(include: str) -> str | None:
    """Map an include target to its F´ dependency module path, or None."""
    path = PurePosixPath(include)
    if len(path.parts) < 2:
        return None  # system or local header
    if path.name.endswith(("Ac.hpp", "Ac.h", "Ac.cpp")):
        return None  # generated autocode
    top = path.parts[0]
    if top.lower() in _SKIP_TOP_DIRS:
        return None
    if not top[:1].isupper():
        return None  # system/platform/third-party header (F´ modules are CapitalCase)
    # A test-helper include such as Drv/Ip/test/ut/Helper.hpp depends on Drv/Ip.
    parts = list(path.parts[:-1])
    for i, part in enumerate(parts):
        if part.lower() in TEST_DIR_NAMES:
            parts = parts[:i]
            break
    if not parts:
        return None
    return "/".join(parts)


def declared_in_cmake(dep: str, cmake_text: str) -> bool:
    """True when the dependency module (or an ancestor library that provides
    it, e.g. ``STest`` for ``STest/Pick``) is named in the CMake text."""
    parts = dep.split("/")
    candidates = ["/".join(parts[: i + 1]) for i in range(len(parts))]
    for candidate in candidates:
        for token in (candidate, candidate.replace("/", "_")):
            if re.search(rf"(?<![\w/]){re.escape(token)}(?![\w/])", cmake_text):
                return True
    return False


def main(argv=None) -> int:
    parser = make_parser(__doc__)
    parser.add_argument(
        "--cmake",
        default="CMakeLists.txt",
        help="CMake file relative to the module (default: CMakeLists.txt)",
    )
    args = parser.parse_args(argv)

    cmake_path = args.module / args.cmake
    sources = impl_sources(args.module)

    skipped_reason = None
    cmake_text = ""
    if not cmake_path.is_file():
        skipped_reason = f"no {args.cmake} found"
    elif not sources:
        skipped_reason = "no C++ sources found"
    else:
        cmake_text = cmake_path.read_text(encoding="utf-8", errors="replace")

    module_posix = args.module.resolve().as_posix()
    deps_needed = {}
    for include in includes_of(sources):
        dep = dependency_of(include)
        if dep is None:
            continue
        if module_posix.endswith(dep):
            continue  # header within this module
        deps_needed.setdefault(dep, include)

    failures = []
    if skipped_reason is None:
        for dep, example in sorted(deps_needed.items()):
            if not declared_in_cmake(dep, cmake_text):
                failures.append(
                    f"dependency '{dep}' (from #include \"{example}\") is not declared "
                    f"in {args.cmake} (add it to DEPENDS as {dep.replace('/', '_')})"
                )

    return finish(
        check_id="I1",
        name="Source dependencies listed in CMakeLists",
        category="implementation",
        module=args.module,
        failures=failures,
        skipped_reason=skipped_reason,
        detail=f"{len(deps_needed)} dependency module(s) checked",
        json_output=args.json_output,
    )


if __name__ == "__main__":
    sys.exit(main())

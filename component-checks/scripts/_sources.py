"""Source-file helpers shared by the design/implementation checks."""

from __future__ import annotations

import re
from pathlib import Path
from typing import List

TEST_DIR_NAMES = {"test", "tests", "ut", "test-ut", "googletest"}

_INCLUDE_RE = re.compile(r'^\s*#\s*include\s+["<]([^">]+)[">]', re.MULTILINE)


def is_test_path(path: Path) -> bool:
    return any(part.lower() in TEST_DIR_NAMES for part in path.parts)


def impl_sources(module_dir: Path) -> List[Path]:
    """Non-test C++ sources/headers of a module."""
    out = []
    for pattern in ("*.cpp", "*.cc", "*.cxx", "*.hpp", "*.h"):
        for path in module_dir.rglob(pattern):
            if not is_test_path(path.relative_to(module_dir)):
                out.append(path)
    return sorted(out)


def test_sources(module_dir: Path) -> List[Path]:
    """Unit-test C++ sources/headers of a module."""
    out = []
    for pattern in ("*.cpp", "*.cc", "*.cxx", "*.hpp", "*.h"):
        for path in module_dir.rglob(pattern):
            if is_test_path(path.relative_to(module_dir)):
                out.append(path)
    return sorted(out)


def read_all(paths: List[Path]) -> str:
    chunks = []
    for path in paths:
        try:
            chunks.append(path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
    return "\n".join(chunks)


def includes_of(paths: List[Path]) -> List[str]:
    """All #include targets used by the given sources, deduplicated."""
    seen = []
    for target in _INCLUDE_RE.findall(read_all(paths)):
        if target not in seen:
            seen.append(target)
    return seen

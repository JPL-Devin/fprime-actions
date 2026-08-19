"""Locate a module's component classes and map them to Doxygen page names.

Scans the module's headers for classes deriving from an autocoded
``*ComponentBase`` and returns their namespace-qualified names.  Doxygen
page names follow doxygen's standard mangling (uppercase -> ``_<lower>``,
``_`` -> ``__``, ``::`` -> ``_1_1``), e.g. ``Svc::CommandDispatcherImpl``
-> ``class_svc_1_1_command_dispatcher_impl.html``.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List

_LINE_COMMENT_RE = re.compile(r"//[^\n]*")
_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)
_CLASS_RE = re.compile(
    r"\bclass\s+([A-Za-z_]\w*)(?:\s+final)?\s*:\s*public\s+(?:[\w:]+::)?\w*ComponentBase\b"
)
_TOKEN_RE = re.compile(r"namespace\s+([A-Za-z_][\w:]*)\s*\{|\{|\}")

_EXCLUDED_PARTS = ("test", "tests", "ut")


def _component_classes_in_text(text: str) -> List[str]:
    """Qualified names of ComponentBase-derived classes declared in ``text``."""
    text = _BLOCK_COMMENT_RE.sub("", _LINE_COMMENT_RE.sub("", text))
    classes = [(m.start(), m.group(1)) for m in _CLASS_RE.finditer(text)]
    if not classes:
        return []
    results: List[str] = []
    stack: List[str] = []  # "" for non-namespace braces
    class_iter = iter(classes)
    pos, name = next(class_iter)
    for token in _TOKEN_RE.finditer(text):
        while pos < token.start():
            namespaces = [frame for frame in stack if frame]
            results.append("::".join(namespaces + [name]))
            nxt = next(class_iter, None)
            if nxt is None:
                return results
            pos, name = nxt
        if token.group(1) is not None:
            stack.append(token.group(1))
        elif token.group(0) == "{":
            stack.append("")
        elif stack:
            stack.pop()
    namespaces = [frame for frame in stack if frame]
    results.append("::".join(namespaces + [name]))
    for pos, name in class_iter:
        results.append(name)
    return results


def find_component_classes(module_dir: Path) -> List[str]:
    """Qualified component-class names declared in ``module_dir`` headers."""
    results: List[str] = []
    files = sorted(
        p
        for pattern in ("*.hpp", "*.h")
        for p in module_dir.rglob(pattern)
        if not any(
            part.lower() in _EXCLUDED_PARTS or part.startswith("build-fprime")
            for part in p.relative_to(module_dir).parts
        )
    )
    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for qualified in _component_classes_in_text(text):
            if qualified not in results:
                results.append(qualified)
    return results


def _mangle(part: str) -> str:
    out = []
    for ch in part:
        if ch.isupper():
            out.append("_" + ch.lower())
        elif ch == "_":
            out.append("__")
        else:
            out.append(ch)
    return "".join(out)


def doxygen_class_page(qualified: str) -> str:
    """Doxygen HTML page name for a ``Ns::Class`` qualified name."""
    return "class" + "_1_1".join(_mangle(p) for p in qualified.split("::")) + ".html"

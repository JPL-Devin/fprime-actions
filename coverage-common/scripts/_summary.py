"""Shared helpers for reading gcovr ``--json-summary`` output.

``gcovr --json-summary`` emits a JSON document with totals at the root and a
``files`` array.  We only care about the totals for per-module reporting.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class Totals:
    """A pair of (covered, total) counts plus the derived percentage.

    ``total == 0`` is allowed and produces ``percent == 0.0`` (gcovr's own
    behaviour for modules with no executable lines).
    """

    covered: int
    total: int

    @property
    def percent(self) -> float:
        if self.total <= 0:
            return 0.0
        return round(100.0 * self.covered / self.total, 2)


@dataclass(frozen=True)
class Summary:
    """A coverage summary for one module (or the global ``--all`` run)."""

    line: Totals
    function: Totals
    branch: Totals

    @classmethod
    def from_gcovr_json(cls, doc: dict) -> "Summary":
        """Build from a gcovr ``--json-summary`` document.

        Accepts both modern (``line_total``/``line_covered``) and older
        (``line_percent`` only) gcovr documents; missing counts are treated
        as zero.
        """
        line = Totals(
            covered=int(doc.get("line_covered", 0) or 0),
            total=int(doc.get("line_total", 0) or 0),
        )
        function = Totals(
            covered=int(doc.get("function_covered", 0) or 0),
            total=int(doc.get("function_total", 0) or 0),
        )
        branch = Totals(
            covered=int(doc.get("branch_covered", 0) or 0),
            total=int(doc.get("branch_total", 0) or 0),
        )
        return cls(line=line, function=function, branch=branch)

    def to_catalog_entry(self) -> dict:
        return {
            "line_pct": self.line.percent,
            "line_covered": self.line.covered,
            "line_total": self.line.total,
            "function_pct": self.function.percent,
            "function_covered": self.function.covered,
            "function_total": self.function.total,
            "branch_pct": self.branch.percent,
            "branch_covered": self.branch.covered,
            "branch_total": self.branch.total,
        }


def load_summary(path: Path) -> Optional[Summary]:
    """Load a gcovr ``--json-summary`` file, returning ``None`` on failure.

    Missing files and parse errors both return ``None`` so callers can treat
    "no coverage data" uniformly.
    """
    if not path.is_file():
        return None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return Summary.from_gcovr_json(doc)

"""Repository checklist configuration (``.github/module-checklist.yml``).

Publishers read tier thresholds (and future settings) from a config file in
the repository being published rather than from action inputs, so projects
can version their reporting policy alongside their code.

Schema (all keys optional; defaults apply when the file or key is absent)::

    coverage:
      tiers:            # line-coverage percent cut-offs
        platinum: 95
        gold: 90
        silver: 80

    docs:
      base_url: https://fprime.jpl.nasa.gov   # rendered docs site; "" disables links

The file is parsed as YAML when PyYAML is available (it is preinstalled on
GitHub-hosted runners), with a JSON fallback so a ``.json`` config also
works in bare environments.  Unknown keys are ignored so future settings
(e.g. CodeQL severity mappings, int-coverage thresholds) can be added
without breaking older action versions.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from _tiers import CoverageThresholds

DEFAULT_CONFIG_PATH = ".github/module-checklist.yml"
DEFAULT_DOCS_BASE_URL = "https://fprime.jpl.nasa.gov"


def _parse(text: str) -> dict:
    try:
        import yaml  # type: ignore

        doc = yaml.safe_load(text)
    except ImportError:
        doc = json.loads(text)
    return doc if isinstance(doc, dict) else {}


def load_config(path: Optional[Path]) -> dict:
    """Load the checklist config, returning {} when missing or unreadable."""
    if path is None or not path.is_file():
        return {}
    try:
        return _parse(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 -- any parse failure means defaults
        print(f"config: failed to parse {path}: {exc}; using defaults", file=sys.stderr)
        return {}


def coverage_thresholds(config: dict) -> CoverageThresholds:
    tiers = ((config.get("coverage") or {}).get("tiers")) or {}
    defaults = CoverageThresholds()

    def _num(key: str, fallback: float) -> float:
        value = tiers.get(key, fallback)
        try:
            return float(value)
        except (TypeError, ValueError):
            print(f"config: coverage.tiers.{key} is not a number; using {fallback}", file=sys.stderr)
            return fallback

    return CoverageThresholds(
        platinum=_num("platinum", defaults.platinum),
        gold=_num("gold", defaults.gold),
        silver=_num("silver", defaults.silver),
    )


@dataclass(frozen=True)
class DocsSite:
    """Rendered documentation site (mkdocs + doxygen) URL builder."""

    base_url: str = DEFAULT_DOCS_BASE_URL

    def __bool__(self) -> bool:
        return bool(self.base_url)

    def sdd_url(self, ref: str, module_path: str) -> str:
        """Rendered SDD page for a module, e.g. <base>/devel/Svc/CmdDispatcher/docs/sdd/."""
        return f"{self.base_url}/{ref}/{module_path}/docs/sdd/"

    def doxygen_url(self, ref: str, page: str) -> str:
        """Doxygen API page, e.g. <base>/devel/docs/reference/api/cpp/html/<page>."""
        return f"{self.base_url}/{ref}/docs/reference/api/cpp/html/{page}"


def docs_site(config: dict) -> DocsSite:
    """Read the ``docs:`` section; an empty ``base_url`` disables site links."""
    section = config.get("docs") or {}
    base = section.get("base_url", DEFAULT_DOCS_BASE_URL)
    return DocsSite(base_url=str(base).rstrip("/") if base else "")

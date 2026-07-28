"""Fetch dismissed code-scanning alerts from the GitHub API.

SARIF files are point-in-time analysis artifacts and know nothing about
alerts dismissed in the GitHub UI; those dismissals live only in GitHub's
code-scanning alert database.  This script pulls the dismissed alerts once
per publish (a paginated list call, not per-finding) and writes a compact
JSON file that ``codeql_findings.py`` subtracts from the SARIF results.

Requires a token with ``security-events: read`` in ``GITHUB_TOKEN``.  Any
API failure degrades gracefully: a warning is printed, an empty list is
written, and the publish proceeds with unfiltered SARIF findings.

Output format (one entry per dismissed alert)::

    [{"rule": "cpp/xyz", "path": "Fw/Foo/Bar.cpp", "line": 42,
      "reason": "won't fix", "comment": "false positive in autocode"}]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import List


def extract(alerts: list) -> List[dict]:
    """Reduce raw API alert objects to the fields used for matching."""
    out = []
    for alert in alerts:
        if not isinstance(alert, dict):
            continue
        rule = (alert.get("rule") or {}).get("id") or ""
        instance = alert.get("most_recent_instance") or {}
        location = instance.get("location") or {}
        path = (location.get("path") or "").lstrip("/")
        if not rule or not path:
            continue
        out.append(
            {
                "rule": rule,
                "path": path,
                "line": int(location.get("start_line") or 0),
                "reason": alert.get("dismissed_reason") or "",
                "comment": alert.get("dismissed_comment") or "",
            }
        )
    return out


def fetch(repo: str, api_url: str, token: str) -> List[dict]:
    alerts: list = []
    page = 1
    while True:
        url = (
            f"{api_url.rstrip('/')}/repos/{repo}/code-scanning/alerts"
            f"?state=dismissed&per_page=100&page={page}"
        )
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            batch = json.loads(resp.read().decode("utf-8"))
        if not isinstance(batch, list) or not batch:
            break
        alerts.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return extract(alerts)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, help="owner/name")
    parser.add_argument("--api-url", default=os.environ.get("GITHUB_API_URL", "https://api.github.com"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    token = os.environ.get("GITHUB_TOKEN", "")
    dismissed: List[dict] = []
    if not token:
        print("fetch_dismissed_alerts: GITHUB_TOKEN not set; skipping", file=sys.stderr)
    else:
        try:
            dismissed = fetch(args.repo, args.api_url, token)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            print(
                f"fetch_dismissed_alerts: API fetch failed ({exc}); "
                "proceeding with unfiltered SARIF findings",
                file=sys.stderr,
            )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(dismissed, indent=2) + "\n", encoding="utf-8")
    print(f"fetch_dismissed_alerts: {len(dismissed)} dismissed alert(s)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

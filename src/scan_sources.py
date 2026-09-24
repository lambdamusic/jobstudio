"""Which ATS a tracked company sits on — and, when the answer is "none", why.

This is the one question the scanner acts on for every company, and the companies list
in the web app wants exactly the same answer ("is this being rescanned automatically?").
It lived in `scan-portals.py` until 2026-09-23, where nothing else could reach it: the
hyphen in that filename means it cannot be imported. Re-deriving it in the web app would
have meant two copies of the ATS patterns and two copies of the "not scanned" reasons,
free to drift apart — and a coverage column that lies is worse than no column.

It is not in `scan_config.py` because that module is explicitly the settings belonging to
*one person's job search*; URL shapes for Greenhouse and Lever are toolkit knowledge,
true for everyone.

Pure and offline — the config file plus a regex over the tracked URL, no network — so
`coverage()` is safe to call once per row while rendering a page.
"""

from __future__ import annotations

import re

import scan_config

# Platforms whose public careers URL names the board outright. Everything else — Workday,
# Ashby, SmartRecruiters, Teamtailor, Rippling — hides its tenant behind a corporate page
# and has to be recorded by hand in `company_overrides`, which is why detection alone
# leaves real coverage gaps.
_ATS_PATTERNS = [
    ("greenhouse", re.compile(r"(?:job-boards|boards)(?:\.\w+)?\.greenhouse\.io/([^/?#]+)")),
    ("lever", re.compile(r"jobs\.lever\.co/([^/?#]+)")),
    ("workable", re.compile(r"apply\.workable\.com/([^/?#]+)")),
    # Tenant is the subdomain, so anchor to the scheme separator and exclude
    # BambooHR's own hosts — a company linking to www.bamboohr.com is not a board
    # called "www". Without the `//` the lookahead is useless: `search` just steps
    # one character right and matches "ww".
    ("bamboohr", re.compile(r"//(?!www\.|help\.)([a-z0-9][a-z0-9-]*)\.bamboohr\.com")),
]

BESPOKE = "bespoke career page — no public jobs API"
NO_URL = "no URL on record"


def resolve_source(company_name: str, url: str | None) -> dict | None:
    """Return {"platform": ..., ...params} for a company, preferring a known override
    (generic corporate careers page hiding a real ATS) over URL-pattern detection."""
    overrides = scan_config.company_overrides()
    if company_name in overrides:
        return overrides[company_name]
    if url:
        for platform, pattern in _ATS_PATTERNS:
            m = pattern.search(url)
            if m:
                return {"platform": platform, "token": m.group(1)}
    return None


def coverage(company_name: str, url: str | None) -> dict:
    """Whether `scan` will pick this company up, and on what — or the specific reason it
    won't. Shape: {"scanned": bool, "platform": str, "reason": str, "source": dict|None}.

    The reasons are graded on purpose, because they mean different things to whoever
    reads them: "no URL on record" is a gap in the tracker anyone can close in a minute;
    a `known_unsupported` entry is a platform confirmed by hand with no fetcher written;
    the bespoke fallback means nobody has found an API yet. Collapsing them into one
    "not scanned" would hide the only actionable one.
    """
    if not url and company_name not in scan_config.company_overrides():
        return {"scanned": False, "platform": "", "reason": NO_URL, "source": None}

    source = resolve_source(company_name, url)
    if source is None:
        reason = scan_config.known_unsupported().get(company_name, BESPOKE)
        return {"scanned": False, "platform": "", "reason": reason, "source": None}

    return {"scanned": True, "platform": source["platform"], "reason": "", "source": source}

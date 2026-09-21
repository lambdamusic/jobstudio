"""Scan settings that belong to a job search, not to the toolkit.

Four things the scanner needs are facts about *one person's* search rather than about
how scanning works: which company categories map to which CV target area, which
companies sit on an ATS their public careers URL doesn't reveal, and which are on a
platform with no fetcher yet. They lived as module constants in `scan-portals.py` until
2026-09-21, which meant the toolkit could not be published without publishing the
author's target list along with it.

They now live in `<DATA>/jobs/scan-config.yaml`, next to `jobs/targets/*.yaml`, which is
already where "what am I looking for" is configured. The file is optional: without it
the scanner still runs, detecting each company's ATS from its careers URL alone. What is
lost is only the hand-researched part — the overrides found by inspecting redirects and
embedded widgets, which no amount of URL pattern-matching can infer.

Shape:

    default_area: data-platform            # when a category has no mapping
    category_to_area:
      "Knowledge Graphs & Semantic Platforms": knowledge-graph
    company_overrides:
      "Example Corp": {platform: greenhouse, token: examplecorp}
    known_unsupported:
      "Other Corp": "BambooHR — not yet integrated"
"""

from __future__ import annotations

from pathlib import Path

import yaml

import config

CONFIG_NAME = "scan-config.yaml"


def path() -> Path:
    return config.data_root() / "jobs" / CONFIG_NAME


_cache: dict | None = None


def _load() -> dict:
    """Parse the file once per process. A missing file is normal, not an error."""
    global _cache
    if _cache is not None:
        return _cache
    p = path()
    if not p.is_file():
        _cache = {}
        return _cache
    loaded = yaml.safe_load(p.read_text()) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"{p}: expected a mapping at the top level, got {type(loaded).__name__}")
    _cache = loaded
    return _cache


def _mapping(key: str) -> dict:
    """One top-level key, guaranteed to be a dict so callers can `.get()` unguarded."""
    value = _load().get(key) or {}
    if not isinstance(value, dict):
        raise ValueError(f"{path()}: '{key}' must be a mapping, got {type(value).__name__}")
    return value


def category_to_area() -> dict[str, str]:
    """Company category → CV target area. Categories and areas are orthogonal: a
    category groups companies by domain, an area is a CV positioning, and several
    categories can share one area rather than each getting a bespoke one."""
    return _mapping("category_to_area")


def default_area() -> str:
    """Fallback for a category absent from `category_to_area` — a safety net for a
    category added to the tracker but not yet placed. Empty when unset, which the
    scanner treats as "no area filter applies"."""
    return str(_load().get("default_area") or "")


def company_overrides() -> dict[str, dict]:
    """Company name (as recorded in the tracker) → {"platform": ..., ...params}, for
    companies whose tracked careers URL is a generic corporate page with the real ATS
    hidden underneath. Keyed by name, not URL, because the URL is exactly what's wrong."""
    return _mapping("company_overrides")


def known_unsupported() -> dict[str, str]:
    """Company name → why it isn't scanned, for companies confirmed on a specific ATS
    with no fetcher built. Gives a precise reason in the report instead of the generic
    bespoke-page fallback."""
    return _mapping("known_unsupported")

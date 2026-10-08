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
      "Other Corp": "Webitrent — no public API found"
"""

from __future__ import annotations

from pathlib import Path

import yaml

import config

CONFIG_NAME = "scan-config.yaml"


def path() -> Path:
    return config.data_root() / "jobs" / CONFIG_NAME


def targets_dir() -> Path:
    """`<DATA>/jobs/targets/` — the target-area profiles this file's `category_to_area`
    and `default_area` point at.

    Lives here rather than being spelled out a third time: `scan_report.TARGETS_DIR`
    imports it, and the Django side has its own `settings.TARGETS_DIR` because it
    resolves the data root on a different lifecycle.
    """
    return config.data_root() / "jobs" / "targets"


def target_slugs() -> list[str]:
    """The area slugs that actually exist on disk — a YAML's filename is its slug."""
    return sorted(p.stem for p in targets_dir().glob("*.yaml"))


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


def company_areas() -> dict[str, list[str]]:
    """Company name → the target areas it plausibly hires into, in preference order.

    The usual route to an area is the company's category (`category_to_area`), which
    gives every company exactly one. That breaks for an organisation that genuinely
    hires into two of the user's positionings — a frontier lab with both a safety org
    and a data-product org — where a single category forces a choice that loses half the
    postings before scoring.

    Here rather than on the Company model deliberately: it is a fact about how *this*
    search wants a company scanned, not about the company, and it sits beside
    `company_overrides`, which is the same kind of hand-researched per-company
    exception. Promote it to a real field if it ever needs to show on a company page.

    `scan_match.pick_area` assigns each posting one of these by title overlap, so a
    posting still gets one area and one score.
    """
    raw = _mapping("company_areas")
    out: dict[str, list[str]] = {}
    for company, areas in raw.items():
        if isinstance(areas, str):        # a bare slug is an easy thing to write
            areas = [areas]
        if not isinstance(areas, list):
            raise ValueError(f"{path()}: company_areas['{company}'] must be a list of "
                             f"area slugs, got {type(areas).__name__}")
        out[company] = [str(a) for a in areas]
    return out


def soft_negatives() -> list[str]:
    """Things that should push a role down without disqualifying it — the mirror of
    `bonus_signals`.

    `hard_filters.exclude` already only affects the score (the rubric pulls `ideal_score`
    to 1–2 rather than dropping the posting), but that is a dealbreaker's weight. Some
    traits are real reservations rather than dealbreakers — "heavily political large
    organisations" being the case this was added for: worth knowing about a role, never
    worth hiding it.
    """
    raw = _load().get("soft_negatives") or []
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        raise ValueError(f"{path()}: 'soft_negatives' must be a list, got {type(raw).__name__}")
    return [str(x) for x in raw]


def company_overrides() -> dict[str, dict]:
    """Company name (as recorded in the tracker) → {"platform": ..., ...params}, for
    companies whose tracked careers URL is a generic corporate page with the real ATS
    hidden underneath. Keyed by name, not URL, because the URL is exactly what's wrong."""
    return _mapping("company_overrides")


def criteria_path() -> Path:
    """`jobs/profile/criteria.yaml` — the machine-readable half of the stocktake."""
    return config.data_root() / "jobs" / "profile" / "criteria.yaml"


def ideal_score_inputs() -> dict:
    """What the Ideal-Job Score has to score against, and whether there is any of it.

    The Area Score compares a posting to a target-area profile; the Ideal-Job Score
    compares it to what the person actually wants, which lives in `criteria.yaml` —
    `weighted_motivators`, `hard_filters.exclude`, and the salary floor. On a fresh data
    root that file is a draft with none of them, and the consequence is `#62`: every
    Ideal-Job Score comes back low, not because the roles are poor fits but because there
    is nothing to compare them with. The number renders beside the Area Score in the same
    column shape, so it reads as a measurement.

    `ready` is False when a scan would produce that. Returns the counts too, so a report
    or a check can say which part is missing rather than only that something is.
    """
    path = criteria_path()
    out = {"exists": path.is_file(), "motivators": 0, "dealbreakers": 0,
           "has_salary_floor": False, "ready": False}
    if not out["exists"]:
        return out
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError:
        return out
    if not isinstance(data, dict):
        return out
    out["motivators"] = len(data.get("weighted_motivators") or [])
    hard = data.get("hard_filters") or {}
    out["dealbreakers"] = len(hard.get("exclude") or []) if isinstance(hard, dict) else 0
    out["has_salary_floor"] = bool(isinstance(hard, dict) and hard.get("salary_min"))
    # Motivators are what the score is mostly built from, so they are the one that
    # decides this. Dealbreakers alone can only push a score down, never establish that
    # a role is wanted.
    out["ready"] = out["motivators"] > 0
    return out


def known_unsupported() -> dict[str, str]:
    """Company name → why it isn't scanned, for companies confirmed on a specific ATS
    with no fetcher built. Gives a precise reason in the report instead of the generic
    bespoke-page fallback."""
    return _mapping("known_unsupported")


# ---------------------------------------------------------------------------
# Does this configuration actually resolve? (`#39`)
# ---------------------------------------------------------------------------

# The fields a target-area YAML has to carry for scoring to mean anything. `emphasis`
# and the two section lists are optional — a CV positioning can legitimately have
# nothing to expand or condense — but an area with no description and no key terms
# gives the rubric nothing to score against and the pre-filter nothing to match on.
# `excludes` is optional too, and likewise only checked for shape: an area with no
# anti-fit list is scored on its positive signals alone, which is the old behaviour.
REQUIRED_TARGET_KEYS = ("name", "description", "key_terms")
LIST_TARGET_KEYS = ("emphasis", "key_terms", "expand_sections", "condense_sections",
                    "excludes")

ERROR, WARN, OK = "error", "warn", "ok"


def check(*, targets: Path | None = None, tracked_categories: list[str] | None = None,
          tracked_companies: list[str] | None = None) -> list[tuple[str, str]]:
    """Whether every company the scanner will meet resolves to a real target area.

    This whole chain fails *quietly*. `scan-portals.py` does
    `profiles.get(area, {})`, so an area that names no file yields an empty profile:
    the keyword pre-filter silently falls back to the company's role target alone, and
    the scorer gets no `description`, `emphasis` or `key_terms` to score against — it
    still emits an Area Score, and that number means nothing. Nothing in the report
    says so. On a fresh data root (`#39`) `jobs/targets/` is empty and *every* row is
    like this, which is the worst version: a scan that looks like it worked.

    Returns `(level, message)` pairs rather than printing, so the web app or a test can
    use the same answer. `tracked_categories` is passed in rather than read here to
    keep this free of Django — the caller has it cheaply, this module should not.
    """
    targets = targets if targets is not None else targets_dir()
    results: list[tuple[str, str]] = []

    slugs = sorted(p.stem for p in targets.glob("*.yaml"))
    if not slugs:
        results.append((ERROR, f"No target areas in {targets} — nothing can be scored. "
                               "See init.md §'Define the target areas'."))
    else:
        results.append((OK, f"{len(slugs)} target area(s): {', '.join(slugs)}"))

    for slug in slugs:
        results.extend(_check_one_target(targets / f"{slug}.yaml"))

    fallback = default_area()
    if fallback and fallback not in slugs:
        results.append((ERROR, f"default_area: '{fallback}' has no {fallback}.yaml — every "
                               "unmapped category scores against nothing."))

    mapping = category_to_area()
    for category, area in sorted(mapping.items()):
        if area not in slugs:
            results.append((ERROR, f"category_to_area: '{category}' → '{area}', which has "
                                   f"no {area}.yaml."))

    for company, areas in sorted(company_areas().items()):
        missing = [a for a in areas if a not in slugs]
        if missing:
            results.append((ERROR, f"company_areas: '{company}' → {', '.join(missing)}, "
                                   "which have no target YAML."))
        elif len(areas) < 2:
            # Harmless, but it buys nothing and reads as if it does — one area is exactly
            # what the category would have given.
            results.append((WARN, f"company_areas: '{company}' lists a single area; the "
                                  "category mapping already does that."))
        if tracked_companies is not None and company not in tracked_companies:
            # Keyed by name, so a rename or a typo makes the entry do nothing at all —
            # and the company quietly reverts to its category's single area.
            results.append((WARN, f"company_areas names '{company}', which is not a "
                                  "tracked company — a rename, or a typo."))

    if tracked_categories is not None:
        for category in sorted(set(tracked_categories) - set(mapping)):
            level = OK if fallback in slugs else ERROR
            results.append((level, f"category '{category}' has no mapping — falls back to "
                                   + (f"default_area '{fallback}'." if fallback else
                                      "no area at all.")))
        # A mapping key that matches no tracked category does nothing at all. Usually a
        # renamed category, and silent either way — the scan just uses the fallback.
        for category in sorted(set(mapping) - set(tracked_categories)):
            results.append((WARN, f"category_to_area names '{category}', which is not a "
                                  "tracked category — a rename, or a typo."))

    # The other half of a scan that looks like it worked (`#62`). Everything above is
    # about the Area Score having something to compare against; this is the same question
    # for the Ideal-Job Score, and it fails the same way — a number with nothing behind it
    # rather than an absence.
    inputs = ideal_score_inputs()
    if not inputs["exists"]:
        results.append((WARN, "no jobs/profile/criteria.yaml — the Ideal-Job Score has "
                              "nothing to score against. Run `/jobstudio stocktake`."))
    elif not inputs["ready"]:
        results.append((WARN, "criteria.yaml has no weighted_motivators — every Ideal-Job "
                              "Score will come back low whatever the role, and the report "
                              "says so. Run `/jobstudio stocktake` to fill it in."))
    else:
        missing = []
        if not inputs["dealbreakers"]:
            missing.append("no hard_filters.exclude")
        if not inputs["has_salary_floor"]:
            missing.append("no salary floor")
        detail = f" ({', '.join(missing)})" if missing else ""
        results.append((OK, f"Ideal-Job Score has {inputs['motivators']} weighted "
                            f"motivator(s) to score against{detail}."))

    return results


def _check_one_target(path: Path) -> list[tuple[str, str]]:
    try:
        data = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        return [(ERROR, f"{path.name}: not valid YAML — {exc}")]
    if not isinstance(data, dict):
        return [(ERROR, f"{path.name}: expected a mapping at the top level.")]

    out: list[tuple[str, str]] = []
    for key in REQUIRED_TARGET_KEYS:
        if not data.get(key):
            out.append((ERROR, f"{path.name}: '{key}' is missing or empty."))
    for key in LIST_TARGET_KEYS:
        value = data.get(key)
        if value is None:
            continue
        if not isinstance(value, list):
            out.append((ERROR, f"{path.name}: '{key}' must be a list."))
            continue
        for item in value:
            if not isinstance(item, str):
                # The unquoted-colon trap: `- SciGraph: a knowledge graph` is a mapping,
                # not a string. parsers._flatten_yaml_list patches it up for the web
                # app's display; nothing patches it up for the scorer.
                out.append((ERROR, f"{path.name}: '{key}' entry {item!r} is not a string "
                                   "— quote any entry containing ': '."))
    return out


def _main(argv: list[str] | None = None) -> int:
    """`tools/py src/scan_config.py --check` — would a scan resolve every company to a
    real target area? Exits 1 if not, so it can gate a first scan."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Check that scan-config.yaml and jobs/targets/ line up.")
    parser.add_argument("--check", action="store_true",
                        help="Report problems and exit 1 if any are errors (the default)")
    parser.parse_args(argv)

    try:
        import jobsdb
        categories = [c["name"] for c in jobsdb.categories()]
        companies = [c["name"] for c in jobsdb.companies()]
    except Exception as exc:  # no database yet is a normal state during init
        print(f"  (tracker unavailable, checking config alone — {exc})")
        categories = companies = None

    results = check(tracked_categories=categories, tracked_companies=companies)
    for level, message in results:
        print(f"  {'ERROR' if level == ERROR else level:<5} {message}")

    errors = sum(1 for level, _ in results if level == ERROR)
    print(f"\n{'FAIL' if errors else 'OK'} — {errors} error(s), "
          f"{sum(1 for level, _ in results if level == WARN)} warning(s).")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(_main())

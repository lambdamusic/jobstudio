"""Which postings are worth scoring, and which target area each one belongs to.

Extracted from `scan-portals.py` on 2026-09-27 for the same reason `scan_sources.py` was
on 2026-09-23: the hyphen in that filename means nothing can import it, so anything
living there cannot be tested and cannot be reused. The keyword pre-filter decides what
reaches the scorer at all, and `pick_area` decides which rubric it is judged against —
both are judgement, both are cheap to get subtly wrong, and neither had a test.

Pure and offline: strings and sets, no network, no config lookups. The caller passes the
area profiles in.
"""

from __future__ import annotations

import re


def words(text: str) -> set[str]:
    """Words of four letters or more, lowercased.

    The four-letter floor is doing real work: it drops "ai", "of", "and" and the like, so
    a key term such as "AI control" contributes {"control"} rather than matching every
    posting with "AI" in the title.
    """
    return {w.lower() for w in re.findall(r"[A-Za-z]{4,}", text)}


def is_plausible_match(title: str, role_target: str, key_terms: list[str]) -> bool:
    """Does the posting title share any word with the company's role target or the
    area's key terms? Crude on purpose — it runs before any scoring, so a false positive
    costs one scored candidate and a false negative loses a job silently."""
    reference = words(role_target) | {w for term in key_terms or [] for w in words(term)}
    return bool(words(title) & reference)


def pick_area(title: str, role_target: str, areas: list[str], profiles: dict) -> str | None:
    """Which of a company's candidate areas this posting belongs to — `None` to drop it.

    A company can plausibly hire into more than one of the user's positionings: a
    frontier lab with both a safety org and a data-product org is the case this exists
    for (`company_areas` in scan-config.yaml). The **company** declares which areas are
    possible; the **posting** picks one, by how many of its title words each area's
    `key_terms` account for.

    One posting still gets one area and one score. Scoring a posting once per candidate
    area would double the bill to produce two numbers for one job, and leave the report
    listing it twice — the question "is this role a fit" has one answer.

    Ties, and a title that matches only the company's `role_target`, fall to the first
    area listed, so the order in `company_areas` expresses preference.

    For a company with one area this is exactly `is_plausible_match` — same word sets,
    same outcome — so single-area behaviour is unchanged by multi-area support.
    """
    title_words = words(title)
    best, best_overlap = None, 0
    for area in areas:
        key_terms = profiles.get(area, {}).get("key_terms") or []
        overlap = len(title_words & {w for term in key_terms for w in words(term)})
        if overlap > best_overlap:
            best, best_overlap = area, overlap
    if best is not None:
        return best
    # No area's key terms matched. The role target is the company-level fallback the
    # single-area path has always accepted, so honour it and hand the posting to the
    # preferred area rather than dropping a job the user's own role target describes.
    return areas[0] if areas and (title_words & words(role_target)) else None

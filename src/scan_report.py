#!/usr/bin/env python3
"""
scan_report.py

Shared, API-free report rendering for the portal scan — used by both scoring paths:

- The default, agent-native path: the `scan` skill subcommand scores candidates itself
  (reading `scan_score_rubric.md` as its rubric) and writes a scored candidates file,
  then runs this module to render the final report.
- The opt-in API path (`score-candidates.py`): scores via the Anthropic API, then calls
  `render()` directly (same code, no subprocess round-trip needed there).

Never imports `anthropic` — nothing here does any judgement, only formatting of
already-scored candidates plus the mechanical bookkeeping sections `scan-portals.py`
computed (not-scanned, no-roles, filtered-out, coverage notes).

CLI usage (for the agent-native path, after it has written a scored file):
    python src/scan_report.py --scored jobs/scans/YYYY-MM-DD-scored.json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml

import config
import scan_config

DATA_ROOT = config.data_root()
SCANS_DIR = DATA_ROOT / "jobs" / "scans"
TARGETS_DIR = scan_config.targets_dir()
# Code, not data — manage.py ships with the repo.
REPO_ROOT = config.REPO_ROOT


def load_area_profiles() -> dict[str, dict]:
    """Shared by scan-portals.py (needs `key_terms` for the pre-filter) and
    score-candidates.py (needs the full profile to build its scoring prompt)."""
    profiles = {}
    for path in TARGETS_DIR.glob("*.yaml"):
        profiles[path.stem] = yaml.safe_load(path.read_text())
    return profiles

# Area Score (cv_score) + Ideal-Job Score, combined — the bar for a "Strong match".
STRONG_THRESHOLD = 7


@dataclass
class Candidate:
    company: str
    title: str
    url: str
    role_target: str
    area: str
    category: str = ""  # the company's tracked category — orthogonal to area
    location: str = "unknown"
    cv_score: int | None = None  # "Area Score" in the report — CV/target-area fit
    ideal_score: int | None = None
    location_category: str = "other"  # "uk" | "remote" | "other"
    notes: str = ""
    # Set only for a posting found by searching a job board rather than by rescanning a
    # tracked company (`#8`, src/job_boards.py): which board, whether the advertiser
    # looks like a recruitment agency, and the board's own description snippet and
    # salary — the scorer's only context, since such a posting has no role target.
    source: str = ""
    agency: bool = False
    snippet: str = ""
    salary: str = ""

    @property
    def combined_score(self) -> int:
        return (self.cv_score or 0) + (self.ideal_score or 0)

    @classmethod
    def from_dict(cls, d: dict) -> "Candidate":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


def classify(candidates: list[Candidate]) -> tuple[list[Candidate], list[Candidate], list[Candidate]]:
    """Split scored candidates into (matches, discarded_by_location, needs_review) —
    same logic scan-portals.py used to apply inline right after scoring."""
    matches: list[Candidate] = []
    discarded_by_location: list[Candidate] = []
    needs_review: list[Candidate] = []
    for c in candidates:
        if c.cv_score is None:
            needs_review.append(c)
        elif c.location_category in ("uk", "remote"):
            matches.append(c)
        else:
            discarded_by_location.append(c)
    return matches, discarded_by_location, needs_review


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def _cell(text: str) -> str:
    """Escape pipe characters so free-text (e.g. scorer notes) can't break a markdown table row."""
    return text.replace("|", "/")


def _company_link(name: str, url: str | None) -> str:
    """Link the company name to its tracked careers URL, for manual follow-up."""
    return f"[{name}]({url})" if url else name


def _match_table(candidates: list[Candidate]) -> list[str]:
    """Flat markdown table, one row per candidate, Company/Category/Area as columns —
    used only for the rare/small "Strong matches — wrong location" bucket, where
    grouping by company would be overkill. See _match_table_by_company for the main
    Strong/Other tables."""
    lines = [
        "| Role | Category | Area | Location | Area Score | Ideal-Job Score | Notes |",
        "|---|---|---|---|---|---|---|",
    ]
    for c in candidates:
        loc_label = _cell(f"{c.location} ({c.location_category})")
        role_cell = f"**{_cell(c.company)}** — [{_cell(c.title)}]({c.url})"
        lines.append(f"| {role_cell} | {_cell(c.category)} | {c.area} | {loc_label} | "
                      f"{c.cv_score}/5 | {c.ideal_score}/5 | {_cell(c.notes)} |")
    lines.append("")
    return lines


def _match_table_by_company(candidates: list[Candidate]) -> list[str]:
    """Company-grouped (alphabetical), sorted by combined score within each company.

    Category and Area are normally company-level, so they go once in the heading rather
    than on every row (unlike the flat `_match_table`). A company listed in
    `company_areas` breaks that: its postings are assigned an area each, so the heading
    cannot state one. Those companies get an Area column instead — and only those, so
    the output for every single-area company is unchanged.
    """
    lines: list[str] = []
    by_company: dict[str, list[Candidate]] = {}
    for c in candidates:
        by_company.setdefault(c.company, []).append(c)
    for company in sorted(by_company, key=str.casefold):
        cands = sorted(by_company[company], key=lambda c: c.combined_score, reverse=True)
        first = cands[0]
        multi_area = len({c.area for c in cands}) > 1
        lines.append(f"### {company}")
        lines.append("")
        lines.append(f"*{first.category} → {'scored per role' if multi_area else first.area}*")
        lines.append("")
        if multi_area:
            lines.append("| Role | Area | Location | Area Score | Ideal-Job Score | Notes |")
            lines.append("|---|---|---|---|---|---|")
        else:
            lines.append("| Role | Location | Area Score | Ideal-Job Score | Notes |")
            lines.append("|---|---|---|---|---|")
        for c in cands:
            loc_label = _cell(f"{c.location} ({c.location_category})")
            area_cell = f" {_cell(c.area)} |" if multi_area else ""
            lines.append(f"| [{_cell(c.title)}]({c.url}) |{area_cell} {loc_label} | "
                          f"{c.cv_score}/5 | {c.ideal_score}/5 | {_cell(c.notes)} |")
        lines.append("")
    return lines


def _discovered_table(candidates: list[Candidate]) -> list[str]:
    """Flat, by combined score — the company is the thing being discovered, so it goes
    on every row rather than in a heading."""
    lines = [
        "| Role | Area | Location | Salary | Area Score | Ideal-Job Score | Notes |",
        "|---|---|---|---|---|---|---|",
    ]
    for c in sorted(candidates, key=lambda c: c.combined_score, reverse=True):
        flags = " *(agency)*" if c.agency else ""
        role_cell = f"**{_cell(c.company or 'Unnamed')}**{flags} — [{_cell(c.title)}]({c.url})"
        lines.append(f"| {role_cell} | {c.area} | {_cell(c.location)} ({c.location_category}) | "
                     f"{_cell(c.salary) or '—'} | {c.cv_score}/5 | {c.ideal_score}/5 | "
                     f"{_cell(c.notes)} *({c.source})* |")
    lines.append("")
    return lines


def _company_job_list(entries: dict[str, dict]) -> list[str]:
    """Company-grouped (alphabetical), full per-posting list, for the two
    before-scoring exclusion buckets — so any of these can be manually followed up on
    posting by posting, not just seen as a count. `entries` maps company name to
    {"category": str, "jobs": [{"title", "url", "location"?}]} — "location" is
    present only for the location-exclusion bucket, where it's the actual reason."""
    lines: list[str] = []
    for company in sorted(entries, key=str.casefold):
        data = entries[company]
        jobs = data["jobs"]
        lines.append(f"### {company} ({len(jobs)})")
        lines.append("")
        if data.get("category"):
            lines.append(f"*{data['category']}*")
            lines.append("")
        for job in jobs:
            if job.get("location"):
                lines.append(f"- [{_cell(job['title'])}]({job['url']}) — {_cell(job['location'])}")
            else:
                lines.append(f"- [{_cell(job['title'])}]({job['url']})")
        lines.append("")
    return lines


def write_report(
    scanned_count: int,
    not_scanned: list[tuple[str, str, str | None]],
    matches: list[Candidate],
    discarded_by_location: list[Candidate],
    needs_review: list[Candidate],
    no_roles: list[tuple[str, str | None]],
    total_found: int,
    total_skipped_dedup: int,
    coverage_notes: list[tuple[str, int, int]],
    prefiltered: dict[str, dict],
    location_prefiltered: dict[str, dict],
    discovery: dict | None = None,
) -> Path:
    today = date.today().isoformat()

    # Job-board postings (`#8`) are scored like the rest but never ranked with them: a
    # tracked company was vetted by a person, a job-board hit was not. They get a section
    # of their own, and every count below the line stays about tracked companies only.
    discovered = [c for c in matches if c.source]
    matches = [c for c in matches if not c.source]
    discovered_wrong_location = sum(1 for c in discarded_by_location if c.source)
    discarded_by_location = [c for c in discarded_by_location if not c.source]
    lines = [f"# Portal Scan — {today}", ""]

    # `#62`. The Ideal-Job Score compares a posting to what the person wants, which lives
    # in `criteria.yaml`. With no `weighted_motivators` there is nothing to compare it
    # with, so every score comes back low — and it renders beside the Area Score in the
    # same column shape, which reads as a measurement rather than as an absence. Said here,
    # at the top, rather than left to whoever is driving the scan to notice and mention:
    # the second-person install pass (`#2` M1.8) only caught it because that session
    # happened to say so twice, unprompted.
    #
    # The ranking is affected too, not just the column, so the note has to say that. The
    # Strong-matches cut is on the COMBINED score, so a flat Ideal-Job Score makes the
    # threshold effectively "Area Score plus a constant" — the order is still useful, the
    # bar is not where it looks.
    ideal = scan_config.ideal_score_inputs()
    if not ideal["ready"]:
        missing = ("There is no `jobs/profile/criteria.yaml`"
                   if not ideal["exists"] else
                   "`jobs/profile/criteria.yaml` has no `weighted_motivators`")
        lines += [
            "> **The Ideal-Job Scores in this report are not yet meaningful.** "
            f"{missing}, so there is nothing for them to be scored against and they all "
            "come back low — that is the empty profile talking, not the roles. "
            "**Read the Area Score column and ignore the Ideal-Job one for now.**",
            ">",
            "> It also moves the bar: the Strong-matches cut is on the *combined* score, "
            "so with one half flat it is effectively Area Score plus a constant. The "
            "ordering within a bucket still holds; where the line falls does not.",
            ">",
            "> Run `/jobstudio stocktake` and scan again — it is the step that makes this "
            "column mean something, and it changes the ranking rather than just adding a "
            "number.",
            "",
        ]

    strong = sorted((c for c in matches if c.combined_score >= STRONG_THRESHOLD),
                     key=lambda c: c.combined_score, reverse=True)
    other_matches = sorted((c for c in matches if c.combined_score < STRONG_THRESHOLD),
                            key=lambda c: c.combined_score, reverse=True)
    strong_wrong_location = sorted(
        (c for c in discarded_by_location if c.combined_score >= STRONG_THRESHOLD),
        key=lambda c: c.combined_score, reverse=True)
    weak_discarded_count = len(discarded_by_location) - len(strong_wrong_location)

    lines += [
        "## Strong matches", "",
        f"Area Score + Ideal-Job Score ≥ {STRONG_THRESHOLD}. Grouped by company "
        "(alphabetical), sorted by combined score within each.", "",
    ]
    lines += _match_table_by_company(strong) if strong else ["_None this run._", ""]

    if strong_wrong_location:
        lines += [
            "### Strong matches — wrong location", "",
            "Same bar, but not UK-based or fully remote, so not eligible today — kept "
            "visible rather than silently discarded, since a role this strong is worth "
            "knowing existed. Flat, not grouped by company — this bucket is small by "
            "construction.", "",
        ]
        lines += _match_table(strong_wrong_location)

    lines += [
        "## Other matches", "",
        "Grouped by company (alphabetical), sorted by combined score within each.", "",
    ]
    lines += _match_table_by_company(other_matches) if other_matches else ["_None this run._", ""]

    if discovery is not None:
        lines += [
            "## Discovered on job boards", "",
            "Found by searching general job boards for your target areas, at companies "
            "the company scan does not cover — **not vetted**: nobody has decided these "
            "companies are worth watching. Kept apart from the matches above for that "
            "reason. *Agency* marks an advertiser that looks like a recruitment agency, "
            "where the employer is not named. Sorted by combined score.", "",
        ]
        lines += _discovered_table(discovered) if discovered else ["_None this run._", ""]

    lines += [
        "## Filtered out before scoring",
        "",
        "Postings that were fetched and passed dedup, but shared no keyword with the "
        "company's tracked role target (or key terms) — never sent to the scorer. "
        "Grouped by company (alphabetical) with the full list, so any of these can be "
        "manually checked and followed up on directly.",
        "",
    ]
    lines += _company_job_list(prefiltered) if prefiltered else ["_None._", ""]

    lines += [
        "## Excluded by location",
        "",
        "Postings that passed the keyword pre-filter but were never sent to the scorer "
        "because their location text has no UK or remote signal anywhere in it — a "
        "confident, mechanical read, not an LLM judgement (that's still what decides "
        "uk/remote/other for anything that *does* reach scoring). Deliberately "
        "conservative: vague or missing location text is never excluded here, only "
        "sent through as normal. Grouped by company (alphabetical) with the full list "
        "and each posting's raw location text, for manual follow-up.",
        "",
    ]
    lines += _company_job_list(location_prefiltered) if location_prefiltered else ["_None._", ""]

    lines += ["## Needs manual review (scoring failed)", ""]
    if needs_review:
        for c in needs_review:
            lines.append(f"- **{c.company}** — [{c.title}]({c.url}) — {c.location}")
        lines.append("")
    else:
        lines += ["_None._", ""]

    lines += ["## No open roles found", ""]
    if no_roles:
        for name, url in no_roles:
            lines.append(f"- {_company_link(name, url)}")
        lines.append("")
    else:
        lines += ["_None._", ""]

    lines += ["## Not scanned", ""]
    if not_scanned:
        for name, reason, url in not_scanned:
            lines.append(f"- **{_company_link(name, url)}** — {reason}")
        lines.append("")
    else:
        lines += ["_None._", ""]

    total_prefiltered = sum(len(d["jobs"]) for d in prefiltered.values())
    total_location_prefiltered = sum(len(d["jobs"]) for d in location_prefiltered.values())
    lines += [
        "## Coverage notes", "",
        "### Summary", "",
        f"- Companies scanned: {scanned_count}",
        f"- Companies not scanned: {len(not_scanned)}",
        f"- Roles found: {total_found}",
        f"- Already tracked (skipped): {total_skipped_dedup}",
        f"- Filtered out before scoring (no keyword overlap): {total_prefiltered}",
        f"- Excluded before scoring (no UK/remote location signal): {total_location_prefiltered}",
        f"- Scored matches: {len(matches)} ({len(strong)} strong, {len(other_matches)} other)",
        f"- Discarded (non-UK/non-remote), weak fit: {weak_discarded_count}",
        f"- Discarded (non-UK/non-remote), strong fit — shown above: {len(strong_wrong_location)}",
        "",
    ]
    if discovery is not None:
        strong_discovered = sum(1 for c in discovered if c.combined_score >= STRONG_THRESHOLD)
        lines += [
            "### Job boards", "",
            f"- Boards searched: {', '.join(discovery.get('boards') or []) or 'none'} "
            f"({discovery.get('queries', 0)} queries)",
            f"- Postings found: {discovery.get('found', 0)}",
            f"- Dropped — title only loosely matched the query: {discovery.get('title_filtered', 0)}",
            f"- Dropped — company already covered by the company scan: "
            f"{discovery.get('covered_by_company_scan', 0)}",
            f"- Dropped — company excluded from scans: {discovery.get('excluded', 0)}",
            f"- Dropped — already tracked as an application: {discovery.get('already_tracked', 0)}",
            f"- Dropped — the same job found twice: {discovery.get('duplicates', 0)}",
            f"- Discovered matches: {len(discovered)} ({strong_discovered} strong)",
            f"- Discarded (non-UK/non-remote): {discovered_wrong_location}",
            "",
        ]
        for err in discovery.get("errors") or []:
            lines.append(f"- **Search failed** — {err}")
        if discovery.get("errors"):
            lines.append("")
    lines += [
        "### ATS pagination caps", "",
    ]
    if coverage_notes:
        for name, shown, total in coverage_notes:
            lines.append(f"- **{name}** — showing {shown} of {total} postings returned by the ATS — not exhaustive")
        lines.append("")
    else:
        lines += ["_None — no fetches were truncated this run._", ""]

    SCANS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = SCANS_DIR / f"{today}-portal-scan.md"
    out_path.write_text("\n".join(lines) + "\n")
    return out_path


def refresh_web_db() -> None:
    """Refresh the Django site's Scan rows so the new report shows up immediately at
    /scans/ without a manual `manage.py import_jobs` step. Best-effort: the scan
    report itself is already written to disk regardless of whether this succeeds, so
    a failure here (e.g. the web app isn't set up in this checkout) is a warning, not
    a fatal error.
    """
    manage_py = REPO_ROOT / "src" / "web" / "manage.py"
    if not manage_py.exists():
        return
    try:
        subprocess.run(
            [sys.executable, str(manage_py), "import_jobs", "--quiet"],
            cwd=manage_py.parent, check=True, capture_output=True, text=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"  WARNING: could not refresh the web app's database (manage.py import_jobs failed): "
              f"{e.stderr.strip() or e}")


def render(scored_path: Path) -> Path:
    """Load a scored candidates file (same shape `scan-portals.py`'s candidates.json
    has, but with cv_score/ideal_score/location_category/notes filled in on each
    candidate) and write the final report. Used by both scoring paths."""
    data = json.loads(scored_path.read_text())
    candidates = [Candidate.from_dict(c) for c in data["candidates"]]
    matches, discarded_by_location, needs_review = classify(candidates)
    out_path = write_report(
        scanned_count=data["scanned_count"],
        not_scanned=[tuple(x) for x in data["not_scanned"]],
        matches=matches,
        discarded_by_location=discarded_by_location,
        needs_review=needs_review,
        no_roles=[tuple(x) for x in data["no_roles"]],
        total_found=data["total_found"],
        total_skipped_dedup=data["total_skipped_dedup"],
        coverage_notes=[tuple(x) for x in data["coverage_notes"]],
        prefiltered=data["prefiltered"],
        location_prefiltered=data["location_prefiltered"],
        discovery=data.get("discovery"),
    )
    refresh_web_db()
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Render the final scan report from a scored candidates file (no API call).")
    parser.add_argument("--scored", required=True, type=Path,
                         help="Path to a scored candidates JSON file (see scan-portals.py's "
                              "candidates.json for the unscored shape; a scorer fills in "
                              "cv_score/ideal_score/location_category/notes on each candidate)")
    args = parser.parse_args()

    out_path = render(args.scored)
    print(f"Report written: {out_path}")


if __name__ == "__main__":
    main()

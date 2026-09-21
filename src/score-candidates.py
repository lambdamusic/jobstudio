#!/usr/bin/env python3
"""
score-candidates.py

Opt-in, API-based scoring for the portal scan — the alternative to the default
agent-native scoring the `scan` skill subcommand does live. The only place `anthropic`
gets imported for scan (see backlog/drop-direct-anthropic-api-plan.md §2.2).

Why this exists alongside the agent-native default: agent-native scoring spends Claude
Code session/rate-limit budget, not API dollars. This path bills separately per token
instead — worth it for a large batch, or when session budget is tight. It also makes
`scan-portals.py` -> `score-candidates.py`, chained, a fully headless/cron-able
pipeline again, same as the old monolithic script.

Usage:
    source tools/env.sh && python score-candidates.py --candidates jobs/scans/2026-09-17-candidates.json

Reads the same rubric both scoring paths share (src/prompts/scan_score_rubric.md — see
that file's own header) so methodology can't drift between the two paths. Writes a
scored copy of the candidates file, then renders the same final report format
scan_report.py produces for the agent-native path.
"""

import argparse
import dataclasses
import json
import re
from pathlib import Path

import yaml

from scan_report import Candidate, load_area_profiles, render

import config

DATA_ROOT = config.data_root()
IDEAL_JOB_NOTES_FILE = DATA_ROOT / "jobs" / "notes" / "ideal-job-notes.md"
CRITERIA_FILE = DATA_ROOT / "jobs" / "profile" / "criteria.yaml"
# Code, not data — the scoring rubric ships with the repo.
RUBRIC_FILE = Path(__file__).parent / "prompts" / "scan_score_rubric.md"

MODEL = "claude-sonnet-4-6"
SCORING_CHUNK_SIZE = 20  # candidates per scoring call — keeps the JSON response well under max_tokens
SCORING_CALL_TIMEOUT = 90.0  # seconds — see score_candidates()


def load_ideal_job_notes() -> str:
    return IDEAL_JOB_NOTES_FILE.read_text() if IDEAL_JOB_NOTES_FILE.exists() else ""


def load_criteria_block() -> str:
    """Format jobs/profile/criteria.yaml into the compact text block the rubric's
    {criteria_block} placeholder expects. Returns "" if the file is missing, so
    scoring still runs on a fresh checkout — see scan_score_rubric.md's Dimension 2
    for how each field below is meant to be applied.
    """
    if not CRITERIA_FILE.exists():
        return ""
    data = yaml.safe_load(CRITERIA_FILE.read_text()) or {}
    hard = data.get("hard_filters", {}) or {}
    prefs = data.get("preferences", {}) or {}
    motivators = data.get("weighted_motivators", []) or []
    bonuses = data.get("bonus_signals", []) or []

    parts: list[str] = []
    excludes = hard.get("exclude", []) or []
    if excludes:
        parts.append("Dealbreakers (a role that clearly looks like one of these should score 1–2 on ideal_score, and the note must say so):\n"
                     + "\n".join(f"- {e}" for e in excludes))
    if hard.get("salary_floor_gbp"):
        parts.append(f"Salary floor: £{hard['salary_floor_gbp']:,} base. Flag postings whose stated range tops out below this.")
    leap = prefs.get("sectors_open_to_with_a_leap", []) or []
    if leap:
        parts.append("Domains he'd happily move into (don't penalise an unfamiliar domain if it's one of these): "
                     + "; ".join(leap))
    avoid = prefs.get("avoid_sectors", []) or []
    if avoid:
        parts.append("Sectors to avoid (a soft negative, not an auto-fail like the dealbreakers above — nudge "
                      "ideal_score down and say so in the note if the company's core business is clearly one of "
                      "these): " + "; ".join(avoid))
    if motivators:
        ranked = sorted(motivators, key=lambda m: m.get("weight", 0), reverse=True)
        parts.append("Weighted motivators (weight/5 — the higher the weight, the more it should pull ideal_score):\n"
                     + "\n".join(f"- [{m.get('weight', '?')}] {m.get('text', '')}" for m in ranked))
    culture = prefs.get("culture", []) or []
    if culture:
        parts.append("Culture traits he's drawn to (a soft signal — from what you know or can reasonably infer "
                      "about the company's reputation/culture, nudge ideal_score up if it's known for these, down "
                      "if known for the opposite; say nothing if you have no real signal either way):\n"
                     + "\n".join(f"- {c}" for c in culture))
    values = prefs.get("values", []) or []
    if values:
        parts.append("Personal values, ranked groups from a values exercise (group 1 matters most) — treat like "
                      "the culture traits above, a soft nudge based on company reputation, not a hard filter:\n"
                     + "\n".join(f"{i + 1}. {v}" for i, v in enumerate(values)))
    if bonuses:
        parts.append("Bonus signals (not required; if a posting clearly hits one, say so in the note and nudge ideal_score up):\n"
                     + "\n".join(f"- {b}" for b in bonuses))
    return "\n\n".join(parts)


def score_candidates(area: str, profile: dict, candidates: list[Candidate],
                     ideal_job_notes: str, criteria_block: str = "") -> None:
    if not candidates:
        return

    import anthropic

    postings = [
        {"id": i, "company": c.company, "title": c.title, "role_target": c.role_target, "location": c.location}
        for i, c in enumerate(candidates)
    ]
    rubric = RUBRIC_FILE.read_text()
    prompt = rubric.format(
        area_name=profile.get("name", area),
        description=profile.get("description", "").strip(),
        emphasis="\n".join(f"- {p}" for p in profile.get("emphasis", [])),
        key_terms=", ".join(profile.get("key_terms", [])),
        ideal_job_notes=ideal_job_notes.strip(),
        criteria_block=criteria_block.strip() or "_(none on file)_",
        postings=json.dumps(postings, indent=2),
    )

    # Explicit, well under the SDK's default (600s) — with category->area fallback
    # (2026-09-14) a run can mean 15-20+ of these chunked calls instead of 1-2, so one
    # slow/stuck call shouldn't be able to silently stall the whole scan for 10 minutes.
    client = anthropic.Anthropic(timeout=SCORING_CALL_TIMEOUT)
    try:
        message = client.messages.create(
            model=MODEL,
            max_tokens=max(2048, 200 * len(candidates)),
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.APIError as e:
        print(f"  WARNING: scoring call for '{area}' ({len(candidates)} candidates) failed — {e} "
              f"— these will show up as 'needs manual review' instead of scored.")
        return  # candidates keep cv_score=None -> "needs manual review"

    raw = message.content[0].text.strip()
    raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()

    try:
        results = json.loads(raw)
    except json.JSONDecodeError:
        print(f"  WARNING: scoring response for '{area}' ({len(candidates)} candidates) failed to parse as JSON "
              f"— these will show up as 'needs manual review' instead of scored.")
        return  # candidates keep cv_score=None -> "needs manual review"

    by_id = {r.get("id"): r for r in results if isinstance(r.get("id"), int)}
    for i, c in enumerate(candidates):
        r = by_id.get(i)
        if r and isinstance(r.get("cv_score"), int):
            c.cv_score = r["cv_score"]
            c.ideal_score = r.get("ideal_score") if isinstance(r.get("ideal_score"), int) else None
            c.location_category = r.get("location_category", "other")
            c.notes = r.get("notes", "")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Score a portal scan's candidates via the Anthropic API (opt-in alternative "
                    "to the default agent-native scoring), then render the final report.")
    parser.add_argument("--candidates", required=True, type=Path,
                         help="Path to scan-portals.py's candidates.json for this run")
    args = parser.parse_args()

    data = json.loads(args.candidates.read_text())
    candidates = [Candidate.from_dict(c) for c in data["candidates"]]
    profiles = load_area_profiles()
    ideal_job_notes = load_ideal_job_notes()
    criteria_block = load_criteria_block()

    by_area_candidates: dict[str, list[Candidate]] = {}
    for c in candidates:
        by_area_candidates.setdefault(c.area, []).append(c)
    total_chunks = sum(-(-len(cands) // SCORING_CHUNK_SIZE) for cands in by_area_candidates.values())
    print(f"Scoring {len(candidates)} candidates across {len(by_area_candidates)} areas "
          f"({total_chunks} API call{'s' if total_chunks != 1 else ''})...")
    chunk_num = 0
    for area, cands in by_area_candidates.items():
        for i in range(0, len(cands), SCORING_CHUNK_SIZE):
            chunk = cands[i:i + SCORING_CHUNK_SIZE]
            chunk_num += 1
            print(f"  [{chunk_num}/{total_chunks}] {area}: {len(chunk)} candidates...")
            score_candidates(area, profiles.get(area, {}), chunk, ideal_job_notes, criteria_block)

    scored_path = args.candidates.with_name(args.candidates.name.replace("-candidates.json", "-scored.json"))
    scored_data = dict(data)
    scored_data["candidates"] = [dataclasses.asdict(c) for c in candidates]
    scored_path.write_text(json.dumps(scored_data, indent=2))
    print(f"Scored candidates written: {scored_path}")

    out_path = render(scored_path)
    print(f"Report written: {out_path}")


if __name__ == "__main__":
    main()

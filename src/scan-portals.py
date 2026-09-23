#!/usr/bin/env python3
"""
scan-portals.py

Rescan tracked companies (from the tracker database) for new open roles via public
ATS APIs (Greenhouse, Lever, Workable, Workday, Ashby, SmartRecruiters, Teamtailor,
Rippling ATS, BambooHR) plus a generic first-party-JSON fetcher. Purely mechanical — fetch,
dedup, keyword + location pre-filter, classify not-scanned companies. Never imports
`anthropic` and never calls any model.

Writes the plausible (unscored) candidates plus every already-computed bookkeeping
section to jobs/scans/YYYY-MM-DD-candidates.json. Scoring happens next, as a separate
step, one of two ways (see backlog/drop-direct-anthropic-api-plan.md §2):

- Default, agent-native — the `scan` skill subcommand reads the candidates file and
  scores live, no API call.
- Opt-in, API-based — `python src/score-candidates.py --candidates <path>` for a
  fully headless/cron-able run, or when scoring volume should bill separately rather
  than spend Claude Code session budget.

Either way, `python src/scan_report.py --scored <scored-file>` (or score-candidates.py
internally) renders the same final report format.

Usage:
    python scan-portals.py
    python scan-portals.py --area data-platform
    python scan-portals.py --dry-run
"""

import argparse
import dataclasses
import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

import jobsdb

import httpx

from scan_report import Candidate, load_area_profiles

import config
import scan_config
import scan_sources

DATA_ROOT = config.data_root()
JOBS_DIR = DATA_ROOT / "jobs"
APPS_DIR = JOBS_DIR / "applications"
SCANS_DIR = JOBS_DIR / "scans"

HTTP_TIMEOUT = 10

# Which categories map to which CV area, which companies sit on an ATS their careers URL
# doesn't reveal, and which are on a platform with no fetcher — all four are facts about
# one person's search rather than about how scanning works, so they live in the data root
# (`<DATA>/jobs/scan-config.yaml`) rather than here. See src/scan_config.py.
#
# Categories and areas stay orthogonal: a category groups companies by industry/domain,
# an area is a CV positioning, and several categories can share one area rather than each
# getting a bespoke one just to be scored (decided 2026-09-14).
#
# All four are optional. Without them the scanner still runs, detecting each company's
# ATS from its careers URL; what's lost is the hand-researched part, which no amount of
# URL pattern-matching can infer.

_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def _strip_links(text: str) -> str:
    return _LINK_RE.sub(r"\1", text)


def _extract_url(text: str) -> str | None:
    m = _LINK_RE.search(text)
    return m.group(2) if m else None


# ---------------------------------------------------------------------------
# Known-URL collection (dedup)
# ---------------------------------------------------------------------------

def _normalize(url: str) -> str:
    """Return the job-identifying path segment (last non-empty segment), lowercased.

    ATS platforms don't always echo back the exact URL shape that was saved when an
    application was tracked (e.g. Workable's API returns /j/<code> while a tracked URL
    might be /<company>/j/<code>/apply) — the trailing ID segment is the stable part.
    """
    path = urlsplit(url.strip()).path.rstrip("/")
    segments = [s for s in path.split("/") if s]
    return segments[-1].lower() if segments else ""


def collect_known_urls() -> set[str]:
    known: set[str] = set()

    for url in jobsdb.known_job_urls():
        job_id = _normalize(url)
        if job_id:
            known.add(job_id)

    if APPS_DIR.exists():
        for notes in APPS_DIR.glob("**/notes.md"):
            text = notes.read_text()
            m = re.search(r"\*\*Job URL:\*\*\s*(.+)", text)
            if not m:
                continue
            for url in re.split(r"\s*·\s*", m.group(1).strip()):
                if url.startswith("http"):
                    job_id = _normalize(url)
                    if job_id:
                        known.add(job_id)

    return known


# ---------------------------------------------------------------------------
# Fetching. Which ATS a company is on — and why it isn't scanned when it isn't — moved
# to src/scan_sources.py (2026-09-23) so the web app can show the same answer.
# ---------------------------------------------------------------------------

class ScanError(Exception):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


MAX_RESULTS_PER_COMPANY = 200  # safety cap on pagination, even after server-side keyword filtering


def _search_keyword(role_target: str) -> str:
    """First significant word of the tracked role target, used as a server-side filter
    so a large board (thousands of postings) doesn't return an arbitrary unfiltered slice."""
    m = re.search(r"[A-Za-z]{4,}", role_target)
    return m.group(0) if m else ""


def fetch_jobs(source: dict, role_target: str, client: httpx.Client) -> tuple[list[dict], int | None]:
    """Returns (jobs, total_available). total_available is set only when the source
    reported more results than were fetched (i.e. results were truncated)."""
    platform = source["platform"]
    try:
        if platform == "greenhouse":
            token = source["token"]
            resp = client.get(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs", timeout=HTTP_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            jobs = [
                {
                    "title": j["title"],
                    "url": j["absolute_url"],
                    "location": (j.get("location") or {}).get("name", "unknown"),
                }
                for j in data.get("jobs", [])
            ]
            return jobs, None

        if platform == "lever":
            token = source["token"]
            resp = client.get(f"https://api.lever.co/v0/postings/{token}?mode=json", timeout=HTTP_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            jobs = []
            for j in data:
                categories = j.get("categories", {})
                loc = categories.get("location", "unknown")
                workplace = j.get("workplaceType")
                if workplace:
                    loc = f"{loc} ({workplace})"
                jobs.append({"title": j["text"], "url": j["hostedUrl"], "location": loc})
            return jobs, None

        if platform == "workable":
            token = source["token"]
            resp = client.get(f"https://apply.workable.com/api/v1/widget/accounts/{token}", timeout=HTTP_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            if "jobs" not in data:
                raise ScanError(f"workable account '{token}' returned no jobs field")
            jobs = []
            for j in data["jobs"]:
                parts = [p for p in (j.get("city"), j.get("state"), j.get("country")) if p]
                loc = ", ".join(parts) or "unknown"
                if j.get("telecommuting"):
                    loc = f"{loc} (remote)"
                jobs.append({
                    "title": j["title"],
                    "url": j.get("url") or j.get("shortlink"),
                    "location": loc,
                })
            return jobs, None

        if platform == "workday":
            tenant, wd, site = source["tenant"], source["wd"], source["site"]
            search_text = _search_keyword(role_target)
            page_size = 20
            jobs = []
            total = None
            offset = 0
            while True:
                resp = client.post(
                    f"https://{tenant}.{wd}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs",
                    json={"appliedFacets": {}, "limit": page_size, "offset": offset, "searchText": search_text},
                    timeout=HTTP_TIMEOUT,
                )
                resp.raise_for_status()
                data = resp.json()
                if total is None:
                    total = data.get("total")
                postings = data.get("jobPostings", [])
                if not postings:
                    break
                jobs.extend(
                    {
                        "title": j["title"],
                        "url": f"https://{tenant}.{wd}.myworkdayjobs.com/{site}{j.get('externalPath', '')}",
                        "location": j.get("locationsText", "unknown"),
                    }
                    for j in postings
                )
                offset += page_size
                if (isinstance(total, int) and offset >= total) or len(jobs) >= MAX_RESULTS_PER_COMPANY:
                    break
            truncated_total = total if isinstance(total, int) and total > len(jobs) else None
            return jobs, truncated_total

        if platform == "ashby":
            token = source["token"]
            resp = client.get(f"https://api.ashbyhq.com/posting-api/job-board/{token}", timeout=HTTP_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            jobs = []
            for j in data.get("jobs", []):
                loc = j.get("location", "unknown")
                if j.get("isRemote"):
                    loc = f"{loc} (remote)"
                jobs.append({"title": j["title"], "url": j.get("jobUrl"), "location": loc})
            return jobs, None

        if platform == "bamboohr":
            # Public JSON behind every BambooHR careers page: no key, no paging, the
            # whole board in one response (`meta.totalCount` matches `result`).
            token = source["token"]
            resp = client.get(f"https://{token}.bamboohr.com/careers/list",
                              headers={"Accept": "application/json"}, timeout=HTTP_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            jobs = []
            for j in data.get("result", []):
                # Two location objects, and which one is filled depends on
                # `locationType`: type 1 (remote) carries `atsLocation`, the office
                # types carry `location`. Read both and take whichever has content —
                # the alternative is trusting a numeric code BambooHR doesn't document.
                loc_obj = j.get("location") or {}
                ats_obj = j.get("atsLocation") or {}
                parts = [p for p in (loc_obj.get("city"), loc_obj.get("state")) if p]
                if not parts:
                    parts = [p for p in (ats_obj.get("city"), ats_obj.get("province"),
                                         ats_obj.get("state"), ats_obj.get("country")) if p]
                loc = ", ".join(dict.fromkeys(parts)) or "unknown"
                if str(j.get("locationType")) == "1":
                    loc = f"{loc} (remote)" if loc != "unknown" else "remote"
                jobs.append({
                    "title": j["jobOpeningName"],
                    "url": f"https://{token}.bamboohr.com/careers/{j['id']}",
                    "location": loc,
                })
            return jobs, None

        if platform == "smartrecruiters":
            token = source["token"]
            keyword = _search_keyword(role_target)
            page_size = 100
            jobs = []
            total = None
            offset = 0
            while True:
                resp = client.get(
                    f"https://api.smartrecruiters.com/v1/companies/{token}/postings",
                    params={"limit": page_size, "offset": offset, "q": keyword},
                    timeout=HTTP_TIMEOUT,
                )
                resp.raise_for_status()
                data = resp.json()
                if total is None:
                    total = data.get("totalFound")
                content = data.get("content", [])
                if not content:
                    break
                for j in content:
                    loc_info = j.get("location", {})
                    loc = loc_info.get("fullLocation", "unknown")
                    if loc_info.get("remote"):
                        loc = f"{loc} (remote)"
                    jobs.append({
                        "title": j["name"],
                        "url": f"https://jobs.smartrecruiters.com/{token}/{j['id']}",
                        "location": loc,
                    })
                offset += page_size
                if (isinstance(total, int) and offset >= total) or len(jobs) >= MAX_RESULTS_PER_COMPANY:
                    break
            truncated_total = total if isinstance(total, int) and total > len(jobs) else None
            return jobs, truncated_total

        if platform == "teamtailor":
            domain = source["domain"]
            resp = client.get(f"https://{domain}/jobs.json", timeout=HTTP_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            jobs = []
            for item in data.get("items", []):
                job_posting = item.get("_jobposting") or {}
                locations = job_posting.get("jobLocation") or []
                parts = []
                for loc in locations:
                    addr = loc.get("address", {}) if isinstance(loc, dict) else {}
                    place = ", ".join(p for p in (addr.get("addressLocality"), addr.get("addressCountry")) if p)
                    if place:
                        parts.append(place)
                jobs.append({
                    "title": item["title"],
                    "url": item["url"],
                    "location": "; ".join(parts) if parts else "unknown",
                })
            return jobs, None

        if platform == "rippling":
            # No public API — reads the Next.js SSR hydration payload embedded in the
            # page HTML. Undocumented and could break if the frontend changes; wrapped
            # so a shape change degrades to a ScanError (-> "not scanned"), not a crash.
            token = source["token"]
            resp = client.get(f"https://ats.rippling.com/{token}/jobs", timeout=HTTP_TIMEOUT)
            resp.raise_for_status()
            m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', resp.text, re.DOTALL)
            if not m:
                raise ScanError("rippling: __NEXT_DATA__ payload not found (page structure may have changed)")
            try:
                next_data = json.loads(m.group(1))
                items = next_data["props"]["pageProps"]["dehydratedState"]["queries"][0]["state"]["data"]["items"]
            except (KeyError, IndexError, TypeError):
                raise ScanError("rippling: __NEXT_DATA__ shape changed, could not locate job items")
            jobs = []
            for it in items:
                locs = it.get("locations") or []
                loc = locs[0].get("name", "unknown") if locs else "unknown"
                jobs.append({"title": it["name"], "url": it["url"], "location": loc})
            return jobs, None

        if platform == "firstparty_entries":
            # Not an ATS at all: some companies' own frontends call a first-party JSON
            # endpoint directly (found via network capture). The URL is per-company and
            # comes from the override, so no company's endpoint is baked in here; what
            # is shared is the response shape this parser expects —
            # {"entries": [{title, url, officeTeamLocation}], "totalJobsEntries": N}.
            # A company whose endpoint returns a different shape needs its own branch.
            resp = client.get(
                source["url"],
                params={"offset": 0, "orderBy": "postDate DESC", "section": "jobs", "limit": 50},
                timeout=HTTP_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            jobs = [
                {"title": e["title"], "url": e["url"], "location": e.get("officeTeamLocation", "unknown")}
                for e in data.get("entries", [])
            ]
            total = data.get("totalJobsEntries")
            truncated_total = total if isinstance(total, int) and total > len(jobs) else None
            return jobs, truncated_total

    except httpx.TimeoutException:
        raise ScanError(f"{platform} request timed out after {HTTP_TIMEOUT}s")
    except httpx.HTTPStatusError as e:
        raise ScanError(f"{platform} returned HTTP {e.response.status_code}")
    except (KeyError, json.JSONDecodeError) as e:
        raise ScanError(f"{platform} returned an unexpected response shape ({e})")

    raise ScanError(f"unknown platform '{platform}'")


# ---------------------------------------------------------------------------
# Pre-filter
# ---------------------------------------------------------------------------

def _words(text: str) -> set[str]:
    return {w.lower() for w in re.findall(r"[A-Za-z]{4,}", text)}


def is_plausible_match(title: str, role_target: str, key_terms: list[str]) -> bool:
    title_words = _words(title)
    reference_words = _words(role_target) | {w for term in key_terms for w in _words(term)}
    return bool(title_words & reference_words)


# A second, free pre-filter — location — run right alongside the keyword one, before a
# candidate is ever queued for scoring (decided 2026-09-14, after a live run showed 417
# candidates heading to the scorer; ~85% of those have a location string with no UK or
# remote signal anywhere in it — sending those to the LLM at all was pure waste).
#
# Deliberately conservative in the same direction as parsers.py's
# _UK_OR_REMOTE_HINT_RE (the web page's Unscored-tab heuristic, same intent, kept as a
# separate constant since this one runs at scan time against ATS location strings, not
# report-parsing time against rendered bullets): only ever used to positively EXCLUDE a
# posting when there's a confident "no UK/remote mention at all" read. Vague or missing
# location text is never excluded — better to send an occasional low-value posting to
# the scorer than to silently drop a good match on a rare phrasing the regex missed.
# Real Dimension-3 classification (uk/remote/other) is still the scorer's job for
# anything that gets through — this filter never claims to positively confirm eligibility.
_LOCATION_PREFILTER_HINT_RE = re.compile(
    r"\b(united kingdom|u\.k\.|uk|england|scotland|wales|northern ireland|london|"
    r"edinburgh|glasgow|manchester|birmingham|belfast|cardiff|bracknell|remote)\b",
    re.IGNORECASE,
)
_LOCATION_PREFILTER_VAGUE = {"unknown", "", "multiple locations", "various", "n/a"}


def excluded_by_location_prefilter(location: str) -> bool:
    loc = (location or "").strip()
    if loc.lower() in _LOCATION_PREFILTER_VAGUE:
        return False
    return not _LOCATION_PREFILTER_HINT_RE.search(loc)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Rescan tracked companies for new open roles.")
    parser.add_argument("--area", help="Limit scan to a single target area, by its jobs/targets/ slug")
    parser.add_argument("--dry-run", action="store_true", help="Fetch/parse/dedup only, print stats, write nothing")
    args = parser.parse_args()

    companies = jobsdb.companies()
    known_urls = collect_known_urls()
    profiles = load_area_profiles()

    scanned: list[dict] = []
    not_scanned: list[tuple[str, str, str | None]] = []
    no_roles: list[tuple[str, str | None]] = []
    plausible: list[Candidate] = []
    coverage_notes: list[tuple[str, int, int]] = []
    total_found = 0
    total_skipped_dedup = 0
    platform_counts: dict[str, int] = {}

    # Postings that were fetched and passed dedup, but didn't share a keyword with the
    # company's tracked role target (or, for mapped areas, its key_terms) — the full
    # per-posting list is kept (not just a count) so the report can list them
    # individually for manual follow-up (a real case: one company with ~40 fetched
    # postings and 0 visible anywhere under the old count-only design, because none
    # matched the tracked role target).
    prefiltered: dict[str, dict] = {}  # company -> {"category": str, "jobs": [{"title","url"}]}

    def record_prefiltered(co: dict, job: dict) -> None:
        entry = prefiltered.setdefault(co["name"], {"category": co["category"], "jobs": []})
        entry["jobs"].append({"title": job["title"], "url": job["url"]})

    # Postings that passed the keyword pre-filter but were excluded by
    # excluded_by_location_prefilter() before ever reaching the scorer — same shape and
    # purpose as `prefiltered` above, tracked separately since the reason is different.
    # Also keeps each posting's raw location text — the actual reason it was excluded,
    # useful for manually sanity-checking the heuristic.
    location_prefiltered: dict[str, dict] = {}

    def record_location_prefiltered(co: dict, job: dict, location: str) -> None:
        entry = location_prefiltered.setdefault(co["name"], {"category": co["category"], "jobs": []})
        entry["jobs"].append({"title": job["title"], "url": job["url"], "location": location})

    category_to_area = scan_config.category_to_area()
    default_area = scan_config.default_area()

    with httpx.Client(headers={"User-Agent": "jobstudio-portal-scan/1.0"}) as client:
        for co in companies:
            area = category_to_area.get(co["category"], default_area)
            if args.area and area != args.area:
                continue

            cov = scan_sources.coverage(co["name"], co["url"])
            if not cov["scanned"]:
                not_scanned.append((co["name"], cov["reason"], co["url"]))
                continue

            source = cov["source"]
            platform = cov["platform"]
            try:
                jobs, total_available = fetch_jobs(source, co["role_target"], client)
            except ScanError as e:
                not_scanned.append((co["name"], f"{platform} fetch failed — {e.reason}", co["url"]))
                continue

            scanned.append(co)
            total_found += len(jobs)
            platform_counts[platform] = platform_counts.get(platform, 0) + len(jobs)
            if total_available:
                coverage_notes.append((co["name"], len(jobs), total_available))

            fresh = [j for j in jobs if _normalize(j["url"]) not in known_urls]
            total_skipped_dedup += len(jobs) - len(fresh)

            if not fresh:
                no_roles.append((co["name"], co["url"]))
                continue

            profile = profiles.get(area, {})
            for job in fresh:
                cand = Candidate(
                    company=co["name"], title=job["title"], url=job["url"],
                    role_target=co["role_target"], area=area, category=co["category"],
                    location=job.get("location", "unknown"),
                )
                if not is_plausible_match(job["title"], co["role_target"], profile.get("key_terms", [])):
                    record_prefiltered(co, job)
                elif excluded_by_location_prefilter(cand.location):
                    record_location_prefiltered(co, job, cand.location)
                else:
                    plausible.append(cand)

    if args.dry_run:
        print(f"Scanned: {len(scanned)}, not scanned: {len(not_scanned)}, "
              f"roles found: {total_found}, deduped: {total_skipped_dedup}, "
              f"plausible candidates: {len(plausible)}, "
              f"filtered out pre-scoring: {sum(len(d['jobs']) for d in prefiltered.values())}, "
              f"excluded pre-scoring by location: {sum(len(d['jobs']) for d in location_prefiltered.values())}")
        print(f"By platform: {platform_counts}")
        if coverage_notes:
            print("Truncated (coverage notes):")
            for name, shown, total in coverage_notes:
                print(f"  {name}: showing {shown} of {total}")
        for name, reason, _url in not_scanned:
            print(f"  NOT SCANNED: {name} — {reason}")
        return

    today = date.today().isoformat()
    out_path = SCANS_DIR / f"{today}-candidates.json"
    SCANS_DIR.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({
        "date": today,
        "scanned_count": len(scanned),
        "not_scanned": not_scanned,
        "no_roles": no_roles,
        "total_found": total_found,
        "total_skipped_dedup": total_skipped_dedup,
        "coverage_notes": coverage_notes,
        "prefiltered": prefiltered,
        "location_prefiltered": location_prefiltered,
        "candidates": [dataclasses.asdict(c) for c in plausible],
    }, indent=2))

    print(f"Candidates written: {out_path} ({len(plausible)} plausible, across "
          f"{len({c.area for c in plausible})} areas)")
    print("Next: score them — either let the `scan` skill subcommand score live "
          "(default), or run `python src/score-candidates.py --candidates "
          f"{out_path}` for the opt-in API path.")


if __name__ == "__main__":
    main()

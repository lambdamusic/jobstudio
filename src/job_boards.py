"""Discovery: search general job boards (Adzuna, Reed) for roles at companies you don't track.

The company scan only ever rereads companies already in the tracker — every hit has had a
human decide the company is worth watching. This is the other half (`#8`): the same target
areas, searched across a whole job market, so a company nobody has heard of yet can turn
up. The price is that nothing here is vetted, so the report keeps these apart from
tracked-company matches rather than ranking them together.

Both boards need a free key, which belongs to the person running the search, not to the
toolkit. Best kept in `~/.jobstudio.ini` (`adzuna_app_id`, `adzuna_app_key`,
`reed_api_key`), which is per machine and in no repository; the environment
(`ADZUNA_APP_ID`, …) and `job_boards` in `<DATA>/jobs/scan-config.yaml` also work, but a
data root is often a git repo with a remote, and a key committed there is in its history
for good. A board with no credentials is skipped, so the feature is off until someone
opts in.

What gets searched: `job_boards.queries`, a short list of searches as you would type
them into a job board — `"Head of Data" OR "VP Data"`, `knowledge graph`. `OR` splits a
line into separate phrases, one request each per board. There is deliberately no
fallback to the target areas' `key_terms`: tried on a real search on 2026-10-08, its 62
terms cost 124 requests and added 512 candidates, most of them noise — "training" found
hairdressing coaches, "safety cases" nuclear engineers. Key terms are for recognising a
title, not for searching a market.

A posting is kept only if its title contains every word of the phrase that found it —
"Head of Data & Analytics" for "Head of Data", not "Head of Training" — and is assigned
a target area by its title, as a tracked company's posting is.

Only the HTTP calls touch the network; the filtering and labelling are plain functions,
tested without it.
"""

from __future__ import annotations

import os
import re
from datetime import date, datetime, timedelta

import config
import scan_match

ADZUNA_URL = "https://api.adzuna.com/v1/api/jobs/gb/search/1"
REED_URL = "https://www.reed.co.uk/api/1.0/search"
HTTP_TIMEOUT = 15

DEFAULT_MAX_DAYS_OLD = 7
DEFAULT_RESULTS_PER_QUERY = 50


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def _secret(value, env: str) -> str:
    """One credential: from scan-config.yaml, else the environment, else ~/.jobstudio.ini
    (as the lowercased variable name). The `.ini` is the one to recommend — per machine,
    in no repository — because a data root may well be a git repo with a remote."""
    return str(value or os.environ.get(env) or config.setting(env.lower()) or "")


def credentials(settings: dict) -> dict[str, dict]:
    """{board: creds} for every board that has a complete set. A board missing any part
    is left out, which is how it is switched off."""
    adzuna = settings.get("adzuna") or {}
    reed = settings.get("reed") or {}
    found = {}
    app_id = _secret(adzuna.get("app_id"), "ADZUNA_APP_ID")
    app_key = _secret(adzuna.get("app_key"), "ADZUNA_APP_KEY")
    if app_id and app_key:
        found["adzuna"] = {"app_id": app_id, "app_key": app_key}
    api_key = _secret(reed.get("api_key"), "REED_API_KEY")
    if api_key:
        found["reed"] = {"api_key": api_key}
    return found


def queries(settings: dict) -> list[str]:
    """The phrases to search for, from `job_boards.queries`: each line split on `OR`,
    quotes dropped, deduped case-insensitively in the order given.

    `"Head of Data" OR "VP Data"` -> ["Head of Data", "VP Data"]. Neither board's
    boolean syntax is relied on — one request per phrase works the same on both.
    """
    raw = settings.get("queries") or []
    if isinstance(raw, str):
        raw = [raw]
    seen, out = set(), []
    for line in raw:
        for phrase in re.split(r"\s+OR\s+", str(line)):
            phrase = re.sub(r"\s+", " ", phrase.replace('"', "")).strip()
            if phrase and phrase.casefold() not in seen:
                seen.add(phrase.casefold())
                out.append(phrase)
    return out


# ---------------------------------------------------------------------------
# Labelling and matching — pure
# ---------------------------------------------------------------------------

# Recruitment agencies post most of what a general board carries, under their own name
# rather than the employer's. Neither board marks them reliably in search results, so this
# is a name heuristic: words agencies name themselves with, plus the large UK tech/data
# agencies whose names give nothing away. Extend it per search with `job_boards.agencies`.
_AGENCY_WORDS_RE = re.compile(
    r"\b(recruit\w*|resourcing|staffing|personnel|headhunt\w*|talent (?:solutions|partners|acquisition)"
    r"|search (?:partners|associates|ltd|limited)|search (?:&|and) (?:consultancy|selection)"
    r"|executive search|selection)\b",
    re.IGNORECASE,
)
_KNOWN_AGENCIES = {
    "hays", "michael page", "page personnel", "robert half", "robert walters", "harnham",
    "reed", "adecco", "randstad", "huxley", "hydrogen group", "la fosse", "investigo",
    "nigel frank", "jefferson frank", "tenth revolution group", "computer futures",
    "oho group", "burns sheehan", "opus", "spectrum it", "experis", "manpower",
    "hamilton barnes", "venesky brown", "searchability", "salt", "xcede", "client server",
    "akkodis", "modis", "harvey nash", "nonstop consulting", "data idols", "morson",
    "ashdown", "circle", "psd", "careerwise", "bowers partnership", "gleeson",
}


def is_agency(name: str, extra: list[str] | None = None) -> bool:
    """A known agency name at the start of the advertiser's — agencies post under their
    divisions ("Michael Page Technology", "Morson Edge") — or an agency word anywhere."""
    key = company_key(name)
    if not key:
        return False
    known = _KNOWN_AGENCIES | {company_key(x) for x in extra or []}
    if any(key == k or key.startswith(k + " ") for k in known if k):
        return True
    return bool(_AGENCY_WORDS_RE.search(name or ""))


_SUFFIX_RE = re.compile(r"\b(ltd|limited|plc|inc|llc|llp|gmbh|corp|corporation|co|group|uk|the)\b")


def company_key(name: str) -> str:
    """A company name reduced to what two spellings of it have in common: lowercase,
    punctuation and legal suffixes gone. "Acme Ltd." and "ACME Limited" meet here."""
    s = re.sub(r"[^\w\s]", " ", (name or "").lower())
    s = _SUFFIX_RE.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def company_keys(name: str) -> set[str]:
    """Every key a tracked company should be recognised by: its name, the name without a
    parenthetical, and the parenthetical alone — "Initech Data (Globex Analytics)", a
    subsidiary tracked under its parent's name, is posted under either half."""
    keys = {company_key(name)}
    m = re.match(r"^(.*?)\s*\((.+)\)\s*$", name or "")
    if m:
        keys |= {company_key(m.group(1)), company_key(m.group(2))}
    return {k for k in keys if k}


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def title_matches(title: str, query: str) -> bool:
    """Does the title contain every word of the phrase? Both boards match loosely — on
    the description, on any one word, on stems — and a phrase is what was meant."""
    words = set(_tokens(title))
    return all(w in words for w in _tokens(query))


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------

def _posting(*, board, title, url, company, location, snippet, salary_min=None, salary_max=None) -> dict:
    snippet = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", snippet or "")).strip()
    salary = ""
    # Under £10k is not an annual salary — a day rate, or a typo ("£5" was a real one).
    salary_min, salary_max = [v if v and v >= 10_000 else None for v in (salary_min, salary_max)]
    if salary_min or salary_max:
        lo, hi = salary_min or salary_max, salary_max or salary_min
        salary = f"£{int(lo):,}" if lo == hi else f"£{int(lo):,}–£{int(hi):,}"
    return {"board": board, "title": (title or "").strip(), "url": url or "",
            "company": (company or "").strip(), "location": location or "unknown",
            "snippet": snippet[:400], "salary": salary}


def search_adzuna(client, creds: dict, query: str, *, max_days_old: int, results: int) -> list[dict]:
    resp = client.get(ADZUNA_URL, params={
        "app_id": creds["app_id"], "app_key": creds["app_key"],
        "title_only": query, "max_days_old": max_days_old,
        "results_per_page": results, "sort_by": "date", "content-type": "application/json",
    }, timeout=HTTP_TIMEOUT)
    resp.raise_for_status()
    out = []
    for j in resp.json().get("results", []):
        out.append(_posting(
            board="adzuna", title=j.get("title"), url=j.get("redirect_url"),
            company=(j.get("company") or {}).get("display_name"),
            location=(j.get("location") or {}).get("display_name"),
            snippet=j.get("description"),
            # Adzuna fills in a model's estimate when an advert gives no salary, and says
            # so; on a real search those ranged from £5 to £214,500. Advertised only.
            **({} if str(j.get("salary_is_predicted")) == "1" else
               {"salary_min": j.get("salary_min"), "salary_max": j.get("salary_max")})))
    return out


def search_reed(client, creds: dict, query: str, *, max_days_old: int, results: int,
                today: date | None = None) -> list[dict]:
    # HTTP Basic with the key as the username and an empty password. Reed has no
    # posted-within filter, so age is applied here, from each result's `date`.
    resp = client.get(REED_URL, params={"keywords": query, "resultsToTake": min(results, 100)},
                      auth=(creds["api_key"], ""), timeout=HTTP_TIMEOUT)
    resp.raise_for_status()
    cutoff = (today or date.today()) - timedelta(days=max_days_old)
    out = []
    for j in resp.json().get("results", []):
        try:
            posted = datetime.strptime(j.get("date") or "", "%d/%m/%Y").date()
        except ValueError:
            posted = None
        if posted and posted < cutoff:
            continue
        out.append(_posting(
            board="reed", title=j.get("jobTitle"), url=j.get("jobUrl"),
            company=j.get("employerName"), location=j.get("locationName"),
            snippet=j.get("jobDescription"),
            salary_min=j.get("minimumSalary"), salary_max=j.get("maximumSalary")))
    return out


_SEARCH = {"adzuna": search_adzuna, "reed": search_reed}


def discover(client, settings: dict, profiles: dict[str, dict], areas: list[str], default_area: str, *,
             skip_company_keys: set[str], known: set[str], normalize) -> tuple[list[dict], dict]:
    """Search every configured board for every query. Returns (postings, stats).

    Each returned posting carries `area` — the one of `areas` its title fits best, by
    `scan_match.pick_area`, else `default_area` — and `agency`. Dropped along the way,
    each counted in `stats`:
    - a title missing a word of the phrase that found it (`title_filtered`);
    - a posting already tracked as an application (`already_tracked`, via `known` and the
      same `normalize` the company scan dedups with);
    - a posting from a company the company scan already covered this run
      (`covered_by_company_scan`) — it has been seen there, with its vetting;
    - the same job found twice — by two queries, or on both boards (`duplicates`), keyed
      on company + title, since Adzuna also indexes Reed's listings.
    A board that errors is recorded in `stats["errors"]` and the rest carry on.
    """
    boards = credentials(settings)
    max_days = int(settings.get("max_days_old") or DEFAULT_MAX_DAYS_OLD)
    per_query = int(settings.get("results_per_query") or DEFAULT_RESULTS_PER_QUERY)
    extra_agencies = settings.get("agencies") or []
    stats = {"boards": sorted(boards), "queries": 0, "found": 0, "title_filtered": 0,
             "already_tracked": 0, "covered_by_company_scan": 0, "duplicates": 0, "errors": []}
    seen: set[tuple[str, str]] = set()
    out: list[dict] = []
    phrases = queries(settings) if boards else []
    stats["phrases"] = phrases
    for board, creds in boards.items():
        for query in phrases:
            stats["queries"] += 1
            try:
                found = _SEARCH[board](client, creds, query, max_days_old=max_days, results=per_query)
            except Exception as e:  # one failed query costs that query, not the run
                stats["errors"].append(f"{board} '{query}': {type(e).__name__}: {e}"[:200])
                continue
            stats["found"] += len(found)
            for p in found:
                if not p["title"] or not p["url"]:
                    continue
                if not title_matches(p["title"], query):
                    stats["title_filtered"] += 1
                    continue
                if normalize(p["url"]) in known:
                    stats["already_tracked"] += 1
                    continue
                if company_key(p["company"]) in skip_company_keys:
                    stats["covered_by_company_scan"] += 1
                    continue
                dedup = (company_key(p["company"]), p["title"].casefold())
                if dedup in seen:
                    stats["duplicates"] += 1
                    continue
                seen.add(dedup)
                p["area"] = scan_match.pick_area(p["title"], query, areas, profiles) or default_area
                p["agency"] = is_agency(p["company"], extra_agencies)
                out.append(p)
    return out, stats

# One company, more than one target area (TODO `#40`)

2026-09-27

Prompted by a real case rather than a tidy-up: a pivot toward AI safety means Anthropic
is worth watching for two different kinds of role — the data-product roles it was
originally tracked for, and the safety roles that are now the point. The tracker could
express one of those, not both.

## The problem

Three things were one-per-company: the `category` FK, the area derived from it via
`category_to_area`, and the `role_target` string. The area chooses which rubric a posting
is scored against; the role target feeds the title pre-filter.

So a company with two plausible positionings lost one of them *before scoring*, in
`is_plausible_match`, on a word-overlap test against the wrong area's `key_terms` and the
wrong job titles. Anthropic's tracked role target was "VP/Director Data Products, Head of
Data, Technical Architect, Data Solutions Specialist" — no overlap with "Research
Engineer, Interpretability", so that posting would have been counted in "Filtered out
before scoring" and never looked at again.

## What changed

**`company_areas` in `<DATA>/jobs/scan-config.yaml`** — company name → area slugs, in
preference order. Overrides the single category-derived area.

**`scan_match.pick_area(title, role_target, areas, profiles)`** — the *company* declares
which areas are possible, the *posting* picks one, by how many of its title words each
area's `key_terms` account for. Ties and role-target-only matches fall to the first
listed, so config order expresses preference.

One posting still gets one area and one score. The alternative — score each posting once
per candidate area — doubles the scoring bill to produce two numbers for one job and puts
it in the report twice, when "is this role a fit" has one answer.

**The property that matters**: for a company with one area, `pick_area` is exactly the old
`is_plausible_match` — same word sets, same outcome, `None` where the gate returned False.
A test asserts it over a spread of titles. Without that, adding multi-area support quietly
changes every existing scan, and there would be no way to tell.

**Why config and not a model field.** A `Company.areas` many-to-many is the
modelling-correct answer and costs a migration, an admin widget, an importer change and a
company-page change. `company_overrides` already establishes that per-company scanning
exceptions live in scan-config — this is a fact about how *this search* wants a company
scanned, not about the company. Two lines to undo. Promote it if it ever needs to show on
a company page.

**The report was the only real breakage.** `_match_table_by_company` printed
`first.category → first.area` once per heading, with a docstring asserting the area never
varies within a company's group — precisely the assumption removed. A company whose
postings span areas now gets an Area column and a heading saying "scored per role";
single-area companies produce byte-identical output, so nobody else's report changes.

## `src/scan_match.py`

`_words` and `is_plausible_match` moved out of `scan-portals.py` and `pick_area` joined
them. Same reason `scan_sources.py` was extracted on 2026-09-23: the hyphen in
`scan-portals.py` means nothing can import it, so the function deciding what reaches the
scorer at all had no test and could not get one. `excluded_by_location_prefilter` is the
same class of thing and stayed put — moving it is a separate change.

## Two things found while doing it

**Ashby, SmartRecruiters and Teamtailor were needing overrides they didn't need.** The
comment above `_ATS_PATTERNS` grouped them with Workday and Rippling as platforms that
"hide the tenant behind a corporate page and have to be recorded by hand". That is true of
a company linking to its own careers page and false whenever it links straight at the
board — `jobs.ashbyhq.com/<token>` is as self-describing as `jobs.lever.co/<token>`. So
every Ashby company got a hand-written override, including ones whose tracked URL already
spelled the token out.

Adding them surfaced a trap: the pattern table emitted `{"platform", "token"}` for
everything, but Teamtailor's fetcher reads `source["domain"]` and wants a whole host. That
would have been a KeyError mid-scan, not a check failure. Entries now carry the parameter
name the fetcher reads, and a test asserts the key per platform rather than just the
platform.

**The resolver checks URL shape, not that the board exists.** Testing a guess of
`boards.greenhouse.io/deepmind` reported "scanned via greenhouse"; the board 404s. A real
scan degrades visibly there ("greenhouse fetch failed"), so nothing lies — but
`scan_config --check` cannot tell you a token is dead, and shouldn't be read as saying so.

## `soft_negatives`

Separate, same branch. `hard_filters.exclude` is already score-only — the rubric pulls
`ideal_score` to 1–2 rather than dropping the posting — but that is a dealbreaker's
weight, and "heavily political large organisations" is a reservation, not a dealbreaker:
worth knowing about a role, never worth hiding it. `soft_negatives` is the mirror of
`bonus_signals`, nudging down a point or two with the reason named in the note. The rubric
documents it and a test checks that it does, because a field the rubric never mentions is
decoration.

## Checks

178 tests (17 new), suite green. `tools/py src/scan-portals.py --dry-run` against the real
tracker: 59 companies scanned, 1760 roles, 336 plausible candidates, no crash — no
company is in `company_areas` yet, so that run also exercises the unchanged path.

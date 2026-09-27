# Using `#38`, `#39` and `#40` for real, the day `#40` landed

2026-09-27

Companion to `2026-09-27-multi-area-companies.md`. That entry is the code; this is what
happened when the whole chain — seed a category, define an area, scan against it — was
driven end to end against a live data root for the first time, for a genuine change of
career direction. Deliberately no company names here: `log/` is published, and
`make-public-tree --check` compares the public tree against the names in the tracker.

## The flow held up

One new target area, one new category, seventeen companies, a `category_to_area` mapping,
a `company_areas` entry and a notes file. `scan_config.py --check` came back **0 errors,
0 warnings** across six areas, and a `--dry-run` limited to the new area fetched 1515
roles from seven boards. No step of `init.md` §"Define the target areas" or §"Seed the
tracker" turned out to be wrong or missing, which is the first real evidence either
section is right.

Two things the new checks caught on their first outing, both mine:

**The unquoted-colon trap, immediately.** One `emphasis` bullet I wrote ended a clause
with a colon, so YAML read it as a mapping and the entry arrived as a dict where a string
belonged. `#39`'s check exists for precisely that and it fired on the first validation —
about ninety seconds after being used in anger for the first time.

**A company name that is also an ordinary English word.** One of the seventeen is called
*Resolution*, and this repo says "resolution order" and "resolution chain" about fifteen
times across `src/config.py`, `src/identity.py`, the toolkit plan and four log entries.
The leak check refused the whole tree. Correct behaviour, and exactly what
`.tracked-company-exceptions` is for — but worth knowing that exempting a word this
common means the check can never flag it again, so the exemption is a real, permanent
loss of coverage rather than a formality.

## The finding that mattered most: two companies had never been scanned

Two long-tracked companies, both rated 4/5, both resolved to `bespoke career page — no
public jobs API` and neither had a `company_overrides` entry. So neither had appeared in a
single scan since being added. Both were **one line each** to fix, and both boards turned
out to be live and large.

Nothing was broken: the report had been listing them under "not scanned" with an accurate
reason the whole time. The failure was that nobody read that list as a to-do. This is an
argument for `#22`-style periodic triage of the not-scanned section, and a reason the
graded reasons from `#30` matter — "bespoke page" and "no override yet" look the same in
that list and are not the same problem.

## The pre-filter lesson: qualifiers, not seniority words

The first run produced **353 plausible candidates** for one area, which is a lot to score
live. Counting the matches showed why: **264 of the 353 got through on the single word
"engineer"**, and 263 of the 353 came from one frontier lab's board.

The cause was mine and instructive. The pre-filter splits `role_target` and the area's
`key_terms` into words and passes a posting whose title shares *any* of them. I had put
"research engineer" and "member of technical staff" in the area's `key_terms` — phrases
that read as precise and decompose into {research, engineer, member, technical, staff},
which is most of any large engineering org's board.

Removing them changed the count by **zero**, because each company's own `role_target`
still carried the same words. That is the part worth remembering: the two inputs are
unioned, so trimming one while the other repeats it achieves nothing, and it is easy to
believe you have fixed something. The fix was to trim both — the area's `key_terms` down
to qualifiers (Alignment, Interpretability, Evaluations, Oversight), and the one
enormous board's `role_target` to qualifiers as well.

353 → 130 → 113, in two steps, with **no loss at all** at the small focused companies,
where a bare "Research Engineer" *is* the relevant job. The second step was dropping
"Safety Systems" — a real team name, which contributes the generic word "systems" and was
letting infrastructure roles through.

So: **generic titles belong to a company, qualifiers belong to an area.** A company's
`role_target` only ever matches that company's own board, so a generic word there is
bounded; the same word in an area's `key_terms` applies to every company mapped to it.
Written up in `scan.md` rather than left in this log, because it will be needed again by
anyone adding an area.

## Raised, not done

`#41` — there is no `update-company` CLI. Re-pointing existing rows took three
`manage.py shell` one-liners. Fine once; unbearable across twenty rows, which is what the
next change of direction would mean.

## Checks

178 tests green, `tools/smoke-test` pass, `make-public-tree --check` clean (once the
common-word company name was exempted).

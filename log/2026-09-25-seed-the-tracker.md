# Seeding the tracker at `init` (TODO `#38`)

2026-09-25

## The problem

`init` ends with a data root, a CV and — after `stocktake` — a profile. It does not end
with any companies. `scan` reads tracked companies, so the first scan on a fresh data
root fetches nothing, scores nothing and reports nothing.

That is the toolkit's most visible feature failing on day one, in a way that looks like
a bug rather than an empty input. Nothing on screen says "you have no companies"; the
report just comes back empty. `#38` was raised the day before (commit `34ec870`), which
recorded the problem in `TODO.md` and nothing else.

## What changed

The work is mostly prose — this is an agent-native flow, so the deliverable is the
instructions the agent follows. `subcommands/init.md` gains **§"Seed the tracker"**:

1. Ask for direction rather than guessing — sectors, org size, geography, and any
   companies already in mind. Pre-fill the question from `criteria.yaml` and
   `stocktake.md` §6 so the user is correcting a draft, not filling in a blank.
2. Agree two or three categories and create them.
3. Research 10–20 candidates and present them as a table for a yes per row. Not an
   exhaustive sweep: a tracker seeded with fifty unvetted names is worse than an empty
   one — it is work to undo, it buries the good rows, and every later scan pays for it.
4. Check each careers URL resolves to a readable board *before* writing it.
5. Write the rows.
6. Map the new categories to target areas, then run `scan` and show the result.

Placed after `stocktake`, not at CV time, because that is where the target areas,
sectors and hard filters get written — there is far more to infer a starting list from
by then than the CV alone. `stocktake.md` step 7 offers the same step at close-out when
the tracker is still empty, since that is where someone who skipped it at `init` will
actually be.

## Two gaps that made the flow unwritable

Both only became visible when trying to write step 2 and step 4 as commands someone
could actually run.

**Nothing outside the Django admin could create a category.** `company.md` already said
"propose two or three categories and confirm them before adding the first company", and
gave no mechanism for it. `jobsdb.add_category()` plus `add-category` is that mechanism.
Idempotent, because bootstrapping means proposing a set and then adding companies into
it; an existing category keeps its hand-set `order` rather than having a later call
quietly rewrite it.

**`add-company` silently dropped an unknown category.** `Category.objects.filter(name=...).first()`
returns `None`, which is a valid value for a nullable FK — so the command reported
success, wrote the row, and the mistake surfaced later as a company missing from its
category in the web app and scored against `scan-config.yaml`'s `default_area` instead
of its own. On a cold start, where no category exists yet, *every* `--category` did this.

It now refuses, naming the tracked categories and the command to create the missing one.
Auto-creating on miss was the other option and is worse: it turns a typo into a permanent
second category with one company in it, which is exactly the one-category-per-company
sprawl `company.md` tells the agent to avoid.

**A careers URL could only be checked after it was written.** `scan_sources.coverage()`
already answered "will `scan` pick this up, and on what" — the companies page renders it
per row. But that is one loop too late when the URL is being *chosen*: a company tracked
against a page with no board underneath is invisible to the one feature that makes
tracking it worth anything. `scan_sources.py` now runs as a script over a name and a URL
and prints the same answer. Still pure and offline, so checking twenty candidates during
research costs nothing.

## Found along the way — `#39`

A fresh data root has no **target areas** either. `init` creates `jobs/targets/` and
leaves it empty; nothing else writes into it. `scan` still fetches — every company falls
to `default_area`, itself unset without a `scan-config.yaml` — but scoring has no
`<area>.yaml` to substitute into the rubric, so the Area Score half of every row is
meaningless.

`#38` seeds the companies; `#39` is the other half of making that first scan real.
Deliberately not folded in: it is a different artifact, derived from different inputs,
and doing it here would have meant a second unreviewed design inside a change whose
point was the first one. §"Seed the tracker" step 6 carries a note so the gap is stated
rather than silently producing scores that mean nothing.

## Checks

`tracker` + `cvs` suite green (7 new tests across `CategoryBootstrapTests` and
`ScanCoverageCliTests`), `tools/smoke-test` green, `tools/make-public-tree --check` clean.

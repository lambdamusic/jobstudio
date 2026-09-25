# Target areas on a fresh data root (TODO `#39`)

2026-09-25

Same day as `#38`, which this is the other half of. `#38` gave a cold-start data root
some companies to scan; without this, scanning them produces a report whose scores mean
nothing.

## The problem

A **target area** is a CV positioning — one `jobs/targets/<slug>.yaml`. `init` creates
the directory and nothing ever writes into it: not `stocktake`, not `cv`, not `company`.

The failure is not that scanning breaks. It is that it doesn't:

```python
profile = profiles.get(area, {})          # scan-portals.py
...
is_plausible_match(job["title"], co["role_target"], profile.get("key_terms", []))
```

An area naming no file yields an empty profile, and every downstream step degrades
quietly. The keyword pre-filter falls back to the company's tracked role target alone,
so postings are dropped on a narrower test than intended. The scorer is handed no
`description`, `emphasis` or `key_terms` — and still returns an Area Score for every
row, because that is what it was asked for. The report renders, the tables fill, the
numbers look like numbers. Nothing anywhere says the area profile was empty.

On a fresh data root that is *every* row.

It is not only the empty-directory case. The same silence covers a `category_to_area`
entry pointing at a renamed area, and a `default_area` that was never set — which is why
the fix is a check over the whole chain rather than a "targets dir is empty" warning.

## What changed

**`scan_config.check()`**, plus `tools/py src/scan_config.py --check`. It reports:

- no target areas at all
- a target missing `name`, `description` or `key_terms` — nothing for the rubric to
  score against
- a list entry that isn't a string. `- SciGraph: a knowledge graph` parses as a mapping;
  `parsers._flatten_yaml_list` repairs that for the web app's display, and nothing
  repairs it for the scorer
- `default_area` or a `category_to_area` value naming a file that doesn't exist
- a tracked category with no mapping *and* no usable fallback — it resolves to `""`
- a `category_to_area` key matching no tracked category (warning: it does nothing, which
  is usually a rename)

It lives in `scan_config.py` because four of those are that module's own fields. It
takes `tracked_categories` as an argument rather than reading them, so it stays free of
Django and stays testable without a database. `scan_report.TARGETS_DIR` now imports
`scan_config.targets_dir()` rather than spelling the path out a second time.

**`init.md` §"Define the target areas"**, placed before §"Seed the tracker" — the
ordering is the point, since seeding maps categories onto areas that have to exist
first. Derive two or three from `stocktake.md` §6 and `criteria.yaml`, confirm by name,
write the YAMLs, `import_jobs`, `--check`. `stocktake.md`'s close-out offers both steps
in that order. `scan.md` gains the check as step 0.

The section says areas are positionings, not industries, because that is the mistake
this step invites: an area per industry produces files differing only in `name`, which
score identically and make the tailoring worthless. And `emphasis` is drawn from the
base CV, never invented — those bullets end up in a CV sent to employers, so it is the
same rule on-ramp C already applies to web-sourced facts.

## What the check found on its first two runs

**The shipped example was misconfigured.** `example-data/jobs/scan-config.yaml` mapped
`Data Platform & Modern Data Stack` and `Developer Tools & Observability`; the fixture's
categories are `Data infrastructure`, `Developer tools` and `Fintech`. Both entries
matched nothing, every example company fell through to `default_area: data-platform`,
and `developer-advocacy` — one of the two areas the example ships to demonstrate that
categories and areas are orthogonal — was unreachable in the dataset demonstrating it.
Now keyed on the real names, with `test_the_example_data_root_passes_its_own_check`
asserting no warnings, not just no errors. Reverting the YAML fails that test, which is
how it was confirmed to be a guard rather than decoration.

**The scratch root `jobstudio-devdata` has no `scan-config.yaml`** — it predates the
file (2026-09-21), so all three of its categories resolve to no area. Not a problem with
anyone's job search: that root is a copy of the example dataset kept for exercising the
web app (`#26`), and the real search resolves through `~/.jobstudio.ini`, which passes
`--check` clean across its five areas. Worth a copy from `example-data/` next time the
scratch root is used for a scan, and nothing more.

**A doc was asserting the opposite of the truth.** `docs/portal-scan-and-scoring.md`
said "every company always gets a real area now — there's no 'no target profile for this
category' case left". True of the *mapping* since 2026-09-14, and never true of the
file it names. Corrected, with the `profiles.get(area, {})` behaviour spelled out.

## Note

While verifying `#38` I ran `src/jobsinit.py` against a scratch data root to exercise
the new `add-category` path. `jobsinit` writes the checkout wiring as part of its job,
so that repointed `.jobstudio-data` and `jobstudio.code-workspace` away from
the real data root — and deleting the scratch directory afterwards left the checkout
pointing at nothing.

Restoring it took two goes, and the second one is the interesting part. There was no
record of what `.jobstudio-data` had held, so I inferred `jobstudio-devdata` from
`share-as-toolkit-plan.md` calling it "its development data root" and wrote that. The
**leak check caught the mistake**: `make-public-tree --check` compares the public tree
against the names in *your* tracker, and devdata is a copy of the example, so every
example company in `example-data/` was suddenly "a company from your tracker" and it
refused. The earlier clean run had said "135 in tracker" — the real search, not the
example's five. So the checkout had no pointer at all and resolved through
`~/.jobstudio.ini`. Removed, and the workspace file repointed to match.

This is exactly what `CLAUDE.md` warns about under "Working on the toolkit is not the
same as using it": `JOBSTUDIO_DATA=<scratch>` in the environment does not protect you
when the script under test is the one that writes the pointer. `jobsinit` writing the
wiring is its job; running it ad hoc to exercise something else is what was wrong.

## Checks

`tracker` + `cvs` suite green (9 new tests in `TargetAreaCheckTests`), `tools/smoke-test`
green, `tools/make-public-tree --check` clean.

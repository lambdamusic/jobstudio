# Under the hood — the scripts

Part of the **[docs/](README.md)** guide collection. Everything else in `docs/` is
written for someone *using* the toolkit, where the interface is a Claude command:
`/jobstudio scan`, `/jobstudio application`, and so on. This file is the other layer —
the Python entry points and shell scripts those commands drive.

**You do not need any of this to use the toolkit.** It is here for three situations:

- something went wrong and you want to run one step on its own to see what it did
- you are extending the toolkit, or reading it to decide whether you want to
- you are automating a piece of it from cron or CI, where there is no session to talk to

Everything below goes through **`tools/py`**, the generated wrapper that runs the
project's virtualenv interpreter. `/jobstudio init` writes it; it is gitignored because
its path is specific to your machine. If it is missing, run `init` again or set
`$JOBSEARCH_PY`.

> **Working on the toolkit is not the same as using it.** A bare command here resolves
> to whatever your config says — on the maintainer's machine, that is a real job search.
> When testing a change that writes files, point it somewhere throwaway first:
> `JOBSTUDIO_DATA=/path/to/scratch tools/py src/...`.

---

## Where the data root comes from

Everything reads and writes one **data root**, and none of it lives in this repo.

```bash
tools/py src/config.py --path     # the resolved data root, and nothing else
tools/py src/config.py --chain    # every layer, and which one won
```

Resolution order: `$JOBSTUDIO_DATA`, then the checkout's `.jobstudio-data` pointer,
then `~/.jobstudio.ini`. `--chain` is the first thing to run when something writes to a
place you did not expect.

## Setup

```bash
tools/py src/jobsinit.py --data-root <path> [--from-example] [--name ...] [--venv-python ...]
```

What `/jobstudio init` calls once it has your answers. It creates the data root, writes
`config.yaml`, generates `tools/py`, wires the checkout, and creates the admin account.
Re-running it against a different data root **repoints this checkout** — which is the
intended behaviour, and worth knowing before you run it to test something.

## The tracker database

sqlite owns applications and companies. `src/jobsdb.py` is the command-line way in:

```bash
tools/py src/jobsdb.py status                    # counts, the same ones /jobstudio status prints
tools/py src/jobsdb.py list                      # applications
tools/py src/jobsdb.py show <num>                # one application
tools/py src/jobsdb.py add-company --name ... --url ... --category ... --fit N
tools/py src/jobsdb.py add-category --name ... --order N
tools/py src/jobsdb.py set-status <num> <status>
tools/py src/jobsdb.py set-fit <num> --level {strong,moderate,stretch,weak} [--pros ...] [--cons ...]
tools/py src/jobsdb.py add-application ...        # what /jobstudio application calls
tools/py src/jobsdb.py link-company <num>
tools/py src/jobsdb.py show-company <slug>
tools/py src/jobsdb.py categories
```

There is no `update-company` yet (backlog `#41`) — editing a tracked company means the
Django admin, or a `manage.py shell -c` one-liner.

## CVs and cover letters

```bash
tools/py src/render.py --functional                      # base CV -> .docx
tools/py src/render.py --chronological --label 001-acme
tools/py src/render.py --functional --file <tailored.md> --label 001-acme
tools/py src/render.py --cover-letter --file <letter.md> --label 001-acme
```

`.docx` is the default and usually the only thing you want. `--format html` and
`--format pdf` are opt-in extras; on a cover letter they are *additions*, since the
`.docx` is written either way.

```bash
tools/py src/render.py --functional --check              # parse only, writes nothing
```

**`--check` is the one to know about.** The CV parsers are hand-written regexes that
discard whatever they cannot match, so a CV in the wrong shape does not error — it
renders a clean, well-formed, *empty* document. `--check` reports what each section
actually parsed to, names anything it could not read, and exits non-zero if content was
lost. Both shipped example CVs were silently losing their entire work history until
2026-09-29 precisely because nothing asked this question.

Depth: **[cv-pipeline.md](cv-pipeline.md)**, and the format contract in
`.claude/skills/jobstudio/references/cv-base-format.md`.

## Scanning job boards

```bash
tools/py src/scan-portals.py                             # fetch + pre-filter, no API call
tools/py src/scan_sources.py "<name>" "<careers url>"    # can this company be scanned, and on what platform?
tools/py src/scan_config.py --check                      # target areas, category map, overrides
tools/py src/scan_report.py --scored <path>              # scored candidates -> the markdown report
```

The fetch is mechanical and writes `jobs/scans/YYYY-MM-DD-candidates.json`. Scoring is
done by the agent reading that file against the rubric — no API call, and no key
anywhere in the toolkit.

`scan_sources.py` is the useful one when adding companies: it answers whether a careers
URL resolves to a supported ATS *before* a row is written, rather than leaving you to
read it off a coverage column afterwards.

Depth: **[portal-scan-and-scoring.md](portal-scan-and-scoring.md)**.

## The web app

```bash
tools/run-dev-local-db            # http://127.0.0.1:8010, foreground until Ctrl-C
tools/run-dev-local-db 8020       # if 8010 is busy
tools/site-build --clean          # render the whole site to <DATA>/site/
tools/site-preview                # browse that build locally
bash tools/publish-surge.sh       # site-build, then push to Surge
```

Django management commands, run as `tools/py src/web/manage.py <name>`:

| Command | What it does |
|---|---|
| `import_jobs` | Refresh the rows derived from files — areas, base CVs, scans |
| `build_static` | Render every page to `site/` |
| `refresh_company_status` | Recompute each company's derived status |
| `migrate_exports` / `prune_exports` | One-off tidies from the 2026-09-24 export move |
| `backfill_saved_entry` / `backfill_status_history` | One-off history backfills |
| `changepassword admin` | Change the admin password |

`import_jobs` is rarely needed by hand: scans refresh themselves, and since 2026-09-29
the CV and area pages re-sync from disk when they notice files and rows disagree.

Depth: **[dashboard-status.md](dashboard-status.md)**, and `src/web/README.md` for the
app's internals.

## Checks

```bash
tools/py src/web/manage.py test tracker cvs   # the test suite, against example-data/
tools/smoke-test                              # a from-scratch install in a temp clone
tools/make-public-tree --check                # nothing personal about to be published
```

Run all three before considering a change done. `smoke-test` is the one that catches
assumptions only visible to someone who does not already have the files — note that it
clones committed `HEAD`, so it cannot see uncommitted work. `make-public-tree --check`
matters most after writing prose: this repo is public, and a changelog entry or a test
fixture is exactly where a real company name ends up.

## Data in and out

```bash
tools/db-dump                     # sqlite -> JSON fixture in the data root
tools/db-load                     # the reverse
tools/build-example-fixture       # regenerate example-data/'s fixture
```

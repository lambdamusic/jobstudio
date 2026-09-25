# init

First-run setup: create a data root, wire this checkout to it, and either populate it
with the example job search or start it empty.

`src/jobsinit.py` does the mechanical work and takes every answer as a flag. Your job
is the conversation — ask, confirm, then call it once.

## Ask first

1. **Where should the data live?** Recommend a synced folder (Dropbox, Drive,
   iCloud) and say why: nothing in the data root is version-controlled, so the sync
   service *is* the backup. Suggest `~/Dropbox/jobstudio-data`.
2. **Name, email, location** — goes in `<DATA>/config.yaml`, used in generated
   filenames and documents. Skip if starting from the example, which ships a
   fictional identity.
3. **How do they want to start?** Four on-ramps — offer them explicitly rather than
   defaulting to the empty one, because typing a career into a blank file is the
   worst of the four and the one people abandon.

   | | For | Then |
   |---|---|---|
   | **A. The example** | A first look. Everything is browsable immediately, and `scan` works because the example's companies are real. | Nothing — explore, then re-run `init` for real |
   | **B. From a CV** | They have a CV to hand. Fastest accurate start. | `cv --import <path>`, then `stocktake` for the gaps |
   | **C. From the web** | The CV is stale, elsewhere, or was never written. | Research → confirm → draft, then `stocktake` for the gaps |
   | **D. From scratch** | They would rather just talk. | `cv --rebuild` (interview), then `stocktake` |

   B, C and D all converge on `stocktake`: whatever a CV or the web gives you is
   history and facts, never motivation, constraints or what they actually want next.
   Those only come from asking.

   And all three end at **"Define the target areas"** and then **"Seed the tracker"**
   below, in that order. A data root with a CV, a profile, no areas and no companies is
   not a finished setup — it is the state in which `scan` finds nothing, and then scores
   what it does find against nothing.

Confirm the data root path back to the user before running. It is the one answer that
is annoying to change later.

## On-ramp C — bootstrapping from the web

Offer this as: *"I can look you up and draft a starting profile from what's public —
then we fill the gaps by talking."* Useful, and it has two failure modes that matter
more than the convenience, so handle both explicitly.

**1. Confirm you have the right person before using anything.** Name collisions are
the normal case, not the edge case. Ask for a disambiguator up front — current or last
employer, city, or a URL they own — and search with it. Then show what you found and
ask "is this you?" *before* writing a single line into the data root. Never merge two
people's histories into one CV; if results look like more than one person, say so and
ask rather than guessing.

**2. Nothing web-sourced goes into a CV unconfirmed.** This CV gets sent to employers.
A mis-scraped job title, a wrong set of dates or an invented employer is not a typo —
it reads as a lie on an application, and the user carries that, not you. So:

- Present findings as a **numbered list of proposed facts with their sources**, and get
  confirmation per item — not a finished CV to review, which invites a nod-through.
- Anything unconfirmed is **dropped**, not softened. An empty section is honest; a
  plausible invention is not.
- Dates and titles are the most commonly wrong and the most damaging. Ask about them
  directly even when a source looks authoritative.

**Where to actually look.** Personal site or blog, GitHub, Google Scholar and ORCID,
conference and meetup speaker pages, company team pages, press mentions, professional
society listings.

**On LinkedIn, be straight with the user.** It is the obvious source and the one that
works worst: automated fetches are routinely bot-blocked, and scraping it is against
its terms. Do not promise it and do not quietly fail at it. Ask them instead to paste
their profile text or export the profile PDF — which is faster and more accurate than
anything a scrape would produce, and turns on-ramp C into on-ramp B, which is the
better path anyway.

If research turns up little — a common outcome for people who aren't publishers,
speakers or maintainers — say so plainly and move to D. It is not a failure, and
pretending a thin result is a profile wastes their time.

Once confirmed, write `<DATA>/config.yaml` (name, email, location), draft the base CV
via `cv --rebuild` using the confirmed facts as the starting material rather than a
blank interview, and then run `stocktake`.

## First: find or create the interpreter

`init` writes `tools/py`, a wrapper that `exec`s one specific Python — so it has to know
which one before it can run, and on a fresh clone there may not be one yet. **This is
yours to sort out, not the user's**: they should be able to clone the repo, open a
session and say `/jobstudio init`. Resolve in this order and tell them which you took:

1. **`tools/py` already exists** — read the interpreter path out of it and reuse it.
   Re-running `init` is normal (switching from the example to real data), and silently
   building a second virtualenv would be rude.
2. **A virtualenv already on disk** — one the user names, or a conventional location:
   `~/.venvs/jobstudio`, `$WORKON_HOME/jobstudio` (or `~/.virtualenvs/`, `~/Envs/`), or
   `.venv/` in the repo.
3. **Otherwise create one.** Ask first — it installs packages and writes outside the
   repo, so it is not yours to decide silently:

   ```bash
   python3 -m venv ~/.venvs/jobstudio
   ~/.venvs/jobstudio/bin/python -m pip install -e .
   ```

Check it before going on, because the failure is otherwise deferred to a confusing
place: Python >= 3.11, and `import django, yaml, docx, httpx` all resolve.

## Then run

Call `jobsinit.py` **with that interpreter**. `--venv-python` defaults to whichever
interpreter is running the script, so if you invoke it with the venv's python the flag
is redundant — pass it only when they differ:

```bash
<venv>/bin/python src/jobsinit.py --data-root <path> --from-example
```

or, for an empty start:

```bash
<venv>/bin/python src/jobsinit.py --data-root <path> \
    --name "<full name>" --email "<email>" --location "<city>"
```

Once that has run, `tools/py` exists and everything afterwards goes through it:

```bash
tools/py src/jobsdb.py status
```

## Then check it worked

Don't just report success because the command exited 0 — run the two things that prove
the wiring, and show the output:

```bash
tools/py src/config.py --chain     # which layer resolved the data root, and to what
tools/py src/jobsdb.py status      # reads the database through that data root
```

With `--from-example` that status should report **3 applications tracked**. If it
reports something else, the checkout is pointing at the wrong data root — read the
chain output rather than guessing.

Offer to start the web app (`tools/run-dev-local-db`, http://127.0.0.1:8010) rather
than launching it unasked: it runs in the foreground until interrupted.

## What it writes

| | |
|---|---|
| `<DATA>/` | the tree, `config.yaml`, `db.sqlite3` |
| `<repo>/.jobstudio-data` | the pointer — per checkout, and it beats `~/.jobstudio.ini` |
| `~/.jobstudio.ini` | machine-level default, so `<DATA>` resolves even when the working directory is not the repo |
| `<repo>/tools/py` | venv wrapper, so nothing needs an absolute interpreter path |
| `<repo>/.claude/settings.local.json` | the data root in `permissions.additionalDirectories`, so sessions stop prompting on every file outside the repo |
| `<repo>/jobstudio+data.code-workspace` | one VS Code window over both folders — the `+data` names what it opens: a private data root alongside the public repo |
| `<repo>/src/web/local_settings.py` | copied from the example, if missing |
| `core.hooksPath` → `tools/git-hooks` | git config, so the pre-push leak check runs (below) |
| a Django admin account | `admin`/`admin` by default, or your own via `--admin-user` + `$JOBSTUDIO_ADMIN_PASSWORD`; `--no-admin` skips it |

All gitignored — the workspace file included, since it names an absolute path into
someone's job search. Re-running is safe: it adds what is missing and leaves the rest
alone. Nothing is overwritten without `--force`, and there is no
wipe mode — this points at a directory holding someone's whole job search.

## The pre-push check — only if this checkout has a remote

The repo is public, and it pushes `dev` as well as `main`, so **any** push publishes.
`tools/git-hooks/pre-push` runs `tools/make-public-tree --check` and blocks a push that
would carry personal data. It is versioned in the repo rather than left in `.git/hooks`,
which is not backed up and is empty on a fresh clone — but it only takes effect once git
is told where to look:

```bash
git config core.hooksPath tools/git-hooks
```

Set that during `init` when the checkout has an `origin` remote. Skip it silently when
it does not: someone who cloned the toolkit to *use* it has no repo to leak into, and a
hook that fires on a push they will never make is noise.

Mention it either way, because it is the one piece of `init` that changes what `git`
does. `git push --no-verify` bypasses it deliberately.

## The admin account

Since the database became the source of truth, the **Django admin is the editing
surface** — browsing works without a login, but changing anything does not. The example
dataset deliberately ships no user account (a public repo must not carry a password
hash), so a fresh install has none.

`init` creates one automatically — **`admin` / `admin`** by default — and says so in its
output, including the command to change it. Mention that to the user rather than letting
them find it later; it is fine while the server stays on `127.0.0.1` and not fine after.

To set a real password at install time, or skip the account:

```bash
JOBSTUDIO_ADMIN_PASSWORD='<their password>' tools/py src/jobsinit.py \
    --data-root <path> --admin-user <name> --admin-email <email>
```

**Never pass a password as a command-line flag** — it lands in shell history and in the
process list. That is why `init` takes it from the environment and has no
`--admin-password`.

## Define the target areas — after `stocktake`, on-ramps B/C/D

A **target area** is a CV positioning — one `<DATA>/jobs/targets/<slug>.yaml`. It is
what an application is tagged with, what `cv` tailors toward, and what `scan` scores a
posting against. `init` creates the directory and leaves it empty, and nothing else
writes into it.

**An empty `jobs/targets/` does not stop a scan; it hollows one out.** `scan-portals.py`
looks the area profile up with `profiles.get(area, {})` and carries on, so the keyword
pre-filter quietly falls back to the company's role target alone and the scorer gets no
`description`, `emphasis` or `key_terms` to judge against — it still emits an Area Score
for every row, and that number means nothing. The report does not say so. That is worse
than an error, so do this before the tracker has anything in it to scan.

Skip it on on-ramp A: the example ships two working areas.

### 1. Propose two or three, from the profile

Read `<DATA>/jobs/profile/stocktake.md` §6 (capabilities and career objectives) and
`criteria.yaml` (`preferences.role_types`, `role_level`, `departments`,
`sectors_open_to_with_a_leap`). Those two sections exist to answer "what shape of role
am I going for" — an area is that answer written down in the form the tooling reads.

Two or three. Areas are **positionings, not industries** — a category groups companies
by domain, an area is how the CV is angled, and several categories can share one. An
area per industry is the mistake to avoid; it produces files that differ only in their
`name` and score identically.

One of them may well be a *role-type* target that cuts across industries — solutions
architecture, developer advocacy — chosen when the role itself is that shape whatever
the company does. Propose them by name with a sentence each and get a yes before
writing anything.

### 2. Write one YAML per area

Filename is the slug: `<DATA>/jobs/targets/data-platform.yaml`.

| Key | |
|---|---|
| `name` | Human-readable title, shown in the web app |
| `description` | 2–3 lines: what kind of company, what kind of role, who the users are. The scorer reads this |
| `emphasis` | The CV bullets that matter most for this positioning — **their real achievements**, in their words, with numbers where they have them |
| `key_terms` | Words that appear in postings of this shape. Used by the keyword pre-filter, so too few silently drops good postings and too many drown the scan in noise |
| `expand_sections` / `condense_sections` | Optional: which CV sections `cv` should lengthen or shorten for this area |

`example-data/jobs/targets/data-platform.yaml` is a complete worked example — read it
before writing the first one.

**`emphasis` is drawn from the CV, never invented.** It is the same rule as on-ramp C:
these bullets end up in a tailored CV that gets sent to employers. If the base CV does
not support a bullet, it does not go in.

**Quote any list entry containing `: `** — `- SciGraph: a knowledge graph` parses as a
mapping rather than a string, and the scorer then gets a dict where a term should be.

### 3. Import them and check

```bash
tools/py src/web/manage.py import_jobs    # creates the Area rows from the YAMLs
tools/py src/scan_config.py --check       # do the areas and the config line up?
```

`--check` is the one that catches the silent failures: an area with no `description` or
`key_terms`, a `category_to_area` entry or a `default_area` naming a file that does not
exist, a tracked category that resolves to no area at all, and the unquoted-colon trap.
It exits non-zero when any of those is true. Run it again after seeding the tracker —
the category side of it only has something to say once there are categories.

## Seed the tracker — after the target areas exist

`init` finishes with a CV and a profile and **no companies**, which is the one thing
`scan` needs to do anything at all. The first scan on a fresh data root therefore finds
nothing — so the most visible feature in the toolkit looks broken on day one, for a
reason nothing on screen explains. Close that before handing the session back.

Do it **after `stocktake`**, not at CV time. The stocktake is where the target areas,
sectors and hard filters get written, so by then there is far more to infer a starting
list from than the CV alone. Skip it entirely on on-ramp A — the example ships real
companies precisely so `scan` works out of the box.

### 1. Ask for direction rather than guessing

A tracker seeded with fifty irrelevant names is worse than an empty one: it is work to
undo, it buries the few good rows, and every later scan pays for it. So ask first, in
one short round — sectors and domains; organisation size (SMEs count, and are easy to
forget); geography and remote policy; and **any companies they already have in mind**,
which is usually the best row in the final list and the fastest to confirm.

Read `<DATA>/jobs/profile/criteria.yaml` and `stocktake.md` §6 before asking, and put
what is already there in the question as a proposal — `preferences.sectors`,
`org_size`, `hard_filters.geography`. They should be correcting a draft, not filling in
a blank.

### 2. Agree the categories first

Companies go into categories, and the toolkit ships none. Two or three, broad enough
that several companies share each one — this is a grouping by domain, not a label per
company:

```bash
tools/py src/jobsdb.py add-category --name "Research Infrastructure" --order 1
```

Idempotent, so re-running is safe. `add-company` will **refuse** a category that does
not exist rather than quietly writing the company without one, so create them first.

### 3. Research, then present candidates for confirmation

Aim for **10–20**, not an exhaustive sweep. Enough that the first scan has something to
chew on; few enough that the user can actually read the list and say no to half of it.

Present them as a table — company, what it does in a few words, why it fits *their*
stated direction, proposed category, careers URL — and get a yes per row. Unvetted
entries are cheaper to be wrong about than a CV line, but they are not free, and the
user has the context to reject in seconds what would take you a search to rule out.

Write only what they approve.

### 4. Capture a careers URL that `scan` can actually read

**A name alone is not enough.** A company tracked without a resolvable board is
invisible to `scan`, so a bootstrap that records only names hands back a list that
still scans nothing — the exact failure this step exists to prevent. Check each URL
before writing it, with the same resolver the scanner acts on:

```bash
tools/py src/scan_sources.py "Grafana Labs" "https://grafana.com/about/careers/"
```

It prints either `scanned via <platform>` or `NOT scanned — <reason>`. Offline, no
fetch, so checking twenty is free.

On `NOT scanned`, it is worth one look before settling: many corporate careers pages
hide a Greenhouse, Lever, Ashby, Workday, SmartRecruiters or Teamtailor board
underneath — open the page and check where the job links actually go. When you find
one, record it in `company_overrides` in `<DATA>/jobs/scan-config.yaml` (see `scan.md`)
rather than putting the board URL in the tracker; the tracker should keep the URL a
human would want to click. If there is genuinely no API, add the company anyway with
its real careers page — it shows up in the report's "not scanned" list as a company to
check by hand, which is the honest answer.

### 5. Write the rows

```bash
tools/py src/jobsdb.py add-company \
  --name "Grafana Labs" --url "https://grafana.com/about/careers/" \
  --role-target "Director of Data Platform" --fit 4 \
  --category "Research Infrastructure" \
  --notes "Open-source observability; strong remote-first culture"
```

`--fit` and `--role-target` come from the profile, exactly as `/jobstudio company`
derives them — follow `subcommands/company.md` for the per-field judgement rather than
re-deriving it here.

### 6. Map the categories to target areas, then prove it

`scan` scores each company against a **target area**, picked from the company's category
via `category_to_area` in `<DATA>/jobs/scan-config.yaml`. A category with no mapping
falls to that file's `default_area`. Write both — the file is optional and may not exist
yet; `scan.md` documents its shape and `example-data/jobs/scan-config.yaml` is a working
one to copy.

Several categories can share one area. That is the normal case, not a compromise — do
not add an area to give a category its own.

Then check the whole chain resolves, and run the scan:

```bash
tools/py src/scan_config.py --check
```

Every problem it reports is one the scanner swallows: a mapping pointing at an area with
no file, a category falling through to nothing. Fix them before scanning rather than
after, because a scan with a hollow profile still produces a report full of scores.

Then run `/jobstudio scan` and show them the result. That is what turns the setup from
a claim into something they have watched work.

## Afterwards

Confirm it worked by running `/jobstudio status`, then say what is next: `stocktake`
for an empty start (and then seeding the tracker, above), or just browsing for the
example. Mention that `tools/smoke-test` re-runs the whole thing from a clean clone if
they ever want to check the install.

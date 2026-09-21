# jobstudio

An agent-native job-search toolkit: track companies, log applications, tailor a CV per
role, draft cover letters, and scan ATS job boards for new postings — driven end to end
from a Claude Code session, with a local Django web app for browsing.

**No API key needed.** Every default workflow runs inside your Claude Code session.
There is one opt-in path (`scan --api`, for scoring a scan headlessly, e.g. from cron)
that wants an Anthropic key; nothing else does.

**Your data stays yours.** The toolkit is code. Your job search — CVs, applications,
company research, the tracker database — lives in a separate directory you choose,
outside this repo. Nothing personal is ever committed here.

> **Platforms: macOS and Linux.** Windows is out of scope: the `tools/` scripts are
> bash. It may work under WSL; nothing is built or tested for it.

---

## Quick start

```bash
git clone <this repo> jobstudio && cd jobstudio
```

**1. A virtualenv** (Python >=3.11). Either works — what matters is knowing the path to
its `python`, because step 2 needs it.

<details open>
<summary><b>Plain <code>venv</code></b></summary>

```bash
python3 -m venv ~/.venvs/jobstudio
~/.venvs/jobstudio/bin/python -m pip install -e .
# interpreter path: ~/.venvs/jobstudio/bin/python
```
</details>

<details>
<summary><b><code>virtualenvwrapper</code></b> (<code>mkvirtualenv</code> / <code>workon</code>)</summary>

```bash
mkvirtualenv -p python3 jobstudio     # creates it and activates it
pip install -e .                      # goes into the new env

# interpreter path: $WORKON_HOME/jobstudio/bin/python
# ($WORKON_HOME is ~/.virtualenvs by default; ~/Envs on some setups)
python -c 'import sys; print(sys.executable)'   # prints it, while activated
```
</details>

**2. Create a data root and wire this checkout to it.** `--from-example` populates it
with a complete fictional job search, so there is something to look at before you put
your own in. Substitute your interpreter path from step 1:

```bash
<python> src/jobsinit.py \
    --data-root ~/Dropbox/jobstudio-data --from-example \
    --venv-python <python>
```

**3. From here on, go through the generated wrapper:**

```bash
tools/py src/jobsdb.py status
tools/run-dev-local-db          # the web app, http://127.0.0.1:8010
```

**Signing in.** Browsing needs no login; *editing* happens in the Django admin at
`/admin/`, and `init` creates an account for it — **`admin` / `admin`** by default. The
example dataset ships no account of its own, deliberately: a public repo should not
carry a password hash.

That default is fine while the server stays on `127.0.0.1`, which is where
`tools/run-dev-local-db` puts it. Change it before that stops being true:

```bash
tools/py src/web/manage.py changepassword admin
```

To set your own at install time, or skip the account entirely:

```bash
JOBSTUDIO_ADMIN_PASSWORD='…' <python> src/jobsinit.py … --admin-user <name>
<python> src/jobsinit.py … --no-admin
```

There is no `--admin-password` flag on purpose — a flag lands in shell history and in
the process list.

> **Why `tools/py` rather than activating the environment.** `init` writes `tools/py`
> as a wrapper that `exec`s your interpreter directly, so every script and every Claude
> Code session reaches the right Python without an activated shell. That matters for the
> agent especially: activation does not survive between commands, so a session that
> relied on `workon` would silently fall back to the system Python. Use `mkvirtualenv`
> and `workon` freely in your own terminal — just point `--venv-python` at the
> interpreter, and let `tools/py` do the rest.

Then open a Claude Code session in the repo and run `/jobstudio help`.

To start with your own data instead of the example, run `/jobstudio init` from a
Claude Code session — it asks where the data should live and how you want to begin:
from an existing CV, from public information it looks up about you, or from a blank
interview.

Check the install at any time with `tools/smoke-test`, which clones the repo into a
temp directory, runs `init` from scratch and exercises the pipeline end to end.

## What it does

| Command | |
|---|---|
| `/jobstudio init` | First-run setup: create a data root and wire this checkout to it |
| `/jobstudio company` | Track a company to watch, with researched notes |
| `/jobstudio application` | Log an application: folder, gap analysis, tailored CV, cover letter |
| `/jobstudio cv` | Tailor a CV to a role, or rebuild/import your base CVs |
| `/jobstudio cover-letter` | Draft a cover letter from the application, CV and company notes |
| `/jobstudio stocktake` | Guided interview that builds your career profile |
| `/jobstudio interview` | Prep for a real interview: likely questions, STAR-grounded answers |
| `/jobstudio scan` | Scan tracked companies' ATS boards for new postings and score them |
| `/jobstudio status` | Where everything stands |

Plus a local Django app for browsing applications, companies, CVs and scan reports, and
an optional static-site export.

## How it is laid out

Two directories, deliberately:

```
jobstudio/                 # this repo — the code. Public, shareable, no personal data.
├── .claude/skills/jobstudio/   # the skill: SKILL.md + one file per subcommand
├── src/                          # pipeline scripts + the Django app
├── tools/                        # shell entry points
├── example-data/                 # a complete fictional job search, and the test fixture
└── docs/                         # how each piece works

<your data root>/            # your job search. Private, and yours.
├── config.yaml                   # who you are
├── jobs/                         # CVs, profile, companies, applications, scans
│   └── scan-config.yaml          # your ATS overrides + category→area mapping
├── exports/                      # generated .docx / .html / .pdf
├── backups/django/               # timestamped database dumps
└── db.sqlite3                    # the tracker
```

`init` writes the link between them (`.jobstudio-data` here, `~/.jobstudio.ini` in your
home directory) along with a `tools/py` wrapper and, if you use them, a VS Code
workspace covering both folders.

Put the data root in a synced folder (Dropbox, Drive, iCloud). Nothing in it is
version-controlled, so the sync service is your backup — and `tools/db-dump` writes
timestamped snapshots alongside it.

## Configuration

Five files, and each one lives next to what it configures rather than in a single
`config/` drawer — the data root is organised by topic, not by file kind.

| File | What it controls | When you'd edit it |
|---|---|---|
| `<data>/config.yaml` | Identity — who the search belongs to; used in generated filenames and documents | Once, at setup. `init` writes it |
| `<data>/jobs/targets/<area>.yaml` | One **target area**: a CV positioning, with the emphasis bullets and key terms that tailor a CV and score a scan | Whenever you add or rethink a kind of role you're going after |
| `<data>/jobs/profile/criteria.yaml` | What you'll accept — dealbreakers, salary floor, weighted motivators, sectors. Pairs with `stocktake.md` | After `/jobstudio stocktake`, or when your bar moves |
| `<data>/jobs/scan-config.yaml` | Scanning: ATS overrides for companies whose careers URL hides the real board, category → area mapping, and why a company isn't scanned | When a tracked company shows up "not scanned" but does have an ATS |
| `~/.jobstudio.ini` | Per-machine, not per-search: where the data root is, plus optional `chrome_path` (PDF export), `open_command` (`open` / `xdg-open`) and `editor_url_scheme` (the "Open in VS Code" links) | Moving the data root, or on a machine where Chrome isn't where the toolkit expects |

**None of them is strictly required, but your name has to come from somewhere.** If
`config.yaml` is absent, identity falls back to the `# Name` heading of your base
functional CV; if neither names a person, anything that generates a file stops with a
clear error rather than guessing. The rest degrade quietly: no target areas means no
per-area tailoring, no `criteria.yaml` means scans score on role fit alone, and no
`scan-config.yaml` means the scanner detects each company's ATS from its careers URL and
nothing more.

## Developing

```bash
tools/py src/web/manage.py test tracker cvs   # the test suite, against example-data/
tools/smoke-test                              # from-scratch install, in a temp clone
tools/build-example-fixture                   # regenerate the example database fixture
```

Tests run against `example-data/`, never against a real job search.

## Licence

MIT — see `LICENSE`.

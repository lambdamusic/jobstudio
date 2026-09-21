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
| `<repo>/jobstudio.code-workspace` | one VS Code window over both folders |
| `<repo>/src/web/local_settings.py` | copied from the example, if missing |
| a Django admin account | `admin`/`admin` by default, or your own via `--admin-user` + `$JOBSTUDIO_ADMIN_PASSWORD`; `--no-admin` skips it |

All gitignored except the workspace file. Re-running is safe: it adds what is missing
and leaves the rest alone. Nothing is overwritten without `--force`, and there is no
wipe mode — this points at a directory holding someone's whole job search.

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

## Afterwards

Confirm it worked by running `/jobstudio status`, then say what is next: `stocktake`
for an empty start, or just browsing for the example. Mention that
`tools/smoke-test` re-runs the whole thing from a clean clone if they ever want to
check the install.

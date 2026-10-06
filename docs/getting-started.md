# Getting started

Part of the **[docs/](README.md)** guide collection. The
[README](../README.md#quick-start)'s quick start is the short version — clone, run
`/jobstudio init`, answer its questions. This file is everything around it: doing the
same setup by hand, signing in, what to do once it is running, the web app, the
configuration files, and the checks to run if you are changing the code.

Once you are set up, **[workflow.md](workflow.md)** is where to go next.

---

## Setting it up by hand

The same three steps `init` performs, if you would rather not hand setup to an agent,
or you are debugging one of them.

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
tools/py src/config.py --chain  # which layer resolved the data root, and to what
tools/py src/jobsdb.py status   # should say "3 applications tracked" for the example
tools/run-dev-local-db          # the web app, http://127.0.0.1:8010
```


## Signing in

Browsing needs no login; *editing* happens in the Django admin at `/admin/`, and
`init` creates an account for it — **`admin` / `admin`** by default. The
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

## Once it is running

`/jobstudio help` lists the subcommands. If you started from the example, browse it
first — the web app, a company page, a logged application — then re-run
`/jobstudio init` when you want your own data in. Starting from the example and
starting for real are the same command; the second run just picks a different on-ramp.

Check the install at any time with `tools/smoke-test`, which clones the repo into a
temp directory, runs `init` from scratch and exercises the pipeline end to end.

## The web app

The skill writes; the web app is how you read. Everything the subcommands produce —
applications, companies, tailored CVs, cover letters, scan reports — is browsable, and
it is the fastest way to see where a search actually stands.

```bash
tools/run-dev-local-db          # http://127.0.0.1:8010
```

Runs on `127.0.0.1` only, in the foreground, until Ctrl-C. Browsing needs no login;
*editing* happens in the Django admin at `/admin/` (see **Signing in** above). If 8010
is busy, pass another port: `tools/run-dev-local-db 8020`.

`tools/site-build` renders the same content as a static site you can host or keep as a
snapshot.

## Configuration

Five files, and each one lives next to what it configures rather than in a single
`config/` drawer — the data root is organised by topic, not by file kind.

| File | What it controls | When you'd edit it |
|---|---|---|
| `<data>/config.yaml` | Identity — who the search belongs to; used in generated filenames and documents | Once, at setup. `init` writes it |
| `<data>/jobs/targets/<area>.yaml` | One **target area**: a CV positioning, with the emphasis bullets and key terms that tailor a CV and score a scan | Whenever you add or rethink a kind of role you're going after |
| `<data>/jobs/profile/criteria.yaml` | What you'll accept — dealbreakers, salary floor, weighted motivators, sectors. Pairs with `stocktake.md` | After `/jobstudio stocktake`, or when your bar moves |
| `<data>/jobs/scan-config.yaml` | Scanning: ATS overrides for companies whose careers URL hides the real board, category → area mapping, and why a company isn't scanned | When a tracked company shows up "not scanned" but does have an ATS |
| `~/.jobstudio.ini` | Per-machine, not per-search: where the data root is, plus optional `open_command` (`open` / `xdg-open`) and `editor_url_scheme` (the "Open in VS Code" links) | Moving the data root |

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
tools/make-public-tree --check                # refuse-to-publish check, nothing written
tools/build-example-fixture                   # regenerate the example database fixture
```

Tests run against `example-data/`, never against a real job search.

**The publish check.** This repo is public and pushes every branch, so any push is a
publication. `tools/make-public-tree --check` copies what would ship into a temp
directory, greps it for personal data — your name, your private terms, absolute home
paths, credentials in fixtures, and every company name in *your own tracker database* —
and deletes it again. `tools/git-hooks/pre-push` runs it and blocks the push on a hit;
`git config core.hooksPath tools/git-hooks` turns that on, and `init` does it for you
when the checkout has a remote. `git push --no-verify` bypasses it.

The company check derives its terms from your tracker rather than a maintained list, so
it cannot go stale — which also means it only runs locally, since the database is
gitignored and CI cannot see it. Names that are genuinely technology rather than your
search (a vendor whose API you call, say) go in `.tracked-company-exceptions` — see the
`.example`.

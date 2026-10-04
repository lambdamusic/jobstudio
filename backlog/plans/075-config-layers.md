# Config layers — what the data root resolution actually needs

Detail for `#75` in `TODO.md`. Raised 2026-10-02 by Michele, after setting the toolkit
up on a second machine and finding the configuration hard to reason about: *"Shall we
consider simplifying the config settings? Unclear to me now what is needed."*

## What exists today

`src/config.py:19-21` resolves the data root through three layers, most specific first:

| | Layer | Scope | Set by |
|---|---|---|---|
| 1 | `$JOBSTUDIO_DATA` | one shell or command | by hand, and by the test suite |
| 2 | `.jobstudio-data` in the repo root | one checkout | `init` |
| 3 | `~/.jobstudio.ini` | the whole machine | `init`, unless `--skip-global` |

`SKILL.md:84-99` tells an agent to ask `config.py --path` first and to read the `.ini`
directly **only if no repo is reachable**, with a warning that getting the order
backwards means operating on the wrong person's data root.

## The finding that reframes the question

**The `.ini` is doing two unrelated jobs, and only one of them is duplicated.**

- `data_root` — covered by layers 1 and 2 whenever a repo is in the picture.
- `chrome_path`, `editor_url_scheme`, `open_command` — read through `config.setting()`
  (`config.py:96`) by `render.py:741`, `context_processors.py:26`, `admin.py:44` and
  `views.py:1126`. These are genuinely per-machine, have no other layer, and exist
  precisely so that supporting another platform is data rather than ten `sys.platform`
  branches.

So "do I need the `.ini`?" has two different answers depending on which half is meant,
and the file gives no hint that it holds two kinds of thing. That is most of the
confusion, and it is fixable without removing anything.

## The second finding: layer 3's data-root branch is close to unreachable

`SKILL.md` step 2 fires only when **no repo is reachable**. But the skill lives at
`.claude/skills/jobstudio/` and is a *project* skill — Claude Code loads it from the
directory the session starts in, and there is no user-level copy installed. So a session
started outside the repo has no `/jobstudio` at all, and never reaches the step that
would read the `.ini`.

The branch is therefore reachable by a bare script run (`tools/py src/...` from
elsewhere) but, as written, not by the skill whose instructions describe it.

That is a docs-versus-reality gap, not a bug: the code is right to have the layer, and a
user-level install of the skill would make it live. But `SKILL.md` currently documents a
fallback that the way the skill is installed makes almost impossible to hit.

## What the second machine showed

The setup there has two data roots on one machine — a second person's, and the example
one. That is the case the layering handles **well**: with no `.ini`, a session started
outside a checkout stops and says to run `init`, rather than quietly acting on whichever
root a machine-wide default happened to name. The safe failure is the current behaviour,
and it argues for keeping layer 2 beating layer 3.

The conclusion drawn on that machine — skip the `.ini` entirely — is right for its
*data root* and wrong, or at least untested, for `editor_url_scheme` and friends, which
simply fall back to their defaults.

## Options, not yet decided

1. **Change nothing in the code; fix what the files say.** Split the `.ini` in the docs
   into "the data root, which you probably do not need here" and "per-machine settings,
   which you might". Say in `SKILL.md` that step 2 is for script runs, not for the skill.
   Cheapest, and it addresses the actual complaint, which was comprehension.
2. **Have `init` write an `.ini` with the settings but no `data_root`** unless asked, so
   the common machine gets the useful half and not the dangerous half. `--skip-global`
   then becomes "no `.ini` at all" rather than the only way to avoid a machine-wide root.
3. **Install the skill at user level** (`~/.claude/skills/`), which makes layer 3 real
   and the documented fallback true. Needs testing: the skill's first step runs
   `src/config.py`, so it has to locate the repo from wherever the session started.
   Bigger than this item — it is `#57`/`#2` territory.
4. **Drop `data_root` from the `.ini`.** Honest and simplifying, but it removes the only
   answer for "run a script from outside any checkout", which is a real thing scripts do.
   Weigh against option 2, which keeps the capability and changes the default.

## Out of scope

Anything about how the skill is distributed or installed (`#57`), and the per-machine
settings' own contents — `chrome_path` and `open_command` are working as intended and
are not what prompted this.

# The chat panel

**Ask Claude**, at the top of the web app's sidebar (or **⌘K** / Ctrl+K from any page),
opens a chat drawer on the right. It talks to the same Claude Code you would open in a
terminal in this repo: the `jobstudio` skill and `CLAUDE.md`, your global
`~/.claude` settings and memory, and your data root. So "log this posting", "what's
next on 001-grafana-labs?" or `/jobstudio status` work from there as they do in the
terminal.

It needs Claude Code installed and signed in (`claude` on the PATH). Without it the
button does not appear.

## How it works

There is no API key and no SDK. Each message runs one **headless Claude Code turn**,
`claude -p`, as a subprocess of the web app:

- **from the repo root**, so the project's `CLAUDE.md` and `.claude/skills/` load
- **with the data root added** (`--add-dir`), and `$JOBSTUDIO_DATA` set to the same
  root the app is using, so pointing the server at scratch data points the chat there
  too
- **chained with `--resume <session id>`**, so each message continues the same
  conversation

It runs on whatever account the terminal's `claude` is signed into: a Claude
subscription counts against that plan's usage, not an API bill.

The output is Claude Code's `stream-json`, which the server (`src/web/apps/tracker/
chat.py`) boils down to a handful of events and streams to the page as it arrives.
Each message Claude writes is its own bubble, rendered with the site's markdown once it
is finished; each tool it runs is a `⚙` line between them, in the order they ran.

Every message also says which page you are on, and Claude is told how the app's URLs
map to files, so "what's the next step here?" means the application you are looking at.

## Permissions: Allow & retry

A headless run cannot show you a permission prompt, so anything your settings files do
not already allow is **refused** rather than asked. When that happens the turn ends with
a card listing what was refused, as the narrowest rule that would allow it:

| Refused | Rule offered |
|---|---|
| a shell command | `Bash(<that exact command>)` |
| reading, editing or writing a file | `Read(//<path>)`, `Edit(//<path>)`, `Write(//<path>)` |
| fetching a page | `WebFetch(domain:<host>)` |
| any other tool | the tool's name |

**Allow & retry** grants those rules and asks Claude to try again. Granted rules last
for the rest of that conversation in the panel and are sent with every later message;
they are never written to a settings file. **New** forgets them.

The permission mode is a setting, `CHAT_PERMISSION_MODE` in `local_settings.py`:

- `"default"` (the default): file edits are refused too, so every change to your data
  arrives as a card you allow, one file at a time
- `"acceptEdits"`: edits go through without asking, as they would in a terminal session
  started with that mode; shell commands and reads outside the allowed folders still
  come back as cards

## The usage bar

Under the panel's header, updated after every turn:

- **Context**: tokens the next turn starts from, against the model's context window.
  A fresh conversation already starts at a few tens of thousands — that is what Claude
  Code loads up front.
- **5h** and **Week**: your plan's usage windows, as Claude Code's `/usage` reports
  them. Hover for when each resets.
- **Chat**: the conversation's API-price equivalent so far. Not billed on a
  subscription; a measure of how heavy the conversation has been.

A figure past 80% turns gold.

## Conversations

The transcript, the session id and the rules you have allowed are kept in the browser
tab (`sessionStorage`), so the conversation follows you from page to page. The session
itself lives in Claude Code's own store: hover the id in the panel header for the
command that resumes it in a terminal, `claude --resume <id>`.

One reply at a time per conversation: a second tab sending on the same conversation
while a reply is in progress gets an error rather than a second, overlapping turn.

## Settings

| Setting | Default | |
|---|---|---|
| `CHAT_ENABLED` | on when `claude` is on the PATH | `False` hides the button and turns the endpoint off |
| `CHAT_PERMISSION_MODE` | `"default"` | Claude Code's `--permission-mode` for every turn |

Both go in `src/web/local_settings.py`.

## Limits

- **Each turn starts a process.** A few seconds pass before the first word, even for a
  short question.
- **Local only.** The endpoint refuses any request not from this machine: it hands a
  shell-capable agent to whoever can reach it.
- **The panel width** is yours to drag (its left edge; double-click resets it), and is
  remembered per browser.

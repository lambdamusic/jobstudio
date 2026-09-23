# Any status can be set from the application page

**Date:** 2026-09-23 (continues `log/2026-09-23-cvs-page-tailored-list.md`)
**Session focus:** `#28` — replacing the single hardcoded "Mark reviewing" action.

**Headline:** The page had one status action out of seven, chosen months ago because it
was the one being used that week. The other six all meant opening the Django admin. It
now has a menu of all of them.

---

## The shape decision

The TODO left this open deliberately: a dropdown, a row of small buttons, or a
`<select>` + Go. Michele picked the dropdown.

A row of six always-visible buttons was the tempting one — one click instead of two —
but the actions row already carries four buttons, and six more would wrap to a second
line on any narrow window. The menu keeps the row at its current width and costs one
click.

`<details>`/`<summary>` rather than a scripted dropdown: it opens and closes natively,
so the menu still works with JavaScript off. That is the same bargain `tabs.js` already
makes on this page, and it matters here for the same reason — the published mirror is a
plain file mirror with no server behind it.

## What changed

- `views.mark_reviewing` → `views.set_status(request, num, status)`, at
  `/actions/set-status/<num>/<status>/`. Still behind the `ENVIRONMENT == "local"`
  guard, still saving through `Application.save()` so `status_order` and the post-save
  History log behave exactly as they do for an admin edit.
- The status is **validated against `STATUS_SORT_ORDER`, not trusted**. It now arrives
  from the URL rather than being a constant in the view, so it is input: an unknown
  value 404s instead of writing a status the rest of the app has no handling for.
- `application_detail` passes `other_statuses` — the list minus the current one, so the
  menu never offers a no-op.
- `.menu` / `.menu-body` in `site.css`: the panel is absolutely positioned against the
  `<details>`, so opening it does not reflow the row beneath.

## One thing that looked like a bug and wasn't

The first in-browser check showed the menu rendering *inline* — badges in a row, the
actions row growing taller, no panel. That looked like `position: absolute` failing on a
flex item. It was the browser serving a cached `site.css`; the dev server was already
serving the new rules (`curl | grep menu-body` confirmed three hits). A hard reload
rendered it correctly. Worth remembering before debugging CSS that is already correct.

## Checks

`manage.py test tracker cvs` — 94 green, 4 new covering the two things the generalisation
could break: every status settable, an unknown one refused without writing, the History
log still written, and the menu never offering the current status. `tools/smoke-test` —
SMOKE PASS. Verified end to end in the browser against the `jobstudio-devdata` scratch
root: menu opens, `applied → reviewing` applies, sidebar counts update, History tab shows
the transition. Scratch data set back to `applied` afterwards.

## Also updated

`src/web/README.md`'s local-only list, which documented Open folder and Open in VS Code
but would have left the new action undocumented; and `backlog/share-as-toolkit-plan.md`
§8.3, which cited `/actions/mark-reviewing/<num>/` as the precedent for agent-run
buttons — that URL no longer exists.

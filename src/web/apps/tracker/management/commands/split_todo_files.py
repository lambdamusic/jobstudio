"""One-off: move each application's `## To do` out of notes.md into its own todo.md.

Per folder this:

- writes todo.md: a `# To do` title, then the section's text unchanged except that each
  heading moves up a level (`### Domain` becomes `## Domain`), which gives the To do tab
  its jump index;
- removes the section from notes.md, leaving the rest of the file as it was;
- points the links at it to the new tab: `#notes--<heading>` becomes `#todo--<heading>`,
  in the folder's files and as `/applications/N/#notes--<heading>` anywhere under jobs/;
- updates the wording of each round file's `## To do`, the one line linking its tasks.

A folder with no `## To do` in notes.md, or that already has a todo.md, is skipped.

Reports what it would do and changes nothing unless `--apply` is passed. Safe to re-run.

    manage.py split_todo_files            # show the plan
    manage.py split_todo_files --apply    # rewrite the files
"""

from __future__ import annotations

import re
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

import appfolder
from tracker.parsers import _is_fence, split_sections

_SECTION = re.compile(r"^## To do[ \t]*$")
_HEADING = re.compile(r"^(#{1,6}) ")
_ROUND_TODO = re.compile(r"(?ms)^## To do[ \t]*\n.*?(?=^## |\Z)")


def take_todo(notes: str) -> tuple[str, str] | None:
    """(notes.md without the section, the section's body), or None without one."""
    lines = notes.splitlines(keepends=True)
    in_fence, start, end = False, None, len(lines)
    for i, line in enumerate(lines):
        if _is_fence(line.strip()):
            in_fence = not in_fence
        elif not in_fence:
            m = _HEADING.match(line)
            if start is None:
                if _SECTION.match(line.rstrip("\n")):
                    start = i
            elif m and len(m[1]) <= 2:
                end = i
                break
    if start is None:
        return None
    before = "".join(lines[:start]).rstrip("\n")
    after = "".join(lines[end:])
    rest = (before + "\n\n" if before else "") + after
    return rest, "".join(lines[start + 1:end]).strip("\n")


def promote(body: str) -> str:
    """Each heading up one level, outside code fences."""
    out, in_fence = [], False
    for line in body.split("\n"):
        if _is_fence(line.strip()):
            in_fence = not in_fence
        elif not in_fence and re.match(r"^#{3,6} ", line):
            line = line[1:]
        out.append(line)
    return "\n".join(out)


def anchors(doc: str) -> set[str]:
    return {s["anchor"] for b in split_sections(doc)["blocks"]
            for s in [b, *b["subsections"]]}


def moved_anchors(notes: str, todo: str) -> dict[str, str]:
    """Old anchor under `#notes--` to its new one under `#todo--`. Paired by position,
    because a repeated heading's anchor depends on what comes before it."""
    block = next(b for b in split_sections(notes)["blocks"] if b["anchor"] == "to-do")
    new = [b["anchor"] for b in split_sections(todo)["blocks"]]
    return dict(zip((s["anchor"] for s in block["subsections"]), new))


def retarget_round(text: str) -> str:
    """A round file's `## To do` is one line about where its tasks are: say so afresh."""
    def fix(m):
        s = re.sub(r"\[This round's tasks[^\]]*\]\(#notes--", "[This round's tasks](#todo--", m[0])
        s = re.sub(r"My\s+notes", "To do", s)
        return re.sub(r"notes\.md", "todo.md", s)
    return _ROUND_TODO.sub(fix, text)


def plan_folder(folder: Path) -> dict | None:
    notes_path = folder / "notes.md"
    if (folder / "todo.md").exists() or not notes_path.is_file():
        return None
    notes = notes_path.read_text()
    taken = take_todo(notes)
    if taken is None:
        return None
    rest, body = taken
    todo = f"# To do\n\n{promote(body)}\n"
    mapping = moved_anchors(notes, todo)
    changed_anchors = (anchors(notes) - set(mapping) - {"to-do"}) ^ anchors(rest)
    return {"notes": rest, "todo": todo, "mapping": mapping, "drifted": changed_anchors}


def rewrite_links(text: str, mapping: dict[str, str], prefix: str) -> str:
    """`<prefix>#notes--<old>` to `<prefix>#todo--<new>`, for the moved headings only."""
    def fix(m):
        if m[1] == "to-do":
            return f"{prefix}#todo"
        return f"{prefix}#todo--{mapping[m[1]]}" if m[1] in mapping else m[0]
    return re.sub(rf"{re.escape(prefix)}#notes--([\w-]+)", fix, text)


class Command(BaseCommand):
    help = "Move each application's `## To do` out of notes.md into its own todo.md."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true",
                            help="Actually rewrite the files (default: show the plan only).")

    def handle(self, *args, **options):
        apply = options["apply"]
        jobs = Path(settings.DATA_ROOT) / "jobs"
        apps_dir = jobs / "applications"
        if not apps_dir.is_dir():
            self.stderr.write(self.style.ERROR(f"No application folders at {apps_dir}"))
            return

        plans = {}
        for folder in sorted(p for p in apps_dir.iterdir() if p.is_dir()):
            plan = plan_folder(folder)
            if plan:
                plans[folder] = plan
                note = f"  ANCHORS CHANGED: {sorted(plan['drifted'])}" if plan["drifted"] else ""
                self.stdout.write(f"  {folder.name}/  {len(plan['mapping'])} heading(s){note}")

        writes: dict[Path, str] = {}
        for folder, plan in plans.items():
            writes[folder / "notes.md"] = plan["notes"]
            writes[folder / "todo.md"] = plan["todo"]

        def current(path):
            return writes[path] if path in writes else path.read_text()

        # In the folder, a bare anchor; anywhere, a full link to the application's page.
        for folder, plan in plans.items():
            for path in [*folder.glob("*.md")]:
                text = old = current(path)
                if appfolder.is_interview_filename(path.name):
                    text = retarget_round(text)
                text = rewrite_links(text, plan["mapping"], "")
                if text != old:
                    writes[path] = text
        by_num = {int(f.name[:3]): plan for f, plan in plans.items() if f.name[:3].isdigit()}
        for path in jobs.rglob("*.md"):
            text = old = current(path)
            for num in {int(n) for n in re.findall(r"/applications/(\d+)/#notes--", text)} & set(by_num):
                text = rewrite_links(text, by_num[num]["mapping"], f"/applications/{num}/")
            if text != old:
                writes[path] = text

        created = sum(p.name == "todo.md" for p in writes)
        summary = f"{created} todo.md, {len(writes)} file(s) in all"
        if not plans:
            self.stdout.write(self.style.HTTP_NOT_MODIFIED("Nothing to move."))
        elif apply:
            for path, text in writes.items():
                path.write_text(text)
            self.stdout.write(self.style.SUCCESS(f"{summary} written"))
        else:
            self.stdout.write(self.style.WARNING(
                f"{summary} to write. Nothing was written — re-run with --apply."))

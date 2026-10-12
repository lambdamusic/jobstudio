"""One-off: gather each application's to-dos into one `## To do` section of notes.md.

Since 2026-10-08 every task for an application lives first in its `notes.md`, split by
stage (TODO #84): `### Application` for what comes before any interview, then one
`### <Round label> — <YYYY-MM-DD>` per round, which the round file links to. Before that
they were scattered: the gap analysis's `### Preparation steps` under `## My notes`, and
each interview round's own `## Study before`.

Per folder this:

- moves the body of `### Preparation steps` (any heading starting so) into
  `### Application`;
- moves each round file's `## Study before` body into that round's subsection, rounds
  oldest first, and leaves `## To do` in the round file holding one link to it;
- turns a top-level list item with no checkbox into a task — `- Read…` into
  `- [ ] Read…`, `1. Read…` into `1. [ ] Read…`. A number stays, so a reference
  elsewhere to "step 4" still points at the right one. Nothing else in the moved text is
  reworded;
- puts `## To do` before the first `##` heading of notes.md, after any title and
  preamble line.

A folder whose notes.md already has `## To do` is skipped whole: it has been migrated, or
was written in the new shape. A round with no `## Study before` gets no subsection — an
empty heading would be a promise of tasks that do not exist.

Reports what it would do and changes nothing unless `--apply` is passed. Safe to re-run.

    manage.py migrate_todos            # show the plan
    manage.py migrate_todos --apply    # rewrite the files
"""

from __future__ import annotations

import re
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

import appfolder
from tracker.parsers import parse_date, section_slug

TODO_HEADING = "## To do"
_ITEM_NO_BOX = re.compile(r"^([-*+]|\d+[.)])[ \t]+(?!\[[ xX]\][ \t])")


def _is_fence(line: str) -> bool:
    s = line.strip()
    return s.startswith("```") or s.startswith("~~~")


def take_section(text: str, heading_re: str, level: int) -> tuple[str, str | None, str]:
    """Cut the first section whose heading matches `heading_re` out of `text`.

    A section runs to the next heading of the same level or higher. Returns
    (text before, the section's body or None if absent, text after) — the heading line
    itself belongs to neither side.
    """
    lines = text.splitlines(keepends=True)
    pattern = re.compile(heading_re)
    in_fence = False
    start = end = None
    for i, line in enumerate(lines):
        if _is_fence(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = re.match(r"^(#{1,6}) ", line)
        if start is None:
            if m and len(m.group(1)) == level and pattern.match(line.strip()):
                start = i
        elif m and len(m.group(1)) <= level:
            end = i
            break
    if start is None:
        return text, None, ""
    end = len(lines) if end is None else end
    return "".join(lines[:start]), "".join(lines[start + 1:end]).strip("\n"), "".join(lines[end:])


def as_tasks(body: str) -> str:
    """Top-level list items without a checkbox become tasks: `- x` → `- [ ] x`,
    `1. x` → `1. [ ] x`. Indented lines are an item's detail and stay as they are."""
    out, in_fence = [], False
    for line in body.splitlines():
        if _is_fence(line):
            in_fence = not in_fence
        elif not in_fence:
            line = _ITEM_NO_BOX.sub(r"\1 [ ] ", line)
        out.append(line)
    return "\n".join(out)


def round_heading(path: Path) -> str:
    """`<Round label> — <date>`, as the skill writes it (SKILL.md, "Lists of things to do
    are checklists")."""
    label = appfolder.interview_label(appfolder.interview_stage(path.name))
    d = parse_date(path.name)
    return f"{label} — {d.isoformat()}" if d else label


def plan_folder(folder: Path) -> dict | None:
    """What migrating one folder would write, or None when there is nothing to do."""
    notes_path = folder / "notes.md"
    notes = notes_path.read_text() if notes_path.exists() else ""
    if re.search(r"^## To do\s*$", notes, re.M):
        return None

    before, prep, after = take_section(notes, r"^### Preparation steps", 3)
    notes_rest = before.rstrip("\n") + "\n\n" + after.lstrip("\n") if prep is not None else notes

    rounds = sorted((p for p in folder.iterdir()
                     if p.is_file() and appfolder.is_interview_filename(p.name)),
                    key=lambda p: (parse_date(p.name) or parse_date("0001-01-01"), p.name))
    subsections: list[tuple[str, str]] = []
    round_writes: dict[Path, str] = {}
    for path in rounds:
        text = path.read_text()
        r_before, study, r_after = take_section(text, r"^## Study before\s*$", 2)
        if study is None or not study.strip():
            continue
        heading = round_heading(path)
        link = f"→ [This round's tasks, in My notes](#notes--{section_slug(heading)})"
        round_writes[path] = (r_before.rstrip("\n") + f"\n\n{TODO_HEADING}\n\n{link}\n\n"
                              + r_after.lstrip("\n"))
        subsections.append((heading, as_tasks(study)))

    if prep is None and not subsections:
        return None

    todo = [TODO_HEADING, ""]
    if prep is not None:
        todo += ["### Application", "", as_tasks(prep), ""]
    for heading, body in subsections:
        todo += [f"### {heading}", "", body, ""]
    todo_md = "\n".join(todo).rstrip("\n") + "\n\n"

    # Before the first `##`, outside a fence; the title and any preamble stay above it.
    lines, in_fence, at = notes_rest.splitlines(keepends=True), False, None
    for i, line in enumerate(lines):
        if _is_fence(line):
            in_fence = not in_fence
        elif not in_fence and line.startswith("## "):
            at = i
            break
    if at is None:
        new_notes = notes_rest.rstrip("\n") + "\n\n" + todo_md
    else:
        head = "".join(lines[:at]).rstrip("\n")
        new_notes = (head + "\n\n" if head else "") + todo_md + "".join(lines[at:])

    return {"notes": (notes_path, new_notes), "rounds": round_writes,
            "application": prep is not None, "subsections": [h for h, _ in subsections]}


class Command(BaseCommand):
    help = "Gather each application's to-dos into one `## To do` section of notes.md."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true",
                            help="Actually rewrite the files (default: show the plan only).")

    def handle(self, *args, **options):
        apply = options["apply"]
        apps_dir = Path(settings.DATA_ROOT) / "jobs" / "applications"
        if not apps_dir.is_dir():
            self.stderr.write(self.style.ERROR(f"No application folders at {apps_dir}"))
            return

        folders = rounds = 0
        for folder in sorted(p for p in apps_dir.iterdir() if p.is_dir()):
            plan = plan_folder(folder)
            if plan is None:
                continue
            folders += 1
            parts = (["Application"] if plan["application"] else []) + plan["subsections"]
            self.stdout.write(f"  {folder.name}/  ## To do: {' · '.join(parts)}")
            for path in plan["rounds"]:
                self.stdout.write(f"      Study before → link  {path.name}")
            rounds += len(plan["rounds"])
            if apply:
                path, text = plan["notes"]
                path.write_text(text)
                for path, text in plan["rounds"].items():
                    path.write_text(text)

        if not folders:
            self.stdout.write(self.style.HTTP_NOT_MODIFIED(
                "Nothing to migrate — every notes.md already has a `## To do`."))
            return
        summary = (f"{folders} folder(s), {rounds} round file(s) "
                   f"{'rewritten' if apply else 'to rewrite'}")
        if apply:
            self.stdout.write(self.style.SUCCESS(summary))
        else:
            self.stdout.write(self.style.WARNING(
                f"{summary}. Nothing was written — re-run with --apply."))

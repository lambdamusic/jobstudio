"""Render the whole site to static HTML, without a running server.

Replaces the `runserver` + `wget --mirror` step of the init-django-static-site
methodology. Django's test Client renders each URL in-process, so there is no HTTP, no
port, no crawl delay, and no link rewriting — output is deterministic and takes seconds.

wget's one real advantage is that crawling *discovers* pages; a declarative builder
publishes only what it is told about. That safety net is restored by the link-check pass
at the end: every internal href in the generated HTML must resolve to a file on disk, so a
page we forgot to enumerate fails the build instead of 404ing after publish.

    manage.py build_static                    # -> site/
    manage.py build_static --output /tmp/x    # somewhere safe to inspect first
    manage.py build_static --clean            # drop generated files first
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from urllib.parse import urlparse

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.test import Client

from appfolder import STATUS_SORT_ORDER
from cvs.models import BaseCv
from tracker.models import Application, Area, Company, Scan
from tracker.views import _notes_files

# Files in the output directory that are maintained by hand and must survive a rebuild.
PRESERVE = {"CNAME", ".nojekill", ".nojekyll"}

HREF_RE = re.compile(r'(?:href|src)="([^"]+)"')


def site_urls() -> list[str]:
    """Every URL the published site consists of."""
    urls = ["/", "/applications/", "/applications/all/", "/applications/active/",
            "/companies/", "/areas/", "/cvs/", "/profile/", "/notes/", "/scans/", "/scans/all/"]
    urls += [f"/applications/status/{s}/" for s in STATUS_SORT_ORDER]
    urls += [f"/applications/area/{a}/" for a in Area.objects.values_list("slug", flat=True)]
    urls += [f"/applications/{n}/" for n in Application.objects.values_list("num", flat=True)]
    urls += [f"/companies/{s}/" for s in Company.objects.values_list("slug", flat=True)]
    urls += [f"/cvs/base/{s}/" for s in BaseCv.objects.values_list("slug", flat=True)]
    urls += [f"/scans/{label}/" for label in Scan.objects.values_list("label", flat=True)]
    urls += [f"/notes/{p.stem}/" for p in _notes_files()]
    return urls


class Command(BaseCommand):
    help = "Render the site to static HTML (no server, no wget)."

    def add_arguments(self, parser):
        parser.add_argument("--output", default="site", help="Output directory (default: site)")
        parser.add_argument("--clean", action="store_true",
                            help="Delete previously generated files first")
        parser.add_argument("--skip-link-check", action="store_true")

    def handle(self, *args, **options):
        out = Path(options["output"])
        if not out.is_absolute():
            out = Path(settings.DATA_ROOT) / out
        out.mkdir(parents=True, exist_ok=True)

        # Publish mode hides local-only UI (the admin link, Open folder buttons).
        settings.ENVIRONMENT = "publish"
        # The test Client sends Host: testserver. Django's test runner whitelists that
        # automatically; a management command has to do it itself.
        if "testserver" not in settings.ALLOWED_HOSTS:
            settings.ALLOWED_HOSTS = [*settings.ALLOWED_HOSTS, "testserver"]

        if options["clean"]:
            self._clean(out)

        written = self._render(out)
        self._copy_static(out)

        if not options["skip_link_check"]:
            self._check_links(out, written)

        self.stdout.write(self.style.SUCCESS(
            f"\n{len(written)} pages -> {out}"))

    # ------------------------------------------------------------------
    def _clean(self, out: Path):
        removed = 0
        for entry in out.iterdir():
            if entry.name in PRESERVE:
                continue
            shutil.rmtree(entry) if entry.is_dir() else entry.unlink()
            removed += 1
        self.stdout.write(f"  cleaned {removed} entries (kept {', '.join(sorted(PRESERVE))})")

    def _render(self, out: Path) -> dict[str, Path]:
        client = Client()
        written: dict[str, Path] = {}
        failures = []

        for url in site_urls():
            response = client.get(url)
            if response.status_code != 200:
                failures.append((url, response.status_code))
                continue
            path = out / url.strip("/") / "index.html" if url != "/" else out / "index.html"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(response.content)
            written[url] = path

        if failures:
            for url, code in failures:
                self.stderr.write(self.style.ERROR(f"  {code}  {url}"))
            raise CommandError(f"{len(failures)} page(s) failed to render")

        self.stdout.write(f"  rendered {len(written)} pages")
        return written

    def _copy_static(self, out: Path):
        target = out / settings.STATIC_URL.strip("/")
        if target.exists():
            shutil.rmtree(target)
        count = 0
        for source in settings.STATICFILES_DIRS:
            source = Path(source)
            if not source.is_dir():
                continue
            shutil.copytree(source, target, dirs_exist_ok=True)
            count += sum(1 for _ in source.rglob("*") if _.is_file())
        self.stdout.write(f"  copied {count} static files -> {target.relative_to(out)}/")

    def _check_links(self, out: Path, written: dict[str, Path]):
        """Every internal link must resolve to a file — this is what wget's crawl gave
        us for free, and what a declarative builder would otherwise lose."""
        missing: set[tuple[str, str]] = set()
        for url, path in written.items():
            html = path.read_text()
            for href in HREF_RE.findall(html):
                parsed = urlparse(href)
                if parsed.scheme or parsed.netloc or href.startswith("#"):
                    continue  # external, mailto:, vscode:, file:, anchor
                if "?" in href:
                    missing.add((url, f"{href} (querystring cannot be published)"))
                    continue
                # A fragment (e.g. /areas/#data-platform, deep-linking a tab on another
                # page — tabs.js reads location.hash on load) targets the same file as the
                # bare path; only the path itself needs to resolve to something on disk.
                target = out / parsed.path.strip("/")
                if not (target.is_file() or (target / "index.html").is_file()):
                    missing.add((url, href))

        if missing:
            for page, href in sorted(missing):
                self.stderr.write(self.style.ERROR(f"  broken: {href}  (on {page})"))
            raise CommandError(f"{len(missing)} broken internal link(s)")
        self.stdout.write("  link check: all internal links resolve")

# jobstudio publish

Rebuild the site/ folder from the Django app and sync it to Surge.

## Steps

1. Run the following command from the project root:

```bash
bash tools/publish-surge.sh
```

This runs two steps in sequence:
- `tools/site-build --clean` — re-imports `jobs/*.md` into sqlite (`manage.py import_jobs`), then renders every page to `site/` (`manage.py build_static`). No server needed; takes a couple of seconds.
- `surge site/ <your-domain>` — pushes the site/ folder to the live site

2. Report the result to the user: confirm the site is live at https://<your-domain>/, or surface any errors.

## Notes

- Does not regenerate CV exports — if a base CV changed, re-run `render-html-pdf` for the
  relevant application(s) first.
- Requires `surge` to be installed and authenticated.
- The build fails if any internal link does not resolve; that is intentional, not a flake — it means a page is missing from `site_urls()` in `src/web/apps/tracker/management/commands/build_static.py`.
- Replaced `src/make-docs.py` on 2026-09-07 (retired 2026-09-07).

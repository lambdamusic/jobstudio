# Vendored third-party code

The web app's only runtime dependencies. Everything else here is first-party.

| File | Library | Version | Licence | Source |
|---|---|---|---|---|
| `echarts-6.1.0.min.js` | [Apache ECharts](https://echarts.apache.org/) | 6.1.0 | Apache-2.0 | `https://cdnjs.cloudflare.com/ajax/libs/echarts/6.1.0/echarts.min.js` |
| `mermaid-12.1.0.min.js` | [Mermaid](https://mermaid.js.org/) | 12.1.0 | MIT | `https://cdn.jsdelivr.net/npm/mermaid@12.1.0/dist/mermaid.min.js` |

ECharts: SHA-256 `b66b25aeb4df84e33199dc21694014d336d222cbd9deb0e5a7c14bd6aa0d0fd0`,
1,121,883 bytes, fetched 2026-09-28.

Mermaid: SHA-256 `6484afc32872a3aa16cac9a76ba1816a1ed4cc870a6593cc2e17757750f518b2`,
5,493,176 bytes, fetched 2026-10-05 (cdnjs does not carry 12.x). Loaded on demand by
`js/diagrams.js`, only on a page whose markdown contains a ```mermaid block — at 5MB it
does not belong in every page's `<head>`.

## Why the file is here rather than on a CDN

The published site is a plain file mirror and is meant to work offline. A CDN would also
mean a third-party request every time someone browses their own job search, which is not a
trade anyone asked for. `build_static._copy_static()` already copies every
`STATICFILES_DIRS` tree into `site/`, so a file here ships with the export for free.

## Why ECharts

It covers every chart in `backlog/plans/042-dashboard-charts.md` — Sankey, stacked area, donut,
bar — in one file. The alternative was authoring four chart types by hand on d3, which is
smaller and more controllable but is four times the work for a page that is still being
judged. See the plan's §1.

## Why Mermaid

Diagrams written as text in the markdown files, so the same source renders here, on
GitHub and in an editor preview. Used for the company pages' business diagrams.

## Upgrading

Download the new `echarts.min.js` (or `mermaid.min.js`), record version, size, hash and date above, and check
the page still renders: the charts use `sankey`, `line` (stacked, stepped), `pie`
(donut) and `bar`. Nothing here is patched, so a swap is the whole procedure.

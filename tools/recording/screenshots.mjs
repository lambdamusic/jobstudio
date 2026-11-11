// The stills in docs/images/, one per entry below. Run by tools/record-screenshots,
// which starts the demo server; usage: node screenshots.mjs <base url> <out dir> [name…]
//
// Two kinds of shot. A whole window, sidebar included, for the pages that are about
// layout. A region of the main column for the ones about a single list or chart — the
// region is found from the page's own elements, so it follows the layout if that moves.
import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { launch } from "./cdp.mjs";

const [BASE, OUT, ...ONLY] = process.argv.slice(2);
if (!BASE || !OUT) { console.error("usage: node screenshots.mjs <base url> <out dir> [name…]"); process.exit(2); }

// Regions, evaluated in the page; each returns {x, y, width, height}.
const WINDOW = null;
// The main column, minus some of its padding, from the top of the page down to `height`
// — or, without one, down to whatever is lowest in it.
const column = (height) => `(() => {
  const c = document.querySelector('.content').getBoundingClientRect();
  const bottom = Math.max(...[...document.querySelectorAll('.content-inner *')]
    .map((e) => e.getBoundingClientRect().bottom)) + scrollY + 28;
  return {x: c.left + 12, y: 0, width: c.width - 24, height: ${height ?? "bottom"}}; })()`;
// One section of /stats/: from its heading to the next one.
const section = (id) => `(() => {
  const h = document.getElementById('${id}');
  const all = [...document.querySelectorAll('.content-inner h2')];
  const next = all[all.indexOf(h) + 1];
  const c = document.querySelector('.content-inner').getBoundingClientRect();
  const top = h.getBoundingClientRect().top + scrollY - 24;
  const bottom = next.getBoundingClientRect().top + scrollY - 28;
  return {x: c.left - 24, y: top, width: c.width + 48, height: bottom - top}; })()`;
// An application's tab strip and the open tab under it.
const tabs = (height) => `(() => {
  const t = document.querySelector('[data-tabs]').getBoundingClientRect();
  const c = document.querySelector('.content').getBoundingClientRect();
  return {x: c.left + 12, y: t.top + scrollY - 16, width: c.width - 24, height: ${height}}; })()`;

// Application 4 is the example set's one interviewing application, with two rounds.
const SHOTS = [
  { name: "dashboard", path: "/", size: [1216, 846], clip: WINDOW },
  { name: "application-record", path: "/applications/4/", size: [1216, 848], clip: WINDOW },
  { name: "cvs", path: "/cvs/", size: [1216, 848], clip: WINDOW },
  { name: "stats-at-a-glance", path: "/stats/", size: [1216, 780], clip: WINDOW },
  { name: "applications-list", path: "/applications/status/interviewing/", size: [1216, 900], clip: column() },
  // Wider, so the companies table fits without its last columns cut off.
  { name: "companies-list", path: "/companies/", size: [1400, 900], clip: column(838) },
  { name: "application-interviews", path: "/applications/4/", size: [1216, 1400],
    before: "document.querySelector('[data-tab=interviews]').click()", clip: tabs(825) },
  { name: "stats-status-flow", path: "/stats/", size: [1216, 900], clip: section("flow") },
  { name: "stats-tracked-vs-applied", path: "/stats/", size: [1216, 900], clip: section("companies") },
  { name: "stats-status-over-time", path: "/stats/", size: [1216, 900], clip: section("stock") },
];

const page = await launch();
try {
  for (const s of SHOTS.filter((s) => !ONLY.length || ONLY.includes(s.name))) {
    await page.viewport(...s.size);
    await page.go(BASE + s.path, 1500);
    if (s.before) { await page.js(s.before); await new Promise((r) => setTimeout(r, 400)); }
    let clip = s.clip && (await page.js(s.clip));
    if (clip) clip = Object.fromEntries(Object.entries(clip).map(([k, v]) => [k, Math.round(v)]));
    writeFileSync(join(OUT, `${s.name}.png`), await page.png(clip));
    console.log(`  ${s.name}.png  ${clip ? `${clip.width}x${clip.height}` : s.size.join("x")}`);
  }
} finally {
  await page.close();
}

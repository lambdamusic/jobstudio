// docs/images/quick-intro.gif: a scripted tour of the app, encoded as a GIF. Run by
// tools/record-intro, which starts the demo server; usage: node intro.mjs <base url> <out.gif>
//
// One frame per step, each with the time it stays on screen, rather than a screen
// recording: every frame is sharp, the timing is the script's, and there is no browser
// chrome or pointer. The window is 1232x944 CSS px drawn at half scale, so frames come
// out 616x472 — the size the README has always shown.
//
// Encoding: `sips` turns each PNG into a GIF frame, `gifsicle` joins them with their
// delays. 128 colours, not fewer: at 64 the charts' ribbons band, and below that the
// body text picks up dithering (CHANGELOG, 2026-10-01). `-O3` stores each frame as its
// difference from the last, which is where nearly all the saving is on a flat UI.
import { execFileSync } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { launch, sleep } from "./cdp.mjs";

const [BASE, OUT] = process.argv.slice(2);
if (!BASE || !OUT) { console.error("usage: node intro.mjs <base url> <out.gif>"); process.exit(2); }

const work = mkdtempSync(join(tmpdir(), "jobstudio-intro-"));
const frames = []; // [gif file, delay in centiseconds]
const page = await launch();

async function frame(seconds) {
  const png = join(work, `${String(frames.length).padStart(4, "0")}.png`);
  writeFileSync(png, await page.png());
  const gif = png.replace(/\.png$/, ".gif");
  execFileSync("sips", ["-s", "format", "gif", png, "--out", gif], { stdio: "ignore" });
  frames.push([gif, Math.round(seconds * 100)]);
}
const go = (path) => page.go(BASE + path);
// Scroll to y over `steps` frames, eased in and out, 80ms a frame.
async function scrollTo(y, steps = 14) {
  const from = await page.js("scrollY");
  const to = Math.min(y, await page.js("document.documentElement.scrollHeight - innerHeight"));
  for (let i = 1; i <= steps; i++) {
    const t = i / steps;
    const ease = t < 0.5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2;
    await page.js(`scrollTo(0, ${Math.round(from + (to - from) * ease)})`);
    await sleep(30);
    await frame(0.08);
  }
}
const heading = (id) => page.js(
  `Math.round(document.getElementById('${id}').getBoundingClientRect().top + scrollY - 24)`);
async function tab(name) {
  await page.js(`document.querySelector('[data-tab="${name}"]').click()`);
  await sleep(500);
}

try {
  await page.viewport(1232, 944, 0.5);

  // The stops the README's caption names, in its order.
  await go("/");                          await frame(3.0);
  await scrollTo(520);                    await frame(2.5);

  await go("/applications/all/");         await frame(3.0);
  await scrollTo(400);                    await frame(2.0);

  // Application 1 is the example set's one application with a tailored CV.
  await go("/applications/1/");           await frame(3.0);
  await tab("cv");                        await frame(2.5);
  await scrollTo(500);                    await frame(2.5);

  await go("/areas/");                    await frame(3.0);
  await tab("developer-advocacy");        await frame(2.5);

  await go("/stats/");                    await frame(2.5);
  await scrollTo(await heading("ageing"));    await frame(2.0);
  await scrollTo(await heading("flow"));      await frame(3.0);
  await scrollTo(await heading("companies")); await frame(2.5);
  await scrollTo(await heading("stock"));     await frame(3.0);

  await go("/cvs/");                      await frame(3.5);
} finally {
  await page.close();
}

const args = ["--loopcount=forever"];
for (const [gif, delay] of frames) args.push("-d", String(delay), gif);
execFileSync("gifsicle", [...args, "--colors", "128", "-O3", "-o", OUT]);
rmSync(work, { recursive: true, force: true });

const seconds = frames.reduce((s, [, d]) => s + d, 0) / 100;
console.log(`  ${OUT}  ${frames.length} frames, ${seconds.toFixed(1)}s, ` +
            `${(statSync(OUT).size / 1e6).toFixed(1)} MB`);

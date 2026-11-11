// Headless Chrome over the DevTools protocol — just enough for the recording tools
// (tools/record-screenshots, tools/record-intro). No Puppeteer or Playwright: Node 22+
// ships a WebSocket, and the handful of calls below are all either tool needs.
import { spawn } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const CHROME = process.env.CHROME
  || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";

export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// A fresh profile every run: no stored chat panel, sidebar state or cookies, so every
// recording starts from the app's defaults.
export async function launch() {
  const profile = mkdtempSync(join(tmpdir(), "jobstudio-chrome-"));
  const port = 9300 + Math.floor(Math.random() * 600);
  const chrome = spawn(CHROME, [
    "--headless=new", `--remote-debugging-port=${port}`, `--user-data-dir=${profile}`,
    "--hide-scrollbars", "--no-first-run", "--no-default-browser-check", "about:blank",
  ], { stdio: "ignore" });
  chrome.on("error", (e) => { console.error(`cannot start Chrome (${CHROME}): ${e.message}`); process.exit(1); });

  let target;
  for (let i = 0; i < 100 && !target; i++) {
    try {
      const list = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
      target = list.find((t) => t.type === "page");
    } catch { await sleep(100); }
  }
  if (!target) throw new Error("Chrome did not open a debugging port");

  const ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((r) => ws.addEventListener("open", r, { once: true }));
  let seq = 0;
  const pending = new Map();
  ws.addEventListener("message", (e) => {
    const m = JSON.parse(e.data);
    if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); }
  });
  const send = (method, params = {}) => new Promise((resolve, reject) => {
    const id = ++seq;
    pending.set(id, (m) => (m.error ? reject(new Error(`${method}: ${m.error.message}`)) : resolve(m.result)));
    ws.send(JSON.stringify({ id, method, params }));
  });
  await send("Page.enable");

  const page = {
    send,
    // Evaluate an expression in the page and return its value.
    js: async (expr) => (await send("Runtime.evaluate",
      { expression: expr, returnByValue: true, awaitPromise: true })).result.value,
    viewport: (width, height, scale = 1) => send("Emulation.setDeviceMetricsOverride",
      { width, height, deviceScaleFactor: scale, mobile: false }),
    // Load a page and wait for it, plus time for the charts to finish drawing in.
    async go(url, settle = 1400) {
      await send("Page.navigate", { url });
      for (let i = 0; i < 100 && (await page.js("document.readyState")) !== "complete"; i++) await sleep(100);
      await sleep(settle);
    },
    // PNG bytes: the viewport, or a {x, y, width, height} region of the document.
    async png(clip) {
      const params = { format: "png" };
      if (clip) Object.assign(params, { clip: { ...clip, scale: 1 }, captureBeyondViewport: true });
      return Buffer.from((await send("Page.captureScreenshot", params)).data, "base64");
    },
    // Waits for Chrome to exit before removing its profile: it is still writing to it
    // for a moment after the kill, and the removal fails if it runs first.
    async close() {
      ws.close();
      const exited = new Promise((r) => chrome.once("exit", r));
      chrome.kill();
      await exited;
      rmSync(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
    },
  };
  return page;
}

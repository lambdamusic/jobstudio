/* Highlighter for rendered markdown (TODO #77, local app only).
 *
 * A "Highlight" button turns the mode on and off; it is only added to pages that hold a
 * document it can write to (`.hl-doc[data-hl-source]`). With the mode on:
 *
 *   - selecting text inside a document highlights it: the selection, plus a little text
 *     either side to tell repeated passages apart, goes to /actions/highlight/, which
 *     wraps it in `==…==` in the markdown file;
 *   - clicking a highlight removes it.
 *
 * The page then reloads, because the file is the record and the server is what renders
 * it — the scroll position is put back afterwards. The mode is remembered per browser,
 * so it stays on across that reload and while you work through a page.
 *
 * On a tabbed page the button shows only while the open tab holds such a document — an
 * application's CV, Cover letter and History tabs have nothing to highlight.
 */
(function () {
  "use strict";
  if (!document.querySelector(".hl-doc[data-hl-source]")) return;

  var meta = document.querySelector('meta[name="csrf-token"]');
  var token = meta ? meta.getAttribute("content") : "";
  var KEY = "jobstudio.highlight";
  var CONTEXT = 60;
  var BLOCK = "p, li, td, th, dd, dt, blockquote, h1, h2, h3, h4, h5, h6, summary, pre";

  function remembered() {
    try { return localStorage.getItem(KEY) === "on"; } catch (e) { return false; }
  }
  function remember(on) {
    try { localStorage.setItem(KEY, on ? "on" : "off"); } catch (e) { /* private mode */ }
  }

  var button = document.createElement("button");
  button.type = "button";
  button.className = "hl-toggle";
  button.title = "Select text to highlight it; click a highlight to remove it (H)";
  document.body.appendChild(button);

  function set(on) {
    document.body.classList.toggle("hl-on", on);
    button.setAttribute("aria-pressed", on ? "true" : "false");
    button.textContent = on ? "Highlighting: on" : "Highlight";
    remember(on);
  }
  button.addEventListener("click", function () { set(!document.body.classList.contains("hl-on")); });

  // A document in a hidden tab panel does not count. tabs.js hides panels with the
  // `hidden` attribute, so watching that attribute follows every way of switching tab.
  function showing() {
    return Array.prototype.some.call(document.querySelectorAll(".hl-doc[data-hl-source]"),
      function (d) { return !d.closest("[hidden]"); });
  }
  function refresh() {
    var hide = !showing();
    if (button.hidden !== hide) button.hidden = hide;  // the button's own change re-fires this
  }
  new MutationObserver(refresh).observe(document.body,
    { attributes: true, attributeFilter: ["hidden"], subtree: true });
  refresh();

  document.addEventListener("keydown", function (e) {
    var t = e.target;
    if (e.key !== "h" || e.metaKey || e.ctrlKey || e.altKey || button.hidden) return;
    if (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName)) return;
    set(!document.body.classList.contains("hl-on"));
  });
  set(remembered());

  // Put the reader back where they were after the reload a change causes.
  try {
    var y = sessionStorage.getItem(KEY + ".scroll");
    if (y !== null) {
      sessionStorage.removeItem(KEY + ".scroll");
      window.addEventListener("load", function () { window.scrollTo(0, +y); });
    }
  } catch (e) { /* no storage: the page just starts at the top */ }

  var note = null;
  function say(text) {
    if (!note) {
      note = document.createElement("div");
      note.className = "hl-note";
      note.setAttribute("role", "status");
      document.body.appendChild(note);
    }
    note.textContent = text;
    note.hidden = false;
    clearTimeout(say.timer);
    say.timer = setTimeout(function () { note.hidden = true; }, 5000);
  }

  function send(fields) {
    var body = new FormData();
    Object.keys(fields).forEach(function (k) { body.append(k, fields[k]); });
    return fetch("/actions/highlight/", {
      method: "POST", body: body, credentials: "same-origin",
      headers: { "X-CSRFToken": token }
    })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok && j.ok, j: j }; }); })
      .then(function (res) {
        if (!res.ok) throw new Error(res.j.error || "not saved");
        try { sessionStorage.setItem(KEY + ".scroll", String(window.scrollY)); } catch (e) { /* fine */ }
        location.reload();
      })
      .catch(function (err) { say("Not saved: " + err.message); });
  }

  // Text from the start of the block holding `node` up to (node, offset), or from there
  // to the end of the block holding it — the context either side of a selection.
  function around(node, offset, toEnd) {
    var el = node.nodeType === 1 ? node : node.parentElement;
    var block = (el && el.closest(BLOCK)) || el;
    var r = document.createRange();
    r.selectNodeContents(block);
    if (toEnd) r.setStart(node, offset); else r.setEnd(node, offset);
    var text = r.toString();
    return toEnd ? text.slice(0, CONTEXT) : text.slice(-CONTEXT);
  }

  document.addEventListener("mouseup", function () {
    if (!document.body.classList.contains("hl-on")) return;
    var sel = window.getSelection();
    if (!sel || sel.isCollapsed || !sel.rangeCount) return;
    var range = sel.getRangeAt(0);
    var start = range.startContainer.nodeType === 1 ? range.startContainer : range.startContainer.parentElement;
    var end = range.endContainer.nodeType === 1 ? range.endContainer : range.endContainer.parentElement;
    var doc = start && start.closest(".hl-doc[data-hl-source]");
    if (!doc || !end || end.closest(".hl-doc[data-hl-source]") !== doc) {
      if (doc || (end && end.closest(".hl-doc"))) say("Select within one document.");
      return;
    }
    var text = range.toString();
    if (!text.trim()) return;
    send({
      source: doc.getAttribute("data-hl-source"),
      text: text,
      before: around(range.startContainer, range.startOffset, false),
      after: around(range.endContainer, range.endOffset, true)
    });
  });

  document.addEventListener("click", function (e) {
    if (!document.body.classList.contains("hl-on")) return;
    var mark = e.target.closest && e.target.closest("mark.hl[data-mark]");
    if (!mark) return;
    var sel = window.getSelection();
    if (sel && !sel.isCollapsed) return;  // the end of a selection drag, not a click
    var doc = mark.closest(".hl-doc[data-hl-source]");
    if (!doc) return;
    e.preventDefault();
    send({ source: doc.getAttribute("data-hl-source"), remove: mark.getAttribute("data-mark") });
  });
})();

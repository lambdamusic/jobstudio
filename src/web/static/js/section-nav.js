/* Section navigation for a collapsible document: open the right section, highlight
 * the right pill. Built for interview rounds (`#66`), reused unchanged by My notes and
 * Other files (`#72`) — it was already scoped per index rather than per page.
 *
 * The sections are `<details>`, closed by default and collapsible without any script.
 * This file adds the three things `<details>` alone cannot do:
 *
 *   1. Open the block a link points *into*. A pill for "1.2 Why this role" targets an
 *      `<h3>` inside a closed block; the browser will not open it, so the jump lands
 *      nowhere. Same for an inbound URL carrying `#...--outcome`.
 *   2. Expand all / collapse all, for reading the round straight through.
 *   3. Highlight the pill for the section being read.
 *
 * On (3) — the first version got this wrong and it is worth writing down why. It watched
 * a thin band at the top of the viewport with IntersectionObserver and lit whichever
 * heading was inside it. Click a pill and the target scrolls to y=0, *above* that band,
 * so the heading in the band was the NEXT one down: clicking "Outcome" highlighted the
 * subsection after it. The band was also the only input, so with no heading inside it —
 * most of the time — the highlight simply went stale.
 *
 * What it does now: the active section is the last heading whose top is above the line
 * just under the sticky bar. That is a property of scroll position rather than of an
 * event, so it is correct whether you scrolled there, clicked a pill, or loaded the page
 * on a deep link. `scroll-margin-top` in the CSS is the other half — without it the
 * browser scrolls the target under the sticky bar and the arithmetic disagrees with what
 * the eye sees.
 *
 * Since `#88` the index itself is a table of contents in the flow, not a sticky pill row.
 * This file also builds (4): the sticky part, a one-line "Contents ▾" bar inserted after
 * the index that appears once the index has scrolled out of view, names the section being
 * read, and opens a copy of the same list. Every link — in the index and in the bar's copy
 * — goes through the same handlers, so the two cannot disagree about what is active.
 *
 * Since 2026-10-15 each question and its answer is a `<details class="qa">` of its own
 * (`qa_items`), listed in the index under its heading. This file opens a folded question
 * when a link targets it, opens every answer on "Expand all", and adds (5): a "Hide
 * answers" link per heading, to read its questions alone.
 */
(function () {
  "use strict";

  // The sticky bar's height is measured rather than assumed (a long section name can wrap
  // it on a narrow window). The measured value is written to `--section-clearance` on the
  // scope, which is what `scroll-margin-top` in site.css reads — so the scroll target and
  // the highlight arithmetic always use the same number. 48 is the fallback for a bar
  // that has no box yet (its tab is hidden).
  var FALLBACK_CLEARANCE = 48;
  var GAP_BELOW_INDEX = 8;

  function setup(nav) {
    var scope = nav.parentElement;
    if (!scope) return;
    var list = nav.querySelector(".section-list");
    if (!list || !list.querySelector("a.section-link")) return;

    // (4) The sticky bar: "Contents ▾", the section being read, and a copy of the list.
    var mini = document.createElement("div");
    mini.className = "section-mini";
    mini.innerHTML = '<div class="section-mini-bar">' +
      '<button type="button" class="section-mini-toggle" aria-expanded="false">Contents ▾</button>' +
      '<span class="section-mini-here"></span></div>';
    var bar = mini.firstChild;
    var miniToggle = bar.querySelector(".section-mini-toggle");
    var miniHere = bar.querySelector(".section-mini-here");
    var miniList = list.cloneNode(true);
    miniList.hidden = true;
    bar.appendChild(miniList);
    nav.parentNode.insertBefore(mini, nav.nextSibling);

    function openMini(open) {
      miniList.hidden = !open;
      miniToggle.setAttribute("aria-expanded", open ? "true" : "false");
      miniToggle.textContent = open ? "Contents ▴" : "Contents ▾";
    }
    miniToggle.addEventListener("click", function () { openMini(miniList.hidden); });
    document.addEventListener("click", function (e) {
      if (!miniList.hidden && !bar.contains(e.target)) openMini(false);
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && !miniList.hidden) openMini(false);
    });

    // Shown once the index is out of view. The bar has no height in the flow, so this
    // never moves the page.
    if (window.IntersectionObserver) {
      new IntersectionObserver(function (entries) {
        var gone = !entries[0].isIntersecting && entries[0].boundingClientRect.top < 0;
        mini.classList.toggle("shown", gone);
        if (!gone) openMini(false);
      }).observe(nav);
    }

    var links = Array.prototype.slice.call(nav.querySelectorAll("a.section-link"))
      .concat(Array.prototype.slice.call(miniList.querySelectorAll("a.section-link")));

    var clearance = FALLBACK_CLEARANCE;
    function measure() {
      // Measured with the list folded, which is how the bar sits while reading.
      var h = miniList.hidden ? bar.getBoundingClientRect().height : 0;
      if (!h) return;
      var next = Math.ceil(h) + GAP_BELOW_INDEX;
      if (next === clearance) return;
      clearance = next;
      scope.style.setProperty("--section-clearance", clearance + "px");
    }

    // Each id has two links, one in the index and one in the bar's copy.
    var byTarget = {};
    links.forEach(function (a) {
      var id = a.getAttribute("data-target");
      (byTarget[id] = byTarget[id] || []).push(a);
    });

    function blockFor(id) {
      var el = scope.querySelector('[id="' + CSS.escape(id) + '"]');
      return el ? el.closest("details.doc-section") : null;
    }

    // (1) Opening the block a link points into.
    function reveal(id, scrollTo) {
      var block = blockFor(id);
      if (block && !block.open) block.open = true;
      // A question folded inside it, or the question itself (2026-10-15): open every
      // closed <details> on the way down, or the jump lands on a folded line.
      var target = scope.querySelector('[id="' + CSS.escape(id) + '"]');
      for (var d = target; d && d !== scope; d = d.parentElement) {
        if (d.tagName === "DETAILS" && !d.open) d.open = true;
      }
      if (!scrollTo) return;
      measure();
      var el = scope.querySelector('[id="' + CSS.escape(id) + '"]');
      // After `open` the layout has changed, so let it settle before scrolling.
      if (el) window.requestAnimationFrame(function () { el.scrollIntoView(); });
    }

    links.forEach(function (a) {
      a.addEventListener("click", function (e) {
        var id = a.getAttribute("data-target");
        // Handled here rather than left to the browser: the target may be inside a
        // closed block, where the default jump goes nowhere.
        e.preventDefault();
        openMini(false);
        reveal(id, true);
        if (history.replaceState) history.replaceState(null, "", "#" + id);
        mark(id);
      });
    });

    // (2) Expand all / collapse all.
    var toggle = nav.querySelector("[data-toggle-all]");
    var blocks = Array.prototype.slice.call(
      scope.querySelectorAll("details.doc-section"));
    if (toggle && blocks.length) {
      toggle.addEventListener("click", function () {
        var opening = blocks.some(function (d) { return !d.open; });
        blocks.forEach(function (d) { d.open = opening; });
        // Expanding all means reading straight through, so the answers open too.
        if (opening) showAnswers(scope);
        toggle.textContent = opening ? "Collapse all" : "Expand all";
      });
      blocks.forEach(function (d) {
        d.addEventListener("toggle", function () {
          var allOpen = blocks.every(function (x) { return x.open; });
          toggle.textContent = allOpen ? "Collapse all" : "Expand all";
          update();
        });
      });
    }

    // (5) "Hide answers" (2026-10-15): one link per heading with two or more questions
    // under it, folding every answer there so the questions can be read alone. Questions
    // before any `###`, and headings that are themselves questions, get one link at the top
    // of their section instead.
    Array.prototype.forEach.call(scope.querySelectorAll(".doc-section-body"), function (body) {
      var groups = [], top = { at: null, items: [] }, cur = top;
      groups.push(top);
      Array.prototype.forEach.call(body.children, function (el) {
        if (el.tagName === "H3") { cur = { at: el, items: [] }; groups.push(cur); return; }
        if (el.matches("details.qa-h")) { top.items.push(el); return; }
        if (el.matches("details.qa")) cur.items.push(el);
        Array.prototype.forEach.call(el.querySelectorAll("details.qa:not(.qa-h)"), function (d) {
          if (!d.parentElement.closest("details.qa")) cur.items.push(d);
        });
      });
      groups.forEach(function (g) {
        if (g.items.length < 2) return;
        var b = document.createElement("button");
        b.type = "button";
        b.className = "qa-toggle";
        b.textContent = "Hide answers";
        b.addEventListener("click", function () {
          var hide = b.textContent === "Hide answers";
          g.items.forEach(function (d) { d.open = !hide; });
          b.textContent = hide ? "Show answers" : "Hide answers";
        });
        if (g.at) { g.at.appendChild(b); return; }
        var tools = document.createElement("div");
        tools.className = "qa-tools";
        tools.appendChild(b);
        body.insertBefore(tools, body.firstChild);
      });
    });

    // (3) Highlight.
    var active = null;
    function mark(id) {
      if (id === active) return;
      (byTarget[active] || []).forEach(function (a) { a.classList.remove("here"); });
      active = id;
      (byTarget[id] || []).forEach(function (a) { a.classList.add("here"); });
      var a = (byTarget[id] || [])[0];
      miniHere.textContent = a ? a.textContent.replace(/\s+/g, " ").trim() : "";
    }

    function update() {
      var best = null;
      Object.keys(byTarget).forEach(function (id) {
        var el = scope.querySelector('[id="' + CSS.escape(id) + '"]');
        // A heading inside a closed block has no box worth measuring, and is not
        // something the reader can be looking at.
        if (!el || !el.getClientRects().length) return;
        if (el.getBoundingClientRect().top <= clearance + 4) best = id;
      });
      if (best) mark(best);
    }

    var queued = false;
    function onScroll() {
      if (queued) return;
      queued = true;
      window.requestAnimationFrame(function () { queued = false; update(); });
    }
    function onResize() { measure(); onScroll(); }
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onResize, { passive: true });
    // The bar's height also changes without a window resize: a hidden tab being shown,
    // or the toggle's label changing length.
    if (window.ResizeObserver) new ResizeObserver(onResize).observe(bar);
    measure();

    // A deep link arriving from outside — the focus view's "other rounds" links, or a
    // URL someone saved mid-process.
    function fromHash() {
      var id = window.location.hash.replace("#", "");
      if (id && byTarget[id]) { reveal(id, true); mark(id); }
      // Not a pill, but inside this document — a glossary term's entry, say, which may
      // sit in a closed block.
      else if (id && scope.querySelector('[id="' + CSS.escape(id) + '"]')) reveal(id, true);
      else update();
    }
    window.addEventListener("hashchange", fromHash);
    fromHash();
  }

  function showAnswers(scope) {
    Array.prototype.forEach.call(scope.querySelectorAll("details.qa"), function (d) { d.open = true; });
    Array.prototype.forEach.call(scope.querySelectorAll(".qa-toggle"), function (b) {
      b.textContent = "Hide answers";
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    Array.prototype.forEach.call(
      document.querySelectorAll("[data-section-index]"), setup);
  });
})();

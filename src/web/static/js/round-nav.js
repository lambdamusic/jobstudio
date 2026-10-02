/* Interview round navigation (`#66`): open the right section, highlight the right pill.
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
 * just under the sticky index. That is a property of scroll position rather than of an
 * event, so it is correct whether you scrolled there, clicked a pill, or loaded the page
 * on a deep link. `scroll-margin-top` in the CSS is the other half — without it the
 * browser scrolls the target under the sticky bar and the arithmetic disagrees with what
 * the eye sees.
 */
(function () {
  "use strict";

  // Keep in step with `scroll-margin-top` on `.round-section summary` in site.css.
  var STICKY_CLEARANCE = 56;

  function setup(nav) {
    var scope = nav.parentElement;
    if (!scope) return;
    var links = Array.prototype.slice.call(nav.querySelectorAll("a.section-chip"));
    if (!links.length) return;

    var byTarget = {};
    links.forEach(function (a) { byTarget[a.getAttribute("data-target")] = a; });

    function blockFor(id) {
      var el = scope.querySelector('[id="' + CSS.escape(id) + '"]');
      return el ? el.closest("details.round-section") : null;
    }

    // (1) Opening the block a link points into.
    function reveal(id, scrollTo) {
      var block = blockFor(id);
      if (block && !block.open) block.open = true;
      if (!scrollTo) return;
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
        reveal(id, true);
        if (history.replaceState) history.replaceState(null, "", "#" + id);
        mark(id);
      });
    });

    // (2) Expand all / collapse all.
    var toggle = nav.querySelector("[data-toggle-all]");
    var blocks = Array.prototype.slice.call(
      scope.querySelectorAll("details.round-section"));
    if (toggle && blocks.length) {
      toggle.addEventListener("click", function () {
        var opening = blocks.some(function (d) { return !d.open; });
        blocks.forEach(function (d) { d.open = opening; });
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

    // (3) Highlight.
    var active = null;
    function mark(id) {
      if (id === active) return;
      if (active && byTarget[active]) byTarget[active].classList.remove("here");
      active = id;
      if (byTarget[id]) byTarget[id].classList.add("here");
    }

    function update() {
      var best = null;
      links.forEach(function (a) {
        var id = a.getAttribute("data-target");
        var el = scope.querySelector('[id="' + CSS.escape(id) + '"]');
        // A heading inside a closed block has no box worth measuring, and is not
        // something the reader can be looking at.
        if (!el || !el.getClientRects().length) return;
        if (el.getBoundingClientRect().top <= STICKY_CLEARANCE + 4) best = id;
      });
      if (best) mark(best);
    }

    var queued = false;
    function onScroll() {
      if (queued) return;
      queued = true;
      window.requestAnimationFrame(function () { queued = false; update(); });
    }
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll, { passive: true });

    // A deep link arriving from outside — the focus view's "other rounds" links, or a
    // URL someone saved mid-process.
    function fromHash() {
      var id = window.location.hash.replace("#", "");
      if (id && byTarget[id]) { reveal(id, true); mark(id); }
      else update();
    }
    window.addEventListener("hashchange", fromHash);
    fromHash();
  }

  document.addEventListener("DOMContentLoaded", function () {
    Array.prototype.forEach.call(
      document.querySelectorAll("[data-section-index]"), setup);
  });
})();

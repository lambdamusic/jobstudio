/* Highlights the section you are currently reading in an interview round's jump index.
 *
 * Enhancement only. The index is a list of plain anchor links and works with this file
 * absent, failing to load, or disabled — all this adds is the `.here` class, so nothing
 * here is allowed to be load-bearing.
 *
 * IntersectionObserver rather than a scroll handler: the browser does the work off the
 * main thread, which matters on a page being scrolled while a video call is running.
 */
(function () {
  "use strict";

  if (!window.IntersectionObserver) return;

  function setup(nav) {
    var links = Array.prototype.slice.call(nav.querySelectorAll("a.section-chip"));
    if (links.length < 2) return;

    // The scope is the round, not the document: the Interviews tab stacks several
    // rounds on one page, each with its own index, and an observer watching all of
    // them would light up chips in the round you are not reading.
    var scope = nav.parentElement;
    var byId = {};
    var headings = [];
    links.forEach(function (link) {
      var id = link.getAttribute("href").slice(1);
      var el = scope.querySelector('[id="' + id + '"]');
      if (!el) return;
      byId[id] = link;
      headings.push(el);
    });
    if (!headings.length) return;

    var active = null;
    function mark(id) {
      if (id === active) return;
      if (active && byId[active]) byId[active].classList.remove("here");
      active = id;
      if (byId[id]) byId[id].classList.add("here");
    }

    // Top band only: a heading counts as "current" from when it reaches just under the
    // sticky bar until the next one does. Without the negative bottom margin every
    // heading below the fold would also be intersecting, and the last one would win.
    var seen = {};
    var obs = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) { seen[e.target.id] = e.isIntersecting; });
      for (var i = headings.length - 1; i >= 0; i--) {
        if (seen[headings[i].id]) { mark(headings[i].id); return; }
      }
    }, { rootMargin: "-48px 0px -75% 0px", threshold: 0 });

    headings.forEach(function (h) { obs.observe(h); });
  }

  document.addEventListener("DOMContentLoaded", function () {
    Array.prototype.forEach.call(
      document.querySelectorAll("[data-section-index]"), setup);
  });
})();

/* Tabbed sections.
 *
 * Progressive enhancement: the markup renders every panel visible. This script adds the
 * `js-tabs` class, which is what actually hides the inactive ones — so with JavaScript
 * off, or if this file fails to load, the page is still complete and readable rather than
 * showing only the first section. That matters because the published static site is a
 * plain file mirror with no server behind it.
 *
 * The active tab is reflected in the URL hash, so a section can be linked to directly.
 */
(function () {
  "use strict";

  function setup(group) {
    var tabs = Array.prototype.slice.call(group.querySelectorAll("[data-tab]"));
    var panels = Array.prototype.slice.call(group.querySelectorAll("[data-panel]"));
    if (tabs.length < 2) return;

    group.classList.add("js-tabs");

    function activate(name, pushHash) {
      var found = false;
      tabs.forEach(function (tab) {
        var on = tab.getAttribute("data-tab") === name;
        tab.classList.toggle("active", on);
        tab.setAttribute("aria-selected", on ? "true" : "false");
        tab.setAttribute("tabindex", on ? "0" : "-1");
        if (on) found = true;
      });
      panels.forEach(function (panel) {
        panel.hidden = panel.getAttribute("data-panel") !== name;
      });
      if (found && pushHash && history.replaceState) {
        history.replaceState(null, "", "#" + name);
      }
      return found;
    }

    tabs.forEach(function (tab, i) {
      tab.addEventListener("click", function () {
        activate(tab.getAttribute("data-tab"), true);
      });
      // Left/right arrows move between tabs, as a tablist should.
      tab.addEventListener("keydown", function (e) {
        var next = null;
        if (e.key === "ArrowRight") next = tabs[(i + 1) % tabs.length];
        if (e.key === "ArrowLeft") next = tabs[(i - 1 + tabs.length) % tabs.length];
        if (!next) return;
        e.preventDefault();
        next.focus();
        activate(next.getAttribute("data-tab"), true);
      });
    });

    var fromHash = window.location.hash.replace("#", "");
    if (!fromHash || !activate(fromHash, false)) {
      activate(tabs[0].getAttribute("data-tab"), false);
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    Array.prototype.forEach.call(document.querySelectorAll("[data-tabs]"), setup);
  });
})();

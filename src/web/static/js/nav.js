/* Sidebar groups that open and close (`#94`).
 *
 * The folding itself is native <details>, so it needs no script. This only does two
 * things the markup cannot:
 *
 * - Remembers which groups the reader left open, per browser, in localStorage. A group
 *   the page is inside (`data-inside`) is always open regardless, so the current place is
 *   never hidden; remembering only decides the others. Storage can be blocked (a private
 *   window, cleared site data), so every access is wrapped and a failure just means the
 *   groups start closed.
 * - On /notes/, marks the sub-item for whichever tab is open. Which tab that is lives in
 *   the URL hash, which the server never sees, so the template cannot mark it.
 */
(function () {
  "use strict";

  var KEY = "jobstudio.nav.open";

  function load() {
    try {
      return JSON.parse(window.localStorage.getItem(KEY) || "{}") || {};
    } catch (e) {
      return {};
    }
  }

  function save(state) {
    try {
      window.localStorage.setItem(KEY, JSON.stringify(state));
    } catch (e) { /* blocked storage: the groups just won't be remembered */ }
  }

  function setupFolds() {
    var state = load();
    Array.prototype.forEach.call(document.querySelectorAll("details.nav-fold"), function (fold) {
      var name = fold.getAttribute("data-fold");
      if (!fold.hasAttribute("data-inside") && state[name]) fold.open = true;
      fold.addEventListener("toggle", function () {
        if (fold.hasAttribute("data-inside")) return; // always open here; not a choice
        var now = load();
        now[name] = fold.open;
        save(now);
      });
    });
  }

  function markNotesTab() {
    var links = document.querySelectorAll("[data-tab-link]");
    if (!links.length || window.location.pathname !== "/notes/") return;
    var firstTab = document.querySelector("[data-tabs] [data-tab]");
    var current = window.location.hash.replace("#", "") ||
      (firstTab ? firstTab.getAttribute("data-tab") : "");
    // A hash naming something inside a tab (a coach document, say) keeps the tab tabs.js
    // opened; read it back from the active tab rather than guessing from the hash.
    var active = document.querySelector("[data-tabs] [data-tab].active");
    if (active) current = active.getAttribute("data-tab");
    Array.prototype.forEach.call(links, function (link) {
      link.classList.toggle("active", link.getAttribute("data-tab-link") === current);
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    setupFolds();
    // After tabs.js (also deferred, loaded first) has opened the tab from the hash.
    markNotesTab();
    window.addEventListener("hashchange", function () { setTimeout(markNotesTab, 0); });
  });
})();

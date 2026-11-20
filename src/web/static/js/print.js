/*
 * Print one document — a round, My notes, a file under Other files — rather than the page.
 *
 * A `[data-print]` button prints the nearest `[data-printable]` around it, or the element
 * its value names (`data-print="#id"`) when the button sits outside it. For the length
 * of the print dialog:
 *
 * - everything that is not the document or one of its ancestors gets `.print-hide`, so the
 *   other rounds, the tab strip and the sidebar leave the flow rather than turning
 *   invisible and leaving blank pages behind;
 * - every closed section and question inside it opens, since a round is collapsed on screen and a
 *   printout of numbered headings with nothing under them is no use;
 * - a one-line header names the document (`data-print-title`) and the day it was printed,
 *   and the page title becomes that name, which is what "Save as PDF" offers as the file
 *   name.
 *
 * `afterprint` undoes all of it. A plain ⌘P with no button still opens the sections, so
 * printing the page as a whole is not a list of collapsed headings either.
 */
(function () {
  "use strict";

  var undo = null;

  function each(list, fn) { Array.prototype.forEach.call(list, fn); }

  function openAll(scope, opened) {
    // The document's own sections and questions only — not the status menu, which is a
    // <details> too and would print as an open dropdown.
    each(scope.querySelectorAll("details.doc-section:not([open]), details.qa:not([open])"), function (d) {
      d.open = true;
      opened.push(d);
    });
  }

  function prepare(target) {
    var hidden = [], opened = [];
    for (var el = target; el.parentElement && el !== document.body; el = el.parentElement) {
      each(el.parentElement.children, function (sib) {
        if (sib !== el && !sib.classList.contains("print-hide")) {
          sib.classList.add("print-hide");
          hidden.push(sib);
        }
      });
    }
    openAll(target, opened);

    var title = target.getAttribute("data-print-title");
    var head = document.createElement("header");
    head.className = "print-head";
    var h = document.createElement("h1");
    h.textContent = title || document.title;
    var when = document.createElement("span");
    when.textContent = "Printed " + new Date().toLocaleDateString("en-GB",
      { day: "numeric", month: "short", year: "numeric" });
    head.appendChild(h);
    head.appendChild(when);
    target.insertBefore(head, target.firstChild);

    var pageTitle = document.title;
    if (title) document.title = title;
    document.documentElement.classList.add("printing-one");

    undo = function () {
      each(hidden, function (sib) { sib.classList.remove("print-hide"); });
      each(opened, function (d) { d.open = false; });
      head.remove();
      document.title = pageTitle;
      document.documentElement.classList.remove("printing-one");
    };
  }

  document.addEventListener("click", function (e) {
    var btn = e.target.closest && e.target.closest("[data-print]");
    if (!btn) return;
    var sel = btn.getAttribute("data-print");
    var target = sel ? document.querySelector(sel) : btn.closest("[data-printable]");
    if (!target) return;
    if (undo) undo();
    prepare(target);
    window.print();
  });

  window.addEventListener("beforeprint", function () {
    if (undo) return;  // a button already set this print up
    var opened = [];
    openAll(document, opened);
    undo = function () { each(opened, function (d) { d.open = false; }); };
  });

  window.addEventListener("afterprint", function () {
    if (undo) undo();
    undo = null;
  });
})();

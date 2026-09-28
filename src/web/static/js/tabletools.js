/* Search, filter, sort and paging for a long table, done in the browser.
 *
 * Why client-side. Every filtered view this site publishes has to be a real path — a
 * querystring cannot be mirrored into a static file tree (see build_static). Status and
 * target area already have real paths and keep them; what this adds is the combining and
 * the narrowing, which would need a URL per combination to exist server-side and would
 * publish a page for each. A table of a few hundred rows filters instantly here, works the
 * same in the published mirror as it does locally, and needs no URL at all.
 *
 * Progressive enhancement, like tabs.js and charts.js: the toolbar is hidden until this
 * script adds `js-tools`, so with JavaScript off the page is a complete, readable table
 * rather than a set of controls that do nothing.
 *
 * Markup contract — a toolbar and a table sharing one `data-table` name:
 *
 *   <div class="toolbar" data-table="apps">
 *     <input class="tb-search">                       filters on each row's data-search
 *     <select class="tb-filter" data-field="area">    filters on data-area
 *     <select class="tb-sort">                        values are "<field>:asc|desc",
 *                                                     read from data-sort-<field>
 *   <table data-table="apps" data-page-size="50">
 *     <tr data-search="…" data-area="…" data-sort-date="…">
 *   <p class="tb-empty" hidden>      shown when nothing matches
 *   <button class="tb-more" hidden>  shown while paging has more to give
 *
 * A `#field=value` fragment on the URL preselects a filter, which is how one page links
 * into a narrowed view of another without inventing a querystring.
 */
(function () {
  "use strict";

  function rowsOf(table) {
    return Array.prototype.slice.call(table.tBodies[0].rows);
  }

  function setup(toolbar) {
    var name = toolbar.getAttribute("data-table");
    var table = document.querySelector("table[data-table='" + name + "']");
    if (!table || !table.tBodies.length) return;

    var rows = rowsOf(table);
    var search = toolbar.querySelector(".tb-search");
    var filters = Array.prototype.slice.call(toolbar.querySelectorAll(".tb-filter"));
    var sorter = toolbar.querySelector(".tb-sort");
    var count = toolbar.querySelector(".tb-count");
    var more = toolbar.parentNode.querySelector(".tb-more");
    var empty = toolbar.parentNode.querySelector(".tb-empty");
    var wrap = table.closest(".table-wrap") || table;
    var pageSize = parseInt(table.getAttribute("data-page-size") || "0", 10);
    var shown = pageSize;

    toolbar.classList.add("js-tools");

    function sortKey(row, field) {
      var value = row.getAttribute("data-sort-" + field);
      if (value === null || value === "") return null;
      var number = parseFloat(value);
      return isNaN(number) ? value.toLowerCase() : number;
    }

    function matches(row) {
      var needle = (search && search.value.trim().toLowerCase()) || "";
      if (needle && (row.getAttribute("data-search") || "").toLowerCase().indexOf(needle) < 0) {
        return false;
      }
      return filters.every(function (select) {
        if (!select.value) return true;
        return row.getAttribute("data-" + select.getAttribute("data-field")) === select.value;
      });
    }

    function apply(resetPaging) {
      if (resetPaging) shown = pageSize;

      var order = sorter && sorter.value ? sorter.value.split(":") : null;
      if (order) {
        var field = order[0];
        var sign = order[1] === "asc" ? 1 : -1;
        rows.slice().sort(function (a, b) {
          var x = sortKey(a, field);
          var y = sortKey(b, field);
          // A row with no value for this field sorts last whichever way the arrow points:
          // "unknown" is not the same as "earliest", and putting it at the top of a
          // longest-without-moving list would be a lie about it.
          if (x === null && y === null) return 0;
          if (x === null) return 1;
          if (y === null) return -1;
          return x < y ? -sign : x > y ? sign : 0;
        }).forEach(function (row) { table.tBodies[0].appendChild(row); });
      }

      var visible = 0;
      rows.forEach(function (row) {
        var show = matches(row);
        if (show) visible += 1;
        row.hidden = !show || (pageSize > 0 && visible > shown);
      });

      // A table with only its header row reads as a broken page; say what happened instead.
      if (empty) empty.hidden = visible > 0;
      wrap.hidden = visible === 0;

      if (count) {
        count.textContent = visible === rows.length
          ? rows.length + (rows.length === 1 ? " row" : " rows")
          : visible + " of " + rows.length;
      }
      if (more) {
        var hiding = pageSize > 0 && visible > shown;
        more.hidden = !hiding;
        if (hiding) more.textContent = "Show " + Math.min(pageSize, visible - shown) + " more";
      }
    }

    if (search) search.addEventListener("input", function () { apply(true); });
    filters.forEach(function (select) {
      select.addEventListener("change", function () { apply(true); });
    });
    if (sorter) sorter.addEventListener("change", function () { apply(true); });
    if (more) {
      more.addEventListener("click", function () { shown += pageSize; apply(false); });
    }

    // #field=value — how a chart on another page links into a narrowed view here.
    var hash = decodeURIComponent(window.location.hash.replace(/^#/, ""));
    var pair = hash.split("=");
    if (pair.length === 2) {
      filters.forEach(function (select) {
        if (select.getAttribute("data-field") !== pair[0]) return;
        var wanted = Array.prototype.some.call(select.options, function (option) {
          return option.value === pair[1];
        });
        if (wanted) select.value = pair[1];
      });
    }

    apply(true);
  }

  Array.prototype.forEach.call(document.querySelectorAll(".toolbar[data-table]"), setup);
})();

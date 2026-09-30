/* Charts on /stats/ — see backlog/dashboard-charts-plan.md.
 *
 * This file draws; it never aggregates (R2). Every number arrives finished in the
 * #chart-data payload the view rendered, which is what keeps the terminal mirror possible
 * and the static export inert.
 *
 * It is also an enhancement, not the page. Each chart's numbers are already in the markup
 * as a table; adding `js-charts` to <body> is what reveals the drawings, and the tables
 * collapse behind "The numbers" once something has actually been drawn. With no
 * JavaScript, or if the library fails to load, the page stays a readable document — the
 * same arrangement tabs.js uses.
 *
 * Colours come from CSS custom properties rather than from here, so the palette has one
 * definition (site.css, "chart palette") and a future dark mode is a change in one place.
 */
(function () {
  "use strict";

  var payload = document.getElementById("chart-data");
  if (!payload || typeof echarts === "undefined") return;

  var data = JSON.parse(payload.textContent);
  var css = getComputedStyle(document.documentElement);

  function token(name, fallback) {
    var value = css.getPropertyValue(name);
    return (value && value.trim()) || fallback;
  }

  var ink = token("--ink", "#1a1a2e");
  var muted = token("--muted", "#6b6b76");
  var faint = token("--faint", "#9a9aa5");
  var line = token("--line", "#e6e6ea");
  var stub = token("--c-stub", "#c4c7d0");
  var quiet = [token("--c-quiet", "#c9a13a"), token("--c-quiet-deep", "#8a6a18")];
  // For the charts whose categories are ordered but are not statuses — age bands, and the
  // applications-per-company buckets.
  var ramp = ["--ramp-1", "--ramp-2", "--ramp-3", "--ramp-4"].map(function (n) {
    return token(n, "#47639c");
  });

  // A status is the same colour wherever it appears: this reads the same custom property
  // the badge does, so a pill and a ribbon cannot drift apart.
  function statusColor(status) {
    return token("--st-" + status, stub);
  }

  var BASE = {
    textStyle: { fontFamily: css.getPropertyValue("font-family") || "inherit" },
    animationDuration: 320
  };

  function axisLabel() {
    return { color: muted, fontSize: 11.5 };
  }

  /* ---------------------------------------------------------------- §7 ageing */
  function ageingOption(d) {
    var fresh = 0;
    var bars = d.bands.map(function (band) {
      var color = band.stale
        ? quiet[Math.min(quiet.length - 1, d.bands.filter(function (b) { return b.stale; })
            .indexOf(band))]
        : ramp[Math.min(ramp.length - 1, fresh++)];
      return {
        value: band.count,
        itemStyle: { color: color, borderRadius: [4, 4, 0, 0] },
        band: band
      };
    });
    return Object.assign({}, BASE, {
      grid: { left: 4, right: 4, top: 26, bottom: 4, containLabel: true },
      tooltip: {
        trigger: "item",
        formatter: function (p) {
          var band = p.data.band;
          var line2 = band.adrift ? "<br>" + band.adrift + " with no next action" : "";
          return "<strong>" + band.label + "</strong> since last move<br>" +
            p.value + " application" + (p.value === 1 ? "" : "s") +
            (band.stale ? " · gone quiet" : "") + line2;
        }
      },
      xAxis: {
        type: "category",
        data: d.bands.map(function (b) { return b.stale ? b.label + " · quiet" : b.label; }),
        axisTick: { show: false },
        axisLine: { lineStyle: { color: line } },
        axisLabel: axisLabel()
      },
      yAxis: { type: "value", minInterval: 1, axisLabel: { show: false },
              splitLine: { lineStyle: { color: line } } },
      series: [{
        type: "bar", data: bars, barMaxWidth: 54,
        label: { show: true, position: "top", color: ink, fontSize: 12, fontWeight: 600 }
      }]
    });
  }

  /* ------------------------------------------------------------------ §3 flow */
  function flowOption(d) {
    return Object.assign({}, BASE, {
      tooltip: {
        trigger: "item", triggerOn: "mousemove",
        formatter: function (p) {
          if (p.dataType === "edge") {
            return p.data.label.source + " → " + p.data.label.target +
              "<br><strong>" + p.data.value + "</strong>";
          }
          return "<strong>" + (p.data.label || p.name) + "</strong>";
        }
      },
      series: [{
        type: "sankey", emphasis: { focus: "adjacency" },
        // The rightmost column is the "still here" stubs, whose labels sit outside the
        // diagram — without room for them they are clipped by the container. Wider since
        // the labels carry a bracketed total ("inactive (34)", #56).
        nodeWidth: 13, nodeGap: 13, left: 8, right: 104, top: 10, bottom: 10,
        data: d.nodes.map(function (node) {
          return {
            name: node.name,
            label: node.label,
            itemStyle: {
              // A status keeps its own colour; the entry and end nodes are structural and
              // take the neutral, so they cannot be mistaken for an eighth status.
              color: node.kind === "status" ? statusColor(node.status) : stub,
              borderColor: "transparent"
            }
          };
        }),
        links: d.links.map(function (link) {
          return {
            source: link.source, target: link.target, value: link.value,
            label: { source: labelOf(d, link.source), target: labelOf(d, link.target) },
            lineStyle: { color: "gradient", opacity: link.kind === "move" ? 0.42 : 0.24 }
          };
        }),
        label: {
          color: ink, fontSize: 12,
          formatter: function (p) { return p.data.label || p.name; }
        }
      }]
    });
  }

  function labelOf(d, name) {
    for (var i = 0; i < d.nodes.length; i++) {
      if (d.nodes[i].name === name) return d.nodes[i].label;
    }
    return name;
  }

  /* ------------------------------------------------------------- §5 coverage */
  function coverageOption(d) {
    var share = d.total ? Math.round((d.submitted / d.total) * 100) : 0;
    return Object.assign({}, BASE, {
      tooltip: { trigger: "item", formatter: "{b}<br><strong>{c}</strong> ({d}%)" },
      legend: { bottom: 0, itemWidth: 10, itemHeight: 10,
               textStyle: { color: muted, fontSize: 12 } },
      title: {
        text: share + "%", subtext: "applied to", left: "center", top: "34%",
        textStyle: { color: ink, fontSize: 26, fontWeight: 650 },
        subtextStyle: { color: muted, fontSize: 12 }
      },
      series: [{
        type: "pie", radius: ["54%", "76%"], center: ["50%", "44%"], avoidLabelOverlap: true,
        // The 2px surface ring that keeps adjacent segments from bleeding together.
        itemStyle: { borderColor: token("--bg", "#ffffff"), borderWidth: 2 },
        label: { color: muted, fontSize: 12, formatter: "{b}: {c}" },
        labelLine: { lineStyle: { color: line } },
        // The same three colours the company badges use, because they are the same three
        // states — a company's status in a chart and on its row cannot drift apart.
        data: d.states.map(function (state) {
          return {
            name: state.status, value: state.count,
            itemStyle: { color: statusColor(state.status) }
          };
        })
      }]
    });
  }

  /* ---------------------------------------------------------- §6 per company */
  function perCompanyOption(d) {
    // Reversed because a category axis on y reads bottom-up, and this list should read
    // top-down: none, 1, 2, 3+.
    var rows = d.buckets.slice().reverse();
    return Object.assign({}, BASE, {
      grid: { left: 4, right: 30, top: 6, bottom: 4, containLabel: true },
      tooltip: {
        trigger: "item",
        formatter: function (p) {
          var names = (p.data.companies || []).map(function (c) { return c.name; });
          var tail = p.data.more ? "<br>…and " + p.data.more + " more" : "";
          return "<strong>" + p.value + "</strong> compan" + (p.value === 1 ? "y" : "ies") +
            " with " + p.name + " application" + (p.name === "1" ? "" : "s") +
            (names.length ? "<br>" + names.join("<br>") + tail : "");
        }
      },
      xAxis: { type: "value", minInterval: 1, axisLabel: { show: false },
              splitLine: { lineStyle: { color: line } } },
      yAxis: {
        type: "category", data: rows.map(function (b) { return b.label; }),
        axisTick: { show: false }, axisLine: { lineStyle: { color: line } },
        axisLabel: axisLabel()
      },
      series: [{
        type: "bar", barMaxWidth: 24,
        data: rows.map(function (bucket) {
          // Colour by how many applications the bucket stands for, not by its row: more
          // applications, darker step. "none" is structural, so it takes the stub grey.
          var step = d.buckets.indexOf(bucket) - 1;
          return {
            name: bucket.label, value: bucket.count,
            companies: bucket.companies, more: bucket.more,
            itemStyle: {
              color: step < 0 ? stub : ramp[Math.min(ramp.length - 1, step)],
              borderRadius: [0, 4, 4, 0]
            }
          };
        }),
        label: { show: true, position: "right", color: ink, fontSize: 12, fontWeight: 600 }
      }]
    });
  }

  /* ------------------------------------------------------------------ §4 stock */
  function stockOption(d, view) {
    // Two different measures of the same replay, not one drawn two ways. Stacked shows
    // STOCK — where every application sat at the end of each week, so the top of the pile
    // is the size of the tracker. Lines show FLOW — how many arrived in each status during
    // that week, against a common zero, which is the only reading that can be followed one
    // status at a time: in a stack a band's thickness is its value but its height is
    // everyone else's, so a status that never moved still appears to.
    var stacked = view !== "lines";
    var cells = stacked ? "cells" : "flow";
    var series = d.statuses.map(function (status, i) {
      return {
        name: status, type: "line", stack: stacked ? "stock" : null,
        // Steps, not a curve (R-T3): a status changes on a day, and a smooth line between
        // two weeks would draw values nobody was ever in.
        step: "end", symbol: "none", smooth: false,
        lineStyle: { width: stacked ? 1.5 : 2, color: statusColor(status) },
        // The 2px surface gap that keeps stacked bands from bleeding into each other.
        areaStyle: stacked ? { color: statusColor(status), opacity: 0.85 } : null,
        itemStyle: { color: statusColor(status) },
        emphasis: { focus: "series" },
        data: d.weeks.map(function (week) { return week[cells][i]; })
      };
    });

    // The weeks whose history was reconstructed rather than lived — shaded behind the
    // bands rather than recoloured, so the reader sees the period, not a different series.
    var bands = [];
    d.weeks.forEach(function (week, i) {
      if (!week.reconstructed) return;
      bands.push([{ xAxis: Math.max(0, i - 0.5) }, { xAxis: i + 0.5 }]);
    });
    if (bands.length && series.length) {
      series[series.length - 1].markArea = {
        silent: true,
        itemStyle: { color: token("--c-quiet", "#c9a13a"), opacity: 0.12 },
        data: bands
      };
    }

    return Object.assign({}, BASE, {
      // Room on the right for the last week's label, which otherwise clips.
      grid: { left: 4, right: 28, top: 30, bottom: 4, containLabel: true },
      tooltip: { trigger: "axis", axisPointer: { type: "line", lineStyle: { color: faint } } },
      legend: {
        top: 0, itemWidth: 10, itemHeight: 10, itemGap: 14,
        // The legend keeps funnel order even though the bands are stacked in reverse.
        data: d.statuses,
        textStyle: { color: muted, fontSize: 12 }
      },
      xAxis: {
        type: "category", boundaryGap: false,
        data: d.weeks.map(function (week) { return week.label; }),
        axisTick: { show: false }, axisLine: { lineStyle: { color: line } },
        axisLabel: axisLabel()
      },
      yAxis: { type: "value", minInterval: 1, splitLine: { lineStyle: { color: line } },
              axisLabel: axisLabel() },
      // Reversed when stacked: ECharts stacks the first series at the bottom, and these
      // should read top-to-bottom as the pipeline — saved at the top, the ways it ends
      // underneath. Unstacked there is no pile, so funnel order is the legible one.
      series: stacked ? series.slice().reverse() : series
    });
  }

  /* ------------------------------------------------------------------ wiring */
  var BUILDERS = {
    ageing: function () { return ageingOption(data.ageing); },
    flow: function (view) { return flowOption(data.flow[view || "full"]); },
    coverage: function () { return coverageOption(data.coverage); },
    perCompany: function () { return perCompanyOption(data.perCompany); },
    stock: function (view) { return stockOption(data.stock, view); }
  };

  // A chart's note can depend on which view is drawn (the flow's dropped count does). The
  // server rendered one per view; this shows the active one and hides the rest.
  function showNote(key, view) {
    Array.prototype.forEach.call(
      document.querySelectorAll('[data-note="' + key + '"]'),
      function (note) { note.hidden = note.getAttribute("data-view") !== view; });
  }

  document.body.classList.add("js-charts");
  var drawn = {};

  Array.prototype.forEach.call(document.querySelectorAll("[data-chart]"), function (el) {
    var key = el.getAttribute("data-chart");
    var build = BUILDERS[key];
    if (!build) return;
    // SVG rather than canvas: the marks end up in the DOM, so they print, scale and can be
    // inspected — and the published mirror is a file tree someone may well open offline.
    var chart = echarts.init(el, null, { renderer: "svg" });
    chart.setOption(build());
    drawn[key] = chart;
    window.addEventListener("resize", function () { chart.resize(); });

    // The table did its job while the chart was not there; fold it away now that it is.
    var panel = el.closest(".panel");
    var numbers = panel && panel.querySelector("details.numbers");
    if (numbers) numbers.removeAttribute("open");

    // Whichever view this chart's toggle starts on — the note that matches it.
    var first = document.querySelector('[data-toggle="' + key + '"] [data-view]');
    showNote(key, first ? first.getAttribute("data-view") : "full");
  });

  // §3's two views, switched without a page load.
  Array.prototype.forEach.call(document.querySelectorAll("[data-toggle]"), function (group) {
    var key = group.getAttribute("data-toggle");
    group.addEventListener("click", function (event) {
      var button = event.target.closest("[data-view]");
      if (!button || !drawn[key]) return;
      Array.prototype.forEach.call(group.querySelectorAll("[data-view]"), function (other) {
        other.classList.toggle("active", other === button);
      });
      var view = button.getAttribute("data-view");
      // `true` — replace rather than merge: a series that loses its areaStyle or its
      // stack would otherwise keep them, and the second view would draw the first.
      drawn[key].setOption(BUILDERS[key](view), true);
      showNote(key, view);
    });
  });
})();

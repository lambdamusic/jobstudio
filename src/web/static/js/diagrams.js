/* Mermaid diagrams in rendered markdown.
 *
 * A ```mermaid fence comes out of the markdown filter as
 * <pre><code class="language-mermaid">…</code></pre> — readable source with no script,
 * which is also what GitHub and editor previews start from. This file turns those blocks
 * into drawings, and only on pages that have one: Mermaid is 5MB, so it is fetched on
 * demand rather than in every page's <head>. The URL comes from this script tag's
 * `data-mermaid`, so Django's {% static %} stays the one place paths are decided.
 *
 * A diagram inside a closed <details> section has no size to lay text out against, so it
 * is drawn the first time its section opens rather than up front.
 */
(function () {
  "use strict";

  var me = document.currentScript;
  var src = me && me.getAttribute("data-mermaid");

  function load(cb) {
    if (window.mermaid) return cb();
    var s = document.createElement("script");
    s.src = src;
    s.onload = function () {
      window.mermaid.initialize({
        startOnLoad: false, theme: "neutral", securityLevel: "strict",
        flowchart: { htmlLabels: true, curve: "basis", wrappingWidth: 240, nodeSpacing: 28, rankSpacing: 44, padding: 10 },
        fontFamily: getComputedStyle(document.body).fontFamily
      });
      cb();
    };
    document.head.appendChild(s);
  }

  function swap(code) {
    var div = document.createElement("div");
    div.className = "mermaid diagram";
    div.textContent = code.textContent;
    code.parentElement.replaceWith(div);
    return div;
  }

  function draw(nodes) {
    if (!nodes.length) return;
    load(function () { window.mermaid.run({ nodes: nodes }); });
  }

  document.addEventListener("DOMContentLoaded", function () {
    var blocks = Array.prototype.slice.call(
      document.querySelectorAll("pre > code.language-mermaid"));
    if (!blocks.length || !src) return;
    var now = [];
    blocks.forEach(function (code) {
      var div = swap(code);
      var closed = div.closest("details:not([open])");
      if (!closed) { now.push(div); return; }
      closed.addEventListener("toggle", function once() {
        if (!closed.open) return;
        closed.removeEventListener("toggle", once);
        draw([div]);
      });
    });
    draw(now);
  });
})();

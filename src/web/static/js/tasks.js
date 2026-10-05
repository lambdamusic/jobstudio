/* Live checkboxes for `- [ ]` tasks in rendered markdown (local app only).
 *
 * Each box carries the file it came from (`data-source`) and its order in that file
 * (`data-task`); ticking it POSTs to /actions/task/, which rewrites the marker on disk.
 * If the write fails the box goes back to how it was — the page never claims a tick the
 * file does not have.
 */
(function () {
  "use strict";
  var meta = document.querySelector('meta[name="csrf-token"]');
  var token = meta ? meta.getAttribute("content") : "";

  document.addEventListener("change", function (e) {
    var box = e.target;
    if (!box.matches || !box.matches("input.task-box[data-source]")) return;
    var body = new FormData();
    body.append("source", box.getAttribute("data-source"));
    body.append("index", box.getAttribute("data-task"));
    body.append("checked", box.checked ? "true" : "false");
    box.disabled = true;
    fetch("/actions/task/", {
      method: "POST", body: body, credentials: "same-origin",
      headers: { "X-CSRFToken": token }
    })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok && j.ok, j: j }; }); })
      .then(function (res) {
        if (!res.ok) throw new Error(res.j.error || "save failed");
        box.title = "Saved to the file";
      })
      .catch(function (err) {
        box.checked = !box.checked;
        box.title = "Not saved: " + err.message;
      })
      .then(function () { box.disabled = false; });
  });
})();

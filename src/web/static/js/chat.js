/* The chat panel (prototype, branch `chat-panel`).
 *
 * Each message POSTs to /actions/chat/, which runs one headless `claude -p` turn and
 * streams NDJSON back (event types in apps/tracker/chat.py). The session id and the
 * transcript are kept in sessionStorage, so the conversation follows you from page to
 * page within the tab; "New" forgets both. The session itself lives in Claude Code's
 * store, so it can also be resumed in a terminal with `claude --resume <id>`.
 */
(function () {
  "use strict";
  var panel = document.getElementById("chat-panel");
  if (!panel) return;
  var toggle = document.getElementById("chat-toggle");
  var log = panel.querySelector(".chat-log");
  var form = panel.querySelector("form");
  var input = form.querySelector("textarea");
  var send = form.querySelector("button[type=submit]");
  var sid = panel.querySelector(".chat-sid");
  var meta = document.querySelector('meta[name="csrf-token"]');
  var token = meta ? meta.getAttribute("content") : "";
  var KEY = "jobstudio.chat";

  function load() {
    try { return JSON.parse(sessionStorage.getItem(KEY)) || {}; } catch (e) { return {}; }
  }
  function save() {
    try { sessionStorage.setItem(KEY, JSON.stringify(state)); } catch (e) {}
  }
  var state = load();
  state.turns = state.turns || [];

  function bubble(role, text) {
    var el = document.createElement("div");
    el.className = "chat-msg chat-" + role;
    el.textContent = text;
    log.appendChild(el);
    log.scrollTop = log.scrollHeight;
    return el;
  }
  function showSid() {
    sid.textContent = state.session ? "session " + state.session.slice(0, 8) : "";
    sid.title = state.session ? "claude --resume " + state.session : "";
  }
  function render() {
    log.textContent = "";
    state.turns.forEach(function (t) { bubble(t.role, t.text); });
    showSid();
  }

  function setOpen(open) {
    document.documentElement.classList.toggle("chat-open", open);
    toggle.setAttribute("aria-expanded", open ? "true" : "false");
    state.open = open; save();
    if (open) input.focus();
  }
  toggle.addEventListener("click", function () { setOpen(!state.open); });
  panel.querySelector(".chat-close").addEventListener("click", function () { setOpen(false); });
  panel.querySelector(".chat-new").addEventListener("click", function () {
    state = { turns: [], open: true }; save(); render(); input.focus();
  });

  input.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); }
  });

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var text = input.value.trim();
    if (!text || send.disabled) return;
    input.value = "";
    state.turns.push({ role: "user", text: text }); save();
    bubble("user", text);
    var out = bubble("assistant", "");
    out.classList.add("pending");
    var reply = "";
    send.disabled = true;

    var body = new FormData();
    body.append("message", text);
    body.append("session", state.session || "");
    body.append("page", location.pathname + location.hash);

    function handle(ev) {
      if (ev.t === "session") { state.session = ev.id; save(); showSid(); }
      else if (ev.t === "text") {
        reply += ev.d;
        out.textContent = reply.replace(/^\s+/, "");
      } else if (ev.t === "tool") {
        var tool = document.createElement("div");
        tool.className = "chat-tool";
        tool.textContent = "⚙ " + ev.name + (ev.d ? " · " + ev.d : "");
        log.insertBefore(tool, out);
      } else if (ev.t === "error") {
        reply += "\n\n[error] " + ev.d;
        out.textContent = reply.trim();
      } else if (ev.t === "done") {
        out.title = (ev.ms ? (ev.ms / 1000).toFixed(1) + "s" : "") +
                    (ev.cost != null ? " · ~$" + ev.cost.toFixed(3) + " equiv." : "");
      }
      log.scrollTop = log.scrollHeight;
    }

    fetch("/actions/chat/", {
      method: "POST", body: body, credentials: "same-origin",
      headers: { "X-CSRFToken": token }
    }).then(function (r) {
      if (!r.ok) return r.json().then(function (j) { throw new Error(j.error || r.status); });
      var reader = r.body.getReader();
      var dec = new TextDecoder();
      var buf = "";
      function pump() {
        return reader.read().then(function (res) {
          if (res.done) return;
          buf += dec.decode(res.value, { stream: true });
          var lines = buf.split("\n");
          buf = lines.pop();
          lines.forEach(function (l) { if (l) handle(JSON.parse(l)); });
          return pump();
        });
      }
      return pump();
    }).catch(function (err) {
      reply += "\n\n[error] " + err.message;
      out.textContent = reply.trim();
    }).then(function () {
      out.classList.remove("pending");
      state.turns.push({ role: "assistant", text: reply.trim() }); save();
      send.disabled = false;
      input.focus();
    });
  });

  render();
  if (state.open) setOpen(true);
})();

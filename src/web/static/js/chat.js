/* The chat panel (prototype, branch `chat-panel`).
 *
 * Each message POSTs to /actions/chat/, which runs one headless `claude -p` turn and
 * streams NDJSON back (event types in apps/tracker/chat.py). The reply streams in as
 * plain text and is swapped for the server's rendered markdown when the turn ends.
 *
 * The session id, the transcript and the permission rules allowed so far are kept in
 * sessionStorage, so the conversation follows you from page to page within the tab;
 * "New" forgets all three. The session itself lives in Claude Code's store, so it can
 * also be resumed in a terminal with `claude --resume <id>`.
 */
(function () {
  "use strict";
  var panel = document.getElementById("chat-panel");
  if (!panel) return;
  var toggle = document.getElementById("chat-toggle");
  var log = panel.querySelector(".chat-log");
  var form = panel.querySelector("form");
  var input = form.querySelector("textarea");
  var sendBtn = form.querySelector("button[type=submit]");
  var sid = panel.querySelector(".chat-sid");
  var meta = document.querySelector('meta[name="csrf-token"]');
  var token = meta ? meta.getAttribute("content") : "";
  var KEY = "jobstudio.chat";
  var busy = false;

  function load() {
    try { return JSON.parse(sessionStorage.getItem(KEY)) || {}; } catch (e) { return {}; }
  }
  function save() {
    try { sessionStorage.setItem(KEY, JSON.stringify(state)); } catch (e) {}
  }
  var state = load();
  state.turns = state.turns || [];
  state.allowed = state.allowed || [];

  function scroll() { log.scrollTop = log.scrollHeight; }

  // A turn is {role, text} or {role, html} for a reply, {role: "tool", text} for a tool
  // line, or {role: "denied", items} for the refusals a turn ended with.
  function draw(t) {
    var el = document.createElement("div");
    if (t.role === "tool") {
      el.className = "chat-tool";
      el.textContent = t.text;
    } else if (t.role === "denied") {
      el = deniedCard(t);
    } else {
      el.className = "chat-msg chat-" + t.role;
      if (t.html) { el.innerHTML = t.html; el.classList.add("prose"); }
      else el.textContent = t.text || "";
    }
    log.appendChild(el);
    scroll();
    return el;
  }

  function deniedCard(t) {
    var card = document.createElement("div");
    card.className = "chat-denied";
    var head = document.createElement("div");
    head.textContent = "Claude was refused " + (t.items.length > 1 ? "these" : "this") + ":";
    card.appendChild(head);
    t.items.forEach(function (it) {
      var row = document.createElement("code");
      row.textContent = it.rule;
      card.appendChild(row);
    });
    if (t.done) {
      var note = document.createElement("div");
      note.className = "chat-denied-note";
      note.textContent = "Allowed for this conversation.";
      card.appendChild(note);
      return card;
    }
    var btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = "Allow & retry";
    btn.title = "Allowed for the rest of this conversation only — not saved to a settings file";
    btn.addEventListener("click", function () {
      if (busy) return;
      t.items.forEach(function (it) {
        if (state.allowed.indexOf(it.rule) < 0) state.allowed.push(it.rule);
      });
      t.done = true; save();
      card.replaceWith(deniedCard(t));
      send("I've allowed " + t.items.map(function (it) { return "`" + it.rule + "`"; }).join(", ") +
           ". Please retry what was refused.");
    });
    card.appendChild(btn);
    return card;
  }

  function showSid() {
    sid.textContent = state.session ? "session " + state.session.slice(0, 8) : "";
    sid.title = state.session ? "claude --resume " + state.session : "";
  }
  function render() {
    log.textContent = "";
    state.turns.forEach(draw);
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
    if (busy) return;
    state = { turns: [], allowed: [], open: true }; save(); render(); input.focus();
  });

  input.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); }
  });
  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var text = input.value.trim();
    if (!text || busy) return;
    input.value = "";
    send(text);
  });

  function push(t) { state.turns.push(t); save(); return draw(t); }

  function send(text) {
    busy = true; sendBtn.disabled = true;
    push({ role: "user", text: text });
    var out = draw({ role: "assistant", text: "" });
    out.classList.add("pending");
    var reply = "", html = "", denied = null;

    var body = new FormData();
    body.append("message", text);
    body.append("session", state.session || "");
    body.append("page", location.pathname + location.hash);
    state.allowed.forEach(function (r) { body.append("allow", r); });

    function handle(ev) {
      if (ev.t === "session") { state.session = ev.id; save(); showSid(); }
      else if (ev.t === "text") {
        reply += ev.d;
        out.textContent = reply.replace(/^\s+/, "");
      } else if (ev.t === "tool") {
        // Tool lines are recorded before the reply they belong to, so a reload draws
        // them in the order they happened.
        var t = { role: "tool", text: "⚙ " + ev.name + (ev.d ? " · " + ev.d : "") };
        state.turns.push(t); save();
        log.insertBefore(draw(t), out);
      } else if (ev.t === "html") {
        html = ev.d;
        out.innerHTML = html; out.classList.add("prose");
      } else if (ev.t === "denied") {
        denied = ev.items;
      } else if (ev.t === "error") {
        reply += "\n\n[error] " + ev.d;
        html = "";
        out.classList.remove("prose");
        out.textContent = reply.trim();
      } else if (ev.t === "done") {
        out.title = (ev.ms ? (ev.ms / 1000).toFixed(1) + "s" : "") +
                    (ev.cost != null ? " · ~$" + ev.cost.toFixed(3) + " equiv." : "");
      }
      scroll();
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
      html = "";
      out.classList.remove("prose");
      out.textContent = reply.trim();
    }).then(function () {
      out.classList.remove("pending");
      state.turns.push(html ? { role: "assistant", html: html }
                            : { role: "assistant", text: reply.trim() });
      save();
      if (denied) push({ role: "denied", items: denied });
      busy = false; sendBtn.disabled = false;
      input.focus();
    });
  }

  render();
  if (state.open) setOpen(true);
})();

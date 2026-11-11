/* The chat panel (prototype, branch `chat-panel`).
 *
 * Each message POSTs to /actions/chat/, which runs one headless `claude -p` turn and
 * streams NDJSON back (event types in apps/tracker/chat.py). The reply streams in as
 * plain text and is swapped for the server's rendered markdown when the turn ends.
 *
 * Opened from "Ask Claude" at the top of the sidebar, or ⌘K / Ctrl+K anywhere.
 *
 * A bar under the header shows how full the context is, the plan's five-hour and weekly
 * usage, and the conversation's API-price equivalent, updated after every turn.
 *
 * The session id, the transcript, the usage and the permission rules allowed so far are
 * kept in sessionStorage, so the conversation follows you from page to page within the tab;
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
  var bar = panel.querySelector(".chat-usage");
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
  function kTokens(n) {
    if (n >= 1e6) return +(n / 1e6).toFixed(1) + "M";
    return n >= 1000 ? Math.round(n / 1000) + "k" : String(n);
  }
  function resetTime(ts) {
    if (!ts) return "";
    var d = new Date(ts * 1000);
    var sameDay = d.toDateString() === new Date().toDateString();
    return sameDay ? d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
                   : d.toLocaleDateString([], { weekday: "short", hour: "2-digit", minute: "2-digit" });
  }
  // One segment: a label, a figure, and a tooltip with the detail. Past 80% it turns gold.
  function segment(label, pct, text, tip) {
    var el = document.createElement("span");
    el.className = "chat-meter" + (pct >= 80 ? " high" : "");
    el.title = tip;
    var b = document.createElement("b");
    b.textContent = label;
    el.appendChild(b);
    el.appendChild(document.createTextNode(" " + text));
    return el;
  }
  function showUsage() {
    var u = state.usage, l = state.limits;
    bar.textContent = "";
    if (u && u.context) {
      var pct = u.window ? Math.round(100 * u.context / u.window) : 0;
      bar.appendChild(segment("Context", pct,
        kTokens(u.context) + (u.window ? " / " + kTokens(u.window) : ""),
        "Tokens the next turn starts from" + (u.window ? " (" + pct + "% of the window)" : "")));
    }
    if (l) {
      [["five_hour", "5h"], ["seven_day", "Week"]].forEach(function (w) {
        var v = l[w[0]];
        if (v) bar.appendChild(segment(w[1], v.pct, v.pct + "%",
          "Plan usage in this window, resets " + resetTime(v.resets)));
      });
    }
    if (state.cost) {
      bar.appendChild(segment("Chat", 0, "~$" + state.cost.toFixed(2),
        "API-price equivalent of this conversation so far — not billed on a subscription"));
    }
    bar.hidden = !bar.firstChild;
  }
  function render() {
    log.textContent = "";
    state.turns.forEach(draw);
    showSid();
    showUsage();
  }

  function setOpen(open) {
    document.documentElement.classList.toggle("chat-open", open);
    toggle.setAttribute("aria-expanded", open ? "true" : "false");
    toggle.classList.toggle("active", open);
    state.open = open; save();
    if (open) input.focus();
  }
  toggle.addEventListener("click", function (e) { e.preventDefault(); setOpen(!state.open); });
  panel.querySelector(".chat-close").addEventListener("click", function () { setOpen(false); });
  // ⌘K (Ctrl+K off a Mac) opens and closes the panel from anywhere, inputs included;
  // Escape closes it while focus is inside.
  document.addEventListener("keydown", function (e) {
    if ((e.metaKey || e.ctrlKey) && !e.altKey && !e.shiftKey && e.key.toLowerCase() === "k") {
      e.preventDefault();
      setOpen(!state.open);
    } else if (e.key === "Escape" && state.open && panel.contains(document.activeElement)) {
      setOpen(false);
      toggle.focus();
    }
  });
  panel.querySelector(".chat-new").addEventListener("click", function () {
    if (busy) return;
    // The plan limits belong to the account, not the conversation, so they stay.
    state = { turns: [], allowed: [], open: true, limits: state.limits };
    save(); render(); input.focus();
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

  // Shown at the foot of the log while a turn runs, so a long task between bubbles
  // still looks alive. Not part of the transcript.
  var working = document.createElement("div");
  working.className = "chat-working";
  working.textContent = "working…";

  // Record a turn and draw it at the end of the log, above the indicator.
  function add(t) {
    state.turns.push(t); save();
    var el = draw(t);
    if (working.parentNode) log.appendChild(working);
    scroll();
    return el;
  }

  function send(text) {
    busy = true; sendBtn.disabled = true;
    add({ role: "user", text: text });
    log.appendChild(working); scroll();
    var cur = null, curEl = null, denied = null;

    // The message in progress. It is recorded as it opens, so the tool calls it makes
    // land after it on a reload, and finished when its html arrives — or kept as plain
    // text if the stream stops first.
    function close() {
      if (!cur) return;
      if (!cur.html) cur.text = cur.text.trim();
      if (!cur.html && !cur.text) {
        state.turns.splice(state.turns.indexOf(cur), 1);
        curEl.remove();
      }
      save();
      cur = curEl = null;
    }
    function fail(msg) {
      close();
      add({ role: "assistant", text: "[error] " + msg });
    }

    var body = new FormData();
    body.append("message", text);
    body.append("session", state.session || "");
    body.append("page", location.pathname + location.hash);
    state.allowed.forEach(function (r) { body.append("allow", r); });

    function handle(ev) {
      if (ev.t === "session") { state.session = ev.id; save(); showSid(); }
      else if (ev.t === "message") {
        close();
        cur = { role: "assistant", text: "" };
        curEl = add(cur);
      } else if (ev.t === "text" && cur) {
        cur.text += ev.d; save();
        curEl.textContent = cur.text.replace(/^\s+/, "");
      } else if (ev.t === "html" && cur) {
        cur.html = ev.d; delete cur.text;
        curEl.innerHTML = ev.d; curEl.classList.add("prose");
        close();
      } else if (ev.t === "tool") {
        add({ role: "tool", text: "⚙ " + ev.name + (ev.d ? " · " + ev.d : "") });
      } else if (ev.t === "usage") {
        state.usage = ev;
        state.cost = (state.cost || 0) + (ev.cost || 0);
        save(); showUsage();
      } else if (ev.t === "limits") {
        state.limits = ev; save(); showUsage();
      } else if (ev.t === "denied") {
        denied = ev.items;
      } else if (ev.t === "error") {
        fail(ev.d);
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
      fail(err.message);
    }).then(function () {
      close();
      working.remove();
      if (denied) add({ role: "denied", items: denied });
      busy = false; sendBtn.disabled = false;
      input.focus();
    });
  }

  render();
  if (state.open) setOpen(true);
})();

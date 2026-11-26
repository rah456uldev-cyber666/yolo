// Sends questions without reloading the page and shows a typing indicator.
// Without JavaScript the form still works as a normal POST.
(function () {
  var form = document.getElementById("chat-form");
  var box = document.getElementById("chat-box");
  var prompt = document.getElementById("prompt");
  var send = document.getElementById("send");
  var csrf = document.querySelector('meta[name="csrf-token"]').content;

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text; // textContent = no HTML injection
    return node;
  }

  function addMessage(msg) {
    var empty = document.getElementById("empty-state");
    if (empty) empty.remove();
    var wrap = el("div", "message " + msg.role);
    wrap.appendChild(el("div", "role", msg.role === "user" ? "You" : "Medibot"));
    if (msg.notice) wrap.appendChild(el("div", "notice", "⚠️ " + msg.notice));
    var content = el("div", "content");
    (msg.content || "").split("\n").forEach(function (line, i) {
      if (i) content.appendChild(document.createElement("br"));
      content.appendChild(document.createTextNode(line));
    });
    wrap.appendChild(content);
    if (msg.diseases && msg.diseases.length) {
      var rel = el("div", "related", "Disease library: ");
      msg.diseases.forEach(function (d, i) {
        if (i) rel.appendChild(document.createTextNode(", "));
        var a = el("a", null, d.name);
        a.href = "/diseases/" + encodeURIComponent(d.slug);
        rel.appendChild(a);
      });
      wrap.appendChild(rel);
    }
    if (msg.sources && msg.sources.length) {
      var det = el("details", "sources");
      det.appendChild(el("summary", null, "Sources (" + msg.sources.length + ")"));
      var ul = el("ul");
      msg.sources.forEach(function (s) {
        var li = el("li");
        li.appendChild(el("strong", null, s.source + ", page " + s.page));
        li.appendChild(document.createTextNode(": “" + s.snippet + "…”"));
        ul.appendChild(li);
      });
      det.appendChild(ul);
      wrap.appendChild(det);
    }
    box.appendChild(wrap);
    wrap.scrollIntoView({ behavior: "smooth", block: "end" });
    return wrap;
  }

  function ask(question) {
    addMessage({ role: "user", content: question });
    var typing = addMessage({ role: "assistant", content: "Searching the encyclopedia" });
    typing.classList.add("typing");
    send.disabled = true;
    fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
      body: JSON.stringify({ question: question })
    })
      .then(function (r) { return r.json().then(function (body) { return { ok: r.ok, body: body }; }); })
      .then(function (res) {
        typing.remove();
        addMessage(res.ok ? res.body : { role: "assistant", content: res.body.error || "Something went wrong." });
      })
      .catch(function () {
        typing.remove();
        addMessage({ role: "assistant", content: "Network error. Please try again." });
      })
      .finally(function () { send.disabled = false; prompt.focus(); });
  }

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var q = prompt.value.trim();
    if (!q || send.disabled) return;
    prompt.value = "";
    ask(q);
  });

  prompt.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); }
  });

  document.querySelectorAll(".chip").forEach(function (chip) {
    chip.addEventListener("click", function () { ask(chip.dataset.q); });
  });

  var last = box.lastElementChild;
  if (last) last.scrollIntoView({ block: "end" });
})();

"use strict";
// deck.js — the public share page (/deck/<slug>). Loads the class from /api/deck/<slug> and hands it to
// render.js's read-only renderer, which fills the same #result markup the app uses. No app.js here: no
// session, no feedback widgets, nothing mutating. The only interaction is Copy code, because importing a
// code is the ONLY way the mod can load a shared class.
//
// The slug is not inlined into this file (the CSP forbids inline script) — it rides on #deck's data-*.

(function () {
  const root = document.getElementById("deck");
  if (!root) { return; }
  const api = root.dataset.api || ("/api/deck/" + encodeURIComponent(root.dataset.slug || ""));

  function dead(msg) {
    root.innerHTML = "";
    const card = document.createElement("section");
    card.className = "card";
    const h = document.createElement("h1");
    h.textContent = "This class link is no longer valid";
    const p = document.createElement("p");
    p.className = "muted";
    p.textContent = msg;
    const nav = document.createElement("p");
    const forge = document.createElement("a");
    forge.className = "btn primary";
    forge.href = "/app";
    forge.textContent = "Forge your own";
    const mod = document.createElement("a");
    mod.className = "btn";
    mod.href = "/download";
    mod.textContent = "Get the mod";
    nav.append(forge, document.createTextNode(" "), mod);
    card.append(h, p, nav);
    root.appendChild(card);
  }

  function show(cls) {
    // renderResult() (the app path) pokes #spinner, which this page has no reason to carry — give it a
    // hidden one so a render.js that hasn't grown renderClassView yet still works here.
    if (!document.getElementById("spinner")) {
      const s = document.createElement("div");
      s.id = "spinner";
      s.className = "hidden";
      root.appendChild(s);
    }
    const render = window.renderClassView || window.renderResult;
    render(cls, { readOnly: true });
    const btn = document.getElementById("copy-code");
    if (btn) {
      btn.addEventListener("click", () => {
        const box = document.getElementById("r-code");
        if (window.copy) { window.copy(box.value); }
        else { navigator.clipboard.writeText(box.value); }
      });
    }
    const name = cls.character?.name || cls.name;
    if (name) { document.title = name + " — BLANK the spire"; }
  }

  fetch(api, { headers: { "Accept": "application/json" } })
    .then((r) => {
      if (!r.ok) { throw new Error("gone"); }
      return r.json();
    })
    .then(show)
    .catch(() => dead("It may have been deleted, or the link was mistyped. "
      + "Ask whoever shared it for a fresh link — or forge your own class."));
})();

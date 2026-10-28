"use strict";
// deck.js — the public share page (/deck/<slug>). Loads the class from /api/deck/<slug> and hands it to
// render.js's read-only renderer, which fills the same #result markup the app uses. No app.js here: no
// session, no feedback widgets, nothing mutating. Interactions: Copy code (importing a code is the ONLY way
// the mod can load a shared class) and "Forge your own twist", which prefills the app's concept box.
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
    h.textContent = BTS_I18N.t("deck.dead.title");
    const p = document.createElement("p");
    p.className = "muted";
    p.textContent = msg;
    const nav = document.createElement("p");
    const forge = document.createElement("a");
    forge.className = "btn primary";
    forge.href = "/app";
    forge.textContent = BTS_I18N.t("deck.dead.forge");
    const mod = document.createElement("a");
    mod.className = "btn";
    mod.href = "/download";
    mod.textContent = BTS_I18N.t("deck.dead.get_mod");
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
    if (name) { document.title = BTS_I18N.t("common.title_suffix", { page: name }); }
    if (cls.featured === true) { markFeatured(); }
    const sendPc = document.getElementById("send-pc");
    if (sendPc && window.sendToPc) {
      const url = location.origin + "/deck/" + encodeURIComponent(root.dataset.slug || "");
      sendPc.addEventListener("click", () => window.sendToPc(name, url));
    }
    const remix = document.getElementById("remix");
    if (remix) { remix.addEventListener("click", () => startRemix(cls, name)); }
  }

  // Classes in The Archive are curated, so the page speaks to a stranger rather than "someone shared this".
  function markFeatured() {
    const lede = document.getElementById("lede");
    if (lede) {
      lede.innerHTML = BTS_I18N.html("deck.lede_featured");
    }
    const sub = document.querySelector("header .sub");
    if (sub) { sub.textContent = BTS_I18N.t("deck.header.sub_featured"); }
  }

  // "Forge your own twist": hand the concept to the app via localStorage (app.js boot() reads bts_prefill
  // once, fills #concept, then deletes it). /login bounces signed-in visitors on to /app, so it fits both.
  function startRemix(cls, name) {
    const prefill = {
      concept: cls.concept || name || "",
      name: name || "",
      from: root.dataset.slug || "",
    };
    try { localStorage.setItem("bts_prefill", JSON.stringify(prefill)); } catch (_) { /* no store */ }
    location.href = "/login";
  }

  // Every string (render.js included) comes from i18n.js, so the page renders once its json is in.
  Promise.all([
    fetch(api, { headers: { "Accept": "application/json" } }).then((r) => {
      if (!r.ok) { throw new Error("gone"); }
      return r.json();
    }),
    BTS_I18N.ready,
  ])
    .then(([cls]) => show(cls))
    .catch(() => BTS_I18N.ready.then(() => dead(BTS_I18N.t("deck.dead.body"))));
})();

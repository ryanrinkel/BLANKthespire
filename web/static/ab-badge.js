"use strict";

// Admin-only experiment badge (docs/plans/AB_TESTING_PLAN.md 3.10 item 1). Loaded on the pages that can carry
// an experiment (landing.html, signin.html), next to webview.js. It asks /api/me; only an ADMIN's answer
// carries user.experiments (every live experiment in web/experiments.py), and the badge shows the ones whose
// page is this path: "🧪 hero · you see b · see a · see b · results". The arm shown comes from the <html
// data-ab="hero:b"> the server stamped (which reflects a ?ab= preview), falling back to the arm the server
// computes for this IP + UA. For everyone else nothing is built: no element, no markup in the HTML.
// Wrapped so its names stay out of the global scope the other classic scripts share.
(() => {
  function shownArms() {
    const out = {};
    const raw = (document.documentElement.dataset.ab || "").trim();
    for (const item of raw.split(/\s+/)) {
      const i = item.indexOf(":");
      if (i > 0) out[item.slice(0, i)] = item.slice(i + 1);
    }
    return out;
  }

  function link(text, href) {
    const a = document.createElement("a");
    a.href = href;
    a.target = "_self";
    a.textContent = text;
    return a;
  }

  function render(exps) {
    const shown = shownArms();
    const wrap = document.createElement("div");
    wrap.className = "ab-badges";
    for (const e of exps) {
      const pill = document.createElement("div");
      pill.className = "ab-badge";
      pill.title = `${e.hypothesis || ""}\nday ${e.day} of ${e.of}`;
      const arm = shown[e.name] || e.arm || "?";
      pill.appendChild(document.createTextNode(`🧪 ${e.name} · you see ${arm}`));
      for (const a of e.arms || []) {
        pill.appendChild(document.createTextNode(" · "));
        pill.appendChild(link(`see ${a}`, `${location.pathname}?ab=${encodeURIComponent(e.name)}:${encodeURIComponent(a)}`));
      }
      pill.appendChild(document.createTextNode(" · "));
      pill.appendChild(link("results", "/app#account"));
      wrap.appendChild(pill);
    }
    document.body.appendChild(wrap);
  }

  async function boot() {
    try {
      const me = await (await fetch("/api/me")).json();
      // /api/me hands out a sign-up bonus notice ONCE; if this read was first, park it like the page would.
      if (window.BTS_EVENT && typeof window.BTS_EVENT.keepWelcome === "function") window.BTS_EVENT.keepWelcome(me);
      const u = me && me.user;
      if (!u || !u.admin || !Array.isArray(u.experiments)) return;
      const here = u.experiments.filter((e) => e && e.page === location.pathname);
      if (here.length) render(here);
    } catch (_) { /* the badge is a convenience: any failure leaves the page as it is */ }
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();

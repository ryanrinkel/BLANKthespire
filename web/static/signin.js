"use strict";

// The /login chooser. The server decides which providers exist (a provider only registers when its
// CLIENT_ID/SECRET pair is set), so the buttons are built from /api/me.providers rather than hardcoded —
// a deploy with only Discord credentials shows one button, and nothing here needs touching to add a provider.

const LABELS = { google: "Google", discord: "Discord", github: "GitHub" };

const el = (id) => document.getElementById(id);

(async () => {
  let me = null;
  try {
    me = await (await fetch("/api/me")).json();
  } catch (_) { /* offline or the API is down — fall through to the "not configured" copy */ }

  if (me && me.user) { window.location.replace("/app"); return; }

  const providers = (me && me.providers) || [];
  const box = el("providers");
  for (const p of providers) {
    const a = document.createElement("a");
    a.className = "btn primary";
    a.href = "/login/" + p;
    a.textContent = "Continue with " + (LABELS[p] || p);
    box.appendChild(a);
  }

  if (me && me.email_login) el("email-form").classList.remove("hidden");
  if (me && me.dev_auth) el("dev-signin").classList.remove("hidden");
  if (!providers.length && !(me && (me.dev_auth || me.email_login))) {
    el("none").classList.remove("hidden");
  }
})();

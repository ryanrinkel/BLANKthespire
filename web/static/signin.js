"use strict";

// The /login chooser. The server decides which providers exist (a provider only registers when its
// CLIENT_ID/SECRET pair is set), so the buttons are built from /api/me.providers rather than hardcoded —
// a deploy with only Discord credentials shows one button, and nothing here needs touching to add a provider.

const LABELS = { google: "Google", discord: "Discord", github: "GitHub" };

const el = (id) => document.getElementById(id);

// The magic link: POST the address, then swap the form for "check your inbox". The server answers the same
// way whether it sent anything or not (rate limit, bad syntax), so there is nothing to branch on — and
// nothing here ever reveals whether an account exists.
function wireEmailForm() {
  const form = el("email-form");
  const button = form.querySelector("button");
  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const email = el("email").value.trim();
    if (!email) return;
    el("email-error").classList.add("hidden");
    button.disabled = true;
    button.textContent = "Sending…";

    let data = null;
    try {
      const r = await fetch("/api/auth/email/start", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Requested-With": "fetch" },
        body: JSON.stringify({ email }),
      });
      data = await r.json();
    } catch (_) { /* offline: fall through to the error hint */ }

    if (!data || !data.ok) {
      button.disabled = false;
      button.textContent = "Email me a link";
      el("email-error").classList.remove("hidden");
      return;
    }

    const sent = document.createElement("div");
    sent.className = "signin-sent";
    const p = document.createElement("p");
    p.textContent = "Check your inbox — the link expires in 15 minutes.";
    sent.appendChild(p);
    if (data.link) {  // dev auth with no mail provider: the link comes back instead of being sent
      const a = document.createElement("a");
      a.className = "btn primary";
      a.href = data.link;
      a.textContent = "Open the sign-in link (local dev)";
      sent.appendChild(a);
    }
    form.replaceWith(sent);
  });
}

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

  if (me && me.email_login) {
    el("email-form").classList.remove("hidden");
    if (providers.length) el("or").classList.remove("hidden");
    wireEmailForm();
  }
  if (me && me.dev_auth) el("dev-signin").classList.remove("hidden");
  if (!providers.length && !(me && (me.dev_auth || me.email_login))) {
    el("none").classList.remove("hidden");
  }
})();

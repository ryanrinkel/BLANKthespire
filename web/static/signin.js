"use strict";

// The /login chooser. The server decides which providers exist (a provider only registers when its
// CLIENT_ID/SECRET pair is set), so the buttons are built from /api/me.providers rather than hardcoded —
// a deploy with only Discord credentials shows one button, and nothing here needs touching to add a provider.

const LABELS = { google: "Google", discord: "Discord", github: "GitHub" };

// Link mode (/login?link=1, from the Account tab's "Link another"): the visitor IS signed in and stays so —
// the provider flow they pick attaches its identity to their account (auth._resolve_identity rule 2) and
// comes back to /app#account. Without the flag a signed-in visitor never reaches this page (the server
// bounces them to /app), so everything below only has to tell the two apart.
const LINKING = new URLSearchParams(location.search).get("link") === "1";

const el = (id) => document.getElementById(id);
// UI strings come from i18n.js (loaded first); the page init below awaits BTS_I18N.ready before using them.
const t = (key, vars) => BTS_I18N.t(key, vars);

// The "try a featured class" escape hatch is for visitors without an account; linking is for members.
if (LINKING) el("try-instead").classList.add("hidden");

// In an in-app browser (YouTube, Instagram, ...: webview.js) Google sign-in cannot work — Google refuses
// embedded webviews — so the button is dropped, and the email magic link goes first with a line saying why:
// Mail opens the link in the real browser, where the session then lives. GitHub (which does not block
// webviews) stays, below the form. Plus a one-tap hand-off to Safari / Chrome, with the menu route always
// spelled out under it because the x-safari-https scheme is not guaranteed to do anything.
const WV = window.BTS_WEBVIEW || { any: false };
const WEBVIEW_BLOCKED = new Set(["google"]);

function webviewLayout(emailLogin) {
  el("webview-head").textContent = t("signin.webview.head", { where: WV.where });
  if (WV.openUrl) {
    const open = el("open-browser");
    open.href = WV.openUrl;
    open.textContent = t("signin.open_browser", { browser: WV.browser });
    open.classList.remove("hidden");
    el("webview-menu").textContent = WV.menuHint + ".";
    el("webview-menu").classList.remove("hidden");
  }
  el("webview-box").classList.remove("hidden");
  if (!LINKING) el("lede").classList.add("hidden");  // link mode keeps its "signed in as ..." lede
  if (emailLogin) {
    // DOM order becomes: webview box, email form, "or", provider buttons.
    const box = el("providers");
    box.before(el("email-form"));
    box.before(el("or"));
    el("email-form").querySelector("label").textContent = t("signin.webview.email_label", { browser: WV.browser });
    el("email-form").classList.add("signin-email-first");
    el("email-form").querySelector("button").classList.add("primary");  // the way in here: make it the loud one
  }
}

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
    button.textContent = t("signin.email.sending");

    let data = null;
    try {
      const r = await fetch("/api/auth/email/start", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Requested-With": "fetch" },
        body: JSON.stringify({ email, lang: BTS_I18N.lang }),  // the magic-link email's language
      });
      data = await r.json();
    } catch (_) { /* offline: fall through to the error hint */ }

    if (!data || !data.ok) {
      button.disabled = false;
      button.textContent = t("signin.email.button");
      el("email-error").classList.remove("hidden");
      return;
    }

    const sent = document.createElement("div");
    sent.className = "signin-sent";
    const p = document.createElement("p");
    p.textContent = t("signin.email.sent");
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
    [me] = await Promise.all([fetch("/api/me").then((r) => r.json()), BTS_I18N.ready]);
  } catch (_) { /* offline or the API is down — fall through to the "not configured" copy */ }
  await BTS_I18N.ready;

  // A sign-up event (signup-event.js): park a welcome notice this read may have consumed before bouncing to
  // the app, and show the event ribbon under the lede to a signed-out visitor only.
  const EV = window.BTS_EVENT;
  if (EV) {
    EV.keepWelcome(me);
    EV.ribbon(me, (node) => el("lede").after(node));
  }

  if (me && me.user && !LINKING) { window.location.replace("/app"); return; }

  const owned = new Set(((me && me.user && me.user.identities) || []).map((i) => i.provider));
  if (me && me.user) {
    el("title").textContent = t("signin.link.title");
    el("lede").textContent = t("signin.link.lede", { who: me.user.name || me.user.email || t("signin.link.who_fallback") });
    el("back-app").classList.remove("hidden");
  }

  // In link mode the account's existing providers are dropped: re-running one of them would just sign in
  // again (rule 1) and link nothing.
  const providers = ((me && me.providers) || [])
    .filter((p) => !owned.has(p) && !(WV.any && WEBVIEW_BLOCKED.has(p)));
  if (WV.any) webviewLayout(Boolean(me && me.email_login));
  const box = el("providers");
  for (const p of providers) {
    const a = document.createElement("a");
    // In a webview the email button is the primary one; the provider buttons step back to plain.
    a.className = WV.any && me && me.email_login ? "btn" : "btn primary";
    a.href = "/login/" + p;
    a.textContent = t(LINKING ? "signin.provider.link" : "signin.provider.continue", { provider: LABELS[p] || p });
    box.appendChild(a);
  }

  if (me && me.email_login) {
    // Offered in link mode too: a magic link clicked while signed in attaches an email identity (rule 2).
    el("email-form").classList.remove("hidden");
    if (providers.length) el("or").classList.remove("hidden");
    wireEmailForm();
  }
  if (me && me.dev_auth) el("dev-signin").classList.remove("hidden");
  if (!providers.length && !(me && (me.dev_auth || me.email_login))) {
    el("none").classList.remove("hidden");
  }
  if (LINKING && !providers.length && !(me && me.email_login)) {
    el("none").textContent = t("signin.link.all_linked");
    el("none").classList.remove("hidden");
  }
})();

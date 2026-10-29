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
    el("webview-menu").textContent = WV.menuHint;  // the sentence's own full stop is in the string (COPY.md)
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

// The pending address (2026-10-29): the email carries a 6-digit code as well as the link, for when the link
// opens in some other browser — a desktop mail app's embedded Chromium, say, which then holds the session
// instead of this tab. The address is remembered for the tab (sessionStorage) so a reload keeps the code box;
// it expires with the link (15 minutes).
const PENDING_KEY = "bts.signin.pending";
const PENDING_MS = 15 * 60 * 1000;

function loadPending() {
  try {
    const p = JSON.parse(sessionStorage.getItem(PENDING_KEY) || "null");
    if (p && typeof p.email === "string" && p.email && Date.now() - Number(p.at || 0) < PENDING_MS) return p.email;
    sessionStorage.removeItem(PENDING_KEY);
  } catch (_) { /* storage blocked or junk: no pending address */ }
  return "";
}

function savePending(email) {
  try {
    if (email) sessionStorage.setItem(PENDING_KEY, JSON.stringify({ email, at: Date.now() }));
    else sessionStorage.removeItem(PENDING_KEY);
  } catch (_) { /* storage blocked: the code box just won't survive a reload */ }
}

let pendingEmail = "";

// Swap the email form for "check your inbox" + the code box. `devLink` / `devCode`: dev auth with no mail
// provider hands them back instead of sending.
function showCodeBox(email, devLink, devCode) {
  pendingEmail = email;
  const form = el("email-form"), box = el("code-box");
  form.after(box);  // follows the form wherever webviewLayout moved it
  form.classList.add("hidden");
  box.classList.remove("hidden");
  el("code-error").classList.add("hidden");
  const dev = el("code-dev");
  dev.replaceChildren();
  dev.classList.toggle("hidden", !devLink);
  if (devLink) {
    const a = document.createElement("a");
    a.className = "btn ghost";
    a.href = devLink;
    a.textContent = "Open the sign-in link (local dev)" + (devCode ? " · code " + devCode : "");
    dev.appendChild(a);
  }
  const input = el("code");
  input.value = "";
  try { input.focus({ preventScroll: true }); } catch (_) { /* old browsers */ }
}

function wireCodeBox() {
  const form = el("code-form");
  const button = el("code-submit");
  const fail = (key) => {
    const err = el("code-error");
    err.textContent = t(key);
    err.classList.remove("hidden");
  };
  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const code = el("code").value.trim();
    if (!code || !pendingEmail) return;
    el("code-error").classList.add("hidden");
    button.disabled = true;
    button.textContent = t("signin.code.checking");

    let data = null;
    try {
      const r = await fetch("/api/auth/email/code", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Requested-With": "fetch" },
        body: JSON.stringify({ email: pendingEmail, code }),
      });
      data = await r.json();
    } catch (_) { /* offline: fall through to the generic error */ }

    if (data && data.ok) {
      savePending("");
      window.location.assign(data.next || "/app");
      return;
    }
    button.disabled = false;
    button.textContent = t("signin.code.button");
    if (!data || !data.reason) { fail("signin.email.error"); return; }
    fail(["expired", "too_many"].includes(data.reason) ? "signin.code." + data.reason : "signin.code.wrong");
  });

  // "Send a new link": back to the email form, address filled in (and editable, for a typo).
  el("code-resend").addEventListener("click", () => {
    savePending("");
    const emailForm = el("email-form");
    el("code-box").classList.add("hidden");
    emailForm.classList.remove("hidden");
    el("email").value = pendingEmail;
    const btn = emailForm.querySelector("button");
    btn.disabled = false;
    btn.textContent = t("signin.email.button");
    el("email").focus();
  });
}

// The magic link: POST the address, then swap the form for "check your inbox" and the code box. The server
// answers the same way whether it sent anything or not (rate limit, bad syntax), so there is nothing to
// branch on — and nothing here ever reveals whether an account exists.
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

    savePending(email);
    showCodeBox(email, data.link, data.code);  // data.link/code: dev auth with no mail provider only
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
    wireCodeBox();
    const pending = loadPending();  // a reload after "Email me a link": straight back to the code box
    if (pending) showCodeBox(pending);
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

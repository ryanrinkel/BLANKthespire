"use strict";

// Sign-up events (docs/plans/SIGNUP_EVENTS_PLAN.md), shared by landing.js and signin.js — load it before them.
// Two jobs, both driven by the /api/me answer those pages already fetch:
//   ribbon(me, place)  the "sign up before ... and your first forge is on us" line. It is BUILT here, never
//                      written into the HTML, so with no live event the page is exactly what it was: no
//                      element, no gap, no flash. It appears only once /api/promo/active names an event AND
//                      /api/me says the visitor is signed out; any failure leaves nothing on the page.
//   keepWelcome(me)    /api/me hands out user.welcome_grant ONCE (the server stamps it seen on that read). If
//                      the splash or /login is the first page to read it, park it for app.js to show.
// Wrapped so its names stay out of the global scope the other classic scripts share.
window.BTS_EVENT = (() => {
  // Started at load, alongside the page's own /api/me, so the ribbon waits on the slower of the two only.
  // Never exposes a remaining count (the server does not send one).
  const active = fetch("/api/promo/active")
    .then((r) => (r.ok ? r.json() : null))
    .then((d) => (d && d.active && d.active.label ? d.active : null))
    .catch(() => null);

  // The viewer's own day and clock: "Mon, Nov 2, 6:00 AM".
  function localWhen(iso) {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "";
    return d.toLocaleString(undefined, { weekday: "short", month: "short", day: "numeric",
                                         hour: "numeric", minute: "2-digit" });
  }

  async function ribbon(me, place) {
    if (!me || me.user) return;              // unknown or signed in: a signup bonus is nothing to them
    const ev = await active;
    if (!ev) return;
    const when = localWhen(ev.ends_at);
    if (!when || new Date(ev.ends_at) <= new Date()) return;
    const n = Math.max(1, Number(ev.tokens_per_signup) || 1);
    const box = document.createElement("p");
    box.className = "event-ribbon";
    box.setAttribute("role", "status");
    const icon = document.createElement("span");
    icon.className = "event-ribbon-icon";
    icon.setAttribute("aria-hidden", "true");
    icon.textContent = "🎁";
    const text = document.createElement("span");
    const label = document.createElement("b");
    label.textContent = ev.label;
    text.append(label, ": sign up before " + when + " and "
      + (n === 1 ? "your first forge is on us." : "your first " + n + " forges are on us."));
    box.append(icon, text);
    place(box);
  }

  function keepWelcome(me) {
    const u = me && me.user;
    if (!u || !u.welcome_grant) return;
    try {
      localStorage.setItem("bts_welcome_grant", JSON.stringify({ uid: u.id, ...u.welcome_grant }));
    } catch (_) { /* storage blocked: the notice is lost, the tokens are not */ }
  }

  return { ribbon, keepWelcome };
})();

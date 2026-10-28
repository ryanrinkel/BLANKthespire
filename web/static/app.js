"use strict";

// i18n (web/static/i18n.js, loaded first): every user-facing string below comes from
// /static/i18n/<lang>.json by its docs/copy/COPY.md key. appT = plain text (textContent, title, toast,
// confirm), appH = HTML for innerHTML (values escaped). Nothing may call them before BTS_I18N.ready
// (the boot at the bottom of this file waits for it).
const appT = (key, vars) => BTS_I18N.t(key, vars);
const appH = (key, vars) => BTS_I18N.html(key, vars);
// A server JSON error: its translated `code` when there is one, else its English `error`, else "HTTP n".
const appErr = (d, status) => BTS_I18N.err(d, appT("common.http_error", { status }));


let ME = null;
// The non-user half of /api/me ({dev_auth, providers, email_login}) — ME is data.user, so the Account tab's
// sign-in methods (which providers this deploy offers at all) need the envelope kept too.
let ME_META = null;

// CSRF: the server rejects any mutating /api/* call without `X-Requested-With: fetch` (a cross-site form or
// script can't set a custom header). Patch fetch() once so every same-origin call carries it.
{
  const rawFetch = window.fetch.bind(window);
  window.fetch = (input, init) => {
    const url = typeof input === "string" ? input : (input && input.url) || "";
    if (url.startsWith("/") || url.startsWith(location.origin)) {
      init = { ...(init || {}) };
      init.headers = { ...(init.headers || {}), "X-Requested-With": "fetch" };
    }
    return rawFetch(input, init);
  };
}

// Apply the server's token state ({token_balance}) to ME wherever it arrives: /api/me, forge events
// (charged on start, refunded on failure), checkout return, 402s. Unlimited accounts ignore it.
function applyTokenState(data) {
  if (!data || !ME || ME.unlimited) return false;
  if (typeof data.token_balance !== "number") return false;
  ME.token_balance = data.token_balance;
  return true;
}

// Tokens the account can spend right now. v3 (2026-09-18): no daily grant any more, so this is simply
// the thank-you balance that donations left behind.
function spendable() {
  if (!ME) return 0;
  if (ME.unlimited) return Infinity;
  return Number(ME.token_balance || 0);
}

// --- browser-only preferences --------------------------------------------------------------------
// Private windows and locked-down browsers throw on every localStorage access, so nothing here may.
function lsGet(key) { try { return localStorage.getItem(key); } catch (_) { return null; } }
function lsSet(key, value) { try { localStorage.setItem(key, value); } catch (_) { /* no store */ } }
function lsDel(key) { try { localStorage.removeItem(key); } catch (_) { /* no store */ } }

// --- boot ---------------------------------------------------------------------------------------

async function boot() {
  const r = await fetch("/api/me");
  const data = await r.json();
  ME = data.user;
  ME_META = data;
  if (data.dev_auth) {
    el("dev-signin").classList.remove("hidden");
    el("mode-fake-label").classList.remove("hidden");  // no-key offline forge, dev only
  }

  if (!ME) {
    show("gate");
    return;
  }
  el("who").textContent = ME.name || ME.email;
  el("signout").classList.remove("hidden");
  el("gate").classList.add("hidden");
  restoreByok();
  renderTokens();
  restoreForgePref();
  applyRemixPrefill();
  DRAFT_RESTORED = restoreDraft();
  renderBanner();
  renderWelcome(ME.welcome_grant);
  loadEstimate();
  loadDonation();  // the forge tab's inline tier buttons need /api/billing before the Account tab is opened
  // #account is where a finished "link another sign-in" comes back to (auth._landing), so honour the hash.
  selectTab(location.hash === "#account" ? "account" : "forge");
  handlePurchaseReturn();
}

// The concept draft that survives a trip to Stripe (FORGE_FIRST_PLAN.md 3.3): donate() / donateCustom() stash
// {concept, interactive, pref} in bts_draft right before the page unloads to the hosted checkout; boot() puts it
// back once (after applyRemixPrefill, which wins when both exist) and deletes the key. A tab closed mid-checkout
// gets the same draft on its next visit.
let DRAFT_RESTORED = false;  // a draft concept was put back this load (handlePurchaseReturn's toast says so)

function stashDraft() {
  lsSet("bts_draft", JSON.stringify({ concept: el("concept").value, interactive: !!el("interactive").checked,
                                      pref: forgePref() }));
}

function restoreDraft() {
  const raw = lsGet("bts_draft");
  if (!raw) return false;
  lsDel("bts_draft");
  let d = null;
  try { d = JSON.parse(raw); } catch (_) { return false; }
  if (!d || typeof d !== "object") return false;
  let restored = false;
  const box = el("concept");
  if (box && !box.value.trim() && typeof d.concept === "string" && d.concept.trim()) {
    box.value = d.concept;
    el("interactive").checked = !!d.interactive;
    restored = true;
  }
  if (d.pref === "byok" || d.pref === "token") { setForgePref(d.pref); setMode(d.pref); }
  return restored;
}

// "Forge your own twist" on a /deck/<slug> page stashes {concept, name, from} in bts_prefill and sends the
// visitor here via /login. Seed the concept box once (only if it's empty), say what's being remixed, and
// clear the key so a later visit starts blank.
function applyRemixPrefill() {
  const raw = lsGet("bts_prefill");
  if (!raw) return;
  lsDel("bts_prefill");
  let p = null;
  try { p = JSON.parse(raw); } catch (_) { return; }
  const box = el("concept");
  if (!box || box.value.trim() || !p || typeof p.concept !== "string" || !p.concept.trim()) return;
  box.value = p.concept;
  const hint = document.createElement("p");
  hint.className = "hint";
  hint.textContent = appT("app.remix.hint", { name: p.name || appT("app.remix.name_fallback") });
  box.insertAdjacentElement("afterend", hint);
}

// Reflect the user's token state in the header chip, the "Use a token" balance line and the Account
// balance. Which box is open by default is restoreForgePref's job (pay step block below).
function renderTokens() {
  if (!ME) return;
  const unlimited = !!ME.unlimited;
  const paid = Number(ME.token_balance || 0);
  const chip = el("tokens");
  chip.textContent = unlimited ? appT("app.tokens.chip_unlimited") : appT("app.tokens.chip", { count: paid });
  chip.classList.remove("hidden");
  chip.classList.toggle("empty", !unlimited && paid <= 0);

  const line = el("token-balance-line");
  if (line) {
    if (unlimited) line.textContent = appT("app.tokens.line_unlimited");
    else if (paid > 0) line.textContent = appT("app.tokens.line_have", { count: paid });
    else line.textContent = appT("app.tokens.line_none");
  }

  // Keep the Account view's balance in lockstep wherever the numbers change (forge spend, donation).
  const acct = el("acct-balance");
  if (acct) acct.textContent = unlimited ? "∞" : String(paid);

  renderGetTokens();
  renderForgeButton();
  renderBanner();
}

// The forge tab's tier buttons sit behind "Get a forge token" (2026-09-26): folded for an account that already has
// tokens to spend, unfolded when the balance is 0 (that's what they came for), and absent for unlimited
// accounts. null = follow the balance; a click pins the user's choice for the rest of the visit.
let GET_TOKENS_OPEN = null;

function renderGetTokens() {
  const btn = el("forge-get-tokens"), wrap = el("forge-donate-wrap");
  if (!btn || !wrap || !ME) return;
  const unlimited = !!ME.unlimited;
  const open = !unlimited && (GET_TOKENS_OPEN ?? Number(ME.token_balance || 0) <= 0);
  btn.parentElement.classList.toggle("hidden", unlimited);
  wrap.classList.toggle("hidden", !open);
  btn.textContent = open ? appT("app.tokens.hide_options") : appT("app.pay.token.get");
  btn.setAttribute("aria-expanded", String(open));
}

// The pay boxes are a radio pair: clicking the header of the one already selected must not fold it (that
// would leave nothing selected). Switching happens by opening the other box.
function onPaySummaryClick(e) {
  if (e.currentTarget.parentElement.open) e.preventDefault();
}

// Opening one of the two payment boxes closes the other, remembers the choice, and re-renders everything
// that depends on it. Fired from the <details> "toggle" event, so a plain click on the summary counts.
function onPayBoxToggle(openedId, otherId, mode) {
  const box = el(openedId);
  if (box && box.open) {
    const other = el(otherId);
    if (other && other.open) other.open = false;   // fires the other box's toggle, which just re-renders
    // The box restoreForgePref opened by default is not a choice: don't remember it (the event is async,
    // so it arrives here after the fact).
    if (DEFAULT_OPENED === openedId) DEFAULT_OPENED = null;
    else setForgePref(mode);
  }
  renderForgeButton();
  renderBanner();
  renderEstimate();
}

// True while a forge is in flight: the button stays disabled no matter what re-renders underneath it
// (token events arrive mid-forge and call renderTokens -> renderForgeButton).
let FORGING = false;

// Can the open pay box pay for a forge right now? The offline demo always can; a token box needs an unlimited
// account or a token to spend; a key box needs a key and a selected model.
function payable() {
  const m = currentMode();
  if (m === "fake") return true;
  if (m === "token") return !!ME && (!!ME.unlimited || spendable() > 0);
  if (m === "byok") return !!(el("api_key").value.trim() && el("model").value.trim());
  return false;
}

// The forge button is never disabled except mid-forge (FORGE_FIRST_PLAN.md D2): a click that can't pay yet
// reveals the pay step instead. Its label says what the click will cost once a box can pay; until then it is
// plain "Forge the class" with a title saying what is missing.
function renderForgeButton() {
  const btn = el("forge-btn");
  if (!btn) return;
  const m = currentMode();
  let label = appT("app.forge.button"), why = "";
  if (m === "fake") {
    label = "Forge the class (offline demo)";
  } else if (m === "byok") {
    if (payable()) label = appT("app.forge.button_byok");
    else why = el("model").tagName === "SELECT" && currentProvider().mode === "byok"
      ? appT("app.forge.why_byok_list")
      : appT("app.forge.why_byok");
  } else if (m === "token") {
    if (!ME || ME.unlimited) {
      label = appT("app.forge.button_unlimited");
    } else {
      const paid = Number(ME.token_balance || 0);
      if (paid > 0) label = appT("app.forge.button_token", { count: paid });
      else why = appT("app.forge.why_no_tokens");
    }
  } else {
    why = appT("app.forge.why_no_mode");
  }
  btn.textContent = label;
  btn.disabled = FORGING;
  if (why) btn.title = why; else btn.removeAttribute("title");
}

// --- the pay step (forge tab, FORGE_FIRST_PLAN.md 3.2-3.3) ------------------------------------------
// #pay-step wraps the two pay boxes and stays hidden until a Forge click that can't pay yet (or the "Change
// my tokens provider" link); once shown it stays for the rest of the visit. The open <details> box is the choice:
// restoreForgePref opens one on load (token box unless a key is saved) and an explicit pick is remembered in
// localStorage.bts_forge_pref.

let PAY_STEP_OPEN = false;
let DEFAULT_OPENED = null;   // id of the box restoreForgePref opened as a default, until its toggle event lands

function forgePref() {
  const p = lsGet("bts_forge_pref");
  return p === "byok" || p === "token" ? p : null;
}
function setForgePref(mode) { if (mode === "byok" || mode === "token") lsSet("bts_forge_pref", mode); }

// A key the user already saved counts as "decided" even without a stored preference.
function hasSavedKey() {
  try { return !!JSON.parse(localStorage.getItem("bts_byok") || "{}").api_key; } catch (_) { return false; }
}

// Open the box for `mode` and close the other one. The toggle handlers do the remembering.
function setMode(mode) {
  const byok = el("forge-byok"), token = el("forge-token");
  if (!byok || !token) return;
  if (mode === "byok") { token.open = false; byok.open = true; }
  else if (mode === "token") { byok.open = false; token.open = true; }
  renderForgeButton();
}

// Start on the path last chosen — a returning user with a saved key shouldn't have to reopen the box
// every visit. With nothing remembered, a saved key opens the key box and otherwise the token box opens:
// our hosted compute is the default since 2026-10-12, because a new account's 11 forges on 2026-10-11 all
// died on made-up API keys — the key path was presented first and looked like the way in. (Before that,
// both boxes stayed shut and the forge button stayed disabled until one was opened.) The default is not
// written to bts_forge_pref, so a key saved later still wins.
function restoreForgePref() {
  const pref = forgePref();
  if (pref) setMode(pref);
  else if (!currentMode()) {
    const mode = hasSavedKey() ? "byok" : "token";
    DEFAULT_OPENED = mode === "byok" ? "forge-byok" : "forge-token";
    setMode(mode);
  }
  renderForgeButton();
}

// Show the pay step (and keep it shown for the rest of the visit): make sure a box is open, put the one-line
// reason on top (none for the "Change my tokens provider" link), scroll the step under the header and move focus
// to the first thing to do there: a tier button when the token box is open on an empty balance, the key field
// when the key box is open, else the Forge button itself.
function revealPayStep(reason) {
  const step = el("pay-step");
  if (!step) return;
  PAY_STEP_OPEN = true;
  step.classList.remove("hidden");
  el("pay-open").classList.add("hidden");
  if (!el("forge-token").open && !el("forge-byok").open) restoreForgePref();
  const needTiers = el("forge-token").open && !!ME && !ME.unlimited && spendable() <= 0;
  if (needTiers) {
    if (GET_TOKENS_OPEN === false) GET_TOKENS_OPEN = null;  // the tiers are what this click is about: unfold
    renderGetTokens();                                       // them (they fold by themselves once tokens land)
  }
  const line = el("pay-reason");
  line.textContent = reason || "";
  line.classList.toggle("hidden", !reason);
  step.scrollIntoView({ behavior: "smooth", block: "start" });
  let target = el("forge-btn");
  if (needTiers) target = document.querySelector("#forge-donate-tiers .donate-tier") || target;
  else if (el("forge-byok").open) target = el("api_key");
  target.focus({ preventScroll: true });
  renderForgeButton();
}

// What the pay step says when a Forge click can't pay yet.
function payReason() {
  return currentMode() === "byok" ? appT("app.pay.reason_byok") : appT("app.pay.reason_token");
}

// --- "how it works" tutorial banner ---------------------------------------------------------------
// One line under the Forge button (describe, Forge, copy, paste in-game) that every signed-in account sees until
// dismissed; the text is static in index.html. The five-step 2026-09-30 version shrank to this on 2026-10-26
// (FORGE_FIRST_PLAN.md 3.4): installing the mod is now explained on the result, after the class exists.
// Sign-up event welcome (docs/plans/SIGNUP_EVENTS_PLAN.md). /api/me hands out user.welcome_grant ONCE (the
// server stamps it seen on that read), so whichever read gets it shows it: boot(), or loadAccount() if boot's
// read came first on another tab. landing.js / signin.js park one THEY consumed in bts_welcome_grant
// (signup-event.js keepWelcome), tagged with the account id so a different sign-in on this browser never
// inherits it. Nothing to show -> the banner stays hidden; dismissing only hides it (it is already "seen").
function renderWelcome(grant) {
  const raw = lsGet("bts_welcome_grant");
  if (raw) {
    lsDel("bts_welcome_grant");
    if (!grant) {
      try {
        const g = JSON.parse(raw);
        if (g && ME && Number(g.uid) === Number(ME.id)) grant = g;
      } catch (_) { /* a mangled key is just dropped */ }
    }
  }
  const n = grant ? Number(grant.tokens) || 0 : 0;
  if (n <= 0) return;
  el("welcome-text").textContent = appT("app.welcome.text",
    { label: grant.label || appT("app.welcome.label_fallback"), count: n });
  el("welcome-banner").classList.remove("hidden");
}

function renderBanner() {
  const bar = el("v3-banner");
  if (!bar) return;
  bar.classList.toggle("hidden", !(ME && !lsGet("bts_tutorial_banner_dismissed")));
  // Phones (render.js IS_PHONE, PHONE_FUNNEL_PLAN.md 5.1): a one-line "forge here, play on the PC" banner,
  // dismissed on its own key.
  el("phone-banner").classList.toggle("hidden", !(ME && IS_PHONE && !lsGet("bts_phone_banner_dismissed")));
}

// --- BYOK cost estimate ---------------------------------------------------------------------------
// Everything here is SERVER-COMPUTED (/api/forge-estimate) — the browser multiplies, it never owns a price
// table (the old CLAUDE_PRICES list moved into app.py's BYOK_TEXT_PRICES on 2026-09-20). The payload is
//   calls / input_tokens / cached_tokens / output_tokens   rolling average of recent forges
//   images_per_forge                                       rolling average of art calls per forge
//   art: {vendor: {model, per_image_usd, pack_usd, source}} what a complete art pack costs per key type
//   text_prices: {model: [in, out, cached]} in $/M          every model the dropdowns suggest
// so the quote tracks the real pipeline and the real prices instead of a number someone typed once.
let ESTIMATE = null;

async function loadEstimate() {
  try {
    const r = await fetch("/api/forge-estimate");
    if (r.ok) ESTIMATE = await r.json();
  } catch (_) { /* the hint falls back to the generic wording */ }
  renderEstimate();
}

function fmtTokens(n) {
  n = Number(n || 0);
  return n >= 1_000_000 ? (n / 1_000_000).toFixed(1) + "M" : n >= 1000 ? Math.round(n / 1000) + "K" : String(n);
}

function usd(n) { return "$" + Number(n || 0).toFixed(2); }

// [in, out, cached] $/M for a model id, or null when the server has no price for it. An exact hit wins;
// otherwise the LONGEST priced id the typed model starts with, so a dated or pinned slug
// ("gpt-4o-2024-11-20", "claude-sonnet-4-6-20260401") still prices at its family's rate.
function modelPrice(model) {
  const table = ESTIMATE?.text_prices, id = String(model || "").trim();
  if (!table || !id) return null;
  let row = table[id];
  if (!row) {
    let best = "";
    for (const k in table) if (id.startsWith(k) && k.length > best.length) best = k;
    row = best ? table[best] : null;
  }
  return Array.isArray(row) ? { inp: row[0], out: row[1], cached: row[2] } : null;
}

// The `art` block for the selected provider, or null where a BYOK forge makes no art.
function artFor(p) {
  return (p && p.art && p.artKey && ESTIMATE?.art) ? (ESTIMATE.art[p.artKey] || null) : null;
}

// The two models a BYOK forge runs (forge._key_models): the design model shapes the class, the card model
// writes the cards. A blank card box means the design model does both.
function byokModels() {
  const design = el("model").value.trim();
  return { design, cards: el("card_model").value.trim() || design };
}

// USD for one slot's tokens on one model: [cached, uncached] — the first assumes prompt caching works on the
// key, the second is the ceiling without it. Null when the server has no price for the model.
function slotUsd(t, model) {
  const price = modelPrice(model);
  if (!price || !t) return null;
  const inp = Number(t.input_tokens || 0), cached = Number(t.cached_tokens || 0), out = Number(t.output_tokens || 0);
  return [(Math.max(0, inp - cached) * price.inp + cached * price.cached + out * price.out) / 1_000_000,
          (inp * price.inp + out * price.out) / 1_000_000];
}

function tokensLine(t) {
  return appT("app.estimate.tokens_line", { calls: t.calls, input: fmtTokens(t.input_tokens),
                                            cached: fmtTokens(t.cached_tokens), output: fmtTokens(t.output_tokens) });
}

// The whole quote as data: rows of {label, what, cost (USD or null), tip}, the total, and at most one short
// note. The panel and the confirm dialog both render this, so they can never disagree.
function estimateRows() {
  const e = ESTIMATE, p = currentProvider(), { design, cards } = byokModels();
  if (!e) return { rows: [], total: null, text: null, art: null,
                   note: appT("app.estimate.note_fallback") };
  const whole = { calls: e.calls, input_tokens: e.input_tokens, cached_tokens: e.cached_tokens,
                  output_tokens: e.output_tokens };
  // One row when one model does everything; otherwise each half priced on its own model.
  const slots = design === cards || !e.slots
    ? [{ label: appT("app.estimate.row_design_cards"), model: design, t: whole }]
    : [{ label: appT("app.byok.design_label"), model: design, t: e.slots.design },
       { label: appT("app.byok.card_label"), model: cards, t: e.slots.cards }];
  const rows = [], unpriced = [];
  let text = 0, ceiling = 0;
  for (const sl of slots) {
    const usdPair = slotUsd(sl.t, sl.model);
    if (!usdPair) { unpriced.push(sl.model || appT("app.estimate.no_model")); text = null; }
    else if (text != null) { text += usdPair[0]; ceiling += usdPair[1]; }
    // The vendor prefix ("anthropic/", "openai/") is dropped on screen; the tooltip keeps the full id.
    rows.push({ label: sl.label, what: sl.model.split("/").pop() || appT("app.estimate.pick_model"),
                cost: usdPair ? usdPair[0] : null, tip: `${sl.model}: ${tokensLine(sl.t)}` });
  }

  const artBlock = artFor(p);
  let art = null;
  if (artBlock) {
    const n = Number(e.images_per_forge || 36);
    art = artBlock.pack_usd != null ? Number(artBlock.pack_usd)
        : (artBlock.per_image_usd != null ? Number(artBlock.per_image_usd) * n : null);
    rows.push({ label: appT("app.estimate.row_art"), what: appT("app.estimate.art_images", { count: n }), cost: art,
                tip: appT("app.estimate.art_tip", {
                  model: artBlock.model || appT("app.estimate.art_tip_model_fallback", { provider: p.label }),
                  count: n - 2 }) });
  } else {
    rows.push({ label: appT("app.estimate.row_art"), what: appT("app.estimate.art_none"), cost: "—",
                tip: appT("app.estimate.art_none_tip") });
  }
  const total = text != null && (art != null || !artBlock) ? text + (art || 0) : null;

  // One note, most useful first: a model we can't price, then a much cheaper art route (Gemini/xAI bill a
  // flat list price per image; the OpenRouter figure is measured from our own ledger), then the caching
  // caveat when it moves the number.
  const or = e.art?.openrouter;
  let note = "";
  if (unpriced.length) note = appT("app.estimate.note_unpriced", { models: unpriced.join(" / ") });
  else if (artBlock && (p.artKey === "gemini" || p.artKey === "xai") && or?.pack_usd != null && art > or.pack_usd) {
    note = appT("app.estimate.note_openrouter", { price: usd(or.pack_usd) });
  } else if (ceiling > text * 1.25) note = appT("app.estimate.note_caching", { price: usd(ceiling + (art || 0)) });
  return { rows, total, text, art, note };
}

// The confirm dialog: three short lines, same numbers as the panel.
function estimateText() {
  const { total, text, art, note } = estimateRows(), { design, cards } = byokModels();
  const models = design === cards ? appT("app.estimate.confirm_model", { model: design })
    : appT("app.estimate.confirm_models", { design, cards });
  const cost = total != null
    ? appT("app.estimate.confirm_cost", { total: usd(total),
        split: art ? appT("app.estimate.confirm_split", { text: usd(text), art: usd(art) }) : "" })
    : appT("app.estimate.confirm_unknown");
  return [models, cost, note].filter(Boolean).join("\n");
}

// The quote is shown on demand: the "Estimate cost" link reveals it, and any change to the provider or
// a model (showEstimate(false) from those handlers) folds it back, so the numbers on screen always belong
// to the settings on screen.
let ESTIMATE_SHOWN = false;

function showEstimate(shown) {
  ESTIMATE_SHOWN = !!shown;
  renderEstimate();
}

function renderEstimate() {
  const box = el("byok-estimate"), btn = el("estimate-btn");
  if (!box) return;
  box.classList.toggle("hidden", !ESTIMATE_SHOWN);
  if (btn) btn.classList.toggle("hidden", ESTIMATE_SHOWN);
  if (!ESTIMATE_SHOWN) { box.innerHTML = ""; return; }
  const { rows, total, note } = estimateRows();
  const cost = (c) => c == null ? "?" : typeof c === "string" ? c : usd(c);
  box.innerHTML = `<div class="est-head">${appH("app.estimate.title")}</div>`
    + (rows.length ? `<table class="est-table">${rows.map((r) =>
        `<tr title="${esc(r.tip)}"><th>${esc(r.label)}</th><td class="est-what">${esc(r.what)}</td>`
        + `<td class="est-cost">${cost(r.cost)}</td></tr>`).join("")}`
      + `<tr class="est-total"><th>${appH("app.estimate.total")}</th><td></td><td class="est-cost">${total == null ? "?" : "≈ " + usd(total)}</td></tr>`
      + `</table>` : "")
    + (note ? `<p class="est-note">${esc(note)}</p>` : "");
}

function show(id) {
  for (const v of ["gate", "view-forge", "view-library", "view-account"]) el(v).classList.add("hidden");
  el(id).classList.remove("hidden");
}

function selectTab(which) {
  el("nav-forge").classList.toggle("active", which === "forge");
  el("nav-library").classList.toggle("active", which === "library");
  el("nav-account").classList.toggle("active", which === "account");
  if (which === "forge") {
    show("view-forge");
    el("forge-input").classList.remove("hidden");
    el("pay-step").classList.toggle("hidden", !PAY_STEP_OPEN);
    renderBanner();
  }
  else if (which === "account") { show("view-account"); loadAccount(); }
  else { show("view-library"); loadLibrary(); }
}

// --- providers ----------------------------------------------------------------------------------
// Each provider maps to a known base URL (so users pick a name, not a URL) plus a key prefix used to
// auto-select the dropdown when it's unambiguous, the page to get a key, and a few suggested models.
// `mode` distinguishes Anthropic (native SDK path) from the OpenAI-compatible path. "custom" has no
// base_url — it reveals the URL field for any other OpenAI-compatible endpoint. `art: true` marks the
// providers whose image API the server can drive with the same key (mirrors app.py's _BYOK_ART_HOSTS —
// OpenRouter, OpenAI and, since 2026-09-20, Google Gemini and xAI): there the splash, sprite and card
// portraits are generated on the user's key; elsewhere a BYOK forge ships without generated art (the mod
// draws its built-in card doodles) — art is never billed to us.
//
// `models` is a reference list: a model a forge has actually finished on goes FIRST where the provider has
// one, then the rest CHEAPEST FIRST. Since 2026-10-23 only Anthropic (no listing) offers it as the model
// picker; every "byok" provider's pickers hold ONLY what its own /models listing confirmed (loadModels). Refreshed 2026-10-01 against each vendor's
// live model list (OpenAI + Ollama via /models, the rest from their docs or OpenRouter). The estimate
// under the fields prices whichever one is typed, from /api/forge-estimate's `text_prices`. Every id here
// MUST have a price in that table — web/tests/test_forge_estimate.py parses this block and fails if one
// doesn't, so the quote can never quietly go blank on a suggestion we ship.
const PROVIDERS = {
  anthropic:  { label: "Anthropic", mode: "anthropic", base_url: "",
                prefix: "sk-ant-", keyFrom: "console.anthropic.com",
                models: ["claude-sonnet-5", "claude-opus-5-5"] },
  openai:     { label: "OpenAI", mode: "byok", base_url: "https://api.openai.com/v1", art: true, artKey: "openai",
                prefix: "sk-", get keyFrom() { return appT("app.byok.key_from_openai"); },
                models: ["gpt-5.6-sol", "gpt-6.1-sol", "gpt-6-astra"] },
  ollama:     { label: "Ollama Cloud", mode: "byok", base_url: "https://ollama.com/v1",
                prefix: "", keyFrom: "ollama.com/settings/keys",
                models: ["glm-5.3", "gpt-oss:120b", "deepseek-v4.1-flash", "kimi-k2.6"] },
  openrouter: { label: "OpenRouter", mode: "byok", base_url: "https://openrouter.ai/api/v1", art: true,
                artKey: "openrouter",
                prefix: "sk-or-", keyFrom: "openrouter.ai/keys",
                models: ["z-ai/glm-5.3", "google/gemini-3.8-flash", "anthropic/claude-sonnet-5", "openai/gpt-6.1-sol"] },
  groq:       { label: "Groq", mode: "byok", base_url: "https://api.groq.com/openai/v1",
                prefix: "gsk_", keyFrom: "console.groq.com/keys",
                models: ["openai/gpt-oss-120b", "qwen/qwen3.8-27b"] },
  google:     { label: "Google Gemini", mode: "byok", art: true, artKey: "gemini",
                base_url: "https://generativelanguage.googleapis.com/v1beta/openai",
                prefix: "AIza", keyFrom: "aistudio.google.com/apikey",
                models: ["gemini-3.5-flash-lite", "gemini-3.8-flash"] },
  // grok-4.x cannot turn reasoning off (hidden thinking is billed and eats max_tokens), so the
  // explicitly non-reasoning model is suggested first — see forge.py BYOK_HOST_PROFILES.
  xai:        { label: "xAI (Grok)", mode: "byok", base_url: "https://api.x.ai/v1", art: true, artKey: "xai",
                prefix: "xai-", keyFrom: "console.x.ai",
                models: ["grok-4.20-0309-non-reasoning", "grok-4.3", "grok-4.7"] },
  deepseek:   { label: "DeepSeek", mode: "byok", base_url: "https://api.deepseek.com/v1",
                prefix: "", keyFrom: "platform.deepseek.com",
                models: ["deepseek-flash", "deepseek-v4-pro"] },
  together:   { label: "Together", mode: "byok", base_url: "https://api.together.xyz/v1",
                prefix: "", keyFrom: "api.together.xyz/settings/api-keys",
                models: ["zai-org/GLM-5.3", "openai/gpt-oss-120b", "deepseek-ai/DeepSeek-V4.1-Flash"] },
  custom:     { get label() { return appT("app.byok.provider_label_custom"); }, mode: "byok", base_url: "",
                prefix: "", get keyFrom() { return appT("app.byok.key_from_custom"); },
                models: [] },
};

function currentProvider() {
  return PROVIDERS[el("provider").value] || PROVIDERS.custom;
}

// Resolved base URL for the selected provider (the custom field for "custom", else the known URL).
function resolvedBaseUrl() {
  const id = el("provider").value;
  return id === "custom" ? el("base_url").value.trim() : (PROVIDERS[id]?.base_url || "");
}

// Apply the selected provider to the form: show the URL field only for "custom", reset the model pickers
// (Anthropic's static list, or the "load models" placeholder), refresh the hint, and hide "Load models"
// where it can't work (Anthropic / no URL yet). A key already in the box loads the new provider's list.
function applyProvider() {
  const id = el("provider").value;
  const p = currentProvider();
  el("base_url").style.display = id === "custom" ? "" : "none";

  resetModelPickers(p);
  renderLoadModelsBtn();

  el("byok-hint").textContent = appT("app.byok.get_key_at", { where: p.keyFrom });
  // Art is a property of the provider, so it lives in a chip beside the estimate rather than a paragraph;
  // the tooltip carries the detail.
  const chip = el("byok-art");
  chip.textContent = p.art ? appT("app.byok.art_chip_yes") : appT("app.byok.art_chip_no");
  chip.classList.toggle("ok", !!p.art);
  chip.title = p.art
    ? appT("app.byok.art_tip_yes")
    : appT("app.byok.art_tip_no", { provider: p.label });
  renderEstimate();
  scheduleModelLoad();
}

// --- BYOK model pickers ----------------------------------------------------------------------------
// Free-text model boxes let typos and hidden routes through (gtp-5, claude ids sent to OpenAI,
// gemini-3.6-flash-lite, OpenRouter :free), so since 2026-10-23 both models are <select>s filled from the
// provider's OWN listing (/api/models, filtered server-side to forge-capable ids, "Tested" group first).
// Only Anthropic (no listing) offers its static PROVIDERS list, and only "Other" falls back to typed ids
// when its endpoint can't list models (setModelControl("text")). The forge route re-checks the ids.

// The models the user wants back once a list arrives: restoreByok's saved pair, then every pick.
let SAVED_MODELS = { model: "", card_model: "" };
let MODELS_LOADED_FOR = "";   // base_url + "\n" + key of the list in the pickers ("" = none loaded)
let MODELS_LOADING_FOR = "";  // the pair a request is in flight for
let MODEL_LOAD_TIMER = null;

const modelDisplay = (id) => String(id).replace(/^models\//, "");  // Gemini lists "models/<id>"

function modelPair() { return resolvedBaseUrl() + "\n" + el("api_key").value.trim(); }

// True once el("model").value is a real choice: a filled select, or the typed-id fallback.
function modelsReady() {
  const m = el("model");
  return m.tagName === "INPUT" || !m.disabled;
}

function newOption(value, text) {
  const o = document.createElement("option");
  o.value = value; o.textContent = text;
  return o;
}

// Swap both model fields between <select> and the typed <input> fallback, keeping id + class so every
// el("model").value reader works on either. Handlers are re-attached to the new elements.
function setModelControl(kind) {
  const tag = kind === "text" ? "INPUT" : "SELECT";
  for (const id of ["model", "card_model"]) {
    const cur = el(id);
    if (cur.tagName === tag) continue;
    const next = document.createElement(tag.toLowerCase());
    next.id = id; next.className = cur.className;
    if (tag === "INPUT") {
      next.autocomplete = "off";
      next.placeholder = id === "model" ? appT("app.byok.model_placeholder_typed") : appT("app.byok.card_same");
      next.value = (id === "model" ? SAVED_MODELS.model : SAVED_MODELS.card_model) || "";
    } else next.disabled = true;  // empty until filled; modelsReady() then falls back to SAVED_MODELS
    cur.replaceWith(next);
  }
  wireModelFields();
}

function wireModelFields() {
  const onPick = () => {
    SAVED_MODELS = { model: el("model").value.trim(), card_model: el("card_model").value.trim() };
    saveByok(); showEstimate(false); renderForgeButton();
  };
  el("model").onchange = onPick;
  el("card_model").onchange = onPick;
  el("model").oninput = () => { showEstimate(false); renderForgeButton(); };
  el("card_model").oninput = () => showEstimate(false);
}

// Back to the pre-load state for provider `p`: Anthropic's static list (enabled), or disabled placeholders.
function resetModelPickers(p) {
  setModelControl("select");
  MODELS_LOADED_FOR = "";
  const m = el("model"), c = el("card_model");
  m.innerHTML = ""; c.innerHTML = "";
  c.appendChild(newOption("", appT("app.byok.card_same")));
  if (p.mode === "anthropic") {
    for (const id of p.models) { m.appendChild(newOption(id, id)); c.appendChild(newOption(id, id)); }
    if (p.models.includes(SAVED_MODELS.model)) m.value = SAVED_MODELS.model;
    c.value = p.models.includes(SAVED_MODELS.card_model) ? SAVED_MODELS.card_model : "";
    m.disabled = c.disabled = false;
  } else {
    m.appendChild(newOption("", appT("app.byok.design_placeholder")));
    m.disabled = c.disabled = true;
  }
  renderForgeButton();
}

// Fill both pickers from an /api/models reply and reselect what the user had.
function populateModels(d) {
  const m = el("model"), c = el("card_model");
  const want = (modelsReady() && m.value) || SAVED_MODELS.model;
  const wantCard = (modelsReady() ? c.value : SAVED_MODELS.card_model) || "";
  const ids = d.models || [];
  const tested = (d.recommended || []).filter((id) => ids.includes(id));
  const rest = ids.filter((id) => !tested.includes(id));
  m.innerHTML = ""; c.innerHTML = "";
  c.appendChild(newOption("", appT("app.byok.card_same")));
  if (!ids.length) {
    m.appendChild(newOption("", appT("app.byok.no_models")));
    m.disabled = c.disabled = true;
    renderForgeButton();
    return [];
  }
  for (const sel of [m, c]) {
    for (const [label, group] of [[appT("app.byok.group_tested"), tested], [appT("app.byok.group_all"), rest]]) {
      if (!group.length) continue;
      const g = document.createElement("optgroup");
      g.label = label;
      for (const id of group) g.appendChild(newOption(id, modelDisplay(id)));
      sel.appendChild(g);
    }
  }
  const gone = [];
  if (want && ids.includes(want)) m.value = want;
  else { if (want) gone.push(want); m.value = tested[0] || ids[0]; }
  if (wantCard && ids.includes(wantCard)) c.value = wantCard;
  else { if (wantCard) gone.push(wantCard); c.value = ""; }
  m.disabled = c.disabled = false;
  SAVED_MODELS = { model: m.value, card_model: c.value };
  saveByok();
  showEstimate(false);
  renderForgeButton();
  return gone;  // saved ids this list no longer offers (the caller toasts the first)
}

function renderLoadModelsBtn() {
  const p = currentProvider(), btn = el("load-models");
  // Load-models hits {base_url}/models with a Bearer token — works for OpenAI-compatible providers, not
  // Anthropic's native API. Hidden when there's no usable URL.
  btn.style.display = (p.mode === "byok" && resolvedBaseUrl()) ? "" : "none";
  if (!MODELS_LOADING_FOR) btn.textContent = MODELS_LOADED_FOR ? appT("app.byok.reload_models") : appT("app.byok.load_models");
}

// Auto-load (debounced) once a byok provider has a URL + key and the BYOK box is open; never twice for
// the same URL + key.
function scheduleModelLoad() {
  clearTimeout(MODEL_LOAD_TIMER);
  MODEL_LOAD_TIMER = setTimeout(() => {
    if (currentProvider().mode !== "byok" || !el("forge-byok")?.open) return;
    if (!resolvedBaseUrl() || !el("api_key").value.trim()) return;
    const pair = modelPair();
    if (pair === MODELS_LOADED_FOR || pair === MODELS_LOADING_FOR) return;
    loadModels({ auto: true });
  }, 400);
}

// Auto-select the provider from an unambiguous key prefix (sk-ant-, sk-or-, gsk_, AIza). Plain "sk-"
// is shared by several providers, so we never override the user's choice for it.
function providerFromKey(key) {
  for (const [id, p] of Object.entries(PROVIDERS)) {
    if (p.prefix && p.prefix !== "sk-" && key.startsWith(p.prefix)) return id;
  }
  return null;
}

// --- BYOK persistence (browser only; never sent anywhere but the forge request) ------------------

function restoreByok() {
  try {
    const saved = JSON.parse(localStorage.getItem("bts_byok") || "{}");
    if (saved.provider && PROVIDERS[saved.provider]) el("provider").value = saved.provider;
    if (saved.base_url) el("base_url").value = saved.base_url;
    if (saved.api_key) el("api_key").value = saved.api_key;
    // The pickers are filled later (Anthropic now, the rest once the list loads); they reselect these.
    SAVED_MODELS = { model: String(saved.model || ""), card_model: String(saved.card_model || "") };
  } catch (_) { /* a corrupt entry just starts blank */ }
  applyProvider();
}
function saveByok() {
  // Until a list is loaded the pickers hold a placeholder, so the remembered pair is what gets saved.
  const ready = modelsReady();
  lsSet("bts_byok", JSON.stringify({
    provider: el("provider").value,
    base_url: el("base_url").value.trim(),
    model: ready ? el("model").value.trim() : SAVED_MODELS.model,
    card_model: ready ? el("card_model").value.trim() : SAVED_MODELS.card_model,
    api_key: el("api_key").value.trim(),
  }));
  renderBanner();  // a saved key satisfies the "enter an API key" warning
}

// What the forge button would spend, from the UI alone: the dev-only offline demo wins, then whichever
// payment box is open. Null means nothing is selected yet (button disabled).
function currentMode() {
  const fake = el("mode-fake");
  if (fake && fake.checked) return "fake";
  if (el("forge-byok")?.open) return "byok";
  if (el("forge-token")?.open) return "token";
  return null;
}

// --- forge (SSE over POST via fetch stream) ------------------------------------------------------

async function forge() {
  const concept = el("concept").value.trim();
  if (!concept) { toast(appT("app.forge.toast_no_concept")); el("concept").focus(); return; }
  // Nothing armed can pay yet: unfold the pay step instead of forging (FORGE_FIRST_PLAN.md 3.2). A repeat click
  // re-scrolls, re-focuses and repeats the reason as a toast.
  if (!payable()) {
    const reason = payReason();
    if (PAY_STEP_OPEN) toast(reason);
    revealPayStep(reason);
    return;
  }
  const choice = currentMode();  // "token" | "byok" | "fake"

  // The wire `mode` is derived: BYOK splits into Anthropic's native path vs the OpenAI-compatible path
  // based on the chosen provider, so the backend routing is unchanged.
  // Every web forge runs the staged creative front-end with a three-archetype triad (the one-shot /
  // "classic pair" opt-outs were removed on 2026-09-17; the server ignores `staged` and always stages).
  const body = {
    concept,
    mode: choice,
    // interactive forge mode: pause at the archetype checkpoint for the player's pick
    interactive: !!el("interactive").checked,
    triad: true,
  };
  if (choice === "token") {
    if (!ME.unlimited) {
      if (spendable() <= 0) {
        toast(appT("app.forge.toast_no_tokens"));
        return;
      }
      const paid = Number(ME.token_balance || 0);
      if (!confirm(appT("app.forge.confirm_token", { count: paid }))) return;
    }
  } else if (choice === "byok") {
    const p = currentProvider();
    const api_key = el("api_key").value.trim();
    const model = el("model").value.trim();
    if (p.mode === "byok" && el("model").tagName === "SELECT" && (el("model").disabled || !model)) {
      toast(appT("app.forge.toast_load_models"));
      return;
    }
    if (!api_key || !model) { toast(appT("app.forge.toast_need_key")); return; }
    if (!confirm(appT("app.forge.confirm_byok", { provider: p.label, estimate: estimateText() }))) return;
    // Blank = the design model codes the cards too; sent only when it differs, so a one-model forge's
    // request is unchanged.
    const card_model = byokModels().cards !== model ? byokModels().cards : undefined;
    if (p.mode === "anthropic") {
      body.mode = "anthropic";
      body.key = { api_key, model, card_model };
    } else {
      const base_url = resolvedBaseUrl();
      if (!base_url) { toast(appT("app.forge.toast_need_base_url")); return; }
      body.mode = "byok";
      body.key = { base_url, api_key, model, card_model };
    }
    saveByok();
  }

  FORGING = true;
  renderForgeButton();
  el("result").classList.add("hidden");
  el("progress").classList.remove("hidden");
  el("log").textContent = "";
  // Not English: one line up top saying the detail lines stay English (only stage headers are translated).
  if (BTS_I18N.lang !== "en") {
    appendLog(BTS_I18N.has("app.console.log_in_english") ? appT("app.console.log_in_english")
      : "The forge log below is in English; only the stage headers are translated.");
  }
  el("forge-lost").classList.add("hidden");
  resetChoice();  // clear any choice panel left over from a previous forge
  // Echo what we asked for, so a mode mishap (e.g. a stale page) is visible in the log immediately.
  appendLog(appT("app.console.requested", { mode: body.mode,
    interactive: body.interactive ? appT("app.console.requested_interactive") : "" }));

  // started = the server answered, so the forge exists (and a token is reserved); settled = the stream
  // reached its result/error. Started but not settled means the CONNECTION died, not the forge.
  const run = { started: false, settled: false, forgeId: null };
  try {
    const resp = await fetch("/api/forge-class", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!resp.ok && resp.headers.get("content-type")?.includes("application/json")) {
      const e = await resp.json();
      // Server says out of tokens (a stale balance slipped past the pre-check) — unfold the pay step, where
      // the tiers are (the 402 text says "under the Forge button").
      if (resp.status === 402) {
        if (applyTokenState(e)) renderTokens();
        revealPayStep(appT("app.pay.reason_token"));
      }
      throw new Error(appErr(e, resp.status));
    }
    // A non-JSON error page (an nginx 502 while the app restarts) means no forge started.
    if (!resp.ok) throw new Error(appT("app.forge.err_http_nonjson", { status: resp.status }));
    run.started = true;
    await consumeSSE(resp, (event, data) => {
      if (event === "result" || event === "error") run.settled = true;
      if (data && data.forge_id) run.forgeId = data.forge_id;
      onForgeEvent(event, data);
    });
    if (!run.settled) throw new TypeError(appT("app.forge.err_stream_ended"));
  } catch (e) {
    if (e instanceof TypeError && !run.settled) await recoverForge(body, run, e.message);
    else {
      appendLog("✗ " + e.message);
      toast(e.message);
    }
  } finally {
    FORGING = false;
    renderForgeButton();
    el("spinner").classList.add("hidden");
    resetChoice();
  }
}

// The browser lost the forge's progress stream (a phone locking its screen or hopping networks is the usual
// cause — Chrome reports it as a bare "network error"). The forge runs on the server regardless, so instead
// of reading as a failure the page says so and polls /api/forge-jobs/<id> until the job settles, then shows
// the class (or the failure) exactly as the stream would have. Awaited inside forge()'s try, so the button
// stays disabled and the spinner spins until then.
const RECOVER_POLL_MS = 5000;
const RECOVER_GIVE_UP_MS = 30 * 60 * 1000;  // past the server's 20-minute cap plus art; My Classes has it anyway
const RECOVER_NOT_FOUND = 3;                // 404s in a row before "no forge started" (POST never landed)

async function recoverForge(body, run, reason) {
  const token = body.mode === "token";
  const note = (text) => { el("forge-lost-text").textContent = text; el("forge-lost").classList.remove("hidden"); };
  const stillRunning = () => note(appT("app.lost.still_running")
    + (token ? appT("app.lost.refund_note") : ""));
  if (run.started) {
    stillRunning();
    appendLog(appT("app.console.lost", { reason }));
    toast(appT("app.lost.toast_reconnecting"));
  } else {
    note(appT("app.lost.unreachable", { reason }));
    appendLog(appT("app.console.unreachable", { reason }));
    toast(appT("app.lost.toast_unreachable"));
  }

  let id = run.forgeId || "latest";
  let notFound = 0, lastMsg = "", found = run.started;
  const deadline = Date.now() + RECOVER_GIVE_UP_MS;
  while (Date.now() < deadline) {
    await pollPause(RECOVER_POLL_MS);
    let job;
    try {
      const r = await fetch(`/api/forge-jobs/${encodeURIComponent(id)}`);
      if (r.status === 404) {
        if (!found && ++notFound >= RECOVER_NOT_FOUND) {
          note(appT("app.lost.never_started"));
          appendLog(appT("app.console.never_started"));
          return;
        }
        continue;
      }
      if (!r.ok) continue;
      job = await r.json();
    } catch (_) { continue; }  // still offline: keep trying until the deadline
    if (!found) { found = true; stillRunning(); }
    id = job.forge_id;  // a "latest" lookup pins to the job it found
    if (applyTokenState(job)) renderTokens();
    if (job.status === "running") {
      if (job.message && job.message !== lastMsg) { lastMsg = job.message; appendLog("• " + BTS_I18N.console(job.message)); }
      // An engine pick the stream never delivered (or delivered before it died): show it again. The answer
      // goes back on /api/forge/answer as usual, independent of the stream.
      if (job.choice && (!choiceState || choiceState.forgeId !== job.choice.forge_id)) renderChoice(job.choice);
      continue;
    }
    el("forge-lost").classList.add("hidden");
    if (job.status === "done" && job.class_id) {
      try {
        const r = await fetch(`/api/classes/${job.class_id}`);
        if (r.ok) { appendLog(appT("app.console.done_reconnected")); renderResult(await r.json()); return; }
      } catch (_) { /* fall through to the pointer */ }
      appendLog(appT("app.console.done_open_library"));
      toast(appT("app.lost.toast_ready"));
      return;
    }
    const msg = (BTS_I18N.err(job, "") || appT("app.lost.failed_fallback"))
      + (job.refunded ? appT("app.lost.refunded_suffix") : "");
    appendLog("✗ " + msg);
    toast(msg);
    return;
  }
  note(token ? appT("app.lost.gave_up_token") : appT("app.lost.gave_up"));
}

// Wait `ms`, but wake as soon as the tab is visible again or the network comes back: a phone that slept
// through the forge should see the result the moment it's picked up, not up to one poll later.
function pollPause(ms) {
  return new Promise((resolve) => {
    const wake = () => {
      if (document.visibilityState !== "visible") return;
      clearTimeout(t);
      document.removeEventListener("visibilitychange", wake);
      window.removeEventListener("online", wake);
      resolve();
    };
    const t = setTimeout(() => {
      document.removeEventListener("visibilitychange", wake);
      window.removeEventListener("online", wake);
      resolve();
    }, ms);
    document.addEventListener("visibilitychange", wake);
    window.addEventListener("online", wake);
  });
}

async function consumeSSE(resp, handler) {
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buf.indexOf("\n\n")) !== -1) {
      const chunk = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      let event = "message", data = "";
      for (const line of chunk.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data += line.slice(5).trim();
      }
      if (data) handler(event, JSON.parse(data));
    }
  }
}

function onForgeEvent(event, data) {
  // Any event may carry an updated token_balance (charged on success, refunded on failure) — keep the
  // header chip in lockstep with the server.
  if (applyTokenState(data)) renderTokens();
  if (event === "progress") appendLog("• " + BTS_I18N.console(data.message));
  else if (event === "choice") renderChoice(data);
  else if (event === "error") { const m = BTS_I18N.err(data, ""); appendLog("✗ " + m); toast(m); }
  else if (event === "result") { appendLog(appT("app.console.done")); renderResult(data); }
}

// A freshly forged class: spinner off, then the shared renderer + the share bar + what it consumed.
function renderResult(cls) {
  el("spinner").classList.add("hidden");
  renderClassView(cls);
  renderShareBar(cls, false);
  renderUsage(cls);
  // On a phone the result lands under the forge box and the progress log, a screen or two down: bring it
  // (and its "Send to my PC" row) into view. Desktops keep their scroll position.
  if (IS_PHONE) el("result").scrollIntoView({ block: "start" });
}

// What "Copy share link" puts on the clipboard (FORGE_FIRST_PLAN.md 5.5): a one-line blurb with the link,
// `"<name>" — <description>. Play it: <url>`, the description cut to ~140 characters at a word boundary.
function shareText(name, description, url) {
  let d = String(description || "").replace(/\s+/g, " ").trim();
  if (d.length > 140) {
    const cut = d.slice(0, 140);
    const sp = cut.lastIndexOf(" ");
    d = (sp > 60 ? cut.slice(0, sp) : cut).replace(/[\s.,;:!?\u2014-]+$/, "") + "\u2026";
  } else {
    d = d.replace(/[.!?]+$/, "");
  }
  const head = String(name || appT("app.share.name_fallback")).trim();
  return d ? appT("app.share.text", { name: head, description: d, url })
    : appT("app.share.text_no_description", { name: head, url });
}

// The bar above a rendered class: a share link (the public /deck/<slug> page) and, when the class was opened
// from the library, a way back to the forge. Classes without a slug simply get no share button.
function renderShareBar(cls, viewing) {
  const share = el("share-link");
  const url = cls.share_url || (cls.slug ? `${location.origin}/deck/${cls.slug}` : "");
  share.dataset.url = url;
  share.dataset.text = url ? shareText(cls.name || cls.character?.name, cls.character?.description || cls.concept, url) : "";
  share.classList.toggle("hidden", !url);
  const nom = el("nominate");
  nom.classList.toggle("hidden", cls.id == null || !ME);
  if (cls.id != null && ME) paintNominate(nom, cls);
  wireHandoff(el("send-pc"), el("email-me"), cls, url);
  const why = emailBlocker();
  el("r-handoff-note").textContent = why;
  el("r-handoff-note").classList.toggle("hidden", !why);
  el("view-back").classList.toggle("hidden", !viewing);
  el("view-title").textContent = viewing ? appT("app.result.view_saved") : appT("app.result.view_new");
  el("view-bar").classList.remove("hidden");
}

// --- The Archive: nominate a class (FORGE_FIRST_PLAN.md 5.2) -----------------------------------------
// One control in three states, on the result bar (#nominate) and on every My Classes row: not nominated ->
// "☆ Nominate for The Archive" (asks for an optional note, POST); nominated -> "★ Nominated · withdraw"
// (DELETE); featured -> "★ In The Archive" (disabled; only an admin takes a class out). `c` is the class
// object the button was painted from (a /api/classes row or a detail/result payload); it is updated in place.
function paintNominate(btn, c) {
  const featured = !!c.featured, nominated = !featured && !!c.nominated;
  btn.disabled = featured;
  btn.textContent = featured ? appT("app.nominate.featured") : nominated ? appT("app.nominate.nominated")
    : appT("app.result.nominate");
  btn.title = featured ? appT("app.nominate.tip_featured")
    : nominated ? appT("app.nominate.tip_nominated")
      : appT("app.nominate.tip_nominate");
  btn.classList.toggle("on", featured || nominated);
  btn.onclick = featured ? null : () => toggleNomination(btn, c);
}

async function toggleNomination(btn, c) {
  const withdraw = !!c.nominated;
  let body;
  if (!withdraw) {
    const note = prompt(appT("app.nominate.prompt"), "");
    if (note === null) return;  // cancelled
    body = JSON.stringify({ note: String(note).trim().slice(0, 200) });
  }
  btn.disabled = true;
  try {
    const r = await fetch(`/api/classes/${c.id}/nominate`, {
      method: withdraw ? "DELETE" : "POST", headers: { "Content-Type": "application/json" }, body,
    });
    const d = await r.json().catch(() => ({}));
    if (r.status === 409) c.featured = true;  // picked meanwhile
    if (!r.ok) throw new Error(appErr(d, r.status));
    for (const t of [c, libClasses.find((x) => x.id === c.id)]) {
      if (t) { t.nominated = !!d.nominated; t.featured = !!d.featured; t.featured_word = d.featured_word; }
    }
    toast(withdraw ? appT("app.nominate.toast_withdrawn") : appT("app.nominate.toast_nominated"));
  } catch (e) {
    toast(e.message || appT("app.common.toast_retry"));
  } finally {
    paintNominate(btn, c);
  }
}

// --- phone -> PC hand-off (PHONE_FUNNEL_PLAN.md 5.2) -------------------------------------------------
// "Send to my PC" (render.js sendToPc: the share sheet, else copy the link) and "Email it to me" (POST
// /api/classes/<id>/email: the link + the import code to the account's own address). Shown on phones only
// (.phone-only); the email button is disabled, with the reason in its title, when it cannot work.
function emailBlocker() {
  if (!ME_META || !ME_META.mail) return appT("app.handoff.no_mail_server");
  if (!ME || !ME.email) return appT("app.handoff.no_email");
  return "";
}

function wireHandoff(sendBtn, mailBtn, cls, url) {
  const name = cls.character?.name || cls.name || "";
  sendBtn.disabled = !url;
  sendBtn.onclick = () => sendToPc(name, url);
  const why = cls.id == null ? appT("app.handoff.open_from_library") : emailBlocker();
  mailBtn.disabled = !!why;
  mailBtn.title = why || appT("app.handoff.email_tip", { email: ME?.email || appT("app.handoff.email_tip_fallback") });
  mailBtn.onclick = why ? null : () => emailClass(cls.id, mailBtn);
}

async function emailClass(id, btn) {
  btn.disabled = true;
  try {
    const r = await fetch(`/api/classes/${id}/email`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ lang: BTS_I18N.lang }),
    });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(appErr(d, r.status));
    toast(appT("app.handoff.toast_sent", { email: d.to || appT("app.handoff.toast_sent_fallback") }));
  } catch (e) {
    toast(e.message || appT("app.handoff.toast_failed"));
  } finally {
    btn.disabled = false;
  }
}

// What this forge consumed (the server sums the usage meter): shown after a BYOK forge so the cost warning
// is followed by the real number; hidden on the token path where the tokens aren't the user's.
function renderUsage(cls) {
  const line = el("r-usage");
  const u = cls.usage;
  if (!u || currentMode() !== "byok") { line.classList.add("hidden"); return; }
  // The art rows are the user's too: images made and the dollars — "metered" only when the vendor
  // actually reported a cost (OpenRouter); Gemini/xAI/OpenAI report none, so that figure is the list-price
  // "est." and must never read as a bill.
  const art = u.images
    ? appT("app.result.usage_images", { count: u.images })
      + (u.art_cost_usd != null
          ? appT("app.result.usage_art_cost", { cost: Number(u.art_cost_usd).toFixed(2),
              kind: u.art_cost_metered ? appT("app.result.usage_metered") : appT("app.result.usage_est") }) : "")
    : "";
  line.textContent = appT("app.result.usage", {
    calls: u.calls, input: fmtTokens(u.input_tokens),
    cached: u.cached_tokens ? appT("app.result.usage_cached", { cached: fmtTokens(u.cached_tokens) }) : "",
    output: fmtTokens(u.output_tokens), art });
  line.classList.remove("hidden");
}

// --- interactive forge: the mid-forge archetype pick ----------------------------------------------
// The 'choice' SSE event carries the theme-matched engines; the answer goes back on a second request
// (/api/forge/answer). The server auto-continues on its own timeout, so every path out of this panel
// (pick / skip / countdown expiry / stream death) just cleans up the UI — the forge never blocks.

let choiceState = null;

function resetChoice() {
  if (choiceState?.timer) clearInterval(choiceState.timer);
  choiceState = null;
  el("choice").classList.add("hidden");
}

function renderChoice(data) {
  resetChoice();
  choiceState = {
    forgeId: data.forge_id,
    picked: new Set(),
    deadline: Date.now() + (Number(data.timeout_s) || 120) * 1000,
    timer: null,
    sent: false,
  };
  const wrap = el("choice-options");
  wrap.innerHTML = "";
  for (const o of data.options || []) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "choice-opt";
    b.dataset.id = o.id;
    // one line of body text: the map stage's strategy pitch; wildcards/older payloads fall back to
    // the catalog's one-line description, then the raw resonance lines.
    const why = o.pitch || o.description || (o.resonance || []).join(" · ");
    // headline = the themed title the map stage wrote ("Rich in Energy"); wildcards have no themed
    // title, so their engine name stays the headline.
    const title = o.title || o.name;
    // an engine the player asked for by name in their concept ("an orb class") — the front-end pinned it
    // onto the menu (frontend.request); say so, since it may have no themed title/pitch of its own.
    b.innerHTML = `<strong>${esc(title)}</strong>`
      + (o.requested ? `<span class="co-req">${appH("app.choice.requested_badge")}</span>` : "")
      + (o.buildable ? "" : `<span class="co-warn">${appH("app.choice.needs_vocab")}</span>`)
      + (why ? `<em>${esc(why)}</em>` : "");
    b.onclick = () => toggleChoiceOpt(b, String(o.id));
    wrap.appendChild(b);
  }
  el("choice-go").disabled = true;
  el("choice").classList.remove("hidden");
  el("choice").scrollIntoView({ behavior: "smooth", block: "nearest" });
  choiceState.timer = setInterval(tickChoice, 500);
  tickChoice();
}

function toggleChoiceOpt(btn, id) {
  if (!choiceState || choiceState.sent) return;
  if (choiceState.picked.has(id)) {
    choiceState.picked.delete(id);
    btn.classList.remove("sel");
  } else {
    if (choiceState.picked.size >= 2) { toast(appT("app.choice.toast_max")); return; }
    choiceState.picked.add(id);
    btn.classList.add("sel");
  }
  el("choice-go").disabled = choiceState.picked.size === 0;
}

function tickChoice() {
  if (!choiceState) return;
  const left = Math.max(0, Math.round((choiceState.deadline - Date.now()) / 1000));
  el("choice-timer").textContent = appT("app.choice.timer", { seconds: left });
  if (left <= 0) {
    appendLog(appT("app.console.choice_timeout"));
    resetChoice();
  }
}

async function sendChoice(picks) {
  if (!choiceState || choiceState.sent) return;
  choiceState.sent = true;
  const forgeId = choiceState.forgeId;
  resetChoice();
  appendLog(picks.length ? appT("app.console.picked", { picks: picks.join(", ") }) : appT("app.console.skipped"));
  try {
    const r = await fetch("/api/forge/answer", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ forge_id: forgeId, archetypes: picks }),
    });
    if (!r.ok) {
      const e = await r.json().catch(() => ({}));
      appendLog(e.error || e.code ? "• " + BTS_I18N.err(e, "") : appT("app.console.pick_failed"));
    }
  } catch {
    // the server's own timeout auto-continues the forge; nothing to recover here
  }
}

function appendLog(line) {
  const log = el("log");
  log.textContent += (log.textContent ? "\n" : "") + line;
  log.scrollTop = log.scrollHeight;
}

// --- library -------------------------------------------------------------------------------------

let libClasses = [];  // the last /api/classes payload, so the art toggle can repaint without a refetch

async function loadLibrary() {
  let classes;
  try {
    const r = await fetch("/api/classes");
    ({ classes } = await r.json());
  } catch (_) {
    toast(appT("app.library.toast_load_failed"));
    return;
  }
  libClasses = classes;
  paintLibrary();
}

function paintLibrary() {
  const list = el("lib-list");
  list.innerHTML = "";
  el("lib-empty").classList.toggle("hidden", libClasses.length > 0);
  el("lib-show-art").checked = artEnabled();
  for (const c of libClasses) list.appendChild(libRow(c));
}

function libRow(c) {
  const li = document.createElement("li");
  li.className = "lib-row";
  li.innerHTML = `<div class="lr-main"><span class="lr-name">${esc(c.name)}</span>`
    + `<span class="lr-meta">${appH("app.library.cards_meta", { count: c.card_count, vocab: c.vocab_version })}</span>`
    + `<div class="lr-concept muted">${esc(c.concept || "")}</div></div>`
    + `<div class="lr-actions">`
    + `<button data-act="share" title="${esc(appT("app.result.share_tip"))}">${appH("app.library.share")}</button>`
    + `<button data-act="sendpc" class="phone-only">${appH("app.handoff.send_pc")}</button>`
    + `<button data-act="email" class="phone-only">${appH("app.handoff.email_me")}</button>`
    + `<button data-act="code" title="${esc(appT("app.library.code_tip"))}">${appH("app.result.copy_code")}</button>`
    + `<button data-act="nominate"></button>`
    + `<button data-act="rename">${appH("app.library.rename")}</button>`
    + `<button data-act="open">${appH("app.library.open")}</button>`
    + `<button data-act="delete" class="danger">${appH("app.library.delete")}</button></div>`;
  // Splash + sprite thumbnails lead the row (art on, and only when the class shipped with art — a BYOK
  // forge on a text-only provider has neither, and pruned art drops the field server-side).
  if (artEnabled() && (c.splash_thumb_url || c.sprite_thumb_url)) {
    const art = document.createElement("div");
    art.className = "lr-art";
    if (c.splash_thumb_url) art.appendChild(artImg(c.splash_thumb_url, "lr-splash", appT("app.library.splash_alt", { name: c.name })));
    if (c.sprite_thumb_url) art.appendChild(artImg(c.sprite_thumb_url, "lr-sprite", appT("app.library.sprite_alt", { name: c.name })));
    li.insertBefore(art, li.firstChild);
  }
  const share = li.querySelector('[data-act="share"]');
  // List rows carry no description (ForgedClass.summary), so the concept stands in for it.
  if (c.slug) share.onclick = () => copy(shareText(c.name, c.description || c.concept, `${location.origin}/deck/${c.slug}`));
  else share.remove();  // classes without a slug (none since the backfill) simply get no share button
  wireHandoff(li.querySelector('[data-act="sendpc"]'), li.querySelector('[data-act="email"]'), c,
              c.slug ? `${location.origin}/deck/${c.slug}` : "");
  li.querySelector('[data-act="code"]').onclick = () => copyClassCode(c.id);
  paintNominate(li.querySelector('[data-act="nominate"]'), c);
  li.querySelector('[data-act="rename"]').onclick = () => renameClass(c.id, c.name);
  li.querySelector('[data-act="open"]').onclick = () => openClass(c.id);
  li.querySelector('[data-act="delete"]').onclick = () => deleteClass(c.id, c.name);
  return li;
}

async function copyClassCode(id) {
  const r = await fetch(`/api/classes/${id}`);
  const cls = await r.json();
  await copy(cls.code);
}
// Open a saved class in "viewing" mode: the forge input card and the progress log get out of the way so
// the class has the page to itself; the Forge tab (or the bar's back button) brings the forge back.
async function openClass(id) {
  const r = await fetch(`/api/classes/${id}`);
  const cls = await r.json();
  el("nav-forge").classList.remove("active");
  el("nav-library").classList.add("active");
  el("nav-account").classList.remove("active");
  show("view-forge");
  el("forge-input").classList.add("hidden");
  el("v3-banner").classList.add("hidden");
  el("phone-banner").classList.add("hidden");
  el("progress").classList.add("hidden");
  el("spinner").classList.add("hidden");
  renderClassView(cls);
  renderShareBar(cls, true);
  el("r-usage").classList.add("hidden");
  window.scrollTo({ top: 0 });
}
async function renameClass(id, oldName) {
  const name = prompt(appT("app.library.rename_prompt"), oldName);
  if (!name) return;
  await fetch(`/api/classes/${id}`, {
    method: "PATCH", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  loadLibrary();
}
async function deleteClass(id, name) {
  if (!confirm(appT("app.library.delete_confirm", { name }))) return;
  await fetch(`/api/classes/${id}`, { method: "DELETE" });
  loadLibrary();
}

// --- account: balance, donations (fixed-tier Stripe Checkout), donation history ------------------

let DONATE_CFG = null;  // /api/billing payload, fetched once and rendered into both tier panels

async function loadAccount() {
  el("acct-email").textContent = ME ? (ME.email || ME.name || "") : "";
  renderSignInMethods();
  try {
    // Balance can have moved server-side (a webhook credit, another tab) — refresh it too, along with
    // the identities: coming back from a link flow lands here and must show the new method.
    const [meR, purR] = await Promise.all([fetch("/api/me"), fetch("/api/purchases")]);
    const meData = await meR.json();
    if (meData.user) {
      ME = meData.user; ME_META = meData; renderTokens(); renderSignInMethods();
      if (ME.welcome_grant) renderWelcome(ME.welcome_grant);
    }
    await loadDonation();
    renderPurchases((await purR.json()).purchases || []);
  } catch (_) {
    toast(appT("app.account.toast_load_failed"));
  }
  loadStats();
  loadTraffic();
  loadAdminUsers();
  loadAdminArchive();
  loadAdminEvents();
}

// Which sign-ins reach this account, and what is left to add. No unlinking in v1 (see index.html).
// Read lazily (the strings load after this file is parsed). "Dev" is a dev-only label, not in COPY.md.
const IDENTITY_LABELS = {
  get google() { return appT("app.account.identity.google"); },
  get discord() { return appT("app.account.identity.discord"); },
  get github() { return appT("app.account.identity.github"); },
  get email() { return appT("app.account.identity.email"); },
  dev: "Dev",
};

// Light masking for the identity label: an address shows as "r…@gmail.com" — enough to tell two accounts
// apart without printing the whole thing. A display name or a provider id is left as it is.
function maskIdentity(label) {
  const at = String(label || "").indexOf("@");
  return at > 0 ? label[0] + "…" + label.slice(at) : String(label || "");
}

function renderSignInMethods() {
  const list = el("acct-identities");
  if (!list) return;
  const identities = (ME && ME.identities) || [];
  list.innerHTML = "";
  for (const i of identities) {
    const li = document.createElement("li");
    const provider = IDENTITY_LABELS[i.provider] || i.provider;
    li.textContent = i.label ? appT("app.account.identity_row", { provider, label: maskIdentity(i.label) }) : provider;
    list.appendChild(li);
  }

  // Everything this deploy offers that the account hasn't got yet. /login?link=1 is the chooser in link
  // mode: it keeps the session, so whatever is picked there attaches to this account.
  const owned = new Set(identities.map((i) => i.provider));
  const missing = ((ME_META && ME_META.providers) || []).filter((p) => !owned.has(p));
  if (ME_META && ME_META.email_login && !owned.has("email")) missing.push("email");
  const options = el("acct-link-options");
  options.innerHTML = "";
  for (const p of missing) {
    const a = document.createElement("a");
    a.className = "btn ghost";
    a.href = "/login?link=1";
    a.textContent = IDENTITY_LABELS[p] || p;
    options.appendChild(a);
  }
  el("acct-link-row").classList.toggle("hidden", missing.length === 0);
}

function fmtMoney(cents, currency) {
  try {
    return new Intl.NumberFormat(undefined, { style: "currency", currency: (currency || "usd").toUpperCase() })
      .format((cents || 0) / 100);
  } catch (_) { return `$${((cents || 0) / 100).toFixed(2)}`; }
}

// Tier headlines want "$3", not "$3.00" — the fee line under them carries the cents.
function fmtMoneyShort(cents, currency) { return fmtMoney(cents, currency).replace(/[.,]00$/, ""); }

// /api/billing is static config (fixed tiers) — fetch it once, then render the same buttons into the
// forge tab's inline panel and the Account tab.
async function loadDonation() {
  if (!DONATE_CFG) {
    try {
      const r = await fetch("/api/billing");
      DONATE_CFG = await r.json();
    } catch (_) { DONATE_CFG = null; }
  }
  renderDonation(DONATE_CFG);
}

function renderDonation(cfg) {
  DONATE_CFG = cfg || null;
  renderDonatePanel("donate", "donate-tiers", "donate-custom", "donate-note", cfg);
  renderDonatePanel("forge-donate-box", "forge-donate-tiers", "forge-donate-custom",
                    "forge-donate-note", cfg);
}

// One panel: the tier buttons + the custom-amount row, or the "switched off" note in their place.
function renderDonatePanel(boxId, tiersId, customId, noteId, cfg) {
  const enabled = !!(cfg && cfg.enabled);
  const box = el(boxId), note = el(noteId);
  if (!box) return;
  box.classList.toggle("hidden", !enabled);
  if (note) note.classList.toggle("hidden", enabled);
  if (enabled) { renderTiers(el(tiersId), cfg); renderCustomAmount(el(customId), cfg); }
}

// What the card is charged for a `net_cents` donation, and the fee inside it — the same arithmetic as
// billing.gross_for(), from the rates /api/billing publishes, so the two can't drift.
function grossFee(netCents, custom) {
  const pct = Number(custom.fee_pct || 0), fixed = Number(custom.fee_fixed_cents || 0);
  const gross = Math.ceil((netCents + fixed) / (1 - pct / 100));
  return { gross, fee: gross - netCents };
}

// Which custom-amount panels are open, by container id. Kept outside the renderer so a re-render (a fresh
// /api/billing, a returning purchase) doesn't fold a box the user just opened, and so the forge tab and the
// Account tab each remember their own.
const CUSTOM_SHOWN = new Set();

// Collapsed by default: one centred "Enter another custom amount" button under the tier buttons, since the
// three fixed amounts are what most people want. Clicking it swaps in the real row.
// "$ [ 25 ] (Get 25 tokens)" above a line spelling out the real charge. Everything past the fixed tiers is
// one token per dollar, whole dollars only. No `custom` block in /api/billing (an older server) hides it.
// Ids are derived from the container so the forge tab and the Account tab can both render one.
function renderCustomAmount(container, cfg) {
  if (!container) return;
  const c = cfg && cfg.custom;
  container.innerHTML = "";
  container.classList.toggle("hidden", !c);
  if (!c) return;
  const min = Number(c.min_dollars || 0), max = Number(c.max_dollars || 0);
  const per = Number(c.tokens_per_dollar || 1);
  const base = container.id;
  if (!CUSTOM_SHOWN.has(base)) {
    container.innerHTML = `<div class="custom-reveal"><button id="${base}-open" class="btn" type="button">`
      + `${appH("app.donate.custom_reveal")}</button></div>`;
    el(`${base}-open`).onclick = () => { CUSTOM_SHOWN.add(base); renderCustomAmount(container, cfg); };
    return;
  }
  container.innerHTML =
    `<div class="custom-row"><span class="custom-cur">$</span>`
    + `<input id="${base}-input" class="in custom-amt" type="number" min="${min}" max="${max}" step="1" `
    + `inputmode="numeric" placeholder="${esc(appT("app.donate.custom_placeholder", { min }))}" `
    + `aria-label="${esc(appT("app.donate.custom_aria"))}" />`
    + `<button id="${base}-btn" class="btn" type="button">${appH("app.donate.custom_button")}</button></div>`
    + `<p id="${base}-line" class="hint custom-line"></p>`;
  const input = el(`${base}-input`), btn = el(`${base}-btn`), line = el(`${base}-line`);
  const sentence = appT("app.donate.custom_rule", { min });
  const sync = () => {
    const n = customDollars(input.value, c);
    btn.textContent = n ? appT("app.donate.custom_button_n", { count: n * per }) : appT("app.donate.custom_button");
    if (!n) { line.textContent = sentence; return; }
    const { gross, fee } = grossFee(n * 100, c);
    line.textContent = `${sentence} `
      + appT("app.donate.fee_line", { gross: fmtMoney(gross, cfg.currency), fee: fmtMoney(fee, cfg.currency) });
  };
  input.oninput = sync;
  btn.onclick = () => donateCustom(input.value, btn, cfg);
  sync();
  input.focus();
}

// The typed amount as a whole number of dollars inside the allowed range, or 0 when it isn't one.
function customDollars(raw, c) {
  const s = String(raw || "").trim();
  const n = Number(s);
  if (!s || !Number.isInteger(n)) return 0;
  if (n < Number(c.min_dollars || 0) || n > Number(c.max_dollars || 0)) return 0;
  return n;
}

// The shared tier component: the headline amount over a small line spelling out what the card is
// actually charged, Stripe's pass-through fee included. Same markup on both tabs.
function renderTiers(container, cfg) {
  if (!container) return;
  container.innerHTML = "";
  for (const t of (cfg && cfg.tiers) || []) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "btn donate-tier";
    const n = Number(t.tokens || 0);
    b.innerHTML = `<span class="tier-label">`
      + appH("app.donate.tier_label", { amount: fmtMoneyShort(t.net_cents, cfg.currency), count: n }) + `</span>`
      + `<span class="tier-fee">`
      + appH("app.donate.fee_line", { gross: fmtMoney(t.gross_cents, cfg.currency),
                                     fee: fmtMoney(t.fee_cents, cfg.currency) }) + `</span>`;
    b.onclick = () => donate(t.id, b);
    container.appendChild(b);
  }
}

async function donate(tierId, btn) {
  if (!tierId) return;
  await startCheckout({ tier: tierId }, btn);
}

// The custom-amount button. The server re-validates; this only keeps a hopeless request off the wire.
async function donateCustom(raw, btn, cfg) {
  const c = (cfg && cfg.custom) || null;
  if (!c) return;
  const n = customDollars(raw, c);
  if (!n) {
    toast(appT("app.donate.toast_bad_amount", { min: c.min_dollars, max: c.max_dollars }));
    return;
  }
  await startCheckout({ custom_dollars: n }, btn);
}

// Both donate paths: ask the server for a Stripe Checkout session and hand the browser over to it.
async function startCheckout(payload, btn) {
  btn.disabled = true;
  const label = btn.innerHTML;
  btn.textContent = appT("app.donate.redirecting");
  try {
    const r = await fetch("/api/donate", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...payload, lang: BTS_I18N.lang }),  // Stripe Checkout locale + line-item names
    });
    const d = await r.json();
    if (!r.ok) throw new Error(appErr(d, r.status));
    stashDraft();           // the concept survives the round trip (restoreDraft on the way back)
    location.href = d.url;  // off to Stripe's hosted checkout page
  } catch (e) {
    toast(e.message);
    btn.disabled = false;
    btn.innerHTML = label;
  }
}

function renderPurchases(purchases) {
  const list = el("purchase-list");
  list.innerHTML = "";
  el("purchases-empty").classList.toggle("hidden", purchases.length > 0);
  for (const p of purchases) {
    const li = document.createElement("li");
    li.className = "lib-row";
    const when = p.created_at
      ? new Date(p.created_at).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" })
      : "";
    // amount_cents is always the gross charge. v3 donations pass Stripe's fee to the donor, so those
    // rows split it out; pre-v3 donations and the "pack" rows (token packs, 2026-09-08..16) have no
    // net_cents and keep the old wording.
    const gross = fmtMoney(p.amount_cents, p.currency);
    const fee = typeof p.fee_cents === "number"
      ? p.fee_cents : Number(p.amount_cents || 0) - Number(p.net_cents || 0);
    const what = p.kind === "donation"
      ? (typeof p.net_cents === "number"
        ? appT("app.history.donated_split", { gross, net: fmtMoney(p.net_cents, p.currency),
                                               fee: fmtMoney(fee, p.currency) })
        : appT("app.history.donated", { gross }))
      : appT("app.history.pack", { gross });   // a pre-v3 pack row: never "buy"/"purchase" in donor copy (pricing v3)
    li.innerHTML = `<div class="lr-main"><span class="lr-name">${esc(what)}</span>`
      + `<span class="lr-meta">${appH("app.history.tokens", { count: p.tokens, date: when })}`
      + (p.status === "refunded" ? ` · <span class="refunded">${appH("app.history.refunded")}</span>` : "")
      + `</span></div>`;
    list.appendChild(li);
  }
}

// Back from Stripe: /app?purchase=success&session_id=... or /app?purchase=cancel. Confirm the payment
// server-side (which also credits it immediately if the webhook hasn't landed yet), then clean the URL
// so a refresh doesn't re-fire any of this.
async function handlePurchaseReturn() {
  const params = new URLSearchParams(location.search);
  const outcome = params.get("purchase");
  if (!outcome) return;
  const sessionId = params.get("session_id") || "";
  history.replaceState(null, "", "/app");
  if (outcome === "cancel") { toast(appT("app.checkout.toast_canceled")); return; }
  if (outcome !== "success" || !sessionId) return;

  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      const r = await fetch(`/api/checkout-status?session_id=${encodeURIComponent(sessionId)}`);
      const d = await r.json();
      if (!r.ok) throw new Error(appErr(d, r.status));
      if (d.status === "paid") {
        applyTokenState(d);
        renderTokens();
        const added = appT("app.checkout.added", { count: d.tokens });
        toast(d.tokens > 0
          ? (DRAFT_RESTORED ? appT("app.checkout.toast_thanks_draft", { added })
                            : appT("app.checkout.toast_thanks", { added }))
          : appT("app.checkout.toast_thanks_plain"));
        // They came here to forge, not to read the Account tab: land on the forge, token path armed, the pay
        // step open on "You have N tokens" and the Forge button in view.
        setForgePref("token");
        setMode("token");
        selectTab("forge");
        revealPayStep("");
        el("forge-btn").scrollIntoView({ behavior: "smooth", block: "center" });
        el("forge-btn").focus({ preventScroll: true });
        return;
      }
    } catch (e) {
      toast(e.message);
      return;
    }
    await new Promise((res) => setTimeout(res, 2000));  // still processing — give Stripe a moment
  }
  toast(appT("app.checkout.toast_processing"));
}

// --- admin: forge stats dashboard -----------------------------------------------------------------
// Only accounts on BTSWEB_ADMIN_EMAILS (defaults to the unlimited list) get user.admin from /api/me; for
// everyone else the card stays hidden and nothing is fetched. Data: /api/admin/stats?days=N — forge_jobs
// (one row per attempt: mode, token kind, status), forge_usage (LLM tokens per role/model/provider) and
// purchases. Chart colors were validated against the dark panel surface (#1e1c28) — keep them paired
// with the legend + hover labels so identity never rides on color alone.
const STATS_SERIES = [
  { key: "token", label: "Hosted (our key)", color: "#8f55eb" },
  { key: "byok", label: "Bring your own key", color: "#28a07f" },
  { key: "fake", label: "Offline demo", color: "#c48420" },
];

async function loadStats() {
  const card = el("stats");
  if (!card) return;
  if (!ME || !ME.admin) { card.classList.add("hidden"); return; }
  card.classList.remove("hidden");
  const days = el("stats-days").value;
  try {
    const r = await fetch(`/api/admin/stats?days=${encodeURIComponent(days)}`);
    if (!r.ok) throw new Error("HTTP " + r.status);
    renderStats(await r.json());
  } catch (e) {
    el("stats-note").textContent = "Couldn't load forge stats: " + e.message;
  }
}

function fmtInt(n) { return Number(n || 0).toLocaleString("en-US"); }
function fmtUsd(n) { return n == null ? "—" : "$" + Number(n).toFixed(2); }
function pct(a, b) { return b > 0 ? Math.round((100 * a) / b) + "%" : "—"; }

function renderStats(d) {
  const f = d.forges || {}, bm = f.by_mode || {}, bk = f.by_token_kind || {};
  const h = d.hosted || {}, u = d.users || {}, dn = d.donations || {};
  const tiles = [
    { k: "Forges", v: fmtInt(f.total), s: `${fmtInt(f.ok)} ok · ${fmtInt(f.failed)} failed · ${fmtInt(f.refunded)} refunded` },
    // bk.free only ever counts pre-v3 rows now (the daily grant is gone), so it is shown when there is one.
    { k: "Hosted (our key)", v: fmtInt(bm.token), s: `${pct(bm.token, f.total)} of forges · paid ${fmtInt(bk.paid)} · ∞ ${fmtInt(bk.unlimited)}`
      + (bk.free ? ` · ${fmtInt(bk.free)} legacy free` : "") },
    { k: "Bring your own key", v: fmtInt(bm.byok), s: `${pct(bm.byok, f.total)} of forges` + (bm.fake ? ` · ${fmtInt(bm.fake)} offline demo` : "") },
    { k: "People forging", v: fmtInt(u.forgers), s: `${fmtInt(u.accounts)} accounts total` },
    { k: "Hosted LLM spend", v: fmtUsd(h.est_cost_usd), s: `${fmtInt(h.calls)} calls · ${fmtTokens(h.input_tokens)} in (${fmtTokens(h.cached_tokens)} cached) · ${fmtTokens(h.output_tokens)} out` },
    { k: "Donations", v: fmtMoney(dn.amount_cents || 0, "usd"), s: `${fmtInt(dn.count)} donations · ${fmtInt(dn.tokens)} tokens granted` },
    // The Archive's queue and showcase: current counts, not windowed.
    ...(d.archive ? [
      { k: "Nominations pending", v: fmtInt(d.archive.pending), s: "waiting in Archive nominations (Account tab)" },
      { k: "In The Archive", v: fmtInt(d.archive.featured), s: "classes on /archive right now" },
    ] : []),
  ];
  el("stats-tiles").innerHTML = tiles.map((t) =>
    `<div class="stat-tile"><div class="k">${esc(t.k)}</div><div class="v">${esc(t.v)}</div><div class="s">${esc(t.s)}</div></div>`).join("");

  renderStatsChart(d.daily || []);

  const provRows = (d.providers || []).map((p) =>
    `<tr><td>${esc(p.provider || "unknown")}</td><td class="num">${fmtInt(p.forges)}</td><td class="num">${pct(p.forges, f.total)}</td></tr>`).join("");
  el("stats-providers").innerHTML = `<tr><th>Provider</th><th class="num">Forges</th><th class="num">Share</th></tr>`
    + (provRows || `<tr><td colspan="3" class="muted">No usage rows in this window.</td></tr>`);

  const modelRows = (d.models || []).map((m) =>
    `<tr><td class="id">${esc(m.model || "?")}<div class="muted">${esc(m.provider || "")} · ${esc(m.mode || "")}</div></td>`
    + `<td class="num">${fmtInt(m.forges)}</td><td class="num">${fmtInt(m.calls)}</td>`
    + `<td class="num">${fmtTokens(m.input_tokens)}</td><td class="num">${fmtTokens(m.output_tokens)}</td></tr>`).join("");
  el("stats-models").innerHTML = `<tr><th>Model</th><th class="num">Forges</th><th class="num">Calls</th><th class="num">In</th><th class="num">Out</th></tr>`
    + (modelRows || `<tr><td colspan="5" class="muted">No usage rows in this window.</td></tr>`);

  el("stats-note").textContent = (d.since ? `Since ${d.since} (UTC). ` : "All time. ")
    + "Hosted spend is estimated from the model price table (BTSWEB_MODEL_PRICES; models on the Ollama flat plan "
    + "count as $0). BYOK forges bill the user's own provider and carry no cost here.";
}

// Stacked bars, one per day with forges, hosted / BYOK / demo. Inline SVG, no library: recessive grid,
// 2px surface gaps between segments, legend above, per-bar hover title. Days with no forges are skipped
// (the API only returns days that have some), so the x axis labels the first, last and a few in between.
function renderStatsChart(daily, series = STATS_SERIES, boxId = "stats-chart",
                          empty = "No forges in this window.", aria = "Forges per day by mode") {
  const box = el(boxId);
  if (!daily.length) { box.innerHTML = `<p class="hint">${esc(empty)}</p>`; return; }
  const STATS_SERIES = series;
  const W = 720, H = 200, padL = 34, padR = 8, padT = 8, padB = 22;
  const innerW = W - padL - padR, innerH = H - padT - padB;
  const totals = daily.map((r) => STATS_SERIES.reduce((n, s) => n + Number(r[s.key] || 0), 0));
  const max = Math.max(1, ...totals);
  const step = innerW / daily.length;
  const barW = Math.max(2, Math.min(28, step - 3));
  const y = (v) => padT + innerH - (v / max) * innerH;
  const ticks = [0, Math.ceil(max / 2), max];
  let svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(aria)}">`;
  for (const t of ticks) {
    svg += `<line class="grid" x1="${padL}" x2="${W - padR}" y1="${y(t).toFixed(1)}" y2="${y(t).toFixed(1)}" />`
      + `<text class="axis" x="${padL - 6}" y="${(y(t) + 4).toFixed(1)}" text-anchor="end">${t}</text>`;
  }
  daily.forEach((r, i) => {
    const x = padL + i * step + (step - barW) / 2;
    let acc = 0;
    const parts = STATS_SERIES.map((s) => `${s.label}: ${Number(r[s.key] || 0)}`).join(" · ");
    svg += `<g><title>${esc(r.day)} — ${esc(parts)}</title>`;
    for (const s of STATS_SERIES) {
      const v = Number(r[s.key] || 0);
      if (!v) continue;
      const top = y(acc + v), bottom = y(acc);
      const hgt = Math.max(0, bottom - top - (acc ? 2 : 0));  // 2px surface gap between stacked segments
      svg += `<rect x="${x.toFixed(1)}" y="${top.toFixed(1)}" width="${barW.toFixed(1)}" height="${hgt.toFixed(1)}" rx="2" fill="${s.color}" />`;
      acc += v;
    }
    svg += `</g>`;
    const labelEvery = Math.max(1, Math.ceil(daily.length / 8));
    // The last day is labelled too, unless it would sit on top of the previous label ("10-2610-27").
    const sincePrev = i % labelEvery;
    if (sincePrev === 0 || (i === daily.length - 1 && sincePrev >= Math.ceil(labelEvery / 2))) {
      svg += `<text class="axis" x="${(x + barW / 2).toFixed(1)}" y="${H - 6}" text-anchor="middle">${esc(r.day.slice(5))}</text>`;
    }
  });
  svg += `</svg>`;
  const legend = `<div class="stats-legend">` + STATS_SERIES.map((s) =>
    `<span><i style="background:${s.color}"></i>${esc(s.label)}</span>`).join("") + `</div>`;
  box.innerHTML = legend + `<div class="stats-wrap">${svg}</div>`;
}

// --- admin: site traffic ------------------------------------------------------------------------------
// Same gate as the stats card. Data: /api/admin/traffic = the nginx access log summarised by
// tools/traffic_report.py (unique IPs per UTC day, crawlers/scanners dropped by user agent, so every
// number is a floor). The four depth buckets are exclusive per day, so the bars stack to "humans seen".
// "browser" = /api/me ran (landing.js calls it on every splash load), so it only proves a real browser;
// "signed_in" = a signed-in-only route answered 200. Summaries written before 2026-10-13 carry one "app"
// bucket instead (= today's browser + signed_in); trafficCompat() shows it as "ran our JS".
const TRAFFIC_SERIES = [
  { key: "signed_in", label: "Signed in", color: "#8f55eb" },
  { key: "clicked", label: "Clicked past the splash", color: "#28a07f" },
  { key: "browser", label: "Ran our JS, went no further", color: "#3f7fbf" },
  { key: "landing_only", label: "Splash only (no JS)", color: "#5a5870" },
];

function trafficCompat(r) {
  if (!r || r.browser !== undefined || r.signed_in !== undefined || r.app === undefined) return r || {};
  return { ...r, browser: r.app, signed_in: 0 };
}

// "desktop 12 · phone 9 · webview 7" (webview = an in-app browser, e.g. the YouTube app). "" on old data.
function deviceChips(dv) {
  if (!dv) return "";
  return `desktop ${fmtInt(dv.desktop)} · phone ${fmtInt(dv.phone)} · webview ${fmtInt(dv.phone_webview)}`;
}

async function loadTraffic() {
  const card = el("traffic");
  if (!card) return;
  if (!ME || !ME.admin) { card.classList.add("hidden"); return; }
  card.classList.remove("hidden");
  try {
    const r = await fetch("/api/admin/traffic");
    if (!r.ok) throw new Error("HTTP " + r.status);
    renderTraffic(await r.json());
  } catch (e) {
    el("traffic-note").textContent = "Couldn't load traffic: " + e.message;
  }
}

function renderTraffic(d) {
  if (!d.available) {
    el("traffic-tiles").innerHTML = "";
    el("traffic-chart").innerHTML = "";
    el("traffic-referers").innerHTML = el("traffic-pages").innerHTML = el("traffic-campaigns").innerHTML = "";
    el("traffic-note").textContent = d.reason || "No traffic summary yet.";
    return;
  }
  const days = el("traffic-days").value;
  const w = trafficCompat((d.windows || {})[days]);
  const daily = (d.daily || []).map(trafficCompat).filter((r) => !w.since || r.day >= w.since);
  el("traffic-report").classList.toggle("hidden", !d.report);

  const botShare = pct(w.bot_requests, w.requests);
  const dv = w.devices;
  const tiles = [
    { k: "Visitors", v: fmtInt(w.humans), s: `${fmtInt(w.landing_only)} splash only · ${fmtInt(w.browser)} ran our JS · ${fmtInt(w.clicked)} clicked through · ${fmtInt(w.signed_in)} signed in` },
    { k: "Signed in", v: fmtInt(w.signed_in), s: `${pct(w.signed_in, w.humans)} of visitors · used the app signed in` },
    ...(dv ? [{ k: "On a phone", v: pct(Number(dv.phone || 0) + Number(dv.phone_webview || 0), w.humans),
                s: deviceChips(dv) }] : []),
    { k: "Shared deck pages", v: fmtInt(w.deck), s: "unique visitors to /deck/…" },
    // Summaries written before The Archive shipped (2026-10-26) have no archive bucket.
    { k: "Archive page", v: w.archive !== undefined ? fmtInt(w.archive) : "—", s: "unique visitors to /archive" },
    // The mod fetching a class's art from /static/forged/ is the only trace a code was imported.
    { k: "Imported into the game", v: fmtInt(w.imports), s: `classes the mod fetched art for · ${fmtInt(w.import_fetches)} fetches · all-time ${fmtInt(Object.keys(d.imports || {}).length)}` },
    { k: "Requests", v: fmtInt(w.requests), s: `${botShare} from crawlers and scanners` },
  ];
  el("traffic-tiles").innerHTML = tiles.map((t) =>
    `<div class="stat-tile"><div class="k">${esc(t.k)}</div><div class="v">${esc(t.v)}</div><div class="s">${esc(t.s)}</div></div>`).join("");

  renderStatsChart(daily, TRAFFIC_SERIES, "traffic-chart", "No visitors in this window.", "Visitors per day by depth");

  const refRows = (w.referers || []).map((r) =>
    `<tr><td>${esc(r.source)}</td><td class="num">${fmtInt(r.visitors)}</td></tr>`).join("");
  el("traffic-referers").innerHTML = `<tr><th>Source</th><th class="num">Visitors</th></tr>`
    + (refRows || `<tr><td colspan="2" class="muted">No outside referers in this window (direct, search-with-no-referer, or private).</td></tr>`);
  const pageRows = (w.pages || []).map((r) =>
    `<tr><td>${esc(r.path)}</td><td class="num">${fmtInt(r.visitors)}</td></tr>`).join("");
  el("traffic-pages").innerHTML = `<tr><th>Page</th><th class="num">Visitors</th></tr>`
    + (pageRows || `<tr><td colspan="2" class="muted">No page hits in this window.</td></tr>`);
  // Tagged links: clicks = hits on a URL carrying utm_source, visitors = unique IPs, then how deep those
  // IPs got anywhere in the window (same IP = same person, as everywhere on this card).
  // Rows from before 2026-10-13 have "app" (= ran our JS) and no signed_in / devices: show "—" there.
  const campRows = (w.campaigns || []).map((r) => {
    const chips = deviceChips(r.devices);
    return `<tr><td>${esc(r.campaign)}${chips ? `<div class="muted">${esc(chips)}</div>` : ""}</td>`
      + `<td class="num">${fmtInt(r.clicks)}</td><td class="num">${fmtInt(r.visitors)}</td>`
      + `<td class="num">${fmtInt(r.clicked)}</td><td class="num">${fmtInt(r.browser !== undefined ? r.browser : r.app)}</td>`
      + `<td class="num">${r.signed_in !== undefined ? fmtInt(r.signed_in) : "—"}</td><td class="num">${fmtInt(r.workshop)}</td></tr>`;
  }).join("");
  el("traffic-campaigns").innerHTML =
    `<tr><th>source/campaign</th><th class="num">Clicks</th><th class="num">Visitors</th><th class="num">Clicked on</th><th class="num">Ran JS</th><th class="num">Signed in</th><th class="num">Workshop</th></tr>`
    + (campRows || `<tr><td colspan="7" class="muted">No tagged links in this window. Tag a link with ?utm_source=…&amp;utm_campaign=… and it shows up here.</td></tr>`);

  const span = w.since ? `${w.since} → ${d.last_day} (${fmtInt(w.day_count)} days, UTC)` : "no days logged";
  el("traffic-note").textContent = `${span}. From the nginx access log, refreshed ${d.generated_at || "?"}. `
    + "Unique IPs, crawlers and scanners dropped by user agent — spoofed ones still land in “splash only”, "
    + "so “ran our JS” and deeper are people. Device = the IP's first user agent of the day; "
    + "webview = an in-app browser (YouTube, Reddit, Discord). The site loads no analytics script.";
}

// --- wiring --------------------------------------------------------------------------------------

el("nav-forge").onclick = () => selectTab("forge");
el("nav-library").onclick = () => selectTab("library");
el("forge-lost-library").onclick = () => selectTab("library");
el("nav-account").onclick = () => selectTab("account");
el("tokens").onclick = () => selectTab("account");  // the header chip doubles as a shortcut to buy/see balance
el("forge-btn").onclick = forge;
el("choice-go").onclick = () => sendChoice([...(choiceState?.picked || [])]);
el("choice-skip").onclick = () => sendChoice([]);
el("copy-code").onclick = () => copy(el("r-code").value);
el("share-link").onclick = () => copy(el("share-link").dataset.text || el("share-link").dataset.url);
el("view-back").onclick = () => selectTab("forge");
// "Show art" repaints the list in place; an open class view follows via the body.no-art CSS rule, and
// the next render (open / forge) skips the art entirely.
el("lib-show-art").onchange = (ev) => { setArtEnabled(ev.target.checked); paintLibrary(); };
el("signout").onclick = async () => { await fetch("/logout", { method: "POST" }); location.href = "/"; };
el("load-models").onclick = () => loadModels();
el("pay-open").onclick = () => revealPayStep("");
el("v3-banner-x").onclick = () => { lsSet("bts_tutorial_banner_dismissed", "1"); renderBanner(); };
el("phone-banner-x").onclick = () => { lsSet("bts_phone_banner_dismissed", "1"); renderBanner(); };

// feedback overlay: close on the × button, a backdrop click, or Escape; submit posts the rating.
el("fb-close").onclick = closeFeedback;
el("fb-submit").onclick = submitFeedback;
el("fb-overlay").onclick = (ev) => { if (ev.target === el("fb-overlay")) closeFeedback(); };
document.addEventListener("keydown", (ev) => {
  if (ev.key === "Escape" && !el("fb-overlay").classList.contains("hidden")) closeFeedback();
});

async function loadModels({ auto = false } = {}) {
  const base_url = resolvedBaseUrl();
  const api_key = el("api_key").value.trim();
  if (!base_url || !api_key) { if (!auto) toast(appT("app.byok.toast_need_key")); return; }
  const pair = modelPair();
  if (pair === MODELS_LOADING_FOR) return;
  MODELS_LOADING_FOR = pair;
  const btn = el("load-models");
  btn.disabled = true; btn.textContent = appT("app.byok.loading");
  try {
    const r = await fetch("/api/models", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ base_url, api_key }),
    });
    const d = await r.json();
    if (!r.ok) throw new Error(appErr(d, r.status));
    if (pair !== modelPair()) return;  // the provider or key changed mid-request: that list is stale
    // The server drops models that can't run a forge (embeddings, speech, images, OpenRouter :free routes,
    // small or short-context models) and lists the ones a forge has finished on first ("recommended").
    setModelControl("select");
    const gone = populateModels(d);
    MODELS_LOADED_FOR = pair;
    const hid = d.hidden ? appT("app.byok.toast_loaded_hidden", { count: d.hidden }) : "";
    if (gone.length) toast(appT("app.byok.toast_saved_gone", { model: gone[0] }));
    else toast(appT("app.byok.toast_loaded", { count: d.models.length, hidden: hid }));
  } catch (e) {
    if (pair !== modelPair()) return;
    if (el("provider").value === "custom") {
      // Not every OpenAI-compatible server has /models: let the user type the ids instead.
      setModelControl("text");
      renderForgeButton();
      toast(appT("app.byok.toast_typed_fallback", { error: e.message }));
    } else toast(e.message);
  } finally {
    if (MODELS_LOADING_FOR === pair) MODELS_LOADING_FOR = "";
    btn.disabled = false;
    renderLoadModelsBtn();
  }
}
// --- admin: user management ------------------------------------------------------------------------
// Same gate as the stats card (ME.admin from /api/me): adjust a token balance, or grant unlimited hosted
// forging, without a redeploy. Data: /api/admin/users (one row per account) and /api/admin/actions (the
// audit trail). Nothing here can grant admin — that stays in BTSWEB_ADMIN_EMAILS.
let ADMIN_Q_TIMER = null;

async function loadAdminUsers() {
  const card = el("admin-users");
  if (!card) return;
  if (!ME || !ME.admin) { card.classList.add("hidden"); return; }
  card.classList.remove("hidden");
  const q = el("admin-users-q").value.trim();
  try {
    const r = await fetch(`/api/admin/users?q=${encodeURIComponent(q)}`);
    if (!r.ok) throw new Error("HTTP " + r.status);
    renderAdminUsers(await r.json());
  } catch (e) {
    el("admin-users-note").textContent = "Couldn't load users: " + e.message;
  }
  loadAdminActions();
}

function renderAdminUsers(d) {
  const users = d.users || [];
  // Tokens input + Save share one cell and the per-row status note sits UNDER them (a capped-width block),
  // so it can't shunt the columns sideways mid-edit. Seven columns, sized to fit the card without scrolling.
  const head = `<tr><th class="who-cell">Account</th><th>Tokens</th>`
    + `<th title="Unlimited hosted forging">∞</th><th class="num" title="Forges that finished and saved a class. Attempts that died (a bad key, a mistyped model, no credits) are listed separately — hover the count for the latest error">Forges</th><th class="num" title="Classes the game has fetched art for = codes imported into the mod (from the nginx log, refreshed every 15 min)">Imported</th>`
    + `<th class="num">Donated</th><th>Joined</th></tr>`;
  const rows = users.map((u) => {
    // On the env master list ⇒ the toggle can't change anything, so it is checked and disabled with a
    // reason rather than silently ignoring the click.
    const envLocked = !!u.unlimited_env;
    const checked = (u.unlimited || envLocked) ? " checked" : "";
    const joined = u.created_at ? String(u.created_at).slice(0, 10) : "—";
    const who = esc(u.email || "(no email)")
      + (u.admin ? ` <span class="sub">· admin</span>` : "")
      + `<div class="sub">${esc(u.name || "")}${u.name && u.providers.length ? " · " : ""}`
      + `${esc((u.providers || []).join(", "))}</div>`
      // A starting balance from a sign-up event, so tokens with no donation behind them are explainable.
      + (u.promo_label ? `<div class="sub">🎁 ${esc(u.promo_label)} (+${Number(u.promo_tokens || 0)})</div>` : "");
    return `<tr data-uid="${u.id}">`
      + `<td class="who-cell">${who}</td>`
      + `<td class="tok-cell"><input class="in tok" type="number" min="0" max="100000" step="1"`
      + ` value="${Number(u.token_balance || 0)}" data-orig="${Number(u.token_balance || 0)}"`
      + ` aria-label="Token balance for ${esc(u.email || ("user " + u.id))}" />`
      + `<button class="btn tok-save" type="button">Save</button>`
      + `<div class="row-note" role="status"></div></td>`
      + `<td><label class="unl"><input type="checkbox" class="unl-box"${checked}`
      + `${envLocked ? " disabled" : ""} /> ∞</label>`
      + (envLocked ? `<div class="sub">via env list</div>` : "")
      + `</td>`
      + `<td class="num">${forgesCell(u)}</td>`
      + `<td class="num">${importedCell(u, d.imports_known)}</td>`
      + `<td class="num">${u.donated_cents ? fmtMoney(u.donated_cents, "usd") : "—"}</td>`
      + `<td class="joined" title="${esc(String(u.created_at || ""))}">${esc(joined)}</td></tr>`;
  }).join("");
  el("admin-users-table").innerHTML = head
    + (rows || `<tr><td colspan="7" class="muted">No accounts match that search.</td></tr>`);

  el("admin-users-note").textContent = (users.length < (d.total || 0)
    ? `Showing ${users.length} of ${d.total} accounts — narrow the search to see the rest.`
    : `${d.total || 0} account${(d.total || 0) === 1 ? "" : "s"}. Changing a balance takes effect on their next forge.`)
    + (d.imports_known ? " “Imported” = classes the game has fetched art for (hover for which, when); up to 15 min behind."
                       : " “Imported” is unknown until the traffic summary has run.");

  // One delegated listener per render: the rows are innerHTML, so per-row handlers would leak.
  const table = el("admin-users-table");
  table.onclick = (ev) => {
    const btn = ev.target.closest(".tok-save");
    if (btn) saveAdminTokens(btn.closest("tr"));
  };
  table.onchange = (ev) => {
    if (ev.target.classList.contains("unl-box")) saveAdminUnlimited(ev.target.closest("tr"), ev.target);
  };
  // Enter in a token box saves that row, which is how anyone actually uses a table of number inputs.
  table.onkeydown = (ev) => {
    if (ev.key === "Enter" && ev.target.classList.contains("tok")) {
      ev.preventDefault();
      saveAdminTokens(ev.target.closest("tr"));
    }
  };
}

// Finished forges, then the attempts that died as a muted "· N failed" whose hover carries the newest error
// (mode, UTC time, the provider's words). Failed attempts used to be folded into one number, which made an
// account whose every forge died on its own API key read as a prolific forger who never imported.
function forgesCell(u) {
  const done = fmtInt(u.forges);
  const failed = Number(u.forges_failed || 0);
  if (!failed) return done;
  const lf = u.last_failed || {};
  const when = lf.at ? String(lf.at).slice(0, 16).replace("T", " ") + " UTC" : "";
  const tip = `${failed} attempt${failed === 1 ? "" : "s"} failed. Latest`
    + (lf.mode ? ` (${lf.mode}` + (when ? `, ${when}` : "") + `)` : when ? ` (${when})` : "")
    + `: ${lf.error || "no detail recorded"}`;
  return `${done} <span class="sub failed-n" title="${esc(tip)}">· ${failed} failed</span>`;
}

// "2 / 3" classes imported, with a hover listing each imported class, its first/last fetch (UTC) and
// the mod version that fetched it (none shown = a build before the mod sent a user agent).
function importedCell(u, known) {
  if (!known) return `<span class="muted" title="No traffic summary yet">?</span>`;
  const imp = u.imported || [];
  if (!imp.length) return `<span class="muted" title="The game has never fetched art for any of this account's ${fmtInt(u.classes)} classes">0 / ${fmtInt(u.classes)}</span>`;
  const when = (s) => String(s || "").replace("T", " ").replace("Z", "");
  const tip = imp.map((r) => `#${r.class_id} ${r.name || "(unnamed)"}: first ${when(r.first)}`
    + (r.last && r.last !== r.first ? `, last ${when(r.last)}` : "")
    + ` · ${r.imports} import${r.imports === 1 ? "" : "s"}, ${r.fetches} fetches`
    + (r.versions && r.versions.length ? ` · mod ${r.versions.join(", ")}` : "")).join("\n");
  return `<span class="imported" title="${esc(tip)}">${imp.length} / ${fmtInt(u.classes)}</span>`;
}

function adminRowNote(row, msg, cls) {
  const note = row.querySelector(".row-note");
  note.textContent = msg;
  note.className = "row-note" + (cls ? " " + cls : "");
}

async function saveAdminTokens(row) {
  const uid = row.dataset.uid;
  const input = row.querySelector(".tok");
  const btn = row.querySelector(".tok-save");
  const want = Number(input.value);
  if (!Number.isInteger(want) || want < 0 || want > 100000) {
    adminRowNote(row, "0–100000 only", "err");
    return;
  }
  btn.disabled = true;
  adminRowNote(row, "Saving…", "");
  try {
    const r = await fetch(`/api/admin/users/${uid}/tokens`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ balance: want }),
    });
    const data = await r.json();
    if (!r.ok) throw new Error(data.error || "HTTP " + r.status);
    input.value = data.token_balance;
    input.dataset.orig = data.token_balance;
    adminRowNote(row, `Saved (was ${data.previous})`, "ok");
    // Editing your own row must move the header pill too, or it lies until the next reload.
    if (ME && Number(uid) === Number(ME.id)) { ME.token_balance = data.token_balance; renderTokens(); }
    loadAdminActions();
  } catch (e) {
    input.value = input.dataset.orig;
    adminRowNote(row, e.message, "err");
  } finally {
    btn.disabled = false;
  }
}

async function saveAdminUnlimited(row, box) {
  const uid = row.dataset.uid;
  const want = box.checked;
  box.disabled = true;
  adminRowNote(row, "Saving…", "");
  try {
    const r = await fetch(`/api/admin/users/${uid}/unlimited`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ unlimited: want }),
    });
    const data = await r.json();
    if (!r.ok) throw new Error(data.error || "HTTP " + r.status);
    // Turning the flag off on an env-list account leaves them unlimited anyway — say so instead of
    // showing a cleared checkbox that the next reload will re-tick.
    if (!want && data.unlimited_env) {
      box.checked = true;
      adminRowNote(row, "Still unlimited via env list", "");
    } else {
      adminRowNote(row, want ? "Unlimited on" : "Unlimited off", "ok");
    }
    if (ME && Number(uid) === Number(ME.id)) { ME.unlimited = box.checked; renderTokens(); }
    loadAdminActions();
  } catch (e) {
    box.checked = !want;
    adminRowNote(row, e.message, "err");
  } finally {
    box.disabled = false;
  }
}

const ADMIN_ACTION_VERB = { set_tokens: "tokens", set_unlimited: "unlimited" };
// Sign-up event actions have no target account; old/new are the cap before -> after, the event is in a.note.
const PROMO_ACTION_LABEL = { promo_create: "created", promo_edit: "edited", promo_end: "ended" };
// The Archive's actions target the class OWNER; which class (and the word / note) rides in a.note.
const ARCHIVE_ACTION_LABEL = {
  feature_class: "featured", pass_nomination: "passed on", unfeature_class: "unfeatured",
};

async function loadAdminActions() {
  const list = el("admin-actions");
  if (!list) return;
  try {
    const r = await fetch("/api/admin/actions?limit=10");
    if (!r.ok) return;
    const rows = (await r.json()).actions || [];
    list.innerHTML = rows.length
      ? rows.map((a) => {
        const when0 = a.created_at ? new Date(a.created_at + "Z").toLocaleString() : "";
        if (PROMO_ACTION_LABEL[a.action]) {
          const cap = a.action === "promo_create" ? ` · cap ${a.new_value}`
            : a.action === "promo_edit" && a.old_value !== a.new_value ? ` · cap ${a.old_value} → ${a.new_value}` : "";
          return `<li>${esc(a.actor_email || "?")} ${PROMO_ACTION_LABEL[a.action]} sign-up ${esc(a.note || "event")}`
            + `${esc(cap)}<span class="sub"> · ${esc(when0)}</span></li>`;
        }
        if (ARCHIVE_ACTION_LABEL[a.action]) {
          return `<li>${esc(a.actor_email || "?")} ${ARCHIVE_ACTION_LABEL[a.action]} ${esc(a.note || "a class")}`
            + ` (owner ${esc(a.target_email || "?")})<span class="sub"> · ${esc(when0)}</span></li>`;
        }
        const what = ADMIN_ACTION_VERB[a.action] || a.action;
        const from = a.action === "set_unlimited" ? (a.old_value ? "on" : "off") : a.old_value;
        const to = a.action === "set_unlimited" ? (a.new_value ? "on" : "off") : a.new_value;
        const when = a.created_at ? new Date(a.created_at + "Z").toLocaleString() : "";
        return `<li>${esc(a.actor_email || "?")} set ${what} for ${esc(a.target_email || "?")}: `
          + `${esc(String(from))} → ${esc(String(to))}<span class="sub"> · ${esc(when)}</span></li>`;
      }).join("")
      : `<li class="muted">Nothing changed yet.</li>`;
  } catch (_) { /* the audit trail is context, never a blocker */ }
}

// --- admin: The Archive queue ----------------------------------------------------------------------
// Same gate as the Users card. /api/admin/nominations -> two tables: pending nominations (Feature / Pass) and
// what is in The Archive now (Unfeature). Writes answer 403 + reauth when the sign-in is older than 4h; the
// message says so and lands in the card's note, like the Users card's row notes.
async function loadAdminArchive() {
  const card = el("admin-archive");
  if (!card) return;
  if (!ME || !ME.admin) { card.classList.add("hidden"); return; }
  card.classList.remove("hidden");
  try {
    const r = await fetch("/api/admin/nominations");
    if (!r.ok) throw new Error("HTTP " + r.status);
    renderAdminArchive(await r.json());
  } catch (e) {
    el("admin-archive-note").textContent = "Couldn't load nominations: " + e.message;
  }
}

function archiveWhen(iso) { return iso ? String(iso).slice(0, 16).replace("T", " ") + " UTC" : "—"; }
// Name (linking to its /deck page in a new tab), then the owner and the one-line description underneath, so
// the pending table fits the 760px card without scrolling the Feature / Pass buttons out of sight.
function archiveClassCell(c, withOwner) {
  const name = esc(c.name || "(unnamed)");
  const link = c.share_url ? `<a href="${esc(c.share_url)}" target="_blank" rel="noopener">${name}</a>` : name;
  return link + (withOwner ? `<div class="sub">${esc(c.owner_email)}</div>` : "")
    + (c.description ? `<div class="sub">${esc(c.description)}</div>` : "");
}

function renderAdminArchive(d) {
  const pending = d.pending || [], featured = d.featured || [];
  const flag = (on) => (on ? "✓" : "–");
  el("admin-nominations").innerHTML = `<tr><th class="wrap-cell">Class · owner</th><th class="wrap-cell">Concept</th>`
    + `<th class="num">Cards</th><th title="splash · sprite · card art">Art S·P·C</th><th class="wrap-cell">Note</th>`
    + `<th>Nominated</th><th></th></tr>`
    + (pending.map((c) => `<tr data-cid="${c.id}" data-name="${esc(c.name || "")}">`
      + `<td class="wrap-cell">${archiveClassCell(c, true)}</td>`
      + `<td class="wrap-cell">${esc(c.concept)}</td><td class="num">${fmtInt(c.card_count)}</td>`
      + `<td class="flags" title="splash ${c.has_splash ? "yes" : "no"} · sprite ${c.has_sprite ? "yes" : "no"} · card art ${c.has_card_art ? "yes" : "no"}">`
      + `${flag(c.has_splash)} ${flag(c.has_sprite)} ${flag(c.has_card_art)}</td>`
      + `<td class="wrap-cell">${c.nomination_note ? esc(c.nomination_note) : `<span class="muted">—</span>`}</td>`
      + `<td title="${esc(archiveWhen(c.nominated_at))}">${esc(String(c.nominated_at || "—").slice(0, 10))}</td>`
      + `<td><div class="row-actions"><button class="btn" type="button" data-act="feature">Feature</button>`
      + `<button class="btn ghost" type="button" data-act="pass">Pass</button></div></td></tr>`).join("")
      || `<tr><td colspan="7" class="muted">No nominations waiting.</td></tr>`);
  el("admin-featured").innerHTML = `<tr><th>Word</th><th class="wrap-cell">Class</th><th>Owner</th><th>Featured</th><th></th></tr>`
    + (featured.map((c) => `<tr data-cid="${c.id}" data-name="${esc(c.name || "")}">`
      + `<td><span class="featured-word">${esc(c.featured_word || "?")}</span></td>`
      + `<td class="wrap-cell">${archiveClassCell(c)}</td><td>${esc(c.owner_email)}</td>`
      + `<td>${esc(archiveWhen(c.featured_at))}</td>`
      + `<td><button class="btn ghost" type="button" data-act="unfeature">Unfeature</button></td></tr>`).join("")
      || `<tr><td colspan="5" class="muted">Nothing in The Archive yet.</td></tr>`);
  const card = el("admin-archive");
  card.onclick = (ev) => {
    const btn = ev.target.closest("button[data-act]");
    const row = btn && btn.closest("tr[data-cid]");
    if (row) adminArchiveAct(btn, row.dataset.cid, btn.dataset.act, row.dataset.name);
  };
}

async function adminArchiveAct(btn, id, act, name) {
  let body;
  if (act === "feature") {
    const first = String(name || "").trim().split(/\s+/)[0].toUpperCase();
    const word = prompt(`The five-letter board word for "${name}" (A–Z), shown as "<WORD> the spire":`,
      /^[A-Z]{5}$/.test(first) ? first : "");
    if (word === null) return;
    const w = String(word).trim().toUpperCase();
    if (!/^[A-Z]{5}$/.test(w)) { el("admin-archive-note").textContent = "The word must be exactly five letters A–Z."; return; }
    body = JSON.stringify({ word: w });
  } else if (act === "unfeature" && !confirm(`Take "${name}" out of The Archive?`)) {
    return;
  }
  btn.disabled = true;
  const note = el("admin-archive-note");
  try {
    const r = await fetch(`/api/admin/classes/${id}/${act}`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: body || "{}",
    });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.error || ("HTTP " + r.status));
    note.textContent = act === "feature" ? `“${name}” is in The Archive as ${d.featured_word}.`
      : act === "pass" ? `Passed on “${name}”.` : `“${name}” is out of The Archive.`;
    await loadAdminArchive();
    loadAdminActions();
  } catch (e) {
    note.textContent = e.message;
    btn.disabled = false;
  }
}

// --- admin: sign-up events ----------------------------------------------------------------------------
// Same gate as the Users card. /api/admin/promos -> one row per event (newest first) with its status
// (scheduled | live | capped | ended) and what its accounts did after the grant. The form creates or edits
// (same full body either way; an ended event is history and offers neither Edit nor End now). Times are typed
// and shown in the browser's zone and sent as ISO with that zone's offset, which the server requires. Writes
// answer 403 + reauth when the sign-in is older than 4h, 400 on bad input and 409 on an overlapping window;
// each message lands in the form's note (or the card's note for End now), like the Archive card.
let ADMIN_EVENTS = [];
let EDITING_EVENT = null;  // the id the form is editing, or null for a new event

const pad2 = (n) => String(n).padStart(2, "0");
function localTzName() {
  try {
    const part = new Intl.DateTimeFormat(undefined, { timeZoneName: "short" }).formatToParts(new Date())
      .find((p) => p.type === "timeZoneName");
    return part ? part.value : "";
  } catch (_) { return ""; }
}
function evWhen(iso) {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleString(undefined, {
    weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}
// "2026-10-30T18:00" (a datetime-local value, the viewer's wall clock) -> "2026-10-30T18:00:00-04:00", the
// offset taken for THAT date so a window across a DST change keeps the hour that was typed.
function localInputToIso(v) {
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(v || "");
  if (!m) return null;
  const off = -new Date(+m[1], +m[2] - 1, +m[3], +m[4], +m[5]).getTimezoneOffset();
  const a = Math.abs(off);
  return `${m[1]}-${m[2]}-${m[3]}T${m[4]}:${m[5]}:00${off >= 0 ? "+" : "-"}${pad2(Math.floor(a / 60))}:${pad2(a % 60)}`;
}
function isoToLocalInput(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}T${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
}
function noteEl(id, msg, cls) {
  const n = el(id);
  n.textContent = msg;
  n.className = "hint" + (cls ? " " + cls : "");
}

async function loadAdminEvents() {
  const card = el("admin-events");
  if (!card) return;
  if (!ME || !ME.admin) { card.classList.add("hidden"); return; }
  card.classList.remove("hidden");
  const tz = localTzName();
  el("admin-events-tz").textContent = "Every account created inside an event's window starts with its free tokens, "
    + "until the cap of accounts is reached. One event at a time. Times are in your time zone"
    + (tz ? ` (${tz})` : "") + ".";
  try {
    const r = await fetch("/api/admin/promos");
    if (!r.ok) throw new Error("HTTP " + r.status);
    renderAdminEvents(await r.json());
  } catch (e) {
    noteEl("admin-events-note", "Couldn't load sign-up events: " + e.message, "err");
  }
}

function renderAdminEvents(d) {
  ADMIN_EVENTS = d.promos || [];
  const head = `<tr><th class="wrap-cell">Event</th><th>Status</th><th class="wrap-cell">Window</th>`
    + `<th class="num" title="Accounts granted / the cap">Granted</th>`
    + `<th class="num" title="Granted accounts with at least one finished forge after the grant">Forged</th>`
    + `<th class="num" title="What their hosted (token) forges cost us after the grant, metered where known">Our cost</th>`
    + `<th class="num" title="Granted accounts that donated after the grant, and how much">Donated</th><th></th></tr>`;
  const rows = ADMIN_EVENTS.map((p) => {
    const st = p.stats || {};
    const n = Number(p.tokens_per_signup || 0);
    const ended = p.status === "ended";
    const early = p.ended_at ? `<div class="sub">ended early ${esc(evWhen(p.ended_at))}</div>` : "";
    return `<tr data-id="${p.id}">`
      + `<td class="wrap-cell">${esc(p.label)}<div class="sub">#${p.id} · ${n} token${n === 1 ? "" : "s"} per signup`
      + `${p.created_by_email ? " · " + esc(p.created_by_email) : ""}</div></td>`
      + `<td><span class="ev-pill ${esc(p.status)}">${esc(p.status)}</span></td>`
      + `<td class="wrap-cell">${esc(evWhen(p.starts_at))} →<div>${esc(evWhen(p.ends_at))}</div>${early}</td>`
      + `<td class="num">${fmtInt(st.granted)} / ${fmtInt(p.max_grants)}</td>`
      + `<td class="num">${fmtInt(st.forged_after)}</td>`
      + `<td class="num">${fmtUsd(st.hosted_cost_usd)}</td>`
      + `<td class="num">${fmtInt(st.donated_after)}`
      + (st.donated_cents_after ? `<div class="sub">${fmtMoney(st.donated_cents_after, "usd")}</div>` : "") + `</td>`
      + `<td>${ended ? "" : `<div class="row-actions"><button class="btn" type="button" data-act="edit">Edit</button>`
        + `<button class="btn ghost" type="button" data-act="end">End now</button></div>`}</td></tr>`;
  }).join("");
  el("admin-events-table").innerHTML = head
    + (rows || `<tr><td colspan="8" class="muted">No sign-up events yet.</td></tr>`);
  el("admin-events-table").onclick = (ev) => {
    const btn = ev.target.closest("button[data-act]");
    const row = btn && btn.closest("tr[data-id]");
    const p = row && ADMIN_EVENTS.find((x) => String(x.id) === row.dataset.id);
    if (!p) return;
    if (btn.dataset.act === "edit") openEventForm(p);
    else endAdminEvent(btn, p);
  };
}

function openEventForm(p) {
  EDITING_EVENT = p ? p.id : null;
  el("admin-event-form-title").textContent = p ? `Edit event #${p.id}` : "New event";
  el("admin-event-save").textContent = p ? "Save changes" : "Create event";
  el("ev-label").value = p ? p.label : "";
  el("ev-tokens").value = p ? p.tokens_per_signup : 1;
  el("ev-cap").value = p ? p.max_grants : "";
  if (p) {
    el("ev-start").value = isoToLocalInput(p.starts_at);
    el("ev-end").value = isoToLocalInput(p.ends_at);
  } else {
    // A starting point to adjust: the next whole hour, for two days.
    const start = new Date();
    start.setMinutes(0, 0, 0);
    start.setHours(start.getHours() + 1);
    el("ev-start").value = isoToLocalInput(start.toISOString());
    el("ev-end").value = isoToLocalInput(new Date(start.getTime() + 48 * 3600 * 1000).toISOString());
  }
  noteEl("admin-event-note", "", "");
  el("admin-event-form").classList.remove("hidden");
  el("ev-label").focus();
}

function closeEventForm() {
  EDITING_EVENT = null;
  el("admin-event-form").classList.add("hidden");
}

async function saveAdminEvent(ev) {
  ev.preventDefault();
  const starts = localInputToIso(el("ev-start").value), ends = localInputToIso(el("ev-end").value);
  if (!starts || !ends) { noteEl("admin-event-note", "Pick a start and an end.", "err"); return; }
  const cap = el("ev-cap").value.trim();
  const body = {
    label: el("ev-label").value.trim(),
    tokens_per_signup: el("ev-tokens").value.trim() || 1,
    max_grants: cap === "" ? null : cap,
    starts_at: starts, ends_at: ends,
  };
  const editing = EDITING_EVENT;
  const btn = el("admin-event-save");
  btn.disabled = true;
  noteEl("admin-event-note", "Saving…", "");
  try {
    const r = await fetch(editing ? `/api/admin/promos/${editing}` : "/api/admin/promos", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.error || ("HTTP " + r.status));
    closeEventForm();
    noteEl("admin-events-note", `${editing ? "Saved" : "Created"} event #${d.id} “${d.label}” (${d.status}).`, "ok");
    await loadAdminEvents();
    loadAdminActions();
  } catch (e) {
    // A 409 names the clashing window in UTC ISO; say it in the same local time as the table.
    noteEl("admin-event-note", e.message.replace(/\d{4}-\d{2}-\d{2}T[\d:.]+(?:Z|[+-]\d{2}:\d{2})/g, evWhen), "err");
  } finally {
    btn.disabled = false;
  }
}

async function endAdminEvent(btn, p) {
  if (!confirm(`End “${p.label}” now? Accounts created after this get no free tokens, and an ended event `
    + "can't be edited or restarted.")) return;
  btn.disabled = true;
  try {
    const r = await fetch(`/api/admin/promos/${p.id}/end`, { method: "POST" });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.error || ("HTTP " + r.status));
    if (EDITING_EVENT === p.id) closeEventForm();
    noteEl("admin-events-note", `Ended “${p.label}”. The public ribbon can take up to a minute to disappear.`, "ok");
    await loadAdminEvents();
    loadAdminActions();
  } catch (e) {
    noteEl("admin-events-note", e.message, "err");
    btn.disabled = false;
  }
}

// Which box is open IS the choice: opening one closes the other and is remembered for next visit.
el("forge-byok").addEventListener("toggle", () => onPayBoxToggle("forge-byok", "forge-token", "byok"));
el("forge-token").addEventListener("toggle", () => onPayBoxToggle("forge-token", "forge-byok", "token"));
el("mode-fake").onchange = () => renderForgeButton();
for (const id of ["forge-byok", "forge-token"]) el(id).querySelector("summary").addEventListener("click", onPaySummaryClick);
el("forge-get-tokens").onclick = () => {
  GET_TOKENS_OPEN = el("forge-donate-wrap").classList.contains("hidden");
  renderGetTokens();
};

// A provider the USER picks starts its pickers fresh (no "saved model isn't offered" for another vendor's id).
el("provider").onchange = () => {
  SAVED_MODELS = { model: "", card_model: "" };
  applyProvider(); saveByok(); showEstimate(false); renderForgeButton();
};
wireModelFields();
el("base_url").oninput = renderLoadModelsBtn;
el("base_url").onchange = () => { saveByok(); scheduleModelLoad(); };
el("forge-byok").addEventListener("toggle", scheduleModelLoad);
el("estimate-btn").onclick = () => showEstimate(true);
el("key-safety-btn").onclick = () => el("key-safety").classList.toggle("hidden");
el("stats-days").onchange = loadStats;
el("welcome-x").onclick = () => el("welcome-banner").classList.add("hidden");
el("admin-events-new").onclick = () => openEventForm(null);
el("admin-event-cancel").onclick = closeEventForm;
el("admin-event-form").onsubmit = saveAdminEvent;
el("traffic-days").onchange = loadTraffic;
// Debounced so typing an address doesn't fire a query per keystroke.
el("admin-users-q").oninput = () => {
  clearTimeout(ADMIN_Q_TIMER);
  ADMIN_Q_TIMER = setTimeout(loadAdminUsers, 250);
};

// Sniff an unambiguous key prefix and jump the dropdown to the matching provider.
el("api_key").oninput = () => {
  const guess = providerFromKey(el("api_key").value.trim());
  if (guess && guess !== el("provider").value) {
    el("provider").value = guess;
    SAVED_MODELS = { model: "", card_model: "" };
    applyProvider();
  }
  renderForgeButton();
};
// A finished key (blur after typing, or a paste) loads that provider's model list.
el("api_key").onchange = scheduleModelLoad;
el("api_key").addEventListener("paste", () => setTimeout(scheduleModelLoad, 0));

// Every string comes from the i18n json, so nothing renders before it has loaded (English included).
BTS_I18N.ready.then(() => {
  applyProvider();
  boot();
});

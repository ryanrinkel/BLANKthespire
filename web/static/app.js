"use strict";


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
  renderBanner();
  loadEstimate();
  loadDonation();  // the forge tab's inline tier buttons need /api/billing before the Account tab is opened
  // #account is where a finished "link another sign-in" comes back to (auth._landing), so honour the hash.
  selectTab(location.hash === "#account" ? "account" : "forge");
  handlePurchaseReturn();
}

// Reflect the user's token state in the header chip, the "Use a token" balance line and the Account
// balance. Steering the default path moved into the chooser block below (restoreForgePref).
function renderTokens() {
  if (!ME) return;
  const unlimited = !!ME.unlimited;
  const paid = Number(ME.token_balance || 0);
  const chip = el("tokens");
  chip.textContent = unlimited ? "∞ tokens" : `${paid} token${paid === 1 ? "" : "s"}`;
  chip.classList.remove("hidden");
  chip.classList.toggle("empty", !unlimited && paid <= 0);

  const line = el("token-balance-line");
  if (line) {
    if (unlimited) line.textContent = "\u221E tokens \u2014 your account forges free.";
    else if (paid > 0) line.textContent = `You have ${paid} token${paid === 1 ? "" : "s"}.`;
    else line.textContent = "You have no tokens \u2014 get some below.";
  }

  // Keep the Account view's balance in lockstep wherever the numbers change (forge spend, donation).
  const acct = el("acct-balance");
  if (acct) acct.textContent = unlimited ? "∞" : String(paid);

  renderForgeButton();
  renderChooser();
  renderBanner();  // its wording depends on the balance
}

// Opening one of the two payment boxes closes the other, remembers the choice, and re-renders everything
// that depends on it. Fired from the <details> "toggle" event, so a plain click on the summary counts.
function onPayBoxToggle(openedId, otherId, mode) {
  const box = el(openedId);
  if (box && box.open) {
    const other = el(otherId);
    if (other && other.open) other.open = false;   // fires the other box's toggle, which just re-renders
    setForgePref(mode);
    CHOOSER_FORCED = false;
  }
  renderForgeButton();
  renderChooser();
  renderBanner();
  renderEstimate();
}

// True while a forge is in flight: the button stays disabled no matter what re-renders underneath it
// (token events arrive mid-forge and call renderTokens -> renderForgeButton).
let FORGING = false;

// The forge button is the gate: it only enables once the open box can actually pay for a forge, and it
// says what the click will cost. Disabled, it carries a title saying what is missing.
function renderForgeButton() {
  const btn = el("forge-btn");
  if (!btn) return;
  const m = currentMode();
  let ok = false, label = "Forge the class", why = "";
  if (m === "fake") {
    ok = true;
    label = "Forge the class (offline demo)";
  } else if (m === "byok") {
    if (el("api_key").value.trim() && el("model").value.trim()) {
      ok = true;
      label = "Forge the class (uses your API key)";
    } else why = "Enter your API key and a model.";
  } else if (m === "token") {
    if (!ME || ME.unlimited) {
      ok = true;
      label = "Forge the class (free \u2014 unlimited account)";
    } else {
      const paid = Number(ME.token_balance || 0);
      if (paid > 0) {
        ok = true;
        label = `Forge the class (uses 1 of your ${paid} token${paid === 1 ? "" : "s"})`;
      } else why = "You have no tokens \u2014 get some below or bring a key.";
    }
  } else {
    why = "Open 'Bring your own key' and enter a key, or 'Use a token'.";
  }
  btn.textContent = label;
  btn.disabled = FORGING || !ok;
  if (why) btn.title = why; else btn.removeAttribute("title");
}

// --- onboarding chooser (forge tab) ---------------------------------------------------------------
// First visit with nothing to spend and no key on file: two cards, "use my key" vs "support the forge".
// Once a path is picked it collapses to a one-line strip. The open <details> box stays the source of
// truth — this only opens one of them and remembers the pick in localStorage.bts_forge_pref.

let CHOOSER_FORCED = false;  // "change" reopens the cards even for an account that now has tokens

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
// every visit. With nothing remembered both boxes stay shut and the button stays disabled until one is
// opened (the chooser cards above are what points at them).
function restoreForgePref() {
  const pref = forgePref();
  if (pref) setMode(pref);
  renderForgeButton();
  renderChooser();
}

function renderChooser() {
  const box = el("chooser");
  if (!box) return;
  const paid = Number((ME && ME.token_balance) || 0);
  const pref = forgePref();
  // Undecided: nothing to spend, no key on file, nothing remembered.
  const undecided = CHOOSER_FORCED
    || (!!ME && !ME.unlimited && paid <= 0 && !hasSavedKey() && !pref);
  const mode = pref || currentMode();
  // Nothing decided and nothing to decide about (unlimited, offline demo, or simply no box open yet on an
  // account that isn't stuck): no strip to draw.
  if (!ME || (!undecided && (!mode || ME.unlimited || mode === "fake"))) {
    box.classList.add("hidden");
    return;
  }
  box.classList.remove("hidden");
  el("chooser-head").classList.toggle("hidden", !undecided);
  el("chooser-cards").classList.toggle("hidden", !undecided);
  const strip = el("chooser-strip");
  strip.classList.toggle("hidden", undecided);
  if (undecided) return;
  strip.innerHTML = (mode === "byok" ? "Forging with your key" : "Forging with tokens")
    + ' · <button id="chooser-change" class="linkish" type="button">change</button>';
  // innerHTML replaced the node — re-wire on every render.
  el("chooser-change").onclick = () => { lsDel("bts_forge_pref"); CHOOSER_FORCED = true; renderChooser(); };
}

function chooseByok() {
  setForgePref("byok");
  CHOOSER_FORCED = false;
  setMode("byok");          // opens #forge-byok, where the key fields live
  el("provider").focus();
  renderChooser();
}

function chooseToken() {
  setForgePref("token");
  CHOOSER_FORCED = false;
  setMode("token");         // tiers inline on the forge tab, not a trip to the Account tab
  el("forge-token").scrollIntoView({ behavior: "smooth", block: "nearest" });
  renderChooser();
}

// --- "you need a key or a token" warning ----------------------------------------------------------
// Since v3 (2026-09-18) nothing forges for free on our models, so the forge tab carries a dismissible
// warning until the account has done one of the two things it asks for: saved an API key, or (for the
// wording) holds tokens. Unlimited accounts never see it. Re-rendered whenever the token state changes.
function renderBanner() {
  const bar = el("v3-banner");
  if (!bar) return;
  const show = !!ME && !ME.unlimited && !hasSavedKey() && !lsGet("bts_v3_banner_dismissed");
  bar.classList.toggle("hidden", !show);
  if (!show) return;
  el("v3-banner-text").textContent = Number(ME.token_balance || 0) > 0
    ? "Enter an API key or use a token to forge!"
    : "Enter an API key or get tokens to forge.";
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

// The whole quote as data: a header, aligned [label, what, cost] rows, and free-text notes. Both the HTML
// panel and the plain-text confirm dialog render this, so they can never disagree.
function estimateRows(model) {
  const e = ESTIMATE, p = currentProvider();
  if (!e) {
    return { head: "", rows: [],
             notes: ["A forge makes roughly 50 model calls and around 1.4M input tokens — check your "
                     + "provider's pricing."] };
  }
  const inp = e.input_tokens, cached = e.cached_tokens, out = e.output_tokens;
  const rows = [], notes = [];
  const head = `Estimated cost per forge on your ${p.label} key`;

  const price = modelPrice(model);
  const tokens = `~${e.calls} calls · ~${fmtTokens(inp)} in (~${fmtTokens(cached)} cached) · `
    + `~${fmtTokens(out)} out`;
  let textUsd = null;
  if (price) {
    textUsd = (Math.max(0, inp - cached) * price.inp + cached * price.cached + out * price.out) / 1_000_000;
    const noCache = (inp * price.inp + out * price.out) / 1_000_000;
    notes.push(`Text assumes prompt caching works on your key — up to ${usd(noCache)} without it.`);
  } else {
    notes.push("We have no price for that model — multiply the token counts by your provider's price sheet."
      + " On frontier models a forge can be a few dollars.");
  }
  rows.push(["Text", `${model || "(pick a model)"}  ${tokens}`, textUsd == null ? "?" : "≈ " + usd(textUsd)]);

  const art = artFor(p);
  let artUsd = null;
  if (art) {
    const n = Number(e.images_per_forge || 36);
    artUsd = art.pack_usd != null ? Number(art.pack_usd)
           : (art.per_image_usd != null ? Number(art.per_image_usd) * n : null);
    const per = art.per_image_usd != null ? ` × $${Number(art.per_image_usd).toFixed(3)}` : "";
    rows.push(["Art", `${art.model || p.label + " image API"}  ${n} images (splash, sprite, ${n - 2} card `
      + `portraits)${per}`, artUsd == null ? "?" : "≈ " + usd(artUsd)]);
  } else if (p.mode) {
    notes.push(`No generated art on this key — ${p.label} has no image API we can drive, so classes forged `
      + "here ship with the game's built-in card doodles.");
  }
  if (textUsd != null && artUsd != null) rows.push(["Total", "", "≈ " + usd(textUsd + artUsd)]);

  // Gemini and xAI bill a flat per-image list price with no cheaper model on the same API, so say what the
  // alternative key would cost for the SAME pack — the OpenRouter number is measured from our own ledger.
  const or = ESTIMATE.art?.openrouter;
  if (art && (p.artKey === "gemini" || p.artKey === "xai") && or?.pack_usd != null) {
    notes.push(`Art is generated on your key; there's no cheaper ${p.label} image model on this API. `
      + `An OpenRouter key makes the same pack for about ${usd(or.pack_usd)}.`);
  }
  return { head, rows, notes };
}

// Plain text (the confirm dialog). Same numbers as the panel.
function estimateText(model) {
  const { head, rows, notes } = estimateRows(model);
  const lines = [];
  if (head) lines.push(head);
  for (const [label, what, cost] of rows) lines.push(`  ${label.padEnd(7)}${what}${what ? "   " : ""}${cost}`);
  return lines.concat(notes).join("\n");
}

function renderEstimate() {
  const box = el("byok-estimate");
  if (!box) return;
  const { head, rows, notes } = estimateRows(el("model").value.trim());
  // Column widths from the content, so Text / Art / Total line up without a real table.
  const w1 = Math.max(0, ...rows.map(r => r[1].length));
  const table = rows.map(([label, what, cost]) =>
    esc(`  ${label.padEnd(7)}${what.padEnd(w1)}   ${cost}`)).join("\n");
  box.innerHTML = (head ? `⚠ ${esc(head)}` : "⚠")
    + (table ? `<pre>${table}</pre>` : "")
    + notes.map(n => `<p class="est-note">${esc(n)}</p>`).join("");
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
    renderChooser();
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
// `models` is the suggestion list, CHEAPEST FIRST (the first entry is also the placeholder): the estimate
// under the fields prices whichever one is typed, from /api/forge-estimate's `text_prices`. Every id here
// MUST have a price in that table — web/tests/test_forge_estimate.py parses this block and fails if one
// doesn't, so the quote can never quietly go blank on a suggestion we ship.
const PROVIDERS = {
  anthropic:  { label: "Anthropic", mode: "anthropic", base_url: "",
                prefix: "sk-ant-", keyFrom: "console.anthropic.com",
                models: ["claude-sonnet-4-6", "claude-haiku-4-5", "claude-opus-4-8"] },
  openai:     { label: "OpenAI", mode: "byok", base_url: "https://api.openai.com/v1", art: true, artKey: "openai",
                prefix: "sk-", keyFrom: "platform.openai.com (an API key, not a ChatGPT login)",
                models: ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "o4-mini"] },
  ollama:     { label: "Ollama Cloud", mode: "byok", base_url: "https://ollama.com/v1",
                prefix: "", keyFrom: "ollama.com/settings/keys",
                models: ["glm-5.2", "gemma4:31b", "gpt-oss:120b", "qwen3.5:397b", "deepseek-v4-pro"] },
  openrouter: { label: "OpenRouter", mode: "byok", base_url: "https://openrouter.ai/api/v1", art: true,
                artKey: "openrouter",
                prefix: "sk-or-", keyFrom: "openrouter.ai/keys",
                models: ["anthropic/claude-sonnet-4.6", "openai/gpt-4o", "google/gemini-2.5-pro"] },
  groq:       { label: "Groq", mode: "byok", base_url: "https://api.groq.com/openai/v1",
                prefix: "gsk_", keyFrom: "console.groq.com/keys",
                models: ["llama-3.3-70b-versatile", "moonshotai/kimi-k2-instruct"] },
  google:     { label: "Google Gemini", mode: "byok", art: true, artKey: "gemini",
                base_url: "https://generativelanguage.googleapis.com/v1beta/openai",
                prefix: "AIza", keyFrom: "aistudio.google.com/apikey",
                models: ["gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-3-flash-preview",
                         "gemini-2.5-pro"] },
  // grok-4.x cannot turn reasoning off (hidden thinking is billed and eats max_tokens), so the
  // explicitly non-reasoning model is suggested first — see forge.py BYOK_HOST_PROFILES.
  xai:        { label: "xAI (Grok)", mode: "byok", base_url: "https://api.x.ai/v1", art: true, artKey: "xai",
                prefix: "xai-", keyFrom: "console.x.ai",
                models: ["grok-4.20-0309-non-reasoning", "grok-4.3", "grok-4.6"] },
  deepseek:   { label: "DeepSeek", mode: "byok", base_url: "https://api.deepseek.com/v1",
                prefix: "", keyFrom: "platform.deepseek.com",
                models: ["deepseek-chat", "deepseek-reasoner"] },
  together:   { label: "Together", mode: "byok", base_url: "https://api.together.xyz/v1",
                prefix: "", keyFrom: "api.together.xyz/settings/api-keys",
                models: ["deepseek-ai/DeepSeek-V3", "meta-llama/Llama-3.3-70B-Instruct-Turbo"] },
  custom:     { label: "Other", mode: "byok", base_url: "", prefix: "", keyFrom: "your provider",
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

// Apply the selected provider to the form: show the URL field only for "custom", fill the model
// suggestions, refresh the hint, and hide "Load models" where it can't work (Anthropic / no URL yet).
function applyProvider() {
  const id = el("provider").value;
  const p = currentProvider();
  el("base_url").style.display = id === "custom" ? "" : "none";

  const dl = el("model-list");
  dl.innerHTML = "";
  for (const m of p.models) { const o = document.createElement("option"); o.value = m; dl.appendChild(o); }
  el("model").placeholder = p.models[0] ? `Model — e.g. ${p.models[0]}` : "Model";

  // Load-models hits {base_url}/models with a Bearer token — works for OpenAI-compatible providers, not
  // Anthropic's native API. Hide it when there's no usable URL.
  el("load-models").style.display = (p.mode === "byok" && (id !== "custom" || resolvedBaseUrl())) ? "" : "none";

  el("byok-hint").innerHTML =
    `Get an <b>API key</b> from ${esc(p.keyFrom)}. Your key is sent with this one request and kept only `
    + `in your browser — never saved on our server. `
    + (p.art
        ? `<b>Art included:</b> the splash, sprite and card portraits are generated on this key too `
          + `— the estimate below is the real per-image price for this provider.`
        : `<b>No generated art:</b> ${esc(p.label)} can't make images, so classes forged on this key `
          + `ship without splash, sprite or card portraits (the game uses its built-in card doodles).`);
  renderEstimate();
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
    applyProvider();
    if (saved.base_url) el("base_url").value = saved.base_url;
    if (saved.model) el("model").value = saved.model;
    if (saved.api_key) el("api_key").value = saved.api_key;
  } catch (_) { applyProvider(); }
}
function saveByok() {
  lsSet("bts_byok", JSON.stringify({
    provider: el("provider").value,
    base_url: el("base_url").value.trim(),
    model: el("model").value.trim(),
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
  if (!concept) { toast("Describe a class first."); return; }
  const choice = currentMode();  // "token" | "byok" | "fake" | null
  if (!choice) {
    toast("Open 'Bring your own key' and enter a key, or 'Use a token'.");
    return;
  }

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
        toast("No tokens to spend — get some, or bring your own key.");
        return;
      }
      const paid = Number(ME.token_balance || 0);
      if (!confirm(`This will use 1 token. You have ${paid}. Forge this class?`)) return;
    }
  } else if (choice === "byok") {
    const p = currentProvider();
    const api_key = el("api_key").value.trim();
    const model = el("model").value.trim();
    if (!api_key || !model) { toast("Enter your API key and a model — or switch to 'Use a token'."); return; }
    if (!confirm(`This forge bills YOUR API key (${model}).\n\n${estimateText(model)}\n\nForge this class?`)) return;
    if (p.mode === "anthropic") {
      body.mode = "anthropic";
      body.key = { api_key, model };
    } else {
      const base_url = resolvedBaseUrl();
      if (!base_url) { toast("Enter the base URL for your provider."); return; }
      body.mode = "byok";
      body.key = { base_url, api_key, model };
    }
    saveByok();
  }

  FORGING = true;
  renderForgeButton();
  el("result").classList.add("hidden");
  el("progress").classList.remove("hidden");
  el("log").textContent = "";
  resetChoice();  // clear any choice panel left over from a previous forge
  // Echo what we asked for, so a mode mishap (e.g. a stale page) is visible in the log immediately.
  appendLog(`• requested: ${body.mode}` + (body.interactive ? " · interactive" : ""));

  try {
    const resp = await fetch("/api/forge-class", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!resp.ok && resp.headers.get("content-type")?.includes("application/json")) {
      const e = await resp.json();
      // Server says out of tokens (a stale balance slipped past the pre-check) — route to the donate flow.
      if (resp.status === 402) {
        if (applyTokenState(e)) renderTokens();
        selectTab("account");
      }
      throw new Error(e.error || ("HTTP " + resp.status));
    }
    await consumeSSE(resp, onForgeEvent);
  } catch (e) {
    appendLog("✗ " + e.message);
    toast(e.message);
  } finally {
    FORGING = false;
    renderForgeButton();
    el("spinner").classList.add("hidden");
    resetChoice();
  }
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
  if (event === "progress") appendLog("• " + data.message);
  else if (event === "choice") renderChoice(data);
  else if (event === "error") { appendLog("✗ " + data.error); toast(data.error); }
  else if (event === "result") { appendLog("✓ done"); renderResult(data); }
}

// A freshly forged class: spinner off, then the shared renderer + the share bar + what it consumed.
function renderResult(cls) {
  el("spinner").classList.add("hidden");
  renderClassView(cls);
  renderShareBar(cls, false);
  renderUsage(cls);
}

// The bar above a rendered class: a share link (the public /deck/<slug> page) and, when the class was opened
// from the library, a way back to the forge. Classes without a slug simply get no share button.
function renderShareBar(cls, viewing) {
  const share = el("share-link");
  const url = cls.share_url || (cls.slug ? `${location.origin}/deck/${cls.slug}` : "");
  share.dataset.url = url;
  share.classList.toggle("hidden", !url);
  el("view-back").classList.toggle("hidden", !viewing);
  el("view-title").textContent = viewing ? "Viewing a saved class" : "Your new class";
  el("view-bar").classList.remove("hidden");
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
    ? ` · ${u.images} image${u.images === 1 ? "" : "s"}`
      + (u.art_cost_usd != null
          ? ` ($${Number(u.art_cost_usd).toFixed(2)} ${u.art_cost_metered ? "metered" : "est."})` : "")
    : "";
  line.textContent = `This forge used ${u.calls} calls · ${fmtTokens(u.input_tokens)} input tokens`
    + (u.cached_tokens ? ` (${fmtTokens(u.cached_tokens)} from cache)` : "")
    + ` · ${fmtTokens(u.output_tokens)} output tokens${art} on your key.`;
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
    b.innerHTML = `<strong>${esc(title)}</strong>`
      + (o.buildable ? "" : `<span class="co-warn">needs new vocab — some cards may substitute</span>`)
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
    if (choiceState.picked.size >= 2) { toast("Pick at most 2 — deselect one first."); return; }
    choiceState.picked.add(id);
    btn.classList.add("sel");
  }
  el("choice-go").disabled = choiceState.picked.size === 0;
}

function tickChoice() {
  if (!choiceState) return;
  const left = Math.max(0, Math.round((choiceState.deadline - Date.now()) / 1000));
  el("choice-timer").textContent = `(${left}s — then the forge decides)`;
  if (left <= 0) {
    appendLog("• choice timed out — the forge decides");
    resetChoice();
  }
}

async function sendChoice(picks) {
  if (!choiceState || choiceState.sent) return;
  choiceState.sent = true;
  const forgeId = choiceState.forgeId;
  resetChoice();
  appendLog(picks.length ? "• you picked: " + picks.join(", ") : "• skipped — the forge decides");
  try {
    const r = await fetch("/api/forge/answer", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ forge_id: forgeId, archetypes: picks }),
    });
    if (!r.ok) {
      const e = await r.json().catch(() => ({}));
      appendLog("• " + (e.error || "the pick didn't land — the forge decides"));
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

async function loadLibrary() {
  let classes;
  try {
    const r = await fetch("/api/classes");
    ({ classes } = await r.json());
  } catch (_) {
    toast("Couldn't load your classes — check your connection.");
    return;
  }
  const list = el("lib-list");
  list.innerHTML = "";
  el("lib-empty").classList.toggle("hidden", classes.length > 0);
  for (const c of classes) list.appendChild(libRow(c));
}

function libRow(c) {
  const li = document.createElement("li");
  li.className = "lib-row";
  li.innerHTML = `<div class="lr-main"><span class="lr-name">${esc(c.name)}</span>`
    + `<span class="lr-meta">${c.card_count} cards · v${c.vocab_version}</span>`
    + `<div class="lr-concept muted">${esc(c.concept || "")}</div></div>`
    + `<div class="lr-actions">`
    + `<button data-act="code">Copy code</button>`
    + `<button data-act="rename">Rename</button>`
    + `<button data-act="open">Open</button>`
    + `<button data-act="delete" class="danger">Delete</button></div>`;
  li.querySelector('[data-act="code"]').onclick = () => copyClassCode(c.id);
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
  el("chooser").classList.add("hidden");    // viewing a saved class: the forge furniture gets out of the way
  el("v3-banner").classList.add("hidden");
  el("progress").classList.add("hidden");
  el("spinner").classList.add("hidden");
  renderClassView(cls);
  renderShareBar(cls, true);
  el("r-usage").classList.add("hidden");
  window.scrollTo({ top: 0 });
}
async function renameClass(id, oldName) {
  const name = prompt("New name:", oldName);
  if (!name) return;
  await fetch(`/api/classes/${id}`, {
    method: "PATCH", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  loadLibrary();
}
async function deleteClass(id, name) {
  if (!confirm(`Delete "${name}"? This cannot be undone.`)) return;
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
    if (meData.user) { ME = meData.user; ME_META = meData; renderTokens(); renderSignInMethods(); }
    await loadDonation();
    renderPurchases((await purR.json()).purchases || []);
  } catch (_) {
    toast("Couldn't load your account — check your connection.");
  }
  loadStats();
}

// Which sign-ins reach this account, and what is left to add. No unlinking in v1 (see index.html).
const IDENTITY_LABELS = { google: "Google", discord: "Discord", github: "GitHub", email: "Email", dev: "Dev" };

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
    li.textContent = (IDENTITY_LABELS[i.provider] || i.provider)
      + (i.label ? ` (${maskIdentity(i.label)})` : "");
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
  container.innerHTML =
    `<div class="custom-row"><span class="custom-cur">$</span>`
    + `<input id="${base}-input" class="in custom-amt" type="number" min="${min}" max="${max}" step="1" `
    + `inputmode="numeric" placeholder="${min}+" aria-label="Custom amount in dollars" />`
    + `<button id="${base}-btn" class="btn" type="button">Get tokens</button></div>`
    + `<p id="${base}-line" class="hint custom-line"></p>`;
  const input = el(`${base}-input`), btn = el(`${base}-btn`), line = el(`${base}-line`);
  const sentence = `$${min} and up: one token per dollar, whole dollars only.`;
  const sync = () => {
    const n = customDollars(input.value, c);
    btn.textContent = n ? `Get ${n * per} token${n * per === 1 ? "" : "s"}` : "Get tokens";
    if (!n) { line.textContent = sentence; return; }
    const { gross, fee } = grossFee(n * 100, c);
    line.textContent = `${sentence} ${fmtMoney(gross, cfg.currency)} charged, incl. `
      + `${fmtMoney(fee, cfg.currency)} card fee`;
  };
  input.oninput = sync;
  btn.onclick = () => donateCustom(input.value, btn, cfg);
  sync();
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
    b.innerHTML = `<span class="tier-label">${esc(fmtMoneyShort(t.net_cents, cfg.currency))} → `
      + `${n} token${n === 1 ? "" : "s"}</span>`
      + `<span class="tier-fee">${esc(fmtMoney(t.gross_cents, cfg.currency))} charged, incl. `
      + `${esc(fmtMoney(t.fee_cents, cfg.currency))} card fee</span>`;
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
    toast(`Enter a whole dollar amount between $${c.min_dollars} and $${c.max_dollars}.`);
    return;
  }
  await startCheckout({ custom_dollars: n }, btn);
}

// Both donate paths: ask the server for a Stripe Checkout session and hand the browser over to it.
async function startCheckout(payload, btn) {
  btn.disabled = true;
  const label = btn.innerHTML;
  btn.textContent = "Redirecting…";
  try {
    const r = await fetch("/api/donate", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || ("HTTP " + r.status));
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
        ? `Donated ${gross} (${fmtMoney(p.net_cents, p.currency)} + ${fmtMoney(fee, p.currency)} card fee)`
        : `Donated ${gross}`)
      : `Bought ${p.tokens} token${p.tokens === 1 ? "" : "s"} for ${gross}`;
    li.innerHTML = `<div class="lr-main"><span class="lr-name">${esc(what)}</span>`
      + `<span class="lr-meta">+${p.tokens} token${p.tokens === 1 ? "" : "s"} · ${esc(when)}`
      + (p.status === "refunded" ? ' · <span class="refunded">refunded</span>' : "") + `</span></div>`;
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
  if (outcome === "cancel") { toast("Donation canceled — you weren't charged."); return; }
  if (outcome !== "success" || !sessionId) return;

  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      const r = await fetch(`/api/checkout-status?session_id=${encodeURIComponent(sessionId)}`);
      const d = await r.json();
      if (!r.ok) throw new Error(d.error || ("HTTP " + r.status));
      if (d.status === "paid") {
        applyTokenState(d);
        renderTokens();
        toast(d.tokens > 0
          ? `Thank you! ${d.tokens} token${d.tokens === 1 ? "" : "s"} added — you're ready to forge.`
          : "Thank you for supporting the forge!");
        // They came here to forge, not to read the Account tab: land on the forge, token path armed.
        setForgePref("token");
        setMode("token");
        selectTab("forge");
        return;
      }
    } catch (e) {
      toast(e.message);
      return;
    }
    await new Promise((res) => setTimeout(res, 2000));  // still processing — give Stripe a moment
  }
  toast("Payment is processing — your balance will update shortly.");
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
  ];
  el("stats-tiles").innerHTML = tiles.map((t) =>
    `<div class="stat-tile"><div class="k">${esc(t.k)}</div><div class="v">${esc(t.v)}</div><div class="s">${esc(t.s)}</div></div>`).join("");

  renderStatsChart(d.daily || []);

  const provRows = (d.providers || []).map((p) =>
    `<tr><td>${esc(p.provider || "unknown")}</td><td class="num">${fmtInt(p.forges)}</td><td class="num">${pct(p.forges, f.total)}</td></tr>`).join("");
  el("stats-providers").innerHTML = `<tr><th>Provider</th><th class="num">Forges</th><th class="num">Share</th></tr>`
    + (provRows || `<tr><td colspan="3" class="muted">No usage rows in this window.</td></tr>`);

  const modelRows = (d.models || []).map((m) =>
    `<tr><td>${esc(m.model || "?")}<div class="muted">${esc(m.provider || "")} · ${esc(m.mode || "")}</div></td>`
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
function renderStatsChart(daily) {
  const box = el("stats-chart");
  if (!daily.length) { box.innerHTML = `<p class="hint">No forges in this window.</p>`; return; }
  const W = 720, H = 200, padL = 34, padR = 8, padT = 8, padB = 22;
  const innerW = W - padL - padR, innerH = H - padT - padB;
  const totals = daily.map((r) => STATS_SERIES.reduce((n, s) => n + Number(r[s.key] || 0), 0));
  const max = Math.max(1, ...totals);
  const step = innerW / daily.length;
  const barW = Math.max(2, Math.min(28, step - 3));
  const y = (v) => padT + innerH - (v / max) * innerH;
  const ticks = [0, Math.ceil(max / 2), max];
  let svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Forges per day by mode">`;
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
    if (i % labelEvery === 0 || i === daily.length - 1) {
      svg += `<text class="axis" x="${(x + barW / 2).toFixed(1)}" y="${H - 6}" text-anchor="middle">${esc(r.day.slice(5))}</text>`;
    }
  });
  svg += `</svg>`;
  const legend = `<div class="stats-legend">` + STATS_SERIES.map((s) =>
    `<span><i style="background:${s.color}"></i>${esc(s.label)}</span>`).join("") + `</div>`;
  box.innerHTML = legend + `<div class="stats-wrap">${svg}</div>`;
}

// --- wiring --------------------------------------------------------------------------------------

el("nav-forge").onclick = () => selectTab("forge");
el("nav-library").onclick = () => selectTab("library");
el("nav-account").onclick = () => selectTab("account");
el("tokens").onclick = () => selectTab("account");  // the header chip doubles as a shortcut to buy/see balance
el("forge-btn").onclick = forge;
el("choice-go").onclick = () => sendChoice([...(choiceState?.picked || [])]);
el("choice-skip").onclick = () => sendChoice([]);
el("copy-code").onclick = () => copy(el("r-code").value);
el("share-link").onclick = () => copy(el("share-link").dataset.url);
el("view-back").onclick = () => selectTab("forge");
el("signout").onclick = async () => { await fetch("/logout", { method: "POST" }); location.href = "/"; };
el("load-models").onclick = loadModels;
el("choose-byok").onclick = chooseByok;
el("choose-token").onclick = chooseToken;
el("v3-banner-x").onclick = () => { lsSet("bts_v3_banner_dismissed", "1"); renderBanner(); };

// feedback overlay: close on the × button, a backdrop click, or Escape; submit posts the rating.
el("fb-close").onclick = closeFeedback;
el("fb-submit").onclick = submitFeedback;
el("fb-overlay").onclick = (ev) => { if (ev.target === el("fb-overlay")) closeFeedback(); };
document.addEventListener("keydown", (ev) => {
  if (ev.key === "Escape" && !el("fb-overlay").classList.contains("hidden")) closeFeedback();
});

async function loadModels() {
  const base_url = resolvedBaseUrl();
  const api_key = el("api_key").value.trim();
  if (!base_url || !api_key) { toast("Pick a provider and enter your API key first."); return; }
  const btn = el("load-models");
  btn.disabled = true; const label = btn.textContent; btn.textContent = "Loading…";
  try {
    const r = await fetch("/api/models", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ base_url, api_key }),
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || ("HTTP " + r.status));
    const dl = el("model-list");
    dl.innerHTML = "";
    for (const id of d.models) { const o = document.createElement("option"); o.value = id; dl.appendChild(o); }
    saveByok();
    toast(`Loaded ${d.models.length} models — click the Model box to pick one.`);
    el("model").focus();
  } catch (e) {
    toast(e.message);
  } finally {
    btn.disabled = false; btn.textContent = label;
  }
}
// Which box is open IS the choice: opening one closes the other and is remembered for next visit.
el("forge-byok").addEventListener("toggle", () => onPayBoxToggle("forge-byok", "forge-token", "byok"));
el("forge-token").addEventListener("toggle", () => onPayBoxToggle("forge-token", "forge-byok", "token"));
el("mode-fake").onchange = () => { renderForgeButton(); renderChooser(); };

el("provider").onchange = () => { applyProvider(); saveByok(); renderEstimate(); renderForgeButton(); };
el("model").oninput = () => { renderEstimate(); renderForgeButton(); };
el("stats-days").onchange = loadStats;

// Sniff an unambiguous key prefix and jump the dropdown to the matching provider.
el("api_key").oninput = () => {
  const guess = providerFromKey(el("api_key").value.trim());
  if (guess && guess !== el("provider").value) { el("provider").value = guess; applyProvider(); }
  renderForgeButton();
};

applyProvider();
boot();

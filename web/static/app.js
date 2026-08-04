"use strict";

const $ = (sel) => document.querySelector(sel);
const el = (id) => document.getElementById(id);

let ME = null;

// --- boot ---------------------------------------------------------------------------------------

async function boot() {
  const r = await fetch("/api/me");
  const data = await r.json();
  ME = data.user;
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
  selectTab("forge");
  handlePurchaseReturn();
}

// Reflect the user's token balance in the header chip + the "Use a token" hint, and steer the default mode:
// out of tokens (and not unlimited) ⇒ start on BYOK so the forge button isn't a dead end.
function renderTokens() {
  if (!ME) return;
  const unlimited = !!ME.unlimited;
  const bal = unlimited ? Infinity : Number(ME.token_balance || 0);
  const chip = el("tokens");
  chip.textContent = unlimited ? "∞ tokens" : `${bal} token${bal === 1 ? "" : "s"}`;
  chip.classList.remove("hidden");
  chip.classList.toggle("empty", !unlimited && bal <= 0);

  const status = el("token-status");
  if (unlimited) status.textContent = "Forges on our models (gemma + glm-5.2). Your account forges free.";
  else if (bal > 0) status.textContent = `Forges on our models (gemma + glm-5.2). Uses 1 of your ${bal} token${bal === 1 ? "" : "s"} — a free one arrives daily.`;
  else {
    status.innerHTML = "You're out of tokens for today — a free one arrives tomorrow. "
      + "<b>Bring your own key</b> below to keep forging, or "
      + '<button id="donate-cta" class="linkish" type="button">support the forge</button>.';
    // innerHTML replaced the node — re-wire the CTA on every render.
    el("donate-cta").onclick = () => selectTab("account");
  }

  // Keep the Account view's big balance in lockstep wherever the number changes (forge spend, purchase).
  const acct = el("acct-balance");
  if (acct) acct.textContent = unlimited ? "∞" : String(bal);

  // If the token path is unusable, default the radio to BYOK on load.
  if (!unlimited && bal <= 0) {
    const byok = document.querySelector('input[name="mode"][value="byok"]');
    if (byok) { byok.checked = true; applyMode(); }
  }
}

// Show the fields for the selected mode (token vs BYOK vs offline-fake).
function applyMode() {
  const m = currentMode();
  el("token-fields").style.display = m === "token" ? "" : "none";
  el("byok-fields").style.display = m === "byok" ? "" : "none";
}

function show(id) {
  for (const v of ["gate", "view-forge", "view-library", "view-account"]) el(v).classList.add("hidden");
  el(id).classList.remove("hidden");
}

function selectTab(which) {
  el("nav-forge").classList.toggle("active", which === "forge");
  el("nav-library").classList.toggle("active", which === "library");
  el("nav-account").classList.toggle("active", which === "account");
  if (which === "forge") show("view-forge");
  else if (which === "account") { show("view-account"); loadAccount(); }
  else { show("view-library"); loadLibrary(); }
}

// --- providers ----------------------------------------------------------------------------------
// Each provider maps to a known base URL (so users pick a name, not a URL) plus a key prefix used to
// auto-select the dropdown when it's unambiguous, the page to get a key, and a few suggested models.
// `mode` distinguishes Anthropic (native SDK path) from the OpenAI-compatible path. "custom" has no
// base_url — it reveals the URL field for any other OpenAI-compatible endpoint.
const PROVIDERS = {
  anthropic:  { label: "Anthropic", mode: "anthropic", base_url: "",
                prefix: "sk-ant-", keyFrom: "console.anthropic.com",
                models: ["claude-sonnet-4-6", "claude-haiku-4-5", "claude-opus-4-8"] },
  openai:     { label: "OpenAI", mode: "byok", base_url: "https://api.openai.com/v1",
                prefix: "sk-", keyFrom: "platform.openai.com (an API key, not a ChatGPT login)",
                models: ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "o4-mini"] },
  ollama:     { label: "Ollama Cloud", mode: "byok", base_url: "https://ollama.com/v1",
                prefix: "", keyFrom: "ollama.com/settings/keys",
                models: ["glm-5.2", "gemma4:31b", "gpt-oss:120b", "qwen3.5:397b", "deepseek-v4-pro"] },
  openrouter: { label: "OpenRouter", mode: "byok", base_url: "https://openrouter.ai/api/v1",
                prefix: "sk-or-", keyFrom: "openrouter.ai/keys",
                models: ["anthropic/claude-sonnet-4.6", "openai/gpt-4o", "google/gemini-2.5-pro"] },
  groq:       { label: "Groq", mode: "byok", base_url: "https://api.groq.com/openai/v1",
                prefix: "gsk_", keyFrom: "console.groq.com/keys",
                models: ["llama-3.3-70b-versatile", "moonshotai/kimi-k2-instruct"] },
  google:     { label: "Google Gemini", mode: "byok",
                base_url: "https://generativelanguage.googleapis.com/v1beta/openai",
                prefix: "AIza", keyFrom: "aistudio.google.com/apikey",
                models: ["gemini-2.5-pro", "gemini-2.5-flash"] },
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
    + `in your browser — never saved on our server.`;
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
  localStorage.setItem("bts_byok", JSON.stringify({
    provider: el("provider").value,
    base_url: el("base_url").value.trim(),
    model: el("model").value.trim(),
    api_key: el("api_key").value.trim(),
  }));
}

function currentMode() {
  return document.querySelector('input[name="mode"]:checked').value;
}

// --- forge (SSE over POST via fetch stream) ------------------------------------------------------

async function forge() {
  const concept = el("concept").value.trim();
  if (!concept) { toast("Describe a class first."); return; }
  const choice = currentMode();  // "token" | "byok" | "fake"

  // The wire `mode` is derived: BYOK splits into Anthropic's native path vs the OpenAI-compatible path
  // based on the chosen provider, so the backend routing is unchanged.
  const stagedEl = el("staged");
  const interactiveEl = el("interactive");
  const body = {
    concept,
    mode: choice,
    staged: stagedEl ? stagedEl.checked : true,
    // interactive forge mode: mid-forge archetype pick (only meaningful with the staged front-end)
    interactive: !!(interactiveEl && interactiveEl.checked && (stagedEl ? stagedEl.checked : true)),
  };
  if (choice === "token") {
    if (!ME.unlimited) {
      const bal = Number(ME.token_balance || 0);
      if (bal <= 0) {
        toast("You're out of tokens for today — a free one arrives tomorrow, or bring your own key.");
        selectTab("account");
        return;
      }
      if (!confirm(`This will use 1 token. You have ${bal}. Forge this class?`)) return;
    }
  } else if (choice === "byok") {
    const p = currentProvider();
    const api_key = el("api_key").value.trim();
    const model = el("model").value.trim();
    if (!api_key || !model) { toast("Enter your API key and a model — or switch to 'Use a token'."); return; }
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

  el("forge-btn").disabled = true;
  el("result").classList.add("hidden");
  el("progress").classList.remove("hidden");
  el("log").textContent = "";
  resetChoice();  // clear any choice panel left over from a previous forge
  // Echo what we asked for, so a mode mishap (e.g. a stale page) is visible in the log immediately.
  appendLog(`• requested: ${body.mode} · ${body.staged ? "creative" : "one-shot"}`
            + (body.interactive ? " · interactive" : ""));

  try {
    const resp = await fetch("/api/forge-class", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!resp.ok && resp.headers.get("content-type")?.includes("application/json")) {
      const e = await resp.json();
      // Server says out of tokens (a stale balance slipped past the pre-check) — route to the buy flow.
      if (resp.status === 402) {
        if (typeof e.token_balance === "number") { ME.token_balance = e.token_balance; renderTokens(); }
        selectTab("account");
      }
      throw new Error(e.error || ("HTTP " + resp.status));
    }
    await consumeSSE(resp, onForgeEvent);
  } catch (e) {
    appendLog("✗ " + e.message);
    toast(e.message);
  } finally {
    el("forge-btn").disabled = false;
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
  if (data && typeof data.token_balance === "number" && ME && !ME.unlimited) {
    ME.token_balance = data.token_balance;
    renderTokens();
  }
  if (event === "progress") appendLog("• " + data.message);
  else if (event === "choice") renderChoice(data);
  else if (event === "error") { appendLog("✗ " + data.error); toast(data.error); }
  else if (event === "result") { appendLog("✓ done"); renderResult(data); }
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

// --- result + cards ------------------------------------------------------------------------------

function renderResult(cls) {
  el("spinner").classList.add("hidden");
  el("r-name").textContent = cls.character?.name || cls.name;
  el("r-desc").textContent = cls.character?.description || "";
  renderArchetypes(cls.archetypes);
  renderRelic(cls.relic, cls.id);
  renderMechanics(cls.character, cls.id);
  el("r-code").value = cls.code;
  const wrap = el("r-cards");
  wrap.innerHTML = "";
  for (const c of cls.cards || []) wrap.appendChild(cardEl(c, cls.id));
  el("result").classList.remove("hidden");
}

// --- the archetypes the class was built around ---------------------------------------------------
// The same cards the player picked from at the archetype checkpoint: themed title + one strategy line.
// Classes forged before this was stored (or via paths without a pitch) fall back to the catalog
// name + description; an empty list (old classes) hides the section entirely.

function renderArchetypes(archetypes) {
  const box = el("r-archetypes");
  box.innerHTML = "";
  const list = (archetypes || []).filter((a) => a && (a.title || a.name || a.id));
  if (!list.length) { box.classList.add("hidden"); return; }
  for (const a of list) {
    const d = document.createElement("div");
    d.className = "arch";
    const headline = a.title || a.name || a.id;
    const line = a.pitch || a.description || "";
    d.innerHTML = `<div class="mech-top"><span class="mech-badge">⚙ Archetype</span>`
      + `<span class="mech-name">${esc(headline)}</span></div>`
      + (line ? `<div class="mech-teaser">${esc(line)}</div>` : "");
    box.appendChild(d);
  }
  box.classList.remove("hidden");
}

// --- forged keystone relic ----------------------------------------------------------------------

function renderRelic(relic, classId) {
  const box = el("r-relic");
  if (!relic) { box.classList.add("hidden"); box.innerHTML = ""; return; }
  const lines = relicLines(relic);
  box.innerHTML = `<button class="cc-fb" title="Give feedback" aria-label="Give feedback">💬</button>`
    + `<div class="relic-top"><span class="relic-badge">⬦ Keystone relic</span>`
    + `<span class="relic-name">${esc(relic.name || "")}</span></div>`
    + (relic.description ? `<div class="relic-desc">${esc(relic.description)}</div>` : "")
    + (lines.length ? `<ul class="relic-eff">${lines.map((l) => `<li>${esc(l)}</li>`).join("")}</ul>` : "");
  // Only persisted (forged / re-opened) classes can take feedback — they have an id to tie it to.
  const fb = box.querySelector(".cc-fb");
  if (classId != null) {
    fb.onclick = (ev) => {
      ev.stopPropagation();
      openFeedback({ classId, kind: "relic", subjectId: relic.name || "", title: relic.name || "Keystone relic",
                     detailHtml: elementDetailHtml(relic.description, lines), chip: box });
    };
  } else { fb.remove(); }
  box.classList.remove("hidden");
}

function relicLines(relic) {
  return [...(relic.modifiers || []).map(fmtMod), ...(relic.hooks || []).map(fmtHook)].filter(Boolean);
}

const RELIC_MOD_LABELS = {
  max_energy: "max energy", first_attack: "first-attack damage",
  cost_reduction: "card cost reduction", start_combat_block: "block at combat start",
};
function fmtMod(m) {
  return `+${m.amount} ${RELIC_MOD_LABELS[m.stat] || m.stat}`;
}

const RELIC_TRIGGER_LABELS = {
  turn_start: "Turn start", turn_end: "Turn end", attacked: "When attacked",
  on_exhaust: "On exhaust", on_card_played: "On card played", combat_end: "Combat end",
  on_card_drawn: "On card drawn", on_damage_dealt: "On damage dealt", on_block_gained: "On block gained",
};
function fmtHook(h) {
  const trig = RELIC_TRIGGER_LABELS[h.trigger] || h.trigger;
  const eff = (h.effects || []).map(fmtEffect).join(", ");
  const tgt = h.target && h.target !== "self" ? ` → ${h.target}` : "";
  const cond = h.when?.kind ? ` (if ${String(h.when.kind).replace(/_/g, " ")})` : "";
  const once = h.once_per_combat ? " · once/combat" : "";
  return `${trig}${tgt}: ${eff}${cond}${once}`;
}

// --- forged class mechanics (custom orbs / statuses / summons) -----------------------------------
// These carry no card text, so a player can't otherwise tell what an invented orb/status/summon does.
// We surface each as a chip; clicking it opens the feedback popout with a full description + effect lines.

const MECH_KINDS = [
  { kind: "orb", badge: "◉ Orb", pool: "orb_pool", lines: orbLines },
  { kind: "status", badge: "✦ Status", pool: "status_pool", lines: statusLines },
  { kind: "summon", badge: "⚔ Summon", pool: "summon_pool", lines: summonLines },
];

function renderMechanics(character, classId) {
  const box = el("r-mechanics");
  box.innerHTML = "";
  const items = [];
  for (const spec of MECH_KINDS) {
    for (const entry of (character?.[spec.pool] || [])) {
      // Base orbs are plain name strings (lightning/frost/dark) — they have no custom definition to describe.
      if (typeof entry !== "object" || entry == null) continue;
      items.push({ spec, entry });
    }
  }
  if (!items.length) { box.classList.add("hidden"); return; }
  box.innerHTML = `<div class="mech-head">Class mechanics — custom elements this class invents. `
    + `Click one to see what it does and rate it.</div><div class="mech-grid"></div>`;
  const grid = box.querySelector(".mech-grid");
  for (const { spec, entry } of items) grid.appendChild(mechEl(spec, entry, classId));
  box.classList.remove("hidden");
}

function mechEl(spec, entry, classId) {
  const d = document.createElement("div");
  d.className = "mech mech-" + spec.kind;
  const emoji = entry.emoji ? esc(entry.emoji) + " " : "";
  const lines = spec.lines(entry);
  // Show the FULL effect in the chip (e.g. an orb's channel AND evoke), not just a teaser — the player
  // shouldn't have to open the popout to read what it does. The popout stays for giving feedback.
  const descHtml = entry.description ? `<div class="mech-teaser">${esc(entry.description)}</div>` : "";
  const effHtml = lines.length
    ? `<ul class="mech-eff">${lines.map((l) => `<li>${esc(l)}</li>`).join("")}</ul>` : "";
  d.innerHTML = `<button class="cc-fb" title="Give feedback" aria-label="Give feedback">💬</button>`
    + `<div class="mech-top"><span class="mech-badge">${spec.badge}</span>`
    + `<span class="mech-name">${emoji}${esc(entry.name || "")}</span></div>`
    + descHtml + effHtml;
  d.onclick = () => openFeedback({
    classId, kind: spec.kind, subjectId: entry.name || "", title: (entry.emoji ? entry.emoji + " " : "") + (entry.name || ""),
    detailHtml: elementDetailHtml(entry.description, lines), chip: d,
  });
  if (classId == null) d.querySelector(".cc-fb").remove();
  return d;
}

// Build the popout body shared by every non-card element: an italic description plus a bulleted effect list.
function elementDetailHtml(description, lines) {
  return (description ? `<p class="fb-detail-desc">${esc(description)}</p>` : "")
    + (lines && lines.length ? `<ul class="fb-detail-eff">${lines.map((l) => `<li>${esc(l)}</li>`).join("")}</ul>` : "");
}

const ORB_VAL_LABELS = { passive: "Each turn while channeled", evoke: "On evoke" };
function orbLines(orb) {
  const out = [];
  const passive = (orb.passive || []).map((e) => fmtEffect(e, "enemy")).join(", ");
  const evoke = (orb.evoke || []).map((e) => fmtEffect(e, "enemy")).join(", ");
  if (passive) out.push(`${ORB_VAL_LABELS.passive}: ${passive}`);
  if (evoke) out.push(`${ORB_VAL_LABELS.evoke}: ${evoke}`);
  return out;
}

const STATUS_HOOK_LABELS = {
  damage_dealt: "your attacks", damage_taken: "damage you take",
  block_gained: "block you gain", turn_start: "turn start", turn_end: "turn end",
};
function statusLines(st) {
  const out = [];
  const kind = st.type === "debuff" ? "Debuff" : "Buff";
  const hook = STATUS_HOOK_LABELS[st.hook] || (st.hook ? String(st.hook).replace(/_/g, " ") : "");
  out.push(hook ? `${kind} — affects ${hook}` : kind);
  if (st.decay && st.decay !== "none") out.push(`Decays: ${String(st.decay).replace(/_/g, " ")}`);
  return out;
}

function summonLines(sm) {
  const out = [];
  if (sm.max_hp != null) out.push(`Max HP: ${sm.max_hp}`);
  out.push("A passive minion — summon it, then spend cards to make it attack.");
  return out;
}

function cardEl(c, classId) {
  const d = document.createElement("div");
  d.className = "cardchip r-" + (c.rarity || "common");
  d.dataset.cardId = c.id ?? "";
  const effects = (c.effects || []).map((e) => fmtEffect(e, c.target)).join(". ");
  d.innerHTML = `<button class="cc-fb" title="Give feedback" aria-label="Give feedback">💬</button>`
    + `<div class="cc-top"><span class="cc-name">${esc(c.name)}</span>`
    + `<span class="cc-cost">${c.cost ?? ""}</span></div>`
    + `<div class="cc-meta">${esc(c.type)} · ${esc(c.rarity)}</div>`
    + `<div class="cc-eff">${esc(effects)}</div>`;
  // classId is needed to tie feedback to a persisted card; only forged/re-opened classes have one.
  const fb = d.querySelector(".cc-fb");
  if (classId != null) {
    fb.onclick = (ev) => {
      ev.stopPropagation();
      openFeedback({ classId, kind: "card", subjectId: c.id ?? "", title: c.name || "", chip: d });
    };
  } else {
    fb.remove();
  }
  return d;
}

// --- per-card feedback overlay ------------------------------------------------------------------

// UI labels → the generator's canonical categories (btsgen.contract). Order = display order.
const FB_CATEGORIES = [
  { value: "great", label: "Good" },
  { value: "overpowered", label: "Seems OP" },
  { value: "underpowered", label: "Underpowered" },
  { value: "off_theme", label: "Off-theme" },
  { value: "confusing", label: "Doesn't make sense" },
  { value: "doesnt_work", label: "Doesn't work" },
];

// What the popout rates. `kind` is "card" for deck cards, or "orb"/"status"/"summon"/"relic" for the
// non-card elements; `subjectId` is the card id (cards) or the element name (elements).
let fbState = { classId: null, kind: "card", subjectId: "", chip: null, category: null };

const FB_TITLES = {
  card: "How's this card?", relic: "How's this relic?", orb: "How's this orb?",
  status: "How's this status?", summon: "How's this summon?",
};

// Open the shared feedback popout. `detailHtml` (elements only) shows a description + effect lines so the
// player can actually evaluate a mechanic that carries no card text.
function openFeedback({ classId, kind, subjectId, title, detailHtml, chip }) {
  fbState = { classId, kind, subjectId: subjectId ?? "", chip, category: null };
  el("fb-title").textContent = FB_TITLES[kind] || "How's this?";
  el("fb-card-name").textContent = title || "";
  const detail = el("fb-detail");
  detail.innerHTML = detailHtml || "";
  detail.classList.toggle("hidden", !detailHtml);
  el("fb-note").value = "";
  el("fb-submit").disabled = true;
  const wrap = el("fb-cats");
  wrap.innerHTML = "";
  for (const cat of FB_CATEGORIES) {
    const b = document.createElement("button");
    b.className = "fb-cat";
    b.textContent = cat.label;
    b.onclick = () => {
      fbState.category = cat.value;
      for (const x of wrap.children) x.classList.toggle("selected", x === b);
      el("fb-submit").disabled = false;
    };
    wrap.appendChild(b);
  }
  el("fb-overlay").classList.remove("hidden");
}

function closeFeedback() { el("fb-overlay").classList.add("hidden"); }

async function submitFeedback() {
  if (!fbState.category) return;
  const btn = el("fb-submit");
  btn.disabled = true;
  // Cards and elements have separate server endpoints (different server-side resolution), same payload shape.
  const isCard = fbState.kind === "card";
  const url = isCard ? "/api/card-feedback" : "/api/element-feedback";
  const body = isCard
    ? { class_id: fbState.classId, card_id: fbState.subjectId }
    : { class_id: fbState.classId, element_kind: fbState.kind, element_id: fbState.subjectId };
  body.category = fbState.category;
  body.note = el("fb-note").value.trim();
  try {
    const r = await fetch(url, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.error || ("HTTP " + r.status));
    if (fbState.chip) {
      fbState.chip.classList.add("rated");
      const fb = fbState.chip.querySelector(".cc-fb");
      if (fb) {
        fb.textContent = "✓";
        const label = (FB_CATEGORIES.find((c) => c.value === fbState.category) || {}).label;
        fb.title = label ? `You rated this: ${label} — click to change` : "Feedback sent — click to change";
      }
    }
    closeFeedback();
    toast("Thanks for the feedback!");
  } catch (e) {
    toast(e.message);
    btn.disabled = false;
  }
}

// --- effect -> in-game-style text ----------------------------------------------------------------
// Render each effect op the way the card reads in play ("Deal 6 damage", "At the end of each turn:
// gain 1 Strength") instead of the raw vocabulary op ("add_trigger 2"). The CARD carries one target
// (enemy/self/all_enemies); a trigger's nested payload is always self/orb, so those pass "self".

const STATUS_NAMES = {
  vulnerable: "Vulnerable", weak: "Weak", frail: "Frail", poison: "Poison", strength: "Strength",
  dexterity: "Dexterity", thorns: "Thorns", regen: "Regen", metallicize: "Metallicize", artifact: "Artifact",
  buffer: "Buffer", intangible: "Intangible", ritual: "Ritual", blur: "Blur", barricade: "Barricade",
  focus: "Focus", temp_strength: "Strength (this turn)", temp_dexterity: "Dexterity (this turn)",
};
const TRIGGER_PREFIX = {
  turn_start: "At the start of each turn", turn_end: "At the end of each turn",
  ripen: "After it ripens in hand", on_hp_lost: "Whenever you lose HP",
};
const SCALE_SUFFIX = {
  cards_in_hand: " per card in hand", cards_retained: " per card retained",
  unspent_energy_last_turn: " per unspent energy",
  forged: " plus your Forge", // Phase M (gap #36): the additive Forge payoff
};
const titleCase = (s) => String(s || "").replace(/_/g, " ").replace(/\b\w/g, (m) => m.toUpperCase());
const statusName = (s) => STATUS_NAMES[s] || titleCase(s);

function condCore(c) {
  const v = c.value;
  switch (c.kind) {
    case "orb_count_ge": return `you have ${v ?? "enough"}+ orbs`;
    case "orbs_match": return "your channeled orbs match";
    case "target_has_status": return `the enemy has ${statusName(c.status)}`;
    case "no_block": return "you have no Block";
    case "has_block": return "you have Block";
    case "hp_below_half": return "you're below half HP";
    case "enemy_count_ge": return `there are ${v ?? "enough"}+ enemies`;
    case "turn_at_least": return `it's turn ${v ?? "?"}+`;
    case "hand_size_ge": return `your hand has ${v ?? "enough"}+ cards`;
    case "retained_last_turn": return "you retained a card last turn";
    case "forged_ge": return `your Forge is ${v ?? "enough"}+`;
    default: return titleCase(c.kind);
  }
}
const condText = (c) => ` (${c.negate ? "unless" : "if"} ${condCore(c)})`;

function effPhrase(e, target) {
  const a = e.amount;
  const scale = (e.scale && e.scale !== "x") ? (SCALE_SUFFIX[e.scale] || "") : "";
  const hits = e.hits > 1 ? ` ×${e.hits}` : "";
  const toAll = target === "all_enemies" ? " to all enemies" : "";
  switch (e.op) {
    case "damage": return `Deal ${a ?? ""} damage${scale}${toAll}${hits}`;
    case "block": return `Gain ${a ?? ""} Block${scale}`;
    case "draw": return `Draw ${a ?? 1} card${(a ?? 1) == 1 ? "" : "s"}${scale}`;
    case "gain_energy": return `Gain ${a ?? 1} energy`;
    case "lose_hp": return `Lose ${a ?? ""} HP`;
    case "heal": return `Heal ${a ?? ""}`;
    case "gain_orb_slot": return `Gain ${a ?? 1} orb slot${(a ?? 1) == 1 ? "" : "s"}`;
    case "forge": return `Forge ${a ?? 1}`; // Phase M (gap #36): stoke the Forge counter
    case "exhaust": return "Exhaust";
    case "innate": return "Innate";
    case "retain": return "Retain";
    case "ethereal": return "Ethereal";
    case "evoke": return "Evoke your next orb";
    case "channel_orb": return `Channel ${titleCase(e.orb || "an orb")}${a > 1 ? ` ×${a}` : ""}`;
    case "apply_status":
      return target === "self" ? `Gain ${a ?? ""} ${statusName(e.status)}`
                               : `Apply ${a ?? ""} ${statusName(e.status)}${toAll}`;
    case "apply_status_custom": return `Apply ${a ?? ""} ${e.status_name || "status"}`;
    case "summon": return `Summon ${e.summon_name || "a minion"}${a ? ` (${a} HP)` : ""}`;
    case "summon_attack": return `Minion attacks for ${a ?? ""}${hits}`;
    case "buff_summon": return `Give your minion +${a ?? ""} ${statusName(e.status)}`;
    case "add_trigger":
      return `${TRIGGER_PREFIX[e.trigger] || "Each turn"}: `
             + (e.effects || []).map((x) => effPhrase(x, "self")).join(", ");
    default: return a != null ? `${titleCase(e.op)} ${a}` : titleCase(e.op);
  }
}

function fmtEffect(e, target) {
  const base = effPhrase(e, target).replace(/\s+/g, " ").trim();
  return base + (e.when && e.when.kind ? condText(e.when) : "");
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
async function openClass(id) {
  const r = await fetch(`/api/classes/${id}`);
  const cls = await r.json();
  selectTab("forge");
  el("progress").classList.add("hidden");
  renderResult(cls);
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

// --- account: balance, donations (pay-what-you-want Stripe Checkout), donation history -----------

let DONATE_CFG = null;  // last /api/billing payload — donate() validates amounts against it

async function loadAccount() {
  el("acct-email").textContent = ME ? (ME.email || ME.name || "") : "";
  try {
    // Balance can have moved server-side (webhook credit, another tab, the daily grant) — refresh it too.
    const [meR, billR, purR] = await Promise.all([
      fetch("/api/me"), fetch("/api/billing"), fetch("/api/purchases"),
    ]);
    const me = (await meR.json()).user;
    if (me) { ME = me; renderTokens(); }
    renderDonation(await billR.json());
    renderPurchases((await purR.json()).purchases || []);
  } catch (_) {
    toast("Couldn't load your account — check your connection.");
  }
}

function fmtMoney(cents, currency) {
  try {
    return new Intl.NumberFormat(undefined, { style: "currency", currency: (currency || "usd").toUpperCase() })
      .format((cents || 0) / 100);
  } catch (_) { return `$${((cents || 0) / 100).toFixed(2)}`; }
}

function renderDonation(cfg) {
  DONATE_CFG = cfg || null;
  const enabled = !!(cfg && cfg.enabled);
  el("donate").classList.toggle("hidden", !enabled);
  el("donate-note").classList.toggle("hidden", enabled);
  if (!enabled) return;
  const presets = el("donate-presets");
  presets.innerHTML = "";
  for (const cents of cfg.presets || []) {
    const b = document.createElement("button");
    b.className = "btn donate-preset";
    b.type = "button";
    b.textContent = fmtMoney(cents, cfg.currency);
    b.onclick = (ev) => donate(cents, ev.target);
    presets.appendChild(b);
  }
  // Static elements, but wiring here (idempotent) keeps all donate logic in one place.
  el("donate-btn").onclick = (ev) => {
    const dollars = parseFloat(el("donate-amount").value);
    donate(Math.round(dollars * 100), ev.target);
  };
}

async function donate(amountCents, btn) {
  if (!Number.isFinite(amountCents) || amountCents <= 0) { toast("Enter an amount in dollars first."); return; }
  if (DONATE_CFG && (amountCents < DONATE_CFG.min_cents || amountCents > DONATE_CFG.max_cents)) {
    toast(`Donations can be ${fmtMoney(DONATE_CFG.min_cents, DONATE_CFG.currency)} to `
      + `${fmtMoney(DONATE_CFG.max_cents, DONATE_CFG.currency)}.`);
    return;
  }
  btn.disabled = true;
  const label = btn.textContent;
  btn.textContent = "Redirecting…";
  try {
    const r = await fetch("/api/donate", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ amount_cents: amountCents }),
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || ("HTTP " + r.status));
    location.href = d.url;  // off to Stripe's hosted checkout page
  } catch (e) {
    toast(e.message);
    btn.disabled = false;
    btn.textContent = label;
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
    li.innerHTML = `<div class="lr-main"><span class="lr-name">Donated ${esc(fmtMoney(p.amount_cents, p.currency))}</span>`
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
        if (typeof d.token_balance === "number" && ME && !ME.unlimited) {
          ME.token_balance = d.token_balance;
          renderTokens();
        }
        toast(`Thank you for supporting the forge — ${d.tokens} token${d.tokens === 1 ? "" : "s"} added!`);
        selectTab("account");
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

// --- helpers -------------------------------------------------------------------------------------

async function copy(text) {
  try { await navigator.clipboard.writeText(text); toast("Copied!"); }
  catch (_) { toast("Copy failed — select the text manually."); }
}
function esc(s) {
  return String(s ?? "").replace(/[&<>"]/g, (m) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[m]));
}
let toastTimer = null;
function toast(msg) {
  const t = el("toast");
  t.textContent = msg;
  t.classList.remove("hidden");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.add("hidden"), 3200);
}

// --- wiring --------------------------------------------------------------------------------------

el("nav-forge").onclick = () => selectTab("forge");
el("nav-library").onclick = () => selectTab("library");
el("nav-account").onclick = () => selectTab("account");
el("tokens").onclick = () => selectTab("account");  // the header chip doubles as a shortcut to buy/see balance
el("forge-btn").onclick = forge;
el("choice-go").onclick = () => sendChoice([...(choiceState?.picked || [])]);
el("choice-skip").onclick = () => sendChoice([]);
// interactive needs the staged front-end: keep the two checkboxes honest instead of silently ignoring one
el("interactive").onchange = () => { if (el("interactive").checked) el("staged").checked = true; };
el("staged").onchange = () => { if (!el("staged").checked) el("interactive").checked = false; };
el("copy-code").onclick = () => copy(el("r-code").value);
el("signout").onclick = async () => { await fetch("/logout"); location.href = "/"; };
el("load-models").onclick = loadModels;

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
for (const radio of document.querySelectorAll('input[name="mode"]')) {
  radio.onchange = applyMode;
}

el("provider").onchange = () => { applyProvider(); saveByok(); };

// Sniff an unambiguous key prefix and jump the dropdown to the matching provider.
el("api_key").oninput = () => {
  const guess = providerFromKey(el("api_key").value.trim());
  if (guess && guess !== el("provider").value) { el("provider").value = guess; applyProvider(); }
};

applyProvider();
boot();

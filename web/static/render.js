"use strict";

// render.js — the class renderers shared by the app (index.html / app.js) and the public share page
// (deck.html). Loaded BEFORE app.js; both are plain scripts in one global scope, so `$`/`el` and every
// helper here are globals app.js relies on. renderClassView(cls, {readOnly}) fills the #result markup;
// readOnly (the public page) passes no classId, which drops every feedback widget.

const $ = (sel) => document.querySelector(sel);
const el = (id) => document.getElementById(id);

// --- art ------------------------------------------------------------------------------------------
// "Show art" is a browser-only preference (the checkbox lives on My Classes); default on. It lives here
// rather than app.js because the public /deck page renders the same class view without app.js. Private
// windows throw on localStorage, so every access is guarded.
const ART_PREF_KEY = "bts_show_art";
function artEnabled() {
  try { return localStorage.getItem(ART_PREF_KEY) !== "0"; } catch (_) { return true; }
}
function setArtEnabled(on) {
  try { localStorage.setItem(ART_PREF_KEY, on ? "1" : "0"); } catch (_) { /* no store */ }
  document.body.classList.toggle("no-art", !on);
}
document.body.classList.toggle("no-art", !artEnabled());

// An art <img> that removes itself when the file is gone (btsweb-prune rotates old art off the server, and
// a class forged without art has no URL at all — the caller skips it). Lazy: a long library only fetches
// the rows on screen.
function artImg(src, className, alt) {
  const im = document.createElement("img");
  im.className = className;
  im.alt = alt || "";
  im.loading = "lazy";
  im.decoding = "async";
  im.onerror = () => im.remove();
  im.src = src;
  return im;
}

// The splash + sprite strip under the class name. Thumb URLs come from the API (small WebP renders);
// the full-size *_url fields are what the import code carries and stay out of the page.
function renderClassArt(cls) {
  const box = el("r-art");
  if (!box) return;
  box.innerHTML = "";
  const splash = cls.splash_thumb_url, sprite = cls.sprite_thumb_url;
  if (!artEnabled() || (!splash && !sprite)) { box.classList.add("hidden"); return; }
  const name = cls.character?.name || cls.name || "class";
  if (splash) box.appendChild(artImg(splash, "r-splash", `${name} splash art`));
  if (sprite) box.appendChild(artImg(sprite, "r-sprite", `${name} combat sprite`));
  box.classList.remove("hidden");
}

// --- result + cards ------------------------------------------------------------------------------

// Fill the #result markup (r-name, r-desc, r-archetypes, r-relic, r-mechanics, r-cards, r-code) from a class
// bundle. readOnly = no feedback widgets (the public share page has no session to rate with; the API shape
// there also carries no id). The caller owns everything around it (spinner, progress, view switching).
function renderClassView(cls, opts) {
  const readOnly = !!(opts && opts.readOnly);
  const classId = readOnly ? null : (cls.id ?? null);
  el("r-name").textContent = cls.character?.name || cls.name || "";
  el("r-desc").textContent = cls.character?.description || "";
  renderArchetypes(cls.archetypes);
  renderRelic(cls.relic, classId);
  renderMechanics(cls.character, classId);
  renderClassArt(cls);
  el("r-code").value = cls.code || "";
  const wrap = el("r-cards");
  wrap.innerHTML = "";
  const art = artEnabled() ? (cls.card_art || {}) : {};  // {card id: portrait thumb URL}
  for (const c of cls.cards || []) wrap.appendChild(cardEl(c, classId, art[c.id]));
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
  attack_base: "damage on every attack", max_hp: "max HP", // Phase AS (v48); max_hp may be negative (the price)
};
function fmtMod(m) {
  return `${m.amount > 0 ? "+" : ""}${m.amount} ${RELIC_MOD_LABELS[m.stat] || m.stat}`;
}
function ordinal(n) { return n + ({ 1: "st", 2: "nd", 3: "rd" }[n % 100 > 10 && n % 100 < 14 ? 0 : n % 10] || "th"); }

const RELIC_TRIGGER_LABELS = {
  turn_start: "Turn start", turn_end: "Turn end", attacked: "When attacked",
  on_exhaust: "On exhaust", on_card_played: "On card played", combat_end: "Combat end",
  on_card_drawn: "On card drawn", on_damage_dealt: "On damage dealt", on_block_gained: "On block gained",
  on_hp_lost: "On HP lost",
};
function fmtHook(h) {
  let trig = RELIC_TRIGGER_LABELS[h.trigger] || h.trigger;
  // Phase AS (v48): a typed on_card_played reads "On Attack played"; every_n reads "every 3rd".
  if (h.trigger === "on_card_played" && h.card_type) trig = `On ${h.card_type[0].toUpperCase()}${h.card_type.slice(1)} played`;
  const every = h.every_n ? ` (every ${ordinal(h.every_n)})` : "";
  const eff = (h.effects || []).map(fmtEffect).join(", ");
  const tgt = h.target && h.target !== "self" ? ` → ${h.target}` : "";
  const cond = h.when?.kind ? ` (if ${String(h.when.kind).replace(/_/g, " ")})` : "";
  const once = h.once_per_combat ? " · once/combat" : "";
  return `${trig}${every}${tgt}: ${eff}${cond}${once}`;
}

// --- forged class mechanics (custom orbs / statuses / summons) -----------------------------------
// These carry no card text, so a player can't otherwise tell what an invented orb/status/summon does.
// We surface each as a chip; clicking it opens the feedback popout with a full description + effect lines.

const MECH_KINDS = [
  { kind: "orb", badge: "◉ Orb", pool: "orb_pool", lines: orbLines },
  { kind: "status", badge: "✦ Status", pool: "status_pool", lines: statusLines },
  { kind: "summon", badge: "⚔ Summon", pool: "summon_pool", lines: summonLines },
  // Phase BA (v55): the class's signature potion. It carries no card text and it is not in the deck, so this
  // panel is the only place a player can read what it does before one drops.
  { kind: "potion", badge: "🧪 Potion", pool: "potion_pool", lines: potionLines },
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
  // Phase AY (v54): run-persistent Forge is a CLASS KNOB, not a pool entry — no card says it, so the panel is
  // the only place a player can learn the counter survives the fight. Informational: no feedback subject.
  const persist = !!character?.forge_persist;
  if (!items.length && !persist) { box.classList.add("hidden"); return; }
  box.innerHTML = `<div class="mech-head">Class mechanics — custom elements this class invents.`
    + (classId != null ? ` Click one to see what it does and rate it.` : ``) + `</div><div class="mech-grid"></div>`;
  const grid = box.querySelector(".mech-grid");
  if (persist) grid.appendChild(forgePersistEl());
  for (const { spec, entry } of items) grid.appendChild(mechEl(spec, entry, classId));
  box.classList.remove("hidden");
}

// Phase AY (v54): the static chip for `"forge_persist": true`. Same shape as a mech chip, but inert — there is
// no invented element to rate, just a rule about this class's Forge counter.
function forgePersistEl() {
  const d = document.createElement("div");
  d.className = "mech mech-forge";
  d.innerHTML = `<div class="mech-top"><span class="mech-badge">⚒ Forge</span>`
    + `<span class="mech-name">Keeps its edge</span></div>`
    + `<div class="mech-teaser">This class's Forge counter does not fully reset between fights.</div>`
    + `<ul class="mech-eff"><li>At the end of each combat it banks up to 5 Forge</li>`
    + `<li>Your first turn of the next combat gets that much Forge back (and summons your blade)</li></ul>`;
  return d;
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
  if (classId != null) {
    d.onclick = () => openFeedback({
      classId, kind: spec.kind, subjectId: entry.name || "", title: (entry.emoji ? entry.emoji + " " : "") + (entry.name || ""),
      detailHtml: elementDetailHtml(entry.description, lines), chip: d,
    });
  } else {
    d.querySelector(".cc-fb").remove();
  }
  return d;
}

// Build the popout body shared by every non-card element: an italic description plus a bulleted effect list.
function elementDetailHtml(description, lines) {
  return (description ? `<p class="fb-detail-desc">${esc(description)}</p>` : "")
    + (lines && lines.length ? `<ul class="fb-detail-eff">${lines.map((l) => `<li>${esc(l)}</li>`).join("")}</ul>` : "");
}

// Phase AR (v49): a `passive_timing: turn_start` orb (the Plasma shape) says so; fmtEffect already appends a
// per-effect `when` gate ("… (if you have 3+ orbs)").
const ORB_VAL_LABELS = { passive: "Each turn while channeled", passive_turn_start: "At the start of each turn while channeled", evoke: "On evoke" };
function orbLines(orb) {
  const out = [];
  const passive = (orb.passive || []).map((e) => fmtEffect(e, "enemy")).join(", ");
  const evoke = (orb.evoke || []).map((e) => fmtEffect(e, "enemy")).join(", ");
  if (passive) out.push(`${orb.passive_timing === "turn_start" ? ORB_VAL_LABELS.passive_turn_start : ORB_VAL_LABELS.passive}: ${passive}`);
  if (evoke) out.push(`${ORB_VAL_LABELS.evoke}: ${evoke}`);
  return out;
}

const STATUS_HOOK_LABELS = {
  damage_dealt: "your attacks", damage_taken: "damage you take",
  block_gained: "block you gain", turn_start: "turn start", turn_end: "turn end",
  energy_gain: "energy you gain", card_draw: "cards you draw",
  damage_over_time: "HP lost at its turn start", hit_count: "hits per attack",  // Phase AQ (v47)
};
// Phase BA (v55): the signature potion's chip lines — what it does, when you can drink it, and the one fact
// a player cannot infer from anywhere else: it is an ADDITION to the normal potion table, not a replacement.
function potionLines(po) {
  const out = [];
  const rarity = String(po.rarity || "common");
  out.push(`${rarity.charAt(0).toUpperCase()}${rarity.slice(1)} potion — usable `
           + (po.usage === "any" ? "any time" : "in combat"));
  const tgt = po.target || "self";
  const eff = (po.effects || []).map((e) => potionEffectText(e, tgt)).filter(Boolean).join(", ");
  if (eff) out.push(eff);
  out.push("Drops alongside the usual potions on runs of this class");
  return out;
}

// `summon`'s shared phrasing reads `amount` as the minion's HP (its meaning on a card); on a potion the
// amount is a COUNT, so render that one op here and defer everything else to the shared formatter.
function potionEffectText(e, target) {
  if (e && e.op === "summon") {
    const n = e.amount ?? 1;
    return `Summon ${e.summon_name || "a minion"}${n > 1 ? ` ×${n}` : ""}`;
  }
  return fmtEffect(e, target);
}

function statusLines(st) {
  const out = [];
  const kind = st.type === "debuff" ? "Debuff" : "Buff";
  const hook = STATUS_HOOK_LABELS[st.hook] || (st.hook ? String(st.hook).replace(/_/g, " ") : "");
  // Phase AQ: a multiplicative damage status reads as a percent scaler, not a flat stack bonus.
  const mode = st.mode === "multiplicative" ? " (+10% per stack, up to double)" : "";
  out.push(hook ? `${kind} — affects ${hook}${mode}` : kind);
  if (st.decay && st.decay !== "none") out.push(`Decays: ${String(st.decay).replace(/_/g, " ")}`);
  return out;
}

// Phase AV (v52): a pool entry is PASSIVE (an Osty-style bodyguard) unless it declares a move cycle; an
// autonomous entry may also be ETHEREAL (attackable:false) and carry on_summon / on_death / on_nth_attack
// payoffs. Mirrors SummonRunner.Describe on the C# side (same order: HP-or-Ethereal, the move cycle, on
// summon, on death, every Nth hit).
function summonMoves(sm) {
  if (Array.isArray(sm.moves) && sm.moves.length) return sm.moves.map((m) => m && m.actions).filter(Array.isArray);
  if (Array.isArray(sm.actions) && sm.actions.length) return [sm.actions];
  return [];
}

// The minion sub-vocabulary is its own small op set (attack / block / heal_self / apply_status) — map it
// onto the card-effect phraser so one formatter serves both.
function summonActionAsEffect(x) {
  const op = x.op === "attack" ? "damage" : x.op === "heal_self" ? "heal" : x.op;
  return { ...x, op };
}

function summonActionPhrase(actions) {
  return (actions || []).map((x) => fmtEffect(summonActionAsEffect(x), x.target || "enemy")).join(", ");
}

function summonLines(sm) {
  const out = [];
  const moves = summonMoves(sm);
  out.push(sm.attackable === false ? "Ethereal (cannot be attacked)"
                                   : `Max HP: ${sm.max_hp != null ? sm.max_hp : "?"}`);
  if (!moves.length) {
    out.push("A passive minion — summon it, then spend cards to make it attack.");
  } else if (moves.length === 1) {
    out.push(`Each turn: ${summonActionPhrase(moves[0])}`);
  } else {
    moves.forEach((m, i) => out.push(`Turn ${i + 1}: ${summonActionPhrase(m)}`));
  }
  if (Array.isArray(sm.on_summon) && sm.on_summon.length) out.push(`On summon: ${summonActionPhrase(sm.on_summon)}`);
  if (Array.isArray(sm.on_death) && sm.on_death.length) out.push(`On death: ${summonActionPhrase(sm.on_death)}`);
  const nth = sm.on_nth_attack;
  if (nth && Array.isArray(nth.actions) && nth.actions.length) {
    out.push(`Every ${nth.n}th hit: ${summonActionPhrase(nth.actions)}`);
  }
  return out;
}

// A card's `upgrade` (when present) is a positional overlay: upgrade.effects[i] replaces effects[i]
// (same op, better numbers — mirrors the mod's per-var delta in EffectRunner.UpgradeDelta), and
// upgrade.cost is the ABSOLUTE post-upgrade cost. Merge each entry over its base effect so a sparse
// upgrade spec still renders as a whole card.
function upgradedView(c) {
  const up = c.upgrade || {};
  const effects = (c.effects || []).map((e, i) => ({ ...e, ...((up.effects || [])[i] || {}) }));
  return { ...c, name: (c.name || "") + "+", cost: up.cost ?? c.cost, effects };
}

function hasUpgrade(c) {
  return c.upgrade != null && typeof c.upgrade === "object" && !Array.isArray(c.upgrade)
    && ((Array.isArray(c.upgrade.effects) && c.upgrade.effects.length > 0) || c.upgrade.cost != null);
}

function cardEl(c, classId, artUrl) {
  const d = document.createElement("div");
  d.className = "cardchip r-" + (c.rarity || "common");
  d.dataset.cardId = c.id ?? "";
  d.innerHTML = `<button class="cc-fb" title="Give feedback" aria-label="Give feedback">💬</button>`
    + `<div class="cc-top"><span class="cc-name"></span><span class="cc-cost"></span></div>`
    + `<div class="cc-meta">${esc(c.type)} · ${esc(c.rarity)}</div>`
    + `<div class="cc-eff"></div>`;
  // The portrait (when the class shipped with card art) sits above the name, like the in-game card.
  if (artUrl) d.insertBefore(artImg(artUrl, "cc-art", ""), d.querySelector(".cc-top"));
  // Name/cost/effects are painted (not baked into the innerHTML) so the upgrade toggle can repaint
  // them without rebuilding the chip — the feedback button keeps its listener and rated state.
  const paint = (view) => {
    d.querySelector(".cc-name").textContent = view.name ?? "";
    d.querySelector(".cc-cost").textContent = view.cost ?? "";
    d.querySelector(".cc-eff").textContent =
      (view.effects || []).map((e) => fmtEffect(e, view.target)).join(". ");
  };
  paint(c);
  if (hasUpgrade(c)) {
    const lab = document.createElement("label");
    lab.className = "cc-up";
    lab.innerHTML = `<input type="checkbox"> Show upgraded`;
    lab.querySelector("input").onchange = (ev) => {
      d.classList.toggle("upgraded", ev.target.checked);
      paint(ev.target.checked ? upgradedView(c) : c);
    };
    d.appendChild(lab);
  }
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
  status: "How's this status?", summon: "How's this summon?", potion: "How's this potion?",
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
  temp_thorns: "Thorns (this turn)", temp_focus: "Focus (this turn)", // Phase AN (v44)
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
    // Phase AR (v49): the later kinds, now reachable from an orb chip too (were falling through to titleCase).
    case "draw_pile_empty": return "your draw pile is empty";
    case "hp_lost_ge": return `you've lost ${v ?? "enough"}+ HP this turn`;
    case "dark_ge": return `your Dark is ${v ?? "enough"}+`;
    case "light_ge": return `your Light is ${v ?? "enough"}+`;
    case "centered": return `you're centered (within ${v ?? "?"})`;
    case "target_hp_below_half": return "the enemy is below half HP";
    case "target_has_block": return "the enemy has Block";
    case "energy_ge": return `you have ${v ?? "enough"}+ energy`;
    case "cards_played_this_turn_ge": return `you've played ${v ?? "enough"}+ cards this turn`;
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
    case "damage": return `Deal ${a ?? ""} damage${scale}${toAll}${hits}${e.unblockable === true ? " (ignores Block)" : ""}`; // Phase AN (v44)
    case "block": return `Gain ${a ?? ""} Block${scale}`;
    case "draw": return `Draw ${a ?? 1} card${(a ?? 1) == 1 ? "" : "s"}${scale}`;
    case "gain_energy": return `Gain ${a ?? 1} energy`;
    case "lose_hp": return `Lose ${a ?? ""} HP`;
    case "gain_max_hp": return `Gain ${a ?? ""} Max HP`; // Phase AN (v44)
    case "cost_shift": { // Phase AO (v45)
      const kind = { attack: "Attacks", skill: "Skills", power: "Powers" }[e.card_type] || "cards";
      const life = e.scope === "combat" ? "this combat" : "this turn";
      return e.count ? `Your next ${e.count > 1 ? e.count + " " : ""}${kind} cost ${a ?? 1} less ${life}` : `Your ${kind} cost ${a ?? 1} less ${life}`;
    }
    case "heal": return `Heal ${a ?? ""}`;
    case "discard": return `Discard ${a ?? 1} ${e.cards === "choose" ? "chosen" : "random"} card${(a ?? 1) == 1 ? "" : "s"}`; // Phase AP (v46)
    case "retrieve_card": { // Phase AP (v46)
      const n = a ?? 1;
      const pile = e.pile === "exhaust" ? "exhaust" : "discard";
      return e.cards === "choose" ? `Return ${n} chosen card${n == 1 ? "" : "s"} from your ${pile} pile to hand`
                                  : `Return ${n} random card${n == 1 ? "" : "s"} from your ${pile} pile to hand`;
    }
    case "add_status_card": { // Phase AP (v46)
      const n = a ?? 1;
      const name = { dazed: "Dazed", burn: "Burn" }[e.card] || "Wound";
      const pile = { draw: "draw pile", discard: "discard pile" }[e.pile] || "hand";
      return `Add ${n} ${n == 1 || name === "Dazed" ? name : name + "s"} to your ${pile}`;
    }
    case "gain_orb_slot": return `Gain ${a ?? 1} orb slot${(a ?? 1) == 1 ? "" : "s"}`;
    case "forge": return `Forge ${a ?? 1}`; // Phase M (gap #36): stoke the Forge counter
    case "spend_forge": return `Spend ${a ?? 1} Forge`; // Phase AX (v53, gap #44): the ramp cash-out (the card's price)
    case "spread_debuffs": return "Copy the target's debuffs to all other enemies"; // Phase AX (v53, gaps #45-#47)
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
    case "sacrifice_summon": return "Sacrifice your minion"; // Phase AV (v52): consume it (its on_death rattle fires)
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


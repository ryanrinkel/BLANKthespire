"use strict";

// render.js — the class renderers shared by the app (index.html / app.js) and the public share page
// (deck.html). Loaded BEFORE app.js; both are plain scripts in one global scope, so `$`/`el` and every
// helper here are globals app.js relies on. renderClassView(cls, {readOnly}) fills the #result markup;
// readOnly (the public page) passes no classId, which drops every feedback widget.

const $ = (sel) => document.querySelector(sel);
const el = (id) => document.getElementById(id);

// UI strings come from i18n.js (BTS_I18N, loaded first; docs/copy/COPY.md keys). Nothing here calls them at
// load time: every caller (app.js, deck.js) awaits BTS_I18N.ready before it renders. rT = plain text (for
// textContent / attributes / string building), rH = HTML (for innerHTML; vars are escaped).
const rT = (key, vars) => BTS_I18N.t(key, vars);
const rH = (key, vars) => BTS_I18N.html(key, vars);
// A label table keyed by a data value: the COPY.md key when the value is one we know, else null.
const rLabel = (prefix, known, value) => (known.includes(value) ? rT(prefix + value) : null);
// A forged class's translated name / description (the bundle's `loc` block, I18N_PLAN.md C2) for the site
// language, else `english`, per field. The one lookup every painter below uses (BTS_I18N.locField). Card
// RULES text is never in `loc`: the site always prints it in English.
const locField = (src, section, key, field, english) => BTS_I18N.locField(src, section, key, field, english);
// Data values shown as words: app.card_type.<type>, app.rarity.<rarity>, app.decay.<decay>; an unknown value
// prints raw (as before).
const CARD_TYPES = ["attack", "skill", "power"];
const RARITIES = ["basic", "common", "uncommon", "rare", "token"];
const DECAYS = ["lose_one_eot", "lose_all_eot"];
const capFirst = (s) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s);
const cardTypeLabel = (t) => rLabel("app.card_type.", CARD_TYPES, t) || String(t ?? "");
const rarityLabel = (r) => rLabel("app.rarity.", RARITIES, r) || String(r ?? "");

// --- phones (docs/plans/PHONE_FUNNEL_PLAN.md section 5) ----------------------------------------------
// A phone can forge but cannot play: the game runs on a PC. Coarse pointer (touch-first) or a phone/tablet
// UA turns on the hand-off furniture (body.is-phone shows .phone-only); desktops never see it.
const IS_PHONE = (() => {
  try {
    return window.matchMedia("(pointer: coarse)").matches || /iPhone|iPad|iPod|Android|Mobile/.test(navigator.userAgent);
  } catch (_) { return false; }
})();
document.body.classList.toggle("is-phone", IS_PHONE);

// "Send to my PC": the OS share sheet (AirDrop to a Mac, Messages / Notes / Mail to yourself) with the
// public /deck/<slug> link, which shows the import code. Where there is no share sheet, copy the link.
async function sendToPc(name, url) {
  if (!url) return;
  if (navigator.share) {
    try {
      const shown = name || rT("app.share_sheet.name_fallback");
      await navigator.share({
        title: rT("app.share_sheet.title", { name: shown }),
        text: rT("app.share_sheet.text", { name: shown }),
        url,
      });
      return;
    } catch (e) {
      if (e && e.name === "AbortError") return;  // the sheet was dismissed: not an error
    }
  }
  await copy(url);
}

// The import code box is readonly; a tap selects the whole code so the phone's Copy bubble is one tap away.
// One delegated listener covers the app and the public /deck page (both render #r-code).
function selectCodeBox(ev) {
  const box = ev.target;
  if (!box || box.id !== "r-code") return;
  box.select();
  try { box.setSelectionRange(0, box.value.length); } catch (_) { /* iOS needs the range form */ }
}
document.addEventListener("focusin", selectCodeBox);
document.addEventListener("click", selectCodeBox);

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
  const name = locField(cls, "character", null, "name", cls.character?.name || cls.name || "class");
  if (splash) box.appendChild(artImg(splash, "r-splash", rT("app.library.splash_alt", { name })));
  if (sprite) box.appendChild(artImg(sprite, "r-sprite", rT("app.result.sprite_alt", { name })));
  box.classList.remove("hidden");
}

// --- result + cards ------------------------------------------------------------------------------

// Fill the #result markup (r-name, r-desc, r-archetypes, r-relic, r-mechanics, r-cards, r-code) from a class
// bundle. readOnly = no feedback widgets (the public share page has no session to rate with; the API shape
// there also carries no id). The caller owns everything around it (spinner, progress, view switching).
function renderClassView(cls, opts) {
  const readOnly = !!(opts && opts.readOnly);
  const classId = readOnly ? null : (cls.id ?? null);
  el("r-name").textContent = locField(cls, "character", null, "name", cls.character?.name || cls.name || "");
  el("r-desc").textContent = locField(cls, "character", null, "description", cls.character?.description || "");
  renderArchetypes(cls.archetypes, cls);
  renderRelic(cls.relic, classId, cls);
  renderMechanics(cls.character, classId, cls);
  renderClassArt(cls);
  el("r-code").value = cls.code || "";
  const wrap = el("r-cards");
  wrap.innerHTML = "";
  const art = artEnabled() ? (cls.card_art || {}) : {};  // {card id: portrait thumb URL}
  for (const c of cls.cards || []) wrap.appendChild(cardEl(c, classId, art[c.id], cls));
  renderRulesNote(wrap);
  el("result").classList.remove("hidden");
}

// Not English: the card names above may be translated, but the rules text is the site's English renderer
// (I18N_PLAN.md C2, phase 1), so say once, under the cards, that the game prints it in the player's language.
function renderRulesNote(wrap) {
  let note = el("r-rules-note");
  if (BTS_I18N.lang === "en") { if (note) note.remove(); return; }
  if (!note) {
    note = document.createElement("p");
    note.id = "r-rules-note";
    note.className = "hint muted";
    wrap.after(note);
  }
  note.textContent = rT("deck.rules_in_english");
}

// --- the archetypes the class was built around ---------------------------------------------------
// The same cards the player picked from at the archetype checkpoint: themed title + one strategy line.
// Classes forged before this was stored (or via paths without a pitch) fall back to the catalog
// name + description; an empty list (old classes) hides the section entirely.

function renderArchetypes(archetypes, src) {
  const box = el("r-archetypes");
  box.innerHTML = "";
  // keep each archetype's bundle index: the translated names (loc.<locale>.archetypes[i]) are positional
  const list = (archetypes || []).map((a, i) => ({ a, i })).filter(({ a }) => a && (a.title || a.name || a.id));
  if (!list.length) { box.classList.add("hidden"); return; }
  for (const { a, i } of list) {
    const d = document.createElement("div");
    d.className = "arch";
    // the translation covers the archetype NAME (the pitch title is not translated), so it wins over the title
    const headline = locField(src, "archetypes", i, "name", a.title || a.name || a.id);
    const line = a.pitch || a.description || "";
    d.innerHTML = `<div class="mech-top"><span class="mech-badge">${rH("app.result.archetype_badge")}</span>`
      + `<span class="mech-name">${esc(headline)}</span></div>`
      + (line ? `<div class="mech-teaser">${esc(line)}</div>` : "");
    box.appendChild(d);
  }
  box.classList.remove("hidden");
}

// --- forged keystone relic ----------------------------------------------------------------------

function renderRelic(relic, classId, src) {
  const box = el("r-relic");
  if (!relic) { box.classList.add("hidden"); box.innerHTML = ""; return; }
  const lines = relicLines(relic);
  const name = locField(src, "relic", null, "name", relic.name || "");
  const desc = locField(src, "relic", null, "description", relic.description || "");
  box.innerHTML = fbButtonHtml()
    + `<div class="relic-top"><span class="relic-badge">${rH("app.result.relic_badge")}</span>`
    + `<span class="relic-name">${esc(name)}</span></div>`
    + (desc ? `<div class="relic-desc">${esc(desc)}</div>` : "")
    + (lines.length ? `<ul class="relic-eff">${lines.map((l) => `<li>${esc(l)}</li>`).join("")}</ul>` : "");
  // Only persisted (forged / re-opened) classes can take feedback — they have an id to tie it to.
  const fb = box.querySelector(".cc-fb");
  if (classId != null) {
    fb.onclick = (ev) => {
      ev.stopPropagation();
      openFeedback({ classId, kind: "relic", subjectId: relic.name || "", title: name || rT("app.result.relic_fallback_title"),
                     detailHtml: elementDetailHtml(desc, lines), chip: box });
    };
  } else { fb.remove(); }
  box.classList.remove("hidden");
}

function relicLines(relic) {
  return [...(relic.modifiers || []).map(fmtMod), ...(relic.hooks || []).map(fmtHook)].filter(Boolean);
}

// app.relic.mod.<stat> is the whole line ("{amount} max energy"); {amount} carries its sign ("+1", "-8").
// max_hp is Phase AS (v48) and may be negative (the price).
const RELIC_MOD_STATS = ["max_energy", "first_attack", "cost_reduction", "start_combat_block", "attack_base", "max_hp"];
function fmtMod(m) {
  const amount = `${m.amount > 0 ? "+" : ""}${m.amount}`;
  return RELIC_MOD_STATS.includes(m.stat) ? rT("app.relic.mod." + m.stat, { amount }) : `${amount} ${m.stat}`;
}
function ordinal(n) { return n + ({ 1: "st", 2: "nd", 3: "rd" }[n % 100 > 10 && n % 100 < 14 ? 0 : n % 10] || "th"); }
// "every Nth": an English ordinal (1st, 2nd, 3rd, 4th, 11th, 21st); every other language takes the bare number
// (its template carries the counter word: zh 每{n}次).
function nthLabel(n) { return BTS_I18N.lang === "en" ? ordinal(n) : String(n); }

// app.relic.trigger.<trigger>
const RELIC_TRIGGERS = ["turn_start", "turn_end", "attacked", "on_exhaust", "on_card_played", "combat_end",
  "on_card_drawn", "on_damage_dealt", "on_block_gained", "on_hp_lost"];
function fmtHook(h) {
  let trig = rLabel("app.relic.trigger.", RELIC_TRIGGERS, h.trigger) || h.trigger;
  // Phase AS (v48): a typed on_card_played reads "On Attack played"; every_n reads "every 3rd".
  if (h.trigger === "on_card_played" && h.card_type) {
    trig = rT("app.relic.trigger.on_type_played", { type: capFirst(cardTypeLabel(h.card_type)) });
  }
  const every = h.every_n ? rT("app.relic.every_nth", { n: nthLabel(h.every_n) }) : "";
  const eff = (h.effects || []).map(fmtEffect).join(", ");
  const tgt = h.target && h.target !== "self" ? ` → ${h.target}` : "";
  const cond = h.when?.kind ? ` (if ${String(h.when.kind).replace(/_/g, " ")})` : "";
  const once = h.once_per_combat ? rT("app.relic.once_per_combat") : "";
  return `${trig}${every}${tgt}: ${eff}${cond}${once}`;
}

// --- forged class mechanics (custom orbs / statuses / summons) -----------------------------------
// These carry no card text, so a player can't otherwise tell what an invented orb/status/summon does.
// We surface each as a chip; clicking it opens the feedback popout with a full description + effect lines.

const MECH_KINDS = [
  { kind: "orb", badge: "app.mech.badge_orb", pool: "orb_pool", lines: orbLines },
  { kind: "status", badge: "app.mech.badge_status", pool: "status_pool", lines: statusLines },
  { kind: "summon", badge: "app.mech.badge_summon", pool: "summon_pool", lines: summonLines },
  // Phase BA (v55): the class's signature potion. It carries no card text and it is not in the deck, so this
  // panel is the only place a player can read what it does before one drops.
  { kind: "potion", badge: "app.mech.badge_potion", pool: "potion_pool", lines: potionLines },
];

// pool kind -> the bundle `loc` section its entries are translated under (keyed by the English name)
const MECH_LOC = { orb: "orbs", status: "statuses", summon: "summons", potion: "potions" };

function renderMechanics(character, classId, src) {
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
  box.innerHTML = `<div class="mech-head">${rH("app.mech.head")}`
    + (classId != null ? rH("app.mech.head_rate") : ``) + `</div><div class="mech-grid"></div>`;
  const grid = box.querySelector(".mech-grid");
  if (persist) grid.appendChild(forgePersistEl());
  for (const { spec, entry } of items) grid.appendChild(mechEl(spec, entry, classId, src));
  box.classList.remove("hidden");
}

// Phase AY (v54): the static chip for `"forge_persist": true`. Same shape as a mech chip, but inert — there is
// no invented element to rate, just a rule about this class's Forge counter.
function forgePersistEl() {
  const d = document.createElement("div");
  d.className = "mech mech-forge";
  d.innerHTML = `<div class="mech-top"><span class="mech-badge">${rH("app.mech.forge_badge")}</span>`
    + `<span class="mech-name">${rH("app.mech.forge_name")}</span></div>`
    + `<div class="mech-teaser">${rH("app.mech.forge_teaser")}</div>`
    + `<ul class="mech-eff"><li>${rH("app.mech.forge_line_1")}</li>`
    + `<li>${rH("app.mech.forge_line_2")}</li></ul>`;
  return d;
}

function mechEl(spec, entry, classId, src) {
  const d = document.createElement("div");
  d.className = "mech mech-" + spec.kind;
  const emoji = entry.emoji ? esc(entry.emoji) + " " : "";
  const lines = spec.lines(entry);
  const name = locField(src, MECH_LOC[spec.kind], entry.name, "name", entry.name || "");
  const desc = locField(src, MECH_LOC[spec.kind], entry.name, "description", entry.description || "");
  // Show the FULL effect in the chip (e.g. an orb's channel AND evoke), not just a teaser — the player
  // shouldn't have to open the popout to read what it does. The popout stays for giving feedback.
  const descHtml = desc ? `<div class="mech-teaser">${esc(desc)}</div>` : "";
  const effHtml = lines.length
    ? `<ul class="mech-eff">${lines.map((l) => `<li>${esc(l)}</li>`).join("")}</ul>` : "";
  d.innerHTML = fbButtonHtml()
    + `<div class="mech-top"><span class="mech-badge">${rH(spec.badge)}</span>`
    + `<span class="mech-name">${emoji}${esc(name)}</span></div>`
    + descHtml + effHtml;
  if (classId != null) {
    d.onclick = () => openFeedback({
      classId, kind: spec.kind, subjectId: entry.name || "", title: (entry.emoji ? entry.emoji + " " : "") + name,
      detailHtml: elementDetailHtml(desc, lines), chip: d,
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
function orbLines(orb) {
  const out = [];
  const passive = (orb.passive || []).map((e) => fmtEffect(e, "enemy")).join(", ");
  const evoke = (orb.evoke || []).map((e) => fmtEffect(e, "enemy")).join(", ");
  if (passive) out.push(`${rT(orb.passive_timing === "turn_start" ? "app.mech.orb_passive_turn_start" : "app.mech.orb_passive")}: ${passive}`);
  if (evoke) out.push(`${rT("app.mech.orb_evoke")}: ${evoke}`);
  return out;
}

// app.mech.status_hook.<hook>; damage_over_time / hit_count are Phase AQ (v47)
const STATUS_HOOKS = ["damage_dealt", "damage_taken", "block_gained", "turn_start", "turn_end", "energy_gain",
  "card_draw", "damage_over_time", "hit_count"];
// Phase BA (v55): the signature potion's chip lines — what it does, when you can drink it, and the one fact
// a player cannot infer from anywhere else: it is an ADDITION to the normal potion table, not a replacement.
function potionLines(po) {
  const out = [];
  const rarity = String(po.rarity || "common");
  out.push(rT("app.mech.potion_line", {
    rarity: capFirst(rarityLabel(rarity)),
    when: rT(po.usage === "any" ? "app.mech.potion_any_time" : "app.mech.potion_in_combat"),
  }));
  const tgt = po.target || "self";
  const eff = (po.effects || []).map((e) => potionEffectText(e, tgt)).filter(Boolean).join(", ");
  if (eff) out.push(eff);
  out.push(rT("app.mech.potion_drops"));
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
  const kind = rT(st.type === "debuff" ? "app.mech.status_debuff" : "app.mech.status_buff");
  const hook = rLabel("app.mech.status_hook.", STATUS_HOOKS, st.hook) || (st.hook ? String(st.hook).replace(/_/g, " ") : "");
  // Phase AQ: a multiplicative damage status reads as a percent scaler, not a flat stack bonus.
  const mode = st.mode === "multiplicative" ? rT("app.mech.status_multiplicative") : "";
  out.push(hook ? rT("app.mech.status_line", { kind, hook, mode }) : kind);
  if (st.decay && st.decay !== "none") {
    const decay = rLabel("app.decay.", DECAYS, st.decay) || String(st.decay).replace(/_/g, " ");
    out.push(rT("app.mech.status_decays", { decay }));
  }
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
  out.push(sm.attackable === false ? rT("app.mech.summon_ethereal")
                                   : rT("app.mech.summon_max_hp", { hp: sm.max_hp != null ? sm.max_hp : "?" }));
  if (!moves.length) {
    out.push(rT("app.mech.summon_passive"));
  } else if (moves.length === 1) {
    out.push(rT("app.mech.summon_each_turn", { actions: summonActionPhrase(moves[0]) }));
  } else {
    moves.forEach((m, i) => out.push(rT("app.mech.summon_turn_n", { n: i + 1, actions: summonActionPhrase(m) })));
  }
  if (Array.isArray(sm.on_summon) && sm.on_summon.length) {
    out.push(rT("app.mech.summon_on_summon", { actions: summonActionPhrase(sm.on_summon) }));
  }
  if (Array.isArray(sm.on_death) && sm.on_death.length) {
    out.push(rT("app.mech.summon_on_death", { actions: summonActionPhrase(sm.on_death) }));
  }
  const nth = sm.on_nth_attack;
  if (nth && Array.isArray(nth.actions) && nth.actions.length) {
    out.push(rT("app.mech.summon_every_nth", { n: nthLabel(nth.n), actions: summonActionPhrase(nth.actions) }));
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

function cardEl(c, classId, artUrl, src) {
  const d = document.createElement("div");
  d.className = "cardchip r-" + (c.rarity || "common");
  d.dataset.cardId = c.id ?? "";
  const shownName = locField(src, "cards", c.id, "name", c.name ?? "");
  d.innerHTML = fbButtonHtml()
    + `<div class="cc-top"><span class="cc-name"></span><span class="cc-cost"></span></div>`
    + `<div class="cc-meta">${esc(cardTypeLabel(c.type))} · ${esc(rarityLabel(c.rarity))}</div>`
    + `<div class="cc-eff"></div>`;
  // The portrait (when the class shipped with card art) sits above the name, like the in-game card.
  if (artUrl) d.insertBefore(artImg(artUrl, "cc-art", ""), d.querySelector(".cc-top"));
  // Name/cost/effects are painted (not baked into the innerHTML) so the upgrade toggle can repaint
  // them without rebuilding the chip — the feedback button keeps its listener and rated state.
  const paint = (view) => {
    // upgradedView() appends "+" to the English name; the shown (maybe translated) name gets the same "+"
    d.querySelector(".cc-name").textContent = view === c ? shownName : shownName + "+";
    d.querySelector(".cc-cost").textContent = view.cost ?? "";
    d.querySelector(".cc-eff").textContent =
      (view.effects || []).map((e) => fmtEffect(e, view.target)).join(". ");
  };
  paint(c);
  if (hasUpgrade(c)) {
    const lab = document.createElement("label");
    lab.className = "cc-up";
    lab.innerHTML = `<input type="checkbox"> ${rH("app.card.show_upgraded")}`;
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
      openFeedback({ classId, kind: "card", subjectId: c.id ?? "", title: shownName || "", chip: d });
    };
  } else {
    fb.remove();
  }
  return d;
}

// --- per-card feedback overlay ------------------------------------------------------------------

// The generator's canonical categories (btsgen.contract), labelled by app.feedback.cat.<value>. Order =
// display order.
const FB_CATEGORIES = ["great", "overpowered", "underpowered", "off_theme", "confusing", "doesnt_work"]
  .map((value) => ({ value, get label() { return rT("app.feedback.cat." + value); } }));

// What the popout rates. `kind` is "card" for deck cards, or "orb"/"status"/"summon"/"relic" for the
// non-card elements; `subjectId` is the card id (cards) or the element name (elements).
let fbState = { classId: null, kind: "card", subjectId: "", chip: null, category: null };

// app.feedback.title_<kind>
const FB_TITLE_KINDS = ["card", "relic", "orb", "status", "summon", "potion"];

// The 💬 button on every chip (title + aria-label: app.result.feedback_tip).
function fbButtonHtml() {
  const tip = esc(rT("app.result.feedback_tip"));
  return `<button class="cc-fb" title="${tip}" aria-label="${tip}">💬</button>`;
}

// Open the shared feedback popout. `detailHtml` (elements only) shows a description + effect lines so the
// player can actually evaluate a mechanic that carries no card text.
function openFeedback({ classId, kind, subjectId, title, detailHtml, chip }) {
  fbState = { classId, kind, subjectId: subjectId ?? "", chip, category: null };
  el("fb-title").textContent = rLabel("app.feedback.title_", FB_TITLE_KINDS, kind) || rT("app.feedback.title_fallback");
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
    if (!r.ok) throw new Error(BTS_I18N.err(d, rT("common.http_error", { status: r.status })));
    if (fbState.chip) {
      fbState.chip.classList.add("rated");
      const fb = fbState.chip.querySelector(".cc-fb");
      if (fb) {
        fb.textContent = "✓";
        const label = (FB_CATEGORIES.find((c) => c.value === fbState.category) || {}).label;
        fb.title = label ? rT("app.feedback.rated_tip", { label }) : rT("app.feedback.sent_tip");
      }
    }
    closeFeedback();
    toast(rT("app.feedback.toast_thanks"));
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
  vigor: "Vigor", double_damage: "Double Damage", // Phase BF (v60, gap #54)
  temp_strength_down: "Strength Down (this turn)", strength_down: "Strength (permanent loss)", doom: "Doom", // Phase BL (v64)
  // Phase BM (v65, gaps #68/#69): the self statuses (their phrases are BM_PHRASES below)
  no_draw: "No Draw", no_energy_gain: "No Energy Gain", no_block_gain: "No Block", dex_decay: "Wraith Form",
  focus_decay: "Biased Cognition", lose_strength: "Strength", lose_dexterity: "Dexterity", lose_focus: "Focus",
  echo_form: "Echo Form",
  loop: "Loop", // Phase BQ (v68, gap #78)
};
// Phase BM (v65, gaps #68/#69): the self-drawbacks + Echo Form read like the card text (lockstep with cardgen._BM_SENTENCES).
const BM_PHRASES = {
  no_draw: () => "You cannot draw additional cards this turn",
  no_energy_gain: () => "You cannot gain energy this turn",
  no_block_gain: (a) => `You cannot gain Block from cards for ${a ?? ""} turns`,
  dex_decay: (a) => `At the start of your turn, lose ${a ?? ""} Dexterity`,
  focus_decay: (a) => `At the start of your turn, lose ${a ?? ""} Focus`,
  lose_strength: (a) => `Lose ${a ?? ""} Strength`,
  lose_dexterity: (a) => `Lose ${a ?? ""} Dexterity`,
  lose_focus: (a) => `Lose ${a ?? ""} Focus`,
  echo_form: () => "The first card you play each turn is played twice",
  loop: () => "At the start of your turn, trigger your next orb's passive", // Phase BQ (v68, gap #78): the base Loop
};
const TRIGGER_PREFIX = {
  turn_start: "At the start of each turn", turn_end: "At the end of each turn",
  ripen: "After it ripens in hand", on_hp_lost: "Whenever you lose HP",
  on_poison_damage: "Whenever an enemy takes Poison damage", // Phase BE (v59, gap #56)
  on_shuffle: "Whenever you shuffle your draw pile", // Phase BO (v66, gap #74)
  // Phase BP (v67, gap #77): Arsenal / Sleight of Flesh / the orb evoke
  on_card_generated: "Whenever you create a card", on_debuff_applied: "Whenever you apply a debuff",
  on_evoke: "Whenever you Evoke an orb",
};
// Phase BI (v61, gap #62): the card-trigger filters read exactly like the card text (cardgen._trigger_head /
// ForgedCards.TriggerSentence): "Whenever you play an Attack", "Every 3rd time you play an Attack",
// "Every 5th card you play", "This turn, whenever you play an Attack".
const REACTIVE_HEAD = {
  on_hp_lost: "Whenever you lose HP", on_exhaust: "Whenever a card is Exhausted",
  on_card_played: "Whenever you play a card", on_card_drawn: "Whenever you draw a card",
  on_damage_dealt: "Whenever you deal damage", on_block_gained: "Whenever you gain Block",
  attacked: "Whenever you are attacked", on_blade_played: "Whenever you play your blade",
  on_poison_damage: "Whenever an enemy takes Poison damage",
  on_shuffle: "Whenever you shuffle your draw pile", // Phase BO (v66, gap #74)
  on_card_generated: "Whenever you create a card", on_debuff_applied: "Whenever you apply a debuff", // Phase BP (v67)
  on_evoke: "Whenever you Evoke an orb",
};
const TRIGGER_KIND_WORDS = { attack: "an Attack", skill: "a Skill", power: "a Power", non_attack: "a non-Attack card", status: "a Status" };
// Phase BP (v67, gap #76): "Costs 1 less this turn for each Skill you play" / "After you play this, it costs 0 for the
// rest of combat" / "Whenever you draw this, it costs 1 less this combat" / "Costs 1 more each time you play it".
function costDeltaPhrase(e) {
  if (e.set_zero) return "After you play this, it costs 0 for the rest of combat";
  const amt = Number(e.amount ?? -1);
  if (amt > 0) return `Costs ${amt} more each time you play it`;
  const n = Math.max(1, -amt);
  const life = e.scope === "combat" ? "this combat" : "this turn";
  if (e.on === "played") return `Costs ${n} less ${life} each time you play it`;
  if (e.on === "drawn") return `Whenever you draw this, it costs ${n} less ${life}`;
  const noun = { attack_played: "Attack", skill_played: "Skill" }[e.on] || "card";
  return `Costs ${n} less ${life} for each ${noun} you ${e.on === "card_exhausted" ? "Exhaust" : "play"}`;
}
function trigHead(e) {
  const n = e.every_n > 1 ? e.every_n : 0;
  // Phase BP (v67, gap #77): the Vicious status filter — "Whenever you apply Vulnerable"
  const debuffHead = e.trigger === "on_debuff_applied" && e.status ? `Whenever you apply ${statusName(e.status)}` : null;
  if (!e.card_type && !n && e.scope !== "this_turn") return debuffHead || TRIGGER_PREFIX[e.trigger] || "Each turn";
  const typed = e.card_type && (e.trigger === "on_card_played" || e.trigger === "on_card_drawn");
  let when = typed ? `Whenever you ${e.trigger === "on_card_drawn" ? "draw" : "play"} ${TRIGGER_KIND_WORDS[e.card_type] || "a card"}`
                   : (debuffHead || REACTIVE_HEAD[e.trigger] || TRIGGER_PREFIX[e.trigger] || "Each turn");
  if (n) {
    if (!typed && e.trigger === "on_card_played") when = `Every ${ordinal(n)} card you play`;
    else if (!typed && e.trigger === "on_card_drawn") when = `Every ${ordinal(n)} card you draw`;
    else if (when.startsWith("Whenever ")) when = `Every ${ordinal(n)} time ${when.slice(9)}`;
  }
  return e.scope === "this_turn" ? `This turn, ${when[0].toLowerCase()}${when.slice(1)}` : when;
}
const SCALE_SUFFIX = {
  cards_in_hand: " per card in hand", cards_retained: " per card retained",
  unspent_energy_last_turn: " per unspent energy",
  forged: " plus your Forge", // Phase M (gap #36): the additive Forge payoff
};
// Phase BJ (v62, gap #63): the combat-history reads print the describe noun ("Deal damage equal to …"), lockstep
// with cardgen._scale_phrase / ForgedCards.ScalePhrase.
const SCALE_NOUN = {
  exhaust_pile_size: "the cards in your exhaust pile",
  discard_pile_size: "the cards in your discard pile",
  discards_this_turn: "the cards you have discarded this turn",
  cards_drawn_this_turn: "the cards you have drawn this turn",
  cards_drawn_this_combat: "the cards you have drawn this combat",
  energy_spent_this_turn: "the energy you have spent this turn",
  hp_loss_events_this_combat: "the times you have lost HP this combat",
  cards_generated_this_combat: "the cards you have created this combat",
  total_enemy_poison: "the total Poison on ALL enemies",
  // Phase BQ (v68, gap #78): the orb reads (Compile Driver), lockstep with cardgen._scale_phrase
  orb_count: "the orbs you have channeled",
  orb_types: "the different orbs you have channeled",
  cards_removed: "the cards removed", // Phase BR (v70, gap #79): what an earlier discard / exhaust_card removed
};
const scaleNoun = (e) => e.scale === "target_status_stacks" ? `the enemy's ${statusName(e.status)}` : SCALE_NOUN[e.scale];
// Phase BK (v63, gap #65): the singular noun a `hits_scale` damage counts — lockstep with cardgen._HITS_PHRASE /
// ForgedCards.HitsPhrase ("Deal 6 damage for each Attack you played this turn"; `x` reads "X times").
const HITS_NOUN = {
  attacks_played_this_turn: "Attack you played this turn",
  cards_in_hand: "other card in your hand",
  skills_in_hand: "Skill in your hand",
  plays_this_combat: "card you have played this combat",
  exhaust_pile_size: "card in your exhaust pile",
  hp_loss_events_this_combat: "time you have lost HP this combat",
  energy_spent_this_turn: "energy you have spent this turn",
  orb_count: "orb you have channeled",
  cards_removed: "card removed", // Phase BR (v70, gap #79): Fiend Fire ("for each card Exhausted" in the card text)
};
const titleCase = (s) => String(s || "").replace(/_/g, " ").replace(/\b\w/g, (m) => m.toUpperCase());
const statusName = (s) => STATUS_NAMES[s] || titleCase(s);

function condCore(c) {
  const v = c.value;
  switch (c.kind) {
    case "orb_count_ge": return c.orb ? `you have ${v ?? "enough"}+ ${titleCase(c.orb)} orbs` // Phase BQ (v68): the orb filter
                                      : `you have ${v ?? "enough"}+ orbs`;
    case "orbs_match": return "your channeled orbs match";
    case "target_has_status": return `the enemy has ${statusName(c.status)}`;
    case "no_block": return "you have no Block";
    case "has_block": return "you have Block";
    case "hp_below_half": return "you're below half HP";
    case "enemy_count_ge": return `there are ${v ?? "enough"}+ enemies`;
    case "turn_at_least": return `it's turn ${v ?? "?"}+`;
    case "turn_at_most": return `it's turn ${v ?? "?"} or earlier`; // Phase BB (v56, gap #59)
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
    // Phase BJ (v62, gap #64): lockstep with cardgen.cond_phrase / Conditions.Phrase.
    case "exhausted_this_turn": return "you have Exhausted a card this turn";
    case "played_cards_last_turn_ge": return `you played ${v ?? "enough"}+ cards last turn`;
    case "target_intends_attack": return "the enemy intends to attack";
    case "target_killed": return "this kills the enemy"; // Phase BN (v69, gap #71): Feed / Sunder (cardgen.cond_phrase)
    default: return titleCase(c.kind);
  }
}
const condText = (c) => ` (${c.negate ? "unless" : "if"} ${condCore(c)})`;

// Phase BN (v69, gaps #72/#73): the noun a random-generation / auto-play filter names (cardgen._RANDOM_NOUNS).
function randomNoun(kind, plural) {
  const [one, many] = { attack: ["Attack", "Attacks"], skill: ["Skill", "Skills"], power: ["Power", "Powers"],
                        non_attack: ["non-Attack card", "non-Attack cards"] }[kind] || ["card", "cards"];
  return plural ? many : one;
}

function effPhrase(e, target) {
  const a = e.amount;
  const scale = (e.scale && e.scale !== "x") ? (SCALE_SUFFIX[e.scale] || "") : "";
  const hits = e.hits > 1 ? ` ×${e.hits}` : "";
  const toAll = target === "all_enemies" ? " to all enemies" : "";
  const noun = scaleNoun(e); // Phase BJ (v62)
  if (e.op === "damage" && e.hits_scale) { // Phase BK (v63): the hit count is a live read
    const per = e.hits_scale === "x" ? "X times" : `for each ${HITS_NOUN[e.hits_scale] || titleCase(e.hits_scale)}`;
    return `Deal ${a ?? ""} damage ${per}${toAll}${e.unblockable === true ? " (ignores Block)" : ""}`;
  }
  if (noun && e.op === "damage") return `Deal damage equal to ${noun}${toAll}${e.unblockable === true ? " (ignores Block)" : ""}`;
  if (noun && e.op === "block") return `Gain Block equal to ${noun}`;
  switch (e.op) {
    case "damage": return `Deal ${a ?? ""} damage${scale}${toAll}${hits}${e.unblockable === true ? " (ignores Block)" : ""}${e.grow_held ? ` (+${e.grow_held} per turn held)` : ""}${e.grow ? ` (grows by ${e.grow})` : ""}`; // Phase AN (v44) / BD (v58) / BR (v70): grow (Rampage, Rolling Boulder)
    case "block": return `Gain ${a ?? ""} Block${scale}${e.grow_held ? ` (+${e.grow_held} per turn held)` : ""}`; // Phase BD (v58)
    case "held_discount": return `Costs ${a ?? 1} less for each turn it is retained`; // Phase BD (v58, gap #58)
    case "cost_delta": return costDeltaPhrase(e); // Phase BP (v67, gap #76): lockstep with cardgen._cost_delta_sentence
    case "draw": return e.scale === "to_hand_size" ? `Draw cards until you have ${a ?? "?"} in hand` // Phase BJ (v62): Expertise
                                                   : `Draw ${a ?? 1} card${(a ?? 1) == 1 ? "" : "s"}${scale}`;
    case "gain_energy": return e.scale === "energy" ? "Double your energy" : `Gain ${a ?? 1} energy`; // Phase BJ (v62)
    case "lose_hp": return `Lose ${a ?? ""} HP`;
    case "gain_max_hp": return `Gain ${a ?? ""} Max HP`; // Phase AN (v44)
    case "cost_shift": { // Phase AO (v45)
      const kind = { attack: "Attacks", skill: "Skills", power: "Powers" }[e.card_type] || "cards";
      const life = e.scope === "combat" ? "this combat" : "this turn";
      return e.count ? `Your next ${e.count > 1 ? e.count + " " : ""}${kind} cost ${a ?? 1} less ${life}` : `Your ${kind} cost ${a ?? 1} less ${life}`;
    }
    case "heal": return `Heal ${a ?? ""}`;
    case "discard": return e.cards === "all" ? "Discard your hand" // Phase BR (v70, gap #79)
                         : `Discard ${a ?? 1} ${e.cards === "choose" ? "chosen" : "random"} card${(a ?? 1) == 1 ? "" : "s"}`; // Phase AP (v46)
    case "stun": return "Stun the enemy"; // Phase BR (v70, gap #11): Whistle, lockstep with cardgen.describe
    case "retrieve_card": { // Phase AP (v46); Phase BO (v66): + the draw-pile tutor and the card_type filter
      const n = a ?? 1;
      const what = { attack: "Attack", skill: "Skill", power: "Power", non_attack: "non-Attack card" }[e.card_type] || "card";
      if (e.pile === "draw")
        return `Put ${n} ${e.cards === "choose" ? "" : "random "}${what}${n == 1 ? "" : "s"} from your draw pile into your hand`;
      const pile = e.pile === "exhaust" ? "exhaust" : "discard";
      return e.cards === "choose" ? `Return ${n} chosen ${what}${n == 1 ? "" : "s"} from your ${pile} pile to hand`
                                  : `Return ${n} random ${what}${n == 1 ? "" : "s"} from your ${pile} pile to hand`;
    }
    case "exhaust_card": { // Phase BC (v57, gap #52)
      const what = { attack: "Attack", skill: "Skill", power: "Power", non_attack: "non-Attack card" }[e.card_type] || "card";
      const n = a ?? 1;
      const where = e.pile === "draw" ? "draw pile" : "hand"; // Phase BO (v66): + the draw pile
      if (e.cards === "all" && !e.card_type && e.pile !== "draw") return "Exhaust your hand"; // Phase BR (v70, gap #79)
      if (e.cards === "all") return `Exhaust all ${what}s in your ${where}`;
      if (e.cards === "up_to") return `Exhaust up to ${n} ${what}${n == 1 ? "" : "s"} in your ${where}`;
      return `Exhaust ${n} ${e.cards === "random" ? "random " : ""}${what}${n == 1 ? "" : "s"} in your ${where}`;
    }
    case "draw_until": return `Draw cards until you draw ${{ attack: "an Attack", skill: "a Skill", power: "a Power" }[e.card_type] || "a non-Attack card"}`; // Phase BC (v57, gap #53)
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
    case "strip_block": return "Remove all of the enemy's Block"; // Phase BL (v64, gap #66): Expose, lockstep with cardgen.describe
    case "strip_artifact": return "Remove the enemy's Artifact"; // Phase BL (v64, gap #66)
    case "replay_next": { // Phase BM (v65, gap #69): lockstep with cardgen._replay_next_sentence
      const kind = e.card_type || "skill";
      const single = { attack: "Attack", power: "Power", all: "card" }[kind] || "Skill";
      const n = Math.max(1, e.count || 1);
      const what = n > 1 ? `your next ${n} ${single}s are` : `your next ${single} is`;
      return kind === "power" ? `${what[0].toUpperCase()}${what.slice(1)} played twice` : `This turn, ${what} played twice`;
    }
    case "block_next_turn": // Phase BM (v65, gap #70): Prolong
      return e.scale === "block" ? "Next turn, gain Block equal to your current Block" : `Next turn, gain ${a ?? ""} Block`;
    case "retain_hand": return "Retain your hand this turn"; // Phase BM (v65, gap #70): Equilibrium
    // Phase BO (v66, gaps #74/#75): lockstep with cardgen.describe.
    case "return_to_hand": return "Returns to your hand after you play it";
    case "to_draw_top": return "Goes on top of your draw pile after you play it";
    case "return_next_turn": return "At the start of your next turn, return this to your hand";
    case "put_back": return e.from === "discard" ? "Put a card from your discard pile on top of your draw pile"
                                                 : "Put a card from your hand on top of your draw pile";
    case "shuffle_hand": return "Shuffle your hand and discard pile into your draw pile";
    case "grant_keyword": {
      const one = { attack: "an Attack", skill: "a Skill", power: "a Power", non_attack: "a non-Attack card" }[e.card_type] || "a card";
      const gains = { sly: "is Sly this turn", ethereal: "gains Ethereal" }[e.keyword] || "gains Retain";
      return `Choose ${one} in your hand. It ${gains}`;
    }
    case "exhaust": return "Exhaust";
    case "innate": return "Innate";
    case "retain": return "Retain";
    case "ethereal": return "Ethereal";
    case "sly": return "Sly"; // Phase BB (v56, gap #55): discarded from hand by an effect = played for free
    case "evoke": // Phase BQ (v68, gap #78): Dualcast (keep) / the newest orb, lockstep with cardgen.describe
      if (e.keep) return "Evoke your next orb twice";
      if (e.which === "newest") return a > 1 ? `Evoke your ${a} newest orbs` : "Evoke your newest orb";
      return "Evoke your next orb";
    case "channel_orb": return e.per_enemy ? `Channel ${titleCase(e.orb || "an orb")} for each enemy` // Phase BQ (v68): Chill
                                           : `Channel ${titleCase(e.orb || "an orb")}${a > 1 ? ` ×${a}` : ""}`;
    case "trigger_passive": { // Phase BQ (v68, gap #78): Darkness / Tesla Coil, lockstep with cardgen._trigger_passive_sentence
      const whose = e.orbs === "all" ? "all your orbs" : "your next orb";
      return (a ?? 1) > 1 ? `Trigger the passive of ${whose} ${a} times` : `Trigger the passive of ${whose}`;
    }
    case "lose_orb_slot": return "Lose 1 Orb Slot"; // Phase BQ (v68, gap #78): Bulk Up
    // Phase BN (v69, gaps #72/#73): lockstep with cardgen._add_random_card_sentence / _autoplay_sentence.
    case "add_random_card": {
      const pile = { discard: "discard pile", draw: "draw pile" }[e.pile] || "hand";
      const n = Math.max(1, a ?? 1);
      const choose = (e.choose_of ?? 0) > 1;
      const txt = choose ? `Choose 1 of ${e.choose_of} random ${randomNoun(e.card_type, true)} to add to your ${pile}`
                : n > 1 ? `Add ${n} random ${randomNoun(e.card_type, true)} to your ${pile}`
                : `Add a random ${randomNoun(e.card_type, false)} to your ${pile}`;
      return txt + (e.free_this_turn ? (!choose && n > 1 ? ". They cost 0 this turn" : ". It costs 0 this turn") : "");
    }
    case "autoplay": {
      const n = Math.max(1, a ?? 1);
      if (e.from === "draw_random")
        return n > 1 ? `Play ${n} random ${randomNoun(e.card_type, true)} from your draw pile`
                     : `Play a random ${randomNoun(e.card_type, false)} from your draw pile`;
      return n > 1 ? `Play the top ${n} cards of your draw pile and Exhaust them` : "Play the top card of your draw pile and Exhaust it";
    }
    case "apply_status":
      // Phase BL (v64, gaps #66/#67): the permanent Strength loss + Blight Strike's Doom read like the card text.
      if (e.status === "strength_down")
        return target === "all_enemies" ? `ALL enemies lose ${a ?? ""} Strength`
             : target === "random_enemy" ? `A random enemy loses ${a ?? ""} Strength` : `The enemy loses ${a ?? ""} Strength`;
      if (e.status === "doom" && e.scale === "damage_dealt_unblocked") return "Apply Doom equal to the unblocked damage dealt";
      if (BM_PHRASES[e.status]) return BM_PHRASES[e.status](a); // Phase BM (v65)
      return target === "self" ? `Gain ${a ?? ""} ${statusName(e.status)}`
                               : `Apply ${a ?? ""} ${statusName(e.status)}${toAll}`;
    case "apply_status_custom": return `Apply ${a ?? ""} ${e.status_name || "status"}`;
    case "summon": return `Summon ${e.summon_name || "a minion"}${a ? ` (${a} HP)` : ""}`;
    case "summon_attack": return `Minion attacks for ${a ?? ""}${hits}`;
    case "buff_summon": return `Give your minion +${a ?? ""} ${statusName(e.status)}`;
    case "sacrifice_summon": return "Sacrifice your minion"; // Phase AV (v52): consume it (its on_death rattle fires)
    case "add_trigger":
      return `${trigHead(e)}: ` // Phase BI (v61): the filtered heads + "to a random enemy"
             + (e.effects || []).map((x) => effPhrase(x, "self") + (x.target === "random_enemy" ? " to a random enemy"
                                                                   : x.target === "that_enemy" ? " to that enemy" : "")).join(", "); // Phase BP (v67)
    default: return a != null ? `${titleCase(e.op)} ${a}` : titleCase(e.op);
  }
}

function fmtEffect(e, target) {
  const base = effPhrase(e, target).replace(/\s+/g, " ").trim();
  return base + (e.when && e.when.kind ? condText(e.when) : "");
}


// --- helpers -------------------------------------------------------------------------------------

async function copy(text) {
  try { await navigator.clipboard.writeText(text); toast(rT("common.toast.copied")); }
  catch (_) { toast(rT("common.toast.copy_failed")); }
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


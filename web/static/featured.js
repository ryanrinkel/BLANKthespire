"use strict";
// featured.js — the tile for one class from The Archive (/api/featured), shared by the landing strip
// (landing.js, which ties hover/focus to its split-flap board through the optional hooks) and the
// /archive page (archive.js). Plain globals, no module: both pages load this file before their own, and
// both await BTS_I18N.ready before they build a tile (the tile strings come from i18n.js).

const FEATURED_DESC_MAX = 110;

// Cut text to ~max characters at a word boundary, with an ellipsis.
function clip(text, max) {
  text = (text || "").trim();
  if (text.length <= max) return text;
  const cut = text.slice(0, max);
  const sp = cut.lastIndexOf(" ");
  return (sp > max * 0.6 ? cut.slice(0, sp) : cut).replace(/[\s,;:.—-]+$/, "") + "…";
}

function featuredPlaceholder(word) {
  const ph = document.createElement("div");
  ph.className = "featured-art featured-ph";
  ph.setAttribute("aria-hidden", "true");
  ph.textContent = word;
  return ph;
}

// One tile: splash art (or the word on a blank board tile), "<WORD> the spire", name, a clipped description
// and the card count, linking to the class's /deck page. `hooks.onHold(kind, word)` / `hooks.onRelease(kind)`
// (kind = "pointer" | "focus") are optional: the landing board uses them; /archive passes none.
function featuredTile(item, hooks) {
  hooks = hooks || {};
  const word = String(item.word || "").toUpperCase();
  // a class forged in the site's language shows its translated name/description (bundle `loc`, I18N plan C2)
  const name = BTS_I18N.locField(item, "character", null, "name", item.name || item.blurb || word);
  const a = document.createElement("a");
  a.className = "featured-tile";
  a.href = item.share_url;

  if (item.splash_thumb_url) {
    const img = document.createElement("img");
    img.className = "featured-art";
    img.src = item.splash_thumb_url;
    img.alt = BTS_I18N.t("archive.tile.splash_alt", { name });
    img.loading = "lazy";
    img.decoding = "async";
    img.width = 320;
    img.height = 180;
    img.addEventListener("error", () => img.replaceWith(featuredPlaceholder(word)), { once: true });
    a.appendChild(img);
  } else {
    a.appendChild(featuredPlaceholder(word));
  }

  const body = document.createElement("div");
  body.className = "featured-body";
  const cap = document.createElement("p");
  cap.className = "featured-cap";
  const w = document.createElement("span");
  w.className = "featured-word";
  w.textContent = word;
  // archive.tile.caption "{word} the Spire": the word keeps its own span wherever the language puts it
  const capParts = BTS_I18N.t("archive.tile.caption").split("{word}");
  cap.append(capParts[0], w, capParts.slice(1).join(""));
  const h = document.createElement("h3");
  h.className = "featured-name";
  h.textContent = name;
  body.append(cap, h);
  const desc = clip(BTS_I18N.locField(item, "character", null, "description", item.description), FEATURED_DESC_MAX);
  if (desc) {
    const p = document.createElement("p");
    p.className = "featured-desc";
    p.textContent = desc;
    body.appendChild(p);
  }
  if (item.card_count) {
    const n = document.createElement("p");
    n.className = "featured-meta";
    n.textContent = BTS_I18N.t("archive.tile.cards", { count: item.card_count });
    body.appendChild(n);
  }
  a.appendChild(body);

  // Board tie-in (landing only): only 5-letter A-Z words fit the five tiles.
  if (/^[A-Z]{5}$/.test(word) && typeof hooks.onHold === "function" && typeof hooks.onRelease === "function") {
    a.addEventListener("pointerenter", () => hooks.onHold("pointer", word));
    a.addEventListener("pointerleave", () => hooks.onRelease("pointer"));
    a.addEventListener("focus", () => hooks.onHold("focus", word));
    a.addEventListener("blur", () => hooks.onRelease("focus"));
  }
  return a;
}

// Fetch The Archive (optionally the newest `limit`) and keep only rows a tile can link. [] on any failure.
async function fetchArchive(limit) {
  try {
    const r = await fetch("/api/featured" + (limit ? "?limit=" + encodeURIComponent(limit) : ""));
    if (!r.ok) return [];
    const items = ((await r.json()) || {}).featured || [];
    return items.filter((it) => it && it.share_url && it.word);
  } catch (_) {
    return [];
  }
}

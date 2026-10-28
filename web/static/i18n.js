/* Site language (docs/plans/I18N_PLAN.md, "A. Website" + "B. Forge console").
 *
 * Loaded FIRST on every page (plain script: the CSP forbids inline scripts). Strings come from
 * /static/i18n/<lang>.json, built from docs/copy/COPY*.md by web/tools/build_i18n.py:
 *   {"lang": "zh", "strings": {"key": "html with {placeholders}"}, "console": {"console.x": {"re", "text"}}}
 * Every `strings` value is HTML: literal < > & are escaped and COPY.md's inline markup is already <strong>,
 * <em>, <a>, <code>; paragraphs are separated by "\n\n".
 *
 * English pages never change: the HTML carries its English text, and when the language is "en" nothing in
 * the DOM is rewritten (only the EN | 中文 toggle is added to the header). en.json is still fetched in
 * English, because the strings page scripts build at runtime come from it through t().
 *
 * Markup conventions (static HTML):
 *   data-i18n="key"          textContent = the string (entities decoded). {name} placeholders are filled
 *                            from data-i18n-var-name="value" attributes on the element.
 *   data-i18n-html="key"     innerHTML = the string. Paragraphs ("\n\n") become <p>…</p> when the element
 *                            already holds <p> children, else they are joined with <br><br>.
 *                            {name} placeholders are filled from a descendant data-i18n-slot="name" (the
 *                            ORIGINAL node is moved into the new markup, so scripts holding a reference to
 *                            it keep working) or from a data-i18n-var-name="value" attribute on the element.
 *   data-i18n-attr="placeholder:key,title:key2,aria-label:key3"   attribute values
 *   <title data-i18n-page="help.meta.title">   document.title = common.title_suffix with {page}
 *
 * API: window.BTS_I18N = {lang, languages, ready, t, html, has, err, set, apply, console}
 *   t(key, vars)     plain text (for textContent, attributes, alert()); vars are inserted as is.
 *                    Plurals: pass the BASE key and vars.count; picks key.one when count === 1, else
 *                    key.other (key.other when .one is absent). Missing key -> English -> the key itself.
 *   html(key, vars)  HTML (for innerHTML); vars are HTML-escaped before they are inserted.
 *   has(key)         true when the key (or its .other plural) exists in the loaded strings or English.
 *   err(data, fallback)  text for a server JSON error: t("server." + data.code) when the server sent a
 *                    code that has a string, else data.error, else fallback.
 *   ready            Promise, resolves once the json is loaded and (non-English) the DOM is translated.
 *                    Page scripts await it before building any string with t().
 *   console(line)    forge-console line, translated by the first matching console.* rule (stage headers
 *                    only); returned unchanged in English or when nothing matches.
 */
(function () {
  "use strict";

  var VERSION = "20261028a";  // cache-buster for the json files; bump with the page ?v= stamps
  var STORE_KEY = "bts.lang";
  var LANGUAGES = [{ code: "en", label: "EN" }, { code: "zh", label: "中文" }];
  // Browser-language auto-select (navigator.language "zh*" -> zh) is implemented but OFF for this release:
  // the Chinese strings are a machine draft no native speaker has reviewed yet, so nobody gets them without
  // choosing them (toggle or ?lang=zh). Flip to true after the review (I18N_PLAN.md phase 4).
  var AUTO_DETECT = false;

  function known(code) {
    for (var i = 0; i < LANGUAGES.length; i++) if (LANGUAGES[i].code === code) return true;
    return false;
  }
  function readStore() {
    try { return window.localStorage.getItem(STORE_KEY); } catch (e) { return null; }
  }
  function writeStore(code) {
    try { window.localStorage.setItem(STORE_KEY, code); } catch (e) { /* private mode: this page only */ }
  }

  function resolveLang() {
    var q = null;
    try { q = new URLSearchParams(window.location.search).get("lang"); } catch (e) { q = null; }
    if (q) q = String(q).toLowerCase();
    if (q && known(q)) { writeStore(q); return q; }
    var stored = readStore();
    if (stored && known(stored)) return stored;
    if (AUTO_DETECT) {
      var nav = String((window.navigator && window.navigator.language) || "").toLowerCase();
      if (nav.indexOf("zh") === 0) return "zh";
    }
    return "en";
  }

  var lang = resolveLang();
  var strings = {};   // the active language
  var english = {};   // en.json, the per-key fallback
  var rules = null;   // compiled console rules, built on first use
  var consoleDoc = {};

  function own(obj, key) { return Object.prototype.hasOwnProperty.call(obj, key); }

  function rawOf(dict, key, vars) {
    var hasCount = vars && vars.count !== undefined && vars.count !== null;
    if (hasCount) {
      var one = key + ".one", other = key + ".other";
      if (Number(vars.count) === 1 && own(dict, one)) return dict[one];
      if (own(dict, other)) return dict[other];
      if (own(dict, one)) return dict[one];
    }
    if (own(dict, key)) return dict[key];
    return null;
  }
  function lookup(key, vars) {
    var s = rawOf(strings, key, vars);
    if (s === null) s = rawOf(english, key, vars);
    return s;
  }

  function escapeHtml(v) {
    return String(v).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
  function decode(s) {
    // the build escapes only & < > (and " inside hrefs); a value with tags stays HTML
    if (/<[a-z\/]/i.test(s)) return s;
    return s.replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"')
      .replace(/&#39;/g, "'").replace(/&amp;/g, "&");
  }
  function fill(s, vars, esc) {
    if (!vars) return s;
    return s.replace(/\{([A-Za-z_][A-Za-z0-9_]*)\}/g, function (m, name) {
      if (!own(vars, name) || vars[name] === undefined || vars[name] === null) return m;
      return esc ? escapeHtml(vars[name]) : String(vars[name]);
    });
  }

  function t(key, vars) {
    var s = lookup(key, vars);
    if (s === null) return key;
    return fill(decode(s), vars, false);
  }
  function html(key, vars) {
    var s = lookup(key, vars);
    if (s === null) return escapeHtml(key);
    return fill(s, vars, true);
  }
  function has(key) {
    return lookup(key, null) !== null || lookup(key, { count: 2 }) !== null;
  }
  function err(data, fallback) {
    if (data && data.code && has("server." + data.code)) return t("server." + data.code, data.vars || null);
    if (data && data.error) return String(data.error);
    return fallback === undefined ? "" : fallback;
  }

  // ------------------------------------------------------------------------------------------ console

  function compileRules() {
    rules = [];
    var keys = Object.keys(consoleDoc || {});
    for (var i = 0; i < keys.length; i++) {
      var entry = consoleDoc[keys[i]];
      if (!entry || !entry.re || typeof entry.text !== "string") continue;
      try { rules.push({ re: new RegExp(entry.re), text: entry.text }); } catch (e) { /* skip a bad rule */ }
    }
  }
  function localizeConsole(line) {
    if (lang === "en" || typeof line !== "string") return line;
    if (rules === null) compileRules();
    for (var i = 0; i < rules.length; i++) {
      var m = rules[i].re.exec(line);
      if (!m) continue;
      var groups = m.groups || {};
      return rules[i].text.replace(/\{([A-Za-z_][A-Za-z0-9_]*)\}/g, function (all, name) {
        return own(groups, name) && groups[name] !== undefined ? groups[name] : all;
      });
    }
    return line;
  }

  // ---------------------------------------------------------------------------------------------- DOM

  function paragraphs(value, host) {
    if (value.indexOf("\n\n") < 0) return value;
    var parts = value.split("\n\n");
    var hasP = false;
    for (var i = 0; i < host.children.length; i++) {
      if (host.children[i].tagName === "P") { hasP = true; break; }
    }
    if (hasP) return "<p>" + parts.join("</p><p>") + "</p>";
    return parts.join("<br><br>");
  }

  function applyHtml(el, key) {
    var raw = lookup(key, null);
    if (raw === null) return;
    var slots = {};
    var slotNodes = el.querySelectorAll("[data-i18n-slot]");
    for (var i = 0; i < slotNodes.length; i++) slots[slotNodes[i].getAttribute("data-i18n-slot")] = slotNodes[i];
    var value = paragraphs(raw, el).replace(/\{([A-Za-z_][A-Za-z0-9_]*)\}/g, function (m, name) {
      if (own(slots, name)) return '<span data-i18n-mark="' + name + '"></span>';
      var attr = el.getAttribute("data-i18n-var-" + name);
      return attr === null ? m : escapeHtml(attr);
    });
    // the json's links carry only href: keep the English link's other attributes (class, target, rel, id)
    var oldLinks = {};
    var olds = el.querySelectorAll("a[href]");
    for (var k = 0; k < olds.length; k++) {
      if (!own(oldLinks, olds[k].getAttribute("href"))) oldLinks[olds[k].getAttribute("href")] = olds[k];
    }
    el.innerHTML = value;
    var news = el.querySelectorAll("a[href]");
    for (var n = 0; n < news.length; n++) {
      var src = oldLinks[news[n].getAttribute("href")];
      if (!src) continue;
      for (var q = 0; q < src.attributes.length; q++) {
        if (!news[n].hasAttribute(src.attributes[q].name)) news[n].setAttribute(src.attributes[q].name, src.attributes[q].value);
      }
    }
    var marks = el.querySelectorAll("[data-i18n-mark]");
    for (var j = 0; j < marks.length; j++) {
      var name = marks[j].getAttribute("data-i18n-mark");
      var node = slots[name];
      if (node) { marks[j].parentNode.replaceChild(node, marks[j]); delete slots[name]; }
      else marks[j].parentNode.removeChild(marks[j]);
    }
  }

  function varsOf(el) {
    var vars = {};
    for (var i = 0; i < el.attributes.length; i++) {
      var a = el.attributes[i].name;
      if (a.indexOf("data-i18n-var-") === 0) vars[a.slice(14)] = el.attributes[i].value;
    }
    return vars;
  }

  function applyText(el, key) {
    var raw = lookup(key, null);
    if (raw === null) return;
    el.textContent = fill(decode(raw), varsOf(el), false);
  }

  function applyAttrs(el, spec) {
    var pairs = String(spec).split(",");
    for (var i = 0; i < pairs.length; i++) {
      var p = pairs[i].split(":");
      if (p.length < 2) continue;
      var attr = p[0].trim(), key = p.slice(1).join(":").trim();
      if (!attr || !key || lookup(key, null) === null) continue;
      el.setAttribute(attr, t(key, varsOf(el)));
    }
  }

  function each(root, sel, fn) {
    if (root.matches && root.matches(sel)) fn(root);
    var list = root.querySelectorAll(sel);
    for (var i = 0; i < list.length; i++) fn(list[i]);
  }

  function apply(root) {
    if (lang === "en") return;
    root = root || document;
    each(root, "[data-i18n]", function (el) { applyText(el, el.getAttribute("data-i18n")); });
    each(root, "[data-i18n-html]", function (el) { applyHtml(el, el.getAttribute("data-i18n-html")); });
    each(root, "[data-i18n-attr]", function (el) { applyAttrs(el, el.getAttribute("data-i18n-attr")); });
    if (root === document) {
      var title = document.querySelector("title[data-i18n-page]");
      if (title && has(title.getAttribute("data-i18n-page"))) {
        document.title = t("common.title_suffix", { page: t(title.getAttribute("data-i18n-page")) });
      }
    }
  }

  // ------------------------------------------------------------------------------------------- toggle

  function set(code) {
    if (!known(code)) code = "en";
    writeStore(code);
    try {
      var url = new URL(window.location.href);
      url.searchParams.delete("lang");  // a ?lang= left in the URL would override the new choice
      window.location.replace(url.toString());
    } catch (e) {
      window.location.reload();
    }
  }

  function renderToggle() {
    if (document.querySelector("[data-lang-toggle]")) return;
    var box = document.createElement("span");
    box.className = "lang-toggle";
    box.setAttribute("data-lang-toggle", "");
    box.setAttribute("role", "group");
    box.setAttribute("aria-label", "Language / 语言");
    for (var i = 0; i < LANGUAGES.length; i++) {
      if (i > 0) {
        var sep = document.createElement("span");
        sep.className = "lang-sep";
        sep.setAttribute("aria-hidden", "true");
        sep.textContent = "|";
        box.appendChild(sep);
      }
      var code = LANGUAGES[i].code;
      var b = document.createElement("button");
      b.type = "button";
      b.className = "lang-opt" + (code === lang ? " active" : "");
      b.setAttribute("data-lang", code);
      b.setAttribute("lang", code);
      b.setAttribute("aria-pressed", code === lang ? "true" : "false");
      b.textContent = LANGUAGES[i].label;
      b.addEventListener("click", (function (c) {
        return function () { if (c !== lang) set(c); };
      })(code));
      box.appendChild(b);
    }
    var nav = document.querySelector("header nav");
    if (nav) {
      nav.appendChild(box);
    } else {
      // pages without a header (the landing page): a small fixed control in the top-right corner
      box.className += " floating";
      document.body.appendChild(box);
    }
  }

  // --------------------------------------------------------------------------------------------- load

  function fetchJson(code) {
    return fetch("/static/i18n/" + code + ".json?v=" + VERSION, { credentials: "same-origin" })
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .catch(function () { return null; });
  }

  var domReady = new Promise(function (resolve) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", function () { resolve(); });
    } else {
      resolve();
    }
  });

  if (lang !== "en") {
    try { document.documentElement.setAttribute("lang", lang); } catch (e) { /* ignore */ }
  }

  var loads = [fetchJson("en")];
  if (lang !== "en") loads.push(fetchJson(lang));

  var ready = Promise.all(loads).then(function (docs) {
    var enDoc = docs[0];
    english = (enDoc && enDoc.strings) || {};
    if (lang === "en") {
      strings = english;
    } else {
      var doc = docs[1];
      strings = (doc && doc.strings) || {};
      consoleDoc = (doc && doc.console) || {};
    }
    rules = null;
    return domReady;
  }).then(function () {
    try { apply(document); } catch (e) { /* a broken string never breaks the page */ }
    return lang;
  });

  domReady.then(function () { try { renderToggle(); } catch (e) { /* ignore */ } });

  window.BTS_I18N = {
    lang: lang,
    languages: LANGUAGES,
    ready: ready,
    t: t,
    html: html,
    has: has,
    err: err,
    set: set,
    apply: apply,
    console: localizeConsole,
  };
})();

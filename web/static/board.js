/* board.js: the menu of the "departure board" look (board.css). Loaded at the end of the page, deferred.

   A burger button in the top-right corner opens a board-style dropdown.
   - Public pages: Home, Forge a class, The Archive, Get the mod, Help, then the language toggle, then
     Terms · Privacy. The page's own header links (all of which the menu covers) are hidden by board.css.
   - /app (detected by #nav-forge): below 820px the tab strip is hidden and the panel lists the REAL tab
     elements (a row click calls tab.click(), so navigation stays app.js's own); at 820px and up there is no
     burger and the header is unchanged.
   The EN | 中文 toggle stays i18n.js's own, outside the menu (board.css parks it beside the burger): with
   AUTO_DETECT off it is the only way a Chinese reader gets Chinese. Labels come from BTS_I18N.t() with English
   fallbacks; changing the language reloads the page (i18n.js set()), so labels follow on the next load.
   No inline handlers (CSP). */
(function () {
  "use strict";

  var IS_APP = !!document.getElementById("nav-forge");
  var PATH = window.location.pathname.replace(/\/+$/, "") || "/";

  // ------------------------------------------------------------------------- the ?look=board share link
  // A page opened with ?look=board (the server's alias for this look) carries the parameter on to same-origin
  // page links, so the look holds while the visitor browses. Nothing is stored: it lives only in the URLs.
  // Rewritten at the moment of use (pointerdown / focus / click, delegated on the document), so links other
  // scripts add or repoint later (Archive tiles, the CTA landing.js repoints, menu rows) are covered too.
  // Left alone: other origins, hash-only links, mailto/tel, downloads and file URLs, the auth/API hops.
  var LOOK = "board";
  var CARRY = new URLSearchParams(window.location.search).get("look") === LOOK;
  var SKIP_PATH = /^\/(?:api|auth|logout|dev-login|webhook|static|admin)(?:\/|$)|^\/login\/|\.[a-z0-9]{2,5}$/i;
  function withLook(href) {
    if (!CARRY || !href || href.charAt(0) === "#") return href;
    var url;
    try { url = new URL(href, window.location.href); } catch (e) { return href; }
    if (url.origin !== window.location.origin || !/^https?:$/.test(url.protocol)) return href;
    if (SKIP_PATH.test(url.pathname) || url.searchParams.get("look") === LOOK) return href;
    url.searchParams.set("look", LOOK);
    return url.pathname + url.search + url.hash;
  }
  function carry(ev) {
    var a = ev.target && ev.target.closest ? ev.target.closest("a[href]") : null;
    if (!a || a.hasAttribute("download")) return;
    var href = a.getAttribute("href");
    var next = withLook(href);
    if (next !== href) a.setAttribute("href", next);
  }
  if (CARRY) {
    ["pointerdown", "focusin", "click", "auxclick"].forEach(function (type) {
      document.addEventListener(type, carry, true);
    });
  }

  function t(key, english) {
    var I = window.BTS_I18N;
    try {
      if (I && I.has(key)) {
        var s = I.t(key);
        if (s && s !== key) return s;
      }
    } catch (e) { /* fall through */ }
    return english;
  }
  function clean(label) {  // nav keys carry arrows / glyphs ("Get the mod ⬇", "Help ?"); menu rows don't
    return String(label).replace(/[←-⇿⬇?]/g, "").replace(/\s+/g, " ").trim();
  }

  // ------------------------------------------------------------------------------------------------ build
  var wrap = document.createElement("div");
  wrap.className = "board-nav" + (IS_APP ? " is-app" : "");

  var btn = document.createElement("button");
  btn.type = "button";
  btn.className = "board-burger";
  btn.setAttribute("aria-expanded", "false");
  btn.setAttribute("aria-controls", "board-menu");
  btn.setAttribute("aria-label", "Menu");  // no i18n key exists for "Menu"
  var bars = document.createElement("span");
  bars.className = "board-burger-bars";
  bars.setAttribute("aria-hidden", "true");
  for (var i = 0; i < 3; i++) bars.appendChild(document.createElement("i"));
  btn.appendChild(bars);

  var panel = document.createElement("nav");
  panel.id = "board-menu";
  panel.className = "board-menu";
  panel.hidden = true;
  panel.setAttribute("aria-label", "Menu");

  var list = document.createElement("ul");
  list.className = "board-menu-list";
  var legal = document.createElement("div");
  legal.className = "board-menu-legal";
  panel.appendChild(list);
  if (!IS_APP) panel.appendChild(legal);

  wrap.appendChild(btn);
  wrap.appendChild(panel);
  var header = document.querySelector("body > header");
  (header || document.body).appendChild(wrap);
  if (!header) wrap.className += " is-floating";

  // ------------------------------------------------------------------------------------------------- rows
  function row(label, opts) {
    var li = document.createElement("li");
    var el = document.createElement(opts.href ? "a" : "button");
    el.className = "board-menu-item";
    if (opts.href) el.href = opts.href; else el.type = "button";
    el.textContent = label;
    if (opts.current) { el.setAttribute("aria-current", "page"); el.className += " is-current"; }
    el.addEventListener("click", function (ev) {
      if (opts.onClick) { ev.preventDefault(); close(false); opts.onClick(); }
      else if (opts.hrefAtClick) { el.href = opts.hrefAtClick(); close(false); }
      else close(false);
    });
    li.appendChild(el);
    list.appendChild(li);
  }

  function buildPublic() {
    list.textContent = "";
    var home = PATH === "/";
    if (!home) row("Home", { href: "/" });  // no i18n key for a bare "Home" (common.nav.back_home has an arrow)
    row(t("app.meta.title", "Forge a Class"), {
      href: "/app",
      hrefAtClick: function () {  // on the splash landing.js repoints #signin (/login, /app or /dev-login)
        var cta = document.getElementById("signin");
        return withLook(home && cta && cta.getAttribute("href") ? cta.getAttribute("href") : "/app");
      },
    });
    row(clean(t("common.nav.archive", "The Archive")), { href: "/archive", current: PATH === "/archive" });
    row(clean(t("common.footer.get_mod", "Get the mod")), { href: "/download", current: PATH === "/download" });
    row(clean(t("common.nav.help", "Help")), { href: "/help", current: PATH === "/help" });
    legal.textContent = "";
    [["/terms", "common.footer.terms", "Terms"], ["/privacy", "common.footer.privacy", "Privacy"]].forEach(function (l, n) {
      if (n) {
        var dot = document.createElement("span");
        dot.setAttribute("aria-hidden", "true");
        dot.textContent = " · ";
        legal.appendChild(dot);
      }
      var a = document.createElement("a");
      a.href = l[0];
      a.textContent = t(l[1], l[2]);
      if (PATH === l[0]) a.setAttribute("aria-current", "page");
      a.addEventListener("click", function () { close(false); });
      legal.appendChild(a);
    });
  }

  function buildApp() {
    list.textContent = "";
    var tabs = document.querySelectorAll("header nav .tab");
    Array.prototype.forEach.call(tabs, function (tab) {
      var label = clean(tab.textContent);
      if (!label) return;
      var current = tab.classList.contains("active");
      if (tab.tagName === "A") {
        row(label, { href: tab.getAttribute("href"), current: current });
      } else {
        row(label, { current: current, onClick: function () { tab.click(); } });
      }
    });
  }

  // ------------------------------------------------------------------------------------------ open/close
  function open() {
    if (IS_APP) buildApp(); else buildPublic();
    panel.hidden = false;
    btn.setAttribute("aria-expanded", "true");
    wrap.classList.add("is-open");
    var first = panel.querySelector(".board-menu-item");
    if (first) first.focus({ preventScroll: true });
  }
  function close(returnFocus) {
    if (panel.hidden) return;
    panel.hidden = true;
    btn.setAttribute("aria-expanded", "false");
    wrap.classList.remove("is-open");
    if (returnFocus) btn.focus({ preventScroll: true });
  }
  btn.addEventListener("click", function () { if (panel.hidden) open(); else close(true); });
  // /app: crossing 820px hides the burger; don't leave a panel open behind it
  var WIDE_APP = window.matchMedia("(min-width: 820px)");
  if (IS_APP && WIDE_APP.addEventListener) WIDE_APP.addEventListener("change", function () { close(false); });
  document.addEventListener("keydown", function (ev) {
    if (ev.key === "Escape" && !panel.hidden) { ev.preventDefault(); close(true); }
  });
  document.addEventListener("click", function (ev) {
    if (!panel.hidden && !wrap.contains(ev.target)) close(false);
  });
  if (!IS_APP) buildPublic();
})();

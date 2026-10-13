"use strict";

// In-app browser (webview) detection, shared by signin.js and landing.js — load this file first.
// Google OAuth refuses embedded webviews (403 disallowed_useragent), and the YouTube iOS app opens links in
// a WKWebView, so those pages steer a webview visitor to the email magic link (Mail opens it in Safari) and
// offer an "Open in Safari / Chrome" hand-off. See docs/plans/PHONE_FUNNEL_PLAN.md section 4.
// Wrapped so its names stay out of the global scope the other classic scripts share.
window.BTS_WEBVIEW = (() => {
  const UA = navigator.userAgent;
  // iOS: every real browser (Safari, Chrome = CriOS, Firefox = FxiOS) carries a `Safari/` token or its own
  // name; a bare WKWebView carries neither. Android's System WebView marks itself with `; wv)`.
  const IOS_WEBVIEW = /iPhone|iPad|iPod/.test(UA) && !/Safari\//.test(UA) && !/CriOS|FxiOS/.test(UA);
  const ANDROID_WEBVIEW = /Android/.test(UA) && /; wv\)/.test(UA);
  const any = IOS_WEBVIEW || ANDROID_WEBVIEW;

  // Which app's browser this is, for the copy. The YouTube app adds nothing to the UA, so an ad click's
  // utm_source is remembered for the tab (the landing page sees it, /login a click later does not).
  let source = "";
  try {
    const utm = new URLSearchParams(location.search).get("utm_source");
    if (utm) sessionStorage.setItem("bts_utm_source", utm.toLowerCase());
    source = sessionStorage.getItem("bts_utm_source") || "";
  } catch (_) { /* storage blocked: fall back to the UA tokens / generic copy */ }
  const APPS = [[/Instagram/, "Instagram"], [/FBAN|FBAV|FB_IAB/, "Facebook"], [/Discord/i, "Discord"],
                [/Reddit/i, "Reddit"], [/TikTok|musical_ly|Bytedance/i, "TikTok"], [/Snapchat/, "Snapchat"],
                [/LinkedInApp/, "LinkedIn"]];
  let app = (APPS.find(([re]) => re.test(UA)) || [])[1] || "";
  if (!app && /youtube/.test(source)) app = "YouTube";

  // Where the hand-off sends the visitor: the same page in the system browser. iOS: the x-safari-https
  // scheme (reported to work from WKWebViews on iOS 17+; unverified on a device, hence the always-visible
  // menu fallback). Android: an intent:// URL, which hands off to Chrome / the default browser.
  const here = location.host + location.pathname + location.search;
  const openUrl = IOS_WEBVIEW ? "x-safari-https://" + here
    : ANDROID_WEBVIEW ? "intent://" + here + "#Intent;scheme=https;end" : "";

  return {
    ios: IOS_WEBVIEW,
    android: ANDROID_WEBVIEW,
    any,
    app,                                                          // "YouTube", "Instagram", ... or ""
    where: app ? "the " + app + " app's browser" : "an in-app browser",  // "You're in <where>"
    browser: IOS_WEBVIEW ? "Safari" : "Chrome",
    openUrl,
    // The manual route, for when the scheme does nothing: both apps keep "open in browser" in a menu.
    menuHint: IOS_WEBVIEW ? "or tap the ··· menu at the top right and choose Open in Safari"
      : "or tap the ⋮ menu at the top right and choose Open in Chrome (or Open in browser)",
  };
})();

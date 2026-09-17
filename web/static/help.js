"use strict";
// The help page ships its screenshot slots before the screenshots exist: drop any <figure class="shot">
// whose image can't be fetched, so the walkthrough reads cleanly as text until PNGs land in
// static/img/help/. (An external file, not an inline onerror= — the CSP forbids inline script.)
//
// The <img>s are loading="lazy", so an offscreen one may never fire load/error at all. A detached probe
// Image() is NOT lazy, so it always resolves — that's what decides each figure's fate.
for (const fig of document.querySelectorAll("figure.shot")) {
  const img = fig.querySelector("img");
  if (!img) { continue; }
  const drop = () => fig.remove();
  img.addEventListener("error", drop);
  const probe = new Image();
  probe.onerror = drop;
  probe.src = img.getAttribute("src");
}

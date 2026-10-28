"use strict";
// archive.js — The Archive page (/archive): every featured class, newest featured first, as the same tiles
// the landing strip uses (featured.js). Public, no session, nothing mutating.

(async () => {
  const grid = document.getElementById("archive-grid");
  const empty = document.getElementById("archive-empty");
  const [items] = await Promise.all([fetchArchive(), BTS_I18N.ready]);
  for (const it of items) grid.appendChild(featuredTile(it));
  empty.classList.toggle("hidden", items.length > 0);
})();

"use strict";
// Select a starter-class code on click (was an inline onclick; the CSP forbids inline script).
for (const ta of document.querySelectorAll("textarea[readonly]")) {
  ta.addEventListener("click", () => ta.select());
}

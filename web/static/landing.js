"use strict";

// BLANK the spire — split-flap landing board.
// Five tiles spell BLANK on arrival, then every IDLE_MS the board "flips" (Solari/train-board
// style: each tile steps forward through the alphabet) to a new 5-letter verb that reads as
// "_____ the spire" — FORGE the spire, CLIMB the spire, BUILD the spire…

const FIRST = "BLANK";
const WORDS = [
  "FORGE", "BUILD", "CRAFT", "CLIMB", "SHAPE", "DREAM",
  "BLAZE", "STORM", "BRAVE", "SCALE", "SLASH", "RAISE",
  "CRAVE", "GOOSE", "MOOSE",   // the featured classes' words, so the idle loop sometimes lands on them
];

const SLOTS = 5;
const IDLE_MS = 2500;        // hold a word this long before flipping to the next
const STEP_MS = 85;          // base time between flaps (one letter advance) — jittered per step
const FLAP_MS = 150;         // how long a single flap animation takes
const A = "A".charCodeAt(0);

const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const rand = (lo, hi) => lo + Math.random() * (hi - lo);

// Build the tiles. Each tile owns a `.flap` whose textContent is its current letter.
const board = document.getElementById("board");
const flaps = [];
for (let i = 0; i < SLOTS; i++) {
  const tile = document.createElement("div");
  tile.className = "tile";
  const flap = document.createElement("span");
  flap.className = "flap";
  flap.textContent = " ";
  tile.appendChild(flap);
  board.appendChild(tile);
  flaps.push(flap);
}

// Advance one tile one letter, with a downward flip flash (skipped if reduced-motion).
function flapStep(flap, ch) {
  flap.textContent = ch;
  if (reduceMotion) return;
  flap.animate(
    [
      { transform: "rotateX(-90deg)", filter: "brightness(1.8)" },
      { transform: "rotateX(0deg)", filter: "brightness(1)" },
    ],
    { duration: FLAP_MS + rand(-30, 40), easing: "ease-out" },
  );
}

// Step one tile from its current letter forward through the alphabet to `target`.
async function rollTile(flap, target) {
  if (reduceMotion) { flap.textContent = target; return; }
  await sleep(rand(0, 320));   // random head-start so the tiles fall out of lockstep
  let code = flap.textContent.charCodeAt(0);
  if (Number.isNaN(code) || code < A || code > A + 25) {
    // Blank tile: flap in a visible A first (so a target of "A" still shows), then keep stepping.
    code = A;
    flapStep(flap, "A");
    await sleep(STEP_MS * rand(0.8, 1.35));
  }
  const goal = target.charCodeAt(0);
  while (code !== goal) {
    code = code === A + 25 ? A : code + 1; // wrap Z→A
    flapStep(flap, String.fromCharCode(code));
    await sleep(STEP_MS * rand(0.75, 1.45));   // jitter each step → letters land slightly off-order
  }
}

// The "___ the Spire!" blank in the How-it-works step 3, kept in sync with the board.
const fillWord = document.getElementById("fill-word");
const setFill = (w) => { if (fillWord) fillWord.textContent = w[0] + w.slice(1).toLowerCase(); };

// Flip the whole board to `word`. Tiles roll in parallel and settle left-to-right naturally,
// since each needs a different number of steps. Two callers share the board (the idle loop and a
// hovered featured tile), so only one roll runs at a time: a call made mid-flip just records the
// newest wish, and the running flip rolls on to it once the current word lands.
let current = "";
let flipping = false;
let wanted = null;
async function flipTo(word) {
  wanted = word;
  if (flipping) return;
  flipping = true;
  try {
    while (wanted) {
      const w = wanted;
      wanted = null;
      if (w === current) continue;
      await Promise.all([...w].map((ch, i) => rollTile(flaps[i], ch)));
      current = w;
      setFill(w);
    }
  } finally {
    flipping = false;
  }
}

// A hovered or focused featured tile holds the board on its word; the idle loop waits while either
// is set and for one full IDLE_MS after both are let go. (Pointer and focus are tracked apart so a
// click, which does both, can't leave the board stuck.)
const held = { pointer: null, focus: null };
let resumeAt = 0;
const isHeld = () => Boolean(held.pointer || held.focus);
function hold(kind, word) { held[kind] = word; flipTo(word); }
function release(kind) { held[kind] = null; resumeAt = Date.now() + IDLE_MS; }

async function run() {
  await flipTo(FIRST);           // land on BLANK first
  while (true) {
    await sleep(IDLE_MS);
    if (flipping || isHeld() || Date.now() < resumeAt) continue;   // never overlap a running flip
    let next = current;
    while (next === current) next = WORDS[Math.floor(Math.random() * WORDS.length)];
    await flipTo(next);
  }
}

// --- The Archive strip ------------------------------------------------------------------------
// The newest four classes from The Archive (/api/featured?limit=4), tiles built by featured.js. Any failure
// (or an empty Archive) leaves the section hidden, so the page degrades to the plain splash.
(async () => {
  const items = await fetchArchive(4);
  if (!items.length) return;

  const grid = document.getElementById("featured-grid");
  for (const it of items) grid.appendChild(featuredTile(it, { onHold: hold, onRelease: release }));
  document.getElementById("featured").classList.remove("hidden");
  // Arrived via /#featured (e.g. from the sign-in page): the section was hidden at load, so jump now.
  if (location.hash === "#featured") document.getElementById("featured").scrollIntoView();
})();

// In an in-app browser (webview.js) Google sign-in will fail, so the note under the CTA says up front that
// email is the way in here, or how to reopen the page in the real browser.
const WV = window.BTS_WEBVIEW;
if (WV && WV.any) {
  const who = WV.app ? "the " + WV.app + " browser" : "this in-app browser";
  document.getElementById("splash-note").textContent = "Sign in by email — " + who
    + " can't do Google sign-in. Or tap " + (WV.ios ? "···" : "⋮") + " → Open in " + WV.browser + ".";
}

// Point the button at the right place: already signed in → straight to the app; local dev (no OAuth
// credentials, so the chooser has no buttons) → the dev-login bypass; otherwise → /login, the provider
// chooser (the default href).
(async () => {
  try {
    const me = await (await fetch("/api/me")).json();
    const go = document.getElementById("signin");
    if (me && me.user) go.href = "/app";
    else if (me && me.dev_auth) go.href = "/dev-login?email=dev@example.com";
  } catch (_) { /* leave the button pointing at /login */ }
})();

run();

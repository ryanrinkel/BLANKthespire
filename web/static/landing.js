"use strict";

// BLANK the spire — split-flap landing board.
// Five tiles spell BLANK on arrival, then every IDLE_MS the board "flips" (Solari/train-board
// style: each tile steps forward through the alphabet) to a new 5-letter verb that reads as
// "_____ the spire" — FORGE the spire, CLIMB the spire, BUILD the spire…

const FIRST = "BLANK";
const WORDS = [
  "FORGE", "BUILD", "CRAFT", "CLIMB", "SHAPE", "DREAM",
  "BLAZE", "STORM", "BRAVE", "SCALE", "SLASH", "RAISE",
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

// Flip the whole board to `word`. Tiles roll in parallel and settle left-to-right naturally,
// since each needs a different number of steps.
async function flipTo(word) {
  await Promise.all([...word].map((ch, i) => rollTile(flaps[i], ch)));
}

// The "___ the Spire!" blank in the How-it-works step 3, kept in sync with the board.
const fillWord = document.getElementById("fill-word");
const setFill = (w) => { if (fillWord) fillWord.textContent = w[0] + w.slice(1).toLowerCase(); };

async function run() {
  await flipTo(FIRST);           // land on BLANK first
  let prev = FIRST;
  setFill(FIRST);
  // No Math.random in this env's tooling, but the browser has it — shuffle-pick avoids repeats.
  while (true) {
    await sleep(IDLE_MS);
    let next = prev;
    while (next === prev) next = WORDS[Math.floor(Math.random() * WORDS.length)];
    await flipTo(next);
    setFill(next);
    prev = next;
  }
}

// Point the button at the right place: already signed in → straight to the app; local dev (no Google
// OAuth, /login 503s) → the dev-login bypass; otherwise → Google sign-in (the default href).
(async () => {
  try {
    const me = await (await fetch("/api/me")).json();
    const go = document.getElementById("signin");
    if (me && me.user) go.href = "/app";
    else if (me && me.dev_auth) go.href = "/dev-login?email=dev@example.com";
  } catch (_) { /* leave the button pointing at /login */ }
})();

run();

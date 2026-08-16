# TRIAD PLAN — three archetypes per forged class (harness v1.7-triad)

## Why

A two-archetype class with mandatory bridge cards plays as ONE deck by design (that was O-1's
whole point) — which means the draft has no real decisions: every reward that touches either
engine is "take it". With THREE archetypes (A, B, C) the class becomes a triangle of PAIRS —
AB, AC, BC — and the player commits to a pair mid-run through what they draft. Choice becomes
real when:

1. Each archetype is a standalone lane (its own enablers/payoffs, draftable from common up).
2. Each PAIR has its own bridge package (the pairwise synergy cards) with a real finisher.
3. Nothing (or almost nothing) fuses all three — a pool where everything blends with
   everything reproduces exactly the no-choice problem we're fixing.
4. The starting deck stays neutral — signatures must not pre-commit the player to one pair.

## Design decisions (the load-bearing ones)

### D1. Bridges become PAIRWISE — schema change

Today a blueprint card carries `"bridge": true` and must fuse "both" engines. Under triad,
a bridge declares its pair: `"bridge": ["<arch_id_1>", "<arch_id_2>"]` (exactly two DISTINCT
archetype ids from this class). Back-compat: `true` stays legal on 2-archetype classes and is
normalized to the (only) pair at parse time.

Budget: **TARGET 2 bridges per pair (6 total — same total as today's TARGET_BRIDGES), floor
1 per pair AND 4 total** (mirrors the MIN/TARGET ask-vs-floor pattern). At least one bridge
rare overall stays required (the poster card); prefer each pair getting one bridge at
common/uncommon (draftable early) and one at uncommon/rare (the payoff).

### D2. Witness math generalizes per pair — plus a "no third wheel" check

`bridges.is_witnessed(card, ops_a, ops_b)` already takes exactly two ops sets — under triad
we call it with the DECLARED pair's ops, so the core function barely changes. Witness tokens
for the pair (X, Y) stay `ops(X) − ops(Y)` / `ops(Y) − ops(X)` (pairwise difference, NOT
minus-the-union — subtracting the third engine too would shrink witness sets and break the
disjoint-pair fast path for overlapping catalogs).

NEW (soft check, warn + repair-directive only, never abort): a pair bridge should NOT touch
the THIRD archetype's unique tokens (`ops(Z) − ops(X) − ops(Y)`). This is the anti-blend
guard — it keeps AB bridges from quietly being ABC cards. Warn-only because token overlap
between engines is common and a hard rule would thrash repairs.

Trinity cards (a card fusing all THREE engines) are **BANNED** (decided 2026-08-15): every
bridge declares exactly one pair. Pure pair separation — the draft signals stay clean.
Validation rejects a 3-id bridge; the prompt states the rule explicitly so the model doesn't
invent one.

### D3. Strategic lines map onto pairs

This is the elegant merge: the existing STRATEGIC LINES system (aggro/control/combo, each
needing ≥3 tagged cards + a rare finisher) becomes the *identity of the pairs*. The compose
stage declares which strategy each PAIR serves (e.g. AB = aggro, AC = control, BC = combo —
concept picks the mapping). "Pick a pair" and "pick a game plan" become the same decision.

**HARD-REQUIRED, all three distinct** (decided 2026-08-15 — the replay guarantee): a triad
blueprint must map its three pairs to the three DISTINCT strategies, and `_strategy_coverage`
for triad classes requires ALL THREE lines covered (each ≥`_LINE_MIN_CARDS` tagged cards
+ ≥1 rare finisher), up from today's ≥2. Three runs of the same class should feel like three
classes. A pair's bridge cards carry that pair's strategy tag (validated: a bridge whose
strategy tag isn't its pair's declared line is an error). The 7-rare budget (D4) covers
three finishers comfortably.

### D4. Pool grows to the practical cap: 32 cards (decided 2026-08-15)

Today: 7C / 12U / 4R ≈ 23 pool cards. Split: ~6 bridges + ~17 mono ≈ 8.5 own cards per
archetype. At the SAME size, three archetypes get ~5.7 own cards each — too thin to be a
draftable lane.

Decision: **9C / 16U / 7R = 32 pool cards** (TARGET_COMMONS=9, TARGET_UNCOMMONS=16,
TARGET_RARES=7; MIN_RARES stays 3 — the boss-reward soft-lock floor is about existence, not
depth). That yields 6 bridges + 26 mono ≈ 8–9 own cards per archetype — every pair-deck
drafts from a genuinely full pool, which is the replay value — and 7 rares covers a finisher
per pair-line plus spares.

Cap math (TIGHT — this needs a blueprint rule): the blueprint cap `_BLUEPRINT_CARD_CAP` is
36 (= `CARDS_PER_CLASS` 40 minus 4 headroom for the merchant/rare safety-net fillers), and
it counts EVERY card row including basics, signatures, and a forge class's blade token:

- normal class, 1 signature:  2 + 1 + 32 = 35 ✓
- normal class, 2 signatures: 2 + 2 + 32 = 36 ✓ (exactly at cap)
- FORGE class (adds the blade token row): 2 + 1 + 1 + 32 = 36 ✓, but with 2 signatures
  2 + 2 + 1 + 32 = 37 ✗ — so the prompt rule is: **a forge class takes ONE signature at
  the 32-pool target** (or drops one uncommon). Encode this in the pool ask, and the
  validator error message should name the fix.

Cost: ~9 extra card-generation calls per forge (~24 → ~33, roughly +38% latency/cost).
Accepted — fun/replayability is the priority.

WHY THE CAP EXISTS (and how to raise it later): the mod compiles a FIXED block of 40
card-slot shells per class — each forged card must be a distinct compiled .NET type because
BaseLib binds card identity to the Type and pools freeze at init. `CARDS_PER_CLASS` (py)
must equal `slotgen.CARDS_PER_CLASS` AND `ForgedCharacters.CardsPerClass` (C#). So the cap
IS changeable, but it's a mod release, not a generation tweak: bump all three, re-run
slotgen.py, rebuild + ship the mod — and older installed mods will REJECT bigger bundles
("bundle has N cards (max M per class)"), so the site must gate big forges on the player's
mod version. Parked as future work (Phase 4 note below) — 32 first, raise the ceiling only
if triad classes feel cramped in playtests.

Per-lane rarity discipline (prompt guidance, not validation): each archetype wants ≥2–3 of
its own commons so a lane is enterable from the first reward.

### D5. Starting deck neutrality

Keep 1–2 signatures, but add a prompt rule: with three archetypes a signature is either
NEUTRAL glue (archetype: null) or tied to the concept's CORE archetype — never a bridge, and
never two signatures serving the same pair. The starting deck must not decide the pair for
the player. Prompt-level only; no new validator (the fantasy sometimes wants a committed
core, e.g. a forge class whose blade IS archetype A — A then appears in two pairs and that's
fine).

### D6. Class-kind pools still bind to ONE archetype

Orb/status/summon/forge subsystems stay owned by a single archetype ("make ONE archetype the
orb engine" — unchanged). The interesting new texture is that the OTHER TWO archetypes each
bridge into it differently (AB: orbs+aggro, AC: orbs+control). No rule change needed beyond
prompt language.

## Change inventory (by file)

### Phase 1 — core plumbing (one-shot concept path works end-to-end)

- **`generation/btsgen/class_forge.py`**
  - `_validate_blueprint` (line ~1063): `len != 2` → `len not in (2, 3)`; pass the count
    through to bridge validation. New checks: each bridge's declared pair is two distinct
    valid archetype ids (a 3-id bridge is an ERROR — trinity cards are banned); per-pair
    floor (≥1 each pair) + total floor (≥4); triad classes require all THREE strategy lines
    covered and each pair mapped to a distinct strategy (D3); forge-class card-row budget
    rule at the 32-pool target (D4). Keep boolean-bridge back-compat for 2-archetype bps.
  - Blueprint system prompt (~line 163, 479–528): "TWO synergistic card archetypes" → "THREE
    … forming a triangle of pairs"; archetypes example gains a third entry; BRIDGE CARDS rule
    rewritten pairwise (declare the pair, 2 per pair, vary fusion shape per pair, ≥1 rare,
    optional single trinity rare, the no-third-wheel rule); signature-neutrality rule (D5);
    strategy↔pair mapping ask (D3). `_POOL_ASK` re-worded with the new targets.
  - Targets (~lines 68–72): TARGET_COMMONS/UNCOMMONS/RARES → 9/16/7 (D4) on the triad
    path; the legacy 2-archetype path keeps 7/12/4 (the targets become mode-dependent).
  - `_resolve_bridge_ctx` (~1628): resolve ops for N archetypes into `{id: (name, ops)}`;
    return per-pair contexts instead of a single a/b pair.
  - `_class_context` (~1653): "Its TWO archetypes" → dynamic ("Its THREE archetypes — three
    engines, three pair-lanes; serve the brief's engine, nod to ONE partner where natural,
    never all three").
  - `_card_context` (~1668): bridge branch reads the card's declared pair, calls
    `repair_directive` with THAT pair's names/ops, and appends the no-third-wheel line
    naming the excluded engine's witness tokens.
  - `fake_output` / `_fake_blueprint` / `_topup_blueprint_briefs`: seed 3 archetypes, pad
    loop `< 2` → `< count`, fake bridges declare pairs, top-up keeps per-pair floors.
  - Coverage/N-1 repair round: witness failures route per declared pair; repair directive
    per pair.
  - `HARNESS_VERSION` → `"1.7-triad"`.

- **`generation/btsgen/bridges.py`**
  - `is_witnessed` / `witness_sets` / `repair_directive`: unchanged signatures (they're
    already pairwise) + new `third_wheel_tokens(ops_x, ops_y, ops_z)` and a
    `pair_key(id1, id2)` normalizer (sorted tuple) used by validation and the ledger.
  - MIN_BRIDGES stays 4 (total floor); add `TARGET_BRIDGES_PER_PAIR = 2`,
    `MIN_BRIDGES_PER_PAIR = 1`. Docstring rewrite.

- **`generation/tests/`**: extend `test_bridges.py` (pair declaration parsing, per-pair
  floors, third-wheel warn, trinity cap, 2-arch boolean back-compat), `test_keystone_balance`
  and any bp fixtures gain a third archetype where they assert counts.

### Phase 2 — staged front-end (the website's real path)

- **`generation/btsgen/frontend/stage_map.py`**: compose prompt "EXACTLY TWO archetypes in
  tension" (~lines 83, 280) → EXACTLY THREE with a TENSION TRIANGLE — per-pair tension lines
  and a per-pair strategy assignment. JSON schema: `"archetype_ids": [a, b, c]`,
  `"pair_lines": [{"pair": [a,b], "strategy": "...", "line": "...", "win_condition": "..."}]`
  (subsumes/extends today's `strategic_lines`). `_fake_output` composes 3-id candidates.
- **`generation/btsgen/frontend/dossier.py`**: candidate docstring/fields — `tension` becomes
  the triangle summary; carry `pair_lines`. Lists already hold N ids, so shape changes are
  minimal.
- **`generation/btsgen/frontend/builder.py`**: narration "each fusing two archetypes" (~266);
  catalog stamping loop already generic; pass 3 ids to ledger recency.
- **`class_forge._dossier_brief`** (~600–658): "The TWO archetypes (in tension …)" → triangle
  block (three archetypes + three pair lines); strategic-lines rows come from `pair_lines`.
- **`generation/btsgen/ledger.py`** (~188–229): `pair_penalty`/`payload_line` — emit ALL
  C(3,2)=3 pairs per forge (`for combo in combinations(sorted(ids), 2)`), penalize repeats
  of any pair AND (stronger) the full triple. `archetype_design_line` already takes an id
  list — verify it iterates rather than unpacks.
- **`web/forge.py` / `web/static/app.js`**: mostly agnostic already (renderArchetypes loops;
  the pick-checkpoint is option-generic). Verify the interactive archetype-pick checkpoint
  copy and any report text that says "both archetypes". `pool_cards_per_archetype` is a
  legacy no-op knob — leave it.
- **Report (`frontend/dossier.py` dossier HTML / `_ARCHETYPE_REPORT` tooling)**: optional
  polish — render the synergy TRIANGLE (three lanes + three pair packages) so a forge's
  choice structure is visible at a glance.
- **`generation/tests/test_frontend.py`** (~263): `len(archs) == 2` → `== 3`;
  `test_ledger.py` pair fixtures → triples emitting three pairs.

### Phase 3 — tune, verify, ship

- Forge 3–5 real classes (varied kinds: normal / orb / forge / status) and REVIEW the
  triangle: does each pair read as a distinct game plan? Do mono-lanes have enough commons?
  Is any archetype a "kingmaker" that both other lanes need (that's a soft failure — it
  makes AB vs AC a fake choice since A is always in)?
- Balance knobs to revisit after playtests: pool size (D4), per-pair bridge target, whether
  the trinity card stays.
- `character_pipeline.py`/`character_validator.py` (prototype path, `len != 2` at validator
  ~820): FROZEN at 2 (decided 2026-08-15) — not in the web forge path; add a comment there
  pointing at this plan so the divergence is deliberate, not drift.
- The mod (C#) is archetype-agnostic — BTSC bundles carry no archetype data; no mod rebuild
  (card count stays ≤ 40 slots per D4).

## Rollout / compat — triad is an EXPERIMENT first (decided 2026-08-15)

The 2-archetype path stays the untouched default until triad classes are verified fun:

- Triad is OPT-IN behind a flag (`BTS_TRIAD=1` env for the CLI; a query param / toggle on
  the web forge). Flag off → exactly today's v1.6 flow: same prompts, same 7/12/4 targets,
  same boolean bridges. Validation accepts 2 OR 3 archetypes so both paths share one
  codebase; all mode-dependent knobs (targets, prompt asks, strategy floor) key off the
  blueprint's archetype count.
- The triad path stamps `HARNESS_VERSION = "1.7-triad-exp"` (the forge-flow version is the
  first log line) so every forge is attributable; the legacy path keeps stamping 1.6.
- Old ledger entries (2-id) and old saved forges keep working (display + ledger code
  iterate over id lists).
- Graduation criteria: forge 3–5 triad classes across kinds, playtest for pair
  distinctness + replay pull. If they clearly beat 2-archetype forges, flip the default
  (bump to `1.7-triad`) and keep `BTS_ARCHETYPE_COUNT=2` as the kill-switch.

## Phase 4 (future, only if 32 feels cramped): raise the 40-slot ceiling

Bump `CARDS_PER_CLASS` (class_forge.py) + `slotgen.CARDS_PER_CLASS` + C#
`ForgedCharacters.CardsPerClass` in lockstep, re-run slotgen.py, rebuild and release the
mod. Older installed mods reject bigger bundles, so the site must gate oversized forges on
the player's mod version (manifest bump). Not needed for this plan — 32 pool fits under
the current cap.

## Decisions log (2026-08-15)

1. **Pool size**: 32 (9C/16U/7R) — the practical max under the current cap; fun > cost.
2. **Trinity card**: BANNED — every bridge is exactly one pair.
3. **Strategy↔pair mapping**: HARD-required — three pairs, three distinct strategies, each
   a full package with a rare finisher.
4. **Prototype path**: frozen at 2 — triad is a web-forge experiment until proven.

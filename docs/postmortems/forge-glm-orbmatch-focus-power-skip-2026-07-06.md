# glm-5.2 reproducibly fails to code the "orb-match end-of-turn Focus power" — the vocab's OWN example

Found 2026-07-06 during the 8h `btsgen-forge-class --ollama` suite (ollama-cloud mixture, cards coded
by `glm-5.2`). A **specific, contract-valid card shape fails validation + the single repair attempt in
every forge that briefs it**, so the card is silently skipped. Seen in **2 of 2** classes whose
front-end chose a `slot_machine` (orb-match) archetype. This is a **model-coding / repair-robustness
bug**, NOT a vocabulary gap — the shape is the vocabulary's own blessed example.

## The card shape (identical brief, two classes)
| forge | card | brief |
|---|---|---|
| stonks (#16) | **Perfect Call** (rare power, cost 2) | "Power: at end of turn, channel 2 random orbs; if your orbs match, gain 2 Focus" |
| mariecurie (#21) | **Chernobyl Protocol** (rare power, cost 3) | "Power: at end of turn, channel 2 random orbs. If your orbs match, gain 2 Focus" |

Both produced `card N (Name): failed, skipped` → the class shipped 26/27 (graceful degradation worked).

## Why this is a bug, not a vocab limitation
The brief is the **canonical worked example in the contract**:
- `mod/contract/VOCABULARY.md:184` — *"At the end of your turn, channel a random orb; if your orbs
  match, gain 2 Focus."* given verbatim as a valid trigger design.
- `:179` — same example, "…orbs match, gain Focus".
- Every primitive it composes is blessed and demonstrably passes elsewhere:
  - `add_trigger trigger:"turn_end"` with an optional `when` (VOCABULARY.md:149-152, card.schema.json:38).
  - `when:{kind:"orbs_match"}` (VOCABULARY.md:123; passed in stonks' *Moon Shot* "if your orbs match,
    deal 32").
  - `channel_orb orb:"random" amount:2` (VOCABULARY.md:21).
  - `focus` status gain (statuses/focus.json; passed in Tesla's *Singularity Coil* / *Faraday Cage*).

So the individual ops all validate in other cards — it's the **nested composition** (`add_trigger turn_end`
→ payload with `when:{orbs_match}` → `channel_orb random` + `focus`) that glm-5.2 emits wrong, and the
one repair pass can't fix. The failure is reproducible and shape-specific.

## ROOT CAUSE — CONFIRMED via targeted repro (2026-07-06, glm-5.2, same generator the suite uses)
`scratchpad/repro_orbmatch3.py` — 3 iterations of `first_attempt` + the pipeline's own
`_extract_or_error` + `CardValidator.validate`. Two compounding failure modes, both on this shape:

**(1) Schema-invalid `when` placement — the "1 error" on a parseable attempt.** glm-5.2 encodes the
conditional by hanging `when:{kind:"orbs_match"}` on a sub-effect **inside** the `add_trigger` payload:
```json
{"op":"add_trigger","trigger":"turn_end","effects":[
  {"op":"channel_orb","orb":"random"},
  {"op":"channel_orb","orb":"random"},
  {"op":"apply_status","status":"focus","amount":2,"when":{"kind":"orbs_match"}}   ← rejected
]}
```
Validator:
```
schema [effects/0/effects/2]: Additional properties are not allowed ('when' was unexpected)
schema [upgrade/effects/0/effects/2]: Additional properties are not allowed ('when' was unexpected)
```
The schema allows `when` on **top-level** effects and on the **`add_trigger` op itself** (gating the whole
payload), but NOT on individual effects nested inside a trigger's `effects` payload.

**(2) Empty / truncated completions.** 2 of 3 first-attempts were unparseable: one **empty** (raw len 0,
model streamed nothing), one **truncated** after the header (raw len 135, cut mid-object). Under
`response_format=json_object` + this heavy nested schema, glm-5.2 intermittently emits nothing or stops
early. The single repair attempt likewise returns non-JSON (repro v1: "repair: still unparseable"), so a
one-error-away card is discarded.

**Design tension this exposes (vocab vs schema).** The vocabulary's canonical example (VOCABULARY.md:184)
is *"channel a random orb; **if** your orbs match, gain 2 Focus"* — channel UNCONDITIONAL, Focus
CONDITIONAL. Encoding exactly that needs a `when` on ONE sub-effect of the trigger payload — precisely what
the schema forbids. You can gate the WHOLE trigger (`when` on the `add_trigger` op → channel+Focus both
gated) or nothing; "channel always, Focus-if-match" is **not expressible**. So the model is actively nudged
toward the illegal per-sub-effect `when`. This mismatch should be resolved, not just worked around.

Revised fixes (supersedes the hypotheses list):
1. **Resolve the vocab/schema mismatch** — either allow `when` on `add_trigger`-payload sub-effects
   (matches the vocab example + the natural design), OR change VOCABULARY.md:184 to a whole-trigger gate
   and add a "you cannot gate a single sub-effect of a trigger" note so the model stops trying.
2. **Harden card-gen against empty/truncated completions** — retry on len-0 / parse-fail (this empty
   response is general to glm-5.2 on heavy cards, not unique to this one).
3. **Surface skip errors** (below) — still valid; would have shown error (1) immediately.

## Observability gap that blocks root-causing from logs
The forge log prints only `card N (Name): failed, skipped` — **the validator errors are never surfaced**.
`forge_class` (class_forge.py ~1203) discards `pres.result.errors` for a skipped brief. You cannot tell
a vocab gap from a model miss from a balance rejection without them. **Recommend: log the final
validation errors for every skipped brief** (even at WARN). This alone would have root-caused the above.

## Repro — DONE (2026-07-06)
Captured live during the suite. Scripts + raw output in scratchpad:
`repro_orbmatch.py` (full pipeline: attempt-1 = 1 error, repair = unparseable → skip),
`repro_orbmatch3.py` (isolates attempt-1 via the pipeline's own parse+validate → the exact schema errors
above). Reproduces on glm-5.2 with the same `build_ollama_mix()` card generator the suite uses.

## Impact
Low game-impact (class still ships, one fewer card) but it **silently drops a signature payoff card** for
orb/slot-machine classes — exactly the archetype's keystone. On the website this is an invisible quality
regression for that class fantasy. Fix priority: (1) surface skip errors, (2) targeted few-shot for the
trigger+orbs_match+focus composition (or a shape-aware repair hint), (3) consider a second repair attempt.

## Scope
- 2/2 slot_machine-archetype forges hit it; non-orb classes never briefed this shape, so 0 there.
- Not the DNS transient (that's a separate report). Not a crash — exit 0, valid bundle.

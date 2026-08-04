# Neow "Kaleidoscope" option crashes the game for forged classes

Found 2026-07-03 by the AutoSlay smoke gate (first Linux runs), reproduced twice with two DIFFERENT
forged classes — the stale June-21 "The Totopo" (seed BTSTWEAK3) and a freshly fake-forged
"Test Toxin" (seed BTSTWEAK6) — so it is the OPTION, not any one class's content.

## Symptom
AutoSlay (or presumably a player) picks the Neow event option **Kaleidoscope** while playing a forged
class → the game process exits immediately. No managed exception reaches the log — godot.log simply
ENDS after the lines below (looks like a native/assert death, not a C# throw), and the AutoSlay log
gets no RunFailed marker (the smoke driver classifies it "ambiguous — log has no
RunCompleted/RunFailed marker").

## Last log lines (identical shape both times; full log: neow-kaleidoscope-crash-2026-07-03.godot.log)
```
[INFO] [AutoSlay] Action: Selecting event option: NEOW (option: Kaleidoscope)
[WARN] [BlankTheSpire] [RewardGuard] single-rarity custom card pool with RegularEncounter odds → forced Uniform ...
[WARN] [BlankTheSpire] [RewardGuard] reward card-gen failed with no fallback card available; suppressing to
       avoid a hang. Tried to create a card for a reward, but we couldn't generate a valid rarity!
       Odds: RegularEncounter Card pool: , blacklist:
```

## Reading
Note `Card pool: ` is EMPTY in the failure — Test Toxin has a healthy 9-card pool, so Kaleidoscope is
drawing from some OTHER pool a forged class never populates (colorless/special?). RewardGuard's
suppression stops the hang it was built for, but whatever consumes the (now empty/null) reward next
dies natively. Same family as the boss-reward-rarity and merchant hangs: base-game systems assuming
pools a forged class doesn't fill.

## Repro
`uv run btsgen-autoslay-smoke --seeds BTSTWEAK6 --character class1` with any forged class staged in
slot 01 — AutoSlay picks Neow options randomly, so use a seed known to pick Kaleidoscope (BTSTWEAK6,
BTSTWEAK1..3 with the same map rng) or just run a few seeds.

## Next steps (not done)
- Find what pool Kaleidoscope rolls (decompiled game src is reproducible via ilspycmd; look for the
  NEOW event option handlers) and either populate/guard it for forged classes in RewardGuard, or
  patch the option away for forged classes.

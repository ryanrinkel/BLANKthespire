"""BTS import-code codec (Python mirror of mod/BlankTheSpireCode/Engine/BTS1Codec.cs).

Two code kinds, identical primitives — only the magic + payload shape differ:
  BTS1.<vocabVersion>.<base64url(gzip(json))>.<crc32>   a single forged CARD
  BTSC.<vocabVersion>.<base64url(gzip(json))>.<crc32>   a whole CLASS bundle
                                                          {kind:"class", character:{…}, cards:[…], relic?:{…}}

A code is data over the closed vocabulary (safe by construction) — the in-game importer re-validates every
op/status/target against the live EffectRunner before writing anything. This module is the reference encoder
that keeps the website's codec byte-compatible with the C# decoder.

The three primitives are standard, so codes round-trip between this and the C# implementation:
  gzip (stdlib), base64url (RFC 4648 §5, padding stripped), CRC-32/IEEE (zlib.crc32 over the RAW json bytes).

Pure stdlib. Usage:
    python -m btsgen.bts1 encode-card  mod/content/cards/quick_jab.json
    python -m btsgen.bts1 encode-class path/to/classdir [slot]      # dir w/ NN.json + NN/cards/*.json
    python -m btsgen.bts1 decode "BTS1.2.H4sI...."
"""
from __future__ import annotations
import base64
import gzip
import json
import sys
import zlib
from pathlib import Path

VOCAB_VERSION = 39  # must be <= ForgedCards.VocabVersion (39: Phase AI (gap #7) — GRAFT. New op `graft_card`
#                     {card_id}: the CHOOSE form of transform_card (as purge_card is the choose form of purge). When
#                     played, YOU pick a card in HAND (CardSelectCmd.FromHand) and THAT picked card PERMANENTLY becomes
#                     the named same-class card for the rest of the run (deck original swapped + the picked hand clone
#                     transformed now). Reuses ResolveTransformTarget (no-chain / no-self / same-class) + the purge
#                     DeckVersion guard (null-DeckVersion pick = combat-only). Guards: same-class + exists · not on BASIC
#                     · card-only · ⊥ purge/purge_card · counts toward the same ≤3 transform-family cap (warning).
#                     38: Phase AH (gaps #35/#38) — TRANSFORM_CARD. New op
#                     `transform_card` {card_id}: when the carrying card is PLAYED it PERMANENTLY becomes that
#                     same-class card for the rest of the run (self-rewrite / two-card mode-swap). Deck original
#                     swapped via CardCmd.Transform under the purge DeckVersion guard + the in-hand clone this combat.
#                     Guards: same-class + exists · not on BASIC · card-only · ⊥ purge · no transform CHAINS (a target
#                     may carry transform_card only if it swaps BACK — A↔B mode-swap; A→B→C rejected) · self-transform
#                     rejected · class cap ≤3 (warning). 37: Phase AG (gap #39) — UPGRADE-COST CHANNEL. The
#                     `upgrade` object gains an optional `cost` (0..3) = the card's ABSOLUTE cost after upgrade
#                     (upgrades cheapen, never tax: cost <= base; not on X-cost). CardSpec.UpgradedCost applied via
#                     MockSetEnergyCost on the Upgraded event; the signature blade's upgrade now drops 2→1. 36: Phase AF (gap #41) — BLADE EMPOWER. New op
#                     `blade_empower` {amount 2..3}: a one-turn ×N multiplier on the forge class's signature blade
#                     token (a burst spike distinct from the slow Forge ramp). Forge-class only + card-only. 35: Phase AE (gap #25) — CARD TAGS. New optional card
#                     field `tags` (1..2 lowercase slugs, declarative) + ADDITIVE scale `tag_cards_owned`
#                     (damage/block only) requiring a sibling `tag`: printed amount + count of cards carrying that
#                     tag across your combat piles (Perfected-Strike synergy). 34: Phase AD (gap #12) — HP-LOST GATE. New `when`
#                     condition `hp_lost_ge` {1..15}: true when you've lost >= N HP THIS turn (any source; the
#                     Ice Shatter self-fuel→payoff threshold). Snapshot-based (HP at turn start minus now); resets
#                     each turn. Pair a `lose_hp` fuel effect with a payoff gated on it. 33: Phase AC (gap #2) — SUMMON HEAL/SHIELD. New ops
#                     `heal_summon` {1..9} + `shield_summon` {1..12}: heal / grant Block to YOUR living summon
#                     (CreatureCmd.Heal / GainBlock). Class-only (summon class); legal on cards AND in add_trigger
#                     self-payloads (the medic engine). No summon out → logged no-op. 32: Phase AB (gap #20) — CORRUPTION. New flag-op
#                     `corruption` (no amount/target, card-only, power/skill): grants a binary per-combat power —
#                     your Skills cost 0 but Exhaust when played (base-game Corruption). Rejected in add_trigger
#                     payloads; <=1 corruption card per class. 31: Phase AA (gap #17 R-2) — SCRY. New op `scry`
#                     {amount:N}: look at the top N cards of your DRAW pile and discard any subset (draw-filter;
#                     the 3rd discard-subsystem primitive after discard + on_discard). Top-N slice → CardSelectCmd.
#                     FromSimpleGrid (min 0/max N) → CardCmd.Discard → fires on_discard. Card-only. AutoSlay auto-
#                     picks. 30: Phase Z (gap #19 choose) — CHOOSE-PURGE. New op
#                     `purge_card`: the player PICKS one card in hand and purges it (removes it from the run deck for
#                     the rest of the run — targeted deck-thinning) via CardSelectCmd.FromHand → CardPileCmd.Remove
#                     FromDeck(DeckVersion)+RemoveFromCombat (reuses Phase-W removal). Card-only (rejected in trigger
#                     payloads). AutoSlay auto-picks. 29: Phase X (gap #18 player-pick) — CHOOSE-UPGRADE. New
#                     `cards` scope `choose` on `upgrade_card`: the player PICKS one upgradable hand card (the true
#                     Armaments fantasy) via CardSelectCmd.FromHandForUpgrade → CardCmd.Upgrade. Card-only (rejected
#                     in trigger payloads). AutoSlay auto-picks. 28: Phase W (gap #19) — SELF-PURGE. New flag-op
#                     `purge`: a played card is removed from your RUN DECK for the rest of the run (deck-thinning;
#                     a stronger exhaust). purge ⊥ exhaust; never on a basic. 27: Phase V (gap #18) — IN-RUN UPGRADE. New op
#                     `upgrade_card` {cards: random|all}: upgrade cards in HAND for the rest of this combat
#                     (choiceless) — `random` one random upgradable hand card, `all` every upgradable one (Armaments+).
#                     Combat-scoped (hand cards are deck clones). No amount. Legal in add_trigger payloads (`random`
#                     only).
# --- 26: Phase U (gap #23) — RAMPAGE. New optional `grow`
#                     (1..9) field on a `damage` op: damage = amount + grow × (times THIS card played earlier this
#                     combat); first play = printed. Per-card-instance, per-combat reset. NOT a scale (grow ⊥ scale).
# --- 25: Phase T — the TRUE BLADE. The signature blade is
#                     no longer innate + deck-seeded; the FIRST Forge income of combat SUMMONS it to hand
#                     (ForgedForgePower.Stoke). Blade shape: token:true + damage scale:"forged" + retain, cost 2 /
#                     base 10, rarity "token". + op "summon_blade" (put your blade into hand from anywhere;
#                     class-only, no amount; cards + add_trigger payloads). + trigger "on_blade_played" (fires
#                     when you play your token blade; multi-fire, once_per_turn-eligible). Legacy v20-v24 blades
#                     (innate + deck-seeded) still load — the summon guard skips a blade already in a pile.
#                     (24: Phase S — THE BALANCE GAUGE. op "balance_step"
#                     {pole: light/dark, amount:1..5}: move a SIGNED per-combat player counter (positive=Dark,
#                     negative=Light, absent at 0) toward a pole; legal on cards + in add_trigger payloads (income
#                     engine, like forge). + when conditions light_ge/dark_ge N (that pole's magnitude >= N) /
#                     centered N (|gauge| <= N). Gauge BITES at |8| each turn-start (Dark: lose 3 HP; Light: 1 Weak).
#                     (23: Phase R — discard subsystem. op "discard"
#                     {amount:N}: discard N random cards from hand (choiceless); legal on cards + in add_trigger
#                     payloads (forced churn). + trigger kind "on_discard": CARD-LATENT Reflex — fires THIS card's
#                     payload when it's effect-discarded (NOT turn-end cleanup, NOT on play). scry (R-2) deferred).
#                     (22: Phase Q — op "add_card" {card_id, pile:
#                     hand/discard/draw, amount? 1..3}: generate combat-transient copies of a SAME-CLASS card
#                     into a pile; class-only; legal on cards AND in add_trigger payloads (the on_exhaust compost
#                     loop, gap #8); depth-1 loop discipline (a generated card may not itself add_card)).
#                     (21: Phase P precision reads — scale
#                     "damage_dealt_unblocked" (heal-only lifesteal) + scale "target_debuff_count" (damage-only)
#                     + when {kind:"draw_pile_empty"} (Grand-Finale gate) + relic hook "on_hp_lost").
#                     (20: Sovereign Blade (Tier 1) — a card may carry
#                     `token:true`, marking it the forge class's non-drafted signature blade: seeded into the
#                     starting deck by slot but registered autoAdd:false + showInCardLibrary:false so it is
#                     never offered as a reward/draft nor listed in the compendium. No new op — the blade is
#                     `damage scale:"forged"` + `retain` + `innate` (all v19); token is card-level metadata
#                     (CardSpec.IsToken, honored by DataCard). Bumped so a v20 blade code isn't silently
#                     mis-imported by a v19 mod (which would leak the blade into rewards);
#                     19: Phase M "Forge" (gap #36) — op `forge` stokes a
#                     per-combat player-level Forge counter (cards / trigger payloads / relic hooks);
#                     scale:"forged" on damage/block resolves ADDITIVELY (printed amount + Forge — the one
#                     additive exception in the scale family); + `when` condition forged_ge N;
#                     18: Phase H4 reactive card triggers — add_trigger gains
#                     on_exhaust/on_card_played/on_card_drawn/on_damage_dealt/on_block_gained/attacked, a
#                     once_per_turn gate, and enemy-targeted payloads (target:enemy|all_enemies on damage/debuff);
#                     17: gap #9 "on_hp_lost" — add_trigger trigger:"on_hp_lost"
#                     fires its self/orb payload whenever you lose HP on your own turn (the bleed/sacrifice payoff);
#                     16: gap #6 "ripen" — add_trigger trigger:"ripen" with
#                     amount=N waits N turn-starts then fires its self/orb payload ONCE (delayed maturation);
#                     15: true-Osty summons — summon grows HP / (re)summons ONE
#                     passive minion; + summon_attack (strike through it) + buff_summon; K-3 custom mechanics disabled)
CARD_MAGIC = "BTS1"
CLASS_MAGIC = "BTSC"


def _encode(magic: str, json_text: str) -> str:
    data = json_text.encode("utf-8")
    crc = zlib.crc32(data) & 0xFFFFFFFF
    payload = base64.urlsafe_b64encode(gzip.compress(data)).rstrip(b"=").decode("ascii")
    return f"{magic}.{VOCAB_VERSION}.{payload}.{crc:08x}"


def encode_card(card_json_text: str) -> str:
    return _encode(CARD_MAGIC, card_json_text)


def encode_class(bundle_json_text: str) -> str:
    return _encode(CLASS_MAGIC, bundle_json_text)


# Back-compat alias (old call sites encoded single cards).
encode = encode_card


def decode(code: str) -> tuple[str, str]:
    """Return (json_text, kind) where kind is 'card' or 'class'. Raises ValueError on any bad code."""
    clean = "".join(code.split())  # strip whitespace from line-wrapped pastes
    parts = clean.split(".")
    if len(parts) != 4:
        raise ValueError("not a BLANK the spire code.")
    kind = {CARD_MAGIC: "card", CLASS_MAGIC: "class"}.get(parts[0])
    if kind is None:
        raise ValueError("not a BLANK the spire (BTS1/BTSC) code.")
    ver = int(parts[1])
    if ver > VOCAB_VERSION:
        raise ValueError(f"code needs a newer mod (code v{ver} > supported v{VOCAB_VERSION}).")
    payload = parts[2] + "=" * (-len(parts[2]) % 4)
    data = gzip.decompress(base64.urlsafe_b64decode(payload))
    if f"{zlib.crc32(data) & 0xFFFFFFFF:08x}" != parts[3].lower():
        raise ValueError("corrupted code (checksum mismatch).")
    return data.decode("utf-8"), kind


def build_class_bundle(class_dir: str | Path, class_slot: int = 1) -> dict:
    """Assemble a {kind:'class', character, cards[]} bundle from a forged-class dir layout:
    <class_dir>/<KK>.json (the character) + <class_dir>/<KK>/cards/NN.json (its cards, in slot order)."""
    class_dir = Path(class_dir)
    character = json.loads((class_dir / f"{class_slot:02d}.json").read_text(encoding="utf-8"))
    cards_dir = class_dir / f"{class_slot:02d}" / "cards"
    cards = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(cards_dir.glob("*.json"))]
    return {"kind": "class", "character": character, "cards": cards}


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "encode-card":
        print(encode_card(Path(argv[2]).read_text(encoding="utf-8")))
    elif cmd == "encode-class":
        bundle = build_class_bundle(argv[2], int(argv[3]) if len(argv) > 3 else 1)
        print(encode_class(json.dumps(bundle, separators=(",", ":"))))
    elif cmd == "decode":
        text, kind = decode(argv[2])
        print(f"# kind: {kind}\n{text}")
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

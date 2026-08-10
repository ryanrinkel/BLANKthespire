"""Forge a whole CLASS (the website's core) — concept -> blueprint -> card set -> BTSC import code.

This is the lean, vocab-v2-constrained class generator behind P3. It deliberately does NOT reuse the
prototype's character_pipeline (which targets the full prototype vocabulary + a starter relic): the mod's
EffectRunner only runs the v2 vocabulary, and a forged class is imported as a `BTSC` bundle
(`{kind:"class", character:{…}, cards:[…]}`) whose cards live in slot order. So we:

  1. blueprint   one LLM call -> class identity + 2 archetypes + a per-card design brief list (v2 only).
  2. card set    each non-basic brief -> the proven generate->validate->repair-once card pipeline, pointed
                 at mod/contract (the v2 card schema + vocabulary). Strike/Defend basics are synthesized
                 verbatim (the StS rule), spending no model calls.
  3. assemble    cards in slot order (basics first), character.starting_deck = [{slot,count}], -> BTSC code.

Starter relics are NOT generated (the mod uses a placeholder; custom forged relics are a later phase).

    uv run btsgen-forge-class --concept "a frost mage who freezes then shatters"            # needs a key
    uv run btsgen-forge-class --concept "anything" --fake                                    # offline, no key
    uv run btsgen-forge-class --concept "..." --base-url https://api.openai.com/v1 \
        --api-key sk-... --model gpt-4o                                                       # BYOK path
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from .bridges import MIN_BRIDGES  # Phase O-1: the required-bridge-card count (fusion enforcer)

def _find_repo_root() -> Path:
    """Repo root = the directory that contains ``mod/contract/``. Resolve it robustly so the forge works
    whether btsgen runs from the source tree (``uv run`` / ``pip install -e``) OR is installed non-editably
    into a venv's site-packages. The droplet does the latter (``pip install ./generation`` COPIES this file
    out of the repo), so the old ``parents[2]`` guess pointed INTO the venv
    (``…/.venv/lib/pythonX/mod/contract`` -> FileNotFoundError). Resolution order:
      1. ``BTS_REPO_ROOT`` env — the web app sets this from its own location (see web/forge.py);
      2. walk up from this file looking for ``mod/contract/VOCABULARY.md`` (source / editable installs);
      3. legacy ``parents[2]`` fallback.
    """
    env = os.environ.get("BTS_REPO_ROOT")
    if env:
        return Path(env)
    here = Path(__file__).resolve()
    for cand in here.parents:
        if (cand / "mod" / "contract" / "VOCABULARY.md").exists():
            return cand
    return here.parents[2]


REPO = _find_repo_root()
CONTRACT = REPO / "mod" / "contract"
RELIC_VOCAB = CONTRACT / "RELIC_VOCABULARY.md"  # Phase L: the constrained forged-relic vocab (LLM prompt + lockstep)

# Creative-harness / forge-flow version. Independent of VOCAB_VERSION (mod compatibility): bump this whenever
# the forge FLOW changes (blueprint prompt, staged front-end, strategic lines, card pipeline, safety nets…) so
# a log line lets you tell which harness produced a given forge — on the CLI and in the streamed browser log.
# It's the FIRST line emitted by forge_class(). Bump on any harness tweak; a short "-what" suffix helps track.
HARNESS_VERSION = "1.3-resonant"

# Forged-class pool target. A base StS2 class pool is 20 common / 35 uncommon / 25 rare (~80 non-basic
# cards); we ship a lean, reward-functional subset — each non-basic brief is one card-generation (LLM)
# call, so this is the main cost/latency lever per class. MIN_RARES is the HARD floor the assembly
# GUARANTEES: a boss card reward rolls a Rare under BossEncounter odds (no lower-rarity fallback), and the
# run SOFT-LOCKS if the class has no available Rare — so every class must ship >=MIN_RARES Rares (the
# 4-rare target stays comfortably above it). See boss-reward-rarity-hang.
TARGET_COMMONS = 7
TARGET_UNCOMMONS = 12
TARGET_RARES = 4
MIN_RARES = 3
TARGET_POOL = TARGET_COMMONS + TARGET_UNCOMMONS + TARGET_RARES  # ~23 non-basic pool cards

# The strategy taxonomy for STRATEGIC LINES (see the blueprint prompt): every class's pool must support at
# least two of these as genuinely draftable game plans, each with its own rare finisher — the Ironclad test
# (one pool drafts Strength aggro OR block control OR an exhaust combo engine). Kept to the classic trio on
# purpose; nuances like "ramp"/"attrition" live in a line's free text, not the tag.
STRATEGIES = ("aggro", "control", "combo")
_LINE_MIN_CARDS = 3  # a supported line = at least this many tagged pool cards, including >=1 rare finisher

# The mod compiles a FIXED block of card-slot shells per class (each forged card must be a distinct compiled
# .NET type — BaseLib binds card identity to the Type, and pools freeze at init), so a class can hold at most
# this many cards. The in-game import REJECTS any bundle with more ("bundle has N cards (max M per class)").
# MUST equal ForgedCharacters.CardsPerClass (C#) AND slotgen.CARDS_PER_CLASS — raising it means bumping all
# three, re-running slotgen.py, and rebuilding the mod.
CARDS_PER_CLASS = 40
# Headroom the blueprint must leave so the merchant/rare safety nets can add fillers without breaching the cap.
# (Final card count <= planned count, since the safety nets only RESTORE generation-dropped cards — so capping
# the plan caps the bundle.) Keep this a few below CARDS_PER_CLASS.
_BLUEPRINT_CARD_CAP = CARDS_PER_CLASS - 4
# Every forged class starts with EXACTLY this many cards — the base-game / mod contract. The assembly normalizes
# the two basics' copy counts so the deck always totals this regardless of how many signatures the class has.
STARTING_DECK_SIZE = 10


def point_btsgen_at_mod_contract() -> None:
    """Repoint the card schema/vocabulary/statuses at the constrained v2 mod contract. MUST run before the
    btsgen modules that read paths at import time."""
    # GODOT_ROOT is only asserted-to-exist (its content paths are all overridden below). The prototype
    # build root it defaults to isn't deployed to the website host, so anchor it at the repo root, which is.
    os.environ["BTSGEN_GODOT_ROOT"] = str(REPO)
    os.environ["BTSGEN_CARD_SCHEMA"] = str(CONTRACT / "card.schema.json")
    os.environ["BTSGEN_VOCABULARY"] = str(CONTRACT / "VOCABULARY.md")
    os.environ["BTSGEN_DESIGN_HEURISTICS"] = str(CONTRACT / "DESIGN_HEURISTICS.md")
    os.environ["BTSGEN_STATUSES_DIR"] = str(CONTRACT / "statuses")
    os.environ["BTSGEN_CARDS_DIR"] = str(REPO / "mod" / "content" / "cards")
    os.environ["BTSGEN_GENERATED_DIR"] = str(REPO / "generation" / "scratch" / "_class_gen")


@dataclass
class ClassBrief:
    concept: str = ""
    # Legacy knob — pool size is now driven by the TARGET_* rarity targets (a base-class-sized pool), not
    # this per-archetype count. Kept for call-site back-compat; no longer affects how many cards are asked for.
    pool_cards_per_archetype: int = 4
    # Phase N-2: the featured-mechanic roulette picks (ids into btsgen.featured.FEATURED_MENU). forge_class
    # rolls these per concept before stage 1 and both brief modes REQUIRE the blueprint to weave them in.
    featured: list | None = None

    def describe(self) -> str:
        return f"concept: {self.concept}"


@dataclass
class ClassResult:
    ok: bool
    bundle: dict | None = None          # the BTSC bundle: {kind, character, cards[]}
    blueprint: dict | None = None
    skipped: list[str] = field(default_factory=list)
    log: list[str] = field(default_factory=list)


def archetype_display(bp: dict | None) -> list[dict]:
    """The blueprint's two archetypes in report shape: {id, name, title, pitch, description}, every value a
    stripped string ('' when absent). title/pitch exist only when the interactive front-end enriched the bp;
    displays fall back to name + description. Display-only — never part of the encoded BTSC bundle."""
    if not isinstance(bp, dict):
        return []
    out = []
    for a in bp.get("archetypes") or []:
        if isinstance(a, dict):
            out.append({k: str(a.get(k) or "").strip()
                        for k in ("id", "name", "title", "pitch", "description")})
    return out


# --- the blueprint contract (constrained to vocab v2; no relic, no structural ops) ---------------

class _BlueprintContract:
    """Duck-typed contract for the blueprint LLM call (system_prompt / user_brief / repair_message).

    Runs in TWO modes with the SAME system_prompt (so the 190-line f-string is never re-touched — only the
    user message changes): mode="concept" (today's one-shot: concept -> everything) and mode="dossier" (the
    staged front-end: a decided identity -> card briefs + pools). Both emit the IDENTICAL bp shape, so
    _validate_blueprint and everything downstream is untouched."""

    def __init__(self, mode: str = "concept") -> None:
        self.mode = mode

    def system_prompt(self) -> str:
        from . import paths
        vocab = paths.VOCABULARY.read_text(encoding="utf-8")
        return f"""You are a CLASS designer for "BLANK the spire", a Slay-the-Spire-like deckbuilder. From a \
player's concept you design a whole new playable class: its identity, HP, TWO synergistic card archetypes, \
and a one-line design brief for every card in its set. You output ONE JSON "blueprint" — briefs only, NO \
card-effect JSON (each card is generated and validated separately from your briefs).

THE HARD CONSTRAINT — the engine runs a CLOSED, SMALL vocabulary. Every mechanic you design must be \
expressible with ONLY these:
{vocab}

There are NO other ops, statuses, or primitives — no conditionals, no state-scaling, no card generation, no \
custom keywords. If the concept implies a mechanic that doesn't exist (freeze, burn, scaling…), \
translate its FANTASY onto these primitives (e.g. "freeze" -> Weak/Frail/Vulnerable + Block; "burn"/"venom" \
-> Poison; "berserk" -> Strength + lose_hp; "tempo" -> draw + gain_energy). Stay strictly INSIDE the \
vocabulary (a brief that can't be built from it will be dropped) — but WITHIN it, range widely rather than \
conservatively.

Both archetypes must be built from this vocabulary and CROSS-SYNERGIZE (cards of one get better with the \
other). ANY engine the vocabulary supports is fair game — the full status list (Thorns, Regen, Metallicize, \
Artifact, Buffer, Blur, temp buffs...), triggers, `when` conditions, scaled amounts, retain / exhaust / \
innate / ethereal, multi-hit, and the class-kind pools (orbs, custom statuses, a summon) where the identity \
fits. Do NOT default to a Strength or Poison engine out of habit; let the concept pick its engines from the \
whole list. Use Vulnerable/Weak sparingly — they are generic filler.

ORB CLASSES (optional — only when the concept fits): the vocabulary includes a Defect-style ORB subsystem \
(see the "Orbs" section above). If — and ONLY if — the concept is an elemental/channeling/"slot-machine"/ \
alchemist identity (storm-caller, elementalist, gambler, etc.), you MAY make this an ORB CLASS: set top-level \
"orb_slots" to 3 or 4, declare an "orb_pool" (below), make ONE archetype the orb engine (briefs that \
channel_orb + evoke + a `focus` payoff), and use the orb ops/`focus` freely in THAT archetype's briefs. For \
every NON-orb concept, set "orb_slots": 0, OMIT "orb_pool", and do NOT use channel_orb / evoke / gain_orb_slot \
/ focus anywhere — they do nothing without orb slots.

THE ORB POOL (orb classes only — this is how a class invents its OWN elements): an orb class declares \
"orb_pool", an ORDERED list of the orbs it channels. Each entry is EITHER a base orb name string \
("lightning"/"frost"/"dark") OR a CUSTOM orb you invent: an object {{ "name", "passive_val", "evoke_val", \
"passive": [orb-effects], "evoke": [orb-effects] }}. This gives three modalities — base-only (all strings), \
MIXED (strings + custom), or all-custom — pick what fits the fantasy. **Up to 3 custom orbs per class.** A \
custom orb's "passive" fires EVERY turn (keep its numbers SMALL) and its "evoke" is the one-shot burst \
(bigger). Each is a list of orb-effects {{ "op", "amount", "target", ... }} where target is "self" / "enemy" / \
"all_enemies" — orbs CAN hit enemies (unlike triggers). Allowed orb-effect ops: `damage` (target enemy or \
all_enemies), `apply_status` (a self-buff on "self", OR a debuff vulnerable/weak/frail/poison on enemy/ \
all_enemies), `block`/`draw`/`gain_energy`/`heal`/`gain_orb_slot` (always "self"), `channel_orb` (chain another \
pool orb). "passive_val"/"evoke_val" are the HUD numbers (Focus scales them; set them to the orb's main damage/ \
block). You MAY also give a custom orb a "hue" (0.0–1.0) for its color (e.g. fire ≈0.03, poison ≈0.3, ice \
≈0.55); otherwise each gets a distinct auto color. Cards channel a pool orb BY NAME — write the brief as "channel an Ember orb" and the card will emit \
channel_orb orb:"ember" (the orb's name LOWERCASED), or "channel a lightning orb"; `orb:"random"` rolls only \
THIS class's pool. Make each custom orb express the class fantasy (e.g. a fire orb that sears an enemy each turn \
and bursts all enemies on evoke; an ash orb that shields you each turn and corrodes foes on evoke). Example: \
"orb_pool": [ "lightning", {{ "name": "Ember", "passive_val": 2, "evoke_val": 8, \
"passive": [ {{"op":"damage","amount":2,"target":"enemy"}} ], \
"evoke": [ {{"op":"damage","amount":8,"target":"all_enemies"}} ] }} ].

THE SLOT-MACHINE ARCHETYPE (a premier orb design — reach for it when the concept is luck/gambling/chaos/RNG, \
or just to make an orb class exciting): channel RANDOM orbs (`channel_orb` with `orb:"random"`, often \
`amount` 2-3 = a "pull"), then pay off the JACKPOT with effects guarded by `when:{{kind:"orbs_match"}}` — the \
big damage / debuffs / Block that fire only when the pulled orbs all come up the same type. Briefs for this \
archetype should pair "pull random orbs" cards with "if your orbs match, <something great>" payoff cards \
(`orbs_match` is the jackpot; `orb_count_ge` rewards filling slots). Conditional payoffs are swings, so put \
the splashy numbers at uncommon/rare. Conditions also work OFF the orb engine on ANY class — \
`when:{{kind:"hp_below_half"}}` (execute), `when:{{kind:"no_block"}}` (reward aggression), \
`when:{{kind:"target_has_status", status:"poison|vulnerable|weak|frail"}}` (follow-up) — use these to give a \
card a real "if X then bonus" twist instead of a flat stat line. `orbs_match`/`orb_count_ge` are ORB-CLASS \
ONLY; the other three are generic.

TRIGGERS / POWER ENGINES (`add_trigger`): a `power`-type card can grant an ONGOING effect that fires every turn \
— "At the end of your turn, gain Block" (Metallicize), "…gain Strength" (a Demon-Form ramp), "At the start of \
your turn, draw 1 and gain 1 energy" (a tempo engine), an orb auto-channeler, etc. Use a brief like "power: at \
end of turn, gain N Block" or "power: each turn start, draw a card". The per-turn payload is SELF/orb-only \
(block/draw/energy/heal/lose_hp/self-buffs/orb ops — NO targeted damage or enemy debuffs), and may be gated by a \
fire-time condition (e.g. "…if your orbs match, gain Focus"). These are the build-around RARES/uncommons that \
make a class snowball; give most classes one or two. Keep per-turn numbers small (they compound). A trigger \
payload's numeric effect may also `scale` to "cards_retained" (e.g. "power: at end of turn, gain Block equal \
to cards retained") — see SCALED AMOUNTS below.

SCALED AMOUNTS / RETAIN PAYOFF (`scale`): a damage/block/draw card effect can make its amount a LIVE value \
instead of a fixed number by adding `"scale": "<source>"` (keep a nominal "amount"; it is ignored). Sources: \
"cards_in_hand" (other cards in hand), "cards_retained" (cards you HELD into this turn = your hand at turn \
start), "unspent_energy_last_turn", and "x" (X-cost only). Reach for these — especially "cards_retained" plus \
the `retain` keyword and the `retained_last_turn`/`hand_size_ge` conditions — when the concept's fantasy is \
PATIENCE / coiling / holding cards back for a big release (a duelist who waits for the opening, a sniper, a \
hoarder). A signature Retain archetype = cheap/zero-cost cards with `retain`, payoffs that `scale` to \
cards_retained or are gated `when:{{"kind":"retained_last_turn"}}` / `when:{{"kind":"hand_size_ge","value":N}}`, \
and maybe a power that each turn gains Block equal to cards retained. At most one scaled damage/block per card.

PRECISION READS (small, high-leverage scalars/gates — reach for one only when the concept invites it; never \
sprinkle): LIFESTEAL — a `damage` card may then `heal` for the UNBLOCKED damage it just dealt via \
`scale:"damage_dealt_unblocked"` on the heal (put the heal AFTER the damage on the SAME card): the Reaper — "Deal \
8 damage to ALL enemies. Heal HP equal to the unblocked damage dealt." FLECHETTES — a `damage` card may deal \
damage equal to the debuffs on its target via `scale:"target_debuff_count"` (pairs with a Vulnerable/Weak/Frail/\
Poison shell — more debuffs, bigger hit). GRAND FINALE — gate a splashy rare behind \
`when:{{"kind":"draw_pile_empty"}}` (fires only once you've drawn your whole deck; pair with heavy draw). \
HP-SPENT THRESHOLD (Ice Shatter) — gate a payoff on `when:{{"kind":"hp_lost_ge","value":N}}` (true once you've \
lost N+ HP THIS turn, 1-15): pair a self-damage `lose_hp` fuel effect earlier on the card with the gated payoff \
("Lose 3 HP. Deal 18 damage if you've lost 3+ HP this turn.").

TAGGED SYNERGY (`tags` + `scale:"tag_cards_owned"` — the Perfected-Strike / strikes-matter identity): reach for \
this when the concept's fantasy is a DRILLED, repeated technique — many copies of one kind of card that reward \
owning them. TWO parts: (1) TAG A FAMILY — give 3-5 cards of the class the SAME lowercase `"tags":["<slug>"]` (1-2 \
slugs per card; purely a label, no behavior). (2) PAYOFFS — add 1-2 damage/block cards carrying \
`scale:"tag_cards_owned"` + a matching `"tag":"<slug>"`, which deal/block their printed `amount` PLUS 1 per tagged \
card you own ("Deal 6 damage, plus 1 per 'strike' card you own."). A payoff whose tag is on fewer than 2 cards is \
near-dead — always build out the tag family (the pipeline warns otherwise).

TOKEN GENERATION (`add_card` — the compost / conjurer loop): a card may GENERATE combat-transient copies of one \
of THIS class's OWN cards into a pile — `{{"op":"add_card","card_id":"<a card id from this class>","pile":"hand"|\
"discard"|"draw","amount":1-3}}` (copies vanish at combat end; never enter the deck). Reach for it on \
combo/engine concepts: conjure cheap attacks into hand, or — the COMPOST loop — put it inside a power's \
`add_trigger` payload so "what burns returns" ("Whenever a card is Exhausted, add a copy of Cinder to your \
discard pile" pairs `on_exhaust` with `add_card`). LOOP DISCIPLINE (hard): keep amounts small (1-2); the \
referenced card must NOT itself `add_card`; and NEVER make a 0-cost card that re-adds ITSELF to hand (a one-card \
engine) — send self-copies to the DISCARD pile (the Anger pattern) or charge a real price. `add_card` is \
CLASS-ONLY (it copies your class's own cards).

RAMPAGE (`grow` — an attack that grows as you replay it): a `damage` card may carry `{{"op":"damage",\
"amount":8,"grow":5}}` so its damage climbs by `grow` EACH time you play THIS card this combat (first play = \
printed amount; it shows its current damage in hand). base-StS Rampage. Reach for it on aggro/combo concepts \
built around ONE signature weapon; give a grow attack cheap DRAW/RETAIN support so it recurs, and keep it to \
1-2 grow cards per class (identity, not wallpaper). Rules: `grow` is DAMAGE-ONLY, 1..9, must be <= `amount`, and \
can't combine with `scale` (it IS the card's one calculated value). NOT `forge`: `grow` is ONE card feeding \
itself; Forge is a CLASS-level counter many cards pump into a `scale:"forged"` payoff.

IN-RUN UPGRADE (`upgrade_card` — sharpen your tools mid-fight, the Armaments fantasy): a skill may carry \
`{{"op":"upgrade_card","cards":"choose"}}` (YOU pick one upgradable card in hand — the true Armaments feel, the \
best default), `"cards":"random"` (one random upgradable card), or `"cards":"all"` (every upgradable card in hand — \
a strong uncommon+). COMBAT-SCOPED: upgrades last this combat only, so pair with RETAIN or big/refilling hands so \
an upgraded card sticks around to matter. A rare power may carry a `turn_start` → `upgrade_card` (`random` only) \
payload for a slow-burn engine. 1-2 upgrade cards per class. No amount.

DECK-THINNING (`purge` / `purge_card` — thin your deck forever): a strong one-shot skill/attack may carry the \
flag-op `{{"op":"purge"}}` — when played, THAT card leaves your RUN DECK for the rest of the run (a permanent, \
stronger `exhaust` that never comes back); over-stat it for its cost (you only get it once). OR use the op \
`{{"op":"purge_card"}}` — when played, the PLAYER chooses a card in hand and purges THAT card (targeted \
deck-thinning: cut a Basic, a Curse, or a dead draw); the purge_card card itself stays, so it can be a repeatable \
skill, and it pairs naturally with a normal cost/stat line. Reach for either on combo / lean-engine concepts where \
the fantasy is sharpening the deck toward a few key cards; keep it to 1-3 per class total. Rules: `purge` and \
`exhaust` are MUTUALLY EXCLUSIVE on one card; NEVER put `purge`/`purge_card` on a basic (Strike/Defend). No \
amount/target on either.

DISCARD / HAND-CHURN (`discard` + `on_discard` — throw cards away for value): reach for this when the fantasy is \
recklessness / gambling / sifting / a hand you deliberately churn. TWO parts: (1) `discard` INCOME — `{{"op": \
"discard","amount":1}}` discards random cards from your hand (a cost/enabler; put it on cheap attacks as a rider, \
or in a power's `turn_start` payload for forced churn: "At the start of your turn, discard 1"). Pair discard with \
DRAW so you refill (discard without draw just shrinks your hand). (2) `on_discard` PAYOFFS — the Reflex payoff: a \
card carrying `{{"op":"add_trigger","trigger":"on_discard","effects":[...]}}` fires its payload when THAT card is \
DISCARDED BY AN EFFECT (not when played, not at end-of-turn cleanup). Design these as discard FUEL — cards you \
WANT to throw away: "Whenever this card is discarded, gain 6 Block" / "…draw 2" / "…deal 8 to a random enemy" \
(payload may target). Keep it in hand and discard it for the value. A discard class ships discard income at common \
+ a couple of on_discard fuel cards + a churn engine power (turn_start discard) at uncommon/rare. (3) `scry` — \
`{{"op":"scry","amount":3}}` lets the player look at the top N of the DRAW pile and discard any (a draw-quality \
filter; typical N 2-5). Scry-discards ALSO trigger `on_discard`, so a scry card doubles as controllable discard \
FUEL (choose exactly which fuel card to pitch) — put a `scry` skill in any discard/`on_discard` class, and it also \
fits sifting/foresight concepts on its own. Card-only (no repeating-trigger scry).

CORRUPTION (`corruption` — your Skills cost 0 but Exhaust when played): reach for this when the fantasy is \
RECKLESS TEMPO / spending yourself / a Faustian bargain — a burst of free skills at the cost of burning them. ONE \
power (or skill) carries the flag-op `{{"op":"corruption"}}`; while it is active this combat every SKILL you play \
costs 0 but Exhausts. Build AROUND it: (1) SKILL DENSITY — a corruption class wants lots of cheap-ish Skills \
(block, draw, apply_status utility) that become free spam once Corruption is up. (2) AN EXHAUST PAYOFF — the free \
Skills all Exhaust, so pair with an `on_exhaust` engine (gap #13: a power whose `add_trigger` trigger `on_exhaust` \
payload gives Block/draw each time a card Exhausts — Feel No Pain / Dark Embrace). The exhausting free Skills FEED \
that engine. Rules: put `corruption` on a POWER or SKILL (never an attack); ONE per class (it is a binary power — \
a second grant does nothing); card-only (never in a trigger payload).

METAMORPH (`transform_card` — a card that PERMANENTLY becomes another of your cards mid-run): reach for this when \
the fantasy is a SHAPE THAT LEARNS / a weapon that reconfigures / a circuit that rewrites itself — the deck \
literally changes as the run goes on. A card carries `{{"op":"transform_card","card_id":"<a DIFFERENT card in \
this class>"}}`; when played it permanently BECOMES that card for the rest of the run (the run-deck copy is \
swapped, so it's the new card in every later combat). TWO shapes: \
 (1) RANK-UP — a weak/cheap card that transforms into a strong one, ideally behind a `when` gate so it "earns" the \
    upgrade ("Deal 6 damage. Transforms into Molten Edge once you've forged 10." — put `"when":{{...}}` on the \
    transform_card effect; use whatever condition fits the concept). The caterpillar→butterfly. \
 (2) MODE-SWAP — TWO cards that each `transform_card` into the OTHER (A→B and B→A): a stance / weapon-mode toggle \
    the player flips between (a precise mode ↔ a heavy mode). This is the ONE case a transform target may itself \
    carry transform_card — because it swaps straight BACK. \
 (3) GRAFT (`graft_card` — the CHOOSE form: transform a card the PLAYER PICKS): a card carrying \
`{{"op":"graft_card","card_id":"<a STRONG card in this class>"}}`, when played, lets the player pick a card in \
HAND and permanently reforges THAT picked card into card_id for the rest of the run (as `purge_card` is the \
targeted `purge`). The "prune & graft" fantasy — CUT a weak/Basic/dead draw and GRAFT it into one of your payoffs \
(a gardener grafting a cutting; a smith reforging scrap into a blade). Pairs with a class that has a weak Basic or \
generates junk. \
RULES (hard): the target is always a DIFFERENT same-class card (never itself — that's a no-op); NEVER build a \
CHAIN A→B→C (a target may carry transform_card ONLY if it swaps back — the runtime refuses a real chain, so it'd \
be a dead op; the pipeline warns); never on a BASIC card; transform_card/graft_card are mutually exclusive with \
`purge`/`purge_card` (transform/graft BECOME a card, purge DELETES it); one per card; card-only (never in a \
trigger payload); keep transform_card + graft_card together to 1-3 per class.

THE FORGE / SIGNATURE-BLADE ARCHETYPE (`forge` + the SIGNATURE BLADE — the base-game Forge keyword): reach for \
this when the concept's fantasy is a SMITH / craftsman / a signature weapon or technique that GROWS over the \
fight — "my blade gets stronger every time I stoke it", ramp you feel hit-by-hit. This is how the base game \
builds a Forge class — design AROUND these four beats, don't just sprinkle the op:
 1. THE BLADE IS THE WIN CONDITION. It is NOT in your deck — your FIRST Forge of each combat CREATES it in your \
    hand (a 2-energy token attack that Retains and deals its printed base PLUS your Forge). Give a forge class \
    EXACTLY ONE `signature_blade` card (role "signature_blade", deck_count 1): NAME and THEME it as this class's \
    weapon (a war-hammer, a hexblade, a growing incantation). You do NOT spell out its effects — the harness \
    builds the blade (summoned-on-first-Forge + Retain + damage + your Forge) as a never-drafted token.
 2. INCOME IS THE CURVE. Numeric `forge` riders spread across CHEAP COMMONS ("Deal 5 damage. Forge 3." — small \
    numbers, Forge 1-3; it compounds) + AT LEAST ONE engine source (a power whose `add_trigger` turn_start \
    payload Forges each turn, e.g. "at the start of your turn, Forge 2" — that trigger income IS the engine, and \
    a turn-1 turn_start Forge is what summons the blade) + optionally a rare big-stoke spike.
 3. MANIPULATION IS THE TEXTURE (REQUIRED — ship AT LEAST ONE card that touches the blade itself, beyond plain \
    income). In-vocab means: `summon_blade` (retrieval — "Put your blade into your hand from anywhere", the \
    Summon-Forth pattern; great on a cheap skill or a rare) OR an `on_blade_played` trigger rider (a power: \
    "Whenever you play your blade, gain 8 Block / draw a card / gain 1 energy" — the Parry pattern). A forge \
    class with income but NO blade interaction plays flat.
 4. PAYOFFS STAY CONCENTRATED. The blade is the PRIMARY forged payoff; ship AT MOST ONE extra `scale:"forged"` \
    card at uncommon/rare (write it "deal 6 damage, plus your Forge"), optionally gated behind \
    `when:{{"kind":"forged_ge","value":N}}` ("if your Forge is 10+, …") as the archetype's rare finisher. \
    OPTIONAL BURST: one `{{"op":"blade_empower","amount":2}}` (or 3) skill/power — "Your blade deals 2x damage \
    this turn" — a spike distinct from the slow ramp (cash a big Forge in one swing). Forge-class only (it needs \
    the blade); card-only; 1 per class.
The counter resets each combat. A forge class MUST ship its ONE signature_blade, real Forge income, AND ≥1 \
blade-manipulation card; NEVER sprinkle `forge` onto a class whose identity is elsewhere, and non-forge classes \
ship NO signature_blade / summon_blade / on_blade_played.

THE BALANCE ARCHETYPE (`balance_step` + the Balance gauge — a dual-pole class axis): reach for this when the \
concept's fantasy is DUALITY / a tug-of-war between two opposed forces — light vs dark, order vs chaos, calm vs \
fury, life vs death. The identity anchor is the BALANCE GAUGE: a SIGNED per-combat counter with two opposite \
ends (Light and Dark; 0 = centered), moved with the `balance_step` op ({{"op":"balance_step","pole": \
"light"|"dark","amount":1-5}} = "Shift N toward the Light/Dark"). Ship the ENGINE: INCOME on BOTH poles at \
common (small steps, 1-3 — the gauge is a slow tug-of-war), including inside a power's `add_trigger` payload \
("power: at the start of your turn, shift 2 toward the Dark" — that trigger income IS the engine). PAYOFFS gate \
on the gauge at uncommon/rare via `when`: {{"kind":"dark_ge","value":N}} / {{"kind":"light_ge","value":N}} \
("if your Dark is 5+, deal +damage / gain +block" — a leaning-pole payoff) and the knife's-edge \
{{"kind":"centered","value":N}} ("if you are centered (within 2), …" — a rare that rewards NOT committing to a \
pole). The gauge BITES at the extremes: while |gauge| >= 8, each turn-start the leaning pole penalizes you (the \
Dark drains 3 HP, the Light inflicts 1 Weak) — so leaning hard is a real commitment, never free. A BALANCE \
class MUST have income on BOTH poles AND at least one pole- or centered-gated payoff (a one-pole gauge is just \
Forge with extra steps); NEVER sprinkle a lone `balance_step` onto a class whose identity is elsewhere. The \
gauge resets each combat.

THE STATUS POOL (optional — this is how a class invents its OWN signature buff/debuff): a class may declare \
"status_pool", up to 4 CUSTOM statuses that ARE the class identity (like Strength/Vulnerable, but yours). Each is \
a MODIFIER — while active it changes ONE number — and cards apply it BY NAME with the `apply_status_custom` op \
(amount = stacks). Reach for this when the concept's fantasy is a signature condition (a duelist's "Razor Focus", \
an alchemist's "Corrosion", a monk's "Flow") rather than orbs or generic statuses. Each entry is an object: \
{{ "name", "emoji" (a single emoji), "type": "buff"|"debuff", "hook": <which number>, "decay": <how it fades>, \
"description" }}. The `hook` (and its REQUIRED side) is one of: `damage_dealt` (BUFF — your attacks deal +stacks \
damage, Strength-like), `damage_taken` (DEBUFF — the afflicted enemy takes +stacks damage, a Brittle/expose), \
`block_gained` (BUFF — +stacks Block when you gain Block, Dexterity-like), `energy_gain` (BUFF — +stacks energy \
per turn), `card_draw` (BUFF — draw +stacks cards). `decay` is "none" (permanent), "lose_one_eot" (−1 stack at end \
of your turn), or "lose_all_eot" (clears at end of your turn). BUFFS are applied by SELF-target cards (worded \
"Gain N <Name>"); the single DEBUFF hook (damage_taken) by ENEMY-target cards ("Apply N <Name>"). Card briefs \
apply them by name: write "gain 2 Razor Focus" or "apply 2 Brittle to the enemy" and the card emits \
apply_status_custom status_name:"Razor Focus". Keep numbers SMALL (these fire every relevant event). Example: \
"status_pool": [ {{ "name": "Razor Focus", "emoji": "\U0001F5E1", "type": "buff", "hook": "damage_dealt", \
"decay": "none", "description": "Your attacks deal bonus damage equal to its stacks." }} ]. A class can combine \
a status_pool with normal cards (mixed) or build its whole identity on its statuses. apply_status_custom is \
STATUS-CLASS ONLY (a class that declared a status_pool); never use it otherwise.

THE SUMMON POOL (optional — this is how a class invents its OWN minion): a class may declare "summon_pool" with \
EXACTLY ONE custom summon — an Osty-style bodyguard. Reach for this when the concept's fantasy is a \
NECROMANCER / beastmaster / conjurer / commander who fights THROUGH a single loyal minion rather than orbs, \
statuses, or raw cards. The minion works EXACTLY like the base game's Osty: ONE on board at a time; it is PASSIVE \
(it does NOTHING on its own turn); it is a MEAT-SHIELD with an HP bar that soaks the enemy hits aimed at you; it \
clears at combat end. The class's OFFENSE comes from cards that strike THROUGH the minion. The pool entry is just \
{{ "name", "max_hp" (1-60, its starting HP), "description" }} — NO moves, NO attackable flag, NO on_summon / \
on_death. Three card ops drive the minion (all SUMMON-CLASS ONLY):
  • `summon` (summon_name:"<the minion>", amount = HP): the base-game Summon keyword. If the minion is NOT on \
    board, summon it with `amount` HP (omit amount to use its max_hp). If it IS already on board, this instead \
    RAISES its Max HP by `amount` (grow it — exactly like base-game Osty). Cards: "summon your Thrall (8 HP)" or, \
    to scale it, "raise your Thrall's HP by 6". Usually a self-target skill.
  • `summon_attack` (amount per-hit, optional "hits"): deal damage THROUGH the minion — the MINION is the \
    attacker, so it scales with the minion's Strength (a base-game "Osty attack"). Does nothing if the minion \
    isn't out. This is how a summon class deals its damage. Put it on attack cards (single-target, or all-enemies \
    if the card is AoE). Card brief: "your summon strikes for 9" or "your summon hits all enemies for 5".
  • `buff_summon` (amount, optional "status" — a self-buff, default strength): buff the living minion so its \
    summon_attacks hit harder (or make it tankier with block-type buffs). Does nothing if the minion isn't out. \
    Card brief: "your summon gains 3 Strength".
  • `heal_summon` (amount 1-9) / `shield_summon` (amount 1-12): the SELFLESS medic ops — spend a card to heal your \
    minion's HP or give it Block, keeping your bodyguard alive when enemies target it. Do nothing if the minion \
    isn't out. Both also work inside `add_trigger` payloads (a per-turn medic engine: "at the start of your turn, \
    heal your summon 3"). Optional support for a summon class — reach for them when the fantasy is a protected/ \
    nurtured ally; a lone medic card with no `summon` to heal is dead (the pipeline warns).
The loop is: summon the minion (and grow its HP), buff it (Strength), then strike through it with summon_attack — \
its Strength makes those hits scale, while it body-blocks for you. Build attack cards around summon_attack and \
skills around summon / buff_summon. \
REQUIRED — the minion is PASSIVE and NEVER attacks on its own, so `summon_attack` is the ONLY way it deals damage \
and the ONLY thing that makes `buff_summon` worth anything: a summon class MUST include SEVERAL summon_attack cards \
(make them the bulk of its attacks — at minimum one per archetype), and must NEVER ship buff_summon (or Strength on \
the minion) without summon_attack cards to spend it on (Strength with no summon_attack is dead weight). Roughly \
balance the kit so summon_attack cards clearly outnumber buff_summon cards. \
Example: "summon_pool": [ {{ "name": "Bone Thrall", "max_hp": 12, \
"description": "A raised servant that guards you and strikes at your command." }} ], with cards like \
{{"op":"summon","summon_name":"Bone Thrall","amount":12}} (a skill), \
{{"op":"summon_attack","amount":9}} (an attack), and {{"op":"buff_summon","amount":3,"status":"strength"}} (a skill). \
summon / summon_attack / buff_summon are SUMMON-CLASS ONLY (a class that declared a summon_pool); never use them otherwise.

STRATEGIC LINES (REQUIRED — this is what makes a class DRAFTABLE, not just playable): a real class supports \
MORE THAN ONE way to win, and the player picks a lane mid-run from the cards the Spire offers — base-game \
Ironclad drafts Strength aggro OR block-matters control OR an exhaust/0-cost combo engine from ONE pool. Weave \
2-3 strategic lines through this pool: "aggro" (maximize offense, win fast before enemies scale), "control" \
(survive and outlast — a control line ALWAYS needs a named FINISHER or it stalls with no way to close), and \
"combo" (assemble specific pieces into an engine that pops off — exhaust thinning, draw/energy tempo, retain, \
0-cost cards, `when`-gated payoffs are its parts). Tag every pool card with the line it PRIMARILY serves via \
"strategy": "aggro" | "control" | "combo" | null (null = generic glue that any deck drafts). Each line needs a \
real PACKAGE: enablers at common, amplifiers at uncommon, and AT LEAST ONE RARE FINISHER — rares are the \
wincons a player builds toward (think Barricade / Demon Form / Corruption, expressed in THIS vocabulary). The \
two archetypes should serve DIFFERENT mixes of lines: that is the tension made real, and it is what separates \
a deep class from a pile of synergies.

# THE BLUEPRINT FORMAT (output EXACTLY this shape, a single JSON object, nothing else)
{{
  "name": "<= 24 chars",
  "description": "<= 160 chars, the class fantasy",
  "max_hp": 70,
  "orb_slots": 0,
  "orb_pool": [],
  "status_pool": [],
  "summon_pool": [],
  "archetypes": [
    {{ "id": "snake_case", "name": "Short Name", "description": "the engine, in vocabulary terms" }},
    {{ "id": "snake_case", "name": "Short Name", "description": "the engine, in vocabulary terms" }}
  ],
  "cards": [
    {{ "role": "basic_attack", "name_hint": "Strike", "type": "attack", "rarity": "basic", "cost": 1, "deck_count": 5, "archetype": null, "theme": "the literal Strike" }},
    {{ "role": "basic_skill",  "name_hint": "Defend", "type": "skill",  "rarity": "basic", "cost": 1, "deck_count": 4, "archetype": null, "theme": "the literal Defend" }},
    {{ "role": "signature", "name_hint": "...", "type": "attack|skill|power", "rarity": "basic", "cost": 0-3, "deck_count": 1, "archetype": "<id>", "theme": "the class-defining starter card, concrete and vocabulary-only" }},
    {{ "role": "signature_blade", "name_hint": "...", "type": "attack", "rarity": "token", "cost": 2, "deck_count": 0, "archetype": "<id>", "theme": "FORGE CLASSES ONLY — name/theme this class's growing signature weapon; the harness builds its effects (summoned to hand on your first Forge, retained, damage + your Forge). NOT in the starting deck." }},
    {{ "role": "pool", "name_hint": "...", "type": "...", "rarity": "common|uncommon|rare", "cost": 0-3, "deck_count": 0, "archetype": "<id>", "strategy": "aggro|control|combo|null", "bridge": false, "theme": "a concrete one-line design using ONLY the vocabulary" }}
  ]
}}

RULES:
- EXACTLY one basic_attack (deck_count 5) and one basic_skill (deck_count 4); name them "Strike"/"Defend" — \
the harness synthesizes those two verbatim, so spend no design effort there.
- One or two `signature` cards (rarity "basic", deck_count 1) — the class's identity, in the starting deck.
- A FORGE class (and ONLY a forge class) adds EXACTLY ONE `signature_blade` card (rarity "token", deck_count 0): \
name/theme its growing signature weapon; the harness builds the blade's effects. It is NOT in the starting deck — \
your first Forge each combat summons it to hand. A forge class MUST ALSO ship ≥1 blade-manipulation card (a \
`summon_blade` retrieval or an `on_blade_played` trigger power). See THE FORGE / SIGNATURE-BLADE ARCHETYPE. \
Non-forge classes ship NONE of these.
- `pool` cards (deck_count 0) are the class's REWARD POOL — mirror a base class scaled ~half: about \
{TARGET_COMMONS} commons (enablers), {TARGET_UNCOMMONS} uncommons (amplifiers), and {TARGET_RARES} rares \
(payoffs — bigger numbers / more effects, still vocabulary-only), spread across BOTH archetypes. At LEAST \
{MIN_RARES} rares is REQUIRED: a boss card reward rolls a Rare and the run SOFT-LOCKS if the class has no \
Rare available, so never ship fewer.
- STRATEGIC LINES (REQUIRED): tag each pool card with the "strategy" it primarily serves ("aggro"/"control"/\
"combo", or null for generic glue). At least TWO distinct strategies must each get a full package: >={_LINE_MIN_CARDS} \
tagged cards including >=1 rare finisher. A control line MUST include its finisher among those rares.
- BRIDGE CARDS (REQUIRED — this is what makes the two archetypes ONE class, not two half-decks stapled \
together): at least {MIN_BRIDGES} pool cards must be FUSION cards that combine BOTH archetypes' engines in a \
SINGLE card (touch a signature mechanic of EACH — not one engine or the other). Mark each with "bridge": true, \
and make AT LEAST ONE of them a RARE (the fusion's poster card). Weave them across the pool; a bridge still \
carries a "strategy" tag and counts toward that line.
- Every `theme` is a concrete, mechanically explicit one-liner the card generator can build from the \
vocabulary (numbers optional). Reference the archetype's engine.
- REPRINT HOMAGE (REQUIRED): exactly ONE pool card is a faithful recreation of a REAL card from base \
Slay the Spire 2 — keep its name, and rebuild its exact effect from THIS vocabulary. Pick an iconic \
base card that expresses cleanly in the vocabulary (e.g. Deflect: 0-cost skill, gain 4 Block; Slice: \
0-cost attack, deal 6 damage; Bludgeon: 3-cost attack, deal 32 damage) and that flatters this class's \
engine. Make it a COMMON, and write its theme as 'Reprint of <Name> (base game): <the original \
effect, spelled out concretely>'. One familiar face among the strangers grounds the class for \
returning players.
- Total pool is about {TARGET_POOL} cards (+ the 2 basics + 1-2 signatures) — a base-class-sized pool plays \
like a real class, not a demo. Output ONLY the JSON object.
- MERCHANT RULE (REQUIRED): the in-game shop builds one card entry per card TYPE — Attack, Skill, AND Power — \
from the class's NON-basic pool, so every class MUST include at least one non-basic (common/uncommon/rare) card \
of EACH type: ≥1 Attack, ≥1 Skill, and ≥1 Power. A class with no non-basic Power card hangs the game at a \
merchant. Powers are the build-around engines (use `add_trigger` per-turn effects, or a lasting self-buff like \
Strength/Dexterity) — give every class one or two regardless of theme.
- "orb_slots": 0 for a normal class; 3-4 ONLY for an orb class (then one archetype must be the orb engine).
- "orb_pool": [] for a normal class; for an orb class, list every orb it channels — base name strings and/or \
up to 3 custom orb objects (see THE ORB POOL). Channel-card briefs must reference orbs by their pool name.
- "status_pool": [] unless the class's identity is its OWN signature buff/debuff(s); then declare up to 4 custom \
statuses (see THE STATUS POOL) and have cards apply them by name (apply_status_custom). Only a class with a \
status_pool may use apply_status_custom. Buff statuses ride self-target cards; the damage_taken debuff rides \
enemy-target cards.
- "summon_pool": [] unless the class's identity is fighting THROUGH its OWN minion; then declare EXACTLY ONE custom \
summon (see THE SUMMON POOL) and drive it with summon / summon_attack / buff_summon. Only a class with a \
summon_pool may use those ops; summon / buff_summon ride self-target skills, summon_attack rides attack cards."""

    _POOL_ASK = (f"Give it a base-class-sized reward pool: about {TARGET_COMMONS} commons, "
                 f"{TARGET_UNCOMMONS} uncommons, and {TARGET_RARES} rares (~{TARGET_POOL} pool cards), split "
                 f"across the two archetypes, plus the two basics and 1-2 signatures. At least {MIN_RARES} "
                 "rares is REQUIRED. Weave in the strategic lines: tag pool cards with \"strategy\" so at "
                 f"least two distinct strategies each get >={_LINE_MIN_CARDS} tagged cards including >=1 "
                 "rare finisher. Include the required reprint homage: one COMMON pool card faithfully "
                 "recreating a real base-game card, its theme written as 'Reprint of <Name> (base game): "
                 f"<original effect>'. Include at least {MIN_BRIDGES} BRIDGE cards (\"bridge\": true) that "
                 "fuse BOTH archetypes' engines into one card, at least one of them a rare.")

    def user_brief(self, brief) -> str:
        return self._dossier_brief(brief) if self.mode == "dossier" else self._concept_brief(brief)

    @staticmethod
    def _featured_ask(brief) -> str:
        """Phase N-2: the rolled featured-mechanic REQUIRED block for this concept (empty if none)."""
        from .featured import injection_block
        return injection_block(getattr(brief, "featured", None))

    @staticmethod
    def _recency_status() -> str:
        """Phase N-4: a status-focused 'recently overused' nudge from the cross-forge ledger (guarded —
        a missing/corrupt ledger yields an empty string, never an error)."""
        try:
            from . import ledger
            return ledger.blueprint_status_line(ledger.read_window())
        except Exception:
            return ""

    def _concept_brief(self, brief: ClassBrief) -> str:
        return (f'Design a new playable class from this player concept:\n"{brief.concept.strip()}"\n\n'
                f"{self._POOL_ASK}{self._featured_ask(brief)}{self._recency_status()}\n"
                "Return only the JSON blueprint object.")

    def _dossier_brief(self, brief) -> str:
        """mode='dossier': the staged front-end has ALREADY decided the identity (name, fantasy, two archetypes
        in tension, the class_kind, a keystone relic intent). Your job is the part the blueprint stage is good
        at: turn that into validated card briefs + any pools, using the SAME output shape and ALL the rules."""
        c = brief.candidate
        kind_guidance = {
            "orb": ('This is an ORB CLASS: set "orb_slots" to 3 or 4, declare an "orb_pool" (base orbs and/or up '
                    'to 3 custom orbs — see THE ORB POOL), and make ONE archetype the orb engine.'),
            "status": ('This is a STATUS CLASS: declare a "status_pool" (up to 4 custom statuses — see THE STATUS '
                       'POOL) and have cards apply them by name with apply_status_custom. "orb_slots": 0.'),
            "summon": ('This is a SUMMON CLASS: declare a "summon_pool" with ONE passive Osty-style minion (see THE '
                       'SUMMON POOL); cards summon / summon_attack / buff_summon it. "orb_slots": 0.'),
            "normal": ('This is a NORMAL class: "orb_slots": 0, OMIT orb_pool/status_pool/summon_pool, and do not use '
                       'their class-only ops.'),
        }.get(c.class_kind, "")
        archs = "\n".join(f'- {aid}: {desc}' for aid, desc in zip(c.archetype_ids, c.archetype_descs))
        relic = ""
        if brief.relic_intent:
            ri = brief.relic_intent
            relic = (f'\nKeystone relic intent (its relic is designed separately — let it INFORM the card briefs\' '
                     f'feel, do not build a relic here): "{ri.get("name", "")}" — {ri.get("effect_sketch", ri.get("fantasy", ""))}')
        skin = ""
        sk = getattr(brief, "skin", None) or {}
        if sk.get("imagery") or sk.get("flavor"):
            flav = ", ".join(sk.get("flavor") or []) or "the theme"
            img = ", ".join(sk.get("imagery") or [])
            skin = (f'\nFLAVOR SKIN — the MECHANICS above come from the subject; DRESS this class in its flavor. '
                    f'Name the class and its cards to evoke {flav}, drawing on this imagery for names and feel '
                    f'(do NOT let it change any mechanics): {img}.')
        # The compose stage declared the candidate's strategic lines — the pool must build a package for each.
        lines = ""
        lns = [l for l in (getattr(c, "strategic_lines", None) or []) if isinstance(l, dict)]
        if lns:
            rows = "\n".join(f'- {str(l.get("strategy", "?")).strip().lower()}: {l.get("line", "")}'
                             + (f' (win condition: {l.get("win_condition")})' if l.get("win_condition") else "")
                             + (f' [plays like: {l.get("idiom")}]' if l.get("idiom") else "")
                             for l in lns)
            lines = ('\nIts STRATEGIC LINES (build a package for EACH — enablers at common, amplifiers at '
                     'uncommon, >=1 rare FINISHER — and tag the cards with "strategy"):\n' + rows + "\n")
        return (
            "A staged design front-end has already chosen this class identity. Build its blueprint — the card "
            "briefs and any pools — faithfully to it. Do NOT rename it or change its archetypes.\n\n"
            f'Name (use EXACTLY): "{c.name}"\n'
            f'Fantasy (this is the description): {c.fantasy}\n'
            f'Suggested max_hp: {c.suggested_max_hp}\n'
            f'Core loop: {c.core_loop}\n'
            f'Weakness: {c.weakness}\n'
            f'The TWO archetypes (in tension — {c.tension or "they pull against each other"}):\n{archs}\n'
            f'{lines}{kind_guidance}{relic}{skin}\n\n'
            f"Use these two archetypes as the blueprint's two archetypes (keep their ids). {self._POOL_ASK}"
            f"{self._featured_ask(brief)}{self._recency_status()}\n"
            "Return only the JSON blueprint object.")

    def repair_message(self, blueprint_text: str, errors: list[str]) -> str:
        bullet = "\n".join(f"- {e}" for e in errors)
        return ("That blueprint failed validation:\n" f"{bullet}\n\n"
                "Here is what you returned:\n" f"{blueprint_text}\n\n"
                "Return a corrected SINGLE JSON blueprint object that fixes every error and still matches the "
                "concept. Output only the JSON object.")

    def fake_output(self, brief) -> dict:
        """Offline blueprint for the staged front-end's --fake path. In dossier mode, seed a valid bp of the
        right class_kind and stamp the chosen identity onto it (so the fake exercises the same downstream)."""
        if self.mode != "dossier":
            return _fake_blueprint(brief)
        c = brief.candidate
        seed = {"orb": "orb", "status": "status", "summon": "summon"}.get(c.class_kind, "")
        bp = _fake_blueprint(ClassBrief(concept=seed))
        bp["name"] = (c.name or bp["name"])[:24]
        bp["description"] = (c.fantasy or bp["description"])[:160]
        bp["max_hp"] = int(c.suggested_max_hp)
        ids = list(c.archetype_ids) or ["a", "b"]
        descs = list(c.archetype_descs) or ["", ""]
        while len(ids) < 2:
            ids.append(f"arch_{len(ids)}"); descs.append("")
        bp["archetypes"] = [{"id": ids[0], "name": ids[0], "description": descs[0]},
                            {"id": ids[1], "name": ids[1], "description": descs[1]}]
        if getattr(brief, "relic_intent", None):
            bp["relic_intent"] = brief.relic_intent
        # The staged path validates the blueprint strictly (real path must pass _validate_blueprint), but the
        # _fake_blueprint seeds are light (the fake=True path relies on the post-gen safety nets). Top up so the
        # fake bp also passes — every merchant type + the rare floor + the candidate's strategic-line packages.
        declared = [l.get("strategy") for l in (getattr(c, "strategic_lines", None) or []) if isinstance(l, dict)]
        return _topup_blueprint_briefs(bp, strategies=declared)


# --- Phase L: the keystone starter relic (constrained to the mod's ForgedRelic runtime) -----------
# These sets MIRROR the C# ForgedCharacters.TryParseRelic gate so generation never emits a relic the mod would
# reject on import (the lockstep discipline). focus is in SelfBuffStatuses (orb-only at runtime; harmless here).
_RELIC_SELF_BUFFS = {"strength", "dexterity", "thorns", "regen", "metallicize", "artifact", "buffer",
                     "intangible", "ritual", "blur", "temp_strength", "temp_dexterity", "barricade", "focus"}
_RELIC_DEBUFFS = {"vulnerable", "weak", "frail", "poison"}
_RELIC_TRIGGERS = {"turn_start", "turn_end", "attacked", "on_exhaust", "on_card_played",
                   "combat_end", "on_card_drawn", "on_damage_dealt", "on_block_gained",
                   "on_hp_lost"}  # L-4 adds the middle four; Phase P adds on_hp_lost (own unblocked HP loss)
_RELIC_EFFECT_OPS = {"damage", "block", "draw", "gain_energy", "heal", "lose_hp", "apply_status",
                     "channel_orb", "summon",  # Phase L compose: channel_orb/summon — CLASS-CONDITIONAL (gated on bp below)
                     "forge"}  # Phase M (gap #36): relic-side Forge income (the smoldering-heirloom keystone)
_RELIC_TARGETS = {"self", "enemy", "all_enemies", "attacker"}  # "attacker" valid only on the "attacked" trigger
_RELIC_CONDITION_KINDS = {"hp_below_half", "no_block",
                          "has_block", "enemy_count_ge", "turn_at_least", "hand_size_ge"}  # L-4 player-state reads
_RELIC_COND_NEEDS_VALUE = {"enemy_count_ge", "turn_at_least", "hand_size_ge"}
_RELIC_MODIFIER_STATS = {"max_energy", "first_attack", "cost_reduction", "start_combat_block"}  # L-4 adds start_combat_block


def _validate_relic(relic, bp=None) -> list[str]:
    """Mirror C# TryParseRelic. When `bp` (the class blueprint) is given, also gate the Phase L compose ops on
    class content: channel_orb requires the class to declare orbs; summon requires the named minion in its pool."""
    errs: list[str] = []
    if not isinstance(relic, dict):
        return ["relic is not an object"]
    # Phase L compose gate (only with class context): which compose ops this class can support, and the legal names.
    has_orbs = bool(bp and (bp.get("orb_pool") or (bp.get("orb_slots") or 0) >= 1))
    summon_names = {str(s.get("name", "")).strip().lower()
                    for s in (bp.get("summon_pool") or [])} if bp else set()
    if not str(relic.get("name", "")).strip():
        errs.append("relic needs a non-empty name")
    hooks = relic.get("hooks") or []
    mods = relic.get("modifiers") or []
    if not isinstance(hooks, list):
        errs.append("relic 'hooks' must be a list"); hooks = []
    if not isinstance(mods, list):
        errs.append("relic 'modifiers' must be a list"); mods = []
    if not hooks and not mods:
        errs.append("relic has no hooks and no modifiers (it would do nothing)")
    for i, h in enumerate(hooks):
        if not isinstance(h, dict):
            errs.append(f"hook[{i}] must be an object"); continue
        trigger = str(h.get("trigger", "")).strip().lower()
        if trigger not in _RELIC_TRIGGERS:
            errs.append(f"hook[{i}] trigger must be one of {sorted(_RELIC_TRIGGERS)}")
        target = str(h.get("target", "self")).strip().lower()
        if target not in _RELIC_TARGETS:
            errs.append(f"hook[{i}] target '{target}' must be self/enemy/all_enemies/attacker")
        if target == "attacker" and trigger != "attacked":
            errs.append(f"hook[{i}] target 'attacker' is only valid on the 'attacked' trigger")
        effs = h.get("effects") or []
        if not isinstance(effs, list) or not effs:
            errs.append(f"hook[{i}] needs a non-empty 'effects' list"); effs = []
        for j, e in enumerate(effs):
            if not isinstance(e, dict):
                errs.append(f"hook[{i}].effects[{j}] must be an object"); continue
            op = str(e.get("op", "")).strip().lower()
            if op not in _RELIC_EFFECT_OPS:
                errs.append(f"hook[{i}].effects[{j}] op '{op}' must be one of {sorted(_RELIC_EFFECT_OPS)}"); continue
            if op == "damage" and target == "self":
                errs.append(f"hook[{i}] 'damage' needs an enemy target (set target to enemy/all_enemies)")
            if op == "apply_status":
                st = str(e.get("status", "")).strip().lower()
                if st not in _RELIC_SELF_BUFFS and st not in _RELIC_DEBUFFS:
                    errs.append(f"hook[{i}].effects[{j}] unsupported status '{st}'")
                elif st in _RELIC_DEBUFFS and target == "self":
                    errs.append(f"hook[{i}] debuff '{st}' needs an enemy target")
            elif op == "channel_orb":
                if not str(e.get("orb", "")).strip():
                    errs.append(f"hook[{i}].effects[{j}] channel_orb needs an 'orb' (\"random\" or a pool orb name)")
                elif bp is not None and not has_orbs:
                    errs.append(f"hook[{i}] channel_orb is only valid for an ORB class (this class has no orbs)")
            elif op == "summon":
                nm = str(e.get("summon_name", "")).strip()
                if not nm:
                    errs.append(f"hook[{i}].effects[{j}] summon needs a 'summon_name'")
                elif bp is not None and nm.lower() not in summon_names:
                    errs.append(f"hook[{i}] summon '{nm}' is not in this class's summon_pool {sorted(summon_names)}")
            elif int(e.get("amount", 0) or 0) < 1:
                errs.append(f"hook[{i}].effects[{j}] op '{op}' needs amount >= 1")
            if trigger == "combat_end" and op != "heal":
                errs.append(f"hook[{i}] 'combat_end' may only use the 'heal' effect (combat is over)")
        when = h.get("when")
        if when is not None:
            if not isinstance(when, dict):
                errs.append(f"hook[{i}] 'when' must be an object")
            else:
                kind = str(when.get("kind", "")).strip().lower()
                if kind not in _RELIC_CONDITION_KINDS:
                    errs.append(f"hook[{i}] 'when' kind must be one of {sorted(_RELIC_CONDITION_KINDS)}")
                elif kind in _RELIC_COND_NEEDS_VALUE and int(when.get("value", 0) or 0) < 1:
                    errs.append(f"hook[{i}] 'when' kind '{kind}' needs value >= 1")
    for i, m in enumerate(mods):
        if not isinstance(m, dict):
            errs.append(f"modifier[{i}] must be an object"); continue
        if str(m.get("stat", "")).strip().lower() not in _RELIC_MODIFIER_STATS:
            errs.append(f"modifier[{i}] stat must be one of {sorted(_RELIC_MODIFIER_STATS)}")
        if int(m.get("amount", 0) or 0) == 0:
            errs.append(f"modifier[{i}] needs a non-zero amount")
    return errs


# --- keystone balance: the deck-aware power gate ("Diamond Hands" fix) ------------------------------
# _validate_relic above mirrors the C# importer — structure only. This gate prices the keystone AGAINST
# THE GENERATED CARD SET, because the model that designs the relic designed the deck too, and its
# favourite trick is a `when` condition its own deck satisfies for free (hand_size_ge on a retain-heavy
# class), which reads like a restriction but plays like an unconditional payout. The proxy is: card
# effect weights (CardValidator._score_effect) x payouts-per-combat for the trigger x estimated
# condition uptime FOR THIS DECK, plus flat values for the passive modifiers. Failing the budget is a
# repair-loop error (the message names the offender so the model can weaken the payout, gate it
# once_per_combat, or pick a genuinely costly condition); still failing after repair drops the relic
# (the class ships on the Burning Blood default — never with an overtuned keystone).

_KEYSTONE_BUDGET = 13.0   # the common-relic band (relic_validator's tiers): a starter is common-power.
_KEYSTONE_GRACE = 1.15    # the proxy is coarse — a <=15% exceedance is heuristic noise, not a reject.
# Payouts over a ~3-turn hallway fight. Reactive hooks fire per event (the vocab's own "can fire many
# times a turn" warning); once_per_combat collapses any trigger to 1.
_HOOK_FREQ = {"turn_start": 3.0, "turn_end": 3.0, "attacked": 2.0, "on_hp_lost": 1.5,
              "on_exhaust": 2.0, "on_card_played": 9.0, "on_card_drawn": 12.0,
              "on_damage_dealt": 6.0, "on_block_gained": 4.0, "combat_end": 1.0}
# Flat per-amount value of the passive modifiers (always-on, uncondition-able). The two energy stats
# price above the starter budget ON PURPOSE: +1 energy/turn is Coffee-Dripper (boss) power and -1 cost
# on every card is stronger still — the base game never ships either without a downside, so a forged
# starter doesn't get to either.
_MODIFIER_VALUE = {"max_energy": 18.0, "cost_reduction": 24.0,
                   "first_attack": 1.0, "start_combat_block": 0.8}


def _card_has_flag_op(card: dict, flag: str) -> bool:
    effs = list(card.get("effects") or []) + list((card.get("upgrade") or {}).get("effects") or [])
    return any(isinstance(e, dict) and e.get("op") == flag for e in effs)


def _keystone_deck_stats(made: list[dict]) -> dict:
    """Retain saturation of the class, measured both ways a run gets there: the STARTING deck (basics
    ~5 copies each, signatures 1 — the mix stage 3 locks) and the draftable POOL (where the deck
    converges mid-run). Retain is what inflates a turn-start hand past the drawn 5 — even one retain
    basic (5 copies) means the player holds a card most turns."""
    start_copies = start_retain = pool = pool_retain = 0
    for m in made or []:
        card = m.get("card") or {}
        role = (m.get("plan") or {}).get("role")
        has_retain = _card_has_flag_op(card, "retain")
        if role in _BASIC_ROLES:
            start_copies += 5
            start_retain += 5 if has_retain else 0
        elif role in _SIGNATURE_ROLES:
            start_copies += 1
            start_retain += 1 if has_retain else 0
        elif not card.get("token"):  # the blade is summoned, never drafted
            pool += 1
            pool_retain += 1 if has_retain else 0
    share = max(start_retain / start_copies if start_copies else 0.0,
                pool_retain / pool if pool else 0.0)
    return {"share": share, "start": f"{start_retain}/{start_copies or '?'} starting-deck cards",
            "pool": f"{pool_retain}/{pool or '?'} pool cards"}


def _cond_uptime(when, deck_stats: dict) -> float:
    """How often a hook's `when` actually holds, 0.05..1.0. hand_size_ge is the deck-aware one: the
    expected turn-start hand is the drawn 5 plus what retain lets the player hold (players hold retain
    cards on purpose — retaining is free). Estimated at turn start (the roomiest hand), so mid-turn
    triggers price conservatively high — the strict direction for a power gate."""
    if not isinstance(when, dict):
        return 1.0
    kind = str(when.get("kind", "")).strip().lower()
    try:
        value = int(when.get("value", 0) or 0)
    except (TypeError, ValueError):
        value = 0
    up = 1.0
    if kind == "hp_below_half":
        up = 0.35
    elif kind in ("no_block", "has_block"):
        up = 0.5
    elif kind == "enemy_count_ge":
        up = 1.0 if value <= 1 else (0.5 if value == 2 else 0.25)
    elif kind == "turn_at_least":
        up = min(1.0, max(0.15, (7.0 - value) / 6.0))  # ~6-turn fight
    elif kind == "hand_size_ge":
        expected = 5 + min(5, round(10 * deck_stats["share"]))
        deficit = value - expected
        up = 1.0 if deficit <= 0 else (0.35 if deficit == 1 else (0.12 if deficit == 2 else 0.05))
    if when.get("negate"):
        up = 1.0 - up
    return min(1.0, max(0.05, up))


def _relic_balance_errors(relic: dict, made: list[dict], card_validator) -> list[str]:
    """The deck-aware keystone power gate. Returns repair-loop error strings ([] = inside budget).
    Never raises — an internal error must not break a forge (the gate is a net, not a load-bearer)."""
    try:
        stats = _keystone_deck_stats(made)
        total = 0.0
        parts: list[tuple[float, str]] = []  # (value, human reason) — the top one names the fix
        for i, h in enumerate(relic.get("hooks") or []):
            if not isinstance(h, dict):
                continue
            trigger = str(h.get("trigger", "")).strip().lower()
            value = sum(card_validator._score_effect(e) for e in h.get("effects") or []
                        if isinstance(e, dict))
            once = bool(h.get("once_per_combat"))
            freq = 1.0 if once else _HOOK_FREQ.get(trigger, 3.0)
            when = h.get("when") if isinstance(h.get("when"), dict) else None
            uptime = _cond_uptime(when, stats)
            total += value * freq * uptime
            ops = "+".join(str(e.get("op")) for e in h.get("effects") or [] if isinstance(e, dict))
            reason = f"hook[{i}] ({trigger}{', once_per_combat' if once else ''}: {ops}) ~{value * freq * uptime:.0f}"
            if when and str(when.get("kind")) == "hand_size_ge" and uptime >= 0.9:
                reason += (f" — its 'hand_size_ge {when.get('value')}' condition is ~always true for this"
                           f" deck (retain on {stats['start']}, {stats['pool']}), so it is no discount")
            parts.append((value * freq * uptime, reason))
        for m in relic.get("modifiers") or []:
            if not isinstance(m, dict):
                continue
            amt = m.get("amount", 0)
            amt = float(amt) if isinstance(amt, (int, float)) and not isinstance(amt, bool) else 0.0
            stat = str(m.get("stat", "")).strip().lower()
            v = _MODIFIER_VALUE.get(stat, 0.0) * amt
            total += v
            reason = f"modifier ({stat} {int(amt)}) ~{v:.0f}"
            if stat in ("max_energy", "cost_reduction"):
                reason += " — a flat energy stat is boss-relic power, never a starter's"
            parts.append((v, reason))
        if total <= _KEYSTONE_BUDGET * _KEYSTONE_GRACE:
            return []
        top = max(parts, key=lambda p: p[0])[1] if parts else "?"
        return [f"keystone too strong for an always-on STARTER: power proxy ~{total:.0f} exceeds the "
                f"~{_KEYSTONE_BUDGET:.0f} budget. Biggest piece: {top}. Weaken the payout, gate the hook "
                "once_per_combat, slow its trigger, or use a condition this class does NOT trivially "
                "satisfy — keep the same theme."]
    except Exception:  # noqa: BLE001 — advisory gate: scoring bug must never block a forge
        return []


class _RelicContract:
    """Duck-typed contract for the keystone-relic LLM call. The 'brief' passed to first_attempt/repair is the
    BLUEPRINT dict (the class identity), so the relic is designed as that class's keystone."""

    def system_prompt(self) -> str:
        from .contract import relic_forms
        vocab = RELIC_VOCAB.read_text(encoding="utf-8")
        forms = relic_forms()
        forms_block = ("\n\n" + forms) if forms else ""
        return f"""You are a RELIC designer for "BLANK the spire", a Slay-the-Spire-like deckbuilder. You design ONE \
custom STARTER RELIC for a freshly-forged class — the keystone that rewards its core loop (like Cracked Core \
defines the Defect's orbs). Output ONE JSON relic object, NOTHING else.

THE HARD CONSTRAINT — the engine runs a CLOSED, SMALL relic vocabulary. Compose ONLY from these:
{vocab}

It is a STARTER relic: ALWAYS-ON, so keep numbers MODEST and keep it SIMPLE — ONE keystone idea, a single hook \
(or a single modifier, no hook). A second hook ONLY if it is a genuine drawback/cost; never add a hook just to \
nod at the second archetype. Lead with the class's DOMINANT archetype; the other is flavor in the name, not an \
extra mechanic. Make it express THIS class — read the class name, description, and archetypes in the brief and \
design the relic that names their build.

ALWAYS include "icon_emoji": ONE single emoji picturing the relic itself (the object/theme, not the \
mechanics) — it becomes the in-game relic icon. Prefer a concrete thing (🗡️ 🛡️ 🕯️ 💀 🧪 ⚙️ 🔮 🌩️) over an \
abstract symbol.{forms_block}"""

    def user_brief(self, bp) -> str:
        archs = bp.get("archetypes") or []
        arch_lines = "\n".join(f"- {a.get('name')}: {a.get('description')}"
                               for a in archs if isinstance(a, dict)) or "- (none)"
        # Phase L compose context: tell the LLM which compose ops THIS class supports (else they're rejected).
        has_orbs = bool(bp.get("orb_pool") or (bp.get("orb_slots") or 0) >= 1)
        summon_names = [str(s.get("name")) for s in (bp.get("summon_pool") or []) if isinstance(s, dict)]
        compose = []
        if has_orbs:
            compose.append('This class HAS ORBS — you MAY use the `channel_orb` op (e.g. a Cracked-Core-style relic '
                           'that channels an orb at combat start via turn_start + once_per_combat).')
        if summon_names:
            compose.append(f'This class HAS MINIONS {summon_names} — you MAY use the `summon` op (a companion relic '
                           f'that summons one at combat start). Use exactly one of those names.')
        if not compose:
            compose.append('This class has NO orbs and NO minions — do NOT use `channel_orb` or `summon`.')
        # Staged front-end: the keystone INTENT (name + effect sketch) steers the relic toward the designed
        # identity; the constrained vocabulary still arbitrates what's actually built.
        intent = bp.get("relic_intent") if isinstance(bp.get("relic_intent"), dict) else None
        intent_line = ""
        if intent:
            intent_line = (f'\nKEYSTONE INTENT (design toward this): "{intent.get("name", "")}" — '
                           f'{intent.get("effect_sketch", intent.get("fantasy", ""))}\n')
        return (f'Design the keystone STARTER relic for this new class:\n'
                f'Name: "{bp.get("name", "the class")}"\nFantasy: {bp.get("description", "")}\n'
                f'Archetypes:\n{arch_lines}\n{intent_line}\nCOMPOSE: {" ".join(compose)}\n\n'
                f'Return only the JSON relic object (tier "starter").')

    def repair_message(self, relic_text: str, errors: list[str]) -> str:
        bullet = "\n".join(f"- {e}" for e in errors)
        return ("That relic failed validation:\n" f"{bullet}\n\n"
                "Here is what you returned:\n" f"{relic_text}\n\n"
                "Return a corrected SINGLE JSON relic object that fixes every error and still fits the class. "
                "Output only the JSON object.")


_BASIC_ROLES = {"basic_attack", "basic_skill"}
# The forge class's signature-blade role: a reserved TOKEN attack, marked non-drafted. Phase T: it is NOT in the
# starting deck — the first Forge of combat summons it to hand — so it does NOT ride _SIGNATURE_ROLES (deck
# accounting) but IS protected from cap-trimming. Synthesized (not LLM-designed); a forge class ships EXACTLY one.
_BLADE_ROLE = "signature_blade"
# Roles that ride the starting deck at deck_count 1 (each contributes one non-basic starter; the basics absorb
# the remainder to hit STARTING_DECK_SIZE). The blade is EXCLUDED (Phase T: summoned, not deck-seeded).
_SIGNATURE_ROLES = {"signature"}

# The card types the in-game merchant builds a shop entry for. Every class's NON-basic pool must contain at
# least one of each, or CardFactory.CreateForMerchant throws and the game hangs at a merchant (see the
# merchant-hang bug). Mirror of the colored card types the shop offers.
_MERCHANT_TYPES = ("attack", "skill", "power")


def _validate_blueprint(bp: dict) -> list[str]:
    errs: list[str] = []
    if not isinstance(bp, dict):
        return ["blueprint is not an object"]
    for key in ("name", "description", "max_hp", "archetypes", "cards"):
        if key not in bp:
            errs.append(f"missing '{key}'")
    if errs:
        return errs
    if not isinstance(bp["archetypes"], list) or len(bp["archetypes"]) != 2:
        errs.append("need exactly 2 archetypes")
    cards = bp.get("cards") or []
    if not isinstance(cards, list) or not cards:
        errs.append("need a non-empty cards list")
        return errs
    roles = [c.get("role") for c in cards]
    if roles.count("basic_attack") != 1 or roles.count("basic_skill") != 1:
        errs.append("need exactly one basic_attack and one basic_skill")
    # A forge class ships EXACTLY one signature blade; a non-forge class ships none. (0 or 1 here; the assembly's
    # blade-safety net adds one if Forge income is present but the model omitted it.)
    if roles.count(_BLADE_ROLE) > 1:
        errs.append(f"a class ships at most one {_BLADE_ROLE} (the single growing signature blade)")
    if len(cards) > _BLUEPRINT_CARD_CAP:
        errs.append(f"at most {_BLUEPRINT_CARD_CAP} cards per class (the mod holds {CARDS_PER_CLASS} card "
                    f"slots; the remainder is reserved for merchant/rare safety fillers)")
    # Merchant safety: the shop builds one entry per card type from the NON-basic pool; an empty type bucket
    # makes CardFactory.CreateForMerchant throw and hangs the game. Require ≥1 non-basic of each merchant type.
    # The signature blade is a TOKEN (never in the shop), so it does NOT count toward a merchant bucket.
    nonbasic_types = {str(c.get("type", "")).lower() for c in cards
                      if c.get("role") not in _BASIC_ROLES
                      and str(c.get("rarity", "")).lower() not in ("basic", "token")
                      and not c.get("token")}
    for t in _MERCHANT_TYPES:
        if t not in nonbasic_types:
            errs.append(f"need at least one non-basic {t} card — the merchant builds a {t} shop entry from the "
                        f"class pool and an empty {t} bucket hangs the game")
    # Boss-reward safety: a boss card reward rolls a Rare (BossEncounter odds, no lower-rarity fallback) and
    # the run soft-locks if the class has no Rare available. Require a floor of MIN_RARES rare pool cards.
    rares = sum(1 for c in cards if c.get("role") not in _BASIC_ROLES
                and str(c.get("rarity", "")).lower() == "rare")
    if rares < MIN_RARES:
        errs.append(f"need at least {MIN_RARES} rare pool cards (a boss card reward rolls a Rare and the run "
                    f"hangs if none is available); got {rares}")
    # Strategic-line coverage: the pool must support >=2 distinct strategies (aggro/control/combo), each as a
    # real package — >=_LINE_MIN_CARDS tagged non-basic cards including >=1 rare finisher. This is the
    # Ironclad test: one pool, several draftable game plans, each with a wincon to build toward.
    errs += _strategy_coverage(cards)[0]
    # O-1 fusion enforcer: a two-archetype class must ship real BRIDGE cards that combine BOTH engines in one
    # card (>=MIN_BRIDGES pool cards tagged "bridge", >=1 of them a rare — the fusion's poster card). The
    # post-generation witness detector (bridges.py, run in the coverage round) checks they actually fuse; this
    # is the blueprint-stage tag-count + rare floor.
    bridge_cards = [c for c in cards if isinstance(c, dict) and c.get("bridge")
                    and c.get("role") not in _BASIC_ROLES]
    if len(bridge_cards) < MIN_BRIDGES:
        errs.append(f"need at least {MIN_BRIDGES} bridge cards ('bridge': true, role 'pool') that fuse BOTH "
                    f"archetypes' engines into one card; got {len(bridge_cards)}")
    elif not any(str(c.get("rarity", "")).lower() == "rare" for c in bridge_cards):
        errs.append("at least one bridge card must be a rare (the fusion's poster card)")
    if not (60 <= int(bp.get("max_hp", 0)) <= 95):
        errs.append("max_hp must be 60..95")
    orb_slots = 0
    try:
        orb_slots = int(bp.get("orb_slots", 0) or 0)
    except (TypeError, ValueError):
        errs.append("orb_slots must be an integer (0 for a normal class, 3-4 for an orb class)")
    else:
        if not (0 <= orb_slots <= 4):
            errs.append("orb_slots must be 0..4")
    if "orb_pool" in bp and bp.get("orb_pool"):
        errs += _validate_orb_pool(bp.get("orb_pool"), orb_slots)
    if "status_pool" in bp and bp.get("status_pool"):
        errs += _validate_status_pool(bp.get("status_pool"))
    if "summon_pool" in bp and bp.get("summon_pool"):
        errs += _validate_summon_pool(bp.get("summon_pool"))
    return errs


_GLUE_TAGS = {"", "any", "all", "glue", "none", "null"}  # ways the model says "generic glue" — all fine


def _strategy_coverage(cards) -> tuple[list[str], dict[str, dict]]:
    """Count the pool's strategy packages. Returns (errors, {strategy: {cards, rares}}). A card with no
    strategy tag (or a glue tag) is legal — it's the generic filler any deck drafts — but at least TWO
    distinct strategies must each have a full package (>=_LINE_MIN_CARDS cards, >=1 rare finisher)."""
    errs: list[str] = []
    by: dict[str, dict] = {}
    for c in cards or []:
        if not isinstance(c, dict) or c.get("role") in _BASIC_ROLES:
            continue
        raw = c.get("strategy")
        tag = str(raw).strip().lower() if raw is not None else ""
        if tag in _GLUE_TAGS:
            continue
        if tag not in STRATEGIES:
            errs.append(f"card '{c.get('name_hint', '?')}' has strategy '{raw}' — must be one of "
                        f"{'/'.join(STRATEGIES)} (or null for generic glue)")
            continue
        b = by.setdefault(tag, {"cards": 0, "rares": 0})
        b["cards"] += 1
        if str(c.get("rarity", "")).lower() == "rare":
            b["rares"] += 1
    covered = sorted(s for s, b in by.items() if b["cards"] >= _LINE_MIN_CARDS and b["rares"] >= 1)
    if len(covered) < 2:
        tally = ", ".join(f"{s}: {b['cards']} card(s)/{b['rares']} rare(s)" for s, b in sorted(by.items())) \
                or "no cards tagged"
        errs.append(f"the pool must support at least 2 strategic lines: tag pool cards with \"strategy\" "
                    f"(aggro/control/combo) so >=2 strategies each have >={_LINE_MIN_CARDS} tagged cards "
                    f"including >=1 rare finisher; covered so far: {covered or 'none'} ({tally})")
    return errs, by


def validate_blueprint_for(strategies) -> "callable":
    """Validator closure for the staged path (mirrors validate_compose_for): the generic blueprint checks
    PLUS the chosen candidate's DECLARED strategic lines — each declared strategy must be a covered package
    in the pool, so the blueprint actually builds what the compose stage promised."""
    need = [s for s in dict.fromkeys(str(x).strip().lower() for x in (strategies or [])) if s in STRATEGIES]

    def _validate(bp: dict) -> list[str]:
        errs = _validate_blueprint(bp)
        if not isinstance(bp, dict) or not need:
            return errs
        by = _strategy_coverage(bp.get("cards") or [])[1]
        for s in need:
            b = by.get(s, {"cards": 0, "rares": 0})
            if b["cards"] < _LINE_MIN_CARDS or b["rares"] < 1:
                errs.append(f"the class declared a '{s}' strategic line but the pool doesn't support it: "
                            f"needs >={_LINE_MIN_CARDS} cards tagged \"strategy\": \"{s}\" including >=1 "
                            f"rare finisher (got {b['cards']} card(s), {b['rares']} rare(s))")
        return errs

    return _validate


# --- Phase I: orb pool validation (mirrors the C# ForgedCharacters orb-pool parser) ---------------

_BASE_ORBS = {"lightning", "frost", "dark"}
_ORB_EFFECT_OPS = {"damage", "block", "apply_status", "draw", "gain_energy", "heal", "gain_orb_slot", "channel_orb"}
_ORB_SELF_BUFFS = {"strength", "dexterity", "thorns", "regen", "metallicize", "artifact", "buffer",
                   "intangible", "ritual", "blur", "temp_strength", "temp_dexterity", "barricade", "focus"}
_ORB_DEBUFFS = {"vulnerable", "weak", "frail", "poison"}
_ORB_TARGETS = {"self", "enemy", "all_enemies"}
_MAX_CUSTOM_ORBS = 3  # must equal ForgedCharacters.MaxCustomOrbs


def _validate_orb_pool(pool, orb_slots: int) -> list[str]:
    errs: list[str] = []
    if not isinstance(pool, list):
        return ["orb_pool must be a list of base-orb names and/or custom-orb objects"]
    if pool and not (orb_slots and orb_slots > 0):
        errs.append("orb_pool requires orb_slots >= 1 (the class needs somewhere to channel)")
    custom = 0
    names: set[str] = set()
    for i, entry in enumerate(pool):
        if isinstance(entry, str):
            nm = entry.strip().lower()
            if nm not in _BASE_ORBS:
                errs.append(f"orb_pool[{i}] base orb '{entry}' must be one of lightning/frost/dark")
            if nm in names:
                errs.append(f"orb_pool has duplicate orb name '{nm}'")
            names.add(nm)
        elif isinstance(entry, dict):
            custom += 1
            nm = str(entry.get("name", "")).strip()
            if not nm:
                errs.append(f"orb_pool[{i}] custom orb needs a non-empty name")
            key = nm.lower()
            if key in names:
                errs.append(f"orb_pool has duplicate orb name '{key}'")
            names.add(key)
            errs += _validate_orb_effects(entry.get("passive") or [], f"orb '{nm or i}' passive")
            errs += _validate_orb_effects(entry.get("evoke") or [], f"orb '{nm or i}' evoke")
            if not (entry.get("passive") or entry.get("evoke")):
                errs.append(f"custom orb '{nm or i}' needs a passive or an evoke effect")
        else:
            errs.append(f"orb_pool[{i}] must be a base-orb name string or a custom-orb object")
    if custom > _MAX_CUSTOM_ORBS:
        errs.append(f"at most {_MAX_CUSTOM_ORBS} custom orbs per class (got {custom})")
    return errs


def _validate_orb_effects(effs, where: str) -> list[str]:
    errs: list[str] = []
    if not isinstance(effs, list):
        return [f"{where} must be a list of effects"]
    for e in effs:
        if not isinstance(e, dict):
            errs.append(f"{where}: each effect must be an object")
            continue
        op = str(e.get("op", "")).lower()
        if op not in _ORB_EFFECT_OPS:
            errs.append(f"{where}: op '{op}' is not allowed in an orb (one of {sorted(_ORB_EFFECT_OPS)})")
            continue
        target = str(e.get("target", "")).lower()
        if target and target not in _ORB_TARGETS:
            errs.append(f"{where}: target '{target}' must be self/enemy/all_enemies")
        if op == "damage" and target == "self":
            errs.append(f"{where}: damage can't target self")
        if op == "apply_status":
            st = str(e.get("status", "")).lower()
            if st not in _ORB_SELF_BUFFS and st not in _ORB_DEBUFFS:
                errs.append(f"{where}: unsupported status '{st}'")
            elif st in _ORB_SELF_BUFFS and target and target != "self":
                errs.append(f"{where}: self-buff '{st}' must target self")
            elif st in _ORB_DEBUFFS and target == "self":
                errs.append(f"{where}: debuff '{st}' can't target self")
        if op == "channel_orb":
            if not str(e.get("orb", "")).strip():
                errs.append(f"{where}: channel_orb needs an 'orb' name")
        elif int(e.get("amount", 0) or 0) < 1:
            errs.append(f"{where}: op '{op}' needs amount >= 1")
    return errs


def _orb_pool_custom_names(bp: dict) -> set[str]:
    """The lowercased names of a blueprint's custom orbs — injected into the card validator so channel cards
    may reference them by name (Phase I)."""
    names: set[str] = set()
    for entry in (bp.get("orb_pool") or []):
        if isinstance(entry, dict) and str(entry.get("name", "")).strip():
            names.add(str(entry["name"]).strip().lower())
    return names


# --- Phase J: status pool validation (mirrors the C# ForgedCharacters status-pool parser) ----------

_STATUS_HOOKS = {"damage_dealt", "damage_taken", "block_gained", "energy_gain", "card_draw"}
_STATUS_DECAYS = {"none", "lose_one_eot", "lose_all_eot"}
_MAX_CUSTOM_STATUSES = 4  # must equal ForgedCharacters.MaxCustomStatuses


def _validate_status_pool(pool) -> list[str]:
    errs: list[str] = []
    if not isinstance(pool, list):
        return ["status_pool must be a list of custom-status objects"]
    if len(pool) > _MAX_CUSTOM_STATUSES:
        errs.append(f"at most {_MAX_CUSTOM_STATUSES} custom statuses per class (got {len(pool)})")
    names: set[str] = set()
    for i, st in enumerate(pool):
        if not isinstance(st, dict):
            errs.append(f"status_pool[{i}] must be an object")
            continue
        nm = str(st.get("name", "")).strip()
        if not nm:
            errs.append(f"status_pool[{i}] needs a non-empty name")
        key = nm.lower()
        if key and key in names:
            errs.append(f"status_pool has duplicate status name '{key}'")
        names.add(key)
        typ = str(st.get("type", "buff")).strip().lower()
        if typ not in ("buff", "debuff"):
            errs.append(f"status '{nm or i}': type must be buff/debuff")
        hook = str(st.get("hook", "")).strip().lower()
        if hook not in _STATUS_HOOKS:
            errs.append(f"status '{nm or i}': hook must be one of {sorted(_STATUS_HOOKS)}")
        decay = str(st.get("decay", "none")).strip().lower()
        if decay not in _STATUS_DECAYS:
            errs.append(f"status '{nm or i}': decay must be one of {sorted(_STATUS_DECAYS)}")
        stack = str(st.get("stack", "counter")).strip().lower()
        if stack not in ("counter", "single"):
            errs.append(f"status '{nm or i}': stack must be counter/single")
        # side rules (mirror C#): damage_dealt/block_gained/energy_gain/card_draw are buffs (your own numbers);
        # damage_taken is a debuff (the afflicted enemy takes more).
        is_buff = typ == "buff"
        if hook in ("damage_dealt", "block_gained", "energy_gain", "card_draw") and not is_buff:
            errs.append(f"status '{nm or i}': {hook} must be a buff (it changes your own numbers)")
        if hook == "damage_taken" and is_buff:
            errs.append(f"status '{nm or i}': damage_taken must be a debuff (the afflicted enemy takes more)")
    return errs


def _status_pool_custom_names(bp: dict) -> set[str]:
    """The lowercased names of a blueprint's custom statuses — injected into the card validator so
    apply_status_custom cards may reference them by name (Phase J)."""
    names: set[str] = set()
    for st in (bp.get("status_pool") or []):
        if isinstance(st, dict) and str(st.get("name", "")).strip():
            names.add(str(st["name"]).strip().lower())
    return names


def _card_uses_custom_status(card: dict) -> bool:
    """True if any (base/upgrade) effect applies a forged custom status — a class-only mechanic that does
    nothing without a status_pool (used to drop such a card off a non-status class)."""
    effs = list(card.get("effects") or [])
    effs += list((card.get("upgrade") or {}).get("effects") or [])
    return any(e.get("op") == "apply_status_custom" for e in effs)


# --- Phase K: summon pool validation (mirrors the C# ForgedCharacters summon-pool parser) -----------

_SUMMON_OPS = {"attack", "block", "apply_status", "heal_self"}
_SUMMON_TARGETS = {"self", "enemy", "all_enemies"}
_SUMMON_ENEMY_STATUSES = {"vulnerable", "weak", "frail", "poison"}
# v15 true-Osty: a summon class declares EXACTLY ONE passive Osty-style minion (the engine still allows 2, kept
# dormant). The K-3 custom-summon fields (moves/attackable/on_summon/on_death) are no longer emitted (see below).
_MAX_SUMMONS = 1
_SUMMON_MAX_HP = 60                 # generation cap on the minion's starting HP (the engine itself allows 1..999)
# The K-3 autonomous-move caps below are now DORMANT (the generator no longer emits minion moves); kept for the
# dormant engine path / possible re-add (see _validate_summon_actions, no longer called for pools).
_SUMMON_ACTION_CAPS = {"attack": 20, "block": 12, "apply_status": 6, "heal_self": 12}
_SUMMON_MAX_HITS = 4


def _validate_summon_actions(arr, where: str, enemy_facing_only: bool = False) -> list[str]:
    """One action list (a move, or an on_summon / on_death payload) — mirrors C# ForgedCharacters.TryParseSummonActions.
    enemy_facing_only=True (a death rattle) forbids block / heal_self / self-buff, since the minion is gone."""
    errs: list[str] = []
    if not isinstance(arr, list):
        return [f"{where} actions must be a list"]
    for a in arr:
        if not isinstance(a, dict):
            errs.append(f"{where}: each action must be an object")
            continue
        op = str(a.get("op", "")).strip().lower()
        if op not in _SUMMON_OPS:
            errs.append(f"{where}: action op '{op}' is not one of {sorted(_SUMMON_OPS)}")
            continue
        if enemy_facing_only and op in ("block", "heal_self"):
            errs.append(f"{where}: '{op}' can't run on death (the minion is gone) — use attack or a debuff")
            continue
        amount = int(a.get("amount", 0) or 0)
        hits = int(a.get("hits", 1) or 1)
        status = str(a.get("status", "")).strip().lower() if a.get("status") is not None else None
        target = str(a.get("target", "")).strip().lower()
        if target and target not in _SUMMON_TARGETS:
            errs.append(f"{where}: target '{target}' is not one of {sorted(_SUMMON_TARGETS)}")
        if amount < 1:
            errs.append(f"{where}: action '{op}' needs amount >= 1")
        elif amount > _SUMMON_ACTION_CAPS.get(op, 99):
            errs.append(f"{where}: '{op}' amount {amount} too high (max {_SUMMON_ACTION_CAPS[op]}; keep minion numbers small)")
        if hits < 1:
            errs.append(f"{where}: hits must be >= 1")
        elif hits > _SUMMON_MAX_HITS:
            errs.append(f"{where}: hits {hits} too high (max {_SUMMON_MAX_HITS})")
        if hits > 1 and op != "attack":
            errs.append(f"{where}: 'hits' only applies to attack")
        if op == "attack":
            if target == "self":
                errs.append(f"{where}: attack can't target self")
        elif op in ("block", "heal_self"):
            if target and target != "self":
                errs.append(f"{where}: '{op}' runs on the minion (target must be self)")
        elif op == "apply_status":
            self_buff = status in _ORB_SELF_BUFFS
            if not status or not (self_buff or status in _SUMMON_ENEMY_STATUSES):
                errs.append(f"{where}: unsupported status '{status}'")
            elif enemy_facing_only and self_buff:
                errs.append(f"{where}: self-buff '{status}' can't run on death (the minion is gone) — use a debuff")
            elif self_buff and target and target != "self":
                errs.append(f"{where}: self-buff '{status}' must target self (the minion)")
            elif (not self_buff) and target == "self":
                errs.append(f"{where}: debuff '{status}' can't target self")
        if op != "apply_status" and status is not None:
            errs.append(f"{where}: 'status' only applies to apply_status (op '{op}')")
    return errs


# v15 true-Osty: the K-3 custom-summon fields are no longer emitted (the engine keeps them dormant). Reject them so
# the model uses the passive-minion + summon_attack/buff_summon model instead of the old autonomous-move design.
_REMOVED_SUMMON_FIELDS = ("moves", "actions", "attackable", "on_summon", "on_death")


def _validate_summon_pool(pool) -> list[str]:
    errs: list[str] = []
    if not isinstance(pool, list):
        return ["summon_pool must be a list with a single custom-summon object"]
    if len(pool) > _MAX_SUMMONS:
        errs.append(f"a class may declare at most {_MAX_SUMMONS} summon (got {len(pool)}); a summon class fights "
                    f"through ONE Osty-style minion")
    names: set[str] = set()
    for i, sm in enumerate(pool):
        if not isinstance(sm, dict):
            errs.append(f"summon_pool[{i}] must be an object")
            continue
        nm = str(sm.get("name", "")).strip()
        if not nm:
            errs.append(f"summon_pool[{i}] needs a non-empty name")
        key = nm.lower()
        if key and key in names:
            errs.append(f"summon_pool has duplicate summon name '{key}'")
        names.add(key)
        try:
            max_hp = int(sm.get("max_hp", 10) or 10)
        except (TypeError, ValueError):
            max_hp = 0
        if not (1 <= max_hp <= _SUMMON_MAX_HP):
            errs.append(f"summon '{nm or i}': max_hp must be 1..{_SUMMON_MAX_HP} (its starting HP)")
        present = [k for k in _REMOVED_SUMMON_FIELDS if k in sm]
        if present:
            errs.append(f"summon '{nm or i}': {', '.join(present)} no longer supported — a forged summon is a "
                        f"PASSIVE Osty-style minion (no moves/attackable/on_summon/on_death). Its offense comes from "
                        f"summon_attack cards; buff it with buff_summon; grow/(re)summon it with the summon op")
    return errs


def _summon_pool_custom_names(bp: dict) -> set[str]:
    """The lowercased names of a blueprint's custom summons — injected into the card validator so summon cards
    may reference them by name (Phase K)."""
    names: set[str] = set()
    for sm in (bp.get("summon_pool") or []):
        if isinstance(sm, dict) and str(sm.get("name", "")).strip():
            names.add(str(sm["name"]).strip().lower())
    return names


def _card_uses_summons(card: dict) -> bool:
    """True if any (base/upgrade) effect uses a summon op (summon / summon_attack / buff_summon) — all class-only
    mechanics that do nothing without a summon_pool (used to drop such a card off a non-summon class)."""
    effs = list(card.get("effects") or [])
    effs += list((card.get("upgrade") or {}).get("effects") or [])
    return any(e.get("op") in ("summon", "summon_attack", "buff_summon") for e in effs)


_ORB_OPS = {"channel_orb", "evoke", "gain_orb_slot"}
_ORB_CONDITIONS = {"orbs_match", "orb_count_ge"}  # the orb-reading `when` kinds (orb-class only)


def _card_uses_orbs(card: dict) -> bool:
    """True if any (base/upgrade/trigger-payload) effect uses an orb op, the Focus status, or an orb-reading
    `when` condition — all orb-class-only mechanics that do nothing without orb slots."""
    effs = list(card.get("effects") or [])
    effs += list((card.get("upgrade") or {}).get("effects") or [])
    # a trigger's payload (Phase H3) can also carry orb ops / Focus
    effs += [t for e in effs if e.get("op") == "add_trigger" for t in (e.get("effects") or [])]
    for e in effs:
        if e.get("op") in _ORB_OPS:
            return True
        if e.get("op") == "apply_status" and e.get("status") == "focus":
            return True
        when = e.get("when")
        if isinstance(when, dict) and when.get("kind") in _ORB_CONDITIONS:
            return True
    return False


def _synthesize_basic(plan: dict) -> dict:
    is_attack = plan["role"] == "basic_attack"
    return {
        "id": "strike" if is_attack else "defend",
        "name": "Strike" if is_attack else "Defend",
        "type": "attack" if is_attack else "skill",
        "rarity": "basic", "cost": 1,
        "target": "enemy" if is_attack else "self",
        "source": "llm",
        "effects": [{"op": "damage", "amount": 6}] if is_attack else [{"op": "block", "amount": 5}],
        "upgrade": {"effects": [{"op": "damage", "amount": 9}] if is_attack else [{"op": "block", "amount": 8}]},
    }


# --- the Sovereign Blade (Phase T): a forge class's signature growing weapon -------------------------
# One reserved attack marked a non-drafted TOKEN. Base-game-exact (Phase T): it is NOT in the deck — your FIRST
# Forge of each combat SUMMONS it to hand (the mod's ForgedForgePower.Stoke). It Retains until you swing it and
# deals its printed base PLUS your per-combat Forge counter (damage scale:"forged"). Cost 2, base damage 10 (the
# base-game Sovereign Blade: cost 2, damage 10, Retain, Token; upgrade drops cost 2->1 but our upgrade model is
# positional effect-deltas only, so we keep a DAMAGE upgrade 10->13 and file cost-upgrade as a future gap). Like
# Strike/Defend it is SYNTHESIZED (not LLM-generated) so its exact retain+forged shape and the token flag are
# guaranteed by construction; the blueprint only names/themes it. It carries real `token` rarity (base-game
# tokens do; the mod summons it and CardFactory never rolls Token for a draft/reward).
_BLADE_BASE_DAMAGE = 10
_BLADE_UPGRADE_DAMAGE = 13


def _slug(text: str, fallback: str) -> str:
    """A snake_case card id (schema ^[a-z][a-z0-9_]*$) from free text, or the fallback if it can't start alpha."""
    s = re.sub(r"_+", "_", re.sub(r"[^a-z0-9_]+", "_", (text or "").lower())).strip("_")
    return s if s[:1].isalpha() else fallback


def _synthesize_blade(plan: dict | None) -> dict:
    """The forge class's signature blade card (a non-drafted token). Uses the blueprint's name_hint (so each
    class names its own weapon), but a fixed low base + the forged scaling — like the base-game Sovereign Blade,
    which is always the same card across a run; the class-specific part is the name/flavor."""
    plan = plan or {}
    name = str(plan.get("name_hint") or "Sovereign Blade")[:40]

    def effs(dmg: int) -> list[dict]:
        # base-game blade shape: the attack (base + your Forge), then Retain. NO innate — Phase T summons it on
        # your first Forge instead of opening it in hand.
        return [{"op": "damage", "amount": dmg, "scale": "forged"}, {"op": "retain"}]

    return {
        "id": _slug(name, "sovereign_blade"),
        "name": name,
        "type": "attack", "rarity": "token", "cost": 2, "target": "enemy", "source": "llm",
        "effects": effs(_BLADE_BASE_DAMAGE),
        # Phase AG (gap #39): the base-game True Blade gets CHEAPER as you invest — upgrading it drops cost 2 -> 1,
        # so a ramped blade also becomes spammable (DataCard applies the cost on the Upgraded event).
        "upgrade": {"effects": effs(_BLADE_UPGRADE_DAMAGE), "cost": 1},
        "token": True,  # DataCard: summoned on first Forge, never drafted / in the compendium / in the deck
    }


def _card_forges(card: dict) -> bool:
    """True if any (base/upgrade/trigger-payload) effect uses the `forge` op — i.e. this card is Forge income."""
    def walk(effects) -> bool:
        for e in effects or []:
            if not isinstance(e, dict):
                continue
            if e.get("op") == "forge" or walk(e.get("effects")):
                return True
        return False

    return walk(card.get("effects")) or walk((card.get("upgrade") or {}).get("effects"))


def _relic_forges(relic: dict | None) -> bool:
    """True if the class's forged relic stokes Forge in any hook (relic-side Forge income)."""
    if not isinstance(relic, dict):
        return False
    return any(isinstance(h, dict) and any(isinstance(e, dict) and e.get("op") == "forge"
                                           for e in (h.get("effects") or []))
               for h in (relic.get("hooks") or []))


def _fallback_pool_card(card_type: str, idx: int, rarity: str = "common") -> dict:
    """A minimal, always-valid v2 pool card of the given type+rarity — the last-resort filler that keeps the
    shop (merchant types) and boss reward (rare floor) from hanging when generation dropped a needed bucket.
    deck_count 0 (pool only, never a starter). Rare fillers carry rare-appropriate (bigger) numbers."""
    is_rare = rarity == "rare"
    base = {"id": f"forged_{rarity}_filler_{card_type}_{idx}",
            "name": f"{'Greater' if is_rare else 'Spare'} {card_type.title()}",
            "type": card_type, "rarity": rarity, "cost": 2 if is_rare else 1, "source": "llm"}
    if card_type == "attack":
        dmg, up = (18, 24) if is_rare else (7, 10)
        base.update(target="enemy", effects=[{"op": "damage", "amount": dmg}],
                    upgrade={"effects": [{"op": "damage", "amount": up}]})
    elif card_type == "skill":
        blk, up = (18, 24) if is_rare else (6, 9)
        base.update(target="self", effects=[{"op": "block", "amount": blk}],
                    upgrade={"effects": [{"op": "block", "amount": up}]})
    else:  # power — a simple lasting self-buff (gain Strength), like Inflame
        st, up = (2, 3) if is_rare else (1, 2)
        base.update(target="self", effects=[{"op": "apply_status", "status": "strength", "amount": st}],
                    upgrade={"effects": [{"op": "apply_status", "status": "strength", "amount": up}]})
    return base


def _ensure_merchant_types(made: list[dict], note) -> list[dict]:
    """Guarantee the assembled NON-basic pool has a card of every merchant type. Generation can drop the
    planned Power (or an archetype), leaving an empty type bucket that hangs the merchant — synthesize a
    placeholder filler for any missing type so the shop is always fillable (belt-and-braces with the in-game
    Harmony guard)."""
    def is_nonbasic(m: dict) -> bool:
        return (m.get("plan") or {}).get("role") not in _BASIC_ROLES \
            and str(m["card"].get("rarity", "")).lower() != "basic"
    present = {str(m["card"].get("type", "")).lower() for m in made if is_nonbasic(m)}
    for t in _MERCHANT_TYPES:
        if t not in present:
            card = _fallback_pool_card(t, len(made) + 1)
            made.append({"plan": {"role": "pool", "deck_count": 0}, "card": card})
            note(f"merchant-safety: pool had no non-basic {t}; added '{card['name']}' so the shop won't hang")
    return made


def _ensure_min_rares(made: list[dict], note) -> list[dict]:
    """Guarantee the assembled NON-basic pool has at least MIN_RARES Rares. A boss card reward rolls a Rare
    (BossEncounter odds, no lower-rarity fallback); with no available Rare, CardFactory.CreateForReward throws
    and the run soft-locks at the rewards screen (the boss-reward-rarity-hang). Generation can drop planned
    rares, so synthesize rare fillers up to the floor — belt-and-braces with the prompt's ~TARGET_RARES target."""
    def is_nonbasic_rare(m: dict) -> bool:
        return (m.get("plan") or {}).get("role") not in _BASIC_ROLES \
            and str(m["card"].get("rarity", "")).lower() == "rare"
    have = sum(1 for m in made if is_nonbasic_rare(m))
    i = 0
    while have < MIN_RARES:
        t = _MERCHANT_TYPES[i % len(_MERCHANT_TYPES)]  # cycle attack/skill/power for variety
        card = _fallback_pool_card(t, len(made) + 1, rarity="rare")
        made.append({"plan": {"role": "pool", "deck_count": 0}, "card": card})
        note(f"rare-floor: pool had {have} rare(s) (<{MIN_RARES}); added '{card['name']}' so boss rewards won't hang")
        have += 1
        i += 1
    return made


def _resolve_bridge_ctx(bp: dict):
    """Resolve the two archetypes' catalog `ops` for the O-1 witness detector. Returns
    {ops_a, ops_b, name_a, name_b} or None when the ops can't be resolved — an invented concept-path
    archetype id not in the catalog, or an archetype with no ops — in which case the semantic bridge check
    is skipped (the blueprint-stage tag-count + rare floor still applies). Fully guarded: any failure yields
    None and the forge proceeds (coverage is advisory)."""
    try:
        from .frontend.catalog import load_catalog
        archs = [a for a in (bp.get("archetypes") or []) if isinstance(a, dict)]
        if len(archs) != 2:
            return None
        cat = load_catalog()
        resolved = []
        for a in archs:
            e = cat.by_id.get(str(a.get("id")))
            ops = set(e.ops) if e else set()
            if not ops:
                return None
            resolved.append((str(a.get("name") or a.get("id") or "engine"), ops))
        (name_a, ops_a), (name_b, ops_b) = resolved
        return {"ops_a": ops_a, "ops_b": ops_b, "name_a": name_a, "name_b": name_b}
    except Exception:
        return None


def forge_class(brief: ClassBrief, *, blueprint_gen, card_gen_factory, relic_gen=None, fake: bool = False,
                on_event=None, front_end=None) -> ClassResult:
    """Orchestrate one class. `blueprint_gen` does the blueprint call; `card_gen_factory()` returns a fresh
    card generator for the card pipeline (Anthropic / OpenAI-compatible / fake). `on_event(str)`, if given,
    is called with each progress line as it happens (the website streams these to the browser).

    `front_end` (a BlueprintBuilder) opts into the STAGED creative front-end: instead of the single opaque
    blueprint call, it runs cloud->cluster->map->compose->relic-intent and produces the SAME `bp` dict. The
    bp shape is identical, so stage 2 onward (card set, safety nets, assembly) is untouched. None -> today's
    one-shot path."""
    from .contract import Brief as CardBrief
    from .pipeline import generate_card
    from .validator import CardValidator
    from .bts1 import VOCAB_VERSION

    res = ClassResult(ok=False)

    def note(m: str) -> None:
        res.log.append(m)
        if on_event is not None:
            try:
                on_event(m)
            except Exception:
                pass  # a broken progress sink must never break generation

    # Stamp every forge with the harness version up front — the first log line on both the CLI and the
    # browser stream, so you can tell which creative-harness produced a given class. See HARNESS_VERSION.
    note(f"forge harness v{HARNESS_VERSION} (vocab v{VOCAB_VERSION})")

    # --- Phase N-2: roll the featured-mechanic roulette (seeded per concept) BEFORE stage 1 so both brief
    # modes REQUIRE them. The one-shot concept brief uses this BLIND roll as-is; the staged front-end may
    # RE-ROLL theme-aware after its cloud stage (Phase N-5) — brief.featured is re-resolved after build().
    # Missing picks are checked + repaired by the N-1 coverage round.
    from . import featured as _featured_mod
    _feat = _featured_mod.roll_featured(brief.concept)
    brief.featured = [f.id for f in _feat]
    if _feat:
        note("featured mechanics (rolled): " + "; ".join(f.id for f in _feat))

    # --- stage 1: blueprint -------------------------------------------------
    if fake:
        bp = _fake_blueprint(brief)
    elif front_end is not None:
        # Staged creative front-end (cloud->cluster->map->compose->relic-intent -> a bp dict).
        note("running the staged creative front-end...")
        try:
            bp = front_end.build(brief)
        except Exception as e:  # noqa: BLE001 — a front-end failure aborts the class, like a bad blueprint
            note(f"front-end failed: {e}")
            return res
        errs = _validate_blueprint(bp) if isinstance(bp, dict) else ["front-end returned no blueprint"]
        if errs:
            note("front-end blueprint invalid: " + "; ".join(errs[:5]))
            return res
        # Phase N-5: the front-end may have re-rolled brief.featured theme-aware — re-resolve so the
        # coverage round enforces the FINAL picks, not the blind pre-roll.
        _feat = _featured_mod.resolve(getattr(brief, "featured", None) or [])
    else:
        note("designing the class blueprint...")
        text, messages = blueprint_gen.first_attempt(brief)
        bp = _extract(text)
        errs = _validate_blueprint(bp) if bp is not None else ["unparseable blueprint"]
        if errs:
            note(f"blueprint attempt 1: {len(errs)} error(s); repairing")
            text, messages = blueprint_gen.repair(messages, text, errs)
            bp = _extract(text)
            errs = _validate_blueprint(bp) if bp is not None else ["unparseable blueprint"]
            if errs:
                hint = (" (the model's response was likely cut off mid-JSON — usually a transient "
                        "thinking-heavy response; try again)") if errs == ["unparseable blueprint"] else ""
                note("blueprint invalid after repair: " + "; ".join(errs[:5]) + hint)
                return res
    res.blueprint = bp
    # Phase N-5: the FINAL featured ids ride the blueprint so the ledger records them (recency damping for
    # later themed rolls). Bundle assembly reads explicit keys, so this never leaks into the shipped class.
    bp["featured"] = [f.id for f in _feat]
    _arche = ", ".join(str(a.get("name") or a.get("id") or "") for a in (bp.get("archetypes") or [])
                       if isinstance(a, dict))
    note(f"blueprint ready: '{bp['name']}' ({bp.get('max_hp', '?')} HP)"
         + (f" built around {_arche}" if _arche else "")
         + f" - now designing {len(bp['cards'])} cards one by one:")

    # --- stage 2: the card set ----------------------------------------------
    # Inject the class's custom orb names (Phase I) + custom status names (Phase J) + custom summon names
    # (Phase K) so channel / apply_status_custom / summon cards may reference them by pool name.
    validator = CardValidator(extra_orbs=_orb_pool_custom_names(bp),
                              extra_statuses=_status_pool_custom_names(bp),
                              extra_summons=_summon_pool_custom_names(bp))
    card_gen = card_gen_factory()
    made: list[dict] = []  # {plan, card} in slot order
    total = len(bp["cards"])
    for i, plan in enumerate(bp["cards"]):
        if plan.get("role") in _BASIC_ROLES:
            card = _synthesize_basic(plan)
            made.append({"plan": plan, "card": card})
            note(f"card {i+1}/{total}: {card['name']} (synthesized basic, no design needed)")
            continue
        if plan.get("role") == _BLADE_ROLE:
            # The signature blade is synthesized (like the basics), not LLM-designed — its retain+forged shape
            # and token flag are guaranteed by construction. The blueprint only names/themes it.
            card = _synthesize_blade(plan)
            made.append({"plan": plan, "card": card})
            note(f"card {i+1}/{total}: {card['name']} (synthesized Sovereign Blade — cost 2, retain, "
                 "damage + your Forge; a token summoned to hand on your first Forge, not in the deck)")
            continue
        theme = plan.get("theme", "")
        if plan.get("name_hint"):
            theme = f"{theme} (suggested name: {plan['name_hint']})"
        cbrief = CardBrief(card_type=plan.get("type", "attack"), rarity=plan.get("rarity", "common"),
                           target_cost=plan.get("cost"), theme=theme)
        note(f"card {i+1}/{total}: designing '{plan.get('name_hint', '?')}' - "
             f"{plan.get('rarity', '?')} {plan.get('type', '?')}, cost {plan.get('cost', '?')}"
             + (f" - {str(plan.get('theme'))[:90]}" if plan.get("theme") else ""))
        pres = generate_card(cbrief, gen=card_gen, validator=validator)
        if not pres.ok or pres.card is None:
            res.skipped.append(plan.get("name_hint", f"card {i+1}"))
            note(f"card {i+1} ({plan.get('name_hint','?')}): failed, skipped")
            continue
        # Safety net: orb ops/Focus only belong to an orb class (orb_slots > 0). On a normal class they
        # do nothing, so drop any card the model snuck them onto.
        if int(bp.get("orb_slots", 0) or 0) == 0 and _card_uses_orbs(pres.card):
            res.skipped.append(plan.get("name_hint", f"card {i+1}"))
            note(f"card {i+1} ({plan.get('name_hint','?')}): orb op on a non-orb class — dropped")
            continue
        # Safety net (Phase J): apply_status_custom only belongs to a status class. Drop it off a class with
        # no status_pool (the validator's extra_statuses already rejects unknown names, but a class with NO
        # pool would have an empty allowed set, so this is the belt-and-braces drop).
        if not _status_pool_custom_names(bp) and _card_uses_custom_status(pres.card):
            res.skipped.append(plan.get("name_hint", f"card {i+1}"))
            note(f"card {i+1} ({plan.get('name_hint','?')}): custom status on a non-status class — dropped")
            continue
        # Safety net (Phase K): summon only belongs to a summon class. Drop it off a class with no summon_pool
        # (same belt-and-braces as the orb/status drops above).
        if not _summon_pool_custom_names(bp) and _card_uses_summons(pres.card):
            res.skipped.append(plan.get("name_hint", f"card {i+1}"))
            note(f"card {i+1} ({plan.get('name_hint','?')}): summon on a non-summon class — dropped")
            continue
        made.append({"plan": plan, "card": pres.card})
        validator.known_cards.add(pres.card["id"])
        if pres.balance_repaired and pres.balance_repair:
            br = pres.balance_repair
            note(f"card {i+1} ({pres.card.get('name')}): overtuned — auto-tuned "
                 f"{br['score_before']:.0f} -> {br['score_after']:.0f} (budget ~{br['ceiling']:.0f})")
        note(f"card {i+1}/{total}: {pres.card.get('name')} ready "
             f"({pres.card.get('rarity')} {pres.card.get('type', '')})")

    if len(made) < 3:
        note("too few cards survived; aborting class")
        return res

    # --- stage 2.4 (Phase N-1): set-level creative-breadth coverage + ONE bounded repair round ----------
    # Census the non-basic pool; if it's short on distinctive mechanics, regenerate the plainest cards with a
    # compact REQUIRED directive naming the miss. Advisory only (WARNING notes, never fatal) and runs BEFORE
    # the merchant/rare safety nets so any repaired card flows through them.
    def _regen_card(plan: dict, old_card: dict, directive: str):
        """Rebuild ONE pool card with its theme + an appended coverage/featured directive. Returns the new
        card dict or None (keep the original). Applies the SAME class-kind safety-net drops as the main loop
        and keeps card ids unique against the rest of the set."""
        theme = plan.get("theme", "")
        if plan.get("name_hint"):
            theme = f"{theme} (suggested name: {plan['name_hint']})"
        theme = f"{theme}\n{directive}".strip()
        cbrief = CardBrief(card_type=plan.get("type", "attack"), rarity=plan.get("rarity", "common"),
                           target_cost=plan.get("cost"), theme=theme)
        pres = generate_card(cbrief, gen=card_gen, validator=validator)
        if not pres.ok or pres.card is None:
            return None
        new = pres.card
        # same class-kind guards as the per-card loop: a repaired card must not sneak orb / custom-status /
        # summon ops onto a class that has no such pool.
        if int(bp.get("orb_slots", 0) or 0) == 0 and _card_uses_orbs(new):
            return None
        if not _status_pool_custom_names(bp) and _card_uses_custom_status(new):
            return None
        if not _summon_pool_custom_names(bp) and _card_uses_summons(new):
            return None
        old_id = (old_card or {}).get("id")
        avoid = {(m.get("card") or {}).get("id") for m in made} - {old_id, None}
        nid = new.get("id") or _slug(new.get("name", ""), "forged_card")
        if nid in avoid:
            k = 2
            while f"{nid}_{k}" in avoid:
                k += 1
            nid = f"{nid}_{k}"
            new["id"] = nid
        if old_id:
            validator.known_cards.discard(old_id)
        validator.known_cards.add(nid)
        return new

    try:
        from . import coverage
        coverage.enforce_coverage(made, _regen_card, note, featured=_feat,
                                  bridge_ctx=_resolve_bridge_ctx(bp))
    except Exception as e:  # coverage is advisory — a bug here must never break a forge
        note(f"coverage: skipped (internal error: {e})")

    # Merchant safety net: guarantee the non-basic pool has a card of every type the shop wants (Attack/Skill/
    # Power). Generation can drop the planned Power, leaving an empty bucket that hangs the merchant in-game.
    made = _ensure_merchant_types(made, note)
    # Boss-reward safety net: guarantee >=MIN_RARES Rares so a boss card reward can always roll one (an empty
    # Rare bucket soft-locks the rewards screen — the boss-reward-rarity-hang).
    made = _ensure_min_rares(made, note)

    # Phase K (v15) design self-check: the summon is PASSIVE — `summon_attack` is its ONLY offense and the only
    # thing `buff_summon` (Strength) can be spent on. Surface a summon class that ended up with buff_summon but no
    # summon_attack (a dead-buff hole — see THE SUMMON POOL guidance). A note, not a reject (the class still ships;
    # the blueprint guidance is the real fix).
    if _summon_pool_custom_names(bp):
        def _class_has_op(op: str) -> bool:
            return any(e.get("op") == op
                       for m in made
                       for e in (list(m["card"].get("effects") or [])
                                 + list((m["card"].get("upgrade") or {}).get("effects") or [])))
        if _class_has_op("buff_summon") and not _class_has_op("summon_attack"):
            note("WARNING: summon class has buff_summon cards but NO summon_attack — the passive minion never "
                 "attacks on its own, so its Strength buffs are dead weight. Add summon_attack cards (re-forge).")

    # --- stage 2.5: the keystone starter relic (Phase L) --------------------
    # Optional + non-fatal: if relic generation fails, the class still ships (the slot defaults to Burning Blood).
    relic = None
    if fake:
        relic = _fake_relic(bp)
    elif relic_gen is not None:
        note("designing the keystone starter relic...")

        def _relic_errors(r) -> list[str]:
            # structural gate (mirrors the C# importer), then — only on a structurally-sound relic —
            # the deck-aware power gate (the "Diamond Hands" fix: a condition this deck trivially
            # satisfies must not unlock an always-on payout).
            errs = _validate_relic(r, bp) if r is not None else ["unparseable relic"]
            return errs or _relic_balance_errors(r, made, validator)

        rtext, rmsgs = relic_gen.first_attempt(bp)
        relic = _extract(rtext)
        rerrs = _relic_errors(relic)
        if rerrs:
            note(f"relic attempt 1: {len(rerrs)} error(s); repairing")
            rtext, rmsgs = relic_gen.repair(rmsgs, rtext, rerrs)
            relic = _extract(rtext)
            rerrs = _relic_errors(relic)
        if rerrs:
            note("relic invalid after repair; shipping without a forged relic (defaults to Burning Blood): "
                 + "; ".join(rerrs[:3]))
            relic = None
        else:
            relic.setdefault("source", "llm")
            note(f"relic OK: {relic.get('name')}")
    if relic is not None:
        relic.setdefault("tier", "starter")

    # --- stage 2.6: guarantee the signature blade for a forge class ---------
    # A forge class — Forge income anywhere (a card, a trigger payload, or the relic hook) — MUST ship its
    # Sovereign Blade, the identity anchor that cashes the counter. The blueprint normally supplies one
    # (role signature_blade, synthesized in the loop above); if the model didn't design one, synthesize a
    # default-named blade so the signature is never missing. We only ADD a blade where Forge income already
    # exists — never fabricate income. (Belt-and-braces with the blueprint prompt, like the merchant/rare nets.)
    has_blade = any(m["plan"].get("role") == _BLADE_ROLE or m["card"].get("token") for m in made)
    has_income = any(_card_forges(m["card"]) for m in made) or _relic_forges(relic)
    if has_income and not has_blade:
        blade = _synthesize_blade(None)
        made.append({"plan": {"role": _BLADE_ROLE, "deck_count": 0}, "card": blade})
        note(f"blade-safety: forge class had Forge income but no signature blade; added '{blade['name']}' "
             "(cost 2, retain, damage + your Forge) as a token summoned on your first Forge (not in the deck)")

    # --- stage 3: assemble the BTSC bundle ----------------------------------
    # Hard backstop: the mod holds CARDS_PER_CLASS card slots and the import rejects a larger bundle. The
    # blueprint cap + "safety nets only restore drops" reasoning means this never triggers, but if it somehow
    # does, drop trailing pool fillers (never a basic/signature) so the class still imports.
    if len(made) > CARDS_PER_CLASS:
        protected = _BASIC_ROLES | _SIGNATURE_ROLES | {_BLADE_ROLE}  # never trim a basic, a signature, or the blade
        kept = [m for m in made if m["plan"].get("role") in protected]
        for m in made:
            if m["plan"].get("role") not in protected and len(kept) < CARDS_PER_CLASS:
                kept.append(m)
        dropped = len(made) - len(kept)
        note(f"cap-guard: trimmed {dropped} surplus pool card(s) to fit the {CARDS_PER_CLASS}-card class cap")
        made = [m for m in made if m in kept]

    # Lock the starting deck to EXACTLY STARTING_DECK_SIZE cards (base-game / mod contract). Each signature
    # contributes 1 copy; the two basics absorb the remainder, so the deck is always 10 regardless of how many
    # signatures survived (1 sig -> 5 Strike + 4 Defend + 1; 2 sig -> 4 + 4 + 1 + 1; 0 sig -> 5 + 5). The blade
    # is NOT counted here (Phase T: summoned on first Forge, never seeded) and is forced to deck_count 0 below.
    n_sig = sum(1 for m in made if m["plan"].get("role") in _SIGNATURE_ROLES)  # signatures only (NOT the blade)
    rest = max(0, STARTING_DECK_SIZE - n_sig)
    atk_count = (rest + 1) // 2  # attack gets the larger half
    skill_count = rest - atk_count
    for m in made:
        role = m["plan"].get("role")
        if role == "basic_attack":
            m["plan"]["deck_count"] = atk_count
        elif role == "basic_skill":
            m["plan"]["deck_count"] = skill_count
        elif role in _SIGNATURE_ROLES:
            m["plan"]["deck_count"] = 1
        elif role == _BLADE_ROLE:
            m["plan"]["deck_count"] = 0  # Phase T: the blade is summoned, never in the starting deck
    cards = [m["card"] for m in made]
    starting_deck = []
    for slot, m in enumerate(made, start=1):
        cnt = int(m["plan"].get("deck_count", 0) or 0)
        if cnt > 0:
            starting_deck.append({"slot": slot, "count": cnt})
    orb_slots = int(bp.get("orb_slots", 0) or 0)
    character = {
        "name": bp["name"],
        "description": bp.get("description", ""),
        "max_hp": int(bp.get("max_hp", 70)),
        "max_energy": int(bp.get("max_energy", 3)),
        "orb_slots": orb_slots,
        "starting_deck": starting_deck,
    }
    # Phase I: carry the forged orb pool (only meaningful on an orb class). The C# importer re-validates it.
    orb_pool = bp.get("orb_pool") or []
    if orb_slots > 0 and orb_pool:
        character["orb_pool"] = orb_pool
    # Phase J: carry the forged status pool (the class's signature custom buffs/debuffs). Re-validated on import.
    status_pool = bp.get("status_pool") or []
    if status_pool:
        character["status_pool"] = status_pool
    # Phase K: carry the forged summon pool (the class's minions). Re-validated on import.
    summon_pool = bp.get("summon_pool") or []
    if summon_pool:
        character["summon_pool"] = summon_pool
    res.bundle = {"kind": "class", "character": character, "cards": cards}
    # Phase L: the keystone starter relic rides the bundle as a top-level sibling (the C# importer folds it into
    # the character dict + re-validates via TryParseRelic). Optional — absent → the class uses Burning Blood.
    if relic is not None:
        res.bundle["relic"] = relic
    res.ok = True
    note(f"bundle assembled: {len(cards)} cards, starting deck {sum(d['count'] for d in starting_deck)} cards"
         + (f", relic '{relic['name']}'" if relic is not None else ""))
    # Phase N-4: record this successful forge in the cross-forge usage ledger (guarded — a ledger failure
    # must NEVER break a shipped class). Later forges read the window to steer away from recent repeats.
    try:
        from . import ledger
        if ledger.record_forge(res.bundle, bp):
            note("recorded this forge in the cross-forge usage ledger")
    except Exception:
        pass
    return res


# --- offline fakes (no key) ----------------------------------------------------------------------

def _extract(text: str) -> dict | None:
    from .generator import extract_card_json
    try:
        return extract_card_json(text)
    except ValueError:
        return None


def _ensure_bridge_tags(bp: dict) -> dict:
    """Phase O-1: tag >=MIN_BRIDGES non-basic pool cards as bridges, at least one a rare — so a fake or
    topped-up blueprint satisfies the fusion-enforcer tag-count + rare floor in _validate_blueprint. Fake
    bridges will NOT semantically WITNESS both engines (that is the real forge's job, checked by the coverage
    round); here we only guarantee the tags so the offline paths validate. Mutates + returns bp."""
    cards = bp.setdefault("cards", [])
    pool = [c for c in cards if isinstance(c, dict) and c.get("role") == "pool"]

    def _bridges():
        return [c for c in pool if c.get("bridge")]

    def _has_rare_bridge():
        return any(str(c.get("rarity", "")).lower() == "rare" for c in _bridges())

    # the rare poster bridge first, then fill to the count with any remaining pool cards
    if not _has_rare_bridge():
        rare = next((c for c in pool if str(c.get("rarity", "")).lower() == "rare" and not c.get("bridge")), None)
        if rare is not None:
            rare["bridge"] = True
    for c in pool:
        if len(_bridges()) >= MIN_BRIDGES:
            break
        c["bridge"] = True
    # pool too small to tag enough (shouldn't happen after the topup above) — append bridge fillers
    n = 0
    while len(_bridges()) < MIN_BRIDGES:
        n += 1
        filler = {"role": "pool", "name_hint": f"Fusion {n}", "type": "skill",
                  "rarity": "rare" if not _has_rare_bridge() else "common", "cost": 1, "deck_count": 0,
                  "archetype": None, "strategy": None, "bridge": True, "theme": "fuse both archetypes"}
        cards.append(filler)
        pool.append(filler)
    return bp


def _topup_blueprint_briefs(bp: dict, strategies=None) -> dict:
    """Append filler pool BRIEFS so a (light) fake blueprint satisfies _validate_blueprint: a non-basic card of
    every merchant type + at least MIN_RARES rares + a full package (>=_LINE_MIN_CARDS cards, >=1 rare) for
    each strategic line in `strategies` (default: two, so the generic >=2-lines floor passes). Only used by
    the staged front-end's --fake path."""
    cards = bp.setdefault("cards", [])

    def _nonbasic_types() -> set:
        return {str(c.get("type", "")).lower() for c in cards
                if c.get("role") not in _BASIC_ROLES and str(c.get("rarity", "")).lower() != "basic"}

    def _rares() -> int:
        return sum(1 for c in cards if c.get("role") not in _BASIC_ROLES
                   and str(c.get("rarity", "")).lower() == "rare")

    def _brief(t: str, n: int) -> dict:
        return {"role": "pool", "name_hint": f"Spare {t.title()} {n}", "type": t, "rarity": "rare",
                "cost": 2, "deck_count": 0, "archetype": None, "theme": f"a rare {t}"}

    n = 0
    for t in _MERCHANT_TYPES:
        if t not in _nonbasic_types():
            n += 1; cards.append(_brief(t, n))
    while _rares() < MIN_RARES:
        n += 1; cards.append(_brief(_MERCHANT_TYPES[n % len(_MERCHANT_TYPES)], n))
    # Strategy coverage: honor the declared lines when given, else default to two so the floor passes.
    want = [s for s in dict.fromkeys(str(x).strip().lower() for x in (strategies or [])) if s in STRATEGIES]
    if len(want) < 2:
        want += [s for s in STRATEGIES if s not in want][:2 - len(want)]

    def _line(s: str) -> tuple[int, int]:
        tagged = [c for c in cards if c.get("role") not in _BASIC_ROLES
                  and str(c.get("strategy") or "").strip().lower() == s]
        return len(tagged), sum(1 for c in tagged if str(c.get("rarity", "")).lower() == "rare")

    for s in want:
        cnt, rare_cnt = _line(s)
        while cnt < _LINE_MIN_CARDS or rare_cnt < 1:
            n += 1
            rarity = "rare" if rare_cnt < 1 else "common"
            cards.append({"role": "pool", "name_hint": f"Spare {s.title()} {n}", "type": "skill",
                          "rarity": rarity, "cost": 1, "deck_count": 0, "archetype": None,
                          "strategy": s, "theme": f"a {rarity} {s}-line card"})
            cnt, rare_cnt = _line(s)
    return _ensure_bridge_tags(bp)  # O-1: satisfy the >=MIN_BRIDGES + rare fusion floor


def _fake_blueprint(brief: ClassBrief) -> dict:
    """Offline blueprint for --fake. Wraps the per-kind variant with the O-1 bridge tags so the fake path
    carries valid `"bridge"` tags too (the one-shot --fake path skips validation, but the tags keep the
    offline blueprints honest and let the bridge coverage plumbing exercise on them)."""
    return _ensure_bridge_tags(_fake_blueprint_variant(brief))


def _fake_blueprint_variant(brief: ClassBrief) -> dict:
    c = (brief.concept or "").lower()
    if any(k in c for k in ("forge", "smith", "anvil", "hammer", "blacksmith", "molten", "furnace", "sovereign")):
        # Offline FORGE-class fake (Phase T): exercises the signature_blade role (synthesized token, summoned on
        # first Forge, NOT in the deck) + Forge income (cards + a turn_start engine) + BOTH blade-manipulation
        # forms (on_blade_played rider + summon_blade retrieval) so the decision-#9 rule is covered offline.
        return {
            "name": "Test Forge",
            "description": f"Offline fake FORGE class for: {brief.concept[:60]}",
            "max_hp": 74,
            "orb_slots": 0,
            "archetypes": [
                {"id": "forge_ramp", "name": "Forge Ramp", "description": "stoke the Forge, swing the growing blade"},
                {"id": "temper", "name": "Temper", "description": "Block and outlast while the blade sharpens"},
            ],
            "cards": [
                {"role": "basic_attack", "name_hint": "Strike", "type": "attack", "rarity": "basic", "cost": 1, "deck_count": 5, "archetype": None, "theme": "Strike"},
                {"role": "basic_skill", "name_hint": "Defend", "type": "skill", "rarity": "basic", "cost": 1, "deck_count": 4, "archetype": None, "theme": "Defend"},
                {"role": "signature_blade", "name_hint": "Sovereign Blade", "type": "attack", "rarity": "token", "cost": 2, "deck_count": 0, "archetype": "forge_ramp", "theme": "the class's growing signature weapon"},
                {"role": "pool", "name_hint": "Riposte", "type": "power", "rarity": "uncommon", "cost": 1, "deck_count": 0, "archetype": "temper", "strategy": "control", "theme": "power: whenever you play your blade, gain 8 block (parry)"},
                {"role": "pool", "name_hint": "Summon Forth", "type": "skill", "rarity": "common", "cost": 0, "deck_count": 0, "archetype": "forge_ramp", "strategy": None, "theme": "summon_blade — put your blade to your hand from anywhere"},
                {"role": "pool", "name_hint": "Kindle", "type": "skill", "rarity": "common", "cost": 1, "deck_count": 0, "archetype": "forge_ramp", "strategy": None, "theme": "forge 2 to stoke your counter"},
                {"role": "pool", "name_hint": "Stoke", "type": "power", "rarity": "common", "cost": 1, "deck_count": 0, "archetype": "forge_ramp", "strategy": "control", "theme": "power: at the start of your turn, forge 2 (the engine)"},
                {"role": "pool", "name_hint": "Emberstrike", "type": "attack", "rarity": "common", "cost": 1, "deck_count": 0, "archetype": "forge_ramp", "strategy": "aggro", "theme": "deal 6 damage, plus your Forge"},
                {"role": "pool", "name_hint": "Heavy Blow", "type": "attack", "rarity": "uncommon", "cost": 2, "deck_count": 0, "archetype": "forge_ramp", "strategy": "aggro", "theme": "deal heavy damage"},
                {"role": "pool", "name_hint": "Anvil Guard", "type": "skill", "rarity": "common", "cost": 1, "deck_count": 0, "archetype": "temper", "strategy": "control", "theme": "block and draw a card"},
                {"role": "pool", "name_hint": "Reforge", "type": "skill", "rarity": "uncommon", "cost": 1, "deck_count": 0, "archetype": "forge_ramp", "strategy": "control", "theme": "forge 3"},
                {"role": "pool", "name_hint": "Overheat", "type": "attack", "rarity": "rare", "cost": 2, "deck_count": 0, "archetype": "forge_ramp", "strategy": "aggro", "theme": "deal big damage, plus your Forge"},
                {"role": "pool", "name_hint": "Bulwark", "type": "power", "rarity": "rare", "cost": 1, "deck_count": 0, "archetype": "temper", "strategy": "control", "theme": "power: at the end of your turn, gain Block"},
                {"role": "pool", "name_hint": "Molten Edge", "type": "skill", "rarity": "rare", "cost": 2, "deck_count": 0, "archetype": "temper", "strategy": "aggro", "theme": "gain big block"},
            ],
        }
    if any(k in c for k in ("orb", "slot machine", "element", "storm", "lightning", "frost", "channel")):
        # Offline ORB-class fake: exercises orb_slots + the channel/evoke/focus card path end-to-end.
        return {
            "name": "Test Tempest",
            "description": f"Offline fake ORB class for: {brief.concept[:60]}",
            "max_hp": 70,
            "orb_slots": 3,
            # MIXED pool: base lightning + a custom Ember orb (exercises the Phase I forged-orb path offline).
            "orb_pool": [
                "lightning",
                {"name": "Ember", "passive_val": 2, "evoke_val": 8,
                 "passive": [{"op": "damage", "amount": 2, "target": "enemy"}],
                 "evoke": [{"op": "damage", "amount": 8, "target": "all_enemies"}]},
            ],
            "archetypes": [
                {"id": "channel", "name": "Channel", "description": "channel orbs that tick each turn"},
                {"id": "discharge", "name": "Discharge", "description": "evoke bursts and Focus scaling"},
            ],
            "cards": [
                {"role": "basic_attack", "name_hint": "Strike", "type": "attack", "rarity": "basic", "cost": 1, "deck_count": 5, "archetype": None, "theme": "Strike"},
                {"role": "basic_skill", "name_hint": "Defend", "type": "skill", "rarity": "basic", "cost": 1, "deck_count": 4, "archetype": None, "theme": "Defend"},
                {"role": "signature", "name_hint": "Spark", "type": "skill", "rarity": "basic", "cost": 1, "deck_count": 1, "archetype": "channel", "theme": "channel a lightning orb"},
                {"role": "pool", "name_hint": "Kindle", "type": "skill", "rarity": "common", "cost": 1, "deck_count": 0, "archetype": "channel", "theme": "channel an ember orb"},
                {"role": "pool", "name_hint": "Dark Well", "type": "skill", "rarity": "common", "cost": 1, "deck_count": 0, "archetype": "channel", "theme": "channel a lightning orb"},
                {"role": "pool", "name_hint": "Discharge", "type": "skill", "rarity": "uncommon", "cost": 1, "deck_count": 0, "archetype": "discharge", "theme": "evoke your next orb"},
                {"role": "pool", "name_hint": "Attune", "type": "power", "rarity": "uncommon", "cost": 1, "deck_count": 0, "archetype": "discharge", "theme": "gain focus"},
                {"role": "pool", "name_hint": "Jackpot", "type": "attack", "rarity": "rare", "cost": 2, "deck_count": 0, "archetype": "channel", "theme": "channel 3 random orbs, then deal big damage if your orbs match"},
            ],
        }
    if any(k in c for k in ("status", "duelist", "blade", "razor", "sharpen", "brittle", "signature")):
        # Offline STATUS-class fake: exercises status_pool + the apply_status_custom card path end-to-end.
        return {
            "name": "Test Edge",
            "description": f"Offline fake STATUS class for: {brief.concept[:60]}",
            "max_hp": 74,
            "orb_slots": 0,
            "status_pool": [
                {"name": "Razor Focus", "emoji": "\U0001F5E1", "type": "buff", "hook": "damage_dealt",
                 "decay": "none", "description": "Your attacks deal bonus damage equal to its stacks."},
                {"name": "Brittle", "emoji": "\U0001F494", "type": "debuff", "hook": "damage_taken",
                 "decay": "none", "description": "This enemy takes bonus damage equal to its stacks."},
            ],
            "archetypes": [
                {"id": "edge", "name": "Edge", "description": "stack Razor Focus, then strike"},
                {"id": "expose", "name": "Expose", "description": "apply Brittle, then exploit"},
            ],
            "cards": [
                {"role": "basic_attack", "name_hint": "Strike", "type": "attack", "rarity": "basic", "cost": 1, "deck_count": 5, "archetype": None, "theme": "Strike"},
                {"role": "basic_skill", "name_hint": "Defend", "type": "skill", "rarity": "basic", "cost": 1, "deck_count": 4, "archetype": None, "theme": "Defend"},
                {"role": "signature", "name_hint": "Razor Edge", "type": "skill", "rarity": "basic", "cost": 1, "deck_count": 1, "archetype": "edge", "theme": "gain 2 razor focus"},
                {"role": "pool", "name_hint": "Lacerate", "type": "attack", "rarity": "common", "cost": 1, "deck_count": 0, "archetype": "expose", "theme": "deal damage and apply brittle to the enemy"},
                {"role": "pool", "name_hint": "Whetstone", "type": "skill", "rarity": "common", "cost": 1, "deck_count": 0, "archetype": "edge", "theme": "gain 2 razor focus"},
                {"role": "pool", "name_hint": "Bladesong", "type": "power", "rarity": "uncommon", "cost": 1, "deck_count": 0, "archetype": "edge", "theme": "power: at the end of your turn, gain Block (a per-turn trigger engine)"},
                {"role": "pool", "name_hint": "Killing Blow", "type": "attack", "rarity": "rare", "cost": 2, "deck_count": 0, "archetype": "expose", "theme": "deal big damage"},
            ],
        }
    if any(k in c for k in ("summon", "minion", "beast", "wolf", "necromanc", "conjur", "pet", "commander", "tame")):
        # Offline SUMMON-class fake (v15 true-Osty): ONE passive minion + the summon / summon_attack / buff_summon
        # card path end-to-end. The minion does nothing on its turn; cards strike through it and pump its Strength.
        return {
            "name": "Test Thrall",
            "description": f"Offline fake SUMMON class for: {brief.concept[:60]}",
            "max_hp": 70,
            "orb_slots": 0,
            "summon_pool": [
                {"name": "Bone Thrall", "max_hp": 12,
                 "description": "A raised servant that guards you and strikes at your command."},
            ],
            "archetypes": [
                {"id": "raise", "name": "Raise", "description": "summon and grow the thrall"},
                {"id": "command", "name": "Command", "description": "strike through the thrall and buff it"},
            ],
            "cards": [
                {"role": "basic_attack", "name_hint": "Strike", "type": "attack", "rarity": "basic", "cost": 1, "deck_count": 5, "archetype": None, "theme": "Strike"},
                {"role": "basic_skill", "name_hint": "Defend", "type": "skill", "rarity": "basic", "cost": 1, "deck_count": 4, "archetype": None, "theme": "Defend"},
                {"role": "signature", "name_hint": "Raise Thrall", "type": "skill", "rarity": "basic", "cost": 1, "deck_count": 1, "archetype": "raise", "theme": "summon your Bone Thrall (12 HP)"},
                {"role": "pool", "name_hint": "Command Strike", "type": "attack", "rarity": "common", "cost": 1, "deck_count": 0, "archetype": "command", "theme": "your summon strikes for 8"},
                {"role": "pool", "name_hint": "Feed Strength", "type": "skill", "rarity": "common", "cost": 1, "deck_count": 0, "archetype": "command", "theme": "your summon gains 2 Strength"},
                {"role": "pool", "name_hint": "Reinforce", "type": "skill", "rarity": "uncommon", "cost": 1, "deck_count": 0, "archetype": "raise", "theme": "raise your thrall's HP by 6 (summon)"},
                {"role": "pool", "name_hint": "Bone Bulwark", "type": "power", "rarity": "uncommon", "cost": 1, "deck_count": 0, "archetype": "raise", "theme": "power: at the end of your turn, gain Block (a per-turn trigger engine)"},
                {"role": "pool", "name_hint": "Reaping Blow", "type": "attack", "rarity": "rare", "cost": 2, "deck_count": 0, "archetype": "command", "theme": "your summon strikes for 14"},
            ],
        }
    return {
        "name": "Test Toxin",
        "description": f"Offline fake class for: {brief.concept[:80]}",
        "max_hp": 72,
        "orb_slots": 0,
        "archetypes": [
            {"id": "venom", "name": "Venom", "description": "stack Poison, then spread it"},
            {"id": "bulwark", "name": "Bulwark", "description": "Block and Dexterity tempo"},
        ],
        "cards": [
            {"role": "basic_attack", "name_hint": "Strike", "type": "attack", "rarity": "basic", "cost": 1, "deck_count": 5, "archetype": None, "theme": "Strike"},
            {"role": "basic_skill", "name_hint": "Defend", "type": "skill", "rarity": "basic", "cost": 1, "deck_count": 4, "archetype": None, "theme": "Defend"},
            {"role": "signature", "name_hint": "Tainted Edge", "type": "attack", "rarity": "basic", "cost": 1, "deck_count": 1, "archetype": "venom", "theme": "damage + a little poison"},
            {"role": "pool", "name_hint": "Spit", "type": "skill", "rarity": "common", "cost": 1, "deck_count": 0, "archetype": "venom", "theme": "apply poison to all enemies"},
            {"role": "pool", "name_hint": "Guard", "type": "skill", "rarity": "common", "cost": 1, "deck_count": 0, "archetype": "bulwark", "theme": "block + draw"},
            {"role": "pool", "name_hint": "Outbreak", "type": "skill", "rarity": "rare", "cost": 2, "deck_count": 0, "archetype": "venom", "theme": "big poison to all enemies + frail"},
            {"role": "pool", "name_hint": "Iron Will", "type": "power", "rarity": "rare", "cost": 1, "deck_count": 0, "archetype": "bulwark", "theme": "power: at the end of your turn, gain Block (a per-turn trigger engine)"},
        ],
    }


def _fake_relic(bp: dict) -> dict:
    """Offline keyless keystone relic — a modest always-on starter that exercises every v1 path: a once_per_combat
    buff, a per-turn block, a per-turn enemy tick, an hp_below_half conditional heal, a reactive attacked/attacker
    retaliation + on_exhaust/on_card_played blocks + a combat_end heal (L-3/L-4), and
    max_energy/first_attack/cost_reduction/start_combat_block modifiers."""
    name = str(bp.get("name", "Forged"))
    slug = "".join(c if c.isalnum() else "_" for c in name.lower()).strip("_") or "forged"
    return {
        "id": f"{slug}_keystone",
        "name": (f"{name} Sigil")[:32],
        "description": "Offline fake keystone relic.",
        "tier": "starter",
        "modifiers": [{"stat": "max_energy", "amount": 1}, {"stat": "first_attack", "amount": 3},
                      {"stat": "cost_reduction", "amount": 1}, {"stat": "start_combat_block", "amount": 4}],
        "hooks": [
            {"trigger": "turn_start", "once_per_combat": True,
             "effects": [{"op": "apply_status", "status": "strength", "amount": 1}]},
            {"trigger": "turn_start", "effects": [{"op": "block", "amount": 3}]},
            {"trigger": "turn_end", "target": "enemy", "effects": [{"op": "damage", "amount": 2}]},
            {"trigger": "turn_start", "when": {"kind": "hp_below_half"},
             "effects": [{"op": "heal", "amount": 3}]},
            {"trigger": "attacked", "target": "attacker", "effects": [{"op": "damage", "amount": 2}]},
            {"trigger": "on_exhaust", "effects": [{"op": "block", "amount": 1}]},
            {"trigger": "on_card_played", "once_per_combat": True, "effects": [{"op": "block", "amount": 2}]},
            {"trigger": "combat_end", "effects": [{"op": "heal", "amount": 4}]},  # Burning Blood
        ],
        "source": "llm",
    }


class _CardFake:
    """Keyless card generator emitting unique valid v2 cards (duck-types AnthropicGenerator)."""
    model = "fake-offline"

    def __init__(self) -> None:
        self._n = 0

    def first_attempt(self, brief):
        self._n += 1
        n = self._n
        rarity = getattr(brief, "rarity", "common")
        cost = max(1, getattr(brief, "target_cost", None) or 1)
        theme = (getattr(brief, "theme", "") or "").lower()
        base = {"id": f"forged_class_card_{n}", "name": f"Forged {n}", "rarity": rarity, "cost": cost, "source": "llm"}
        # Phase T blade manipulation FIRST — these markers ("summon_blade"/"parry"/"play your blade") are specific,
        # and a bare "summon"/"block" substring in the same theme would otherwise be caught by a later branch.
        if "on_blade_played" in theme or "play your blade" in theme or "parry" in theme or "riposte" in theme:
            card = {**base, "type": "power", "target": "self",
                    "effects": [{"op": "add_trigger", "trigger": "on_blade_played",
                                 "effects": [{"op": "block", "amount": 8}]}]}
        elif "summon_blade" in theme or "blade to your hand" in theme or "retrieve" in theme:
            card = {**base, "type": "skill", "target": "self", "effects": [{"op": "summon_blade"}]}
        # Phase J custom-status fakes — "razor focus" contains the substring "focus" (the orb-Focus
        # branch below) and "apply brittle" is otherwise a plain attack, so detect them before the orb branches.
        elif "razor focus" in theme:  # a self-buff custom status applied by a self-target card
            card = {**base, "type": "skill", "target": "self",
                    "effects": [{"op": "apply_status_custom", "status_name": "Razor Focus", "amount": 2 + (n % 2)}]}
        elif "brittle" in theme:  # a debuff custom status applied by an enemy-target card (+ damage)
            card = {**base, "type": "attack", "target": "enemy",
                    "effects": [{"op": "damage", "amount": 5 + n},
                                {"op": "apply_status_custom", "status_name": "Brittle", "amount": 2}]}
        # Phase K (v15 true-Osty) summon fakes — three ops drive the class's one minion ("Bone Thrall", matching the
        # SUMMON-class fake's pool). Check the SPECIFIC ops first ("your summon strikes/gains" both contain "summon").
        elif "your summon gains" in theme or "buff_summon" in theme:  # buff the living summon (default Strength)
            card = {**base, "type": "skill", "target": "self",
                    "effects": [{"op": "buff_summon", "amount": 2 + (n % 3), "status": "strength"}]}
        elif "strikes" in theme or "summon_attack" in theme or ("summon" in theme and "through" in theme):
            # strike THROUGH the summon (the minion is the dealer)
            card = {**base, "type": "attack", "target": "enemy",
                    "effects": [{"op": "summon_attack", "amount": 8 + n}]}
        elif "summon" in theme:  # the Osty Summon keyword: (re)summon / grow the minion, amount = HP
            card = {**base, "type": "skill", "target": "self",
                    "effects": [{"op": "summon", "summon_name": "Bone Thrall", "amount": 12}]}
        # Orb-aware fakes so an offline orb-class forge produces real orb cards. Check the slot-machine
        # (random + orbs_match) brief FIRST — its theme also contains "channel"/"orb" — then evoke/focus
        # before plain channel, since their briefs ("evoke your next orb") also contain the word "orb".
        elif "random" in theme or "match" in theme or "jackpot" in theme:
            card = {**base, "type": "attack", "target": "enemy",
                    "effects": [{"op": "channel_orb", "orb": "random", "amount": 3},
                                {"op": "damage", "amount": 12 + n, "when": {"kind": "orbs_match"}}]}
        elif "evoke" in theme:
            card = {**base, "type": "skill", "target": "self", "effects": [{"op": "evoke"}]}
        elif "channel" in theme or "orb" in theme:
            # include the fake's custom orb names (ember/cinder) so the orb-pool path is exercised offline
            orb = next((o for o in ("lightning", "frost", "dark", "ember", "cinder") if o in theme), "lightning")
            card = {**base, "type": "skill", "target": "self", "effects": [{"op": "channel_orb", "orb": orb}]}
        elif "focus" in theme:
            card = {**base, "type": "power", "target": "self",
                    "effects": [{"op": "apply_status", "status": "focus", "amount": 2 + (n % 3)}]}
        # Phase M forge fakes — a forged PAYOFF ("plus your Forge") vs Forge INCOME (stoke the counter). Check
        # the payoff phrase first ("plus your forge"/"forged" both contain "forge"), then income; the income
        # branch routes power/trigger themes to a turn-start forge engine, else a plain forge skill.
        elif "plus your forge" in theme or "forged" in theme:
            card = {**base, "type": "attack", "target": "enemy",
                    "effects": [{"op": "damage", "amount": 6 + n, "scale": "forged"}]}
        elif "forge" in theme:
            if any(w in theme for w in ("power", "trigger", "each turn", "start of turn", "end of turn")):
                kind = "turn_end" if "end of turn" in theme else "turn_start"
                card = {**base, "type": "power", "target": "self",
                        "effects": [{"op": "add_trigger", "trigger": kind,
                                     "effects": [{"op": "forge", "amount": 2}]}]}
            else:
                card = {**base, "type": "skill", "target": "self",
                        "effects": [{"op": "forge", "amount": 2 + (n % 3)}]}
        elif "trigger" in theme or "each turn" in theme or "end of turn" in theme or "start of turn" in theme:
            kind = "turn_start" if "start" in theme else "turn_end"
            card = {**base, "type": "power", "target": "self",
                    "effects": [{"op": "add_trigger", "trigger": kind,
                                 "effects": [{"op": "block", "amount": 4 + (n % 3)}]}]}
        else:
            # vary effects a little by index so the validator's reprint gate doesn't trip
            effects = [{"op": "damage", "amount": 5 + n}, {"op": "apply_status", "status": "poison", "amount": 2 + (n % 3)}]
            up = [{"op": "damage", "amount": 7 + n}, {"op": "apply_status", "status": "poison", "amount": 3 + (n % 3)}]
            card = {**base, "type": "attack", "target": "enemy", "effects": effects, "upgrade": {"effects": up}}
        text = json.dumps(card)
        return text, [{"role": "user", "content": "fake"}, {"role": "assistant", "content": text}]

    def repair(self, messages, prev_text, errors):
        return prev_text, messages

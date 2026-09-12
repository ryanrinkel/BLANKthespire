"""Validator-in-the-loop. Three checks, mirroring the engine's gate:

1. Schema shape + op vocab-closure + recursion  -> jsonschema against card.schema.json
2. Reference integrity (apply_status.status / add_card.card_id resolve)
3. Balance score  -> a faithful port of core/validation/ContentValidator.gd
   (same weights, same expected/ceiling formula) so harness scores match the engine.

The published card.schema.json is the single source of truth for shape. jsonschema
handles the recursive `effect` $ref that Anthropic structured-outputs cannot, so the
schema enforces the closed op vocabulary for free (the oneOf/const list). Statuses and
card ids are open strings in the schema, so they need the explicit ref check below — the
same split ContentValidator.gd makes.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from jsonschema import Draft202012Validator

from . import paths

# ---- balance constants: per-stack value of each status (Phase AJ-b: keyed to the MOD's 18 statuses) ----
# The base five came from the prototype's ContentValidator.gd; the rest (poison/thorns/regen/metallicize/artifact/
# buffer/blur/intangible/barricade/focus/temp_*) used to fall through to the 2.0 default, so Intangible 1 priced like
# Weak 1. Relative scale: a permanent stat (Strength 4, Dexterity 3) > a one-turn burst (temp_* ~half) > a decaying
# debuff (Vulnerable 2, Weak/Frail 1.5) ; the build-defining rares (Intangible/Ritual/Barricade) sit well above.
_STATUS_WEIGHT = {
    "vulnerable": 2.0, "weak": 1.5, "frail": 1.5,
    "poison": 1.2,          # N damage over N turns, decaying — a slow burn, cheaper than a flat hit
    "strength": 4.0, "dexterity": 3.0,
    "temp_strength": 2.0, "temp_dexterity": 1.5,   # this-turn only: ~half the permanent stat
    "temp_thorns": 1.0, "temp_focus": 1.5,         # Phase AN (v44): this-turn only, ~half of thorns / focus
    "thorns": 2.0,          # pays out per enemy hit taken
    "regen": 2.0,           # heal per turn, decaying
    "metallicize": 3.0,     # STS2 Plating: N + (N-1) + ... + 1 Block over N turns
    "artifact": 2.0, "buffer": 3.0, "blur": 2.0,
    "intangible": 8.0,      # a turn of near-invulnerability — rare-tier, keep amounts tiny
    "ritual": 4.0,          # Strength per turn: snowballs (rare-tier)
    "barricade": 4.0,       # Block persists/compounds (Barricade; the prototype called it "armor")
    "focus": 3.0,           # +N to every orb value (orb classes)
    # LEGACY (prototype contract only; harmless under the mod contract — its schema never emits these names)
    "strength_temp": 2.0, "armor": 4.0, "burrowed": 6.0,
}

_RARITY_RANK = {"basic": 0, "common": 1, "uncommon": 2, "rare": 3}
# ops whose integer `amount` is a flat, player-positive benefit (used by the dominance check)
_SIMPLE_BENEFIT_OPS = {"damage", "block", "draw", "gain_energy", "heal",
                       "gain_max_hp"}  # Phase AN (v44): a flat (run-permanent) stat gain
# Phase H3: composite/build-around ops (the schema/triggerEffect $def enforces add_trigger's payload shape;
# these are for the balance heuristics — a trigger is a build-around, not a flat stat line).
# Phase AJ-b: the prototype's composite ops (multi / conditional / from_state / fuse) are NOT in this set any more —
# the mod contract never sees them (its schema rejects them). They survive only in _LEGACY_PROTOTYPE_OPS, which the
# walker / scorer / build-around check consult ONLY when the active contract is the prototype one (self._mod_contract
# is False). Deleting them outright would retire the prototype-era validator tests; that is a separate decision.
_LEGACY_PROTOTYPE_OPS = {"multi", "conditional", "from_state", "fuse"}
_BUILD_AROUND_OPS = {"add_trigger", "apply_status_custom",
                     "summon", "summon_attack", "buff_summon",
                     "heal_summon", "shield_summon",  # Phase AC (gap #2): summon support, not a flat stat line
                     "sacrifice_summon",  # Phase AV (v52): spending the minion for a payoff is a build-around, not a stat line

                     "forge",  # Phase M (gap #36): Forge income/payoff is a build-around, not a stat line
                     "balance_step",  # Phase S (gap #1): a Balance-gauge step is build-around income, not a stat line
                     "upgrade_card",  # Phase V (gap #18): in-run upgrade is a utility/build-around, not a flat stat line
                     "blade_empower",  # Phase AF (gap #41): a transient blade multiplier is a build-around, not a stat line
                     "purge_card",  # Phase Z (gap #19 choose): targeted deck-thinning is a build-around, not a flat stat line
                     "transform_card",  # Phase AH (gaps #35/#38): a run-permanent self-rewrite is a build-around, not a stat line
                     "graft_card",  # Phase AI (gap #7): a choose-a-card run-permanent transform is a build-around, not a stat line
                     "scry",  # Phase AA (gap #17 R-2): a draw-filter / on_discard fuel is a build-around, not a flat stat line
                     "cost_shift",  # Phase AO (v45): a typed energy discount is a tempo utility, not a flat stat line
                     "retrieve_card",  # Phase AP (v46): pile recursion (Headbutt / Exhume) is a build-around, not a stat line
                     "spend_forge",  # Phase AX (v53, gap #44): cashing out the Forge ramp is a build-around, not a stat line
                     "spread_debuffs"}  # Phase AX (v53, gaps #45-#47): contagion is a build-around payoff, not a stat line
# F5: the live state scalars an effect's amount may scale to (mirrors ForgedCards.SupportedScales). "x" stays
# the X-cost scalar; the rest are hand/energy state reads. Only "cards_retained" is allowed inside a trigger.
# Phase M: "forged" is the ADDITIVE exception (printed amount + the Forge counter) and is damage/block-only.
_SUPPORTED_SCALES = {"x", "cards_in_hand", "cards_retained", "unspent_energy_last_turn", "forged",
                     # Phase P: damage_dealt_unblocked = heal-only lifesteal (heal the unblocked damage this card
                     # dealt); target_debuff_count = damage-only (deal damage = debuffs on the struck target).
                     "damage_dealt_unblocked", "target_debuff_count",
                     # Phase AE (gap #25): tag_cards_owned = ADDITIVE (printed amount + count of cards with a tag),
                     # damage/block-only, requires a sibling `tag`.
                     "tag_cards_owned",
                     # Phase AM (v43): five more live player reads (replace-semantics). `energy` is damage/block/draw
                     # but COST-0 ONLY (the cost is paid before the card resolves — checked at the card level, below);
                     # the other four are damage/block-only (_DAMAGE_BLOCK_ONLY_SCALES). Mirrors ForgedCards.
                     "block", "hp_lost_this_turn", "draw_pile_count", "energy", "plays_this_combat"}
_DAMAGE_BLOCK_ONLY_SCALES = {"block", "hp_lost_this_turn", "draw_pile_count", "plays_this_combat"}
# Phase AM (v43): the `when` kinds that read the CHOSEN target — single-enemy cards only, never in a trigger
# (mirrors Conditions.TargetKinds). target_has_status predates this set and keeps its looser legacy rule.
_TARGET_CONDITIONS = {"target_hp_below_half", "target_has_block"}
# Phase AL (v42): the scalars a trigger payload may use — PLAYER-level reads only (mirror ForgedCards.TriggerScales);
# and the payload ops whose amount a scale may replace / add to (mirror ForgedCards.TriggerScalableOps). `forged`
# keeps its ADDITIVE damage/block-only shape; a TARGETED payload may be scaled only when it is `damage`.
_TRIGGER_SCALES = {"cards_retained", "cards_in_hand", "unspent_energy_last_turn", "forged"}
_TRIGGER_SCALABLE_OPS = {"damage", "block", "draw", "gain_energy", "heal", "lose_hp", "gain_orb_slot", "apply_status"}
# Self-buff statuses (mirror C# EffectRunner.SelfBuffStatuses) — a buff_summon's status must be one of these
# (it lands on the minion, like Strength). Kept in lockstep with the mod's ForgedCards.buff_summon validation.
_SELF_BUFF_STATUSES = {"strength", "dexterity", "thorns", "regen", "metallicize", "artifact", "buffer",
                       "intangible", "ritual", "blur", "temp_strength", "temp_dexterity", "barricade", "focus",
                       "temp_thorns", "temp_focus"}  # Phase AN (v44): one-turn Thorns / Focus
# H4 (gaps #13/#14): the reactive triggers that can fire many times a turn → eligible for 'once_per_turn'
# (mirror ForgedCards.MultiFireTriggers); and the debuffs a TARGETED trigger apply_status may apply.
_MULTI_FIRE_TRIGGERS = {"on_hp_lost", "on_exhaust", "on_card_played", "on_card_drawn", "on_damage_dealt",
                        "on_block_gained", "attacked",
                        "on_discard",  # Phase R (gap #17): a card can be discarded, redrawn, discarded again
                        "on_blade_played"}  # Phase AJ (v40): the blade can be played several times a turn (C# parity)
_ENEMY_DEBUFF_STATUSES = {"vulnerable", "weak", "frail", "poison"}
# Phase AK (v41): the POWER-HOSTED reactive kinds eligible for 'once_per_combat' (mirror ForgedCards.OncePerCombatTriggers)
# — every multi-fire kind except the card-latent on_discard (no power instance to carry the fired flag).
_ONCE_PER_COMBAT_TRIGGERS = _MULTI_FIRE_TRIGGERS - {"on_discard"}
# Phase Q (gap #16): the combat piles add_card may target + the copies-per-play cap. Mirrors ForgedCards.AddCardPiles
# / AddCardMaxAmount. card_id existence is the ref-integrity check (_ref_errors); these are the shape rules.
_ADD_CARD_PILES = {"hand", "discard", "draw"}
_ADD_CARD_MAX = 3
# Phase AP (v46): the retrieve_card source piles (discard / exhaust — never draw), the pick modes shared by
# discard / retrieve_card (random / choose), the base-game Status cards add_status_card may generate, and the per-play
# caps. Mirrors ForgedCards.RetrievePiles / PickModes / StatusCards / RetrieveMaxAmount / StatusCardMaxAmount + the
# schema clauses. Both new ops are card-only (the triggerEffect op enum omits them); a payload discard stays random.
_RETRIEVE_PILES = {"discard", "exhaust"}
_PICK_MODES = {"random", "choose"}
_STATUS_CARDS = {"dazed", "wound", "burn"}
_RETRIEVE_MAX = 2
_STATUS_CARD_MAX = 3
# Phase AP (v46): the relative sting of each Status card (a negative price — the drawback an over-statted card pays):
# a Burn deals 2 when it sits in hand at end of turn; a Wound is a dead draw; a Dazed is a dead draw that at least
# leaves the hand on its own (Ethereal).
_STATUS_CARD_STING = {"burn": 2.5, "wound": 2.0, "dazed": 1.5}
# Phase S (gap #1): the poles balance_step may move the gauge toward + the per-step cap. Mirrors ForgedCards
# .BalancePoles / BalanceStepMaxAmount. The both-poles / gated-payoff PAIRING rule is a class-level check
# (character_validator.balance_pairing_warnings) — a lone balance card is a warning there, not a per-card reject.
_BALANCE_POLES = {"light", "dark"}
_BALANCE_STEP_MAX = 5
# Phase AC (gap #2): summon heal/shield per-op caps (mirror ForgedCards.HealSummonMaxAmount / ShieldSummonMaxAmount).
_HEAL_SUMMON_MAX = 9
_SHIELD_SUMMON_MAX = 12
# Phase AN (v44): the gain_max_hp cap (mirrors ForgedCards.GainMaxHpMaxAmount + the schema clause). A run-permanent
# stat (Feed is +3/+4), so the band is tight; card-only (the triggerEffect op enum omits it).
_GAIN_MAX_HP_MAX = 5
# Phase AO (v45): the cost_shift shape (mirrors ForgedCards.CostShiftKinds / CostShiftScopes / CostShiftMaxAmount /
# CostShiftMaxCount + the schema clauses). Card-only (the triggerEffect op enum omits it); scope:"combat" is amount 1
# and RARE-ONLY here (the C# has no rarity at effect level), ≤1 such card per class (character_validator).
_COST_SHIFT_KINDS = {"attack", "skill", "power", "all"}
_COST_SHIFT_SCOPES = {"this_turn", "combat"}
_COST_SHIFT_MAX = 2
_COST_SHIFT_MAX_COUNT = 3
# Phase V/X (gap #18): the hand-scopes upgrade_card may use. Mirrors ForgedCards.UpgradeScopes. `random` is legal on
# cards AND in trigger payloads; `all` (whole hand) and `choose` (Phase X — the player picks one card) are card-only
# (a repeating whole-hand upgrade / a repeating pick-UI every turn is degenerate — rejected in a trigger by both this
# validator and ForgedCards.ValidateTrigger).
_UPGRADE_SCOPES = {"random", "all", "choose"}
# Phase AX (v53, gap #44): the spend_forge cap - a ramp cash-out is a real commitment but never a one-line
# counter wipe. Lockstep with ForgedCards.SpendForgeMaxAmount + the schema clause.
_SPEND_FORGE_MAX = 10
# Phase AX (v53): the card energy-cost ceiling, raised 3 -> 4. Cost 4 is the HEAVYWEIGHT slot: RARE-ONLY (hard,
# both sides) and expected to carry a headline effect (a warning, generation-side only). Lockstep with
# ForgedCards.MaxCardCost + card.schema.json.
_MAX_COST = 4
# Phase AX (v53): the keyword flag-ops an UPGRADE may ADD (exactly one, appended to the end of the upgrade effect
# list). Removal is exhaust-only. `purge` is deliberately absent - it is not a CardKeyword.
_KEYWORD_OPS = {"exhaust", "retain", "innate", "ethereal"}
# Phase AX (v53): how many times one card may declare the SAME apply_status. The second must be `when`-gated and
# takes a suffixed var ("Weak2"); a third is always a reject. Lockstep with ForgedCards.MaxSameStatusPerCard.
_MAX_SAME_STATUS = 2


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)      # hard rejects
    warnings: list[str] = field(default_factory=list)    # balance flags (don't reject)
    score: float = 0.0


# --- vocab-demand mining (2026-08-16) ---------------------------------------------------------------
# When the card model emits a token the vocabulary doesn't have — an op, a `when` kind, a scale, a
# status — the validation error NAMES the token it reached for. That is organic demand for a mechanic
# that doesn't exist yet, the best possible source of vocab-expansion ideas, and it used to be thrown
# away with the error list. These patterns pull (kind, token) pairs back out of the error strings;
# SHAPE mistakes (bad amounts, illegal combinations, balance) are deliberately not matched — a model
# misusing an existing token is noise, a model asking for a missing one is signal.
_MISS_SCHEMA_ENUM = re.compile(r"schema \[(?P<path>[^\]]*)\]: '(?P<tok>[^']+)' is not one of ")
_MISS_SCHEMA_FIELD = {  # schema-path suffix -> the vocab surface the model reached for
    "op": "op", "kind": "condition", "scale": "scale", "status": "status", "trigger": "trigger"}
_MISS_TEXT = [(re.compile(r"unsupported scale '(?P<tok>[^']+)'"), "scale"),
              (re.compile(r"unknown status '(?P<tok>[^']+)'"), "status")]
_MISS_TOKEN_OK = re.compile(r"^[a-z][a-z0-9_]{1,31}$")  # slug-shaped reaches only; garbage isn't demand


def vocab_misses(errors: list[str]) -> list[tuple[str, str]]:
    """Extract (kind, token) vocabulary reaches from validation-error strings, deduped in order."""
    out: list[tuple[str, str]] = []
    for err in errors or []:
        if not isinstance(err, str):
            continue
        m = _MISS_SCHEMA_ENUM.search(err)
        if m:
            field_name = m.group("path").rstrip("/").rsplit("/", 1)[-1]
            kind = _MISS_SCHEMA_FIELD.get(field_name)
            if kind and _MISS_TOKEN_OK.match(m.group("tok")) and (kind, m.group("tok")) not in out:
                out.append((kind, m.group("tok")))
            continue
        for pat, kind in _MISS_TEXT:
            m = pat.search(err)
            if m and _MISS_TOKEN_OK.match(m.group("tok")) and (kind, m.group("tok")) not in out:
                out.append((kind, m.group("tok")))
    return out


class CardValidator:
    """Loads the schema + known-id sets once, then validates single cards repeatedly."""

    def __init__(self, extra_orbs: set[str] | None = None, extra_statuses: set[str] | None = None,
                 extra_summons: set[str] | None = None) -> None:
        paths.assert_project_present()
        schema = json.loads(paths.CARD_SCHEMA.read_text())
        self._schema_validator = Draft202012Validator(schema)
        # Detect the constrained STS2-mod contract (vs the prototype schema) so the mod-engine structural
        # checks below run only where they apply — the prototype engine has none of those runtime limits.
        _ops = schema.get("$defs", {}).get("effect", {}).get("properties", {}).get("op", {}).get("enum", [])
        self._mod_contract = "channel_orb" in _ops
        # Valid channel_orb orb names. The schema no longer pins these (it allows any custom name so a forged
        # ORB class can channel its own orbs by pool name, Phase I); membership is checked here instead.
        # Base orbs + 'random' are always valid; a class generator injects its custom orb names via extra_orbs.
        # (Single-card / shared generation passes none -> strict base set, matching the C# shared-card path.)
        self._allowed_orbs = {"lightning", "frost", "dark", "random"} | (extra_orbs or set())
        # Phase J: the custom (forged) status names this class declared in its status_pool — apply_status_custom
        # may reference ONLY these (lowercased). Shared / single-card generation passes none, so apply_status_custom
        # has no valid target there and is rejected (it's a class-only op, like custom-orb channels).
        self._allowed_custom_statuses = {s.strip().lower() for s in (extra_statuses or set())}
        # Phase K: the forged minion names this class declared in its summon_pool — the `summon` op may reference
        # ONLY these (lowercased). Shared / single-card generation passes none, so summon has no valid target
        # there and is rejected (it's a class-only op, like custom-orb channels / apply_status_custom).
        self._allowed_custom_summons = {s.strip().lower() for s in (extra_summons or set())}
        self.known_statuses = self._ids_in(paths.STATUSES_DIR)
        # authored pool + already-quarantined generated cards both count as resolvable refs
        self.known_cards = self._ids_in(paths.CARDS_DIR) | self._ids_in(paths.GENERATED_DIR)
        # status kind/decay (for the permanence tripwire) + full authored corpus (for dominance)
        self.status_meta = self._status_meta()
        self.corpus = self._load_cards(paths.CARDS_DIR)
        # skeleton index over the corpus, for the functional-reprint gate
        self.corpus_ids = {c["id"] for c in self.corpus}
        self._reprint_index: dict[tuple, list[tuple[str, list[float]]]] = {}
        for c in self.corpus:
            k, n = self._reprint_key_nums(c)
            self._reprint_index.setdefault(k, []).append((c["id"], n))

    # -- public ------------------------------------------------------------
    def validate(self, card: dict) -> ValidationResult:
        errors = self._schema_errors(card)
        # ref-integrity only makes sense once the shape is roughly an object with effects
        if isinstance(card, dict):
            errors += self._ref_errors(card)
            if self._mod_contract:
                errors += self._engine_structural_errors(card)
        if errors:
            return ValidationResult(ok=False, errors=errors)
        rep_errors, rep_warnings = self.reprint_findings(card)
        if rep_errors:
            return ValidationResult(ok=False, errors=rep_errors)
        score = self.score_card(card)
        warnings = self.balance_warnings(card, score)
        warnings += self.rarity_floor_warnings(card, score)
        warnings += self.dominance_warnings(card)
        warnings += self.permanence_warnings(card)
        warnings += self.loop_warnings(card)
        warnings += rep_warnings
        return ValidationResult(ok=True, warnings=warnings, score=score)

    # -- 1. schema ---------------------------------------------------------
    def _schema_errors(self, card) -> list[str]:
        out: list[str] = []
        for e in sorted(self._schema_validator.iter_errors(card), key=lambda e: list(e.path)):
            loc = "/".join(str(p) for p in e.path) or "(root)"
            out.append(f"schema [{loc}]: {e.message}")
        return out

    # -- 2. reference integrity -------------------------------------------
    def _ref_errors(self, card: dict) -> list[str]:
        out: list[str] = []
        # a card may reference itself (Anger copies itself into the discard)
        self_id = card.get("id")
        cards_ok = self.known_cards | ({self_id} if isinstance(self_id, str) else set())

        def walk(effects, path: str) -> None:
            if not isinstance(effects, list):
                return
            for i, eff in enumerate(effects):
                if not isinstance(eff, dict):
                    continue
                p = f"{path}[{i}]"
                op = eff.get("op")
                if op == "apply_status":
                    s = eff.get("status")
                    if isinstance(s, str) and s not in self.known_statuses:
                        out.append(f"{p}: unknown status '{s}' (not in data/statuses/)")
                elif op == "add_card":
                    c = eff.get("card_id")
                    if isinstance(c, str) and c not in cards_ok:
                        out.append(f"{p}: add_card references unknown card '{c}'")
                elif op == "transform_card":
                    # Phase AH (gaps #35/#38): the target must be a same-class card that EXISTS, and must NOT be
                    # THIS card (a card becoming itself is a no-op). Existence uses known_cards (not cards_ok — self
                    # is explicitly rejected here). The chain-vs-mode-swap rule is set-level (transform_warnings).
                    c = eff.get("card_id")
                    if isinstance(c, str):
                        if c == self_id:
                            out.append(f"{p}: transform_card can't target itself ('{c}') — a card becoming itself is a no-op")
                        elif c not in self.known_cards:
                            out.append(f"{p}: transform_card references unknown card '{c}'")
                elif op == "graft_card":
                    # Phase AI (gap #7): the graft TARGET (the card the PICKED card becomes) must be a same-class
                    # card that EXISTS. Unlike transform_card there's no self-target check here — graft transforms a
                    # PICKED hand card (a runtime pick, unknown at generation), not the carrier; the picked==target
                    # self-into-itself case is a runtime no-op (ResolveTransformTarget). The chain/mode-swap +
                    # ≤3-per-class rules are set-level (transform_warnings, shared with transform_card).
                    c = eff.get("card_id")
                    if isinstance(c, str) and c not in cards_ok:
                        out.append(f"{p}: graft_card references unknown card '{c}'")
                elif not self._mod_contract and op in ("multi", "fuse"):   # LEGACY prototype composites
                    walk(eff.get("effects"), f"{p}.effects")
                elif not self._mod_contract and op == "conditional":       # LEGACY prototype composite
                    walk(eff.get("then"), f"{p}.then")
                    walk(eff.get("else"), f"{p}.else")

        walk(card.get("effects"), "effects")
        if isinstance(card.get("upgrade"), dict):
            walk(card["upgrade"].get("effects"), "upgrade.effects")
        return out

    # -- 2b. mod-engine structural integrity (mirror of ForgedCards.Validate) -----------
    # Constraints of the STS2-mod runtime that the JSON schema cannot express: the game builds ONE
    # DynamicVarSet per card and THROWS on a duplicate var key (the card-22 crash), allows one Hits var
    # and one calculated (scale:x) var, and couples X-cost to scale:x. Hard ERRORS (gated to the mod
    # contract) so the website's repair loop fixes them instead of emitting a card the in-game importer
    # rejects. The in-game ForgedCards.Validate is the authoritative gate; this keeps the two in lockstep.
    @staticmethod
    def _status_occurrence(effects: list, i: int) -> int:
        """Phase AX (v53): how many EARLIER effects apply the SAME status as effects[i] (0 = the first / not an
        apply_status). Occurrence 1 is the `when`-gated second copy, which takes the suffixed var name and applies
        with a literal amount at runtime. Mirrors ForgedCards.StatusOccurrence."""
        if effects[i].get("op") != "apply_status":
            return 0
        st = effects[i].get("status")
        return sum(1 for j in range(i)
                   if effects[j].get("op") == "apply_status" and effects[j].get("status") == st)

    @classmethod
    def _var_key_at(cls, effects: list, i: int):
        """Phase AX (v53): the var key of the i-th effect. apply_status is occurrence-numbered, so a card's SECOND
        (gated) Weak declares 'status:weak:2' instead of colliding with the first. Mirrors ForgedCards.VarKey."""
        eff = effects[i]
        if eff.get("op") != "apply_status":
            return cls._var_key(eff)
        occ = cls._status_occurrence(effects, i)
        return "status:" + str(eff.get("status")) + (f":{occ + 1}" if occ else "")

    @staticmethod
    def _var_key(eff: dict):
        """The DynamicVar key an effect declares in DataCard (None = none). Mirrors ForgedCards.VarKey:
        damage/block collapse to one key each; a scale:x draw declares no var."""
        op = eff.get("op")
        if op == "damage":
            return "Damage"
        if op == "block":
            return "Block"
        if op == "draw":
            return None if str(eff.get("scale", "")).strip() else "Cards"  # any scaled draw declares no var
        if op == "gain_energy":
            return "Energy"
        if op == "heal":
            return "Heal"
        if op == "lose_hp":
            return "Loss"
        if op == "gain_max_hp":  # Phase AN (v44): the MaxHpVar (mirrors ForgedCards.VarKey)
            return "MaxHp"
        if op == "discard":  # Phase R (gap #17): the random-discard count var (mirrors ForgedCards.VarKey)
            return "Discard"
        if op == "scry":  # Phase AA (gap #17 R-2): the top-of-draw look count var (mirrors ForgedCards.VarKey)
            return "Scry"
        if op == "apply_status":
            return "status:" + str(eff.get("status"))
        return None  # channel_orb / evoke / gain_orb_slot / exhaust / innate / retain / ethereal: no var

    def _engine_structural_errors(self, card: dict) -> list[str]:
        effects = [e for e in (card.get("effects") or []) if isinstance(e, dict)]
        out: list[str] = []
        # channel_orb orb-name membership (the schema no longer pins it): base orbs + 'random' + any custom
        # orb names this class declared. Checked across base AND upgrade effects.
        # Guard a malformed 'upgrade' (a weak LLM sometimes emits it as a list/str): report it as a
        # structural error so the repair loop can fix it, instead of throwing AttributeError and crashing
        # the whole forge on '.get' of a non-dict.
        _up = card.get("upgrade")
        if _up is not None and not isinstance(_up, dict):
            out.append(f"'upgrade' must be an object with an 'effects' list, not a {type(_up).__name__}.")
            _up = None
        up_effects = [e for e in ((_up or {}).get("effects") or []) if isinstance(e, dict)]
        # Phase AG (gap #39): an upgrade may LOWER the card's energy cost (absolute). Upgrades cheapen, never tax:
        # cost 0..4 (Phase AX), <= the base cost, and not on an X-cost card. Mirrors ForgedCards.TryParseCardJson.
        if isinstance(_up, dict) and _up.get("cost") is not None:
            ucost = _up.get("cost")
            base_cost = card.get("cost", 0)
            base_is_x = isinstance(base_cost, str) and base_cost.strip().upper() == "X"
            if base_is_x:
                out.append("upgrade 'cost' is not allowed on an X-cost card.")
            elif not (isinstance(ucost, int) and not isinstance(ucost, bool) and 0 <= ucost <= _MAX_COST):
                out.append(f"upgrade 'cost' must be an integer 0..{_MAX_COST}; got {ucost!r}.")
            elif isinstance(base_cost, int) and ucost > base_cost:
                out.append(f"upgrade 'cost' ({ucost}) may not exceed the base cost ({base_cost}) — upgrades cheapen, never tax.")
        # Phase AJ (v40): a random_enemy card has no chosen target (each hit / status effect rolls its own enemy), so
        # the target-reading condition and scale are rejected on it. Mirrors ForgedCards.Validate.
        is_random_target = card.get("target") == "random_enemy"
        for e in effects + up_effects:
            if is_random_target:
                if isinstance(e.get("when"), dict) and e["when"].get("kind") == "target_has_status":
                    out.append("'when:target_has_status' can't be used on a random_enemy card (no chosen target to read — each effect rolls its own random enemy).")
                if str(e.get("scale", "")).strip().lower() == "target_debuff_count":
                    out.append("'scale:target_debuff_count' can't be used on a random_enemy card (no chosen target to read — each effect rolls its own random enemy).")
            if e.get("op") == "channel_orb":
                orb = e.get("orb")
                if orb is not None and orb not in self._allowed_orbs:
                    out.append(f"channel_orb 'orb':'{orb}' is not a valid orb here "
                               f"(base lightning/frost/dark, 'random', or a custom orb in this class's pool).")
            # Phase J: apply_status_custom must name a status in THIS class's status_pool (class-only op).
            if e.get("op") == "apply_status_custom":
                nm = str(e.get("status_name", "")).strip().lower()
                if not nm:
                    out.append("apply_status_custom needs a 'status_name' (a custom status in this class's status_pool).")
                elif nm not in self._allowed_custom_statuses:
                    out.append(f"apply_status_custom 'status_name':'{e.get('status_name')}' is not a status in "
                               f"this class's status_pool (apply_status_custom is class-only).")
            # Phase K: summon must name a minion in THIS class's summon_pool (class-only op). v15 true-Osty: the
            # summon op's amount is the HP to grant/grow (Osty keyword), NOT a minion count — no board cap.
            if e.get("op") == "summon":
                nm = str(e.get("summon_name", "")).strip().lower()
                if not nm:
                    out.append("summon needs a 'summon_name' (the minion in this class's summon_pool).")
                elif nm not in self._allowed_custom_summons:
                    out.append(f"summon 'summon_name':'{e.get('summon_name')}' is not a minion in "
                               f"this class's summon_pool (summon is class-only).")
            # Phase K (v15 true-Osty): summon_attack / buff_summon strike-through / buff the class's one summon —
            # class-only (need a summon_pool). buff_summon's status (if given) must be a self-buff (lands on the minion).
            if e.get("op") in ("summon_attack", "buff_summon"):
                if not self._allowed_custom_summons:
                    out.append(f"{e.get('op')} is only valid on a summon class (one with a summon_pool).")
                if e.get("op") == "buff_summon":
                    st = e.get("status")
                    if st is not None and str(st).strip().lower() not in _SELF_BUFF_STATUSES:
                        out.append(f"buff_summon 'status':'{st}' must be a self-buff (e.g. strength); it lands on the minion.")
            # Phase AC (gap #2): heal_summon / shield_summon heal / Block the class's one living summon — class-only
            # (need a summon_pool), like summon_attack/buff_summon; bounded caps. Mirrors ForgedCards.Validate.
            # Phase AX (v53, gap #44): spend_forge CONSUMES the per-combat Forge counter as this card's price
            # (the cash-out half of the ramp `forge` builds). The band is schema+engine capped; forge-class is
            # class-level (character_validator.forge_pairing_warnings), card-only is the schema's triggerEffect
            # op enum. Mirrors ForgedCards.Validate.
            if e.get("op") == "spend_forge":
                sfa = e.get("amount")
                if not (isinstance(sfa, int) and not isinstance(sfa, bool) and 1 <= sfa <= _SPEND_FORGE_MAX):
                    out.append(f"spend_forge 'amount' (the Forge consumed) must be 1..{_SPEND_FORGE_MAX}; got {sfa!r}.")
            # Phase AX (v53, gaps #45-#47): spread_debuffs is a flag-op - it copies the STRUCK target's debuffs
            # onto every OTHER living enemy, so it reads the chosen target (single-enemy cards only, like the AM
            # target conditions) and carries no amount/status/scale of its own. Mirrors ForgedCards.Validate.
            if e.get("op") == "spread_debuffs":
                if e.get("amount") is not None:
                    out.append("spread_debuffs carries no amount (it copies the debuffs already on the target).")
                if e.get("status") is not None:
                    out.append("'status' does not apply to spread_debuffs (it copies whatever debuffs the target has).")
                if str(e.get("scale", "")).strip():
                    out.append("'scale' does not apply to spread_debuffs (it copies the target's live debuff stacks).")
                if str(card.get("target", "")).strip().lower() != "enemy":
                    out.append('spread_debuffs needs a single-enemy card (target "enemy") -- it copies the CHOSEN '
                               "target's debuffs to the others.")
            # Phase AV (v52): sacrifice_summon consumes the class's living minion (its on_death rattle fires) -
            # class-only like the rest of the summon family, and a flag-op (no amount/status/hits).
            if e.get("op") == "sacrifice_summon":
                if not self._allowed_custom_summons:
                    out.append("sacrifice_summon is only valid on a summon class (one with a summon_pool).")
                if int(e.get("amount", 0) or 0) != 0:
                    out.append("sacrifice_summon carries no amount (it's a flag-op that consumes your summon).")
                if e.get("status") is not None:
                    out.append("'status' does not apply to sacrifice_summon.")
            if e.get("op") in ("heal_summon", "shield_summon"):
                if not self._allowed_custom_summons:
                    out.append(f"{e.get('op')} is only valid on a summon class (one with a summon_pool).")
                amt = e.get("amount")
                cap = _HEAL_SUMMON_MAX if e.get("op") == "heal_summon" else _SHIELD_SUMMON_MAX
                if isinstance(amt, int) and not isinstance(amt, bool) and amt > cap:
                    out.append(f"{e.get('op')} 'amount' may be at most {cap}; got {amt}.")
            # Phase Q (gap #16): add_card shape rules (card_id existence is checked in _ref_errors). Mirrors
            # ForgedCards.Validate — card_id non-empty, a valid pile, the amount cap. Class-only is enforced in the
            # mod (allowCustomOrbs) + naturally by ref-integrity (card_id must resolve to a same-class card).
            if e.get("op") == "add_card":
                if not str(e.get("card_id", "")).strip():
                    out.append("add_card needs a 'card_id' (a card in this class's own set).")
                pile = str(e.get("pile", "")).strip().lower()
                if pile not in _ADD_CARD_PILES:
                    out.append(f"add_card 'pile':'{e.get('pile')}' must be one of {'/'.join(sorted(_ADD_CARD_PILES))}.")
                amt = e.get("amount")
                if isinstance(amt, int) and not isinstance(amt, bool) and amt > _ADD_CARD_MAX:
                    out.append(f"add_card 'amount' (copies) may be at most {_ADD_CARD_MAX}; got {amt}.")
            # Phase AH (gaps #35/#38): transform_card also carries a same-class card_id (the card it becomes) — so
            # it shares the card_id allow-list with add_card. Non-empty card_id, no pile, no amount. Existence /
            # same-class / self / basic / no-chain are checked below + set-level (character_validator). Mirrors
            # ForgedCards.Validate.
            elif e.get("op") == "transform_card":
                if not str(e.get("card_id", "")).strip():
                    out.append("transform_card needs a 'card_id' (the same-class card it becomes).")
                if e.get("pile") is not None:
                    out.append(f"'pile' does not apply to transform_card (op '{e.get('op')}').")
                amt = e.get("amount")
                if isinstance(amt, int) and not isinstance(amt, bool) and amt != 0:
                    out.append("transform_card carries no amount (it's a flag-op naming the card to become).")
            # Phase AI (gap #7): graft_card is the CHOOSE form of transform_card — it also carries a same-class
            # card_id (the card the PICKED hand card becomes), so it shares the card_id allow-list. Non-empty
            # card_id, no pile, no amount. Existence is checked in the ref-integrity walk; basic/⊥purge below;
            # chain/≤3 set-level (character_validator). Mirrors ForgedCards.Validate.
            elif e.get("op") == "graft_card":
                if not str(e.get("card_id", "")).strip():
                    out.append("graft_card needs a 'card_id' (the same-class card the picked card becomes).")
                if e.get("pile") is not None:
                    out.append(f"'pile' does not apply to graft_card (op '{e.get('op')}').")
                amt = e.get("amount")
                if isinstance(amt, int) and not isinstance(amt, bool) and amt != 0:
                    out.append("graft_card carries no amount (it's a flag-op naming the card to graft into).")
            # Phase AP (v46): retrieve_card returns pile card(s) to hand — a source pile (discard/exhaust), a pick mode
            # (random/choose), an optional amount 1..2, no card_id. Not class-only. Mirrors ForgedCards.Validate.
            elif e.get("op") == "retrieve_card":
                pile = str(e.get("pile", "")).strip().lower()
                if pile not in _RETRIEVE_PILES:
                    out.append(f"retrieve_card 'pile':'{e.get('pile')}' must be one of {'/'.join(sorted(_RETRIEVE_PILES))}.")
                if str(e.get("cards", "")).strip().lower() not in _PICK_MODES:
                    out.append(f"retrieve_card 'cards':'{e.get('cards')}' must be one of {'/'.join(sorted(_PICK_MODES))}.")
                if e.get("card_id") is not None:
                    out.append("'card_id' does not apply to retrieve_card (it returns whatever is in the pile, not a named card).")
                amt = e.get("amount")
                if isinstance(amt, int) and not isinstance(amt, bool) and amt > _RETRIEVE_MAX:
                    out.append(f"retrieve_card 'amount' (cards returned) may be at most {_RETRIEVE_MAX}; got {amt}.")
            # Phase AP (v46): add_status_card generates base-game Status cards (dazed/wound/burn) into a pile — the
            # self-drawback of an over-statted card. A kind (`card`), a destination pile (the add_card piles), an
            # optional amount 1..3, no card_id. Not class-only. Mirrors ForgedCards.Validate.
            elif e.get("op") == "add_status_card":
                if str(e.get("card", "")).strip().lower() not in _STATUS_CARDS:
                    out.append(f"add_status_card 'card':'{e.get('card')}' must be one of {'/'.join(sorted(_STATUS_CARDS))}.")
                pile = str(e.get("pile", "")).strip().lower()
                if pile not in _ADD_CARD_PILES:
                    out.append(f"add_status_card 'pile':'{e.get('pile')}' must be one of {'/'.join(sorted(_ADD_CARD_PILES))}.")
                if e.get("card_id") is not None:
                    out.append("'card_id' does not apply to add_status_card (use 'card': dazed/wound/burn).")
                amt = e.get("amount")
                if isinstance(amt, int) and not isinstance(amt, bool) and amt > _STATUS_CARD_MAX:
                    out.append(f"add_status_card 'amount' (cards added) may be at most {_STATUS_CARD_MAX}; got {amt}.")
            elif e.get("card_id") is not None or e.get("pile") is not None:
                out.append(f"'card_id'/'pile' only apply to add_card/transform_card/graft_card/retrieve_card/add_status_card (op '{e.get('op')}').")
            if e.get("card") is not None and e.get("op") != "add_status_card":
                out.append(f"'card' only applies to add_status_card (op '{e.get('op')}').")
            # Phase S (gap #1): balance_step shape rules. Mirrors ForgedCards.Validate — a valid pole + the step
            # cap. There is no class pool to gate on (any class CAN move the gauge); the both-poles/gated-payoff
            # pairing is a class-level warning (character_validator), so a lone balance card is legal here.
            if e.get("op") == "balance_step":
                pole = str(e.get("pole", "")).strip().lower()
                if pole not in _BALANCE_POLES:
                    out.append(f"balance_step 'pole':'{e.get('pole')}' must be one of {'/'.join(sorted(_BALANCE_POLES))}.")
                amt = e.get("amount")
                if isinstance(amt, int) and not isinstance(amt, bool) and amt > _BALANCE_STEP_MAX:
                    out.append(f"balance_step 'amount' (step size) may be at most {_BALANCE_STEP_MAX}; got {amt}.")
            elif e.get("pole") is not None:
                out.append(f"'pole' only applies to balance_step (op '{e.get('op')}').")
            # Phase V (gap #18): upgrade_card needs a valid hand-scope (random/all). Not class-only (works on
            # whatever's in hand). Combat-scoped. Mirrors ForgedCards.Validate.
            if e.get("op") == "upgrade_card":
                scope = str(e.get("cards", "")).strip().lower()
                if scope not in _UPGRADE_SCOPES:
                    out.append(f"upgrade_card 'cards':'{e.get('cards')}' must be one of {'/'.join(sorted(_UPGRADE_SCOPES))}.")
            # Phase AP (v46): discard's optional pick mode — random (the default) or choose (card-only; the trigger loop
            # below rejects it). retrieve_card's pick mode is validated with its shape above. Mirrors ForgedCards.Validate.
            elif e.get("op") == "discard":
                if e.get("cards") is not None and str(e.get("cards", "")).strip().lower() not in _PICK_MODES:
                    out.append(f"discard 'cards':'{e.get('cards')}' must be one of {'/'.join(sorted(_PICK_MODES))}.")
            elif e.get("cards") is not None and e.get("op") != "retrieve_card":
                out.append(f"'cards' only applies to upgrade_card/discard/retrieve_card (op '{e.get('op')}').")
        for e in effects + up_effects:  # per-effect shape rules apply to the upgrade too (lockstep w/ the
            op = e.get("op")            # mod's `effects.Concat(upgrade)` in ForgedCards.Validate)
            hits = e.get("hits", 1)
            scale = str(e.get("scale", "")).strip().lower()
            # Phase AJ (v40): `hits` is legal on damage AND summon_attack (the engine has run multi-hit summon attacks
            # since Phase K; the vocabulary/schema advertised it, but this guard rejected it — hidden capacity).
            if isinstance(hits, int) and hits > 1 and op not in ("damage", "summon_attack"):
                out.append(f"'hits' only applies to 'damage'/'summon_attack' (op '{op}' had hits {hits}).")
            # Phase AN (v44): `unblockable` is a damage-op flag (card-level; the trigger loop rejects it), and
            # gain_max_hp is banded 1..5. Mirrors ForgedCards.Validate.
            if e.get("unblockable") and op != "damage":
                out.append(f"'unblockable' only applies to damage (op '{op}').")
            if op == "gain_max_hp":
                gm = e.get("amount")
                if isinstance(gm, int) and not isinstance(gm, bool) and gm > _GAIN_MAX_HP_MAX:
                    out.append(f"gain_max_hp 'amount' may be at most {_GAIN_MAX_HP_MAX}; got {gm}.")
            # Phase AO (v45): cost_shift shape rules; its three fields belong to it alone. Mirrors ForgedCards.ValidateCostShift.
            if op == "cost_shift":
                ck = str(e.get("card_type", "")).strip().lower()
                sc = str(e.get("scope", "")).strip().lower()
                ca = e.get("amount")
                cn = e.get("count", 0)
                if ck not in _COST_SHIFT_KINDS:
                    out.append(f"cost_shift needs a 'card_type' (one of {'/'.join(sorted(_COST_SHIFT_KINDS))}); got '{e.get('card_type')}'.")
                if sc not in _COST_SHIFT_SCOPES:
                    out.append(f"cost_shift needs a 'scope' (one of {'/'.join(sorted(_COST_SHIFT_SCOPES))}); got '{e.get('scope')}'.")
                if not (isinstance(ca, int) and not isinstance(ca, bool) and 1 <= ca <= _COST_SHIFT_MAX):
                    out.append(f"cost_shift 'amount' (the discount) must be 1..{_COST_SHIFT_MAX}; got {ca!r}.")
                if not (isinstance(cn, int) and not isinstance(cn, bool) and 0 <= cn <= _COST_SHIFT_MAX_COUNT):
                    out.append(f"cost_shift 'count' (the plays it applies to) must be 1..{_COST_SHIFT_MAX_COUNT}; got {cn!r}.")
                if sc == "combat" and ca != 1:
                    out.append("cost_shift with scope 'combat' must use amount 1 (a whole-combat -2 is degenerate).")
            elif e.get("card_type") is not None or e.get("scope") is not None or e.get("count") is not None:
                out.append(f"'card_type'/'scope'/'count' only apply to cost_shift (op '{op}').")
            if scale:
                if scale not in _SUPPORTED_SCALES:
                    out.append(f"unsupported scale '{scale}' (one of {'/'.join(sorted(_SUPPORTED_SCALES))}).")
                # Phase P (gaps #21/#22): lifesteal is heal-ONLY (replace-semantics; the preceding-damage rule
                # runs per list below); debuff-count is damage-ONLY. Everything else stays damage/block/draw.
                if scale == "damage_dealt_unblocked":
                    if op != "heal":
                        out.append("'scale:damage_dealt_unblocked' only applies to heal (lifesteal — heal the unblocked damage this card dealt).")
                elif scale == "target_debuff_count":
                    if op != "damage":
                        out.append("'scale:target_debuff_count' only applies to damage (deal damage equal to the debuffs on the target).")
                elif scale == "tag_cards_owned":
                    # Phase AE (gap #25): ADDITIVE (printed amount + tagged-card count), damage/block-only, needs a tag.
                    if op not in ("damage", "block"):
                        out.append("'scale:tag_cards_owned' only applies to damage/block (it ADDS the count of your tagged cards to a printed amount).")
                    if not str(e.get("tag", "")).strip():
                        out.append("a 'scale:tag_cards_owned' effect needs a 'tag' (the card tag it counts).")
                    if int(e.get("amount", 0) or 0) < 1:
                        out.append("a 'scale:tag_cards_owned' effect needs amount >= 1 (the count ADDS to the printed amount).")
                elif scale in _DAMAGE_BLOCK_ONLY_SCALES:  # Phase AM (v43)
                    if op not in ("damage", "block"):
                        out.append(f"'scale:{scale}' only applies to damage/block (op '{op}').")
                elif op not in ("damage", "block", "draw"):
                    out.append(f"'scale' only applies to damage/block/draw (op '{op}').")
                # Phase M (gap #36): the additive "forged" scalar adds Forge to a PRINTED damage/block base —
                # never draw, and its amount is REAL (>= 1), unlike the replace-semantics scalars.
                if scale == "forged" and op == "draw":
                    out.append("'scale:forged' only applies to damage/block (Forge adds to a printed damage/block amount).")
                if scale == "forged" and int(e.get("amount", 0) or 0) < 1:
                    out.append("a 'scale:forged' effect needs amount >= 1 (Forge ADDS to the printed amount).")
                if isinstance(hits, int) and hits > 1:
                    out.append("a scaled effect can't also be multi-hit (hits + scale on one effect).")
            # Phase AE (gap #25): a stray `tag` (not on a tag_cards_owned effect) is a mistake — per-effect (a tag
            # on an unscaled effect must also reject). Mirrors ForgedCards.Validate.
            if e.get("tag") is not None and scale != "tag_cards_owned":
                out.append(f"'tag' only applies to a 'scale:tag_cards_owned' effect (op '{op}').")
            # Phase U (gap #23, Rampage): `grow` is an additive per-play damage step — damage-only, NOT a scale.
            grow = e.get("grow", 0)
            if grow:
                if op != "damage":
                    out.append(f"'grow' only applies to damage (op '{op}').")
                if scale:
                    out.append("'grow' and 'scale' can't combine on one effect (grow is an additive per-play step, not a scalar).")
                if not (isinstance(grow, int) and 1 <= grow <= 9):
                    out.append(f"'grow' must be 1..9 (got {grow}).")
                elif grow > int(e.get("amount", 0) or 0):
                    out.append(f"'grow' ({grow}) can't exceed the base damage ({e.get('amount', 0)}) — a card growing faster than its base reads as degenerate.")
            if e.get("orb") is not None and op != "channel_orb":
                out.append(f"'orb' only applies to channel_orb (op '{op}').")
        if sum(1 for e in effects if isinstance(e.get("hits"), int) and e.get("hits", 1) > 1) > 1:
            out.append("at most one multi-hit damage effect per card.")
        # one calculated var per card: at most one scaled damage/block (a scaled draw uses no var → exempt).
        # Phase U (gap #23): a `grow` damage also declares a CalculatedDamage var — counts toward the same budget.
        if sum(1 for e in effects if (str(e.get("scale", "")).strip() and e.get("op") in ("damage", "block"))
               or (e.get("grow", 0) and e.get("op") == "damage")) > 1:
            out.append("at most one scaled/grow damage/block effect per card (the engine allows one calculated value).")
        # Phase P (gap #21): a damage_dealt_unblocked heal must follow a damage op in the SAME list (base and
        # upgrade checked independently — the runtime runs each list top-to-bottom). Mirrors ForgedCards.Validate.
        for lst in (effects, up_effects):
            for i, ef in enumerate(lst):
                if (ef.get("op") == "heal" and str(ef.get("scale", "")).lower() == "damage_dealt_unblocked"
                        and not any(p.get("op") == "damage" for p in lst[:i])):
                    out.append("a 'scale:damage_dealt_unblocked' heal needs a 'damage' op earlier in the same card "
                               "(you heal the damage you dealt).")
        # Phase W (gap #19): self-purge. purge ⊥ exhaust (both mean "the card leaves after this play"; a card can't
        # do both). Never on a BASIC card — a purgeable basic could thin a class's floors (and reads as a trap). The
        # >3-per-class / merchant-floor concerns are class-level (character_validator). Mirrors ForgedCards.Validate.
        has_purge = any(e.get("op") == "purge" for e in effects + up_effects)
        is_basic = str(card.get("rarity", "")).strip().lower() == "basic"
        if has_purge:
            if any(e.get("op") == "exhaust" for e in effects + up_effects):
                out.append("a card can't be both 'purge' and 'exhaust' (purge already removes it from the run — pick one).")
            if is_basic:
                out.append("'purge' is not allowed on a BASIC card (it would thin the class's starting deck / floors).")
        # Phase Z (gap #19 choose): purge_card thins a CHOSEN card (not itself), so no ⊥exhaust rule; but keep
        # deck-EDITING out of the starting deck — a basic shouldn't carry it. Mirrors ForgedCards (SupportedOps only).
        if any(e.get("op") == "purge_card" for e in effects + up_effects) and is_basic:
            out.append("'purge_card' is not allowed on a BASIC card (deck-editing shouldn't be in the starting deck).")
        # Phase AH (gaps #35/#38): transform_card permanently rewrites the run-deck original into another same-class
        # card. Never on a BASIC card (a self-rewriting starter would mutate the starting deck / floors). ⊥ purge
        # (transform BECOMES a card; purge DELETES it — contradictory); at most one per card (a card becomes one
        # thing). Card-only (a payload transform_card is rejected by the schema triggerEffect op enum). The chain /
        # ≤3-per-class rules are set-level (character_validator.transform_warnings). Mirrors ForgedCards.Validate.
        transform_fx = [e for e in effects + up_effects if e.get("op") == "transform_card"]
        if transform_fx:
            if is_basic:
                out.append("'transform_card' is not allowed on a BASIC card (a self-rewriting starter would mutate the starting deck).")
            if any(e.get("op") == "purge" for e in effects + up_effects):
                out.append("a card can't be both 'transform_card' and 'purge' (transform rewrites the run-deck original; purge deletes it — pick one).")
            if sum(1 for e in effects if e.get("op") == "transform_card") > 1:
                out.append("at most one 'transform_card' effect per card (a card can only become one other card).")
        # Phase AI (gap #7): graft_card is the CHOOSE form of transform_card — it transforms a PICKED hand card into
        # a same-class target. Never on a BASIC card (deck-editing shouldn't be in the starting deck); ⊥ purge AND
        # purge_card (graft transforms a card; purge/purge_card DELETE one — contradictory transform-vs-delete); at
        # most one per card. Card-only (a payload graft_card is rejected by the schema triggerEffect op enum). The
        # chain / ≤3-per-class (transform-family) rules are set-level (transform_warnings). Mirrors ForgedCards.Validate.
        graft_fx = [e for e in effects + up_effects if e.get("op") == "graft_card"]
        if graft_fx:
            if is_basic:
                out.append("'graft_card' is not allowed on a BASIC card (deck-editing shouldn't be in the starting deck).")
            if any(e.get("op") in ("purge", "purge_card") for e in effects + up_effects):
                out.append("a card can't be both 'graft_card' and 'purge'/'purge_card' (graft transforms a card; purge deletes one — pick one).")
            if (sum(1 for e in effects if e.get("op") == "graft_card") > 1
                    or sum(1 for e in up_effects if e.get("op") == "graft_card") > 1):
                out.append("at most one 'graft_card' effect per card (a graft transforms the picked card into one other card).")
        # Phase AV (v52): sacrifice_summon consumes your minion so its on_death rattle fires. It is the PRICE half
        # of a card, so it may never stand alone (a card whose only effect kills your own pet is a trap); never on a
        # BASIC (the starting deck has no minion to spend); at most one per effect list (you have one front-most
        # minion), base + upgrade counted independently (the replace-on-upgrade pattern). Mirrors ForgedCards.Validate.
        if any(e.get("op") == "sacrifice_summon" for e in effects + up_effects):
            if is_basic:
                out.append("'sacrifice_summon' is not allowed on a BASIC card (the starting deck has no summon to spend).")
            if sum(1 for e in effects if e.get("op") == "sacrifice_summon") > 1 \
                    or sum(1 for e in up_effects if e.get("op") == "sacrifice_summon") > 1:
                out.append("at most one 'sacrifice_summon' effect per card (you have one summon to spend).")
            for lst in (effects, up_effects):
                if lst and all(e.get("op") == "sacrifice_summon" for e in lst):
                    out.append("'sacrifice_summon' can't be a card's only effect (the sacrifice is the price -- the "
                               "rest of the card is the payoff).")
        # Phase AB (gap #20): corruption grants the Corruption power (your Skills cost 0 + Exhaust when played).
        # POWER/SKILL cards only (never an attack — the fantasy is "your Skills are free"); carries no amount; at
        # most one per card. Card-only (a payload corruption is rejected by the schema triggerEffect op enum).
        # The >1-per-class guidance is class-level (character_validator.corruption_warnings). Mirrors ForgedCards.
        corruption_fx = [e for e in effects + up_effects if e.get("op") == "corruption"]
        if corruption_fx:
            if str(card.get("type", "")).strip().lower() == "attack":
                out.append("'corruption' only applies to a power or skill card (not an attack).")
            if any(int(e.get("amount", 0) or 0) != 0 for e in corruption_fx):
                out.append("corruption carries no amount (it's a flag-op that grants the Corruption power).")
            if sum(1 for e in effects if e.get("op") == "corruption") > 1:
                out.append("at most one 'corruption' effect per card (Corruption is a binary power — one grant is enough).")
        # Phase AF (gap #41): blade_empower is a burst on your signature blade — put it on a SKILL or POWER (never an
        # attack — the empowered swing is the blade's, not this card's), amount 2..3 (schema-enforced). Forge-class is
        # class-level (character_validator.blade_empower_warnings). Mirrors ForgedCards.Validate.
        if any(e.get("op") == "blade_empower" for e in effects + up_effects):
            if str(card.get("type", "")).strip().lower() == "attack":
                out.append("'blade_empower' only applies to a skill or power card (not an attack — the empowered swing is the blade's).")
        # Phase AX (v53, gap #44): spend_forge is the PRICE half of a card - never its only effect (the rest of
        # the list is what the Forge buys), never on a BASIC (the starting deck has no ramp to spend), one per
        # effect list (base + upgrade counted independently, like sacrifice_summon / graft_card). Pair it with a
        # `when` forged_ge gate so it never fires on an empty counter. Mirrors ForgedCards.Validate.
        if any(e.get("op") == "spend_forge" for e in effects + up_effects):
            if is_basic:
                out.append("'spend_forge' is not allowed on a BASIC card (the starting deck has no Forge to spend).")
            if sum(1 for e in effects if e.get("op") == "spend_forge") > 1 \
                    or sum(1 for e in up_effects if e.get("op") == "spend_forge") > 1:
                out.append("at most one 'spend_forge' effect per card (one cash-out per play).")
            for lst in (effects, up_effects):
                if lst and all(e.get("op") == "spend_forge" for e in lst):
                    out.append("'spend_forge' can't be a card's only effect (the spend is the price -- the rest of "
                               "the card is the payoff).")
        # Phase AX (v53, gap #44): a `when` forged_ge gate reads the LIVE Forge counter at execution time, and
        # effects resolve top-to-bottom - so a gated payoff placed AFTER the spend_forge that empties the counter
        # tests a number the same card just spent. Order the card "gated payoff first, spend last". Base and
        # upgrade checked independently, like the lifesteal rule. Mirrors ForgedCards.Validate.
        for lst in (effects, up_effects):
            for i, ef in enumerate(lst):
                w = ef.get("when")
                if isinstance(w, dict) and w.get("kind") == "forged_ge" \
                        and any(q.get("op") == "spend_forge" for q in lst[:i]):
                    out.append("a 'when:forged_ge' effect can't come after a 'spend_forge' in the same card (the "
                               "spend empties the counter the gate reads) -- put the gated payoff FIRST and spend last.")
        # Phase AX (v53, gaps #45-#47): spread_debuffs copies the struck target's debuffs to the other enemies -
        # a payoff, so never on a BASIC, and one per effect list (the debuffs only need copying once).
        if any(e.get("op") == "spread_debuffs" for e in effects + up_effects):
            if is_basic:
                out.append("'spread_debuffs' is not allowed on a BASIC card (contagion is an uncommon/rare payoff).")
            if sum(1 for e in effects if e.get("op") == "spread_debuffs") > 1 \
                    or sum(1 for e in up_effects if e.get("op") == "spread_debuffs") > 1:
                out.append("at most one 'spread_debuffs' effect per card (the debuffs only need copying once).")
        # Phase AX (v53): the card energy-cost ceiling is 4, and cost 4 is the HEAVYWEIGHT slot - RARE-only (a
        # 4-cost common/uncommon is a dead draw at every point in a run). Mirrors ForgedCards.TryParseCardJson.
        _cost = card.get("cost")
        if isinstance(_cost, int) and not isinstance(_cost, bool):
            if not 0 <= _cost <= _MAX_COST:
                out.append(f"card 'cost' must be 0..{_MAX_COST} (or \"X\"); got {_cost}.")
            elif _cost == _MAX_COST and str(card.get("rarity", "")).strip().lower() != "rare":
                out.append(f"cost {_MAX_COST} is RARE-only (got '{card.get('rarity')}') -- the heavyweight slot "
                           "needs a headline effect.")
        # Phase AO (v45): cost_shift — at most one per EFFECT LIST (one discount sentence per play; base + upgrade
        # independent, like graft_card); a whole-combat discount is RARE-ONLY (a build-around power, loop discipline:
        # the per-class ≤1 rule is set-level, character_validator.cost_shift_warnings). Never on a BASIC card (a
        # discount in the starting deck warps the floors). Card-only (the schema triggerEffect op enum omits it).
        # Mirrors ForgedCards.Validate (the ≤1 rule) — rarity/basic are generation-side rules.
        cs_fx = [e for e in effects + up_effects if e.get("op") == "cost_shift"]
        if cs_fx:
            if (sum(1 for e in effects if e.get("op") == "cost_shift") > 1
                    or sum(1 for e in up_effects if e.get("op") == "cost_shift") > 1):
                out.append("at most one 'cost_shift' effect per card (one discount per play).")
            if is_basic:
                out.append("'cost_shift' is not allowed on a BASIC card (a discount in the starting deck warps the floors).")
            if (any(str(e.get("scope", "")).strip().lower() == "combat" for e in cs_fx)
                    and str(card.get("rarity", "")).strip().lower() != "rare"):
                out.append("'cost_shift' with scope 'combat' is RARE-ONLY (a whole-combat discount is a build-around power).")
        # Phase AP (v46): add_status_card is a self-drawback (Wounds/Dazed/Burns clog the deck) — never on a BASIC card
        # (a starter that poisons its own deck is a trap in every run), and at most one per effect list (one drawback
        # sentence per play; base + upgrade independent). Card-only (the schema triggerEffect op enum omits it). The
        # ≤2-per-class clog rule is set-level (character_validator.status_card_warnings).
        sc_fx = [e for e in effects + up_effects if e.get("op") == "add_status_card"]
        if sc_fx:
            if is_basic:
                out.append("'add_status_card' is not allowed on a BASIC card (a starter that clogs its own deck is a trap).")
            if (sum(1 for e in effects if e.get("op") == "add_status_card") > 1
                    or sum(1 for e in up_effects if e.get("op") == "add_status_card") > 1):
                out.append("at most one 'add_status_card' effect per card (one drawback per play — raise the amount instead).")
        # Phase AP (v46): retrieve_card — at most one per effect list (two recursions on one play is a loop; raise the
        # amount to 2 instead). Card-only (the schema triggerEffect op enum omits it).
        if (sum(1 for e in effects if e.get("op") == "retrieve_card") > 1
                or sum(1 for e in up_effects if e.get("op") == "retrieve_card") > 1):
            out.append("at most one 'retrieve_card' effect per card (one retrieval per play — raise the amount instead).")
        cost = card.get("cost", 0)
        costs_x = isinstance(cost, str) and cost.strip().upper() == "X"
        any_scale = any(str(e.get("scale", "")).lower() == "x" for e in effects)
        if costs_x and not any_scale:
            out.append("an X-cost card needs a 'scale:x' effect (otherwise X does nothing).")
        if not costs_x and any_scale:
            out.append("'scale:x' requires the card cost to be \"X\".")
        # Phase AM (v43): scale:"energy" is cost-0 ONLY — the game pays the cost BEFORE the card resolves, so on a
        # paid card the in-hand preview (pre-pay) and the dealt amount (post-pay) would differ by the cost. X-cost is
        # excluded too (X spends everything -> always 0). Mirrors ForgedCards.TryParseCardJson.
        if any(str(e.get("scale", "")).strip().lower() == "energy" for e in effects + up_effects) and (costs_x or cost != 0):
            out.append("'scale:energy' requires a cost-0 card (the cost is paid before the card resolves, so a paid card would preview one number and deal another).")
        # Phase AM (v43): the chosen-target conditions need a chosen target — a single-enemy card. AoE (no play
        # target), self and random_enemy cards have none (the gate would silently never open). Mirrors ForgedCards.Validate.
        if str(card.get("target", "")).strip().lower() != "enemy":
            for e in effects + up_effects:
                w = e.get("when")
                if isinstance(w, dict) and w.get("kind") in _TARGET_CONDITIONS:
                    out.append(f"'when:{w.get('kind')}' needs a single-enemy card (target \"enemy\") — it reads the chosen target.")
        # Phase AX (v53): apply_status is the ONE exception to the dup-var guard - a card may declare the same
        # status TWICE when the SECOND one is `when`-gated (the "Weak now, Weak2 if the gate opens" shape). The
        # second takes a SUFFIXED var so the DynamicVarSet still sees unique keys. Mirrors ForgedCards.Validate.
        for i in range(len(effects)):
            if effects[i].get("op") != "apply_status":
                continue
            occ = self._status_occurrence(effects, i)
            if occ >= _MAX_SAME_STATUS:
                out.append(f"a card may declare '{effects[i].get('status')}' at most {_MAX_SAME_STATUS} times "
                           "(one plain + one `when`-gated); a third is never readable on the card.")
                break
            if occ > 0 and not isinstance(effects[i].get("when"), dict):
                out.append(f"a second '{effects[i].get('status')}' effect must be `when`-gated (the first is the "
                           "printed amount; the second is the conditional bonus) -- an ungated pair should just be "
                           "one bigger number.")
                break
        # the dup-var crash guard: a card may declare each canonical value only once
        seen: set[str] = set()
        for k in (self._var_key_at(effects, i) for i in range(len(effects))):
            if k is None:
                continue
            if k in seen:
                out.append(f"two effects both declare '{k}' — a card may use each value only once "
                           "(one damage, one block, one of each status, etc.); combine them or use "
                           "different ops (e.g. a conditional bonus on a DIFFERENT op like block/a debuff).")
                break
            seen.add(k)
        # Phase H3 add_trigger: one per card; the fire-time `when` can't need a target (the schema's
        # triggerEffect $def already enforces the self/orb-only payload shape, so we only cover those gaps).
        if sum(1 for e in effects if e.get("op") == "add_trigger") > 1:
            out.append("at most one add_trigger per card (a card grants a single trigger power).")
        # H4: 'once_per_turn' is only meaningful on an add_trigger op (mirror ForgedCards.Validate's card-level guard).
        for e in effects + up_effects:
            if e.get("once_per_turn") and e.get("op") != "add_trigger":
                out.append(f"'once_per_turn' only applies to add_trigger (op '{e.get('op')}').")
            if e.get("once_per_combat") and e.get("op") != "add_trigger":  # Phase AK (v41)
                out.append(f"'once_per_combat' only applies to add_trigger (op '{e.get('op')}').")
        for e in effects + up_effects:  # an add_trigger in the UPGRADE is validated too (the mod imports both)
            if e.get("op") != "add_trigger":
                continue
            if (isinstance(e.get("when"), dict)
                    and (e["when"].get("kind") in ("target_has_status", "retained_last_turn")
                         or e["when"].get("kind") in _TARGET_CONDITIONS)):  # Phase AM (v43): the chosen-target reads
                out.append(f"a trigger's 'when' can't use {e['when'].get('kind')} (no card/target at end/start of turn).")
            # gap #6 "ripen": a one-shot after N turns — the add_trigger amount is the countdown (>= 1).
            if e.get("trigger") == "ripen" and int(e.get("amount", 0) or 0) < 1:
                out.append("a 'ripen' trigger needs amount >= 1 (the number of turns to wait before it fires once).")
            # H4: 'once_per_turn' only on a MULTI-FIRE reactive trigger (turn_start/turn_end/ripen already fire once/turn).
            if e.get("once_per_turn") and e.get("trigger") not in _MULTI_FIRE_TRIGGERS:
                out.append(f"'once_per_turn' only applies to a multi-fire trigger "
                           f"({'/'.join(sorted(_MULTI_FIRE_TRIGGERS))}); '{e.get('trigger')}' already fires at most once per turn.")
            # Phase AK (v41): 'once_per_combat' only on a POWER-HOSTED reactive trigger; never together with once_per_turn.
            if e.get("once_per_combat") and e.get("trigger") not in _ONCE_PER_COMBAT_TRIGGERS:
                out.append(f"'once_per_combat' only applies to a power-hosted reactive trigger "
                           f"({'/'.join(sorted(_ONCE_PER_COMBAT_TRIGGERS))}); got '{e.get('trigger')}'.")
            if e.get("once_per_combat") and e.get("once_per_turn"):
                out.append("'once_per_combat' already implies once per turn — set one, not both.")
            for t in (e.get("effects") or []):
                if not isinstance(t, dict):
                    continue
                op = t.get("op")
                tgt = t.get("target")
                ts = str(t.get("scale", "")).strip().lower()
                if t.get("once_per_turn") or t.get("once_per_combat"):
                    out.append("'once_per_turn' / 'once_per_combat' go on the add_trigger op, not on a payload effect.")
                if t.get("unblockable"):  # Phase AN (v44): card-level only (mirrors ForgedCards.ValidateTrigger)
                    out.append("'unblockable' is not allowed in a trigger payload (it flags a card-level damage).")
                if tgt is not None:
                    # H4 (gap #14): a TARGETED payload effect hits enemies — damage / enemy-debuff apply_status only,
                    # and never scaled. (target enum + op-vs-target coupling are also enforced by the schema.)
                    # Phase AK (v41): 'attacker' (the creature that just hit you) exists only on the `attacked` trigger.
                    if tgt == "attacker" and e.get("trigger") != "attacked":
                        out.append(f"a trigger effect target 'attacker' is only valid on the 'attacked' trigger "
                                   f"(got '{e.get('trigger')}').")
                    if op == "apply_status" and str(t.get("status", "")).strip().lower() not in _ENEMY_DEBUFF_STATUSES:
                        out.append(f"a targeted trigger apply_status must be an enemy debuff "
                                   f"({'/'.join(sorted(_ENEMY_DEBUFF_STATUSES))}); got '{t.get('status')}'.")
                    # Phase AL (v42): a targeted payload DAMAGE may be scaled ("deal damage equal to the cards in your
                    # hand to ALL enemies"); a targeted debuff / summon strike / custom status stays literal.
                    if ts and op != "damage":
                        out.append(f"only a targeted trigger 'damage' may be scaled (trigger effect '{op}' had scale '{ts}').")
                else:
                    # a SELF payload apply_status must be a self-buff (the schema status enum now also lists debuffs).
                    if op == "apply_status" and str(t.get("status", "")).strip().lower() not in _SELF_BUFF_STATUSES:
                        out.append(f"a self trigger apply_status must be a self-buff (got '{t.get('status')}'); "
                                   "add target:enemy for a debuff.")
                    # Phase AJ (v40): a trigger-payload channel_orb may name any orb in THIS class's pool (base, 'random',
                    # or a custom orb) — the runtime has resolved custom names since the Phase-I parity fix; the schema
                    # enum used to pin base orbs only. Membership is checked here, like the card-level check above.
                    if op == "channel_orb":
                        orb = t.get("orb")
                        if orb is not None and orb not in self._allowed_orbs:
                            out.append(f"trigger channel_orb 'orb':'{orb}' is not a valid orb here "
                                       f"(base lightning/frost/dark, 'random', or a custom orb in this class's pool).")
                # F5 / Phase AL (v42): a payload may scale to a PLAYER-level read (_TRIGGER_SCALES), only on the ops
                # with a scalable amount — never channel_orb/evoke (a count), never forge/balance_step (the fixed
                # income drumbeat; scaling lives on payoff cards), never the summon/custom-status/pile ops.
                # Mirrors ForgedCards.ValidateTrigger.
                thits = t.get("hits", 1)
                if ts:
                    if ts not in _TRIGGER_SCALES:
                        out.append(f"inside a trigger 'scale' must be one of {'/'.join(sorted(_TRIGGER_SCALES))} (got scale '{ts}').")
                    elif op in ("channel_orb", "evoke"):
                        out.append(f"'scale:{ts}' can't be used on a trigger '{op}' (no scalable amount).")
                    elif op in ("forge", "balance_step"):
                        out.append(f"a trigger '{op}' uses a fixed amount (no scale).")
                    elif op not in _TRIGGER_SCALABLE_OPS:
                        out.append(f"'scale:{ts}' can't be used on a trigger '{op}' "
                                   f"(only {'/'.join(sorted(_TRIGGER_SCALABLE_OPS))} carry a scalable amount).")
                    if ts == "forged" and op not in ("damage", "block"):
                        out.append("'scale:forged' inside a trigger only applies to damage/block (Forge ADDS to a printed damage/block amount).")
                    if ts == "forged" and int(t.get("amount", 0) or 0) < 1:
                        out.append("a 'scale:forged' trigger effect needs amount >= 1 (Forge ADDS to the printed amount).")
                    if isinstance(thits, int) and not isinstance(thits, bool) and thits > 1:
                        out.append("a scaled trigger effect can't also be multi-hit (hits + scale on one effect).")
                    # AutoSlay finding (GAPTESTAL1): the turn_end hook fires AFTER the end-of-turn discard, so a
                    # turn_end cards_in_hand always reads 0. Mirrors ForgedCards.ValidateTrigger.
                    if ts == "cards_in_hand" and e.get("trigger") == "turn_end":
                        out.append("'scale:cards_in_hand' can't be used on a turn_end trigger (the hand is already discarded "
                                   "when it fires — use turn_start or a reactive trigger, or scale:cards_retained).")
                # Phase AL (v42): `hits` inside a payload — damage (targeted) / summon_attack only (schema-enforced too).
                if isinstance(thits, int) and not isinstance(thits, bool) and thits > 1 and op not in ("damage", "summon_attack"):
                    out.append(f"'hits' only applies to a trigger 'damage'/'summon_attack' (trigger effect '{op}' had hits {thits}).")
                # Phase AL (v42): the class engines as payloads — class-only, like the card-level ops. A payload
                # apply_status_custom names a status in THIS class's status_pool; buff_summon's status is a self-buff.
                if op == "apply_status_custom":
                    nm = str(t.get("status_name", "")).strip().lower()
                    if not nm:
                        out.append("a trigger apply_status_custom needs a 'status_name' (a custom status in this class's status_pool).")
                    elif nm not in self._allowed_custom_statuses:
                        out.append(f"a trigger apply_status_custom 'status_name':'{t.get('status_name')}' is not a status in "
                                   f"this class's status_pool (apply_status_custom is class-only).")
                elif t.get("status_name") is not None:
                    out.append(f"'status_name' only applies to apply_status_custom (trigger effect '{op}').")
                # Phase AV (v52): sacrifice_summon is CARD-ONLY - a repeating trigger that eats your minion every
                # turn is a self-destroying engine (and the schema's triggerEffect op enum excludes it too).
                if op == "sacrifice_summon":
                    out.append("'sacrifice_summon' is card-only (never inside an add_trigger payload).")
                # Phase AX (v53): both new ops are CARD-ONLY (the schema's triggerEffect op enum omits them too) -
                # a repeating cash-out drains the ramp every turn, and contagion needs a struck target.
                if op in ("spend_forge", "spread_debuffs"):
                    out.append(f"'{op}' is card-only (never inside an add_trigger payload).")
                if op in ("summon_attack", "buff_summon"):
                    if not self._allowed_custom_summons:
                        out.append(f"a trigger {op} is only valid on a summon class (one with a summon_pool).")
                    if op == "buff_summon":
                        bst = t.get("status")
                        if bst is not None and str(bst).strip().lower() not in _SELF_BUFF_STATUSES:
                            out.append(f"a trigger buff_summon 'status':'{bst}' must be a self-buff (e.g. strength); it lands on the minion.")
                # Phase S (gap #1): a trigger-payload balance_step (the Balance engine) needs a valid pole; a stray
                # 'pole' on any other payload op is an error. Mirrors ForgedCards.ValidateTrigger.
                if op == "balance_step":
                    if str(t.get("pole", "")).strip().lower() not in _BALANCE_POLES:
                        out.append(f"a trigger balance_step 'pole':'{t.get('pole')}' must be one of "
                                   f"{'/'.join(sorted(_BALANCE_POLES))}.")
                elif t.get("pole") is not None:
                    out.append(f"'pole' only applies to balance_step (trigger effect '{op}').")
                # Phase V/X (gap #18): a trigger-payload upgrade_card is `random` ONLY (`all` every turn is degenerate;
                # `choose` would spam the pick UI). Mirrors ForgedCards.ValidateTrigger.
                if op == "upgrade_card":
                    if str(t.get("cards", "")).strip().lower() != "random":
                        out.append(f"a trigger upgrade_card must be 'cards':'random' ('all'/'choose' are card-only — "
                                   f"degenerate in a repeating payload); got '{t.get('cards')}'.")
                # Phase AP (v46): a payload discard stays the choiceless form ('cards' absent or random) — a repeating
                # pick UI every turn is the payload-upgrade_card-choose footgun. Mirrors ForgedCards.ValidateTrigger.
                elif op == "discard":
                    if t.get("cards") is not None and str(t.get("cards", "")).strip().lower() != "random":
                        out.append(f"a trigger discard must be random ('cards':'choose' is card-only — a repeating pick "
                                   f"UI); got '{t.get('cards')}'.")
                elif t.get("cards") is not None:
                    out.append(f"'cards' only applies to upgrade_card/discard (trigger effect '{op}').")
                if t.get("card") is not None:
                    out.append(f"'card' only applies to the card-level add_status_card (trigger effect '{op}').")
        up = card.get("upgrade")
        if isinstance(up, dict) and isinstance(up.get("effects"), list):
            out += self._upgrade_shape_errors(effects, [e for e in up["effects"] if isinstance(e, dict)])
        return out

    @staticmethod
    def _upgrade_shape_errors(effects: list, up_effects: list) -> list[str]:
        """Phase AX (v53): the base-vs-upgrade effect-list shape rule. The upgrade list is a POSITIONAL overlay
        (EffectRunner.UpgradeDelta reads it by index), so it normally has to match the base list's length exactly.
        The one relaxation: an upgrade may CHANGE ONE KEYWORD -- append exactly one of exhaust/retain/innate/
        ethereal that the base lacks, or drop a TRAILING exhaust. Both keep indices 0..n-1 aligned. Mirrors
        ForgedCards.ValidateUpgradeShape line for line."""
        out: list[str] = []
        delta = len(up_effects) - len(effects)
        base_kw = {e.get("op") for e in effects if e.get("op") in _KEYWORD_OPS}
        up_kw = {e.get("op") for e in up_effects if e.get("op") in _KEYWORD_OPS}
        if delta == 0:
            if base_kw != up_kw:
                out.append("an equal-length upgrade must carry the same keywords as the base card (to ADD a "
                           "keyword, APPEND it as one extra upgrade effect; to remove one, drop the trailing "
                           "'exhaust').")
        elif delta == 1:
            extra = up_effects[-1].get("op") if up_effects else None
            if extra not in _KEYWORD_OPS:
                out.append("an upgrade with one extra effect may only APPEND a keyword "
                           f"({'/'.join(sorted(_KEYWORD_OPS))}); got '{extra}'.")
            elif extra in base_kw:
                out.append(f"the base card already has '{extra}' -- an upgrade can't add it twice.")
            elif up_kw != base_kw | {extra}:
                out.append("an upgrade may change at most ONE keyword (append one, or drop the trailing 'exhaust').")
        elif delta == -1:
            last = effects[-1].get("op") if effects else None
            if last != "exhaust":
                out.append("an upgrade with one FEWER effect may only drop a TRAILING 'exhaust' "
                           f"(the base card's last effect is '{last}').")
            elif "exhaust" in up_kw:
                out.append("the upgrade still carries 'exhaust' -- drop it from the upgrade list to remove it.")
            elif up_kw != base_kw - {"exhaust"}:
                out.append("an upgrade may change at most ONE keyword (append one, or drop the trailing 'exhaust').")
        else:
            out.append("upgrade effect count must match base effect count (or append exactly one keyword / drop a "
                       "trailing 'exhaust').")
        return out

    # -- 3. balance (port of ContentValidator.gd) -------------------------
    # Effect-level `when` gates discount an effect's score — a payoff that only sometimes fires is worth
    # less than its printed line, and WITHOUT a discount the balance pass auto-tunes every gated bomb down
    # to an always-on power level, killing the gated-payoff fantasy outright (found 2026-08-16). The generic
    # gate matches the prototype `conditional` op's 0.6; `draw_pile_empty` is the archetypal HARD
    # build-around gate (base-game Grand Finale prints ~2.5-3x an ungated card's numbers behind it — the
    # player must draw/thin their whole deck first), so it earns the deepest discount.
    _WHEN_DISCOUNT_DEFAULT = 0.6
    _WHEN_DISCOUNT = {"draw_pile_empty": 0.35}

    def score_card(self, card: dict) -> float:
        return sum(self._score_effect(e) for e in card.get("effects", []))

    def _score_effect(self, eff) -> float:
        if not isinstance(eff, dict):
            return 0.0
        when = eff.get("when")
        if isinstance(when, dict):
            gate = self._WHEN_DISCOUNT.get(str(when.get("kind", "")), self._WHEN_DISCOUNT_DEFAULT)
            ungated = {k: v for k, v in eff.items() if k != "when"}
            return gate * self._score_effect(ungated)
        amt = self._amt(eff.get("amount", 0))
        op = eff.get("op")
        # Phase M (gap #36): a scale:"forged" damage/block is worth its printed base PLUS the compounding
        # Forge it cashes over a combat — a flat premium in the from_state spirit (the real value depends on
        # the set's forge income, unseen at the card level).
        forged = str(eff.get("scale", "")).strip().lower() == "forged"
        if op == "damage":
            # Phase U (gap #23): a `grow` attack is a self-scaling engine — each grow point compounds over the
            # combat (a per-card forge). Priced a touch above forge income (2.5/pt) since it's built into the card.
            grow_premium = self._amt(eff.get("grow", 0)) * 2.5
            # Phase AN (v44): an unblockable hit is worth more than its number (it lands through any Block).
            unblockable_premium = amt * 0.5 if eff.get("unblockable") is True else 0.0
            return amt + (6.0 if forged else 0.0) + grow_premium + unblockable_premium
        if op == "gain_max_hp":
            # Phase AN (v44): a run-permanent stat (+ an immediate heal of the same amount) — priced like a permanent
            # buff so a common can't carry it cheaply (the vocabulary pins it to uncommon/rare).
            return amt * 4.0
        if op == "cost_shift":
            # Phase AO (v45): energy in disguise. A this-turn typed discount is worth ~2/3 of gain_energy per point
            # (only the matching cards cash it; "all" is nearly gain_energy); a use budget scales with the plays it
            # covers; a whole-combat discount is a rare build-around (priced like a per-turn energy power).
            kind = str(eff.get("card_type", "all")).strip().lower()
            scope = str(eff.get("scope", "this_turn")).strip().lower()
            count = self._amt(eff.get("count", 0))
            width = 5.5 if kind == "all" else 4.0
            if scope == "combat":
                return amt * width * 3.0
            if count > 0:
                return amt * width * min(count, 3.0) * 0.6
            return amt * width
        if op == "block":
            return amt * 0.8 + (6.0 if forged else 0.0)
        if op == "draw":
            return amt * 5.0
        if op == "gain_energy":
            return amt * 6.0
        if op == "heal":
            return amt * 0.5
        if op == "lose_hp":
            return -amt * 0.5
        if op == "forge":
            # Phase M (gap #36): forge income — each stack permanently (this combat) adds +1 to every future
            # forged-payoff play. Narrower than Strength (only forged cards cash it) → priced at half.
            return amt * 2.0
        if op == "balance_step":
            # Phase S (gap #1): a gauge step is build-around income (like forge), but two-directional and carrying a
            # downside (the |8| extreme bites), so priced a touch under forge. Non-zero so a balance-income card
            # doesn't read as a blank stat line (keeps it off the rare/merchant floors via _BUILD_AROUND_OPS).
            return amt * 1.5
        if op == "spend_forge":
            # Phase AX (v53, gap #44): spending the ramp is a COST, not a benefit - it empties the counter every
            # scale:"forged" payoff in the set reads from. Priced as a flat negative (like sacrifice_summon /
            # lose_hp) so the payoff half of the card can be generous without tripping the power ceiling; the
            # per-Forge value it cashes lives on the payoff effect, not here.
            return -amt * 1.5
        if op == "spread_debuffs":
            # Phase AX (v53, gaps #45-#47): copy the struck target's debuffs to every OTHER enemy. The value is the
            # debuffs already in play times the enemy count - both unseen at the card level - so price it as a
            # strong build-around utility, above the transform/purge family and below a full AoE debuff line.
            return 6.0
        if op == "blade_empower":
            # Phase AF (gap #41): a transient ×N burst on the signature blade — it can double/triple a fully-ramped
            # Forge in ONE swing, so it is priced ABOVE plain forge income (amt*2): the premium build-around spike it is.
            return amt * 4.0
        if op == "upgrade_card":
            # Phase V/X (gap #18): in-run upgrade as a combat resource. `all` (every upgradable hand card) is a big
            # swing — priced like a strong uncommon+ skill; `choose` (the player targets the best card) is worth more
            # than `random` (one card, luck of the draw). The real value depends on the hand (unseen at the card
            # level), so flat premiums in the build-around spirit.
            scope = str(eff.get("cards", "")).strip().lower()
            return {"all": 12.0, "choose": 7.0}.get(scope, 5.0)
        if op == "purge_card":
            # Phase Z (gap #19 choose): targeted deck-thinning — the player cuts a chosen card from the run deck.
            # A real but modest build-around payoff (value depends on what's cut, unseen here); light-utility price.
            return 4.0
        if op == "transform_card":
            # Phase AH (gaps #35/#38): a run-permanent self-rewrite (the card becomes another same-class card). The
            # payoff is the DIFFERENCE between the two cards (unseen here — the target's stat line lives elsewhere),
            # so price the transform itself as a modest build-around utility, like purge_card.
            return 4.0
        if op == "graft_card":
            # Phase AI (gap #7): choose a card in hand, transform IT into a same-class target (the choose form of
            # transform_card). Payoff is the target-vs-picked difference (unseen here) + the deck-editing agency;
            # price it as a modest build-around utility, like purge_card / transform_card.
            return 4.0
        if op == "apply_status":
            return self._amt(eff.get("amount", 0)) * float(_STATUS_WEIGHT.get(eff.get("status", ""), 2.0))
        if op == "apply_status_custom":
            # Phase J: a forged modifier status (Strength/Dexterity-shaped). Weight per stack like a generic
            # buff; a conservative score (the real value depends on the class's status spec, unseen here).
            return self._amt(eff.get("amount", 0)) * 3.0
        if op == "summon":
            # Phase K (v15 true-Osty): the Summon keyword grants/grows the minion's HP (amount = HP) — value is a
            # meat-shield + the HP pool its summon_attacks ride on. Score HP modestly (it's defense + a damage base).
            return max(1.0, self._amt(eff.get("amount", 0))) * 0.6
        if op == "summon_attack":
            # Phase K (v15 true-Osty): damage dealt THROUGH the summon — scored like damage (it scales further with
            # the minion's Strength, but that's unseen at the card level). hits multiplies the per-hit amount.
            return self._amt(eff.get("amount", 0)) * max(1, int(eff.get("hits", 1) or 1))
        if op == "sacrifice_summon":
            # Phase AV (v52): spending your minion is a COST, not a benefit - it removes the bodyguard and the body
            # every summon_attack rides on. Priced as a flat negative (like lose_hp) so the card's payoff half can be
            # generous (the heuristics put it at >= 10 Block / 12 damage / 2 draws + energy) without tripping the
            # power ceiling. The on_death rattle it cashes is priced on the SUMMON POOL, not here.
            return -4.0
        if op == "buff_summon":
            # Phase K (v15 true-Osty): a self-buff on the minion (default Strength) — weight per stack like a buff.
            return self._amt(eff.get("amount", 0)) * float(_STATUS_WEIGHT.get(eff.get("status", "strength") or "strength", 3.0))
        if op == "scry":
            # Phase AA (gap #17 R-2): a draw-quality filter (look at top N, discard any) — real card-selection
            # value that also fuels on_discard, but weaker than raw draw; ~1.5 per card looked at.
            return self._amt(eff.get("amount", 0)) * 1.5
        if op == "discard":
            # Phase AP (v46): a RANDOM discard is a cost the archetype notes price (0 here, as before); the CHOSEN form is
            # card selection — you pitch the dead card and keep the live one — worth ~1 per card (under scry's 1.5:
            # scry also digs).
            return self._amt(eff.get("amount", 0)) * (1.0 if str(eff.get("cards", "")).strip().lower() == "choose" else 0.0)
        if op == "retrieve_card":
            # Phase AP (v46): pile recursion — a random return is a weaker-than-draw card (3/card; a draw is 5), a chosen
            # return is a tutor (5/card, draw-priced); pulling from the EXHAUST pile is Exhume (+1: the card was spent).
            n = max(1.0, self._amt(eff.get("amount", 1)))
            per = 5.0 if str(eff.get("cards", "")).strip().lower() == "choose" else 3.0
            return n * (per + (1.0 if str(eff.get("pile", "")).strip().lower() == "exhaust" else 0.0))
        if op == "add_status_card":
            # Phase AP (v46): a NEGATIVE price — the drawback an over-statted card pays. Per-kind sting (Burn > Wound >
            # Dazed); a Status card dropped straight into HAND bites now (×1.25), a draw-pile one bites next cycle.
            n = max(1.0, self._amt(eff.get("amount", 1)))
            sting = _STATUS_CARD_STING.get(str(eff.get("card", "")).strip().lower(), 2.0)
            return -n * sting * (1.25 if str(eff.get("pile", "")).strip().lower() == "hand" else 1.0)
        if not self._mod_contract and op in _LEGACY_PROTOTYPE_OPS:
            return self._score_legacy_prototype_effect(op, eff)
        if op == "add_trigger":
            # Phase H3: a per-turn engine. Score one round of the payload (a conservative lower bound — the
            # real value compounds over the fight; _has_composite keeps it off the flat-rare floor).
            return sum(self._score_effect(t) for t in eff.get("effects", []))
        return 0.0

    def _score_legacy_prototype_effect(self, op: str, eff: dict) -> float:
        """LEGACY (prototype contract only): the Godot prototype's composite ops. Never reached under the mod
        contract (Phase AJ-b) — the mod schema rejects these ops, and _score_effect gates on self._mod_contract."""
        if op == "multi":
            sub = sum(self._score_effect(se) for se in eff.get("effects", []))
            return self._amt(eff.get("times", 1)) * sub
        if op == "from_state":
            return 6.0
        if op == "conditional":
            return sum(self._score_effect(se) for se in eff.get("then", [])) * 0.6
        if op == "fuse":
            # Delayed AoE: sum the payload, AoE premium, discounted for the turn delay; "all"
            # also hurts the planter so it's valued a touch lower than enemies-only.
            sub = sum(self._score_effect(se) for se in eff.get("effects", []))
            return sub * (1.1 if eff.get("scope", "all_enemies") == "all" else 1.3)
        return 0.0

    @staticmethod
    def _amt(v) -> float:
        if isinstance(v, bool):  # guard: bool is an int subclass in Python
            return 0.0
        if isinstance(v, (int, float)):
            return float(v)
        return 3.0  # {state} reference: assume ~3 for scoring, as the engine does

    def power_ceiling(self, card: dict) -> float:
        """The score budget for this card's cost/rarity — the threshold balance_warnings fires over.
        Exposed so the pipeline's balance-repair pass can target the same line the warning does."""
        expected = 5.0 + self._eff_cost(card) * 7.0  # X-cost (mod "X" or prototype -1) ~ 3 energy
        return expected * (1.6 if card.get("rarity", "common") in ("uncommon", "rare") else 1.25)

    def balance_warnings(self, card: dict, score: float | None = None) -> list[str]:
        if score is None:
            score = self.score_card(card)
        ceiling = self.power_ceiling(card)
        if score > ceiling:
            return [f"power score {score:.1f} exceeds ~{ceiling:.1f} for cost "
                    f"{card.get('cost', 0)} / {card.get('rarity', 'common')}"]
        return []

    def rarity_floor_warnings(self, card: dict, score: float | None = None) -> list[str]:
        """The inverse of balance_warnings: a RARE is supposed to be the archetype payoff,
        yet generated rares kept rolling out as flat stat lines weaker than the same set's
        uncommons. Flag a rare that BOTH scores below the plain cost baseline AND has no
        build-around mechanic (composite ops / X-cost). Either alone can be a legitimate
        design (Bludgeon is simple but huge; scaling cards score low but build); together
        they read like a mislabeled common."""
        if card.get("rarity") != "rare":
            return []
        if score is None:
            score = self.score_card(card)
        if self._is_x_cost(card) or self._has_composite(card.get("effects", [])):
            return []
        expected = 5.0 + self._eff_cost(card) * 7.0
        if score < expected:
            return [f"flat rare: power score {score:.1f} is under the cost baseline ~{expected:.0f} "
                    "and there is no build-around mechanic (an add_trigger engine / a `when` gate / a scaled "
                    "amount / X-cost) -- a rare should be the archetype payoff, not a mislabeled common"]
        return []

    @classmethod
    def _has_composite(cls, effects) -> bool:
        if not isinstance(effects, list):
            return False
        for e in effects:
            if not isinstance(e, dict):
                continue
            if e.get("op") in _BUILD_AROUND_OPS:
                return True
            # LEGACY prototype composites. Unconditional here (classmethod, no contract flag) but harmless under the
            # mod contract: its schema rejects these ops long before the rarity-floor check runs.
            if e.get("op") in _LEGACY_PROTOTYPE_OPS:
                return True
            if isinstance(e.get("when"), dict):
                return True  # a per-effect `when` guard (Phase H) is a conditional build-around
            if str(e.get("scale", "")).strip().lower() == "forged":
                return True  # Phase M: a forged-scaled payoff is the Forge archetype's build-around
            for key in ("effects", "then", "else"):
                if cls._has_composite(e.get(key)):
                    return True
        return False

    # -- 3b. corpus comparison: dominance + permanence ---------------------
    # The flat score is context-free; these compare a card to the cards that already exist
    # (the gap that let war_footing >= Inflame slip through). Both are WARNINGS, not rejects.

    def _profile(self, card: dict):
        """A card's flat player-benefit profile {effect_key: positive_int}, or None if the
        card isn't 'simple' enough to compare soundly. Conservative on purpose: any downside,
        debuff, negative/scaled amount, or composite op (multi/from_state/conditional/lose_hp/
        add_card/set_flag) returns None so we never compare on an undercounted profile (which
        would false-positive). Catches the flat 'buff + free rider' creep, abstains elsewhere."""
        prof: dict[str, int] = {}
        for eff in card.get("effects", []):
            if not isinstance(eff, dict):
                return None
            if eff.get("when"):
                return None  # a conditional (Phase H `when`) effect isn't an always-on flat benefit -> abstain
            op = eff.get("op")
            if op in _SIMPLE_BENEFIT_OPS:
                amt = eff.get("amount")
                if not isinstance(amt, int) or isinstance(amt, bool) or amt < 0:
                    return None
                prof[op] = prof.get(op, 0) + amt
            elif op == "apply_status":
                amt, status = eff.get("amount"), eff.get("status")
                meta = self.status_meta.get(status, {})
                # only flat self-buffs compare cleanly; debuffs / to:target / negatives -> abstain
                if (meta.get("kind") != "buff" or eff.get("to") == "target"
                        or not isinstance(amt, int) or isinstance(amt, bool) or amt <= 0):
                    return None
                key = f"buff:{status}"
                prof[key] = prof.get(key, 0) + amt
            else:
                return None
        return prof or None

    def dominance_warnings(self, card: dict) -> list[str]:
        """Flag if `card` is strictly better than an existing card it should not outclass:
        same-or-lower cost AND same-or-lower rarity (at least as accessible), >= on every effect
        the other has, and strictly better somewhere (bigger number or an extra effect)."""
        cand = self._profile(card)
        if not cand:
            return []
        c_cost = self._eff_cost(card)
        c_rank = _RARITY_RANK.get(card.get("rarity", "common"), 1)
        dominated = []
        for other in self.corpus:
            if other.get("id") == card.get("id"):
                continue
            op = self._profile(other)
            if not op:
                continue
            if c_cost > self._eff_cost(other) or c_rank > _RARITY_RANK.get(other.get("rarity", "common"), 1):
                continue
            if other.get("target") != card.get("target"):
                continue  # single-target can't dominate AoE (and vice-versa) — different value
            if card.get("exhaust") and not other.get("exhaust"):
                continue  # candidate carries an exhaust downside the other doesn't
            if any(cand.get(k, 0) < v for k, v in op.items()):
                continue  # candidate misses something the other provides -> can't dominate
            strictly = any(cand.get(k, 0) > v for k, v in op.items()) or any(k not in op for k in cand)
            if strictly:
                dominated.append(other.get("id"))
        if dominated:
            return ["power-creep: strictly better than %s (same-or-lower cost & rarity, "
                    ">= on every effect, plus more)" % ", ".join(sorted(dominated))]
        return []

    def permanence_warnings(self, card: dict) -> list[str]:
        """Flag a cheap permanent self-buff on a card that isn't a power or exhaust. Permanent
        buffs (decay:none) compound all fight = power-tier value (cf. Inflame); the flat score
        undervalues that. Encodes the design rule directly, even with no peer to dominate."""
        if card.get("type") == "power" or card.get("exhaust"):
            return []
        cost = self._eff_cost(card)
        if cost > 1:
            return []
        offenders = []
        for eff in card.get("effects", []):
            if not isinstance(eff, dict) or eff.get("op") != "apply_status":
                continue
            amt, status = eff.get("amount"), eff.get("status")
            meta = self.status_meta.get(status, {})
            if (meta.get("kind") == "buff" and meta.get("decay") == "none"
                    and eff.get("to") != "target"
                    and isinstance(amt, int) and not isinstance(amt, bool) and amt > 0):
                offenders.append(status)
        if offenders:
            return ["cheap permanent buff (%s) on a non-power, non-exhaust cost-%d card -- "
                    "permanent buffs are power-tier (cf. Inflame); use strength_temp, make it a "
                    "power, or add exhaust" % (", ".join(offenders), cost)]
        return []

    @staticmethod
    def _eff_cost(card: dict) -> int:
        c = card.get("cost", 0)
        if isinstance(c, str):
            return 3  # mod X-cost ("X") ~ 3 energy
        return c if c >= 0 else 3  # prototype X-cost (-1) ~ 3 energy, matching the balance heuristic

    @staticmethod
    def _is_x_cost(card: dict) -> bool:
        c = card.get("cost", 0)
        return (isinstance(c, str) and c.strip().upper() == "X") or (isinstance(c, int) and c == -1)

    # -- 3c. loop discipline -------------------------------------------------
    # Player rule (the Hand Out a Rose incident: a 0-cost signature re-adding itself to
    # hand): infinite combos are welcome but must take 3+ cards OR a real price per
    # iteration. These are WARNINGS, never rejects -- emergent hilarity is a feature; a
    # human decides at review. Pair loops (A<->B) are checked set-level by
    # character_validator.combo_loop_warnings; here we catch the one-card engine.

    @classmethod
    def hand_self_adds(cls, card: dict) -> bool:
        """True if the card add_card-copies ITSELF into the HAND (recursively). Copies to
        discard/draw are the sanctioned Anger pattern: the deck cycle gates the loop."""
        return card.get("id") in cls.hand_adds(card)

    @staticmethod
    def hand_adds(card: dict) -> set[str]:
        """Every card_id this card adds to the HAND, anywhere in its effect tree."""
        out: set[str] = set()

        def walk(effects) -> None:
            for e in effects or []:
                if not isinstance(e, dict):
                    continue
                if e.get("op") == "add_card" and e.get("pile") == "hand" \
                        and isinstance(e.get("card_id"), str):
                    out.add(e["card_id"])
                for key in ("effects", "then", "else"):
                    walk(e.get(key))

        walk(card.get("effects"))
        return out

    @classmethod
    def net_energy_cost(cls, card: dict) -> int:
        """Printed cost minus any gain_energy in the effects (X-cost ~ 3): the real price
        of one iteration of the card."""
        gained = 0
        for e in card.get("effects", []):
            if isinstance(e, dict) and e.get("op") == "gain_energy":
                amt = e.get("amount")
                if isinstance(amt, int) and not isinstance(amt, bool):
                    gained += amt
        return cls._eff_cost(card) - gained

    def loop_warnings(self, card: dict) -> list[str]:
        if not self.hand_self_adds(card) or card.get("exhaust"):
            return []
        if any(isinstance(e, dict) and e.get("op") == "lose_hp" for e in card.get("effects", [])):
            return []  # HP loss is a real per-iteration price
        net = self.net_energy_cost(card)
        if net >= 2:
            return []  # 'very expensive' loops are allowed to be tight
        return ["one-card engine: re-adds itself to HAND at net cost %d with no exhaust/HP "
                "price -- infinite combos should take 3+ cards or a real price per iteration "
                "(send copies to the discard pile like Anger, add exhaust, or charge >=2 "
                "energy)" % net]

    # -- 3d. functional reprints --------------------------------------------
    # Generated sets kept shipping existing cards under new names: at the time this was
    # added, 3 different quarantined classes each carried a "+2 Strength power" == Inflame,
    # and 7 of 65 non-basic quarantined cards were exact effect duplicates of the pool.
    # The skeleton index catches a candidate that rebuilds an existing card: numbers
    # stripped, top-level effect order ignored, fuse labels dropped, self-referencing
    # card_ids canonicalized. Identical-or-±1-nudged numbers (cost included) = a functional
    # reprint: hard ERROR at uncommon/rare (drives the repair loop to redesign), a warning
    # at common (an occasional familiar common is fine). The same skeleton with genuinely
    # different numbers only warns at uncommon/rare (a scaled-up multi-hit rare is a
    # legitimate design; a human judges at review). Only fresh LLM candidates are judged:
    # authored/promoted cards twin across classes by design (each class's literal basics,
    # body_slam/crushing_roll), and rarity 'basic' reprints Strike/Defend by rule.

    def _reprint_key_nums(self, card: dict) -> tuple[tuple, list[float]]:
        """(type, target, exhaust, effect-skeleton) + the flat number vector (cost last)."""
        sid = card.get("id")
        nums: list[float] = []

        def scrub(node):
            if isinstance(node, bool):
                return node
            if isinstance(node, (int, float)):
                nums.append(float(node))
                return "#"
            if isinstance(node, list):
                return [scrub(x) for x in node]
            if isinstance(node, dict):
                out = {}
                for k in sorted(node):
                    if k == "label":  # presentation only (fuse labels)
                        continue
                    if k == "card_id" and node[k] == sid:
                        out[k] = "<self>"  # Anger-style self-copy, id-agnostic
                        continue
                    out[k] = scrub(node[k])
                return out
            return node

        parts = []
        for eff in card.get("effects") or []:
            start = len(nums)
            parts.append((json.dumps(scrub(eff), separators=(",", ":")), nums[start:]))
            del nums[start:]
        parts.sort(key=lambda p: p[0])  # top-level effect order is not identity
        key = (card.get("type"), card.get("target"), bool(card.get("exhaust")),
               "[%s]" % ",".join(p[0] for p in parts))
        flat = [n for p in parts for n in p[1]]
        cost = card.get("cost", 0)  # mod X-cost is the string "X"; map it to the -1 sentinel (as _eff_cost
        flat.append(-1.0 if isinstance(cost, str) else float(cost))  # does) so it never 'nudges' into 0
        return key, flat

    def reprint_findings(self, card: dict) -> tuple[list[str], list[str]]:
        """(errors, warnings) per the policy in the block comment above."""
        if (card.get("source") != "llm" or card.get("id") in self.corpus_ids
                or card.get("rarity", "common") == "basic"):
            return [], []
        key, nums = self._reprint_key_nums(card)
        reprints, skeletons = [], []
        for oid, onums in self._reprint_index.get(key, []):
            if oid == card.get("id"):
                continue
            if len(onums) == len(nums) and all(abs(a - b) <= 1.0 for a, b in zip(nums, onums)):
                reprints.append(oid)
            else:
                skeletons.append(oid)
        rarity = card.get("rarity", "common")
        if reprints:
            msg = ("functional reprint of %s: the same effect skeleton with identical-or-"
                   "nudged numbers at the same-or-adjacent cost" % ", ".join(sorted(reprints)))
            if rarity in ("uncommon", "rare"):
                # Creative harness v2 (BTS_HARNESS_V2=1): the per-card brief already lists the class's used
                # shapes up front (Fix A), so at UNCOMMON the gate downgrades to a warning — late cards in a
                # class are no longer pushed into gimmicks or dropped. Rare keeps the hard error.
                from . import harness_v2
                if rarity == "uncommon" and harness_v2.enabled():
                    return [], [msg + " -- tolerated at uncommon under harness v2 (the brief carried the "
                                "used shapes), but it adds nothing new"]
                return [msg + " -- redesign with a mechanically different composition "
                        "(different ops / conditions / scaling), not just different numbers"], []
            return [], [msg + " -- tolerated at common, but it adds nothing new"]
        if skeletons and rarity in ("uncommon", "rare"):
            return [], ["same effect skeleton as %s (numbers differ meaningfully); fine if "
                        "deliberate, but a %s should read as a design that doesn't already "
                        "exist" % (", ".join(sorted(skeletons)), rarity)]
        return [], []

    # -- helpers -----------------------------------------------------------
    @staticmethod
    def _ids_in(directory: Path) -> set[str]:
        out: set[str] = set()
        if not directory.exists():
            return out
        for f in directory.glob("*.json"):
            try:
                d = json.loads(f.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            if isinstance(d, dict) and isinstance(d.get("id"), str):
                out.add(d["id"])
        return out

    @staticmethod
    def _status_meta() -> dict:
        out: dict[str, dict] = {}
        for f in paths.STATUSES_DIR.glob("*.json"):
            try:
                d = json.loads(f.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            if isinstance(d, dict) and isinstance(d.get("id"), str):
                out[d["id"]] = {"kind": d.get("kind", "buff"), "decay": d.get("decay", "none")}
        return out

    @staticmethod
    def _load_cards(directory: Path) -> list[dict]:
        out: list[dict] = []
        if not directory.exists():
            return out
        for f in sorted(directory.glob("*.json")):
            if f.name.endswith(".meta.json"):
                continue
            try:
                d = json.loads(f.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            # skip '+'-suffixed upgrade materializations (don't exist on disk, but be safe)
            if isinstance(d, dict) and isinstance(d.get("id"), str) and not d["id"].endswith("+"):
                out.append(d)
        return out

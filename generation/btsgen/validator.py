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

# ---- balance constants, copied verbatim from ContentValidator.gd ----
_STATUS_WEIGHT = {
    "vulnerable": 2.0, "weak": 1.5, "strength": 4.0,
    "dexterity": 3.0, "frail": 1.5, "ritual": 4.0,
    "strength_temp": 2.0,  # this-turn only: ~half permanent Strength's value
    "armor": 4.0,          # Barricade: Block persists/compounds (kept in parity with ContentValidator.gd)
    "burrowed": 6.0,       # a full turn of invulnerability (situational but a big swing)
}

_RARITY_RANK = {"basic": 0, "common": 1, "uncommon": 2, "rare": 3}
# ops whose integer `amount` is a flat, player-positive benefit (used by the dominance check)
_SIMPLE_BENEFIT_OPS = {"damage", "block", "draw", "gain_energy", "heal"}
# Phase H3: composite/build-around ops (the schema/triggerEffect $def enforces add_trigger's payload shape;
# these are for the balance heuristics — a trigger is a build-around, not a flat stat line).
_BUILD_AROUND_OPS = {"multi", "conditional", "from_state", "fuse", "add_trigger", "apply_status_custom",
                     "summon", "summon_attack", "buff_summon",
                     "heal_summon", "shield_summon",  # Phase AC (gap #2): summon support, not a flat stat line

                     "forge",  # Phase M (gap #36): Forge income/payoff is a build-around, not a stat line
                     "balance_step",  # Phase S (gap #1): a Balance-gauge step is build-around income, not a stat line
                     "upgrade_card",  # Phase V (gap #18): in-run upgrade is a utility/build-around, not a flat stat line
                     "blade_empower",  # Phase AF (gap #41): a transient blade multiplier is a build-around, not a stat line
                     "purge_card",  # Phase Z (gap #19 choose): targeted deck-thinning is a build-around, not a flat stat line
                     "transform_card",  # Phase AH (gaps #35/#38): a run-permanent self-rewrite is a build-around, not a stat line
                     "graft_card",  # Phase AI (gap #7): a choose-a-card run-permanent transform is a build-around, not a stat line
                     "scry"}  # Phase AA (gap #17 R-2): a draw-filter / on_discard fuel is a build-around, not a flat stat line
# F5: the live state scalars an effect's amount may scale to (mirrors ForgedCards.SupportedScales). "x" stays
# the X-cost scalar; the rest are hand/energy state reads. Only "cards_retained" is allowed inside a trigger.
# Phase M: "forged" is the ADDITIVE exception (printed amount + the Forge counter) and is damage/block-only.
_SUPPORTED_SCALES = {"x", "cards_in_hand", "cards_retained", "unspent_energy_last_turn", "forged",
                     # Phase P: damage_dealt_unblocked = heal-only lifesteal (heal the unblocked damage this card
                     # dealt); target_debuff_count = damage-only (deal damage = debuffs on the struck target).
                     "damage_dealt_unblocked", "target_debuff_count",
                     # Phase AE (gap #25): tag_cards_owned = ADDITIVE (printed amount + count of cards with a tag),
                     # damage/block-only, requires a sibling `tag`.
                     "tag_cards_owned"}
_TRIGGER_SCALE = "cards_retained"
# Self-buff statuses (mirror C# EffectRunner.SelfBuffStatuses) — a buff_summon's status must be one of these
# (it lands on the minion, like Strength). Kept in lockstep with the mod's ForgedCards.buff_summon validation.
_SELF_BUFF_STATUSES = {"strength", "dexterity", "thorns", "regen", "metallicize", "artifact", "buffer",
                       "intangible", "ritual", "blur", "temp_strength", "temp_dexterity", "barricade", "focus"}
# H4 (gaps #13/#14): the reactive triggers that can fire many times a turn → eligible for 'once_per_turn'
# (mirror ForgedCards.MultiFireTriggers); and the debuffs a TARGETED trigger apply_status may apply.
_MULTI_FIRE_TRIGGERS = {"on_hp_lost", "on_exhaust", "on_card_played", "on_card_drawn", "on_damage_dealt",
                        "on_block_gained", "attacked",
                        "on_discard"}  # Phase R (gap #17): a card can be discarded, redrawn, discarded again
_ENEMY_DEBUFF_STATUSES = {"vulnerable", "weak", "frail", "poison"}
# Phase Q (gap #16): the combat piles add_card may target + the copies-per-play cap. Mirrors ForgedCards.AddCardPiles
# / AddCardMaxAmount. card_id existence is the ref-integrity check (_ref_errors); these are the shape rules.
_ADD_CARD_PILES = {"hand", "discard", "draw"}
_ADD_CARD_MAX = 3
# Phase S (gap #1): the poles balance_step may move the gauge toward + the per-step cap. Mirrors ForgedCards
# .BalancePoles / BalanceStepMaxAmount. The both-poles / gated-payoff PAIRING rule is a class-level check
# (character_validator.balance_pairing_warnings) — a lone balance card is a warning there, not a per-card reject.
_BALANCE_POLES = {"light", "dark"}
_BALANCE_STEP_MAX = 5
# Phase AC (gap #2): summon heal/shield per-op caps (mirror ForgedCards.HealSummonMaxAmount / ShieldSummonMaxAmount).
_HEAL_SUMMON_MAX = 9
_SHIELD_SUMMON_MAX = 12
# Phase V/X (gap #18): the hand-scopes upgrade_card may use. Mirrors ForgedCards.UpgradeScopes. `random` is legal on
# cards AND in trigger payloads; `all` (whole hand) and `choose` (Phase X — the player picks one card) are card-only
# (a repeating whole-hand upgrade / a repeating pick-UI every turn is degenerate — rejected in a trigger by both this
# validator and ForgedCards.ValidateTrigger).
_UPGRADE_SCOPES = {"random", "all", "choose"}


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
                elif op == "multi":
                    walk(eff.get("effects"), f"{p}.effects")
                elif op == "fuse":
                    walk(eff.get("effects"), f"{p}.effects")
                elif op == "conditional":
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
        # cost 0..3, <= the base cost, and not on an X-cost card. Mirrors ForgedCards.TryParseCardJson.
        if isinstance(_up, dict) and _up.get("cost") is not None:
            ucost = _up.get("cost")
            base_cost = card.get("cost", 0)
            base_is_x = isinstance(base_cost, str) and base_cost.strip().upper() == "X"
            if base_is_x:
                out.append("upgrade 'cost' is not allowed on an X-cost card.")
            elif not (isinstance(ucost, int) and not isinstance(ucost, bool) and 0 <= ucost <= 3):
                out.append(f"upgrade 'cost' must be an integer 0..3; got {ucost!r}.")
            elif isinstance(base_cost, int) and ucost > base_cost:
                out.append(f"upgrade 'cost' ({ucost}) may not exceed the base cost ({base_cost}) — upgrades cheapen, never tax.")
        for e in effects + up_effects:
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
            elif e.get("card_id") is not None or e.get("pile") is not None:
                out.append(f"'card_id'/'pile' only apply to add_card/transform_card/graft_card (op '{e.get('op')}').")
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
            elif e.get("cards") is not None:
                out.append(f"'cards' only applies to upgrade_card (op '{e.get('op')}').")
        for e in effects + up_effects:  # per-effect shape rules apply to the upgrade too (lockstep w/ the
            op = e.get("op")            # mod's `effects.Concat(upgrade)` in ForgedCards.Validate)
            hits = e.get("hits", 1)
            scale = str(e.get("scale", "")).strip().lower()
            if isinstance(hits, int) and hits > 1 and op != "damage":
                out.append(f"'hits' only applies to 'damage' (op '{op}' had hits {hits}).")
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
        cost = card.get("cost", 0)
        costs_x = isinstance(cost, str) and cost.strip().upper() == "X"
        any_scale = any(str(e.get("scale", "")).lower() == "x" for e in effects)
        if costs_x and not any_scale:
            out.append("an X-cost card needs a 'scale:x' effect (otherwise X does nothing).")
        if not costs_x and any_scale:
            out.append("'scale:x' requires the card cost to be \"X\".")
        # the dup-var crash guard: a card may declare each canonical value only once
        seen: set[str] = set()
        for k in (self._var_key(e) for e in effects):
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
        for e in effects + up_effects:  # an add_trigger in the UPGRADE is validated too (the mod imports both)
            if e.get("op") != "add_trigger":
                continue
            if (isinstance(e.get("when"), dict)
                    and e["when"].get("kind") in ("target_has_status", "retained_last_turn")):
                out.append(f"a trigger's 'when' can't use {e['when'].get('kind')} (no card/target at end/start of turn).")
            # gap #6 "ripen": a one-shot after N turns — the add_trigger amount is the countdown (>= 1).
            if e.get("trigger") == "ripen" and int(e.get("amount", 0) or 0) < 1:
                out.append("a 'ripen' trigger needs amount >= 1 (the number of turns to wait before it fires once).")
            # H4: 'once_per_turn' only on a MULTI-FIRE reactive trigger (turn_start/turn_end/ripen already fire once/turn).
            if e.get("once_per_turn") and e.get("trigger") not in _MULTI_FIRE_TRIGGERS:
                out.append(f"'once_per_turn' only applies to a multi-fire trigger "
                           f"({'/'.join(sorted(_MULTI_FIRE_TRIGGERS))}); '{e.get('trigger')}' already fires at most once per turn.")
            for t in (e.get("effects") or []):
                if not isinstance(t, dict):
                    continue
                op = t.get("op")
                tgt = t.get("target")
                ts = str(t.get("scale", "")).strip().lower()
                if tgt is not None:
                    # H4 (gap #14): a TARGETED payload effect hits enemies — damage / enemy-debuff apply_status only,
                    # and never scaled. (target enum + op-vs-target coupling are also enforced by the schema.)
                    if op == "apply_status" and str(t.get("status", "")).strip().lower() not in _ENEMY_DEBUFF_STATUSES:
                        out.append(f"a targeted trigger apply_status must be an enemy debuff "
                                   f"({'/'.join(sorted(_ENEMY_DEBUFF_STATUSES))}); got '{t.get('status')}'.")
                    if ts:
                        out.append("a targeted trigger effect can't be scaled (scale is for the self numeric payload only).")
                else:
                    # a SELF payload apply_status must be a self-buff (the schema status enum now also lists debuffs).
                    if op == "apply_status" and str(t.get("status", "")).strip().lower() not in _SELF_BUFF_STATUSES:
                        out.append(f"a self trigger apply_status must be a self-buff (got '{t.get('status')}'); "
                                   "add target:enemy for a debuff.")
                    # F5: a self trigger payload may scale ONLY to cards_retained, never on channel_orb/evoke (no amount).
                    if ts and ts != _TRIGGER_SCALE:
                        out.append(f"inside a trigger only 'scale:{_TRIGGER_SCALE}' is allowed (got scale '{ts}').")
                    elif ts == _TRIGGER_SCALE and op in ("channel_orb", "evoke"):
                        out.append(f"'scale:{_TRIGGER_SCALE}' can't be used on a trigger '{op}' (no scalable amount).")
                    elif ts == _TRIGGER_SCALE and op in ("forge", "balance_step"):
                        # Phase M/S: trigger-side forge / balance income is a fixed drumbeat; scaling lives on payoff cards.
                        out.append(f"a trigger '{op}' uses a fixed amount (no scale).")
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
                elif t.get("cards") is not None:
                    out.append(f"'cards' only applies to upgrade_card (trigger effect '{op}').")
        up = card.get("upgrade")
        if isinstance(up, dict) and isinstance(up.get("effects"), list) and len(up["effects"]) != len(effects):
            out.append("upgrade effect count must match base effect count.")
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
            return amt + (6.0 if forged else 0.0) + grow_premium
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
        if op == "buff_summon":
            # Phase K (v15 true-Osty): a self-buff on the minion (default Strength) — weight per stack like a buff.
            return self._amt(eff.get("amount", 0)) * float(_STATUS_WEIGHT.get(eff.get("status", "strength") or "strength", 3.0))
        if op == "scry":
            # Phase AA (gap #17 R-2): a draw-quality filter (look at top N, discard any) — real card-selection
            # value that also fuels on_discard, but weaker than raw draw; ~1.5 per card looked at.
            return self._amt(eff.get("amount", 0)) * 1.5
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
        if op == "add_trigger":
            # Phase H3: a per-turn engine. Score one round of the payload (a conservative lower bound — the
            # real value compounds over the fight; _has_composite keeps it off the flat-rare floor).
            return sum(self._score_effect(t) for t in eff.get("effects", []))
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
                    "and there is no build-around mechanic (multi/conditional/from_state/fuse/"
                    "X-cost) -- a rare should be the archetype payoff, not a mislabeled common"]
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

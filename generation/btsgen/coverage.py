"""coverage.py — set-level creative-breadth quotas + ONE bounded repair round (Phase N-1).

The 7B ignores prose adjectives, so breadth ships as STRUCTURE: after the whole card set is designed,
census the non-basic pool (census.py), and if it falls short of the quotas below, regenerate a handful of
the plainest cards with a compact REQUIRED directive naming the missing mechanic. ONE round, budget-capped.
Advisory, NEVER fatal — surviving shortfalls stream as `WARNING:` notes and the class ships anyway
(posture precedent: forge_pairing_warnings / the summon dead-buff warning).

The directive phrasebook here is shared with the N-2 featured-mechanic roulette (one phrasebook for
roulette and repair). Repair targets plain stat-line commons/uncommons first and NEVER touches a basic,
the signature blade, a signature, the reprint homage, or (post-O-1) a bridge card.

W2.2 (vocab-gap remediation, 2026-09-09) widened the v2 menus so the repair round can reach the WHOLE
vocabulary: four more `when` kinds, class-kind-GATED `when` entries (forged_ge for a forge class, the
Balance gauge reads for a balance class, the orb reads for an orb class), a SCALE menu in place of the one
fixed scale directive, three nominate-only rare-tier exotics (ritual / barricade / intangible — repair
never injects them, the blueprint may nominate one), and a KEYWORD menu (retain / innate / ethereal /
multi-hit) with its own quota. All of it rides the creative-harness-v2 path (BTS_HARNESS_V2=1); the v1
menus and quotas stay byte-for-byte so the live A/B baseline is untouched.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import bridges, census

# --- quotas (measured over the NON-basic pool; basics/blade excluded; reprint exempt from plain-share) ---
MAX_PLAIN_SHARE = 0.30            # plain-stat-line cards / pool
MIN_REACTIVE_TRIGGER_KINDS = 2    # distinct trigger kinds beyond turn_start/turn_end
MIN_WHEN_KINDS = 3               # distinct `when` kinds (orb-only kinds count for orb classes)
MIN_EXOTIC_STATUSES = 2          # distinct statuses from census.EXOTIC_STATUSES
MAX_GENERIC_DEBUFF_SHARE = 0.25   # pool cards applying vulnerable/weak
MIN_SCALED_OR_X = 1              # cards with any `scale` or X-cost
MIN_KEYWORD_KINDS = 2            # W2.2 (v2 only): distinct card-shape keywords (retain/innate/ethereal/exhaust/multi_hit)
REPAIR_BUDGET = 6               # max card regenerations, ONE round


# --- the shared directive phrasebook (compact REQUIRED lines; 7B-safe, base-mechanics only so they are
#     valid on any class kind). Each menu is ordered — repair walks it, skipping kinds already present. ---
REACTIVE_MENU = [
    ("attacked", 'REQUIRED: add an ongoing power (op "add_trigger", trigger "attacked") whose payload deals damage back to the attacker.'),
    ("on_hp_lost", 'REQUIRED: add an ongoing power (op "add_trigger", trigger "on_hp_lost") that pays off whenever you lose HP.'),
    ("on_card_played", 'REQUIRED: add an ongoing power (op "add_trigger", trigger "on_card_played", once_per_turn) that rewards playing a card.'),
    ("on_block_gained", 'REQUIRED: add an ongoing power (op "add_trigger", trigger "on_block_gained") that rewards gaining Block.'),
    ("on_exhaust", 'REQUIRED: add an ongoing power (op "add_trigger", trigger "on_exhaust") that rewards exhausting a card.'),
]
WHEN_MENU = [
    ("hp_below_half", 'REQUIRED: gate one effect with `when` hp_below_half (a stronger payoff while you are below half HP).'),
    ("turn_at_least", 'REQUIRED: gate one effect with `when` turn_at_least value:3 (a payoff that arrives as the fight drags on).'),
    ("enemy_count_ge", 'REQUIRED: hit all_enemies and gate a bonus with `when` enemy_count_ge value:2 (reward fighting a crowd).'),
    ("no_block", 'REQUIRED: gate a bonus with `when` no_block (reward attacking with no Block up).'),
    ("has_block", 'REQUIRED: gate a bonus with `when` has_block (reward attacking while you hold Block).'),
]
EXOTIC_MENU = [
    ("thorns", 'REQUIRED: apply_status thorns (attackers take damage back).'),
    ("metallicize", 'REQUIRED: apply_status metallicize (gain Block at the end of every turn).'),
    ("regen", 'REQUIRED: apply_status regen (heal at the end of your turn).'),
    ("temp_strength", 'REQUIRED: apply_status temp_strength (a burst of Strength for this turn only).'),
    ("blur", 'REQUIRED: apply_status blur (your Block is not removed next turn).'),
]
# Creative harness v2 (BTS_HARNESS_V2=1, Fix B): the default exotic menu WITHOUT thorns/metallicize at its head
# (the two most generic entries in the vocabulary — they were injected into 5 of 14 ledger forges each) and a
# few more distinct statuses. Under v2 every menu is either filtered to the blueprint's per-class NOMINATIONS
# or shuffled with a seed derived from the concept hash, so two classes never receive the same injection order.
EXOTIC_MENU_V2 = [
    ("regen", 'REQUIRED: apply_status regen (heal at the end of your turn).'),
    ("temp_strength", 'REQUIRED: apply_status temp_strength (a burst of Strength for this turn only).'),
    ("blur", 'REQUIRED: apply_status blur (your Block is not removed next turn).'),
    ("artifact", 'REQUIRED: apply_status artifact (negate the next debuff applied to you).'),
    ("buffer", 'REQUIRED: apply_status buffer (prevent the next instance of HP loss).'),
    ("temp_dexterity", 'REQUIRED: apply_status temp_dexterity (a burst of Dexterity for this turn only).'),
]
REACTIVE_MENU_V2 = REACTIVE_MENU + [
    ("on_card_drawn", 'REQUIRED: add an ongoing power (op "add_trigger", trigger "on_card_drawn", once_per_turn) that rewards drawing a card.'),
    ("on_damage_dealt", 'REQUIRED: add an ongoing power (op "add_trigger", trigger "on_damage_dealt", once_per_turn) that rewards dealing damage.'),
]
WHEN_MENU_V2 = WHEN_MENU + [
    ("hand_size_ge", 'REQUIRED: gate a bonus with `when` hand_size_ge value:4 (a full-hand payoff).'),
    # W2.2: the rest of the base-vocab `when` kinds the repair round could never reach before.
    ("retained_last_turn", 'REQUIRED: give this card op "retain" and gate a bonus with `when` retained_last_turn '
                           '(the on-hold payoff: stronger if you held it in hand since last turn).'),
    ("draw_pile_empty", 'REQUIRED: gate a very strong effect with `when` draw_pile_empty (the Grand Finale: it only '
                        'fires once you have drawn your whole deck).'),
    ("hp_lost_ge", 'REQUIRED: put a small lose_hp self-cost FIRST on this card, then gate a big payoff with `when` '
                   'hp_lost_ge value:3 (the Ice Shatter threshold: pay HP, cash it the same turn).'),
    ("target_has_status", 'REQUIRED: gate a bonus with `when` target_has_status status:vulnerable (an exploit payoff '
                          'against an enemy you already debuffed).'),
]
# W2.2: class-kind-GATED `when` entries — (key, directive, kind). Dealt only to a class whose kind set (see
# harness_v2.pool_kind: the blueprint's orb/status/summon kind UNIONED with the selected archetypes' mechanic_kind)
# contains `kind`; a nomination of one of these on the wrong class kind is dropped.
WHEN_MENU_KIND = [
    ("forged_ge", 'REQUIRED: gate a payoff with `when` forged_ge value:5 (a Forge threshold: "if your Forge is 5+, ...").', "forge"),
    ("dark_ge", 'REQUIRED: gate a payoff with `when` dark_ge value:3 (a Dark-pole Balance payoff).', "balance"),
    ("light_ge", 'REQUIRED: gate a payoff with `when` light_ge value:3 (a Light-pole Balance payoff).', "balance"),
    ("centered", 'REQUIRED: gate a payoff with `when` centered value:1 (the knife\'s-edge Balance payoff: only while '
                 'the gauge sits within 1 of center).', "balance"),
    ("orbs_match", 'REQUIRED: gate a payoff with `when` orbs_match (the jackpot: every orb you hold is the same type).', "orb"),
    ("orb_count_ge", 'REQUIRED: gate a payoff with `when` orb_count_ge value:2 (a payoff for a full rack of orbs).', "orb"),
]
SCALE_DIRECTIVE = ('REQUIRED: make one damage or block amount scale (scale "cards_in_hand" or '
                   '"cards_retained") instead of a flat number.')
# W2.2: the SCALE menu (v2) — one entry per scale source instead of the single fixed directive above (v1 keeps it).
SCALE_MENU = [
    ("cards_in_hand", 'REQUIRED: make one damage or block amount scale "cards_in_hand" (equal to the OTHER cards in '
                      'your hand) instead of a flat number.'),
    ("cards_retained", 'REQUIRED: make one damage or block amount scale "cards_retained" (equal to the cards you held '
                       'into this turn) instead of a flat number.'),
    ("unspent_energy_last_turn", 'REQUIRED: make one damage, block or draw amount scale "unspent_energy_last_turn" '
                                 '(reward the energy you left over last turn).'),
    ("target_debuff_count", 'REQUIRED: make one damage amount scale "target_debuff_count" (deal damage equal to the '
                            'number of debuffs on the struck enemy - flechettes).'),
    ("damage_dealt_unblocked", 'REQUIRED: put a damage effect FIRST, then a heal with scale "damage_dealt_unblocked" '
                               '(lifesteal: heal for the unblocked damage this card dealt).'),
]
SCALE_MENU_KIND = [
    ("tag_cards_owned", 'REQUIRED: make one damage or block amount scale "tag_cards_owned" with a matching "tag" '
                        '(printed amount PLUS 1 per card you own carrying that tag; the tag must sit on 3-5 cards).', "tags"),
    ("forged", 'REQUIRED: make one damage or block amount scale "forged" (its printed amount PLUS your Forge counter).', "forge"),
]
# W2.2: NOMINATE-ONLY rare-tier exotics — repair never injects them off the shuffled menu; the blueprint may
# nominate one (coverage_nominations.exotic) and then the repair round can reach it.
EXOTIC_NOMINATE_ONLY = [
    ("ritual", 'REQUIRED: apply_status ritual on a RARE power (gain Strength at the end of every turn; small amount).'),
    ("barricade", 'REQUIRED: apply_status barricade on a RARE power (your Block is no longer removed at end of turn).'),
    ("intangible", 'REQUIRED: apply_status intangible amount 1 on a RARE card (all damage you take is reduced to 1 for a turn).'),
]
# W2.2: the KEYWORD menu (v2) — card-shape keywords with their own quota (MIN_KEYWORD_KINDS).
KEYWORD_MENU = [
    ("retain", 'REQUIRED: give this card op "retain" (it stays in your hand at end of turn) and make HOLDING it matter.'),
    ("innate", 'REQUIRED: give this card op "innate" (it starts in your opening hand every combat) - an opener.'),
    ("ethereal", 'REQUIRED: give this card op "ethereal" (it exhausts if still in hand at end of turn) and over-stat it.'),
    ("hits", 'REQUIRED: make this a MULTI-HIT attack: ONE damage effect carrying "hits": 2-4 (deal amount damage that many times).'),
]
NONPLAIN_DIRECTIVE = ('REQUIRED: this card must NOT be a plain stat line - build it around a distinctive '
                      'mechanic (an add_trigger, a `when` gate, an exotic status, or a scaled amount), '
                      'not just damage / block / apply Vulnerable or Weak.')

# Flat key -> directive lookup so the N-2 featured roulette shares this one phrasebook (roulette + repair).
DIRECTIVE_BY_KEY = {key: d for key, d in (REACTIVE_MENU + WHEN_MENU + EXOTIC_MENU)}
DIRECTIVE_BY_KEY["scale"] = SCALE_DIRECTIVE
# v2 keys (thorns/metallicize stay reachable by NOMINATION only — they are gone from the default v2 head)
for _k, _d in (REACTIVE_MENU_V2 + WHEN_MENU_V2 + EXOTIC_MENU_V2):
    DIRECTIVE_BY_KEY.setdefault(_k, _d)
# W2.2 keys: gated `when`, the scale menus, the nominate-only exotics, the keyword menu.
for _k, _d, _kind in (WHEN_MENU_KIND + SCALE_MENU_KIND):
    DIRECTIVE_BY_KEY.setdefault(_k, _d)
for _k, _d in (SCALE_MENU + EXOTIC_NOMINATE_ONLY + KEYWORD_MENU):
    DIRECTIVE_BY_KEY.setdefault(_k, _d)
_KEY_BY_DIRECTIVE = {d: k for k, d in DIRECTIVE_BY_KEY.items()}


# W2.2: one census DETECTOR per menu key — callable(census.CardCensus) -> bool, "this card carries the mechanic
# the directive asks for". The repair planner projects coverage with these and the tests assert every key has one.
def _det_trigger(k):
    return lambda cc: k in cc.triggers


def _det_when(k):
    return lambda cc: k in cc.whens


def _det_status(k):
    return lambda cc: k in cc.statuses


def _det_scale(k):
    return lambda cc: k in cc.scales


def _det_keyword(k):
    kk = census.MULTI_HIT_KIND if k == "hits" else k
    return lambda cc: kk in cc.keyword_kinds


CENSUS_DETECTOR: dict = {}
for _k, _d in REACTIVE_MENU_V2:
    CENSUS_DETECTOR[_k] = _det_trigger(_k)
for _k, _d in WHEN_MENU_V2:
    CENSUS_DETECTOR[_k] = _det_when(_k)
for _k, _d, _kind in WHEN_MENU_KIND:
    CENSUS_DETECTOR[_k] = _det_when(_k)
for _k, _d in (EXOTIC_MENU + EXOTIC_MENU_V2 + EXOTIC_NOMINATE_ONLY):
    CENSUS_DETECTOR[_k] = _det_status(_k)
for _k, _d in SCALE_MENU:
    CENSUS_DETECTOR[_k] = _det_scale(_k)
for _k, _d, _kind in SCALE_MENU_KIND:
    CENSUS_DETECTOR[_k] = _det_scale(_k)
for _k, _d in KEYWORD_MENU:
    CENSUS_DETECTOR[_k] = _det_keyword(_k)
CENSUS_DETECTOR["scale"] = lambda cc: cc.scaled_or_x  # the v1 fixed scale directive

# The per-class nomination categories the blueprint may declare (Fix B): category -> the v2 menu it filters.
# W0.5 adds "sections": blueprint-prompt section KEYS a CALLER (CLI / web / bench via ClassBrief.coverage_nominations)
# may pre-nominate so the pruned pitch for that subsystem is kept in the blueprint prompt. Mirrors
# class_forge.SECTION_KEYS (kept as a literal here to avoid a circular import; tests assert they match).
SECTION_KEYS = frozenset({"orb", "tags", "tokens", "rampage", "upgrade", "purge", "discard", "corruption",
                          "transform", "forge", "balance", "status", "summon"})
NOMINATION_CATEGORIES = ("reactive", "when", "exotic", "scale", "keyword", "sections")
NOMINATION_MAX = {"reactive": 3, "when": 4, "exotic": 3, "scale": 2, "keyword": 2, "sections": 4}
# W2.2: key -> the class kind it needs ("" = any class). Gated keys are dropped from a class that lacks the kind.
KEY_KIND = {k: kind for k, _d, kind in (WHEN_MENU_KIND + SCALE_MENU_KIND)}


def sanitize_nominations(raw) -> dict:
    """Normalize a blueprint's optional `coverage_nominations` ({reactive:[..], when:[..], exotic:[..],
    sections:[..]}) to known directive keys only, per-category capped. Unknown/malformed input -> {} (the
    seeded-shuffle default)."""
    if not isinstance(raw, dict):
        return {}
    known = {"reactive": {k for k, _ in REACTIVE_MENU_V2},
             "when": {k for k, _ in WHEN_MENU_V2} | {k for k, _d, _kind in WHEN_MENU_KIND},
             "exotic": {k for k, _ in EXOTIC_MENU_V2} | {"thorns", "metallicize"} | {k for k, _ in EXOTIC_NOMINATE_ONLY},
             "scale": {k for k, _ in SCALE_MENU} | {k for k, _d, _kind in SCALE_MENU_KIND},
             "keyword": {k for k, _ in KEYWORD_MENU},
             "sections": set(SECTION_KEYS)}
    out: dict = {}
    for cat in NOMINATION_CATEGORIES:
        vals = raw.get(cat)
        if not isinstance(vals, list):
            continue
        keep: list[str] = []
        for v in vals:
            k = str(v).strip().lower()
            if k in known[cat] and k not in keep:
                keep.append(k)
        if keep:
            out[cat] = keep[:NOMINATION_MAX[cat]]
    return out


def _kind_ok(key: str, kinds) -> bool:
    """W2.2: may this menu key be dealt to a class with kind set `kinds`? Ungated keys always; a gated key only
    when the class carries its kind. `kinds` None = the caller doesn't know the class (gated keys are out)."""
    need = KEY_KIND.get(key, "")
    return not need or (kinds is not None and need in kinds)


def _pick(cat: str, menu: list, nominated: dict, seed: int | None, kinds, salt: str) -> list:
    """One v2 menu: the category's nominated keys (in nominated order, kind-gated) when the blueprint nominated
    any; otherwise `menu` (already kind-gated) shuffled with the concept seed."""
    from . import harness_v2
    keys = nominated.get(cat)
    if keys:
        return [(k, DIRECTIVE_BY_KEY[k]) for k in keys if k in DIRECTIVE_BY_KEY and _kind_ok(k, kinds)]
    if seed is not None:
        return harness_v2.seeded_shuffle(menu, seed, salt)
    return list(menu)


def _menus(nominated: dict | None, seed: int | None, kinds=None) -> tuple[list, list, list]:
    """The (reactive, when, exotic) menus the repair walker uses. v1 (flag off): the fixed ordered menus,
    byte-for-byte. v2: each menu is filtered to that category's nominated keys (in nominated order) when the
    blueprint nominated any; otherwise the v2 menu shuffled with the concept seed. W2.2: the v2 `when` menu
    also carries the class-kind-gated entries (WHEN_MENU_KIND) whose kind is in `kinds`."""
    from . import harness_v2
    if not harness_v2.enabled():
        return list(REACTIVE_MENU), list(WHEN_MENU), list(EXOTIC_MENU)
    nominated = nominated or {}
    when_menu = list(WHEN_MENU_V2) + [(k, d) for k, d, kind in WHEN_MENU_KIND if _kind_ok(k, kinds)]
    return (_pick("reactive", REACTIVE_MENU_V2, nominated, seed, kinds, "reactive"),
            _pick("when", when_menu, nominated, seed, kinds, "when"),
            _pick("exotic", EXOTIC_MENU_V2, nominated, seed, kinds, "exotic"))


def _menus_w2(nominated: dict | None, seed: int | None, kinds=None) -> tuple[list, list]:
    """W2.2: the (scale, keyword) menus. v1: the single fixed SCALE_DIRECTIVE (key "scale") and NO keyword menu
    (the keyword quota is v2-only). v2: the scale menu (+ kind-gated sources) and the keyword menu, each
    nominated-or-shuffled like the others."""
    from . import harness_v2
    if not harness_v2.enabled():
        return [("scale", SCALE_DIRECTIVE)], []
    nominated = nominated or {}
    scale_menu = list(SCALE_MENU) + [(k, d) for k, d, kind in SCALE_MENU_KIND if _kind_ok(k, kinds)]
    return (_pick("scale", scale_menu, nominated, seed, kinds, "scale"),
            _pick("keyword", KEYWORD_MENU, nominated, seed, kinds, "keyword"))


def directive_key(directive: str) -> str:
    """The short menu key for a directive line ('attacked', 'thorns', 'scale', 'nonplain', 'bridge', or
    'featured') — what the ledger + bench count as an injected mechanic."""
    if directive in _KEY_BY_DIRECTIVE:
        return _KEY_BY_DIRECTIVE[directive]
    if directive == NONPLAIN_DIRECTIVE:
        return "nonplain"
    if "BRIDGE" in directive or "fuse" in directive.lower():
        return "bridge"
    return "featured"


@dataclass
class PoolReport:
    """The measured state of one class's non-basic pool + its quota violations."""
    pool_size: int = 0                 # measurable cards (incl. reprint + signatures)
    plain_denom: int = 0               # measurable cards EXCLUDING the reprint (plain-share denominator)
    plain: int = 0                     # plain cards among plain_denom
    reactive_kinds: set = field(default_factory=set)
    when_kinds: set = field(default_factory=set)
    exotic_kinds: set = field(default_factory=set)
    generic_debuff_cards: int = 0
    scaled_or_x: int = 0
    scale_kinds: set = field(default_factory=set)     # W2.2: distinct scale sources in use
    keyword_kinds: set = field(default_factory=set)   # W2.2: distinct card-shape keywords (census.keyword_kinds)
    violations: list = field(default_factory=list)   # human-readable

    @property
    def plain_share(self) -> float:
        return (self.plain / self.plain_denom) if self.plain_denom else 0.0

    @property
    def generic_debuff_share(self) -> float:
        return (self.generic_debuff_cards / self.pool_size) if self.pool_size else 0.0


def _role_sets():
    """The protected-role sets live in class_forge; import lazily to avoid an import cycle."""
    from .class_forge import _BASIC_ROLES, _SIGNATURE_ROLES, _BLADE_ROLE
    return _BASIC_ROLES, _SIGNATURE_ROLES, _BLADE_ROLE


def _is_reprint(plan: dict) -> bool:
    return str((plan or {}).get("theme", "")).strip().lower().startswith("reprint of")


def _is_bridge(entry: dict) -> bool:
    # O-1 bridge cards (fusion enforcer) are protected from UNRELATED quota repairs.
    return bool((entry.get("plan") or {}).get("bridge") or (entry.get("card") or {}).get("bridge"))


def bridge_indices(made: list[dict]) -> list[int]:
    """Measurable pool cards tagged as bridges (the O-1 fusion cards)."""
    return [i for i in measurable_indices(made) if _is_bridge(made[i])]


def _pair_ctx(entry: dict, bridge_ctx):
    """The witness context ({name_a, ops_a, name_b, ops_b[, ops_third, name_third]}) for ONE bridge card's
    DECLARED pair (Phase 1). A triad bridge declares `[id1, id2]` -> look that pair up in bridge_ctx["pairs"];
    a 2-archetype boolean bridge uses the single top-level pair. None when it can't be resolved (the semantic
    check is then skipped for that card)."""
    if not bridge_ctx:
        return None
    b = ((entry.get("plan") or {}).get("bridge")) or ((entry.get("card") or {}).get("bridge"))
    if isinstance(b, (list, tuple)) and len(b) == 2:
        key = bridges.pair_key(str(b[0]), str(b[1]))
        return (bridge_ctx.get("pairs") or {}).get(key)
    # boolean bridge (2-archetype) -> the single pair, exposed top-level
    if "ops_a" in bridge_ctx and "ops_b" in bridge_ctx:
        return bridge_ctx
    pairs = bridge_ctx.get("pairs") or {}
    return next(iter(pairs.values())) if len(pairs) == 1 else None


def bridge_failures(made: list[dict], bridge_ctx) -> list[int]:
    """Indices of bridge cards that do NOT witness their DECLARED pair's engines (bridges.is_witnessed).
    Empty when there is no resolvable archetype context (invented concept-path ids) — the semantic check is
    then skipped and only the blueprint-stage tag-count applies. Under triad each bridge is checked against
    ITS OWN pair's ops (routed via _pair_ctx), not one global pair."""
    if not bridge_ctx:
        return []
    fails = []
    for i in bridge_indices(made):
        pctx = _pair_ctx(made[i], bridge_ctx)
        if pctx and not bridges.is_witnessed((made[i].get("card") or {}), pctx["ops_a"], pctx["ops_b"]):
            fails.append(i)
    return fails


def measurable_indices(made: list[dict]) -> list[int]:
    """Indices of cards the quotas MEASURE: everything except basics and the blade/token."""
    basic, sig, blade = _role_sets()
    out = []
    for i, m in enumerate(made):
        plan = m.get("plan") or {}
        card = m.get("card") or {}
        role = plan.get("role")
        if role in basic:
            continue
        if role == blade or card.get("token"):
            continue
        out.append(i)
    return out


def victim_indices(made: list[dict]) -> list[int]:
    """Repair victims, best-first: plain cards, never protected (basic / blade / signature / reprint /
    bridge). Prefer generic-debuff carriers and commons/uncommons; plain rares last; then non-plain
    commons/uncommons as a fallback so a missing mechanic can still land somewhere."""
    basic, sig, blade = _role_sets()

    def rank(i: int):
        m = made[i]
        plan = m.get("plan") or {}
        card = m.get("card") or {}
        cc = census.walk_card(card)
        rarity = str(card.get("rarity", plan.get("rarity", "common"))).lower()
        is_rare = rarity == "rare"
        # lower sorts first
        plain_key = 0 if cc.plain else 1
        debuff_key = 0 if cc.uses_generic_debuff else 1
        rare_key = 1 if is_rare else 0
        return (plain_key, rare_key, debuff_key, i)

    cands = []
    for i in measurable_indices(made):
        m = made[i]
        plan = m.get("plan") or {}
        card = m.get("card") or {}
        role = plan.get("role")
        if role in sig or role == blade or card.get("token"):
            continue
        if _is_reprint(plan) or _is_bridge(m):
            continue
        cands.append(i)
    cands.sort(key=rank)
    return cands


def measure(made: list[dict]) -> PoolReport:
    """Census the non-basic pool and record every quota violation."""
    rep = PoolReport()
    idxs = measurable_indices(made)
    rep.pool_size = len(idxs)
    for i in idxs:
        m = made[i]
        plan = m.get("plan") or {}
        card = m.get("card") or {}
        cc = census.walk_card(card)
        rep.reactive_kinds |= cc.reactive_trigger_kinds
        rep.when_kinds |= set(cc.whens)
        rep.exotic_kinds |= cc.exotic_status_kinds
        if cc.uses_generic_debuff:
            rep.generic_debuff_cards += 1
        if cc.scaled_or_x:
            rep.scaled_or_x += 1
        rep.scale_kinds |= set(cc.scales)
        rep.keyword_kinds |= cc.keyword_kinds
        if not _is_reprint(plan):
            rep.plain_denom += 1
            if cc.plain:
                rep.plain += 1

    v = rep.violations
    if rep.plain_denom and rep.plain_share > MAX_PLAIN_SHARE:
        v.append(f"plain share {rep.plain_share:.0%} > {MAX_PLAIN_SHARE:.0%}")
    if len(rep.reactive_kinds) < MIN_REACTIVE_TRIGGER_KINDS:
        v.append(f"only {len(rep.reactive_kinds)} reactive trigger kind(s) < {MIN_REACTIVE_TRIGGER_KINDS}")
    if len(rep.when_kinds) < MIN_WHEN_KINDS:
        v.append(f"only {len(rep.when_kinds)} `when` kind(s) < {MIN_WHEN_KINDS}")
    if len(rep.exotic_kinds) < MIN_EXOTIC_STATUSES:
        v.append(f"only {len(rep.exotic_kinds)} exotic status(es) < {MIN_EXOTIC_STATUSES}")
    if rep.pool_size and rep.generic_debuff_share > MAX_GENERIC_DEBUFF_SHARE:
        v.append(f"generic-debuff share {rep.generic_debuff_share:.0%} > {MAX_GENERIC_DEBUFF_SHARE:.0%}")
    if rep.scaled_or_x < MIN_SCALED_OR_X:
        v.append(f"{rep.scaled_or_x} scaled/X card(s) < {MIN_SCALED_OR_X}")
    if _keyword_quota_on() and len(rep.keyword_kinds) < MIN_KEYWORD_KINDS:
        v.append(f"only {len(rep.keyword_kinds)} keyword kind(s) < {MIN_KEYWORD_KINDS}")
    return rep


def _keyword_quota_on() -> bool:
    """W2.2: the keyword quota rides the creative-harness-v2 path only (the v1 baseline is the live A/B control)."""
    from . import harness_v2
    return harness_v2.enabled()


def plan_repairs(rep: PoolReport, budget: int = REPAIR_BUDGET, *, nominated: dict | None = None,
                 seed: int | None = None, kinds=None) -> list[str]:
    """Ordered directive lines to inject (one per victim), capped at `budget`. Projects coverage forward as
    it assigns so it never over-requests a mechanic already covered by an earlier directive. `nominated` /
    `seed` (harness v2 only) pick the menus: the blueprint's per-class nominations, else a concept-seeded
    shuffle (see _menus). `kinds` (W2.2, v2) = the class's kind set (harness_v2.pool_kind) that unlocks the
    class-kind-gated `when` / scale entries. Flag off: the fixed v1 menus, unchanged."""
    reactive_menu, when_menu, exotic_menu = _menus(nominated, seed, kinds)
    scale_menu, keyword_menu = _menus_w2(nominated, seed, kinds)
    directives: list[str] = []
    proj_reactive = set(rep.reactive_kinds)
    proj_when = set(rep.when_kinds)
    proj_exotic = set(rep.exotic_kinds)
    proj_scaled = rep.scaled_or_x
    proj_scale_kinds = set(rep.scale_kinds)
    proj_keyword = set(rep.keyword_kinds)

    def room() -> bool:
        return len(directives) < budget

    for key, d in reactive_menu:
        if len(proj_reactive) >= MIN_REACTIVE_TRIGGER_KINDS or not room():
            break
        if key in proj_reactive:
            continue
        directives.append(d)
        proj_reactive.add(key)
    for key, d in when_menu:
        if len(proj_when) >= MIN_WHEN_KINDS or not room():
            break
        if key in proj_when:
            continue
        directives.append(d)
        proj_when.add(key)
    for key, d in exotic_menu:
        if len(proj_exotic) >= MIN_EXOTIC_STATUSES or not room():
            break
        if key in proj_exotic:
            continue
        directives.append(d)
        proj_exotic.add(key)
    for key, d in scale_menu:  # v1: the one fixed SCALE_DIRECTIVE; v2 (W2.2): the first scale source not in use
        if proj_scaled >= MIN_SCALED_OR_X or not room():
            break
        if key in proj_scale_kinds:
            continue
        directives.append(d)
        proj_scaled += 1
        proj_scale_kinds.add(key)
    for key, d in keyword_menu:  # W2.2, v2 only (the v1 keyword menu is empty)
        if len(proj_keyword) >= MIN_KEYWORD_KINDS or not room():
            break
        kk = census.MULTI_HIT_KIND if key == "hits" else key
        if kk in proj_keyword:
            continue
        directives.append(d)
        proj_keyword.add(kk)

    # plain-share / generic-debuff: every directive above converts a plain victim to non-plain. Add generic
    # NONPLAIN directives for the residual plain excess, up to budget.
    projected_plain = max(0, rep.plain - len(directives))
    allowed_plain = int(MAX_PLAIN_SHARE * rep.plain_denom)
    while projected_plain > allowed_plain and room():
        directives.append(NONPLAIN_DIRECTIVE)
        projected_plain -= 1
    return directives


def _featured_missing(made: list[dict], featured) -> list:
    """Featured entries (N-2 roulette; duck-typed .id/.directive/.detect) NOT carried by any measurable
    pool card. coverage does not import featured.py — the entries are passed in — so there is no cycle."""
    if not featured:
        return []
    ccs = [census.walk_card((made[i].get("card") or {})) for i in measurable_indices(made)]
    return [f for f in featured if not _carried(f, ccs)]


def _carried(f, ccs) -> bool:
    """Is featured entry `f` carried by the pool? W2.3 entries may define `carried_by(ccs)` (a pool-level
    detector / a min-card count); older duck-typed entries expose only the per-card `detect`."""
    carried_by = getattr(f, "carried_by", None)
    if callable(carried_by):
        return bool(carried_by(ccs))
    return any(f.detect(cc) for cc in ccs)


def enforce_coverage(made: list[dict], regen_card, note, *, featured=None, bridge_ctx=None,
                     budget: int = REPAIR_BUDGET, nominated: dict | None = None,
                     seed: int | None = None, kinds=None) -> dict:
    """Census the pool, run ONE bounded repair round, stream a summary + WARNING notes. Mutates `made`
    in place (swapping repaired cards). `regen_card(plan, old_card, directive) -> card|None` rebuilds one
    card. `featured` = the N-2 rolled mechanics (each missing one is a quota item with its own directive).
    `bridge_ctx` (O-1) = {ops_a, ops_b, name_a, name_b} or None: when present, bridge cards that do NOT fuse
    both engines are repaired IN PLACE with a fusion directive, ahead of the featured + generic directives
    (bridges are the class identity). `nominated` / `seed` (harness v2): the blueprint's per-class menu
    nominations + the concept seed for the shuffled fallback (see plan_repairs). Returns a summary dict (also
    handy for tests) whose `injections` list records every injected mechanic ({key, old, new, ok}) so the
    ledger + bench can count them. Never raises through to the caller's forge — the caller wraps this, but we
    keep it self-contained too. `kinds` (W2.2) = the class's kind set for the class-kind-gated menus."""
    featured = list(featured or [])
    before = measure(made)
    kw = (f", keywords {len(before.keyword_kinds)} (min {MIN_KEYWORD_KINDS})" if _keyword_quota_on() else "")
    note(f"coverage: pool {before.pool_size} cards - plain {before.plain_share:.0%} (max {MAX_PLAIN_SHARE:.0%}), "
         f"reactive kinds {len(before.reactive_kinds)} (min {MIN_REACTIVE_TRIGGER_KINDS}), "
         f"`when` kinds {len(before.when_kinds)} (min {MIN_WHEN_KINDS}), "
         f"exotic {len(before.exotic_kinds)} (min {MIN_EXOTIC_STATUSES}), "
         f"debuff {before.generic_debuff_share:.0%} (max {MAX_GENERIC_DEBUFF_SHARE:.0%}), "
         f"scaled/X {before.scaled_or_x} (min {MIN_SCALED_OR_X})" + kw)

    feat_missing = _featured_missing(made, featured)
    if featured:
        missing_ids = {f.id for f in feat_missing}
        note("coverage featured: " + "; ".join(
            f"{f.id}={'MISSING' if f.id in missing_ids else 'present'}" for f in featured))

    # O-1 bridges: witness the fusion cards against each card's DECLARED pair (skip the semantic check if the
    # archetype ops can't be resolved). Under triad there are three pairs, so name the engine count, not a
    # single A x B.
    bridge_all = bridge_indices(made)
    bridge_fail = bridge_failures(made, bridge_ctx)
    if bridge_ctx:
        n_pairs = len(bridge_ctx.get("pairs") or {}) or 1
        engines = (f"{bridge_ctx['name_a']} x {bridge_ctx['name_b']}" if "name_a" in bridge_ctx
                   else f"{n_pairs} pair-lanes")
        note(f"coverage bridges: {len(bridge_all)} tagged, {len(bridge_all) - len(bridge_fail)} fuse their "
             f"declared pair ({engines})")
        if len(bridge_all) < bridges.MIN_BRIDGES:
            note(f"WARNING: only {len(bridge_all)} bridge card(s) survived generation "
                 f"(want {bridges.MIN_BRIDGES})")

    summary = {"before": before, "repaired": 0, "attempted": 0, "after": before,
               "featured_missing_before": [f.id for f in feat_missing],
               "bridge_fail_before": list(bridge_fail), "injections": []}
    violations = (list(before.violations)
                  + [f"featured '{f.id}' not woven in" for f in feat_missing]
                  + ([f"{len(bridge_fail)} bridge card(s) do not fuse both engines"] if bridge_fail else []))
    if not violations:
        note("coverage: quotas met, no repair needed")
        return summary

    # Build the (index, directive) repair pairs. FAILED BRIDGES repair IN PLACE (their own index) and go
    # FIRST — they are the class identity; then featured misses, then the generic quota directives, filling
    # non-bridge victims. Everything shares the one budget.
    pairs: list[tuple[int, str]] = []
    if bridge_ctx:
        for i in bridge_fail:
            if len(pairs) >= budget:
                break
            pctx = _pair_ctx(made[i], bridge_ctx) or bridge_ctx  # per declared pair (triad-aware)
            bdir = bridges.repair_directive(pctx["name_a"], pctx["name_b"], pctx["ops_a"], pctx["ops_b"])
            pairs.append((i, bdir))

    remaining = max(0, budget - len(pairs))
    directives: list[str] = []
    for d in [f.directive for f in feat_missing] + plan_repairs(before, remaining, nominated=nominated, seed=seed,
                                                                 kinds=kinds):
        if d not in directives:
            directives.append(d)
    directives = directives[:remaining]
    victims = victim_indices(made)  # excludes bridges + protected roles
    gen_pairs = list(zip(victims, directives))  # cap to available victims
    if len(directives) > len(victims):
        note(f"coverage: {len(directives) - len(victims)} needed mechanic(s) have no eligible plain victim "
             "to carry them (pool too small); repairing what we can")
    pairs += gen_pairs
    note(f"coverage: {len(violations)} shortfall(s): {'; '.join(violations)}")
    note(f"coverage: repairing {len(pairs)} card(s) (budget {budget})")

    for idx, directive in pairs:
        summary["attempted"] += 1
        old = made[idx].get("card") or {}
        old_name = old.get("name", "?")
        new_card = None
        try:
            new_card = regen_card(made[idx].get("plan") or {}, old, directive)
        except Exception as e:  # a repair failure must never break the forge
            note(f"coverage repair: '{old_name}' regeneration errored ({e}); keeping original")
        key = directive_key(directive)
        if new_card:
            made[idx]["card"] = new_card
            summary["repaired"] += 1
            gist = directive.replace("REQUIRED:", "").strip()[:64]
            note(f"coverage repair: '{old_name}' -> '{new_card.get('name', '?')}' ({gist})")
            summary["injections"].append({"key": key, "old": old_name, "new": new_card.get("name", "?"), "ok": True})
        else:
            note(f"coverage repair: '{old_name}' could not be improved; keeping original")
            summary["injections"].append({"key": key, "old": old_name, "new": None, "ok": False})

    after = measure(made)
    feat_missing_after = _featured_missing(made, featured)
    bridge_fail_after = bridge_failures(made, bridge_ctx)
    summary["after"] = after
    summary["featured_missing_after"] = [f.id for f in feat_missing_after]
    summary["bridge_fail_after"] = list(bridge_fail_after)
    surviving = (list(after.violations)
                 + [f"featured '{f.id}' not woven in" for f in feat_missing_after]
                 + ([f"{len(bridge_fail_after)} bridge card(s) still not fusing both engines"]
                    if bridge_fail_after else []))
    if surviving:
        for vio in surviving:
            note(f"WARNING: coverage shortfall persists after repair: {vio}")
    else:
        note("coverage: all quotas met after repair")
    note(f"coverage: after repair - plain {after.plain_share:.0%}, reactive kinds {len(after.reactive_kinds)}, "
         f"`when` kinds {len(after.when_kinds)}, exotic {len(after.exotic_kinds)}, "
         f"debuff {after.generic_debuff_share:.0%}, scaled/X {after.scaled_or_x}"
         + (f", keywords {len(after.keyword_kinds)}" if _keyword_quota_on() else ""))
    return summary

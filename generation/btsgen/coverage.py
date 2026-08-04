"""coverage.py — set-level creative-breadth quotas + ONE bounded repair round (Phase N-1).

The 7B ignores prose adjectives, so breadth ships as STRUCTURE: after the whole card set is designed,
census the non-basic pool (census.py), and if it falls short of the quotas below, regenerate a handful of
the plainest cards with a compact REQUIRED directive naming the missing mechanic. ONE round, budget-capped.
Advisory, NEVER fatal — surviving shortfalls stream as `WARNING:` notes and the class ships anyway
(posture precedent: forge_pairing_warnings / the summon dead-buff warning).

The directive phrasebook here is shared with the N-2 featured-mechanic roulette (one phrasebook for
roulette and repair). Repair targets plain stat-line commons/uncommons first and NEVER touches a basic,
the signature blade, a signature, the reprint homage, or (post-O-1) a bridge card.
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
SCALE_DIRECTIVE = ('REQUIRED: make one damage or block amount scale (scale "cards_in_hand" or '
                   '"cards_retained") instead of a flat number.')
NONPLAIN_DIRECTIVE = ('REQUIRED: this card must NOT be a plain stat line - build it around a distinctive '
                      'mechanic (an add_trigger, a `when` gate, an exotic status, or a scaled amount), '
                      'not just damage / block / apply Vulnerable or Weak.')

# Flat key -> directive lookup so the N-2 featured roulette shares this one phrasebook (roulette + repair).
DIRECTIVE_BY_KEY = {key: d for key, d in (REACTIVE_MENU + WHEN_MENU + EXOTIC_MENU)}
DIRECTIVE_BY_KEY["scale"] = SCALE_DIRECTIVE


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


def bridge_failures(made: list[dict], bridge_ctx) -> list[int]:
    """Indices of bridge cards that do NOT witness both archetypes' engines (bridges.is_witnessed). Empty
    when there is no resolvable archetype context (invented concept-path ids) — the semantic check is then
    skipped and only the blueprint-stage tag-count applies."""
    if not bridge_ctx:
        return []
    ops_a, ops_b = bridge_ctx["ops_a"], bridge_ctx["ops_b"]
    return [i for i in bridge_indices(made)
            if not bridges.is_witnessed((made[i].get("card") or {}), ops_a, ops_b)]


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
    return rep


def plan_repairs(rep: PoolReport, budget: int = REPAIR_BUDGET) -> list[str]:
    """Ordered directive lines to inject (one per victim), capped at `budget`. Projects coverage forward as
    it assigns so it never over-requests a mechanic already covered by an earlier directive."""
    directives: list[str] = []
    proj_reactive = set(rep.reactive_kinds)
    proj_when = set(rep.when_kinds)
    proj_exotic = set(rep.exotic_kinds)
    proj_scaled = rep.scaled_or_x

    def room() -> bool:
        return len(directives) < budget

    for key, d in REACTIVE_MENU:
        if len(proj_reactive) >= MIN_REACTIVE_TRIGGER_KINDS or not room():
            break
        if key in proj_reactive:
            continue
        directives.append(d)
        proj_reactive.add(key)
    for key, d in WHEN_MENU:
        if len(proj_when) >= MIN_WHEN_KINDS or not room():
            break
        if key in proj_when:
            continue
        directives.append(d)
        proj_when.add(key)
    for key, d in EXOTIC_MENU:
        if len(proj_exotic) >= MIN_EXOTIC_STATUSES or not room():
            break
        if key in proj_exotic:
            continue
        directives.append(d)
        proj_exotic.add(key)
    if proj_scaled < MIN_SCALED_OR_X and room():
        directives.append(SCALE_DIRECTIVE)
        proj_scaled += 1

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
    return [f for f in featured if not any(f.detect(cc) for cc in ccs)]


def enforce_coverage(made: list[dict], regen_card, note, *, featured=None, bridge_ctx=None,
                     budget: int = REPAIR_BUDGET) -> dict:
    """Census the pool, run ONE bounded repair round, stream a summary + WARNING notes. Mutates `made`
    in place (swapping repaired cards). `regen_card(plan, old_card, directive) -> card|None` rebuilds one
    card. `featured` = the N-2 rolled mechanics (each missing one is a quota item with its own directive).
    `bridge_ctx` (O-1) = {ops_a, ops_b, name_a, name_b} or None: when present, bridge cards that do NOT fuse
    both engines are repaired IN PLACE with a fusion directive, ahead of the featured + generic directives
    (bridges are the class identity). Returns a summary dict (also handy for tests). Never raises through to
    the caller's forge — the caller wraps this, but we keep it self-contained too."""
    featured = list(featured or [])
    before = measure(made)
    note(f"coverage: pool {before.pool_size} cards - plain {before.plain_share:.0%} (max {MAX_PLAIN_SHARE:.0%}), "
         f"reactive kinds {len(before.reactive_kinds)} (min {MIN_REACTIVE_TRIGGER_KINDS}), "
         f"`when` kinds {len(before.when_kinds)} (min {MIN_WHEN_KINDS}), "
         f"exotic {len(before.exotic_kinds)} (min {MIN_EXOTIC_STATUSES}), "
         f"debuff {before.generic_debuff_share:.0%} (max {MAX_GENERIC_DEBUFF_SHARE:.0%}), "
         f"scaled/X {before.scaled_or_x} (min {MIN_SCALED_OR_X})")

    feat_missing = _featured_missing(made, featured)
    if featured:
        missing_ids = {f.id for f in feat_missing}
        note("coverage featured: " + "; ".join(
            f"{f.id}={'MISSING' if f.id in missing_ids else 'present'}" for f in featured))

    # O-1 bridges: witness the fusion cards (skip the semantic check if the archetype ops can't be resolved).
    bridge_all = bridge_indices(made)
    bridge_fail = bridge_failures(made, bridge_ctx)
    if bridge_ctx:
        note(f"coverage bridges: {len(bridge_all)} tagged, {len(bridge_all) - len(bridge_fail)} fuse both "
             f"engines ({bridge_ctx['name_a']} x {bridge_ctx['name_b']})")
        if len(bridge_all) < bridges.MIN_BRIDGES:
            note(f"WARNING: only {len(bridge_all)} bridge card(s) survived generation "
                 f"(want {bridges.MIN_BRIDGES})")

    summary = {"before": before, "repaired": 0, "attempted": 0, "after": before,
               "featured_missing_before": [f.id for f in feat_missing],
               "bridge_fail_before": list(bridge_fail)}
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
        bdir = bridges.repair_directive(bridge_ctx["name_a"], bridge_ctx["name_b"],
                                        bridge_ctx["ops_a"], bridge_ctx["ops_b"])
        for i in bridge_fail:
            if len(pairs) >= budget:
                break
            pairs.append((i, bdir))

    remaining = max(0, budget - len(pairs))
    directives: list[str] = []
    for d in [f.directive for f in feat_missing] + plan_repairs(before, remaining):
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
        if new_card:
            made[idx]["card"] = new_card
            summary["repaired"] += 1
            gist = directive.replace("REQUIRED:", "").strip()[:64]
            note(f"coverage repair: '{old_name}' -> '{new_card.get('name', '?')}' ({gist})")
        else:
            note(f"coverage repair: '{old_name}' could not be improved; keeping original")

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
         f"debuff {after.generic_debuff_share:.0%}, scaled/X {after.scaled_or_x}")
    return summary

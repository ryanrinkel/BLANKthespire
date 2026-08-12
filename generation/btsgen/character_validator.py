"""Validators for the whole-class harness.

Two gates, mirroring the two stages of the character pipeline:

1. BlueprintValidator — plain-python checks on the harness-internal blueprint (the design
   plan). Catches a malformed plan BEFORE we spend a dozen card-generation calls on it.
2. CharacterValidator — the engine contract for the final assembled character: jsonschema
   against character.schema.json + reference integrity (starting_relic / starting_deck must
   resolve against authored AND quarantined content, since a bundle's cards are quarantined
   first) + the signature-subset rule the schema can't express. Mirrors
   ContentValidator.validate_character so harness-approved == engine-loadable.
"""
from __future__ import annotations

import json
import re

from jsonschema import Draft202012Validator

from . import paths
from .validator import CardValidator, ValidationResult

_SNAKE = re.compile(r"^[a-z0-9_]+$")
_CARD_TYPES = {"attack", "skill", "power"}
_POOL_RARITIES = {"common", "uncommon", "rare"}

# ------------------------------------------------------------- mechanic identity
# Universal deckbuilder currency: ops/statuses that can never DEFINE a class identity, no
# matter who uses them. Everything OUTSIDE these sets is identity-grade (op:fuse,
# status:armor, status:burrowed, ...) and is "owned" by a class when it appears in that
# class's authored cards and nobody else's. Born from the Frost Warden incident: a frost
# concept shipped three fuse cards because nothing flagged fuse as the Armor Dillo's.
_GENERIC_OPS = {"damage", "block", "apply_status", "draw", "gain_energy", "heal",
                "lose_hp", "add_card", "multi", "conditional", "set_flag", "from_state"}
_GENERIC_STATUSES = {"weak", "vulnerable", "frail", "strength", "dexterity", "strength_temp"}


def _card_mechanics(card: dict) -> set[str]:
    """Every op / applied status a card touches, recursively ('op:fuse', 'status:armor')."""
    out: set[str] = set()

    def walk(effects) -> None:
        for e in effects or []:
            if not isinstance(e, dict):
                continue
            op = str(e.get("op", ""))
            if op:
                out.add(f"op:{op}")
            if op == "apply_status" and e.get("status"):
                out.add(f"status:{e['status']}")
            for key in ("effects", "then", "else"):
                walk(e.get(key))

    walk(card.get("effects"))
    _up = card.get("upgrade")  # guard a non-dict 'upgrade' (a weak LLM may emit a list) — same as no upgrade
    walk(_up.get("effects") if isinstance(_up, dict) else None)
    return out


def _identity_grade(mechanics: set[str]) -> set[str]:
    return {m for m in mechanics
            if not (m.startswith("op:") and m[3:] in _GENERIC_OPS)
            and not (m.startswith("status:") and m[7:] in _GENERIC_STATUSES)}


def signature_mechanics() -> dict[str, str]:
    """mechanic -> owning class id, for every identity-grade mechanic used by exactly ONE
    authored class. Computed live from data/cards (like declared_status_ids) so promoting
    a class updates ownership; a mechanic two classes share is owned by nobody. Untagged
    cards count as a shared pseudo-class that can disown a mechanic but never own one."""
    by_class: dict[str, set[str]] = {}
    for f in paths.CARDS_DIR.glob("*.json"):
        try:
            card = json.loads(f.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(card, dict):
            continue
        ch = card.get("character")
        key = ch if isinstance(ch, str) else ""
        by_class.setdefault(key, set()).update(_identity_grade(_card_mechanics(card)))
    owner: dict[str, str] = {}
    for ch, mechs in by_class.items():
        for m in mechs:
            owner[m] = ch if m not in owner else ""
    return {m: ch for m, ch in owner.items() if ch}


def identity_overlap_warnings(cards: list[dict]) -> list[str]:
    """Class-level review flags: the new set leans on a mechanic that is the signature of
    an existing class. Advisory only (warnings, never errors) -- splashing another class's
    mechanic can be a deliberate design, so a human decides at review time."""
    owner = signature_mechanics()
    uses: dict[str, list[str]] = {}
    for card in cards:
        if not isinstance(card, dict):
            continue
        for m in _identity_grade(_card_mechanics(card)):
            if m in owner:
                uses.setdefault(m, []).append(str(card.get("id", "?")))
    out: list[str] = []
    for m, ids in sorted(uses.items()):
        kind, name = m.split(":", 1)
        out.append(
            f"{len(ids)} card(s) use the {kind} '{name}' -- the signature mechanic of "
            f"existing class '{owner[m]}': {', '.join(ids)}. Fine if the concept demands "
            f"it; otherwise re-theme onto primitives this class can own.")
    return out


_MONOTONY_STATUSES = ("vulnerable", "weak")


def debuff_monotony_warnings(cards: list[dict]) -> list[str]:
    """Set-level review flag: the generated set leans on vulnerable/weak — the failure mode
    every early generated class collapsed into (at the time this was added, 44/71 and 36/71
    of all quarantined cards applied them). Advisory, like identity overlap: a debuff-control
    concept may legitimately spam them; a human decides at review."""
    scored = [c for c in cards if isinstance(c, dict) and c.get("rarity") != "basic"]
    if len(scored) < 4:
        return []
    users = [str(c.get("id", "?")) for c in scored
             if any(f"status:{s}" in _card_mechanics(c) for s in _MONOTONY_STATUSES)]
    if len(users) * 3 <= len(scored):
        return []
    return [f"{len(users)}/{len(scored)} non-basic cards apply vulnerable/weak: "
            f"{', '.join(users)}. The class identity should come from its own engines, not "
            "generic debuff spam -- consider re-theming some onto the archetype mechanics."]


def _has_forged_scale(card: dict) -> bool:
    """True if any effect (base/upgrade, incl. trigger payloads) carries scale:"forged" (the Forge payoff)."""
    def walk(effects) -> bool:
        for e in effects or []:
            if not isinstance(e, dict):
                continue
            if str(e.get("scale", "")).strip().lower() == "forged":
                return True
            if any(walk(e.get(key)) for key in ("effects", "then", "else")):
                return True
        return False

    _up = card.get("upgrade")
    return walk(card.get("effects")) or walk(_up.get("effects") if isinstance(_up, dict) else None)


def forge_pairing_warnings(cards: list[dict]) -> list[str]:
    """Set-level Forge coupling (Phase M, gap #36) — the cross-card analogue of the per-card X-cost rule:
    `forge` income is a dead engine without a `scale:"forged"` payoff somewhere in the set, and a forged
    payoff is a dead card without income. Advisory like the other set-level checks (a human decides) —
    but a dud smith / dead blade should never survive review unremarked."""
    income = sorted({str(c.get("id", "?")) for c in cards
                     if isinstance(c, dict) and "op:forge" in _card_mechanics(c)})
    payoff = sorted({str(c.get("id", "?")) for c in cards
                     if isinstance(c, dict) and _has_forged_scale(c)})
    if income and not payoff:
        return [f"forge income with no payoff: {', '.join(income)} build the Forge counter but no card "
                "carries scale:\"forged\" to cash it — add a forged-scaled damage/block payoff or re-theme "
                "the income."]
    if payoff and not income:
        return [f"forged payoff with no income: {', '.join(payoff)} scale with Forge but nothing in the set "
                "uses the `forge` op to build it — add forge income (cards / a turn_start trigger) or drop "
                "the scale."]
    return []


def _has_blade_manipulation(card: dict) -> bool:
    """True if the card touches the signature blade itself (Phase T, decision #9): the `summon_blade` op
    (retrieval) or an `on_blade_played` trigger rider (the Parry pattern). Walks base/upgrade/nested effects."""
    def walk(effects) -> bool:
        for e in effects or []:
            if not isinstance(e, dict):
                continue
            if str(e.get("op", "")) == "summon_blade":
                return True
            if str(e.get("op", "")) == "add_trigger" and str(e.get("trigger", "")) == "on_blade_played":
                return True
            if any(walk(e.get(key)) for key in ("effects", "then", "else")):
                return True
        return False

    _up = card.get("upgrade")
    return walk(card.get("effects")) or walk(_up.get("effects") if isinstance(_up, dict) else None)


def forge_manipulation_warnings(cards: list[dict]) -> list[str]:
    """Set-level Forge texture (Phase T, decision #9) — a forge class (Forge income and/or a token blade)
    must ship AT LEAST ONE card that touches the blade itself (`summon_blade` retrieval or an `on_blade_played`
    rider). Income + a blade with no interaction plays flat. Advisory like forge_pairing_warnings — the blueprint
    prompt demands it, so the check rarely bites; but a blade-less-interaction smith rides the manifest to review."""
    is_forge = any(isinstance(c, dict) and ("op:forge" in _card_mechanics(c) or c.get("token")) for c in cards)
    if not is_forge:
        return []
    if any(isinstance(c, dict) and _has_blade_manipulation(c) for c in cards):
        return []
    return ["forge class ships no blade-manipulation card — every forge class needs ≥1 card that touches the "
            "blade itself (a `summon_blade` retrieval or an `on_blade_played` trigger power); income + a blade "
            "with no interaction plays flat. Add one, per THE FORGE / SIGNATURE-BLADE ARCHETYPE."]


# Phase S (gap #1): the `when` kinds that gate on the Balance gauge (a pole/centered-gated payoff).
_BALANCE_GATE_KINDS = ("light_ge", "dark_ge", "centered")


def _balance_income_poles(card: dict) -> set[str]:
    """The poles ({'light','dark'} subset) this card's balance_step effects push toward (base/upgrade, incl.
    trigger payloads). Empty if the card has no balance_step."""
    poles: set[str] = set()

    def walk(effects) -> None:
        for e in effects or []:
            if not isinstance(e, dict):
                continue
            if e.get("op") == "balance_step":
                p = str(e.get("pole", "")).strip().lower()
                if p in ("light", "dark"):
                    poles.add(p)
            for key in ("effects", "then", "else"):
                walk(e.get(key))

    walk(card.get("effects"))
    _up = card.get("upgrade")
    walk(_up.get("effects") if isinstance(_up, dict) else None)
    return poles


def _has_balance_gate(card: dict) -> bool:
    """True if any effect's `when` (base/upgrade, incl. trigger payloads + a trigger's fire-time when) gates on
    the Balance gauge (light_ge/dark_ge/centered) — the pole/centered payoff half of the archetype."""
    def walk(effects) -> bool:
        for e in effects or []:
            if not isinstance(e, dict):
                continue
            w = e.get("when")
            if isinstance(w, dict) and str(w.get("kind", "")).strip().lower() in _BALANCE_GATE_KINDS:
                return True
            if any(walk(e.get(key)) for key in ("effects", "then", "else")):
                return True
        return False

    _up = card.get("upgrade")
    return walk(card.get("effects")) or walk(_up.get("effects") if isinstance(_up, dict) else None)


def balance_pairing_warnings(cards: list[dict]) -> list[str]:
    """Set-level Balance coupling (Phase S, gap #1) — the balance analogue of forge_pairing_warnings. A class
    using `balance_step` must (a) have income on BOTH poles and (b) carry >= 1 pole/centered-gated payoff: a
    one-pole gauge is just Forge with extra steps, and gauge income with nothing gated on it never pays off.
    The mirror case — a Balance-gated payoff with no gauge income — is a dead gate. Advisory (a human decides)."""
    income_cards = sorted({str(c.get("id", "?")) for c in cards
                           if isinstance(c, dict) and _balance_income_poles(c)})
    gated_cards = sorted({str(c.get("id", "?")) for c in cards
                          if isinstance(c, dict) and _has_balance_gate(c)})
    if not income_cards:
        if gated_cards:
            return [f"Balance-gated payoff with no gauge: {', '.join(gated_cards)} gate on "
                    "light_ge/dark_ge/centered but nothing in the set uses `balance_step` to move the gauge — "
                    "add income on both poles or drop the gate."]
        return []
    poles: set[str] = set()
    for c in cards:
        if isinstance(c, dict):
            poles |= _balance_income_poles(c)
    out: list[str] = []
    if poles != {"light", "dark"}:
        only = next(iter(poles)) if poles else "?"
        out.append(f"one-pole Balance gauge: {', '.join(income_cards)} only push toward the {only} — a gauge "
                   "with income on ONE pole is just Forge with extra steps; add income on the other pole.")
    if not gated_cards:
        out.append(f"Balance income with no gated payoff: {', '.join(income_cards)} move the gauge but no card "
                   "gates on light_ge/dark_ge/centered to cash it — add a pole- or centered-gated payoff.")
    return out


# --- Balance REACHABILITY + payoff density (El Traficante post-mortem, 2026-08-12) -------------------
# balance_pairing_warnings checks EXISTENCE (both poles + >=1 gate); a class can pass it and still play
# dead: El Traficante shipped 14 gauge-steppers against 3 readers, ALL rare, gates at dark_ge/light_ge 5
# while a mixed-pole deck's gauge hovers at 0-3 (opposing steps cancel — the run log's observed peak was
# 3), and its `centered 2` rare was trivially always-true. These lints price the gates AGAINST the set's
# own income, the same posture as class_forge's deck-aware keystone gate. All advisory (a human decides).

# A pole power (balance_step inside a turn_start/turn_end add_trigger payload) played ~turn 2 of a ~6-turn
# fight ticks ~4 times; a reactive-trigger payload fires less predictably — price it at 2.
_BAL_TURN_TRIGGER_FIRES = 4
_BAL_REACTIVE_TRIGGER_FIRES = 2
# Card steppers a COMMITTED drafter (leaning one pole, cycling the deck) actually plays in one combat.
_BAL_COMMITTED_PLAYS = 5
# `centered N` with N >= this is ~always true: the gauge STARTS centered and mixed-pole income keeps it
# there, so the "restriction" plays as an unconditional payout (the Equilibrio failure).
_BAL_CENTERED_TRIVIAL = 2


def _balance_step_profile(card: dict) -> dict:
    """Per-pole income profile of one card: {'direct': {pole: [amounts]}, 'per_turn': {pole: total},
    'reactive': {pole: total}}. `direct` = steps that fire when the card is played (per play);
    `per_turn` = steps inside a turn_start/turn_end add_trigger payload (an engine, fires every turn);
    `reactive` = steps inside any other trigger payload. Base effects only for direct (the floor a
    drafter buys); a committed player upgrades, so the per-card direct amount is max(base, upgrade)."""
    prof = {"direct": {"light": [], "dark": []},
            "per_turn": {"light": 0, "dark": 0},
            "reactive": {"light": 0, "dark": 0}}

    def steps(effects) -> dict:
        got = {"light": 0, "dark": 0}
        for e in effects or []:
            if isinstance(e, dict) and e.get("op") == "balance_step":
                p = str(e.get("pole", "")).strip().lower()
                if p in got:
                    try:
                        got[p] += max(1, int(e.get("amount", 1) or 1))
                    except (TypeError, ValueError):
                        got[p] += 1
        return got

    def walk(effects, bucket: dict) -> None:
        direct = steps([e for e in effects or [] if isinstance(e, dict) and e.get("op") == "balance_step"])
        for p in ("light", "dark"):
            bucket[p] = max(bucket[p], direct[p])
        for e in effects or []:
            if not isinstance(e, dict):
                continue
            if e.get("op") == "add_trigger":
                trig = str(e.get("trigger", "")).strip().lower()
                payload = steps(e.get("effects"))
                key = "per_turn" if trig in ("turn_start", "turn_end") else "reactive"
                for p in ("light", "dark"):
                    prof[key][p] = max(prof[key][p], payload[p])
            for k in ("then", "else"):
                if e.get(k):
                    sub = {"light": 0, "dark": 0}
                    walk(e.get(k), sub)
                    for p in ("light", "dark"):
                        bucket[p] = max(bucket[p], sub[p])

    base = {"light": 0, "dark": 0}
    walk(card.get("effects"), base)
    up = {"light": 0, "dark": 0}
    _upgrade = card.get("upgrade")
    walk(_upgrade.get("effects") if isinstance(_upgrade, dict) else None, up)
    for p in ("light", "dark"):
        amt = max(base[p], up[p])
        if amt:
            prof["direct"][p].append(amt)
    return prof


def _balance_peaks(cards: list[dict]) -> dict:
    """The per-combat gauge peak a COMMITTED drafter can realistically reach per pole: the pole's best
    _BAL_COMMITTED_PLAYS direct card steps (one play each) + its per-turn trigger engines ticking
    _BAL_TURN_TRIGGER_FIRES times + reactive engines at _BAL_REACTIVE_TRIGGER_FIRES. Opposing income is
    NOT subtracted — committed players skip the other pole's cards — so this is the generous ceiling:
    a gate above it is dead even for the player who builds around it."""
    direct = {"light": [], "dark": []}
    per_turn = {"light": 0, "dark": 0}
    reactive = {"light": 0, "dark": 0}
    for c in cards:
        if not isinstance(c, dict):
            continue
        prof = _balance_step_profile(c)
        for p in ("light", "dark"):
            direct[p] += prof["direct"][p]
            per_turn[p] += prof["per_turn"][p]
            reactive[p] += prof["reactive"][p]
    return {p: (sum(sorted(direct[p], reverse=True)[:_BAL_COMMITTED_PLAYS])
                + per_turn[p] * _BAL_TURN_TRIGGER_FIRES
                + reactive[p] * _BAL_REACTIVE_TRIGGER_FIRES)
            for p in ("light", "dark")}


def _balance_gates(card: dict) -> list[tuple[str, int]]:
    """Every (kind, value) Balance gate in the card (base/upgrade, incl. trigger payloads)."""
    found: list[tuple[str, int]] = []

    def walk(effects) -> None:
        for e in effects or []:
            if not isinstance(e, dict):
                continue
            w = e.get("when")
            if isinstance(w, dict) and str(w.get("kind", "")).strip().lower() in _BALANCE_GATE_KINDS:
                try:
                    found.append((str(w.get("kind")).strip().lower(), int(w.get("value", 0) or 0)))
                except (TypeError, ValueError):
                    found.append((str(w.get("kind")).strip().lower(), 0))
            for key in ("effects", "then", "else"):
                walk(e.get(key))

    walk(card.get("effects"))
    _up = card.get("upgrade")
    walk(_up.get("effects") if isinstance(_up, dict) else None)
    return found


def balance_reachability_warnings(cards: list[dict], starting_ids: set | None = None) -> list[str]:
    """Price the set's Balance gates AGAINST its own gauge income (the reachability half the pairing
    check can't see). Warns on: a pole gate above the committed drafter's realistic per-combat peak; a
    `centered N` (N >= 2) gate that is trivially always-true (the gauge starts centered and mixed income
    keeps it there); and STARTING-DECK cards (basics + signatures — pass their ids as `starting_ids`)
    stepping OPPOSITE poles: the forced deck then cancels itself every combat, pinning the gauge at 0
    before the player has drafted anything. Advisory."""
    peaks = _balance_peaks(cards)
    if not any(peaks.values()) and not any(_balance_gates(c) for c in cards if isinstance(c, dict)):
        return []
    out: list[str] = []
    gate_pole = {"dark_ge": "dark", "light_ge": "light"}
    for c in cards:
        if not isinstance(c, dict):
            continue
        cid = str(c.get("id", "?"))
        for kind, value in _balance_gates(c):
            pole = gate_pole.get(kind)
            if pole is not None and value > peaks[pole]:
                out.append(f"unreachable Balance gate: {cid} gates on {kind} {value} but even a committed "
                           f"{pole}-drafter peaks at ~{peaks[pole]} per combat with this set's income — "
                           f"the payoff never fires. Lower the gate or add {pole} income.")
            elif kind == "centered" and value >= _BAL_CENTERED_TRIVIAL:
                out.append(f"trivial `centered` gate: {cid} gates on centered {value}, but the gauge STARTS "
                           "centered and mixed-pole income keeps it near 0 — the gate is ~always true and "
                           "reads as a restriction while paying out unconditionally. Use centered 0-1, or "
                           "gate on a pole instead.")
    if starting_ids:
        start_poles: dict[str, set[str]] = {}
        for c in cards:
            if isinstance(c, dict) and str(c.get("id", "")) in starting_ids:
                prof = _balance_step_profile(c)
                poles = {p for p in ("light", "dark")
                         if prof["direct"][p] or prof["per_turn"][p] or prof["reactive"][p]}
                if poles:
                    start_poles[str(c.get("id"))] = poles
        stepped = set().union(*start_poles.values()) if start_poles else set()
        if stepped == {"light", "dark"}:
            names = ", ".join(f"{cid} ({'/'.join(sorted(ps))})" for cid, ps in sorted(start_poles.items()))
            out.append(f"opposing steppers in the STARTING deck: {names} — the forced starting cards "
                       "cancel each other every combat, pinning the gauge at 0 before any drafting. "
                       "Starting-deck cards may step toward at most ONE pole; let drafted cards carry "
                       "the other.")
    return out


def balance_payoff_density_warnings(cards: list[dict]) -> list[str]:
    """The reader:income ratio + rarity spread of the Balance payoffs. El Traficante shipped 14 steppers
    against 3 readers, ALL rare — the engine ran all game and paid out only if a rare was drafted. Warn
    when readers < 1 per 4 income cards, and when no reader sits below rare. Advisory."""
    income = [c for c in cards if isinstance(c, dict) and _balance_income_poles(c)]
    readers = [c for c in cards if isinstance(c, dict) and _has_balance_gate(c)]
    if not income:
        return []
    out: list[str] = []
    if readers and len(readers) * 4 < len(income):
        out.append(f"Balance payoff density: {len(income)} cards feed the gauge but only {len(readers)} "
                   f"read it ({', '.join(sorted(str(c.get('id', '?')) for c in readers))}) — most of the "
                   "engine's work goes unread. Aim for >=1 reader per ~4 income cards (convert an income "
                   "card's bonus into a pole-gated payoff).")
    if readers and all(str(c.get("rarity", "")).strip().lower() == "rare" for c in readers):
        out.append("all Balance readers are RARE: the gauge only pays off if a rare is drafted, so most "
                   "runs never cash it. Put at least one pole- or centered-gated payoff at uncommon "
                   "(or common).")
    return out


def _has_grow(card: dict) -> bool:
    """True if any of the card's effects (base or upgrade) carries a `grow` (Rampage) damage step."""
    for lst in (card.get("effects") or [], (card.get("upgrade") or {}).get("effects") or []):
        for e in lst:
            if isinstance(e, dict) and e.get("op") == "damage" and isinstance(e.get("grow"), int) and e.get("grow"):
                return True
    return False


def rampage_grow_warnings(cards: list[dict]) -> list[str]:
    """Set-level Rampage guidance (Phase U, gap #23): a `grow` attack is a build-around IDENTITY card, not
    wallpaper. More than two grow cards in a class dilutes the "commit to ONE signature weapon" fantasy and
    stacks multiple independent scaling engines. Advisory (a human decides)."""
    grow_cards = sorted({str(c.get("id", "?")) for c in cards if isinstance(c, dict) and _has_grow(c)})
    if len(grow_cards) > 2:
        return [f"too many Rampage cards: {', '.join(grow_cards)} each carry `grow` — a growing signature "
                "attack is an identity card; keep it to 1-2 per class (commit to ONE weapon, don't wallpaper)."]
    return []


def _has_purge(card: dict) -> bool:
    """True if any of the card's effects (base or upgrade) carries a deck-thinning purge op — the self-purge flag
    `purge` (Phase W, gap #19) or the choose-a-card op `purge_card` (Phase Z, gap #19 choose). Both permanently
    thin the run deck, so both count toward the per-class 1-3 guidance."""
    for lst in (card.get("effects") or [], (card.get("upgrade") or {}).get("effects") or []):
        for e in lst:
            if isinstance(e, dict) and e.get("op") in ("purge", "purge_card"):
                return True
    return False


def purge_warnings(cards: list[dict]) -> list[str]:
    """Set-level self-purge guidance (Phase W, gap #19): `purge` thins your RUN deck permanently — a strong,
    committal one-shot, not wallpaper. More than three purge cards in a class turns deck-thinning into the whole
    identity (and risks a player thinning below the fun floor). The sacred rare/merchant FLOORS are pool-level
    (drafting), not run-deck, so purge can't actually break them (the per-card BASIC ban is enforced in the
    engine validator) — this is a design nicety. Advisory (a human decides)."""
    purge_cards = sorted({str(c.get("id", "?")) for c in cards if isinstance(c, dict) and _has_purge(c)})
    if len(purge_cards) > 3:
        return [f"too many Purge cards: {', '.join(purge_cards)} each carry `purge`/`purge_card` — permanent "
                "deck-thinning is a committal build-around; keep it to 1-3 per class so it sharpens the deck rather "
                "than defining it."]
    return []


def _has_corruption(card: dict) -> bool:
    """True if any of the card's effects (base or upgrade) carries the `corruption` flag-op (Phase AB, gap #20)."""
    for lst in (card.get("effects") or [], (card.get("upgrade") or {}).get("effects") or []):
        for e in lst:
            if isinstance(e, dict) and e.get("op") == "corruption":
                return True
    return False


def _card_has_op(card: dict, ops: set[str]) -> bool:
    """True if any of the card's effects (base or upgrade, incl. nested trigger payloads) uses one of `ops`."""
    def walk(lst):
        for e in lst or []:
            if not isinstance(e, dict):
                continue
            if e.get("op") in ops:
                return True
            if e.get("op") == "add_trigger" and walk(e.get("effects")):
                return True
        return False
    return walk(card.get("effects")) or walk((card.get("upgrade") or {}).get("effects"))


def summon_support_warnings(cards: list[dict]) -> list[str]:
    """Set-level summon-support pairing (Phase AC, gap #2): a class that ships `heal_summon` / `shield_summon`
    cards but NO `summon` op has nothing to heal/shield — the medic ops would always no-op. Advisory (a human
    decides), mirroring the summon-needs-attack guidance in the blueprint."""
    medic = sorted({str(c.get("id", "?")) for c in cards
                    if isinstance(c, dict) and _card_has_op(c, {"heal_summon", "shield_summon"})})
    has_summon = any(isinstance(c, dict) and _card_has_op(c, {"summon"}) for c in cards)
    if medic and not has_summon:
        return [f"summon-support cards with no summon: {', '.join(medic)} heal/shield a summon, but no card in "
                "the class has a `summon` op to bring the minion out — the medic ops will always no-op. Add a "
                "`summon` card, or drop the summon-support."]
    return []


def corruption_warnings(cards: list[dict]) -> list[str]:
    """Set-level Corruption guidance (Phase AB, gap #20): `corruption` grants a BINARY per-combat power (your
    Skills cost 0 + Exhaust). A class needs at most ONE card that grants it — a second is dead redundancy (the
    power is already on; re-granting does nothing). Advisory (a human decides), like purge_warnings."""
    corruption_cards = sorted({str(c.get("id", "?")) for c in cards if isinstance(c, dict) and _has_corruption(c)})
    if len(corruption_cards) > 1:
        return [f"more than one Corruption card: {', '.join(corruption_cards)} each grant `corruption` — it is a "
                "binary per-combat power, so a second grant is dead; keep it to one per class."]
    return []


def blade_empower_warnings(cards: list[dict]) -> list[str]:
    """Set-level Blade-Empower pairing (Phase AF, gap #41): `blade_empower` multiplies the forge class's signature
    blade — it is dead in a class with no `forge` income (no blade to empower). A class shipping blade_empower must
    have forge income (a `forge` op somewhere). Advisory, mirroring forge_pairing_warnings."""
    empower = sorted({str(c.get("id", "?")) for c in cards
                      if isinstance(c, dict) and _card_has_op(c, {"blade_empower"})})
    has_forge = any(isinstance(c, dict) and _card_has_op(c, {"forge"}) for c in cards)
    if empower and not has_forge:
        return [f"blade_empower with no forge income: {', '.join(empower)} multiply the signature blade, but no card "
                "in the class has a `forge` op to build/summon it — the empower is dead. Add forge income, or drop it."]
    return []


def _transform_target(card: dict) -> str | None:
    """The card_id a card's transform_card effect (base or upgrade) names, or None (Phase AH, gaps #35/#38).
    A card has at most one transform_card (per-card validator + ForgedCards.Validate enforce that)."""
    for lst in (card.get("effects") or [], (card.get("upgrade") or {}).get("effects") or []):
        for e in lst:
            if isinstance(e, dict) and e.get("op") == "transform_card" and str(e.get("card_id", "")).strip():
                return str(e["card_id"]).strip()
    return None


def _has_graft(card: dict) -> bool:
    """Does a card carry a graft_card effect (base or upgrade)? (Phase AI, gap #7 — the choose form of
    transform_card; counts toward the same transform-family cap.)"""
    for lst in (card.get("effects") or [], (card.get("upgrade") or {}).get("effects") or []):
        for e in lst:
            if isinstance(e, dict) and e.get("op") == "graft_card" and str(e.get("card_id", "")).strip():
                return True
    return False


def transform_warnings(cards: list[dict]) -> list[str]:
    """Set-level transform-family guidance (Phase AH, gaps #35/#38 + Phase AI, gap #7): cross-card rules the
    per-card validator can't see (it has only card ids, not sibling bodies):
      1. NO TRANSFORM CHAINS — a `transform_card` A→B is allowed to target a card B that ITSELF transforms only
         if B swaps back to A (a two-card mode-swap A↔B). A→B→C (B transforms into a THIRD card) is a chain and
         is flagged (the runtime refuses it — ResolveTransformTarget returns null — so the transform would be a
         silent dead op). This is the set-level half of the chain guard; the mode-swap pair is explicitly OK.
         (graft_card doesn't create chains — it transforms a runtime-PICKED card, not itself — so it's exempt
         from the chain check.)
      2. AT MOST 3 transform-family cards per class — run-permanent card rewriting (transform_card self-rewrite +
         graft_card choose-a-card transform) is a committal build-around; more than three turns the class into a
         shapeshifting gimmick (mirrors purge_warnings, which counts purge + purge_card together). Advisory.
    Returns a warning line per issue (empty = clean)."""
    out: list[str] = []
    by_id = {str(c.get("id", "")): c for c in cards if isinstance(c, dict)}
    xform_ids = sorted(cid for cid, c in by_id.items() if _transform_target(c))
    # (1) chain check (transform_card only): for each A→B, if B also transforms (B→C), it's a mode-swap only when C == A.
    for a_id in xform_ids:
        b_id = _transform_target(by_id[a_id])
        b_card = by_id.get(b_id)
        if b_card is None:
            continue  # unknown target — the per-card validator's ref-integrity already errors on it
        c_id = _transform_target(b_card)
        if c_id is not None and c_id != a_id:
            out.append(f"transform chain: '{a_id}' transforms into '{b_id}', which itself transforms into "
                       f"'{c_id}' — a target may carry transform_card only if it swaps BACK ('{a_id}'). Break the "
                       "chain (a two-card mode-swap A↔B is fine; A→B→C is not — the runtime refuses it as a dead op).")
    # (2) too-many cap — transform_card + graft_card together (the run-permanent card-rewrite family).
    family_ids = sorted({*xform_ids, *(cid for cid, c in by_id.items() if _has_graft(c))})
    if len(family_ids) > 3:
        out.append(f"too many transform cards: {', '.join(family_ids)} each carry `transform_card`/`graft_card` — a "
                   "run-permanent card rewrite is a committal build-around; keep it to 1-3 per class so it sharpens "
                   "the deck rather than defining it.")
    return out


def _card_tags(card: dict) -> set[str]:
    """The lowercase declarative tags a card carries (Phase AE, gap #25)."""
    return {str(t).strip().lower() for t in (card.get("tags") or []) if str(t).strip()}


def _payoff_tags(card: dict) -> set[str]:
    """The tags this card's tag_cards_owned effects reference (base or upgrade)."""
    out: set[str] = set()
    for lst in (card.get("effects") or [], (card.get("upgrade") or {}).get("effects") or []):
        for e in lst:
            if isinstance(e, dict) and str(e.get("scale", "")).lower() == "tag_cards_owned" and e.get("tag"):
                out.add(str(e["tag"]).strip().lower())
    return out


def tag_synergy_warnings(cards: list[dict]) -> list[str]:
    """Set-level tag-synergy check (Phase AE, gap #25): a `tag_cards_owned` payoff that references a tag present
    on FEWER THAN TWO of the class's cards is a near-dead payoff (it scales off almost nothing) — the tag family
    must be built out. Cross-card, so it can't live in the per-card validator. Advisory (a human decides)."""
    tag_counts: dict[str, int] = {}
    for c in cards:
        if isinstance(c, dict):
            for t in _card_tags(c):
                tag_counts[t] = tag_counts.get(t, 0) + 1
    referenced: set[str] = set()
    for c in cards:
        if isinstance(c, dict):
            referenced |= _payoff_tags(c)
    thin = sorted(t for t in referenced if tag_counts.get(t, 0) < 2)
    if thin:
        return [f"tag_cards_owned payoff references tag(s) {', '.join(repr(t) for t in thin)} present on fewer than "
                "2 cards — tag 3-5 cards of the class with that slug so the payoff isn't dead."]
    return []


def combo_loop_warnings(cards: list[dict]) -> list[str]:
    """Set-level loop discipline: a TWO-card free loop (A adds B to hand, B adds A to hand,
    combined net cost <= 1 per round-trip, neither exhausts) is the one-card engine split in
    half -- the player rule says infinite combos take 3+ cards or a real price. Three-card-or
    -wider cycles are deliberately NOT flagged (that's the earned version). Advisory, like
    identity overlap: a human decides at review."""
    by_id = {c["id"]: c for c in cards
             if isinstance(c, dict) and isinstance(c.get("id"), str)}
    out: list[str] = []
    seen: set[tuple[str, str]] = set()
    for aid, a in by_id.items():
        for bid in CardValidator.hand_adds(a):
            if bid == aid or bid not in by_id:
                continue  # self-loops are the per-card check's job
            b = by_id[bid]
            if aid not in CardValidator.hand_adds(b):
                continue
            pair = tuple(sorted((aid, bid)))
            if pair in seen or a.get("exhaust") or b.get("exhaust"):
                continue
            seen.add(pair)
            net = CardValidator.net_energy_cost(a) + CardValidator.net_energy_cost(b)
            if net <= 1:
                out.append(
                    f"two-card free loop: '{pair[0]}' and '{pair[1]}' re-add each other to "
                    f"hand at net cost {net} per round-trip -- infinite combos should take "
                    "3+ cards or a real price (exhaust, HP, >=2 energy); widen or price the "
                    "loop.")
    return out


class BlueprintValidator:
    """Shape + design-rule checks for the blueprint (stage-1 output). No LLM, no engine."""

    def __init__(self) -> None:
        self.known_characters = CardValidator._ids_in(paths.CHARACTERS_DIR) | \
            CardValidator._ids_in(paths.GENERATED_CHARACTERS_DIR)

    def validate(self, bp) -> ValidationResult:
        errors: list[str] = []
        warnings: list[str] = []
        if not isinstance(bp, dict):
            return ValidationResult(ok=False, errors=["blueprint is not a JSON object"])

        # -- identity ------------------------------------------------------
        bid = bp.get("id")
        if not isinstance(bid, str) or not _SNAKE.match(bid or ""):
            errors.append("'id' must be a snake_case string")
        name = bp.get("name")
        if not isinstance(name, str) or not (1 <= len(name) <= 32):
            errors.append("'name' must be a 1..32 char string")
        desc = bp.get("description")
        if not isinstance(desc, str) or not (1 <= len(desc) <= 200):
            errors.append("'description' must be a 1..200 char string")

        hp = bp.get("max_hp")
        if not isinstance(hp, int) or isinstance(hp, bool) or not (40 <= hp <= 120):
            errors.append("'max_hp' must be an integer in 40..120")
        elif not (60 <= hp <= 95):
            warnings.append(f"max_hp {hp} is outside the usual 60..95 band")
        en = bp.get("max_energy", 3)
        if not isinstance(en, int) or isinstance(en, bool) or not (1 <= en <= 6):
            errors.append("'max_energy' must be an integer in 1..6")
        elif en != 3:
            warnings.append(f"max_energy {en} != 3 (every existing class starts at 3)")

        # -- archetypes ------------------------------------------------------
        arch_ids: list[str] = []
        arch_kinds: list[str] = []
        archetypes = bp.get("archetypes")
        if not isinstance(archetypes, list) or len(archetypes) != 2:
            errors.append("'archetypes' must be a list of exactly 2")
        else:
            for i, a in enumerate(archetypes):
                if not isinstance(a, dict):
                    errors.append(f"archetypes[{i}] must be an object")
                    continue
                aid = a.get("id")
                if not isinstance(aid, str) or not _SNAKE.match(aid or ""):
                    errors.append(f"archetypes[{i}].id must be snake_case")
                else:
                    arch_ids.append(aid)
                if not isinstance(a.get("name"), str) or not a.get("name"):
                    errors.append(f"archetypes[{i}].name must be a non-empty string")
                if not isinstance(a.get("description"), str) or not a.get("description"):
                    errors.append(f"archetypes[{i}].description must be a non-empty string")
                kind = a.get("kind")
                if kind not in ("novel", "classic"):
                    errors.append(f"archetypes[{i}].kind must be 'novel' or 'classic'")
                else:
                    arch_kinds.append(kind)
            if len(arch_ids) == 2 and arch_ids[0] == arch_ids[1]:
                errors.append("the two archetype ids must differ")
            if len(arch_kinds) == 2 and arch_kinds[0] == arch_kinds[1]:
                errors.append("archetype kinds must differ: exactly one 'novel' and one 'classic' "
                              "(the class fantasy rule)")

        # -- relic brief ----------------------------------------------------
        relic = bp.get("relic")
        if not isinstance(relic, dict) or not isinstance(relic.get("theme"), str) or not relic.get("theme"):
            errors.append("'relic' must be an object with a non-empty 'theme'")

        # -- card plan ------------------------------------------------------
        cards = bp.get("cards")
        if not isinstance(cards, list) or not (4 <= len(cards) <= 24):
            errors.append("'cards' must be a list of 4..24 design briefs")
            return ValidationResult(ok=not errors, errors=errors, warnings=warnings)

        roles = {"basic_attack": 0, "basic_skill": 0, "signature": 0, "signature_blade": 0, "pool": 0}
        per_arch = {a: 0 for a in arch_ids}
        deck_total = 0
        for i, c in enumerate(cards):
            if not isinstance(c, dict):
                errors.append(f"cards[{i}] must be an object")
                continue
            role = c.get("role")
            if role not in roles:
                errors.append(f"cards[{i}].role must be one of {sorted(roles)}")
                continue
            roles[role] += 1
            if not isinstance(c.get("name_hint"), str) or not c.get("name_hint"):
                errors.append(f"cards[{i}].name_hint must be a non-empty string")
            if not isinstance(c.get("theme"), str) or not c.get("theme"):
                errors.append(f"cards[{i}].theme must be a non-empty string")
            if c.get("type") not in _CARD_TYPES:
                errors.append(f"cards[{i}].type must be one of {sorted(_CARD_TYPES)}")
            cost = c.get("cost")
            if not isinstance(cost, int) or isinstance(cost, bool) or not (-1 <= cost <= 3):
                errors.append(f"cards[{i}].cost must be an integer in -1..3 (-1 = X-cost)")
            dc = c.get("deck_count")
            if not isinstance(dc, int) or isinstance(dc, bool) or dc < 0:
                errors.append(f"cards[{i}].deck_count must be an integer >= 0")
                dc = 0
            deck_total += dc
            arch = c.get("archetype")
            rarity = c.get("rarity")
            if role in ("basic_attack", "basic_skill"):
                if rarity != "basic":
                    errors.append(f"cards[{i}] ({role}) must have rarity 'basic'")
                if not (3 <= dc <= 5):
                    errors.append(f"cards[{i}] ({role}) deck_count must be 3..5")
            elif role == "signature":
                # A signature is a basic starter, one copy, in the starting deck.
                if rarity != "basic":
                    errors.append(f"cards[{i}] ({role}) must have rarity 'basic'")
                if dc != 1:
                    errors.append(f"cards[{i}] ({role}) deck_count must be 1")
            elif role == "signature_blade":
                # Phase T: the forge class's growing weapon is a TOKEN, summoned to hand on the first Forge of
                # combat — NOT in the starting deck (deck_count 0). It is synthesized (only name/theme are used).
                if rarity != "token":
                    errors.append(f"cards[{i}] (signature_blade) must have rarity 'token' "
                                  "(the blade is a summoned token, not a deck card)")
                if dc != 0:
                    errors.append(f"cards[{i}] (signature_blade) deck_count must be 0 "
                                  "(the blade is summoned on your first Forge, not seeded in the deck)")
            else:  # pool
                if rarity not in _POOL_RARITIES:
                    errors.append(f"cards[{i}] (pool) rarity must be one of {sorted(_POOL_RARITIES)}")
                if dc != 0:
                    errors.append(f"cards[{i}] (pool) deck_count must be 0 (pool cards are rewards)")
                if arch not in arch_ids:
                    errors.append(f"cards[{i}] (pool) archetype must be one of the class archetypes")
            if arch in per_arch:
                per_arch[arch] += 1

        if roles["basic_attack"] != 1:
            errors.append("need exactly 1 basic_attack")
        if roles["basic_skill"] != 1:
            errors.append("need exactly 1 basic_skill")
        if roles["signature"] not in (1, 2):
            errors.append("need 1 or 2 signature cards")
        if roles["signature_blade"] > 1:
            errors.append("at most 1 signature_blade (the forge class's single growing weapon)")
        if roles["pool"] < 2:
            errors.append("need at least 2 pool cards")
        if not errors and deck_total != 10:
            errors.append(f"starting deck totals {deck_total} cards; must be exactly 10 "
                          f"(every class starts with 10 — the class_forge path normalizes the basics to hit it)")
        for a, n in per_arch.items():
            if n < 2:
                warnings.append(f"archetype '{a}' has only {n} card(s) in the plan")
        if isinstance(bp.get("id"), str) and bp["id"] in self.known_characters:
            warnings.append(f"class id '{bp['id']}' already exists; it will be renamed")

        return ValidationResult(ok=not errors, errors=errors, warnings=warnings)


class CharacterValidator:
    """The engine contract for the assembled character (stage-2 output)."""

    def __init__(self) -> None:
        paths.assert_character_project_present()
        schema = json.loads(paths.CHARACTER_SCHEMA.read_text())
        self._schema_validator = Draft202012Validator(schema)
        # authored + quarantined both resolve: a bundle's cards/relic sit in quarantine
        # until the WHOLE bundle is approved together.
        self.known_cards = CardValidator._ids_in(paths.CARDS_DIR) | CardValidator._ids_in(paths.GENERATED_DIR)
        self.known_relics = CardValidator._ids_in(paths.RELICS_DIR) | CardValidator._ids_in(paths.GENERATED_RELICS_DIR)
        self.known_characters = CardValidator._ids_in(paths.CHARACTERS_DIR) | \
            CardValidator._ids_in(paths.GENERATED_CHARACTERS_DIR)

    def validate(self, ch) -> ValidationResult:
        errors: list[str] = []
        for e in sorted(self._schema_validator.iter_errors(ch), key=lambda e: list(e.path)):
            loc = "/".join(str(p) for p in e.path) or "(root)"
            errors.append(f"schema [{loc}]: {e.message}")
        if not isinstance(ch, dict):
            return ValidationResult(ok=False, errors=errors)

        relic = ch.get("starting_relic")
        if isinstance(relic, str) and relic not in self.known_relics:
            errors.append(f"starting_relic references unknown relic '{relic}'")
        deck = ch.get("starting_deck") or []
        if isinstance(deck, list):
            for i, cid in enumerate(deck):
                if isinstance(cid, str) and cid not in self.known_cards:
                    errors.append(f"starting_deck[{i}] references unknown card '{cid}'")
            for i, cid in enumerate(ch.get("signature_cards") or []):
                if isinstance(cid, str) and cid not in deck:
                    errors.append(f"signature_cards[{i}] '{cid}' is not in starting_deck")
        if errors:
            return ValidationResult(ok=False, errors=errors)

        warnings: list[str] = []
        hp = ch.get("max_hp", 0)
        if not (60 <= hp <= 95):
            warnings.append(f"max_hp {hp} is outside the usual 60..95 band")
        if ch.get("max_energy", 3) != 3:
            warnings.append(f"max_energy {ch.get('max_energy')} != 3")
        if len(deck) != 10:
            warnings.append(f"starting deck has {len(deck)} cards (every class starts with exactly 10)")
        return ValidationResult(ok=True, warnings=warnings)

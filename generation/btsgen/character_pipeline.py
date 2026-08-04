"""Orchestrate a WHOLE CLASS: blueprint -> cards -> starter relic -> assembled character.

Two-stage design (see character_contract): one blueprint call plans the class; then every
card/relic is generated through the EXISTING single-artifact pipelines (each with its own
validate -> repair-once loop) with the blueprint as design context. The assembled character
is validated against the engine contract and quarantined as a BUNDLE:

    data/generated/cards/<card>.json       (one per set card, tagged character:<class_id>)
    data/generated/relics/<relic>.json     (the starter relic, tier/pool "starter")
    data/generated/characters/<id>.json    (the CharacterData)
    data/generated/characters/<id>.meta.json  (the bundle manifest: card ids, relic id,
                                               warnings rollup -- the review CLI and the
                                               in-game loader both read this)

Failure policy: a failed POOL card is skipped with a warning (the class still works);
a failed basic/signature/relic gets ONE full regeneration, then the whole bundle aborts
and every artifact quarantined by this run is deleted (no orphans).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import character_contract, contract, paths, relic_contract
from .character_contract import Brief
from .character_validator import (BlueprintValidator, CharacterValidator,
                                  balance_pairing_warnings, blade_empower_warnings, combo_loop_warnings,
                                  debuff_monotony_warnings,
                                  corruption_warnings, forge_manipulation_warnings, forge_pairing_warnings,
                                  identity_overlap_warnings, purge_warnings, rampage_grow_warnings,
                                  summon_support_warnings, tag_synergy_warnings, transform_warnings)
from .generator import AnthropicGenerator, extract_card_json
from .pipeline import _unique_id, generate_card
from .relic_pipeline import generate_relic
from .relic_validator import RelicValidator
from .validator import CardValidator

BLUEPRINT_MAX_TOKENS = 16000  # a whole-class plan (plus thinking) far exceeds a single card


@dataclass
class BundleResult:
    ok: bool
    character: dict | None = None
    blueprint: dict | None = None
    card_ids: list[str] = field(default_factory=list)
    relic_id: str | None = None
    quarantine_path: str | None = None
    skipped: list[str] = field(default_factory=list)   # pool briefs dropped after repair failed
    warnings: dict = field(default_factory=dict)        # artifact id -> [warning, ...]
    log: list[str] = field(default_factory=list)


def generate_character(brief: Brief, model: str | None = None, fake: bool = False,
                       on_event=None) -> BundleResult:
    """The whole-class pipeline. `fake=True` swaps in the offline FakeGenerator (no key/cost)."""
    paths.assert_character_project_present()
    res = BundleResult(ok=False)
    created: list[Path] = []  # everything this run quarantined, for abort cleanup

    def note(msg: str) -> None:
        res.log.append(msg)
        if on_event:
            on_event(msg)

    def gen_for(contract_mod, max_tokens: int = 4000):
        if fake:
            from .fakes import FakeGenerator
            return FakeGenerator(contract_mod)
        return AnthropicGenerator(model=model, contract_mod=contract_mod, max_tokens=max_tokens)

    def abort(msg: str) -> BundleResult:
        note(f"ABORT: {msg}")
        for p in created:
            p.unlink(missing_ok=True)
            Path(str(p).replace(".json", ".meta.json")).unlink(missing_ok=True)
        if created:
            note(f"cleaned up {len(created)} quarantined artifact(s) from the aborted bundle")
        return res

    # ---- stage 1: the blueprint -------------------------------------------
    note("designing the class blueprint...")
    bp_gen = gen_for(character_contract, max_tokens=BLUEPRINT_MAX_TOKENS)
    bp_validator = BlueprintValidator()
    text, messages = bp_gen.first_attempt(brief)
    bp, errors = _extract(text)
    if bp is not None:
        vr = bp_validator.validate(bp)
        errors = vr.errors
    if errors:
        note(f"blueprint attempt 1: {len(errors)} error(s); repairing")
        text, messages = bp_gen.repair(messages, text, errors)
        bp, errors = _extract(text)
        if bp is not None:
            vr = bp_validator.validate(bp)
            errors = vr.errors
        if errors:
            return abort("blueprint still invalid after repair: " + "; ".join(errors[:5]))
    res.blueprint = bp
    if vr.warnings:
        res.warnings["blueprint"] = vr.warnings
    class_id = _unique_class_id(str(bp["id"]))
    if class_id != bp["id"]:
        note(f"class id '{bp['id']}' taken; renamed to '{class_id}'")
    note(f"blueprint OK: {bp['name']} ({class_id}) -- {len(bp['cards'])} cards planned")

    # ---- stage 2: the card set ----------------------------------------------
    card_gen = gen_for(contract)
    card_validator = CardValidator()
    made: list[dict] = []       # plan entry + actual generated card, in plan order
    for i, plan in enumerate(bp["cards"]):
        label = f"{plan['role']}" + (f"/{plan['archetype']}" if plan.get("archetype") else "")
        # Basics are never generated: every class starts with the LITERAL Strike/Defend
        # (StS rule), so they are synthesized verbatim -- no model drift, no spent calls.
        if plan["role"] in ("basic_attack", "basic_skill"):
            note(f"card {i + 1}/{len(bp['cards'])} ({label}): literal "
                 f"{'Strike' if plan['role'] == 'basic_attack' else 'Defend'} (synthesized)")
            card = _synthesize_basic(plan, class_id, card_validator, note, created)
            if card is None:
                return abort(f"synthesized basic for role '{plan['role']}' failed validation")
            made.append({"plan": plan, "card": card})
            res.card_ids.append(card["id"])
            continue
        note(f"card {i + 1}/{len(bp['cards'])} ({label}): {plan['name_hint']}...")
        card = _generate_set_card(plan, bp, class_id, made, card_gen, card_validator, note, created, res.warnings)
        if card is None and plan["role"] != "pool":
            note("  essential card failed; one full retry...")
            card = _generate_set_card(plan, bp, class_id, made, card_gen, card_validator, note, created, res.warnings)
            if card is None:
                return abort(f"essential card '{plan['name_hint']}' failed twice")
        if card is None:
            res.skipped.append(plan["name_hint"])
            note(f"  pool card '{plan['name_hint']}' failed twice; skipped")
            continue
        made.append({"plan": plan, "card": card})
        res.card_ids.append(card["id"])

    # The set as a whole must not lean on another class's signature mechanic (advisory:
    # the warning rides the bundle manifest into the review CLI; a human decides).
    idw = identity_overlap_warnings([m["card"] for m in made])
    if idw:
        res.warnings["identity"] = idw
        for w in idw:
            note("  IDENTITY WARN " + w)
    # Same advisory treatment for the vulnerable/weak-spam failure mode: flag it on the
    # bundle manifest so the review CLI surfaces it, but let a human decide.
    mw = debuff_monotony_warnings([m["card"] for m in made])
    if mw:
        res.warnings["monotony"] = mw
        for w in mw:
            note("  MONOTONY WARN " + w)
    # Loop discipline, pair case: two set cards that re-add each other to hand for free
    # (the one-card self-copy is flagged per-card by CardValidator.loop_warnings).
    lw = combo_loop_warnings([m["card"] for m in made])
    if lw:
        res.warnings["loops"] = lw
        for w in lw:
            note("  LOOP WARN " + w)
    # Phase M (gap #36): Forge coupling — forge income must meet a scale:"forged" payoff in the same set
    # (the cross-card analogue of the X-cost rule; a dud smith / dead blade rides the manifest to review).
    fw = forge_pairing_warnings([m["card"] for m in made])
    if fw:
        res.warnings["forge"] = fw
        for w in fw:
            note("  FORGE WARN " + w)
    # Phase T (decision #9): a forge class must ship ≥1 blade-manipulation card (summon_blade / on_blade_played).
    mw = forge_manipulation_warnings([m["card"] for m in made])
    if mw:
        res.warnings["forge_manipulation"] = mw
        for w in mw:
            note("  FORGE WARN " + w)
    # Phase S (gap #1): Balance coupling — a balance class needs income on BOTH poles + a pole/centered-gated
    # payoff (a one-pole gauge is just Forge with extra steps). Same advisory treatment as the forge check.
    bw = balance_pairing_warnings([m["card"] for m in made])
    if bw:
        res.warnings["balance"] = bw
        for w in bw:
            note("  BALANCE WARN " + w)
    # Phase U (gap #23): Rampage identity — a growing signature attack is a build-around, not wallpaper;
    # warn if a class stacks more than two `grow` cards. Same advisory treatment.
    rw = rampage_grow_warnings([m["card"] for m in made])
    if rw:
        res.warnings["rampage"] = rw
        for w in rw:
            note("  RAMPAGE WARN " + w)
    # Phase W (gap #19): self-purge identity — permanent deck-thinning is a committal build-around; warn if a
    # class stacks more than three `purge` cards. Same advisory treatment.
    pw = purge_warnings([m["card"] for m in made])
    if pw:
        res.warnings["purge"] = pw
        for w in pw:
            note("  PURGE WARN " + w)
    # Phase AB (gap #20): corruption is a binary per-combat power — a class needs at most ONE card that grants it
    # (a second is dead noise). Advisory, same treatment.
    cw = corruption_warnings([m["card"] for m in made])
    if cw:
        res.warnings["corruption"] = cw
        for w in cw:
            note("  CORRUPTION WARN " + w)
    # Phase AC (gap #2): a class with heal_summon/shield_summon but no summon op — the medic ops always no-op.
    sw = summon_support_warnings([m["card"] for m in made])
    if sw:
        res.warnings["summon_support"] = sw
        for w in sw:
            note("  SUMMON-SUPPORT WARN " + w)
    # Phase AE (gap #25): a tag_cards_owned payoff referencing a tag on <2 cards is near-dead.
    tw = tag_synergy_warnings([m["card"] for m in made])
    if tw:
        res.warnings["tag_synergy"] = tw
        for w in tw:
            note("  TAG-SYNERGY WARN " + w)
    # Phase AF (gap #41): blade_empower with no forge income is dead (no blade to empower).
    bew = blade_empower_warnings([m["card"] for m in made])
    if bew:
        res.warnings["blade_empower"] = bew
        for w in bew:
            note("  BLADE-EMPOWER WARN " + w)
    # Phase AH (gaps #35/#38): transform chains (A→B→C — dead ops the runtime refuses) + the >3-per-class cap.
    xw = transform_warnings([m["card"] for m in made])
    if xw:
        res.warnings["transform"] = xw
        for w in xw:
            note("  TRANSFORM WARN " + w)

    # ---- stage 3: the starter relic (last, so it can ride the final set) ----
    note("forging the starter relic...")
    relic = _generate_starter_relic(bp, class_id, made, gen_for(relic_contract), note, created, res.warnings)
    if relic is None:
        note("  starter relic failed; one full retry...")
        relic = _generate_starter_relic(bp, class_id, made, gen_for(relic_contract), note, created, res.warnings)
        if relic is None:
            return abort("starter relic failed twice")
    res.relic_id = relic["id"]

    # ---- stage 4: assemble + validate + quarantine the character ------------
    deck: list[str] = []
    signatures: list[str] = []
    for m in made:
        deck += [m["card"]["id"]] * int(m["plan"].get("deck_count", 0))
        if m["plan"]["role"] == "signature":
            signatures.append(m["card"]["id"])
    character = {
        "id": class_id,
        "name": bp["name"],
        "description": bp["description"],
        "max_hp": bp["max_hp"],
        "max_energy": bp.get("max_energy", 3),
        "starting_relic": relic["id"],
        "starting_deck": deck,
        "signature_cards": signatures,
        "source": "llm",
    }
    vr = CharacterValidator().validate(character)  # fresh: sees the just-quarantined cards/relic
    if not vr.ok:
        return abort("assembled character invalid: " + "; ".join(vr.errors[:5]))
    if vr.warnings:
        res.warnings[class_id] = vr.warnings

    paths.GENERATED_CHARACTERS_DIR.mkdir(parents=True, exist_ok=True)
    char_path = paths.GENERATED_CHARACTERS_DIR / f"{class_id}.json"
    char_path.write_text(json.dumps(character, indent=2) + "\n")
    meta = {
        "id": class_id,
        "source": "llm",
        "model": getattr(bp_gen, "model", "?"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "concept": brief.concept,
        "archetypes": [a["id"] for a in bp["archetypes"]],
        "skin": bp.get("skin") or {},   # flavor facets + imagery (staged front-end); {} for concept-mode forges
        "cards": res.card_ids,
        "relic": relic["id"],
        "skipped": res.skipped,
        "warnings": res.warnings,
    }
    (paths.GENERATED_CHARACTERS_DIR / f"{class_id}.meta.json").write_text(json.dumps(meta, indent=2) + "\n")

    res.ok = True
    res.character = character
    res.quarantine_path = str(char_path)
    note(f"bundle quarantined -> {char_path}")
    return res


# --------------------------------------------------------------------------- internals
def _extract(text: str):
    try:
        return extract_card_json(text), []
    except ValueError as e:
        return None, [str(e)]


def _unique_class_id(base: str) -> str:
    taken = CardValidator._ids_in(paths.CHARACTERS_DIR) | CardValidator._ids_in(paths.GENERATED_CHARACTERS_DIR)
    if base not in taken:
        return base
    n = 2
    while f"{base}_{n}" in taken:
        n += 1
    return f"{base}_{n}"


def _set_summary(made: list[dict]) -> list[str]:
    lines = []
    for m in made:
        c, p = m["card"], m["plan"]
        eff = json.dumps(c.get("effects", []), separators=(",", ":"))
        if len(eff) > 160:
            eff = eff[:157] + "..."
        tag = p.get("archetype") or p["role"]
        lines.append(f"  - {c['id']} ({c.get('cost')}E {c.get('type')}, {tag}): {c.get('name')} {eff}")
    return lines


def _class_header(bp: dict, class_id: str) -> list[str]:
    def arch_line(a: dict) -> str:
        kind = f", {a['kind']} mechanic" if a.get("kind") else ""
        return f"  archetype '{a['id']}' ({a['name']}{kind}): {a['description']}"
    return [
        "CLASS CONTEXT -- this content belongs to a NEW class (NOT the Ironclad):",
        f"  class: {bp['name']} (id: {class_id}) -- {bp['description']}",
        arch_line(bp["archetypes"][0]),
        arch_line(bp["archetypes"][1]),
    ]


def _synthesize_basic(plan: dict, class_id: str, validator: CardValidator, note,
                      created: list[Path]):
    """The class's literal Strike/Defend starter (StS rule: every class begins with the same
    plain basics, named exactly that, plus a couple of signatures that hint its archetypes).
    Built verbatim -- the blueprint's basic briefs only contribute deck_count -- then written
    through the same quarantine path as generated cards so the bundle stays uniform."""
    is_attack = plan["role"] == "basic_attack"
    cid = _unique_id(f"{class_id}_strike" if is_attack else f"{class_id}_defend", validator)
    card = {
        "id": cid,
        "name": "Strike" if is_attack else "Defend",
        "type": "attack" if is_attack else "skill",
        "rarity": "basic",
        "character": class_id,
        "cost": 1,
        "target": "enemy" if is_attack else "self",
        "effects": [{"op": "damage", "amount": 6}] if is_attack else [{"op": "block", "amount": 5}],
        "upgrade": {"effects": [{"op": "damage", "amount": 9}] if is_attack
                    else [{"op": "block", "amount": 8}]},
        "source": "llm",  # provenance: part of an LLM bundle (schema enum: authored|llm)
    }
    vr = validator.validate(card)
    if not vr.ok:
        note("  synthesized basic invalid (?): " + "; ".join(vr.errors[:3]))
        return None
    paths.GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    path = paths.GENERATED_DIR / f"{cid}.json"
    path.write_text(json.dumps(card, indent=2) + "\n")
    meta = {
        "id": cid,
        "source": "llm",
        "model": "synthesized:literal-basic",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "brief": f"literal {card['name']} basic for class {class_id}",
        "score": round(vr.score, 2),
        "warnings": vr.warnings,
        "repaired": False,
    }
    (paths.GENERATED_DIR / f"{cid}.meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    created.append(path)
    validator.known_cards.add(cid)
    return card


def _generate_set_card(plan: dict, bp: dict, class_id: str, made: list[dict],
                       gen, validator: CardValidator, note, created: list[Path],
                       warnings_out: dict):
    """One set card through the standard card pipeline; tags + rewrites the quarantined file.
    Returns the final card dict, or None if generation failed (caller decides retry/skip)."""
    cost = plan.get("cost", 1)
    theme = f"{plan['theme']} (suggested name: {plan['name_hint']})"
    if cost == -1:
        theme += "; make it an X-cost card (cost -1: spends all energy)"
    lines = _class_header(bp, class_id)
    lines.append(f"This card's role in the set: {plan['role']}"
                 + (f", archetype '{plan['archetype']}'" if plan.get("archetype") else "") + ".")
    if plan.get("rarity") == "rare":
        lines.append("This is the archetype's RARE PAYOFF: the card the whole archetype is "
                     "drafted around. Per the rarity ladder, make it a build-around engine "
                     "(multi / conditional / from_state / fuse compositions, X-cost) or give it "
                     "splashy headline numbers -- clearly stronger and more ambitious than the "
                     "set's commons. A plain stat line at this rarity is a design failure.")
    lines.append(f'REQUIRED metadata: set "character": "{class_id}"'
                 + (f' and "archetype": "{plan["archetype"]}"' if plan.get("archetype") else "") + ".")
    if made:
        lines.append("Cards already designed for this set (synergize with them, don't duplicate them):")
        lines += _set_summary(made)
    brief = contract.Brief(
        card_type=plan["type"], rarity=plan["rarity"],
        target_cost=None if (cost == -1 or isinstance(cost, str)) else int(cost),  # -1 / "X" ⇒ X-cost
        theme=theme, context="\n".join(lines),
    )
    pres = generate_card(brief, gen=gen, validator=validator)
    for line in pres.log:
        note(f"  {line}")
    if not pres.ok:
        return None

    # Force the class/archetype tags (pool isolation must not depend on model compliance),
    # re-check, and rewrite the quarantined file in place.
    card = dict(pres.card)
    card["character"] = class_id
    if plan.get("archetype"):
        card["archetype"] = plan["archetype"]
    path = Path(pres.quarantine_path)
    vr = validator.validate(card)
    if not vr.ok:  # can only happen if the tags themselves are schema-invalid
        path.unlink(missing_ok=True)
        Path(str(path).replace(".json", ".meta.json")).unlink(missing_ok=True)
        note("  tagging made the card invalid (?); dropped: " + "; ".join(vr.errors[:3]))
        return None
    path.write_text(json.dumps(card, indent=2) + "\n")
    created.append(path)
    # the shared validator instance must learn the new id (ref-integrity for later cards
    # that build on this one, and collision-safe ids within the same run)
    validator.known_cards.add(card["id"])
    if vr.warnings:
        warnings_out[card["id"]] = vr.warnings
        note("  WARN " + " | ".join(vr.warnings))
    return card


def _generate_starter_relic(bp: dict, class_id: str, made: list[dict], gen, note,
                            created: list[Path], warnings_out: dict):
    lines = _class_header(bp, class_id)
    lines.append("This is the class STARTER relic, granted at run start (like Burning Blood / Worn "
                 "Carapace). Starter relics are modest, always-on identity pieces -- NOT run-defining.")
    lines.append('REQUIRED: "tier": "starter" and "pool": "starter".')
    if made:
        lines.append("The class card set it should complement:")
        lines += _set_summary(made)
    brief = relic_contract.Brief(
        tier="starter", pool="starter",
        theme=f"{bp['relic']['theme']} (suggested name: {bp['relic'].get('name_hint', '')})",
        context="\n".join(lines),
    )
    validator = RelicValidator()  # fresh: its card-id set must include the just-made set cards
    pres = generate_relic(brief, gen=gen, validator=validator)
    for line in pres.log:
        note(f"  {line}")
    if not pres.ok:
        return None

    relic = dict(pres.relic)
    relic["tier"] = "starter"   # never in a reward pool, regardless of model compliance
    relic["pool"] = "starter"
    path = Path(pres.quarantine_path)
    vr = validator.validate(relic)
    if not vr.ok:
        path.unlink(missing_ok=True)
        Path(str(path).replace(".json", ".meta.json")).unlink(missing_ok=True)
        note("  forcing starter tier made the relic invalid (?); dropped: " + "; ".join(vr.errors[:3]))
        return None
    path.write_text(json.dumps(relic, indent=2) + "\n")
    created.append(path)
    if vr.warnings:
        warnings_out[relic["id"]] = vr.warnings
        note("  WARN " + " | ".join(vr.warnings))
    return relic

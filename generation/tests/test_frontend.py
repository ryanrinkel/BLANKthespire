"""Offline tests for the staged creative front-end — no API key needed.

Run:  uv run python -m tests.test_frontend     (from generation/)
Exits nonzero on any failure. Covers: the archetype catalog + live buildability (against VOCABULARY.md +
VOCABULARY_GAPS.md), the buildability flip when a gap's status changes, the gap-append writer, the
BlueprintBuilder pipeline end-to-end with fake stage generators (collision/spine, distinctive-among-buildable
picker, relic-intent threading, a bp that passes _validate_blueprint), and the staged path through forge_class.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from btsgen.class_forge import (ClassBrief, _BlueprintContract, _CardFake, _fake_blueprint,
                                _topup_blueprint_briefs, _validate_blueprint, forge_class,
                                point_btsgen_at_mod_contract, validate_blueprint_for)

point_btsgen_at_mod_contract()  # repoint paths/vocab at the constrained mod contract BEFORE the catalog reads them

from btsgen.frontend import BlueprintBuilder, load_catalog  # noqa: E402
from btsgen.frontend import catalog as C  # noqa: E402
from btsgen.frontend.dossier import Candidate, Dossier  # noqa: E402
from btsgen.frontend.fakes import _StageFake  # noqa: E402

_PASS = 0
_FAIL = 0


def check(cond: bool, msg: str) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
    else:
        _FAIL += 1
        print(f"  FAIL: {msg}")


def _fake_make_gen(contract_mod, *, max_tokens):
    return _StageFake(contract_mod)


# --------------------------------------------------------------- catalog + buildability
def test_catalog_loads() -> None:
    print("catalog loads + recomputes buildability:")
    cat = load_catalog()
    check(len(cat.entries) >= 12, f"expected >=12 archetypes, got {len(cat.entries)}")
    ids = {e.id for e in cat.entries}
    check("retain_hold" in ids and "slot_machine" in ids, "seed archetypes must be present")
    buildable = cat.buildable_ids()
    check(len(buildable) >= 8, f"most seed archetypes should be buildable: {len(buildable)}")
    # countdown_ripen's gap #6 shipped 2026-06-26 (vocab v16); balance_gauge's gap #1 + op 'balance_step' shipped
    # 2026-07-08 (Phase S, vocab v24) -> both now BUILDABLE. Every live archetype is buildable post-Phase-S, so the
    # NEEDS-VOCAB path is exercised SYNTHETICALLY in test_buildability_flips_with_gap_status (a fake op + gap status).
    check(cat.by_id["countdown_ripen"].buildable, "countdown_ripen must be buildable (gap #6 done, 'ripen' live)")
    check(cat.by_id["balance_gauge"].buildable, "balance_gauge must be buildable (Phase S shipped gap #1 + balance_step)")
    # retain_hold's gap #5 is shipped (done) and its ops are live -> buildable
    check(cat.by_id["retain_hold"].buildable, "retain_hold must be buildable (gap #5 done, ops live)")
    # every archetype carries strategy leans, and they surface in the MAP prompt block
    check(all(e.leans for e in cat.entries), "every archetype must declare strategy leans")
    check(cat.by_id["strength_berserk"].leans == ["aggro"], "strength_berserk leans aggro")
    check("leans:" in cat.prompt_block(), "leans must appear in the catalog prompt block")


def test_buildability_flips_with_gap_status() -> None:
    print("buildability flips when a referenced gap's status changes:")
    cat = load_catalog()
    live = C.live_vocab_tokens()
    e = cat.by_id["retain_hold"]
    ok_done, _ = C.resolve_buildability(e.ops, e.gap_refs, live, {5: "done"})
    ok_cap, reasons = C.resolve_buildability(e.ops, e.gap_refs, live, {5: "captured"})
    check(ok_done, "retain_hold buildable when gap #5 is done")
    check(not ok_cap, "retain_hold NOT buildable when gap #5 is captured")
    check(any("gap #5" in r for r in reasons), f"reason must name the blocking gap: {reasons}")
    # an op that isn't in the live vocabulary blocks regardless of gaps
    ok_op, op_reasons = C.resolve_buildability(["totally_fake_op"], [], live, {})
    check(not ok_op and any("totally_fake_op" in r for r in op_reasons), "unknown op must block buildability")


def test_gap_status_parses_live_log() -> None:
    print("gap_status parses the live VOCABULARY_GAPS.md:")
    gaps = C.gap_status()
    check(gaps.get(5) == "done", f"gap #5 should parse as done, got {gaps.get(5)}")
    check(gaps.get(6) == "done", f"gap #6 (ripen, shipped 2026-06-26) should parse as done, got {gaps.get(6)}")
    # gap #1 (Balance) shipped 2026-07-08 as Phase S (vocab v24) -> parses as done, which is what flips
    # balance_gauge BUILDABLE (verified in test_catalog_loads).
    check(gaps.get(1) == "done", f"gap #1 should parse as done (Phase S shipped), got {gaps.get(1)}")


def test_append_vocab_gaps() -> None:
    print("append_vocab_gaps appends a numbered captured block (on a temp log):")
    orig = C._gap_log_path
    tmp = Path(tempfile.gettempdir()) / "bts_gaptest_frontend.md"
    tmp.write_text("# Gaps\n\n### 3. Existing\n- **Status:** captured\n", encoding="utf-8")
    try:
        C._gap_log_path = lambda: tmp
        n = C.append_vocab_gaps([{"title": "New Mechanic", "fantasy": "f", "sketch": "s"}])
        check(n == 1, f"should append exactly one gap, got {n}")
        body = tmp.read_text(encoding="utf-8")
        check("### 4. New Mechanic" in body, "appended gap must be numbered #4 (max+1)")
        check(C.gap_status().get(4) == "captured", "appended gap must parse back as captured")
        check(C.append_vocab_gaps([]) == 0, "empty append is a no-op")
    finally:
        C._gap_log_path = orig
        tmp.unlink(missing_ok=True)


def test_append_vocab_gaps_dedups_near_titles() -> None:
    print("append_vocab_gaps credits demand on a near-duplicate title instead of appending:")
    # unit-level: the conservative matcher fires on strong signals, not weak ones
    check(C._gap_titles_match("Light/Dark Balance Gauge", "light dark balance gauge"),
          "normalized-equal titles match")
    check(C._gap_titles_match("In-run Corruption resource", "Corruption resource meter"),
          "high token-overlap titles match")
    check(C._gap_titles_match("Deck-thinning purge keyword", "A deck-thinning purge keyword"),
          "substring containment matches")
    check(not C._gap_titles_match("Rampage grow-on-play", "Balance gauge"),
          "unrelated titles do NOT match (no false positive)")
    check(not C._gap_titles_match("Lightning chain", "Light/Dark Balance Gauge"),
          "one shared weak word is not a match")

    orig = C._gap_log_path
    tmp = Path(tempfile.gettempdir()) / "bts_gaptest_dedup.md"
    tmp.write_text("# Gaps\n\n### 1. Light/Dark Balance Gauge\n"
                   "- **Surfaced by:** Jedi run\n- **Status:** captured\n", encoding="utf-8")
    try:
        C._gap_log_path = lambda: tmp
        # a near-dup + a genuinely new gap in one batch
        n = C.append_vocab_gaps([
            {"title": "light dark balance gauge", "surfaced_by": "Yin-Yang run"},
            {"title": "Totally New Mechanic", "surfaced_by": "Storm run"},
        ])
        check(n == 1, f"only the genuinely-new gap appends, got {n}")
        body = tmp.read_text(encoding="utf-8")
        check("### 2. Totally New Mechanic" in body, "the new gap is numbered #2")
        check("### 2. light dark balance gauge" not in body and "### 3." not in body,
              "the near-duplicate did NOT append a new block")
        check("- **Demand:** ×2 — re-surfaced by: Yin-Yang run" in body,
              "the near-duplicate credited a ×2 demand signal on gap #1")
        # a second re-surfacing bumps the count and appends the source
        C.append_vocab_gaps([{"title": "Light-Dark Balance Gauge!", "surfaced_by": "Moon run"}])
        body = tmp.read_text(encoding="utf-8")
        check("×3" in body and "Moon run" in body, "a second re-surface bumps demand to ×3")
        check(C.gap_status().get(1) == "captured" and C.gap_status().get(2) == "captured",
              "demand credits do not disturb status parsing")
    finally:
        C._gap_log_path = orig
        tmp.unlink(missing_ok=True)


# --------------------------------------------------------------- the builder pipeline
def test_builder_pipeline() -> None:
    print("BlueprintBuilder pipeline (fake stages) -> a valid bp:")
    cat = load_catalog()
    events: list[str] = []
    b = BlueprintBuilder(_fake_make_gen, catalog=cat, on_event=events.append, auto=True, gap_log_append=None)
    bp = b.build(ClassBrief(concept="a storm-calling gambler who channels luck"))
    check(_validate_blueprint(bp) == [], f"front-end bp must pass _validate_blueprint: {_validate_blueprint(bp)}")
    check(bp.get("relic_intent") is not None, "keystone relic intent must be threaded into bp")
    d = b.last_dossier
    check(d is not None and d.chosen is not None, "dossier + chosen must be populated")
    check(len(d.candidates) >= 2, "at least two candidates composed")
    # strategic lines: the compose fake declares aggro+control; they must survive hydration and the bp must
    # cover them (validated by the builder via validate_blueprint_for)
    lines = {l.get("strategy") for l in d.chosen.strategic_lines}
    check(lines == {"aggro", "control"}, f"chosen candidate must carry its strategic lines, got {lines}")
    check(validate_blueprint_for(sorted(lines))(bp) == [],
          f"bp must cover the declared lines: {validate_blueprint_for(sorted(lines))(bp)}")
    # distinctive-among-buildable: the buildable candidate wins over the needs-vocab one
    check(d.chosen.buildable, "chosen candidate must be buildable")
    check(d.chosen.name == "Fake Buildable", f"picker should choose the buildable candidate, got {d.chosen.name}")
    # collision check set a spine (the fake maps two clusters to the same archetype)
    check(d.chosen.spine_archetype is not None, "collision check must set a spine on the chosen candidate")
    check(any("=> chose" in e for e in events), "progress events must flow through on_event")
    # gaps are SURFACED in the progress stream even when not written (gap_log_append=None)
    check(any("surfaced" in e and "gap" in e for e in events),
          "off-vocab gaps must be surfaced as a progress note even without a writer")
    check(d.gaps_logged == 0, "with gap_log_append=None, nothing is written (gaps_logged stays 0)")


def test_picker_prefers_distinctive_buildable() -> None:
    print("picker prefers the distinctive (special-kind) buildable candidate:")
    cat = load_catalog()
    b = BlueprintBuilder(_fake_make_gen, catalog=cat, auto=True)
    normal = Candidate(name="Plain", fantasy="", archetype_ids=["poison_attrition", "block_bulwark"],
                       archetype_descs=["", ""], class_kind="normal", buildable=True)
    orb = Candidate(name="Bold", fantasy="", archetype_ids=["orb_channel", "slot_machine"],
                    archetype_descs=["", ""], class_kind="orb", buildable=True)
    d = Dossier(candidates=[normal, orb])
    check(b._pick(d) is orb, "an orb (special-kind) buildable candidate should out-score a normal one")
    # but a NEEDS-VOCAB bold candidate must lose to a buildable plain one
    orb_unbuildable = Candidate(name="Bold but broken", fantasy="", archetype_ids=["orb_channel", "countdown_ripen"],
                                archetype_descs=["", ""], class_kind="orb", buildable=False)
    d2 = Dossier(candidates=[normal, orb_unbuildable])
    check(b._pick(d2) is normal, "an unbuildable candidate must never be auto-picked over a buildable one")


# --------------------------------------------------------------- strategic lines
def test_strategy_validation() -> None:
    print("strategic-line validation (compose + blueprint):")
    from btsgen.frontend.stage_map import validate_map

    # compose: a candidate with no strategic_lines is rejected; the fake (aggro+control) passes
    bare = {"mappings": [], "candidates": [{"name": "X", "archetype_ids": ["poison_attrition", "block_bulwark"]}]}
    errs = validate_map(bare)
    check(any("strategic_lines" in e for e in errs), f"compose must require strategic_lines: {errs}")
    one_line = {"mappings": [], "candidates": [{"name": "X", "archetype_ids": ["a", "b"], "strategic_lines": [
        {"strategy": "aggro", "line": "l", "win_condition": "w"},
        {"strategy": "aggro", "line": "l2", "win_condition": "w2"}]}]}
    check(any("DISTINCT" in e for e in validate_map(one_line)),
          "two lines of the SAME strategy must be rejected (need >=2 distinct)")

    # blueprint: an untagged pool fails the generic >=2-lines floor; _topup fixes it
    bp = _fake_blueprint(ClassBrief(concept="plain"))
    errs = _validate_blueprint(bp)
    check(any("strategic lines" in e for e in errs), f"untagged pool must fail strategy coverage: {errs}")
    check(_validate_blueprint(_topup_blueprint_briefs(bp)) == [], "topup must satisfy the generic floor")
    # declared-lines closure: a combo declaration is NOT covered by an aggro+control pool
    errs = validate_blueprint_for(["combo"])(bp)
    check(any("'combo'" in e for e in errs), f"declared combo line must be enforced: {errs}")
    check(validate_blueprint_for(["aggro", "control"])(bp) == [],
          "declared aggro+control lines are covered after topup")
    # a bogus tag on a card is an error
    bad = _topup_blueprint_briefs(_fake_blueprint(ClassBrief(concept="plain")))
    bad["cards"].append({"role": "pool", "name_hint": "Bad Tag", "type": "skill", "rarity": "common",
                         "cost": 1, "deck_count": 0, "archetype": None, "strategy": "scam", "theme": "x"})
    check(any("scam" in e for e in _validate_blueprint(bad)), "an unknown strategy tag must be rejected")


# --------------------------------------------------------------- map-only pitch validation
def test_map_pitch_validation() -> None:
    print("validate_map_only: one-sentence pitch contract (interactive option cards):")
    from btsgen.frontend.stage_map import _MapOnlyContract, validate_map_only

    fake = _MapOnlyContract().fake_output({"_catalog": load_catalog()})
    check(validate_map_only(fake) == [], f"the fake map output must validate: {validate_map_only(fake)}")

    good = {"mappings": [{"archetype_id": "retain_hold", "title": "T",
                          "pitch": "hold cheap cards, then release one scaled payoff."}]}
    check(validate_map_only(good) == [], "a short strategy pitch validates")

    unpitched = {"mappings": [{"archetype_id": "retain_hold", "title": "T", "pitch": " "}]}
    check(any("pitch" in e for e in validate_map_only(unpitched)), "an empty pitch is rejected")

    bloated = {"mappings": [{"archetype_id": "retain_hold", "title": "T", "pitch": "x" * 221}]}
    errs = validate_map_only(bloated)
    check(any("too long" in e for e in errs), f"a >220-char pitch must be rejected: {errs}")
    check(validate_map_only({"mappings": [{"archetype_id": "a", "title": "T", "pitch": "x" * 220}]}) == [],
          "220 chars is still inside the cap")


# --------------------------------------------------------------- archetype report enrichment
def test_archetype_enrichment() -> None:
    print("bp archetypes carry the report skin (title/pitch/catalog name):")
    from btsgen.class_forge import archetype_display
    cat = load_catalog()

    # autonomous (fused) path: the map stage writes no title/pitch, but the fake bp's id-as-name
    # archetypes must normalize to the catalog's display names
    b = BlueprintBuilder(_fake_make_gen, catalog=cat, auto=True, gap_log_append=None)
    bp = b.build(ClassBrief(concept="a storm-calling gambler"))
    archs = archetype_display(bp)
    check(len(archs) == 2, f"exactly two report archetypes: {archs}")
    check(all(set(a) == {"id", "name", "title", "pitch", "description"} for a in archs),
          f"report entries must carry exactly the display keys: {archs}")
    check(all(a["name"] and a["name"] != a["id"] for a in archs),
          f"fake-path names must normalize to catalog display names: {archs}")

    # interactive path: the picked archetype carries the map stage's themed title + strategy pitch
    picked: list[str] = []

    def checkpoint(options, dossier):
        check(all(o.get("pitch") or o.get("description") for o in options),
              f"every option card needs one line of body text: {options}")
        picked.append(str(options[0]["id"]))
        return [options[0]["id"]]

    bi = BlueprintBuilder(_fake_make_gen, catalog=cat, auto=True, gap_log_append=None,
                          archetype_checkpoint=checkpoint)
    archs2 = {a["id"]: a for a in archetype_display(bi.build(ClassBrief(concept="a storm-calling gambler")))}
    check(bool(picked) and picked[0] in archs2,
          f"the picked archetype must reach the bp: {picked} vs {sorted(archs2)}")
    a = archs2.get(picked[0] if picked else "", {})
    check(bool(a.get("title")) and bool(a.get("pitch")),
          f"the picked archetype must carry the map stage's title + pitch: {a}")

    # the helper is defensive: junk in, empty out
    check(archetype_display(None) == [], "None bp -> []")
    check(archetype_display({"archetypes": ["oops", None]}) == [], "non-dict entries are dropped")


# --------------------------------------------------------------- N-3 catalog expansion
def test_catalog_expansion() -> None:
    print("N-3: catalog carries 34 entries (26 + P reaper_lifesteal + Q token_conjurer + R madness_discard + U rampage_grow + V battle_smith + W ascetic_purge + AE strike_synergy + AH metamorph), the new ones buildable, metaphors enriched:")
    from btsgen.class_forge import STRATEGIES
    cat = load_catalog()
    check(len(cat.entries) == 34, f"catalog has 34 entries, got {len(cat.entries)}")
    ids = [e.id for e in cat.entries]
    check(len(ids) == len(set(ids)), f"archetype ids are unique: {ids}")

    new_ids = ["counter_riposte", "threshold_duelist", "horde_breaker", "ambush_alpha",
               "fleeting_flux", "untouchable_ward", "burst_window", "iron_regrowth"]
    for eid in new_ids:
        e = cat.by_id.get(eid)
        check(e is not None, f"new archetype '{eid}' is present")
        if e is None:
            continue
        check(e.buildable and not e.block_reasons,
              f"new archetype '{eid}' resolves BUILDABLE, got reasons {e.block_reasons}")
        check(set(e.leans) <= set(STRATEGIES), f"'{eid}' leans ⊆ STRATEGIES, got {e.leans}")

    # every entry (existing + new) now carries >=10 metaphors (wider map-stage resonance surface)
    thin = [(e.id, len(e.metaphors)) for e in cat.entries if len(e.metaphors) < 10]
    check(not thin, f"every entry has >=10 metaphors; thin: {thin}")

    # the catalog file stays pure-ASCII (streams to the Windows console)
    from btsgen.frontend.catalog import _DATA
    raw = _DATA.read_text(encoding="utf-8")
    check(all(ord(c) < 128 for c in raw), "archetypes.json is ASCII-only")

    # strike_tempo's description now names multi-hit explicitly
    check("multi-hit" in cat.by_id["strike_tempo"].description.lower(),
          "strike_tempo description mentions multi-hit")


# --------------------------------------------------------------- contract modes
def test_blueprint_contract_modes() -> None:
    print("_BlueprintContract concept vs dossier user_brief:")
    c = _BlueprintContract()
    check(c.mode == "concept", "default mode is concept")
    concept_brief = c.user_brief(ClassBrief(concept="a venom alchemist"))
    check("player concept" in concept_brief and "a venom alchemist" in concept_brief,
          "concept-mode brief carries the concept verbatim")
    cand = Candidate(name="The Tide", fantasy="patience then release", archetype_ids=["retain_hold", "tempo_draw"],
                     archetype_descs=["hold", "flow"], class_kind="normal", suggested_max_hp=74, tension="hold vs rush",
                     strategic_lines=[{"strategy": "control", "line": "hold and block", "win_condition": "scaled release"},
                                      {"strategy": "combo", "line": "retain pieces", "win_condition": "full-hand payoff"}])
    from btsgen.frontend.dossier import DossierBrief
    dbrief = DossierBrief(candidate=cand, relic_intent={"name": "Coil", "effect_sketch": "x"}, concept="t")
    dossier_brief = _BlueprintContract(mode="dossier").user_brief(dbrief)
    check("already chosen" in dossier_brief and "The Tide" in dossier_brief,
          "dossier-mode brief hands over the decided identity")
    check("retain_hold" in dossier_brief and "Keystone relic intent" in dossier_brief,
          "dossier-mode brief carries the archetypes + relic intent")
    check("STRATEGIC LINES" in dossier_brief and "full-hand payoff" in dossier_brief,
          "dossier-mode brief renders the candidate's strategic lines")


# --------------------------------------------------------------- forge_class seam
def test_forge_class_staged_end_to_end() -> None:
    print("forge_class with front_end -> a full BTSC bundle (fake cards):")
    cat = load_catalog()
    b = BlueprintBuilder(_fake_make_gen, catalog=cat, auto=True, gap_log_append=None)
    res = forge_class(ClassBrief(concept="a patient duelist who holds then strikes"),
                      blueprint_gen=None, card_gen_factory=lambda: _CardFake(), relic_gen=None,
                      fake=False, front_end=b)
    check(res.ok and res.bundle is not None, f"staged forge must succeed: {res.log[-3:]}")
    if res.bundle:
        check(res.bundle["kind"] == "class", "bundle kind must be class")
        check(len(res.bundle["cards"]) >= 3, "bundle must have cards")
        check(len(res.bundle["character"]["starting_deck"]) >= 1, "bundle must have a starting deck")


class _RelicStub:
    """Duck-typed keystone-relic generator: first_attempt returns `first`; repair returns `second`."""

    def __init__(self, first: dict, second: dict | None = None) -> None:
        import json
        self.model = "stub-offline"
        self._first, self._second = json.dumps(first), json.dumps(second if second else first)
        self.repair_errors: list[list[str]] = []

    def first_attempt(self, bp):
        return self._first, [{"role": "user", "content": "relic"}]

    def repair(self, messages, prev_text, errors):
        self.repair_errors.append(list(errors))
        return self._second, messages


def _run_staged_forge(relic_gen) -> object:
    cat = load_catalog()
    b = BlueprintBuilder(_fake_make_gen, catalog=cat, auto=True, gap_log_append=None)
    return forge_class(ClassBrief(concept="a patient duelist who holds then strikes"),
                       blueprint_gen=None, card_gen_factory=lambda: _CardFake(), relic_gen=relic_gen,
                       fake=False, front_end=b)


def test_forge_class_keystone_balance_gate() -> None:
    print("forge_class stage 2.5: overtuned keystone -> balance repair -> modest relic ships:")
    overtuned = {"id": "oc", "name": "Overcharged Core", "tier": "starter", "icon_emoji": "🔋",
                 "description": "Gain 1 Energy at the start of each turn.",
                 "hooks": [{"trigger": "turn_start", "effects": [{"op": "gain_energy", "amount": 1}]}]}
    modest = {"id": "cc", "name": "Calm Core", "tier": "starter", "icon_emoji": "🪨",
              "description": "Gain 3 Block at the start of each turn.",
              "hooks": [{"trigger": "turn_start", "effects": [{"op": "block", "amount": 3}]}]}
    stub = _RelicStub(overtuned, modest)
    res = _run_staged_forge(stub)
    check(res.ok, f"forge must succeed: {res.log[-3:]}")
    check(len(stub.repair_errors) == 1 and any("keystone too strong" in e for e in stub.repair_errors[0]),
          f"the balance gate must drive the repair: {stub.repair_errors}")
    check(res.bundle.get("relic", {}).get("name") == "Calm Core",
          f"the repaired modest relic ships: {res.bundle.get('relic')}")

    print("forge_class stage 2.5: still overtuned after repair -> relic dropped (Burning Blood default):")
    stub2 = _RelicStub(overtuned)  # repair returns the same overtuned relic
    res2 = _run_staged_forge(stub2)
    check(res2.ok, f"forge still succeeds without a relic: {res2.log[-3:]}")
    check(res2.bundle.get("relic") is None, f"no overtuned keystone may ship: {res2.bundle.get('relic')}")
    check(any("shipping without a forged relic" in line for line in res2.log),
          f"the drop must be logged: {[l for l in res2.log if 'relic' in l]}")


def test_strategy_idioms() -> None:
    print("O-3 strategy idioms: optional free-text texture tag, capped, never rejected, rendered:")
    from btsgen.frontend.stage_map import _FAKE_LINES, validate_map
    cat = load_catalog()

    # hydrate carries the idiom and LENGTH-CAPS it
    raw = {"name": "X", "archetype_ids": ["retain_hold", "tempo_draw"], "strategic_lines": [
        {"strategy": "control", "line": "hold", "win_condition": "release", "idiom": "turtle-scale"},
        {"strategy": "aggro", "line": "rush", "win_condition": "fast", "idiom": "z" * 80}]}
    cand = cat.hydrate_candidate(raw)
    check(cand.strategic_lines[0]["idiom"] == "turtle-scale", "idiom is carried through hydration")
    check(len(cand.strategic_lines[1]["idiom"]) == C.IDIOM_MAXLEN, "a long idiom is capped to IDIOM_MAXLEN")

    # absent idiom normalizes to "" and stays VALID
    raw2 = {"name": "X", "archetype_ids": ["retain_hold", "tempo_draw"], "strategic_lines": [
        {"strategy": "control", "line": "l", "win_condition": "w"},
        {"strategy": "aggro", "line": "l2", "win_condition": "w2"}]}
    check(cat.hydrate_candidate(raw2).strategic_lines[0]["idiom"] == "", "absent idiom -> empty string")
    base = {"mappings": [], "candidates": [{"name": "X", "archetype_ids": ["a", "b"], "strategic_lines": [
        {"strategy": "aggro", "line": "l", "win_condition": "w"},
        {"strategy": "control", "line": "l2", "win_condition": "w2"}]}]}
    check(validate_map(base) == [], f"a candidate with NO idiom validates: {validate_map(base)}")
    # an over-long idiom is NOT a validation error (capped at hydration, never enum/length-rejected)
    withlong = {"mappings": [], "candidates": [{"name": "X", "archetype_ids": ["a", "b"], "strategic_lines": [
        {"strategy": "aggro", "line": "l", "win_condition": "w", "idiom": "q" * 200},
        {"strategy": "control", "line": "l2", "win_condition": "w2", "idiom": "!! anything goes !!"}]}]}
    check(validate_map(withlong) == [], f"an over-long/free idiom is never a validation error: {validate_map(withlong)}")

    # the dossier brief RENDERS the idiom (present) and OMITS it (absent)
    cand_i = Candidate(name="The Tide", fantasy="patience", archetype_ids=["retain_hold", "tempo_draw"],
                       archetype_descs=["hold", "flow"], class_kind="normal", suggested_max_hp=74,
                       strategic_lines=[{"strategy": "control", "line": "hold", "win_condition": "release", "idiom": "turtle-scale"},
                                        {"strategy": "aggro", "line": "rush", "win_condition": "fast"}])
    from btsgen.frontend.dossier import DossierBrief
    brief = _BlueprintContract(mode="dossier").user_brief(DossierBrief(candidate=cand_i, concept="t"))
    check("[plays like: turtle-scale]" in brief, "dossier brief renders the idiom texture tag")
    check(brief.count("plays like:") == 1, "the line with no idiom renders no tag")

    # the offline fakes carry idioms (plumbing exercised end-to-end) and still validate
    check(all(l.get("idiom") for l in _FAKE_LINES), "fake strategic lines carry idioms")


def main() -> int:
    test_catalog_loads()
    test_buildability_flips_with_gap_status()
    test_gap_status_parses_live_log()
    test_append_vocab_gaps()
    test_append_vocab_gaps_dedups_near_titles()
    test_builder_pipeline()
    test_picker_prefers_distinctive_buildable()
    test_strategy_validation()
    test_map_pitch_validation()
    test_archetype_enrichment()
    test_catalog_expansion()
    test_blueprint_contract_modes()
    test_strategy_idioms()
    test_forge_class_staged_end_to_end()
    test_forge_class_keystone_balance_gate()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())

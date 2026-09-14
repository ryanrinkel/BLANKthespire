"""Phase AW — HYBRID CLASS KINDS IN GENERATION (VOCAB_GAP_REMEDIATION_PLAN Wave 4; vocab stays v52, NO engine change)
— offline, no API key.

Run:  uv run python -m tests.test_phase_aw       (from generation/)
Exits nonzero on any failure. Covers:
  1. no engine change: bts1.VOCAB_VERSION and ForgedCards.VocabVersion both still 52 (the C# importer already parsed
     orb_pool / status_pool / summon_pool independently — Phase N O-2a; AutoSlay GAPTESTAW1 closed the combat gate);
  2. the catalog: candidate_kinds() keeps every distinct special kind (primary first, capped at MAX_CLASS_KINDS = 2),
     hydrate_candidate stamps class_kinds beside the primary class_kind, Candidate keeps the two consistent;
  3. the dossier brief: a hybrid gets the primary's guidance PLUS the HYBRID sentence with the splash budget (and an
     orb splash never inherits '"orb_slots": 0'); a plain class gets no HYBRID sentence;
  4. prompt pruning keeps BOTH pool sections for a hybrid; exemplar dealing / pool_kind accept a kind list;
  5. _declared_kinds / _splash_sized / _validate_hybrid: <=2 pool kinds, one of them splash-sized, primary ordering;
  6. the fake dossier path grafts a splash pool onto a hybrid candidate and the result passes _validate_blueprint;
  7. builder weight (hybrid 3.5 > orb 3.0), narration label, ledger label 'orb+status', the drop nets keep splash cards;
  8. contract wording (VOCABULARY.md hybrid section, the prompt's HYBRID bullet, the stale 'EXACTLY ONE' summon line
     gone) and the rule-0.9 prompt budget.
"""
from __future__ import annotations

import os
import pathlib
import re
import sys

from btsgen.class_forge import point_btsgen_at_mod_contract

point_btsgen_at_mod_contract()

from btsgen import bts1, harness_v2, ledger, paths  # noqa: E402
from btsgen import class_forge as cf  # noqa: E402
from btsgen.frontend import catalog as cat_mod  # noqa: E402
from btsgen.frontend.builder import BlueprintBuilder, _HYBRID_WEIGHT, _KIND_WEIGHT, _kind_weight  # noqa: E402
from btsgen.frontend.catalog import candidate_kinds, load_catalog  # noqa: E402
from btsgen.frontend.dossier import Candidate, DossierBrief  # noqa: E402

_PASS = 0
_FAIL = 0

MOD_CODE = paths.VOCABULARY.parents[1] / "BlankTheSpireCode"   # mod/contract/.. -> mod/BlankTheSpireCode
BP_AV = 95_153        # the blueprint prompt size Phase AV left behind (see the AV STATUS paragraph)
BP_ALLOWANCE = 1_000  # rule 0.9: the HYBRID bullet (+~310) and VOCABULARY's hybrid section (+~480)


def check(cond: bool, msg: str) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
    else:
        _FAIL += 1
        print(f"  FAIL: {msg}")


def _cand(ids, kinds=None, name="Hybrid", **kw) -> Candidate:
    c = Candidate(name=name, fantasy="storm and steel", archetype_ids=list(ids),
                  archetype_descs=[""] * len(ids), buildable=True, **kw)
    if kinds is not None:
        c.class_kinds = list(kinds)
        c.class_kind = kinds[0] if kinds else "normal"
    return c


def _brief(c: Candidate) -> str:
    return cf._BlueprintContract(mode="dossier", triad=False)._dossier_brief(DossierBrief(candidate=c, concept="x"))


def _fake_bp(c: Candidate) -> dict:
    return cf._BlueprintContract(mode="dossier", triad=False).fake_output(DossierBrief(candidate=c, concept="x"))


# --------------------------------------------------------------------------- 1. no engine change
def test_version() -> None:
    print("no engine change (v52 on both sides):")
    check(bts1.VOCAB_VERSION >= 52, f"bts1.VOCAB_VERSION >= 52 (Phase AW added no bump of its own; AX moved it to 53), got {bts1.VOCAB_VERSION}")
    cs = (MOD_CODE / "Engine" / "ForgedCards.cs").read_text(encoding="utf-8", errors="replace")
    m = re.search(r"VocabVersion\s*=\s*(\d+)", cs)
    check(m is not None and int(m.group(1)) >= 52, f"ForgedCards.VocabVersion >= 52 (Phase AW added no bump of its own; AX moved it to 53), got {m.group(1) if m else None}")
    chars = (MOD_CODE / "Engine" / "ForgedCharacters.cs").read_text(encoding="utf-8", errors="replace")
    for key in ("orb_pool", "status_pool", "summon_pool"):
        check(f'd.ContainsKey("{key}")' in chars, f"ForgedCharacters parses {key} on its own ContainsKey branch (O-2a)")


# --------------------------------------------------------------------------- 2. catalog + Candidate
def _t_catalog() -> None:
    print("catalog: candidate_kinds + hydrate_candidate:")
    check(cat_mod.MAX_CLASS_KINDS == 2, "MAX_CLASS_KINDS is 2 (a primary + one splash)")
    check(candidate_kinds(["orb", "status"]) == ["orb", "status"], "orb + status -> ['orb', 'status'] (orb leads)")
    check(candidate_kinds(["status", "orb"]) == ["orb", "status"], "order-insensitive: status + orb -> orb first")
    check(candidate_kinds(["normal", "normal"]) == [], "two normal archetypes -> [] (a normal class)")
    check(candidate_kinds(["orb", "orb"]) == ["orb"], "two orb archetypes -> ['orb'] (deduplicated)")
    check(candidate_kinds(["orb", "status", "summon"]) == ["orb", "summon"],
          "all three subsystems -> capped at the two boldest (orb, summon)")
    check(candidate_kinds(["status", "summon"]) == ["summon", "status"], "status + summon -> summon leads")
    check(candidate_kinds(None) == [] and candidate_kinds(["bogus"]) == [], "unknown / missing kinds -> []")

    cat = load_catalog()
    h = cat.hydrate_candidate({"name": "H", "fantasy": "", "archetype_ids": ["orb_channel", "status_signature"]})
    check(h.class_kind == "orb", f"hybrid primary class_kind is orb, got {h.class_kind}")
    check(h.class_kinds == ["orb", "status"], f"hydrate stamps class_kinds ['orb', 'status'], got {h.class_kinds}")
    check(h.is_hybrid and h.kind_label() == "orb+status", "is_hybrid + kind_label 'orb+status'")
    t = cat.hydrate_candidate({"name": "T", "fantasy": "",
                               "archetype_ids": ["orb_channel", "status_signature", "summon_swarm"]})
    check(t.class_kinds == ["orb", "summon"], f"triad of all three -> ['orb', 'summon'], got {t.class_kinds}")
    n = cat.hydrate_candidate({"name": "N", "fantasy": "", "archetype_ids": ["poison_attrition", "block_bulwark"]})
    check(n.class_kind == "normal" and n.class_kinds == [] and not n.is_hybrid and n.kind_label() == "normal",
          "a normal pair: class_kind normal, class_kinds [], label 'normal'")
    o = cat.hydrate_candidate({"name": "O", "fantasy": "", "archetype_ids": ["orb_channel", "slot_machine"]})
    check(o.class_kind == "orb" and o.class_kinds == ["orb"], "two orb archetypes: a plain orb class, not a hybrid")

    c1 = _cand(["a", "b"], class_kind="orb")
    check(c1.class_kinds == ["orb"], "Candidate(class_kind='orb') back-fills class_kinds ['orb'] (pre-AW call sites)")
    c2 = Candidate(name="x", fantasy="", archetype_ids=["a", "b"], archetype_descs=["", ""], class_kinds=["status", "orb"])
    check(c2.class_kind == "status", "Candidate(class_kinds=[...]) back-fills class_kind from the first kind")
    c3 = _cand(["a", "b"])
    check(c3.class_kind == "normal" and c3.class_kinds == [], "default Candidate is normal with no kinds")


# --------------------------------------------------------------------------- 3. dossier brief
def _t_brief() -> None:
    print("dossier brief: hybrid guidance:")
    b = _brief(_cand(["orb_channel", "status_signature"], ["orb", "status"]))
    check("This is an ORB CLASS" in b, "orb-primary hybrid keeps the ORB CLASS guidance")
    check("HYBRID: the orb engine LEADS; status is a SPLASH" in b, "the HYBRID sentence names primary + splash")
    check('SMALL "status_pool" (1-2 custom statuses)' in b, "a status splash gets its 1-2 status budget")
    check("at least two bridge cards touch BOTH engines" in b, "the brief asks for two both-engine bridges")
    b2 = _brief(_cand(["status_signature", "orb_channel"], ["status", "orb"]))
    check("This is a STATUS CLASS" in b2 and '"orb_slots": 0' not in b2,
          "status-primary + orb splash: STATUS guidance WITHOUT the '\"orb_slots\": 0' sentence")
    check('set "orb_slots" to 2 or 3' in b2, "an orb splash asks for 2-3 slots")
    b3 = _brief(_cand(["summon_swarm", "status_signature"], ["summon", "status"]))
    check("This is a SUMMON CLASS" in b3 and '"orb_slots": 0' in b3 and "HYBRID: the summon engine LEADS" in b3,
          "summon-primary + status splash keeps '\"orb_slots\": 0' and gets the HYBRID sentence")
    plain = _brief(_cand(["orb_channel", "slot_machine"], class_kind="orb"))
    check("This is an ORB CLASS" in plain and "HYBRID:" not in plain, "a plain orb class gets no HYBRID sentence")
    normal = _brief(_cand(["a", "b"]))
    check("This is a NORMAL class" in normal and "HYBRID:" not in normal, "a normal class gets no HYBRID sentence")


# --------------------------------------------------------------------------- 4. pruning + kind sets
def _t_prune_and_kinds() -> None:
    print("prompt pruning keeps both pool sections; kind sets accept a list:")
    heads = {kind: head for head, _toks, kind, _key, _pitch in cf._PRUNABLE_SECTIONS if kind in ("orb", "status", "summon")}
    check(set(heads) == {"orb", "status", "summon"}, f"one prunable section per pool kind, got {sorted(heads)}")

    def _has(prompt: str, head: str) -> bool:
        return any(p.lstrip().startswith(head) for p in prompt.split("\n\n"))

    # pruning is a harness-v2 behaviour (system_prompt prunes only under BTS_HARNESS_V2) — flip it on for the render
    old = os.environ.get(harness_v2.FLAG)
    os.environ[harness_v2.FLAG] = "1"
    try:
        hyb = cf._BlueprintContract(mode="dossier", triad=True, seed=1, selected_ops=set(),
                                    class_kind=["orb", "status"]).system_prompt()
        orb = cf._BlueprintContract(mode="dossier", triad=True, seed=1, selected_ops=set(), class_kind="orb").system_prompt()
    finally:
        if old is None:
            os.environ.pop(harness_v2.FLAG, None)
        else:
            os.environ[harness_v2.FLAG] = old
    check(_has(hyb, heads["orb"]) and _has(hyb, heads["status"]), "hybrid ['orb','status'] keeps the ORB and STATUS sections")
    check(not _has(hyb, heads["summon"]), "hybrid ['orb','status'] still prunes the SUMMON section")
    check(_has(orb, heads["orb"]) and not _has(orb, heads["status"]), "a plain 'orb' string still prunes the STATUS section")
    check(len(hyb) > len(orb), "the hybrid prompt is longer than the plain orb prompt (the status section is in)")

    check(harness_v2.kind_set("orb") == {"orb"} and harness_v2.kind_set(["orb", "status"]) == {"orb", "status"}
          and harness_v2.kind_set(None) == set(), "kind_set normalizes str / list / None")
    check(harness_v2.pool_kind(["orb", "status"], []) == {"", "orb", "status"}, "pool_kind(list) carries BOTH kinds")
    check(harness_v2.pool_kind("orb", []) == {"", "orb"}, "pool_kind(str) is unchanged")
    check(harness_v2.pool_kind("normal", []) == {""} and harness_v2.pool_kind([], []) == {""}, "normal / [] -> base only")
    pool = harness_v2.load_exemplar_pool()
    ok = harness_v2.pool_kind(["orb", "status"], ["orb_channel", "status_signature"])
    needs = {e["needs"] for e in pool if e["needs"] in ok}
    check({"orb", "status"} <= needs, f"a hybrid's exemplar scope includes needs:orb AND needs:status, got {sorted(needs)}")
    ex = harness_v2.pick_exemplars(["orb_channel", "status_signature"], "common", 7, class_kind=["orb", "status"])
    check(len(ex) == 3 and all(isinstance(c, dict) and c.get("id") for c in ex), "pick_exemplars accepts a kind list")


# --------------------------------------------------------------------------- 5. declared kinds + the hybrid gate
def _t_validate_hybrid() -> None:
    print("_declared_kinds / _splash_sized / _validate_hybrid:")
    st = lambda n: [{"name": f"S{i}", "type": "buff", "hook": "damage_dealt", "decay": "none"} for i in range(n)]  # noqa: E731
    check(cf._declared_kinds({}) == [] and cf._declared_kinds({"orb_slots": 0}) == [], "normal -> []")
    check(cf._declared_kinds({"orb_slots": 3, "orb_pool": ["lightning"]}) == ["orb"], "orb only -> ['orb']")
    check(cf._declared_kinds({"orb_slots": 4, "orb_pool": ["lightning"], "status_pool": st(2)}) == ["orb", "status"],
          "full orb (4 slots) + 2 statuses -> orb leads")
    check(cf._declared_kinds({"orb_slots": 2, "orb_pool": ["lightning"], "status_pool": st(3)}) == ["status", "orb"],
          "2-slot base-orb splash + 3 statuses -> STATUS leads (sizes decide, not the priority table)")
    check(cf._declared_kinds({"orb_slots": 3, "orb_pool": ["lightning"], "status_pool": st(2)}) == ["orb", "status"],
          "both splash-sized -> tie breaks orb > status")
    check(cf._declared_kinds({"summon_pool": [{"name": "T", "max_hp": 10}], "status_pool": st(1)}) == ["summon", "status"],
          "passive minion + 1 status -> tie breaks summon > status")

    check(cf._splash_sized({"orb_slots": 3, "orb_pool": ["lightning", {"name": "Ember"}]}, "orb"), "3 slots + 1 custom orb is splash-sized")
    check(not cf._splash_sized({"orb_slots": 4, "orb_pool": ["lightning"]}, "orb"), "4 slots is NOT splash-sized")
    check(not cf._splash_sized({"orb_slots": 3, "orb_pool": [{"name": "A"}, {"name": "B"}]}, "orb"), "2 custom orbs is NOT splash-sized")
    check(cf._splash_sized({"status_pool": st(2)}, "status") and not cf._splash_sized({"status_pool": st(3)}, "status"),
          "status splash: <=2 statuses")
    check(cf._splash_sized({"summon_pool": [{"name": "T", "max_hp": 10}]}, "summon"), "ONE passive minion is splash-sized")
    check(not cf._splash_sized({"summon_pool": [{"name": "T", "max_hp": 10, "moves": [{"actions": [{"op": "attack", "amount": 3}]}]}]}, "summon"),
          "an AUTONOMOUS minion is NOT splash-sized")
    check(not cf._splash_sized({"summon_pool": [{"name": "A", "max_hp": 10}, {"name": "B", "max_hp": 10}]}, "summon"),
          "two minions are NOT splash-sized")

    check(cf._validate_hybrid({"orb_slots": 5, "orb_pool": ["lightning", {"name": "A"}, {"name": "B"}]}) == [],
          "a single full-sized kind is never a hybrid error")
    errs = cf._validate_hybrid({"orb_slots": 3, "orb_pool": ["lightning"], "status_pool": st(2)})
    check(errs == [], f"orb engine + 2-status splash accepted, got {errs}")
    errs = cf._validate_hybrid({"orb_slots": 4, "orb_pool": [{"name": "A"}, {"name": "B"}], "status_pool": st(3)})
    check(len(errs) == 1 and "SPLASH-sized" in errs[0] and "orb + status" in errs[0],
          f"two full-sized pools -> the splash error naming both budgets, got {errs}")
    errs = cf._validate_hybrid({"orb_slots": 2, "orb_pool": ["lightning"], "status_pool": st(1),
                                "summon_pool": [{"name": "T", "max_hp": 10}]})
    check(len(errs) == 1 and "at most TWO pool kinds" in errs[0], f"three pool kinds -> rejected, got {errs}")


# --------------------------------------------------------------------------- 6. the fake dossier path
def _t_fake_path() -> None:
    print("fake dossier path grafts the splash and validates:")
    orb_st = _fake_bp(_cand(["orb_channel", "status_signature"], ["orb", "status"], name="Storm Duelist"))
    errs = cf._validate_blueprint(orb_st)
    check(errs == [], f"orb-primary + status-splash fake blueprint validates, got {errs}")
    check(int(orb_st.get("orb_slots", 0)) >= 3 and orb_st.get("orb_pool"), "the orb engine is the seed's full pool")
    check(len(orb_st.get("status_pool") or []) == 1, "the status splash is ONE custom status")
    check(cf._declared_kinds(orb_st) == ["orb", "status"], f"declared kinds orb, status; got {cf._declared_kinds(orb_st)}")
    hints = [c.get("name_hint") for c in orb_st["cards"]]
    check("Lacerate" in hints and "Expose" in hints, "two splash briefs were grafted")
    splash = [c for c in orb_st["cards"] if c.get("name_hint") in ("Lacerate", "Expose")]
    check(all(c.get("archetype") == "status_signature" for c in splash), "splash briefs belong to the splash archetype")
    check(cf.validate_blueprint_for([])(orb_st) == [], "the staged validator closure accepts it too")

    st_orb = _fake_bp(_cand(["status_signature", "orb_channel"], ["status", "orb"], name="Edge Storm"))
    check(cf._validate_blueprint(st_orb) == [], f"status-primary + orb-splash validates, got {cf._validate_blueprint(st_orb)}")
    check(st_orb.get("orb_slots") == 2 and st_orb.get("orb_pool") == ["lightning"], "orb splash: 2 slots, base lightning")
    # the status SEED pool is itself splash-sized (2 statuses), so with both pools within budget the size rule has no
    # primary to pick and the tie breaks orb-first — a REAL status engine (3-4 statuses) leads, see _t_validate_hybrid
    check(cf._declared_kinds(st_orb) == ["orb", "status"], f"both splash-sized -> orb first, got {cf._declared_kinds(st_orb)}")
    st_orb["status_pool"] = st_orb["status_pool"] + [dict(st_orb["status_pool"][0], name=f"Extra {i}") for i in range(2)]
    check(cf._validate_blueprint(st_orb) == [] and cf._declared_kinds(st_orb) == ["status", "orb"],
          f"grown to a 4-status engine + the orb splash: still valid, status leads; got {cf._declared_kinds(st_orb)}")

    orb_sm = _fake_bp(_cand(["orb_channel", "summon_swarm"], ["orb", "summon"], name="Storm Caller"))
    check(cf._validate_blueprint(orb_sm) == [], f"orb-primary + summon-splash validates, got {cf._validate_blueprint(orb_sm)}")
    check(len(orb_sm.get("summon_pool") or []) == 1 and not cf._summon_is_autonomous(orb_sm["summon_pool"][0]),
          "summon splash: ONE passive minion")

    plain = _fake_bp(_cand(["orb_channel", "slot_machine"], class_kind="orb", name="Plain Storm"))
    check(not plain.get("status_pool") and not plain.get("summon_pool") and cf._declared_kinds(plain) == ["orb"],
          "a plain orb candidate's fake is untouched")
    twice = dict(orb_st)
    cf._fake_splash(twice, "status", "status_signature")
    check(len(twice["status_pool"]) == 1 and twice["cards"] is orb_st["cards"], "_fake_splash is a no-op when the pool exists")


# --------------------------------------------------------------------------- 7. builder / ledger / drop nets
def _t_builder_ledger_dropnets() -> None:
    print("builder weight + narration, ledger label, drop nets:")
    check(_HYBRID_WEIGHT == 3.5 and _HYBRID_WEIGHT > max(_KIND_WEIGHT.values()), "hybrid weight 3.5 tops the kind table")
    hyb = _cand(["orb_channel", "status_signature"], ["orb", "status"])
    orb = _cand(["orb_channel", "slot_machine"], class_kind="orb")
    check(_kind_weight(hyb) == 3.5 and _kind_weight(orb) == 3.0 and _kind_weight(_cand(["a", "b"])) == 0.0,
          "_kind_weight: hybrid 3.5, orb 3.0, normal 0")
    b = BlueprintBuilder(lambda *a, **k: None, catalog=load_catalog(), auto=True, triad=False)
    check(b._distinctiveness(hyb, [hyb, orb]) > b._distinctiveness(orb, [hyb, orb]),
          "a hybrid out-scores a plain orb candidate on distinctiveness")
    notes: list[str] = []
    b._note = notes.append  # type: ignore[method-assign]
    b._narrate_choice(hyb)
    check(any("orb+status hybrid class" in n for n in notes), f"narration says 'orb+status hybrid class', got {notes}")

    check(ledger._class_kind({"orb_slots": 3, "orb_pool": ["lightning"],
                              "status_pool": [{"name": "S"}]}) == "orb+status", "ledger label 'orb+status'")
    check(ledger._class_kind({"orb_slots": 3}) == "orb" and ledger._class_kind({}) == "normal"
          and ledger._class_kind(None) == "normal", "ledger single-kind / normal labels unchanged")

    bp = {"orb_slots": 3, "orb_pool": ["lightning"], "status_pool": [{"name": "Brittle"}]}
    status_card = {"effects": [{"op": "apply_status_custom", "status_name": "Brittle", "amount": 2}]}
    orb_card = {"effects": [{"op": "channel_orb", "orb": "lightning", "amount": 1}]}
    check(cf._card_uses_custom_status(status_card) and cf._status_pool_custom_names(bp),
          "drop net: a status card on a hybrid has a status_pool -> kept")
    check(cf._card_uses_orbs(orb_card) and int(bp["orb_slots"]) > 0, "drop net: an orb card on a hybrid has slots -> kept")
    check(not cf._status_pool_custom_names({"orb_slots": 3}), "drop net: the same status card on a plain orb class is dropped")


# --------------------------------------------------------------------------- 8. contract wording + budget
def _t_contract() -> None:
    print("contract wording + rule 0.9:")
    vocab = paths.VOCABULARY.read_text(encoding="utf-8")
    check("## Hybrid classes (two pool kinds)" in vocab, "VOCABULARY.md has the hybrid section")
    check("ONE full engine plus ONE **splash** pool" in vocab and "never all three" in vocab,
          "VOCABULARY.md states the one-engine-plus-one-splash rule")
    sp = cf._BlueprintContract(mode="dossier", triad=True, seed=1).system_prompt()
    check("- HYBRID (rare" in sp, "the blueprint prompt carries the one-line HYBRID bullet")
    check("EXACTLY ONE custom" not in sp and "ONE or TWO custom" in sp,
          "the stale 'EXACTLY ONE custom summon' bullet (pre-AV) now says ONE or TWO")
    print(f"  (rule 0.9) blueprint prompt: {len(sp):,} chars (AV left {BP_AV:,}; delta {len(sp) - BP_AV:+,})")
    print(f"  (rule 0.9) VOCABULARY.md:    {len(vocab):,} chars")
    # KNOWN RED since Phase AX (2026-09-11): this pins a ceiling measured on THIS phase's day, but there is
    # only one blueprint prompt and later phases grew it past this line. Do NOT just raise the number - that
    # is the ratchet rule 0.9 exists to stop. The fix is one shared budget assert; see "the rule-0.9 budget is
    # asserted in N places" under Cross-cutting mitigations in VOCAB_GAP_REMEDIATION_PLAN.md.
    check(len(sp) <= BP_AV + BP_ALLOWANCE, f"rule 0.9: the AW additions stay within +{BP_ALLOWANCE:,} (got {len(sp) - BP_AV:+,})")
    tester = pathlib.Path(cf.__file__).parents[1] / "scratch" / "gaptest-aw" / "build_tester.py"
    if tester.exists():
        src = tester.read_text(encoding="utf-8")
        check('"orb_slots": 3' in src and '"status_pool": STATUS_POOL' in src, "the AW smoke tester is an orb+status hybrid")


# --------------------------------------------------------------------------- 9. staged forge end to end (offline)
def _t_end_to_end() -> None:
    print("staged fake forge end to end with a picked orb+status pair:")
    from btsgen.class_forge import ClassBrief, _CardFake, forge_class
    from btsgen.frontend.fakes import _StageFake
    # the interactive archetype checkpoint is the one hook that lets the OFFLINE compose stage be steered: the fake
    # compose honors the player's picks, so picking the orb + status archetypes composes a hybrid candidate.
    events: list[str] = []   # the builder narrates through on_event, forge_class through res.log
    b = BlueprintBuilder(lambda contract_mod, *, max_tokens: _StageFake(contract_mod), catalog=load_catalog(),
                         on_event=events.append, auto=True, gap_log_append=None, triad=False,
                         archetype_checkpoint=lambda options, dossier: ["orb_channel", "status_signature"])
    res = forge_class(ClassBrief(concept="a storm-caller duelist who brands foes with lightning scars"),
                      blueprint_gen=None, card_gen_factory=lambda: _CardFake(), relic_gen=None,
                      fake=False, front_end=b)
    check(res.ok and res.bundle is not None, f"staged hybrid forge must succeed: {res.log[-3:]}")
    d = b.last_dossier
    check(d is not None and any(getattr(c, "is_hybrid", False) for c in (d.candidates or [])),
          "the compose stage produced a hybrid (orb+status) candidate from the pick")
    if res.bundle:
        ch = res.bundle["character"]
        check(int(ch.get("orb_slots", 0) or 0) >= 3 and bool(ch.get("orb_pool")), "the character carries the orb engine")
        check(len(ch.get("status_pool") or []) == 1, "the character carries the ONE-status splash")
        check(not ch.get("summon_pool"), "no third pool")
        check(any("hybrid class: orb engine + status splash" in str(l) for l in res.log),
              "forge_class notes the hybrid (both pools declared)")
        check(any("orb+status hybrid class" in str(e) for e in events), "the builder narrates the hybrid choice")


def main() -> int:
    test_version()
    _t_catalog()
    _t_brief()
    _t_prune_and_kinds()
    _t_validate_hybrid()
    _t_fake_path()
    _t_builder_ledger_dropnets()
    _t_contract()
    _t_end_to_end()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())

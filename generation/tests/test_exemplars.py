"""Offline tests for btsgen/data/exemplar_pool.json — the curated v2 exemplar pool (W0.8) and its dealing (W0.9).
No API key needed.

Run:  uv run python -m tests.test_exemplars     (from generation/)
Exits nonzero on any failure. Covers: (a) every archetype id has >=2 exemplars; (b) every exemplar touches >=1 token
of EACH tagged archetype's `ops`; (c) every op / status / when-kind / scale token in VOCABULARY.md's tables (plus every
add_trigger kind) appears in at least one exemplar; (d) every exemplar passes the card validator under the mod
contract with the pool's placeholder class context; plus the `needs` tagging discipline (class-only tokens <=> a
`needs` tag) and harness_v2._pool_kind dealing by class_kind UNION mechanic_kind (forge / balance).
"""
from __future__ import annotations

import json
import re
import sys

from btsgen.class_forge import point_btsgen_at_mod_contract

point_btsgen_at_mod_contract()

from btsgen import harness_v2, paths  # noqa: E402
from btsgen.bridges import card_tokens  # noqa: E402
from btsgen.frontend import load_catalog  # noqa: E402

_PASS = 0
_FAIL = 0

NEEDS_KINDS = frozenset({"", "orb", "status", "summon", "forge", "balance"})

# Class-only vocabulary -> the `needs` tag an exemplar touching it must carry (so a plain class is never dealt
# an orb / custom-status / summon / forge / balance card it can't run).
CLASS_ONLY_TOKENS = {
    "orb": {"channel_orb", "evoke", "gain_orb_slot", "focus", "orbs_match", "orb_count_ge",
            "temp_focus"},  # Phase AN (v44): the one-turn Focus is orb-class-only like focus
    "status": {"apply_status_custom"},
    "summon": {"summon", "summon_attack", "buff_summon", "heal_summon", "shield_summon",
               "sacrifice_summon"},  # Phase AV (v52)
    "forge": {"forge", "forged", "forged_ge", "blade_empower", "summon_blade", "on_blade_played",
              "spend_forge"},  # Phase AX (v53): the cash-out needs forge income to spend
    "balance": {"balance_step", "light_ge", "dark_ge", "centered"},
}

_ROW_TOKEN_RE = re.compile(r"^\|\s*`([a-z][a-z0-9_]*)`")


def check(cond: bool, msg: str) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
    else:
        _FAIL += 1
        print(f"  FAIL: {msg}")


def _pool() -> tuple:
    harness_v2.load_exemplar_pool.cache_clear()
    return harness_v2.load_exemplar_pool()


def _by_id() -> dict[str, dict]:
    return {e["card"]["id"]: e for e in _pool()}


# --------------------------------------------------------------- VOCABULARY.md harvest
def _table_tokens(section_title: str) -> set[str]:
    """First-column backtick tokens of the table under `## <section_title>` in the live VOCABULARY.md — the same
    backtick-token idea catalog.live_vocab_tokens() uses, restricted to one table's first column."""
    text = paths.VOCABULARY.read_text(encoding="utf-8")
    body = ""
    for part in re.split(r"^## ", text, flags=re.MULTILINE):
        if part.startswith(section_title):
            body = part
            break
    out: set[str] = set()
    for line in body.splitlines():
        m = _ROW_TOKEN_RE.match(line)
        if m and m.group(1) not in ("op", "status", "condition", "target"):
            out.add(m.group(1))
    return out


def vocab_ops() -> set[str]:
    return _table_tokens("Effect ops")


def vocab_statuses() -> set[str]:
    return _table_tokens("Statuses")


def vocab_conditions() -> set[str]:
    return _table_tokens("Conditions")


def _schema_enum(*path: str) -> set[str]:
    node = json.loads(paths.CARD_SCHEMA.read_text(encoding="utf-8"))
    for key in path:
        node = node[key]
    return set(node)


def vocab_scales() -> set[str]:
    # Harvesting the scale sources from VOCABULARY.md's prose bullets is fragile (mixed `"x"` / `forged` quoting), so
    # take the schema's `scale` enum — the same list — and cross-check each is a backtick token in the prose.
    return _schema_enum("$defs", "effect", "properties", "scale", "enum")


def vocab_triggers() -> set[str]:
    return _schema_enum("$defs", "effect", "properties", "trigger", "enum")


# --------------------------------------------------------------- (a) every archetype has >=2
def test_every_archetype_has_two_exemplars() -> None:
    print("(a) every archetype id has >=2 exemplars, every tag is a catalog id:")
    cat = load_catalog()
    pool = _pool()
    check(len(pool) >= 60, f"pool has {len(pool)} exemplars (>= 60 after W0.8)")
    ids = {e.id for e in cat.entries}
    counts = {i: 0 for i in ids}
    for e in pool:
        for a in e["archetypes"]:
            check(a in ids, f"{e['card']['id']} tags unknown archetype '{a}'")
            if a in counts:
                counts[a] += 1
        check(1 <= len(e["archetypes"]) <= 3, f"{e['card']['id']} tags 1-3 archetypes")
    thin = {a: n for a, n in counts.items() if n < 2}
    check(not thin, f"archetypes with fewer than 2 exemplars: {thin}")
    for old, want in (("ex_ash_dividend", ["exhaust_pyre"]), ("ex_surge_capacitor", ["big_energy"])):
        check(_by_id()[old]["archetypes"] == want, f"{old} retagged to {want}")


# --------------------------------------------------------------- (b) each exemplar uses each tag's ops
def test_every_exemplar_uses_each_tagged_archetypes_ops() -> None:
    print("(b) every exemplar touches >=1 token of EACH tagged archetype's ops:")
    cat = load_catalog()
    for e in _pool():
        toks = card_tokens(e["card"])
        for a in e["archetypes"]:
            ops = set(cat.by_id[a].ops) if a in cat.by_id else set()
            check(bool(toks & ops), f"{e['card']['id']} tagged '{a}' but touches none of its ops {sorted(ops)}: {sorted(toks)}")


# --------------------------------------------------------------- (c) the pool spans the whole vocabulary
def test_pool_covers_every_vocabulary_token() -> None:
    print("(c) every op / status / when-kind / scale (and trigger) in VOCABULARY.md appears in some exemplar:")
    ops, statuses, conds, scales, triggers = vocab_ops(), vocab_statuses(), vocab_conditions(), vocab_scales(), vocab_triggers()
    check(len(ops) >= 30, f"harvested the Effect ops table ({len(ops)})")
    check(len(statuses) >= 15, f"harvested the Statuses table ({len(statuses)})")
    check(len(conds) >= 12, f"harvested the Conditions table ({len(conds)})")
    live = set(re.findall(r"`([a-z][a-z0-9_]*)`", paths.VOCABULARY.read_text(encoding="utf-8")))
    check(scales <= live, f"schema scale sources missing from VOCABULARY.md: {scales - live}")
    check(triggers <= live, f"schema trigger kinds missing from VOCABULARY.md: {triggers - live}")
    used: set[str] = set()
    for e in _pool():
        used |= card_tokens(e["card"])
    for label, want in (("op", ops), ("status", statuses), ("when kind", conds), ("scale", scales), ("trigger", triggers)):
        missing = sorted(want - used)
        check(not missing, f"no exemplar uses {label}(s): {missing}")


# --------------------------------------------------------------- (d) every exemplar validates
def test_every_exemplar_passes_the_validator() -> None:
    print("(d) every exemplar passes CardValidator under the mod contract (pool class context):")
    v = harness_v2.exemplar_validator()
    pool = _pool()
    for e in pool:
        r = v.validate(dict(e["card"]))
        check(r.ok, f"{e['card']['id']}: {r.errors}")
        for w in r.warnings:
            if "power score" in w or "flat rare" in w or "REPRINT" in w.upper():
                print(f"  note: {e['card']['id']}: {w}")
    ids = [e["card"]["id"] for e in pool]
    names = [e["card"]["name"].strip().lower() for e in pool]
    check(len(ids) == len(set(ids)), "exemplar ids are unique")
    check(len(names) == len(set(names)), "exemplar names are unique")
    check(all(i.startswith("ex_") for i in ids), "exemplar ids carry the ex_ prefix")
    metaphors = {m.lower() for a in load_catalog().entries for m in a.metaphors}
    check(not (set(names) & metaphors), f"exemplar names collide with catalog metaphors: {set(names) & metaphors}")


# --------------------------------------------------------------- needs discipline + same-class targets
def test_needs_tags_and_card_targets() -> None:
    print("`needs` tags: from the fixed set, present iff the card touches class-only vocabulary; targets are pool ids:")
    by = _by_id()
    for e in _pool():
        cid = e["card"]["id"]
        check(e["needs"] in NEEDS_KINDS, f"{cid} needs '{e['needs']}' not in {sorted(NEEDS_KINDS)}")
        toks = card_tokens(e["card"])
        needed = {kind for kind, toks_k in CLASS_ONLY_TOKENS.items() if toks & toks_k}
        if needed:
            check(e["needs"] in needed, f"{cid} touches {needed}-only vocabulary but needs='{e['needs']}'")
            check(len(needed) == 1, f"{cid} mixes class-only subsystems {needed} (one class kind per exemplar)")
        else:
            check(e["needs"] == "", f"{cid} needs='{e['needs']}' but touches no class-only vocabulary")
        # add_card / transform_card / graft_card name OTHER exemplars in the same archetype family (the same-class rule)
        for eff in e["card"].get("effects", []) + ((e["card"].get("upgrade") or {}).get("effects") or []):
            for node in [eff] + list(eff.get("effects") or []):
                tgt = node.get("card_id")
                if tgt is None:
                    continue
                check(tgt in by, f"{cid}: {node.get('op')} targets '{tgt}', not a pool exemplar")
                if tgt in by:
                    check(bool(set(by[tgt]["archetypes"]) & set(e["archetypes"])),
                          f"{cid}: {node.get('op')} target '{tgt}' shares no archetype ({by[tgt]['archetypes']} vs {e['archetypes']})")
                if node.get("op") == "transform_card":
                    check(tgt != cid, f"{cid}: transform_card can't target itself")


# --------------------------------------------------------------- W0.9: dealing by class_kind UNION mechanic_kind
def test_pool_kind_unions_class_kind_and_mechanic_kind() -> None:
    print("_pool_kind(): class_kind (orb/status/summon) UNION every selected archetype's mechanic_kind:")
    pk = harness_v2._pool_kind
    check(pk("normal", ["retain_hold", "poison_attrition"]) == {"", "retain"}, "a plain class satisfies only '' (+ its base kinds)")
    check("balance" in pk("normal", ["balance_gauge", "block_bulwark", "poison_attrition"]), "balance_gauge -> 'balance'")
    check("forge" in pk("normal", ["forge_ramp", "retain_hold"]), "forge_ramp -> 'forge'")
    check("forge" not in pk("normal", ["battle_smith", "retain_hold"]), "battle_smith alone does NOT unlock forge exemplars")
    check(pk("orb", ["orb_channel", "forge_ramp"]) >= {"", "orb", "forge"}, "orb class + forge_ramp -> both kinds")
    check(pk("summon", ["summon_swarm", "balance_gauge"]) >= {"", "summon", "balance"}, "summon + balance union")
    check("forge" in pk("normal", ["custom_forge_thing"]), "an unknown id containing 'forge' keeps the legacy substring rule")
    check("status" not in pk("normal", ["status_signature"]), "class_kind comes from the blueprint, not the archetype")


def test_balance_and_forge_exemplars_deal_only_to_matching_classes() -> None:
    print("pick_exemplars(): needs:'balance' / 'forge' exemplars reach only a class whose archetypes carry that kind:")
    pool = _pool()
    balance_ids = {e["card"]["id"] for e in pool if e["needs"] == "balance"}
    forge_ids = {e["card"]["id"] for e in pool if e["needs"] == "forge"}
    check(len(balance_ids) >= 3 and len(forge_ids) >= 3, f"balance {len(balance_ids)} / forge {len(forge_ids)} exemplars exist")
    seed = harness_v2.seed_for("a knife's-edge monk")
    # eligibility is deterministic on a single-archetype brief: the archetype+rarity matches outrank everything else
    for rarity in ("common", "uncommon", "rare"):
        got = {c["id"] for c in harness_v2.pick_exemplars(["balance_gauge"], rarity, seed, salt=rarity)}
        check(bool(got & balance_ids), f"a balance_gauge brief ({rarity}) is dealt balance exemplars: {sorted(got)}")
        got = {c["id"] for c in harness_v2.pick_exemplars(["forge_ramp"], rarity, seed, salt=rarity)}
        check(bool(got & forge_ids), f"a forge_ramp brief ({rarity}) is dealt forge exemplars: {sorted(got)}")
    # a triad: the class satisfies the kind, so the kind's exemplars are in the ranked pool (never the other kind's)
    got: set[str] = set()
    dealt: set = set()
    for i in range(6):
        ex = harness_v2.pick_exemplars(["balance_gauge", "block_bulwark", "poison_attrition"], "uncommon", seed,
                                       salt=f"c{i}", avoid_triples=dealt)
        dealt.add(frozenset(c["id"] for c in ex))
        got |= {c["id"] for c in ex}
    check(len(dealt) == 6, "six distinct triples dealt to the balance triad")
    check(not (got & forge_ids), "a balance_gauge triad is never dealt forge exemplars")
    plain: set[str] = set()
    for rarity in ("common", "uncommon", "rare"):
        for i in range(4):
            ex = harness_v2.pick_exemplars(["retain_hold", "block_bulwark", "poison_attrition"], rarity, seed, salt=f"p{rarity}{i}")
            plain |= {c["id"] for c in ex}
    check(not (plain & (balance_ids | forge_ids)),
          f"a plain triad never sees balance/forge exemplars: {sorted(plain & (balance_ids | forge_ids))}")
    forge_got: set[str] = set()
    for i in range(6):
        ex = harness_v2.pick_exemplars(["forge_ramp", "retain_hold", "block_bulwark"], "uncommon", seed, salt=f"f{i}")
        forge_got |= {c["id"] for c in ex}
    check(not (forge_got & balance_ids), "a forge_ramp triad is never dealt balance exemplars")


def main() -> int:
    test_every_archetype_has_two_exemplars()
    test_every_exemplar_uses_each_tagged_archetypes_ops()
    test_pool_covers_every_vocabulary_token()
    test_every_exemplar_passes_the_validator()
    test_needs_tags_and_card_targets()
    test_pool_kind_unions_class_kind_and_mechanic_kind()
    test_balance_and_forge_exemplars_deal_only_to_matching_classes()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())

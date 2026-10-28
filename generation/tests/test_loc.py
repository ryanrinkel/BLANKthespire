"""Offline tests for btsgen.loc (I18N plan C2: per-forge creative-text translation + the bundle `loc` block).

Run:  uv run python -m pytest -q tests/test_loc.py     (from generation/)
The generator stub mirrors the real duck type: `make_gen(contract_mod, *, max_tokens)` returns an object with
first_attempt(brief) -> (text, messages) and repair(messages, prev_text, errors) -> (text, messages).
"""
from __future__ import annotations

import copy
import json

from btsgen import loc as L
from btsgen.frontend.fakes import _StageFake
from btsgen.ollama_mix import _resolve_role

# Shape copied from a fake forge_class() bundle (class_forge assembly, stage 3) plus the optional fields a
# real LLM forge carries (card flavor, status/summon pools, a custom orb with a description).
BUNDLE = {
    "kind": "class",
    "character": {
        "name": "Test Tempest",
        "description": "A storm channeler who hoards lightning.",
        "max_hp": 70, "max_energy": 3, "orb_slots": 3,
        "starting_deck": [{"slot": 1, "count": 5}],
        "color": {"h": 0.5556, "s": 0.8, "v": 1.0},
        "orb_pool": ["lightning",
                     {"name": "Ember", "passive_val": 2, "evoke_val": 8, "description": "Burns for {Passive}.",
                      "passive": [{"op": "damage", "amount": 2}], "evoke": [{"op": "damage", "amount": 8}]},
                     {"name": "Plasma", "passive_val": 1, "evoke_val": 2, "passive": [], "evoke": []}],
        "status_pool": [{"name": "Static", "type": "debuff", "description": "Takes 1 damage per stack."}],
        "summon_pool": [{"name": "Bone Thrall", "max_hp": 12, "description": "A raised servant."}],
        "potion_pool": [{"name": "Test Tempest Decoction", "emoji": "x", "rarity": "uncommon",
                         "description": "Channel 2 orbs.", "effects": [{"op": "channel_orb", "amount": 2}]}],
    },
    "cards": [
        {"id": "strike", "name": "Strike", "type": "attack", "cost": 1, "effects": [{"op": "damage", "amount": 6}]},
        {"id": "defend", "name": "Defend", "type": "skill", "cost": 1, "effects": [{"op": "block", "amount": 5}]},
        {"id": "arc_lash", "name": "Arc Lash", "flavor": "The sky remembers.", "type": "attack", "cost": 1,
         "effects": [{"op": "damage", "amount": 7}]},
        {"id": "x9", "name": "X-9", "type": "skill", "cost": 0, "effects": [{"op": "draw", "amount": 1}]},
        {"id": "blank_name", "name": "  ", "type": "skill", "cost": 0, "effects": []},
    ],
    "relic": {"id": "test_tempest_keystone", "name": "Test Tempest Sigil", "description": "Gain {Block} Block."},
}

EXPECTED_PATHS = {
    "character/name", "character/description",
    "cards/strike/name", "cards/defend/name", "cards/arc_lash/name", "cards/arc_lash/flavor", "cards/x9/name",
    "relic/name", "relic/description",
    "potions/Test Tempest Decoction/name", "potions/Test Tempest Decoction/description",
    "statuses/Static/name", "statuses/Static/description",
    "summons/Bone Thrall/name", "summons/Bone Thrall/description",
    "orbs/Ember/name", "orbs/Ember/description", "orbs/Plasma/name",
}

GOOD = {
    "character/name": "风暴测试者", "character/description": "囤积闪电的风暴引导者。",
    "cards/strike/name": "打击", "cards/defend/name": "防御", "cards/arc_lash/name": "电弧鞭",
    "cards/arc_lash/flavor": "天空记得。", "cards/x9/name": "X-9",
    "relic/name": "风暴印记", "relic/description": "获得{Block}点格挡。",
    "potions/Test Tempest Decoction/name": "风暴煎剂", "potions/Test Tempest Decoction/description": "生成2个充能球。",
    "statuses/Static/name": "静电", "statuses/Static/description": "每层受到1点伤害。",
    "summons/Bone Thrall/name": "骨仆", "summons/Bone Thrall/description": "被唤起的仆从。",
    "orbs/Ember/name": "余烬", "orbs/Ember/description": "灼烧{Passive}。", "orbs/Plasma/name": "等离子",
}


class StubGen:
    """Real generator surface: first_attempt(brief) / repair(messages, prev_text, errors)."""

    def __init__(self, contract_mod, replies, log):
        self._contract = contract_mod
        self._replies = replies
        self._log = log
        self.model = "stub"

    def _next(self):
        r = self._replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r if isinstance(r, str) else json.dumps(r, ensure_ascii=False)

    def first_attempt(self, brief):
        user = self._contract.user_brief(brief)
        self._log.append(("first", self._contract.system_prompt(), user))
        text = self._next()
        return text, [{"role": "user", "content": user}, {"role": "assistant", "content": text}]

    def repair(self, messages, prev_text, errors):
        self._log.append(("repair", errors))
        text = self._next()
        return text, messages + [{"role": "user", "content": "fix"}, {"role": "assistant", "content": text}]


def factory(*replies):
    log, made = [], []

    def make_gen(contract_mod, *, max_tokens):
        made.append((contract_mod, max_tokens))
        return StubGen(contract_mod, list(replies), log)
    make_gen.log, make_gen.made = log, made
    return make_gen


def test_tables():
    assert L.GAME_LOCALE["zh"] == "zhs" and "zhs" in L.LANG_NAMES and "zhs" in L.LOCALE_RULES
    assert L.game_locale("zh") == "zhs" and L.game_locale("zhs") == "zhs"
    assert L.game_locale("en") is None and L.game_locale("xx") is None and L.game_locale(None) is None
    assert L.has_cjk("打击") and not L.has_cjk("Strike") and not L.has_cjk("")


def test_collect_strings():
    got = L.collect_strings(BUNDLE)
    assert set(got) == EXPECTED_PATHS
    assert got["cards/arc_lash/flavor"] == "The sky remembers."
    assert not any(p.startswith("orbs/lightning") for p in got)  # base-orb strings are base-game localized
    assert L.collect_strings({}) == {} and L.collect_strings(None) == {}


def test_collect_archetypes_and_path_escaping():
    b = copy.deepcopy(BUNDLE)
    b["archetypes"] = [{"name": "Storm"}, {"name": ""}, {"name": "Arc"}]
    b["character"]["potion_pool"] = [{"name": "Mr. Bones / Brew", "description": "d text"}]
    got = L.collect_strings(b)
    assert "archetypes/0/name" in got and "archetypes/1/name" not in got and "archetypes/2/name" in got
    assert got["potions/Mr. Bones ~1 Brew/name"] == "Mr. Bones / Brew"
    nested = L._nest({"potions/Mr. Bones ~1 Brew/name": "骨头先生", "archetypes/2/name": "电弧"})
    assert nested["potions"]["Mr. Bones / Brew"]["name"] == "骨头先生"
    assert nested["archetypes"] == [{}, {}, {"name": "电弧"}]


def test_translate_happy_path_schema():
    mg, events = factory(GOOD), []
    out = L.translate_bundle(BUNDLE, "zh", mg, glossary="Block = 格挡", on_event=events.append,
                             concept="a storm channeler")
    assert out == {
        "character": {"name": "风暴测试者", "description": "囤积闪电的风暴引导者。"},
        "cards": {"strike": {"name": "打击"}, "defend": {"name": "防御"},
                  "arc_lash": {"name": "电弧鞭", "flavor": "天空记得。"}, "x9": {"name": "X-9"}},
        "relic": {"name": "风暴印记", "description": "获得{Block}点格挡。"},
        "potions": {"Test Tempest Decoction": {"name": "风暴煎剂", "description": "生成2个充能球。"}},
        "statuses": {"Static": {"name": "静电", "description": "每层受到1点伤害。"}},
        "summons": {"Bone Thrall": {"name": "骨仆", "description": "被唤起的仆从。"}},
        "orbs": {"Ember": {"name": "余烬", "description": "灼烧{Passive}。"}, "Plasma": {"name": "等离子"}},
    }
    assert events == [f"translation (zhs): {len(GOOD)}/{len(GOOD)} strings"]
    (kind, system, user), = mg.log
    assert kind == "first"
    assert "Block = 格挡" in system and "{placeholder}" in system  # glossary verbatim in the stable system part
    assert "a storm channeler" in user and "A storm channeler who hoards lightning." in user
    assert json.loads(user[user.index("{"):user.rindex("}") + 1]) == L.collect_strings(BUNDLE)
    contract_mod, max_tokens = mg.made[0]
    assert 4000 <= max_tokens <= 12000
    assert _resolve_role(contract_mod) == "structure"  # design model, reasoning low on the hosted route
    b = L.apply_loc(copy.deepcopy(BUNDLE), "zh", out)
    assert b["loc"]["zhs"] == out


def test_drops_fall_back_to_english():
    bad = dict(GOOD)
    bad["relic/description"] = "获得格挡。"                       # placeholder lost
    bad["orbs/Ember/description"] = "灼烧{Passive}{Passive}。"     # placeholder multiset differs
    bad["cards/strike/name"] = "Strike"                             # untranslated
    bad["cards/defend/name"] = "防御防御防御防御防御防御防御"       # 14 chars > cap 12
    bad["statuses/Static/description"] = "Takes damage"             # Latin leak, no CJK
    bad["summons/Bone Thrall/name"] = ""                            # empty
    del bad["orbs/Plasma/name"]                                     # missing
    bad["cards/x9/name"] = "X-9"                                    # code: identical is fine
    bad["character/name"] = "  风暴测试者  "                          # trimmed, kept
    events = []
    out = L.translate_bundle(BUNDLE, "zh", factory(bad), on_event=events.append)
    assert "description" not in out["relic"] and out["relic"]["name"] == "风暴印记"
    assert "description" not in out["orbs"]["Ember"] and "Plasma" not in out["orbs"]
    assert "strike" not in out["cards"] and "defend" not in out["cards"]
    assert out["cards"]["x9"] == {"name": "X-9"}
    assert "description" not in out["statuses"]["Static"]
    assert "name" not in out["summons"]["Bone Thrall"]
    assert out["character"]["name"] == "风暴测试者"
    n = len(GOOD)
    assert events[0].startswith(f"translation (zhs): {n - 7}/{n} strings, 7 fell back to English (")
    assert "placeholder changed" in events[0] and "untranslated" in events[0] and "name too long" in events[0]


def test_markup_must_match():
    b = {"kind": "class", "character": {"name": "Hero", "description": "Deal [gold]damage[/gold] now."}, "cards": []}
    out = L.translate_bundle(b, "zh", factory({"character/name": "英雄", "character/description": "造成伤害。"}))
    assert out == {"character": {"name": "英雄"}}


def test_retry_then_success_and_wrapper_key():
    mg = factory("Sure! here you go", {"translations": GOOD})
    out = L.translate_bundle(BUNDLE, "zh", mg)
    assert out["cards"]["arc_lash"]["name"] == "电弧鞭"
    assert [e[0] for e in mg.log] == ["first", "repair"]


def test_unparseable_twice_gives_none():
    mg, events = factory("nope", "still nope"), []
    assert L.translate_bundle(BUNDLE, "zh", mg, on_event=events.append) is None
    assert len(mg.log) == 2
    assert events and "skipped" in events[0] and events[0].startswith("translation (zhs) skipped:")


def test_truncated_reply_salvages_partial():
    text = json.dumps(GOOD, ensure_ascii=False)
    cut = text[: text.index('"relic/name"')]  # truncated mid-object, both tries
    out = L.translate_bundle(BUNDLE, "zh", factory(cut, cut))
    assert out["character"]["name"] == "风暴测试者" and "relic" not in out


def test_model_error_never_raises():
    events = []
    out = L.translate_bundle(BUNDLE, "zh", factory(RuntimeError("HTTP 503 overloaded")), on_event=events.append)
    assert out is None and events == ["translation (zhs) skipped: RuntimeError: HTTP 503 overloaded"]

    def broken_factory(contract_mod, *, max_tokens):
        raise ValueError("no key")
    assert L.translate_bundle(BUNDLE, "zh", broken_factory) is None


def test_english_or_empty_makes_no_call():
    mg = factory()
    assert L.translate_bundle(BUNDLE, "en", mg) is None
    assert L.translate_bundle(BUNDLE, "fr", mg) is None
    assert L.translate_bundle({"kind": "class", "character": {}, "cards": []}, "zh", mg) is None
    assert mg.made == []


def test_offline_stage_fake_factory():
    out = L.translate_bundle(BUNDLE, "zh", lambda c, *, max_tokens: _StageFake(c))
    assert out and out["relic"]["description"] == "测试：Gain {Block} Block."
    assert len(out["cards"]["arc_lash"]["name"]) <= 12


def test_translate_concept():
    mg = factory()
    assert L.translate_concept("a poison summoner", mg, "zh") == "a poison summoner"
    assert L.translate_concept("a poison summoner", mg, "en") == "a poison summoner"
    assert mg.made == []
    mg = factory("A storm mage orb class who uses poison.")
    assert L.translate_concept("会用毒的风暴法师 orb class", mg, "zh") == "A storm mage orb class who uses poison."
    assert _resolve_role(mg.made[0][0]) == "structure"
    # no Latin run on a non-English forge -> translated even without CJK (e.g. a kana-free emoji concept)
    mg = factory("```\na fire dancer\n```")
    assert L.translate_concept("🔥💃", mg, "zh") == "a fire dancer"
    # failures keep the original
    assert L.translate_concept("风暴法师", factory(RuntimeError("down")), "zh") == "风暴法师"
    assert L.translate_concept("风暴法师", factory("风暴法师"), "zh") == "风暴法师"
    assert L.translate_concept("风暴法师", factory(""), "zh") == "风暴法师"
    assert L.translate_concept("风暴法师", lambda c, *, max_tokens: _StageFake(c), "zh") \
        == "an offline fake translated concept"
    long = " ".join(["word"] * 80)
    assert len(L.translate_concept("风暴", factory(long), "zh").split()) == 60


def test_apply_loc_merges():
    b = {"kind": "class", "loc": {"zhs": {"cards": {"a": {"name": "甲"}}, "relic": {"name": "旧"}}}}
    L.apply_loc(b, "zh", {"cards": {"b": {"name": "乙"}}, "relic": {"name": "新"}})
    assert b["loc"]["zhs"] == {"cards": {"a": {"name": "甲"}, "b": {"name": "乙"}}, "relic": {"name": "新"}}
    assert L.apply_loc(b, "zh", None) is b and L.apply_loc(b, "zh", {}) is b


def test_load_glossary(tmp_path):
    assert L.load_glossary(tmp_path / "missing.md") == ""
    p = tmp_path / "GLOSSARY.md"
    p.write_text("Block | 格挡\n", encoding="utf-8")
    assert L.load_glossary(p) == "Block | 格挡\n"

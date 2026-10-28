"""Per-forge language (docs/plans/I18N_PLAN.md C2, phase 3, web side): /api/forge-class takes `lang`, the forge
translates a Chinese concept in and the class's creative strings out (btsgen.loc, called through forge.py's
module globals so they can be patched here), the bundle's `loc` block is stored and served, and `classes.lang`
is migrated onto old databases."""
from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine, inspect, text

from conftest import H, login, sse_events


def _class_row(app_module, class_id):
    from models import ForgedClass
    with app_module.session_scope() as s:
        c = s.query(ForgedClass).filter_by(id=class_id).one()
        return {"lang": c.lang, "concept": c.concept, "bundle": json.loads(c.bundle_json), "code": c.code,
                "slug": c.slug}


# --- the route --------------------------------------------------------------------------------------------

@pytest.mark.parametrize("sent, stored", [("zh", "zh"), ("ZH", "zh"), ("klingon", "en"), ("", "en"),
                                          (None, "en"), (["zh"], "en"), ("zhs", "en")])
def test_forge_class_stores_the_normalised_lang(client, app_module, stub_forge, sent, stored):
    login(client, "lang@example.com")
    body = {"concept": "a plague doctor", "mode": "fake"}
    if sent is not None:
        body["lang"] = sent
    ev = sse_events(client.post("/api/forge-class", json=body, headers=H))
    assert ev[-1][0] == "result"
    assert stub_forge.calls[-1]["lang"] == stored          # what the forge was asked for
    assert ev[-1][1]["lang"] == stored                     # the result payload says it
    assert _class_row(app_module, ev[-1][1]["id"])["lang"] == stored
    rows = client.get("/api/classes").get_json()["classes"]
    assert next(r for r in rows if r["id"] == ev[-1][1]["id"])["lang"] == stored


def test_loc_block_round_trips_through_every_payload(client, app_module, stub_forge, fake_bundle):
    login(client, "locrt@example.com")
    name = fake_bundle["character"]["name"]
    card_id = fake_bundle["cards"][0]["id"]
    loc = {"zhs": {"character": {"name": "瘟疫医生", "description": "以毒为刃。"},
                   "cards": {card_id: {"name": "毒刃"}}, "archetypes": [{"name": "毒"}]}}
    stub_forge.result = {**fake_bundle, "loc": loc}
    try:
        ev = sse_events(client.post("/api/forge-class", json={"concept": "瘟疫医生", "mode": "fake", "lang": "zh"},
                                    headers=H))
    finally:
        stub_forge.result = fake_bundle
    res = ev[-1][1]
    assert ev[-1][0] == "result" and res["loc"] == loc
    row = _class_row(app_module, res["id"])
    assert row["bundle"]["loc"] == loc and row["concept"] == "瘟疫医生"    # the player's own words are stored

    detail = client.get(f"/api/classes/{res['id']}").get_json()
    assert detail["lang"] == "zh" and detail["loc"] == loc
    deck = client.get(f"/api/deck/{row['slug']}").get_json()
    assert deck["lang"] == "zh" and deck["loc"] == loc
    listed = next(r for r in client.get("/api/classes").get_json()["classes"] if r["id"] == res["id"])
    # the list view gets the character slice only
    assert listed["loc"] == {"zhs": {"character": {"name": "瘟疫医生", "description": "以毒为刃。"}}}

    # renamed by the owner: the list shows the owner's name, so the translated name drops out of the slice
    assert client.patch(f"/api/classes/{res['id']}", json={"name": "My Doctor"}, headers=H).status_code == 200
    listed = next(r for r in client.get("/api/classes").get_json()["classes"] if r["id"] == res["id"])
    assert listed["loc"] == {"zhs": {"character": {"description": "以毒为刃。"}}}
    assert client.patch(f"/api/classes/{res['id']}", json={"name": name}, headers=H).status_code == 200

    # The Archive
    from models import ForgedClass
    with app_module.session_scope() as s:
        c = s.query(ForgedClass).filter_by(id=res["id"]).one()
        c.featured_at, c.featured_word = app_module._utcnow_naive(), "PLAGU"
    try:
        item = next(i for i in client.get("/api/featured").get_json()["featured"] if i["slug"] == row["slug"])
        assert item["lang"] == "zh" and item["loc"]["zhs"]["character"]["name"] == "瘟疫医生"
    finally:
        with app_module.session_scope() as s:
            c = s.query(ForgedClass).filter_by(id=res["id"]).one()
            c.featured_at, c.featured_word = None, None


def test_english_class_payloads_carry_lang_en_and_no_loc(client, stub_forge):
    login(client, "plainen@example.com")
    res = sse_events(client.post("/api/forge-class", json={"concept": "x", "mode": "fake"}, headers=H))[-1][1]
    assert res["lang"] == "en" and res["loc"] == {}
    listed = next(r for r in client.get("/api/classes").get_json()["classes"] if r["id"] == res["id"])
    assert listed["lang"] == "en" and "loc" not in listed


# --- the forge pipeline (real offline forge, translation calls spied) ---------------------------------------

@pytest.fixture()
def spies(monkeypatch):
    import forge

    class Spy:
        concept_calls: list = []
        bundle_calls: list = []

    def fake_concept(concept, gen, lang, *, on_event=None):
        Spy.concept_calls.append({"concept": concept, "lang": lang, "gen": gen})
        if on_event:
            on_event("concept translated to English: a plague doctor")
        return "a plague doctor"

    def fake_bundle_tr(bundle, lang, gen, *, glossary=None, on_event=None, concept=None):
        Spy.bundle_calls.append({"bundle": bundle, "lang": lang, "gen": gen, "glossary": glossary,
                                 "concept": concept})
        return {"character": {"name": "中文:" + bundle["character"]["name"]}}

    Spy.concept_calls, Spy.bundle_calls = [], []
    monkeypatch.setattr(forge, "translate_concept", fake_concept)
    monkeypatch.setattr(forge, "translate_bundle", fake_bundle_tr)
    return Spy


def test_zh_stream_translates_the_concept_in_and_the_class_out(client, app_module, spies):
    login(client, "zhstream@example.com")
    ev = sse_events(client.post("/api/forge-class", json={"concept": "一位瘟疫医生", "mode": "fake", "lang": "zh"},
                                headers=H))
    assert ev[-1][0] == "result", ev[-1]
    res = ev[-1][1]
    assert [c["lang"] for c in spies.concept_calls] == ["zh"] and spies.concept_calls[0]["concept"] == "一位瘟疫医生"
    assert len(spies.bundle_calls) == 1
    call = spies.bundle_calls[0]
    assert call["lang"] == "zh" and call["concept"] == "一位瘟疫医生"
    assert "archetypes" in call["bundle"]                  # the display archetypes ride along to be translated
    assert "力量" in (call["glossary"] or "")             # docs/copy/GLOSSARY.md (BTS_GLOSSARY_FILE) is loaded
    progress = [d.get("message") for e, d in ev if e == "progress"]
    assert "concept translated to English: a plague doctor" in progress
    assert any("translating the class's names" in (m or "") for m in progress)
    # stored: the original concept; the loc block in the bundle AND inside the import code
    row = _class_row(app_module, res["id"])
    assert row["concept"] == "一位瘟疫医生" and row["lang"] == "zh"
    zh_name = "中文:" + row["bundle"]["character"]["name"]
    assert row["bundle"]["loc"] == {"zhs": {"character": {"name": zh_name}}}
    from btsgen.bts1 import decode
    wire = json.loads(decode(row["code"])[0])
    assert wire["loc"]["zhs"]["character"]["name"] == zh_name
    assert "archetypes" not in wire and "forge_meta" not in wire


def test_en_stream_never_calls_the_translator(client, spies):
    login(client, "enstream@example.com")
    ev = sse_events(client.post("/api/forge-class", json={"concept": "a plague doctor", "mode": "fake"}, headers=H))
    assert ev[-1][0] == "result"
    assert spies.concept_calls == [] and spies.bundle_calls == []
    assert ev[-1][1]["loc"] == {}


def test_english_concept_on_a_zh_forge_still_asks(client, spies):
    """lang=zh always offers the concept to translate_concept (it decides; a Latin concept comes back as is)."""
    login(client, "zhlatin@example.com")
    ev = sse_events(client.post("/api/forge-class", json={"concept": "a plague doctor", "mode": "fake", "lang": "zh"},
                                headers=H))
    assert ev[-1][0] == "result"
    assert len(spies.concept_calls) == 1 and len(spies.bundle_calls) == 1


def test_pipeline_runs_on_the_english_concept(app_module, spies, monkeypatch):
    import forge
    seen = []
    real = forge.forge_class

    def capture(brief, **kw):
        seen.append(brief.concept)
        return real(brief, **kw)

    monkeypatch.setattr(forge, "forge_class", capture)
    out = forge.forge_to_bundle("一位瘟疫医生", fake=True, staged=True, lang="zh")
    assert seen == ["a plague doctor"]
    assert out["loc"]["zhs"]["character"]["name"].startswith("中文:")


def test_cjk_concept_on_an_english_forge_is_translated_but_not_the_class(app_module, spies):
    import forge
    out = forge.forge_to_bundle("一位瘟疫医生", fake=True, staged=True, lang="en")
    assert len(spies.concept_calls) == 1 and spies.bundle_calls == []
    assert "loc" not in out


def test_a_failing_translation_never_fails_the_forge(app_module, monkeypatch):
    import forge

    def boom(*a, **k):
        raise RuntimeError("model fell over")

    monkeypatch.setattr(forge, "translate_concept", boom)
    monkeypatch.setattr(forge, "translate_bundle", boom)
    out = forge.forge_to_bundle("一位瘟疫医生", fake=True, staged=True, lang="zh")
    assert out["cards"] and "loc" not in out


def test_real_fake_translation_produces_a_zhs_block(app_module):
    """No spies: the offline fake answers loc.py's translate contract (测试卡N names, 测试： prose)."""
    import forge
    out = forge.forge_to_bundle("a plague doctor", fake=True, staged=True, lang="zh")
    zhs = out["loc"]["zhs"]
    assert zhs["character"]["name"].startswith("测试：")
    assert any(v.get("name", "").startswith("测试卡") for v in zhs["cards"].values())


# --- the ledger role ---------------------------------------------------------------------------------------

def test_translation_usage_is_booked_as_role_translate(app_module, monkeypatch):
    import forge
    from btsgen.frontend.fakes import _StageFake

    def factory(key, hosted, fake, model=None, on_usage=None):
        def make_gen(contract_mod, *, max_tokens):
            g = _StageFake(contract_mod)
            real_first = g.first_attempt

            def first_attempt(brief):
                on_usage({"prompt_tokens": 10, "completion_tokens": 5, "_role": forge._role_of(contract_mod),
                          "_model": "fake-model"})
                return real_first(brief)
            g.first_attempt = first_attempt
            return g
        return make_gen

    monkeypatch.setattr(forge, "_make_gen_factory", factory)
    meter = forge.UsageMeter()
    forge.forge_to_bundle("一位瘟疫医生", fake=True, staged=True, lang="zh", on_usage=meter)
    roles = {r["role"]: r["calls"] for r in meter.rows()}
    assert roles.get("translate") == 2                      # the concept in + the class out
    assert roles.get("structure")                           # the design stages kept their own role


def test_role_override_only_while_active():
    import forge
    got = []
    w = forge._RoleOverride(got.append)
    w({"_role": "structure", "prompt_tokens": 1})
    with w.role("translate"):
        w({"_role": "structure", "prompt_tokens": 2})
    w({"_role": "cards"})
    assert [u["_role"] for u in got] == ["structure", "translate", "cards"]


# --- the migration -----------------------------------------------------------------------------------------

def test_migration_adds_lang_to_an_old_classes_table(tmp_path, monkeypatch):
    import db
    eng = create_engine(f"sqlite:///{(tmp_path / 'old.db').as_posix()}")
    with eng.begin() as conn:
        conn.execute(text(
            "CREATE TABLE classes (id INTEGER PRIMARY KEY, user_id INTEGER, name VARCHAR(255), concept TEXT, "
            "vocab_version INTEGER, bundle_json TEXT, code TEXT, splash_hash VARCHAR(64), sprite_hash VARCHAR(64), "
            "card_art_hash VARCHAR(64), slug VARCHAR(32), nominated_at DATETIME, nomination_note VARCHAR(200), "
            "featured_at DATETIME, featured_word VARCHAR(5), created_at DATETIME, updated_at DATETIME)"))
        conn.execute(text("INSERT INTO classes (id, user_id, name, concept, vocab_version, bundle_json, code, slug) "
                          "VALUES (1, 1, 'Old', 'old', 2, '{}', 'BTSC.x', 'abc')"))
    monkeypatch.setattr(db, "engine", eng)
    db._ensure_class_columns()
    assert "lang" in {c["name"] for c in inspect(eng).get_columns("classes")}
    with eng.connect() as conn:
        assert conn.execute(text("SELECT lang FROM classes WHERE id = 1")).scalar() == "en"
    db._ensure_class_columns()  # idempotent

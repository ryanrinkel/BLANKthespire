"""Featured forges: the operator-curated web/featured.json, its loader (app._load_featured), the public
GET /api/featured showcase, and the `featured` flag on /api/deck/<slug>.

Classes are inserted directly (no forge); the featured list is set by monkeypatching app.FEATURED."""
from __future__ import annotations

import json

from conftest import login


def _make_class(app_module, email: str, name: str, *, desc: str = "", n_cards: int = 3,
                with_art: bool = True) -> str:
    from models import ForgedClass, User, new_slug
    cards = [{"id": f"c{i}", "name": f"Card {i}", "type": "attack", "rarity": "common", "cost": 1, "effects": []}
             for i in range(n_cards)]
    with app_module.session_scope() as s:
        uid = s.query(User).filter_by(email=email).one().id
        cls = ForgedClass(user_id=uid, name=name, concept="c", code="BTSC.x", slug=new_slug(),
                          bundle_json=json.dumps({"character": {"name": name, "description": desc},
                                                  "cards": cards}),
                          splash_hash="a" * 16 if with_art else None,
                          sprite_hash="b" * 16 if with_art else None,
                          card_art_hash="c" * 16 if with_art else None)
        s.add(cls)
        s.flush()
        return cls.slug


def _row(word: str, slug: str, blurb: str = "") -> dict:
    return {"word": word, "slug": slug, "blurb": blurb}


def test_featured_list_keeps_file_order_and_skips_dead_slugs(client, app_module, monkeypatch):
    login(client, "feat@example.com")
    a = _make_class(app_module, "feat@example.com", "Alpha", desc="first one", n_cards=4)
    b = _make_class(app_module, "feat@example.com", "Bravo", with_art=False)
    monkeypatch.setattr(app_module, "FEATURED", [_row("BRAVO", b, "second"), _row("GHOST", "nope-not-a-slug"),
                                                 _row("ALPHA", a, "first")])
    anon = app_module.app.test_client()
    r = anon.get("/api/featured")
    assert r.status_code == 200
    assert r.headers["Cache-Control"] == "public, max-age=300"
    items = r.get_json()["featured"]
    assert [i["word"] for i in items] == ["BRAVO", "ALPHA"]  # file order, dead slug dropped

    alpha = items[1]
    assert alpha["slug"] == a and alpha["blurb"] == "first" and alpha["name"] == "Alpha"
    assert alpha["description"] == "first one" and alpha["card_count"] == 4
    assert alpha["share_url"] == f"/deck/{a}"
    assert alpha["splash_thumb_url"] == f"/api/deck/{a}/art/splash?v=aaaaaaaa"
    assert alpha["sprite_thumb_url"] == f"/api/deck/{a}/art/sprite?v=bbbbbbbb"
    assert "card_art" not in alpha  # cards=None: no per-card map

    bravo = items[0]
    assert bravo["description"] == "" and not any(k.endswith("thumb_url") for k in bravo)


def test_featured_payload_has_no_id_or_owner_data(client, app_module, monkeypatch):
    login(client, "owner-secret@example.com")
    a = _make_class(app_module, "owner-secret@example.com", "Secretive")
    monkeypatch.setattr(app_module, "FEATURED", [_row("SHHHH", a)])
    r = app_module.app.test_client().get("/api/featured")
    item = r.get_json()["featured"][0]
    for k in ("id", "user_id", "user", "email", "owner", "code", "concept"):
        assert k not in item
    assert "owner-secret" not in r.get_data(as_text=True)


def test_featured_empty_list(client, app_module, monkeypatch):
    monkeypatch.setattr(app_module, "FEATURED", [])
    r = client.get("/api/featured")
    assert r.status_code == 200 and r.get_json() == {"featured": []}


def test_deck_resolve_reports_featured_flag(client, app_module, monkeypatch):
    login(client, "flag@example.com")
    a = _make_class(app_module, "flag@example.com", "Flagged")
    b = _make_class(app_module, "flag@example.com", "Plain")
    monkeypatch.setattr(app_module, "FEATURED", [_row("FLAGS", a)])
    anon = app_module.app.test_client()
    assert anon.get(f"/api/deck/{a}").get_json()["featured"] is True
    assert anon.get(f"/api/deck/{b}").get_json()["featured"] is False


def test_load_featured_skips_invalid_rows(app_module, tmp_path):
    p = tmp_path / "featured.json"
    p.write_text(json.dumps([
        _row("BRAVE", "slugA", " Blurb A "),
        _row("brave", "slugB"),           # lowercase
        _row("BRAV", "slugC"),            # 4 letters
        _row("BRAVES", "slugD"),          # 6 letters
        _row("BR4VE", "slugE"),           # digit
        _row("CRAVE", ""),                # empty slug
        _row("CRAVE", "x" * 33),          # slug too long
        {"word": "GOOSE"},                # no slug
        "not an object",
        _row("MOOSE", "x" * 32),          # exactly 32 is fine
        {"word": "GHOST", "slug": "slugF"},  # blurb optional
    ]), encoding="utf-8")
    rows = app_module._load_featured(p)
    assert rows == [_row("BRAVE", "slugA", "Blurb A"), _row("MOOSE", "x" * 32), _row("GHOST", "slugF")]


def test_load_featured_missing_or_bad_file_is_empty(app_module, tmp_path):
    assert app_module._load_featured(tmp_path / "nope.json") == []
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert app_module._load_featured(bad) == []
    obj = tmp_path / "obj.json"
    obj.write_text('{"word": "BRAVE"}', encoding="utf-8")
    assert app_module._load_featured(obj) == []


def test_shipped_featured_file_parses(app_module):
    rows = app_module._load_featured(app_module.WEB_DIR / "featured.json")
    assert [r["word"] for r in rows] == ["BRAVE", "CRAVE", "GOOSE", "MOOSE"]

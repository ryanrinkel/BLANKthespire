"""The Archive's public side: GET /api/featured (DB-backed, newest featured first, ?limit), the `featured` flag
on /api/deck/<slug>, the featured.json seed (app._load_featured + app.seed_featured_from_file).

Classes are inserted directly (no forge) and featured by setting featured_at / featured_word (or through the
admin route in test_nominate.py). The test DB is shared across the session, so every test here starts with
nothing featured or nominated."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from conftest import login


@pytest.fixture(autouse=True)
def _empty_archive(app_module):
    from models import ForgedClass
    with app_module.session_scope() as s:
        s.query(ForgedClass).update({ForgedClass.featured_at: None, ForgedClass.featured_word: None,
                                     ForgedClass.nominated_at: None, ForgedClass.nomination_note: None},
                                    synchronize_session=False)
    yield


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


def _feature(app_module, slug: str, word: str, *, ago_s: int = 0) -> None:
    """Put a class in The Archive directly: featured `ago_s` seconds ago."""
    from models import ForgedClass
    with app_module.session_scope() as s:
        cls = s.query(ForgedClass).filter_by(slug=slug).one()
        cls.featured_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=ago_s)
        cls.featured_word = word


def _row(word: str, slug: str, blurb: str = "") -> dict:
    return {"word": word, "slug": slug, "blurb": blurb}


def _words(client, qs: str = "") -> list[str]:
    return [i["word"] for i in client.get("/api/featured" + qs).get_json()["featured"]]


def test_featured_list_is_newest_first_with_public_fields(client, app_module):
    login(client, "feat@example.com")
    a = _make_class(app_module, "feat@example.com", "Alpha", desc="first one", n_cards=4)
    b = _make_class(app_module, "feat@example.com", "Bravo", with_art=False)
    _make_class(app_module, "feat@example.com", "Unpicked")      # never featured: absent
    _feature(app_module, a, "ALPHA", ago_s=60)
    _feature(app_module, b, "BRAVO", ago_s=5)                    # featured later -> first
    anon = app_module.app.test_client()
    r = anon.get("/api/featured")
    assert r.status_code == 200
    assert r.headers["Cache-Control"] == "public, max-age=300"
    items = r.get_json()["featured"]
    assert [i["word"] for i in items] == ["BRAVO", "ALPHA"]

    alpha = items[1]
    assert alpha["slug"] == a and alpha["blurb"] == "Alpha" and alpha["name"] == "Alpha"
    assert alpha["description"] == "first one" and alpha["card_count"] == 4
    assert alpha["share_url"] == f"/deck/{a}"
    assert alpha["splash_thumb_url"] == f"/api/deck/{a}/art/splash?v=aaaaaaaa"
    assert alpha["sprite_thumb_url"] == f"/api/deck/{a}/art/sprite?v=bbbbbbbb"
    assert "card_art" not in alpha  # cards=None: no per-card map

    bravo = items[0]
    assert bravo["description"] == "" and not any(k.endswith("thumb_url") for k in bravo)


def test_unfeatured_and_deleted_classes_drop_out(client, app_module):
    from models import ForgedClass
    login(client, "drop@example.com")
    a = _make_class(app_module, "drop@example.com", "Stays")
    b = _make_class(app_module, "drop@example.com", "Goes")
    c = _make_class(app_module, "drop@example.com", "Deleted")
    for slug, word in ((a, "STAYS"), (b, "GOESS"), (c, "DELET")):
        _feature(app_module, slug, word)
    with app_module.session_scope() as s:
        s.query(ForgedClass).filter_by(slug=b).one().featured_at = None
        cid = s.query(ForgedClass).filter_by(slug=c).one().id
    assert client.delete(f"/api/classes/{cid}", headers={"X-Requested-With": "fetch"}).status_code == 200
    assert _words(client) == ["STAYS"]


def test_limit(client, app_module):
    login(client, "limit@example.com")
    for i, w in enumerate(["AAAAA", "BBBBB", "CCCCC", "DDDDD", "EEEEE", "FFFFF"]):
        _feature(app_module, _make_class(app_module, "limit@example.com", w.title()), w, ago_s=100 - i)
    assert _words(client) == ["FFFFF", "EEEEE", "DDDDD", "CCCCC", "BBBBB", "AAAAA"]
    assert _words(client, "?limit=4") == ["FFFFF", "EEEEE", "DDDDD", "CCCCC"]
    assert _words(client, "?limit=1") == ["FFFFF"]
    assert len(_words(client, "?limit=0")) == 1        # clamped up to 1
    assert len(_words(client, "?limit=999")) == 6      # clamped down to 50
    assert len(_words(client, "?limit=nope")) == 6     # junk -> the default


def test_featured_payload_has_no_id_or_owner_data(client, app_module):
    login(client, "owner-secret@example.com")
    a = _make_class(app_module, "owner-secret@example.com", "Secretive")
    _feature(app_module, a, "SHHHH")
    r = app_module.app.test_client().get("/api/featured")
    item = r.get_json()["featured"][0]
    for k in ("id", "user_id", "user", "email", "owner", "code", "concept", "nomination_note"):
        assert k not in item
    assert "owner-secret" not in r.get_data(as_text=True)


def test_featured_empty_list(client):
    r = client.get("/api/featured")
    assert r.status_code == 200 and r.get_json() == {"featured": []}


def test_deck_resolve_reports_featured_flag(client, app_module):
    from models import ForgedClass
    login(client, "flag@example.com")
    a = _make_class(app_module, "flag@example.com", "Flagged")
    b = _make_class(app_module, "flag@example.com", "Plain")
    _feature(app_module, a, "FLAGS")
    with app_module.session_scope() as s:   # a pending nomination is not public
        s.query(ForgedClass).filter_by(slug=b).one().nominated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    anon = app_module.app.test_client()
    da, db_ = anon.get(f"/api/deck/{a}").get_json(), anon.get(f"/api/deck/{b}").get_json()
    assert da["featured"] is True and da["featured_word"] == "FLAGS"
    assert db_["featured"] is False and db_["featured_word"] is None
    assert "nominated" not in da and "nominated" not in db_


# --- the featured.json seed ---------------------------------------------------------------------------

def test_seed_from_file_keeps_file_order_and_is_idempotent(client, app_module, tmp_path):
    login(client, "seed@example.com")
    first = _make_class(app_module, "seed@example.com", "First")
    second = _make_class(app_module, "seed@example.com", "Second")
    p = tmp_path / "featured.json"
    p.write_text(json.dumps([_row("FIRST", first), _row("GHOST", "not-a-real-slug"), _row("SECND", second)]),
                 encoding="utf-8")
    assert app_module.seed_featured_from_file(p) == 2
    assert _words(client) == ["FIRST", "SECND"]          # file order survives newest-first
    assert app_module.seed_featured_from_file(p) == 0    # second run: something is featured -> no-op
    assert _words(client) == ["FIRST", "SECND"]


def test_seed_does_nothing_when_something_is_featured(client, app_module, tmp_path):
    login(client, "seed2@example.com")
    picked = _make_class(app_module, "seed2@example.com", "Picked")
    other = _make_class(app_module, "seed2@example.com", "Other")
    _feature(app_module, picked, "PICKD")
    p = tmp_path / "featured.json"
    p.write_text(json.dumps([_row("OTHER", other)]), encoding="utf-8")
    assert app_module.seed_featured_from_file(p) == 0
    assert _words(client) == ["PICKD"]
    # --force (tools/migrate_featured.py) applies it, but never re-words an already featured class
    p.write_text(json.dumps([_row("OTHER", other), _row("RENAM", picked)]), encoding="utf-8")
    assert app_module.seed_featured_from_file(p, force=True) == 1
    assert _words(client) == ["OTHER", "PICKD"]


def test_seed_keeps_the_owners_library_order(client, app_module, tmp_path):
    """Featuring writes featured_at without touching updated_at (My Classes sorts by it)."""
    from models import ForgedClass
    login(client, "order@example.com")
    slug = _make_class(app_module, "order@example.com", "Ordered")
    with app_module.session_scope() as s:
        cls = s.query(ForgedClass).filter_by(slug=slug).one()
        cls.updated_at = datetime(2026, 1, 1)
    p = tmp_path / "featured.json"
    p.write_text(json.dumps([_row("ORDER", slug)]), encoding="utf-8")
    assert app_module.seed_featured_from_file(p) == 1
    with app_module.session_scope() as s:
        assert s.query(ForgedClass).filter_by(slug=slug).one().updated_at == datetime(2026, 1, 1)


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
    assert app_module.seed_featured_from_file(tmp_path / "nope.json") == 0


def test_shipped_featured_file_parses(app_module):
    rows = app_module._load_featured(app_module.WEB_DIR / "featured.json")
    assert [r["word"] for r in rows] == ["BRAVE", "CRAVE", "GOOSE", "MOOSE"]

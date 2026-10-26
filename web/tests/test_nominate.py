"""The Archive's queue: owner nominations (POST/DELETE /api/classes/<id>/nominate) and the operator side
(/api/admin/nominations, /api/admin/classes/<id>/feature|pass|unfeature) with its admin_actions rows.

conftest pins BTSWEB_ADMIN_EMAILS=unlimited@example.com. The DB is shared across the session, so every test
here starts with nothing featured or nominated."""
from __future__ import annotations

import json
import time

import pytest

from conftest import H, login

ADMIN = "unlimited@example.com"


@pytest.fixture(autouse=True)
def _empty_archive(app_module):
    from models import ForgedClass
    with app_module.session_scope() as s:
        s.query(ForgedClass).update({ForgedClass.featured_at: None, ForgedClass.featured_word: None,
                                     ForgedClass.nominated_at: None, ForgedClass.nomination_note: None},
                                    synchronize_session=False)
    yield


def _make_class(app_module, email: str, name: str, *, concept: str = "a goose knight", desc: str = "honk",
                with_art: bool = True) -> int:
    from models import ForgedClass, User, new_slug
    with app_module.session_scope() as s:
        uid = s.query(User).filter_by(email=email).one().id
        cls = ForgedClass(user_id=uid, name=name, concept=concept, code="BTSC.x", slug=new_slug(),
                          bundle_json=json.dumps({"character": {"name": name, "description": desc},
                                                  "cards": [{"id": "c1"}, {"id": "c2"}]}),
                          splash_hash="a" * 16 if with_art else None, sprite_hash=None,
                          card_art_hash="c" * 16 if with_art else None)
        s.add(cls)
        s.flush()
        return cls.id


def _owner_class(client, app_module, email: str, name: str = "Goose Knight", **kw) -> int:
    login(client, email)
    return _make_class(app_module, email, name, **kw)


def _nominate(client, cid: int, note=None):
    body = {} if note is None else {"note": note}
    return client.post(f"/api/classes/{cid}/nominate", json=body, headers=H)


def _summary(client, cid: int) -> dict:
    return next(c for c in client.get("/api/classes").get_json()["classes"] if c["id"] == cid)


# --- owner side -------------------------------------------------------------------------------------------

def test_nominate_and_withdraw_round_trip(client, app_module):
    cid = _owner_class(client, app_module, "nom@example.com")
    s0 = _summary(client, cid)
    assert (s0["nominated"], s0["featured"], s0["featured_word"]) == (False, False, None)

    r = _nominate(client, cid, "  it honks  ")
    assert r.status_code == 200
    d = r.get_json()
    assert d["id"] == cid and d["nominated"] is True and d["featured"] is False
    assert _summary(client, cid)["nominated"] is True
    detail = client.get(f"/api/classes/{cid}").get_json()
    assert detail["nominated"] is True and detail["featured"] is False and detail["featured_word"] is None
    from models import ForgedClass
    with app_module.session_scope() as s:
        row = s.query(ForgedClass).filter_by(id=cid).one()
        assert row.nomination_note == "it honks" and row.nominated_at is not None

    r = client.delete(f"/api/classes/{cid}/nominate", headers=H)
    assert r.status_code == 200 and r.get_json()["nominated"] is False
    with app_module.session_scope() as s:
        row = s.query(ForgedClass).filter_by(id=cid).one()
        assert row.nominated_at is None and row.nomination_note is None
    # ...and renominating is allowed
    assert _nominate(client, cid).get_json()["nominated"] is True


def test_nominating_keeps_the_library_order(client, app_module):
    from datetime import datetime
    from models import ForgedClass
    cid = _owner_class(client, app_module, "nomorder@example.com")
    with app_module.session_scope() as s:
        s.query(ForgedClass).filter_by(id=cid).one().updated_at = datetime(2026, 1, 1)
    _nominate(client, cid)
    with app_module.session_scope() as s:
        assert s.query(ForgedClass).filter_by(id=cid).one().updated_at == datetime(2026, 1, 1)


def test_note_is_truncated_to_200(client, app_module):
    from models import ForgedClass
    cid = _owner_class(client, app_module, "longnote@example.com")
    assert _nominate(client, cid, "x" * 500).status_code == 200
    with app_module.session_scope() as s:
        assert s.query(ForgedClass).filter_by(id=cid).one().nomination_note == "x" * 200
    assert _nominate(client, cid, 12345).status_code == 200      # a non-string note is just dropped
    with app_module.session_scope() as s:
        assert s.query(ForgedClass).filter_by(id=cid).one().nomination_note is None


def test_only_the_owner_can_nominate(client, app_module):
    cid = _owner_class(client, app_module, "realowner@example.com")
    login(client, "stranger@example.com")
    assert _nominate(client, cid).status_code == 404
    assert client.delete(f"/api/classes/{cid}/nominate", headers=H).status_code == 404
    assert _nominate(client, 999999).status_code == 404
    anon = app_module.app.test_client()
    assert anon.post(f"/api/classes/{cid}/nominate", json={}, headers=H).status_code == 401
    assert anon.delete(f"/api/classes/{cid}/nominate", headers=H).status_code == 401


def test_nominate_needs_the_csrf_header(client, app_module):
    cid = _owner_class(client, app_module, "csrfnom@example.com")
    assert client.post(f"/api/classes/{cid}/nominate", json={}).status_code == 403


def test_a_featured_class_cannot_be_nominated_or_withdrawn(client, app_module):
    from datetime import datetime, timezone
    from models import ForgedClass
    cid = _owner_class(client, app_module, "already@example.com")
    with app_module.session_scope() as s:
        row = s.query(ForgedClass).filter_by(id=cid).one()
        row.featured_at, row.featured_word = datetime.now(timezone.utc).replace(tzinfo=None), "GOOSE"
    r = _nominate(client, cid)
    assert r.status_code == 409 and r.get_json()["error"] == "already in The Archive"
    assert client.delete(f"/api/classes/{cid}/nominate", headers=H).status_code == 409
    s = _summary(client, cid)
    assert (s["nominated"], s["featured"], s["featured_word"]) == (False, True, "GOOSE")


# --- admin side -------------------------------------------------------------------------------------------

def _queue(client) -> dict:
    r = client.get("/api/admin/nominations")
    assert r.status_code == 200
    return r.get_json()


def test_admin_list_shape(client, app_module):
    old = _owner_class(client, app_module, "q1@example.com", "Older Pick", concept="c" * 300, desc="d" * 300)
    _nominate(client, old, "first")
    time.sleep(1.1)  # nominated_at has second resolution in SQLite
    new = _owner_class(client, app_module, "q2@example.com", "Newer Pick", with_art=False)
    _nominate(client, new)
    _owner_class(client, app_module, "q3@example.com", "Not Nominated")
    login(client, ADMIN)
    q = _queue(client)
    assert set(q) == {"pending", "featured"} and q["featured"] == []
    assert [r["id"] for r in q["pending"]] == [new, old]      # newest nomination first
    row = q["pending"][1]
    assert set(row) == {"id", "name", "slug", "share_url", "owner_email", "concept", "description", "card_count",
                        "has_splash", "has_sprite", "has_card_art", "nomination_note", "nominated_at",
                        "featured_at", "featured_word"}
    assert row["name"] == "Older Pick" and row["owner_email"] == "q1@example.com"
    assert row["share_url"] == f"/deck/{row['slug']}" and row["card_count"] == 2
    assert len(row["concept"]) == 140 and row["concept"].endswith("…")
    assert len(row["description"]) == 140
    assert (row["has_splash"], row["has_sprite"], row["has_card_art"]) == (True, False, True)
    assert row["nomination_note"] == "first" and row["nominated_at"] and row["featured_at"] is None
    assert q["pending"][0]["has_splash"] is False and q["pending"][0]["nomination_note"] == ""


def test_feature_pass_unfeature_happy_paths(client, app_module):
    a = _owner_class(client, app_module, "hp@example.com", "Goose Knight")
    _nominate(client, a, "please")
    b = _owner_class(client, app_module, "hp@example.com", "Moose Monk")
    _nominate(client, b)
    c = _owner_class(client, app_module, "hp@example.com", "Never Nominated")
    login(client, ADMIN)

    r = client.post(f"/api/admin/classes/{a}/feature", json={"word": "goose"}, headers=H)
    assert r.status_code == 200
    d = r.get_json()
    assert d["featured_word"] == "GOOSE" and d["featured_at"] and d["nominated_at"] is None
    assert d["nomination_note"] == "please"          # kept as the record of why
    # the admin may feature a class nobody nominated
    assert client.post(f"/api/admin/classes/{c}/feature", json={"word": "NEVER"}, headers=H).status_code == 200

    q = _queue(client)
    assert [r["id"] for r in q["pending"]] == [b]
    assert {r["id"] for r in q["featured"]} == {a, c}
    assert [i["word"] for i in client.get("/api/featured").get_json()["featured"]][:2] in (
        ["NEVER", "GOOSE"], ["GOOSE", "NEVER"])     # same second -> id breaks the tie

    r = client.post(f"/api/admin/classes/{b}/pass", headers=H)
    assert r.status_code == 200 and r.get_json()["nominated_at"] is None
    assert _queue(client)["pending"] == []
    assert client.post(f"/api/admin/classes/{b}/pass", headers=H).status_code == 404   # nothing pending now

    r = client.post(f"/api/admin/classes/{a}/unfeature", headers=H)
    assert r.status_code == 200 and r.get_json()["featured_at"] is None and r.get_json()["featured_word"] == ""
    assert [r["id"] for r in _queue(client)["featured"]] == [c]
    assert client.post(f"/api/admin/classes/{a}/unfeature", headers=H).status_code == 404
    assert client.post("/api/admin/classes/999999/feature", json={"word": "GHOST"}, headers=H).status_code == 404

    # the owner sees the state on their own rows
    login(client, "hp@example.com")
    sa, sc = _summary(client, a), _summary(client, c)
    assert (sa["nominated"], sa["featured"]) == (False, False)
    assert (sc["featured"], sc["featured_word"]) == (True, "NEVER")


def test_feature_rejects_bad_words(client, app_module):
    cid = _owner_class(client, app_module, "badword@example.com")
    login(client, ADMIN)
    for word in ("GOOS", "GOOSES", "G00SE", "", None, 12345, "GO SE"):
        r = client.post(f"/api/admin/classes/{cid}/feature", json={"word": word}, headers=H)
        assert r.status_code == 400, word
    assert _queue(client)["featured"] == []


def test_non_admin_is_forbidden(client, app_module):
    cid = _owner_class(client, app_module, "notadmin@example.com")
    login(client, "tester@example.com")     # env-unlimited, never an operator
    assert client.get("/api/admin/nominations").status_code == 403
    for act, body in (("feature", {"word": "GOOSE"}), ("pass", {}), ("unfeature", {})):
        assert client.post(f"/api/admin/classes/{cid}/{act}", json=body, headers=H).status_code == 403
    anon = app_module.app.test_client()
    assert anon.get("/api/admin/nominations").status_code == 401
    assert anon.post(f"/api/admin/classes/{cid}/feature", json={"word": "GOOSE"}, headers=H).status_code == 401


def test_admin_writes_need_a_fresh_sign_in(client, app_module):
    cid = _owner_class(client, app_module, "stalefeat@example.com")
    login(client, ADMIN)
    with client.session_transaction() as sess:
        sess["auth_at"] = int(time.time() - app_module.ADMIN_WRITE_MAX_AGE_S - 60)
    for act, body in (("feature", {"word": "GOOSE"}), ("pass", {}), ("unfeature", {})):
        r = client.post(f"/api/admin/classes/{cid}/{act}", json=body, headers=H)
        assert r.status_code == 403 and r.get_json()["reauth"] is True
    assert client.get("/api/admin/nominations").status_code == 200    # reading is fine
    login(client, ADMIN)
    assert client.post(f"/api/admin/classes/{cid}/feature", json={"word": "GOOSE"}, headers=H).status_code == 200


def test_every_archive_write_is_audited(client, app_module):
    cid = _owner_class(client, app_module, "audit-arch@example.com", "Audited Goose")
    _nominate(client, cid, "why not")
    login(client, ADMIN)
    client.post(f"/api/admin/classes/{cid}/pass", headers=H)
    client.post(f"/api/admin/classes/{cid}/feature", json={"word": "GOOSE"}, headers=H)
    client.post(f"/api/admin/classes/{cid}/unfeature", headers=H)
    rows = [a for a in client.get("/api/admin/actions?limit=50").get_json()["actions"]
            if a["target_email"] == "audit-arch@example.com"]
    assert [a["action"] for a in rows] == ["unfeature_class", "feature_class", "pass_nomination"]
    unf, feat, pas = rows
    assert (feat["old_value"], feat["new_value"]) == (0, 1)
    assert (unf["old_value"], unf["new_value"]) == (1, 0)
    assert (pas["old_value"], pas["new_value"]) == (1, 0)
    assert all(a["actor_email"] == ADMIN for a in rows)
    assert f"class #{cid} Audited Goose" in feat["note"] and "GOOSE" in feat["note"]
    assert "why not" in pas["note"]


def test_stats_count_the_queue(client, app_module):
    a = _owner_class(client, app_module, "statq@example.com", "Stat A")
    _nominate(client, a)
    b = _owner_class(client, app_module, "statq@example.com", "Stat B")
    login(client, ADMIN)
    client.post(f"/api/admin/classes/{b}/feature", json={"word": "STATB"}, headers=H)
    assert client.get("/api/admin/stats").get_json()["archive"] == {"pending": 1, "featured": 1}

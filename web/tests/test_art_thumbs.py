"""Art in the web UI: the list/detail shapes carry thumbnail URLs and the thumb routes serve small WebP
renders of the game-sized art (app._art_fields / _art_thumb_response / _card_thumb_response).

No forge runs here: a class row is inserted with its hashes set and the art files written by hand
(Pillow PNGs + a STORED cards.zip, exactly what _persist_class leaves behind)."""
from __future__ import annotations

import io
import json
import zipfile

import pytest
from conftest import login

pytest.importorskip("PIL")
from PIL import Image  # noqa: E402

CARDS = [{"id": "strike_x", "name": "Strike X", "type": "attack", "rarity": "basic", "cost": 1, "effects": []},
         {"id": "odd/id!", "name": "Odd", "type": "skill", "rarity": "common", "cost": 1, "effects": []},
         {"id": "no_art", "name": "No Art", "type": "power", "rarity": "rare", "cost": 2, "effects": []}]


def _png(w: int, h: int, mode: str = "RGB") -> bytes:
    buf = io.BytesIO()
    Image.new(mode, (w, h), (200, 40, 90, 255) if mode == "RGBA" else (200, 40, 90)).save(buf, format="PNG")
    return buf.getvalue()


def _make_class(app_module, email: str, *, with_art: bool = True) -> tuple[int, str]:
    """A saved class for `email` (logged in via dev auth first) with splash/sprite/cards.zip on disk."""
    from models import ForgedClass, User, new_slug
    with app_module.session_scope() as s:
        uid = s.query(User).filter_by(email=email).one().id
        cls = ForgedClass(user_id=uid, name="Thumb Test", concept="c", code="BTSC.x", slug=new_slug(),
                          bundle_json=json.dumps({"character": {"name": "Thumb Test"}, "cards": CARDS}),
                          splash_hash="a" * 16 if with_art else None,
                          sprite_hash="b" * 16 if with_art else None,
                          card_art_hash="c" * 16 if with_art else None)
        s.add(cls)
        s.flush()
        cid, slug = cls.id, cls.slug
    if with_art:
        d = app_module.STATIC_FORGED_DIR / str(cid)
        d.mkdir(parents=True, exist_ok=True)
        (d / "splash.png").write_bytes(_png(1024, 576))
        (d / "sprite.png").write_bytes(_png(1024, 1536, "RGBA"))
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
            z.writestr(f"{app_module._card_art_id(CARDS[0], 0)}.png", _png(1000, 760))
            z.writestr(f"{app_module._card_art_id(CARDS[1], 1)}.png", _png(1000, 760))
        (d / "cards.zip").write_bytes(buf.getvalue())
    return cid, slug


def _dims(resp) -> tuple[str, tuple[int, int]]:
    with Image.open(io.BytesIO(resp.data)) as im:
        return im.format, im.size


def test_list_and_detail_carry_thumb_urls_and_the_card_map(client, app_module):
    login(client, "thumbs@example.com")
    cid, slug = _make_class(app_module, "thumbs@example.com")
    row = next(r for r in client.get("/api/classes").get_json()["classes"] if r["id"] == cid)
    assert row["splash_thumb_url"] == f"/api/classes/{cid}/art/splash?v=aaaaaaaa"
    assert row["sprite_thumb_url"] == f"/api/classes/{cid}/art/sprite?v=bbbbbbbb"
    assert row["splash_url"].endswith(f"/static/forged/{cid}/splash.png?v=aaaaaaaa")
    assert "card_art" not in row  # the list never opens the zip

    d = client.get(f"/api/classes/{cid}").get_json()
    # only cards whose portrait is in the pack, keyed by the card's OWN id (not the sanitized stem)
    assert set(d["card_art"]) == {"strike_x", "odd/id!"}
    assert d["card_art"]["odd/id!"] == f"/api/classes/{cid}/art/card/odd_id?v=cccccccc"
    assert d["card_art_url"].endswith(f"/static/forged/{cid}/cards.zip?v=cccccccc")

    # the public share page gets the same fields under its slug (and still no id)
    pub = client.get(f"/api/deck/{slug}").get_json()
    assert "id" not in pub
    assert pub["splash_thumb_url"] == f"/api/deck/{slug}/art/splash?v=aaaaaaaa"
    assert pub["card_art"]["strike_x"] == f"/api/deck/{slug}/art/card/strike_x?v=cccccccc"


def test_class_without_art_carries_no_art_fields(client, app_module):
    login(client, "noart@example.com")
    cid, _ = _make_class(app_module, "noart@example.com", with_art=False)
    row = next(r for r in client.get("/api/classes").get_json()["classes"] if r["id"] == cid)
    assert not any(k.endswith("_url") for k in row)
    assert "card_art" not in client.get(f"/api/classes/{cid}").get_json()
    assert client.get(f"/api/classes/{cid}/art/splash").status_code == 404


def test_thumbs_are_small_webp_and_cached_on_disk(client, app_module):
    login(client, "thumbs2@example.com")
    cid, slug = _make_class(app_module, "thumbs2@example.com")
    r = client.get(f"/api/classes/{cid}/art/splash?v=aaaaaaaa")
    assert r.status_code == 200 and r.mimetype == "image/webp"
    assert "immutable" in r.headers["Cache-Control"]
    fmt, (w, h) = _dims(r)
    assert fmt == "WEBP" and w <= 480 and h <= 270 and w > 100
    thumbs = app_module.STATIC_FORGED_DIR / str(cid) / "thumbs"
    assert (thumbs / "splash-aaaaaaaa.webp").is_file()

    r = client.get(f"/api/classes/{cid}/art/sprite")
    fmt, (w, h) = _dims(r)
    assert fmt == "WEBP" and h <= 384 and w <= 256
    assert (thumbs / "sprite-bbbbbbbb.webp").is_file()

    r = client.get(f"/api/classes/{cid}/art/card/odd_id")
    assert r.status_code == 200 and r.mimetype == "image/webp"
    fmt, (w, h) = _dims(r)
    assert w <= 300 and h <= 228
    assert (thumbs / "card-odd_id-cccccccc.webp").is_file()

    # the cached file is what serves from now on: delete the source, the thumb still answers
    (app_module.STATIC_FORGED_DIR / str(cid) / "splash.png").unlink()
    assert client.get(f"/api/classes/{cid}/art/splash").status_code == 200

    # public routes reach the same thumbs without a session
    anon = app_module.app.test_client()
    assert anon.get(f"/api/deck/{slug}/art/sprite").status_code == 200
    assert anon.get(f"/api/deck/{slug}/art/card/strike_x").status_code == 200
    assert anon.get(f"/api/deck/{slug}/art/card/no_art").status_code == 404  # not in the pack
    assert anon.get("/api/deck/nope/art/splash").status_code == 404


def test_thumb_routes_are_owner_only_and_reject_bad_names(client, app_module):
    login(client, "owner@example.com")
    cid, _ = _make_class(app_module, "owner@example.com")
    other = app_module.app.test_client()
    login(other, "stranger@example.com")
    assert other.get(f"/api/classes/{cid}/art/splash").status_code == 404
    assert other.get(f"/api/classes/{cid}/art/card/strike_x").status_code == 404
    assert app_module.app.test_client().get(f"/api/classes/{cid}/art/splash").status_code in (401, 403, 302)
    # unknown kinds and stems outside _card_art_id's alphabet never reach the filesystem
    assert client.get(f"/api/classes/{cid}/art/relic").status_code == 404
    assert client.get(f"/api/classes/{cid}/art/card/..%2F..%2Fsplash").status_code == 404
    assert client.get(f"/api/classes/{cid}/art/card/strike.x").status_code == 404


def test_pruned_art_404s_instead_of_erroring(client, app_module):
    """btsweb-prune deletes splash.png/sprite.png (and clears the hashes); a stale URL must just 404."""
    login(client, "pruned@example.com")
    cid, _ = _make_class(app_module, "pruned@example.com")
    (app_module.STATIC_FORGED_DIR / str(cid) / "sprite.png").unlink()
    (app_module.STATIC_FORGED_DIR / str(cid) / "cards.zip").unlink()
    assert client.get(f"/api/classes/{cid}/art/sprite").status_code == 404
    assert client.get(f"/api/classes/{cid}/art/card/strike_x").status_code == 404
    assert client.get(f"/api/classes/{cid}").get_json().get("card_art", {}) == {}

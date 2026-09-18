"""The per-card portrait pack (app._generate_card_art) and the cost ledger that pays for it.

Two things are under test here and they meet in `forge_usage`:

  * ONE zip per class. `_persist_class` renders a portrait per card, packs the successes into
    static/forged/<id>/cards.zip with FLAT entry names, hangs the URL off the bundle so the re-encoded
    import code delivers it, and stamps `classes.card_art_hash`. Both guardrails (wall clock, spend) must
    stop the run early and still ship a partial pack, and BTSWEB_CARD_ART=0 must skip the whole step.
  * REAL money, not a guess. OpenRouter reports `usage.cost` per LLM call and the image backends report
    `ImageResult.cost_usd`; both land in `forge_usage.metered_cost_micros`, art gets its own `art:*` rows,
    and the readers (admin stats, /api/forge-estimate) treat those two facts correctly.

Network-free: the `procedural` image backend needs no key, and the cap tests stub `forge_card_art` outright.
"""
from __future__ import annotations

import json
import time
import zipfile
from pathlib import Path

import pytest
from conftest import H, login, sse_events

ADMIN = "unlimited@example.com"


# --- helpers ---------------------------------------------------------------------------------------

@pytest.fixture()
def small_card_style(monkeypatch):
    """The procedural backend paints pixel by pixel in pure Python, so a real 1536x1024 card render costs
    ~1.5 s — a whole class would add a minute to this suite for no extra coverage. Shrink the RENDER only:
    the backend chain, the crop/resize to the mod's 1000x760 portrait box, the sidecar and the zip all still
    run for real."""
    from btsgen.art.request import StyleProfile
    monkeypatch.setattr("btsgen.art.card.CARD_STYLE",
                        StyleProfile(name="card-test", size=(48, 32), out_format="png"))


@pytest.fixture()
def procedural(monkeypatch, small_card_style):
    monkeypatch.setenv("BTSGEN_IMAGE_BACKEND", "procedural")


def _user_id(app_module, email: str) -> int:
    from models import User
    with app_module.session_scope() as s:
        return s.query(User).filter_by(email=email).one().id


def _persist(app_module, fake_bundle, uid: int, **kw) -> dict:
    """_persist_class against a real forge result — the same call finish_done makes."""
    return app_module._persist_class(uid, "card art test", dict(fake_bundle), **kw)


def _card_art_hash(app_module, class_id: int) -> str | None:
    from models import ForgedClass
    with app_module.session_scope() as s:
        return s.query(ForgedClass).filter_by(id=class_id).one().card_art_hash


def _detail(app_module, class_id: int) -> dict:
    """detail() inside the session — it walks the class's card rows."""
    from models import ForgedClass
    with app_module.session_scope() as s:
        return s.query(ForgedClass).filter_by(id=class_id).one().detail()


def _zip_names(app_module, class_id: int) -> list[str]:
    with zipfile.ZipFile(app_module.STATIC_FORGED_DIR / str(class_id) / "cards.zip") as z:
        return z.namelist()


def _clear(app_module) -> None:
    from models import ForgeJob, ForgeUsage
    with app_module.session_scope() as s:
        s.query(ForgeUsage).delete()
        s.query(ForgeJob).delete()


def _usage(app_module, class_id: int) -> dict:
    from models import ForgeUsage
    with app_module.session_scope() as s:
        return {r.role: r for r in s.query(ForgeUsage).filter_by(class_id=class_id).all()}


def _stub_cards(monkeypatch, *, cost_usd=0.0, delay=0.0, model="test/image-mini"):
    """Replace forge_card_art with an instant always-ok stub of a known price (the caps are about
    arithmetic and cancellation, not about images)."""
    import btsgen.art as bart
    from btsgen.art.request import ImageResult

    def fake(art, card, *, out_path=None, **kw):
        if delay:
            time.sleep(delay)
        p = Path(out_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"stub")
        return ImageResult(ok=True, backend="stub", path=p, model=model, cost_usd=cost_usd,
                           width=1000, height=760)

    monkeypatch.setattr(bart, "forge_card_art", fake)


# --- the happy path: one flat portrait per card, in one zip, in the code ------------------------------

def test_persist_class_packs_one_portrait_per_card(client, app_module, fake_bundle, procedural):
    uid = _user_id(app_module, login(client, "cardart@example.com")["email"])
    detail = _persist(app_module, fake_bundle, uid)
    class_id = detail["id"]

    url = detail["card_art_url"]
    assert url.startswith(f"http://testserver/static/forged/{class_id}/cards.zip?v=")

    names = _zip_names(app_module, class_id)
    # Flat entry names, one per card: the mod flattens to the leaf and looks a portrait up by card id.
    assert set(names) == {f"{c['id']}.png" for c in fake_bundle["cards"]}
    assert len(names) == len(fake_bundle["cards"])
    assert all("/" not in n and "\\" not in n for n in names)

    # The import code the player pastes carries the URL — no second round-trip to learn about the art.
    from btsgen.bts1 import decode
    text, kind = decode(detail["code"])
    assert kind == "class" and json.loads(text)["card_art_url"] == url

    digest = _card_art_hash(app_module, class_id)
    assert digest and f"?v={digest[:8]}" in url
    assert _detail(app_module, class_id)["card_art_hash"] == digest


def test_the_portraits_are_cropped_to_the_mods_portrait_box(client, app_module, fake_bundle, procedural):
    """3d's contract, end to end: whatever ratio the backend renders, the shipped file is 1000x760."""
    from btsgen.art.card import CARD_PORTRAIT_SIZE, image_size
    uid = _user_id(app_module, login(client, "cardsize@example.com")["email"])
    detail = _persist(app_module, fake_bundle, uid)
    one = next((app_module.STATIC_FORGED_DIR / str(detail["id"]) / "cards").glob("*.png"))
    assert image_size(one) == CARD_PORTRAIT_SIZE


def test_deck_page_json_exposes_the_card_art_url(client, app_module, fake_bundle, procedural):
    uid = _user_id(app_module, login(client, "cardshare@example.com")["email"])
    detail = _persist(app_module, fake_bundle, uid)
    body = client.get(f"/api/deck/{detail['slug']}").get_json()
    assert body["card_art_url"] == detail["card_art_url"]


def test_the_static_route_serves_the_zip(client, app_module):
    """The pack is only useful if it can be downloaded: static/forged/ is a plain directory served by
    Flask in dev and aliased whole by nginx in prod, with no suffix allowlist to add .zip to. Written
    into the REAL static tree (the rest of the suite redirects STATIC_FORGED_DIR to a temp dir) because
    that is the path the route resolves, and removed again straight after."""
    import shutil
    from pathlib import Path as P
    here = P(app_module.app.static_folder) / "forged" / "_ziproute_test"
    here.mkdir(parents=True, exist_ok=True)
    try:
        (here / "cards.zip").write_bytes(b"PK\x05\x06" + b"\x00" * 18)   # a valid empty zip
        r = client.get("/static/forged/_ziproute_test/cards.zip?v=deadbeef")
        try:
            assert r.status_code == 200 and r.get_data().startswith(b"PK")
            assert "zip" in (r.headers.get("Content-Type") or "")
        finally:
            r.close()   # Windows will not delete a file send_file still holds open
    finally:
        shutil.rmtree(here, ignore_errors=True)


def test_deleting_a_class_removes_the_pack(client, app_module, fake_bundle, procedural):
    uid = _user_id(app_module, login(client, "carddel@example.com")["email"])
    detail = _persist(app_module, fake_bundle, uid)
    art_dir = app_module.STATIC_FORGED_DIR / str(detail["id"])
    assert (art_dir / "cards.zip").exists()
    assert client.delete(f"/api/classes/{detail['id']}", headers=H).status_code == 200
    assert not art_dir.exists()


# --- the guardrails --------------------------------------------------------------------------------

def test_the_cost_cap_stops_the_pack_and_ships_a_partial_zip(client, app_module, fake_bundle, monkeypatch):
    """$0.02 a card against a $0.03 cap: the run stops as soon as the spend crosses it. Cards already in
    flight may still land (an image we have paid for is not thrown away), so the assertion is 'some, not
    all' — the point is that a partial pack SHIPS rather than the class losing its art."""
    monkeypatch.setattr(app_module, "CARD_ART_WORKERS", 2)
    monkeypatch.setenv("BTSWEB_CARD_ART_MAX_USD", "0.03")
    monkeypatch.setenv("BTSWEB_CARD_ART_BUDGET_S", "600")
    _stub_cards(monkeypatch, cost_usd=0.02, delay=0.02)
    total = len(fake_bundle["cards"])
    lines: list[str] = []

    uid = _user_id(app_module, login(client, "cardcap@example.com")["email"])
    detail = _persist(app_module, fake_bundle, uid, on_event=lines.append)

    names = _zip_names(app_module, detail["id"])
    assert 0 < len(names) < total
    assert "card_art_url" in detail and _card_art_hash(app_module, detail["id"])
    assert any("cost cap" in line and "partial pack" in line for line in lines)


def test_the_time_budget_stops_the_pack(client, app_module, fake_bundle, monkeypatch):
    monkeypatch.setattr(app_module, "CARD_ART_WORKERS", 2)
    monkeypatch.setenv("BTSWEB_CARD_ART_BUDGET_S", "0.05")
    monkeypatch.setenv("BTSWEB_CARD_ART_MAX_USD", "100")   # only the clock may trip here
    _stub_cards(monkeypatch, cost_usd=0.0, delay=0.05)
    total = len(fake_bundle["cards"])
    lines: list[str] = []

    uid = _user_id(app_module, login(client, "cardslow@example.com")["email"])
    detail = _persist(app_module, fake_bundle, uid, on_event=lines.append)

    assert 0 < len(_zip_names(app_module, detail["id"])) < total
    assert any("time budget" in line for line in lines)


def test_card_art_can_be_switched_off(client, app_module, fake_bundle, procedural, monkeypatch):
    monkeypatch.setenv("BTSWEB_CARD_ART", "0")
    uid = _user_id(app_module, login(client, "cardoff@example.com")["email"])
    detail = _persist(app_module, fake_bundle, uid)

    assert "card_art_url" not in detail
    art_dir = app_module.STATIC_FORGED_DIR / str(detail["id"])
    assert not (art_dir / "cards.zip").exists() and not (art_dir / "cards").exists()
    assert _card_art_hash(app_module, detail["id"]) is None
    assert "card_art_url" not in json.loads(decode_text(detail["code"]))


def decode_text(code: str) -> str:
    from btsgen.bts1 import decode
    return decode(code)[0]


def test_a_broken_art_module_never_fails_the_forge(client, app_module, fake_bundle, monkeypatch):
    """Same contract as _generate_art: art is cosmetic, so an exception anywhere in it costs the pack,
    never the class."""
    import btsgen.art as bart

    def boom(*a, **k):
        raise RuntimeError("image vendor is on fire")

    monkeypatch.setattr(bart, "forge_card_art", boom)
    uid = _user_id(app_module, login(client, "cardboom@example.com")["email"])
    detail = _persist(app_module, fake_bundle, uid)
    assert detail["id"] and "card_art_url" not in detail


# --- the ledger ------------------------------------------------------------------------------------

def test_usage_meter_sums_metered_cost_per_row():
    """usage.cost (OpenRouter, from usage:{include:true}) accumulates per (role, model); a row no call
    priced stays None, so "nobody metered this" never reads as "$0"."""
    from forge import UsageMeter
    m = UsageMeter()
    m({"prompt_tokens": 10, "completion_tokens": 2, "cost": 0.0125, "_role": "cards", "_model": "z-ai/glm-5.3"})
    m({"prompt_tokens": 10, "completion_tokens": 2, "cost": 0.0075, "_role": "cards", "_model": "z-ai/glm-5.3"})
    m({"prompt_tokens": 5, "completion_tokens": 1, "_role": "brainstorm", "_model": "gemma4:31b"})
    rows = {(r["role"], r["model"]): r for r in m.rows()}
    assert rows[("cards", "z-ai/glm-5.3")]["cost_usd"] == pytest.approx(0.02)
    assert rows[("cards", "z-ai/glm-5.3")]["calls"] == 2
    assert rows[("brainstorm", "gemma4:31b")]["cost_usd"] is None
    assert m.art_rows() == []                       # LLM calls are not art


def test_usage_meter_art_rows_are_separate_from_llm_rows():
    from forge import UsageMeter
    m = UsageMeter()
    m({"prompt_tokens": 10, "completion_tokens": 2, "_role": "cards", "_model": "z-ai/glm-5.3"})
    m.add_art("splash", "openai/gpt-5-image-mini", 0.004)
    for _ in range(3):
        m.add_art("cards", "openai/gpt-5-image-mini", 0.004)
    m.add_art("sprite", "openai/gpt-image-2.5-flare", None)
    art = {r["role"]: r for r in m.art_rows()}
    assert set(art) == {"art:splash", "art:cards", "art:sprite"}
    assert art["art:cards"]["calls"] == 3 and art["art:cards"]["cost_usd"] == pytest.approx(0.012)
    assert art["art:sprite"]["cost_usd"] is None     # an unmetered backend is not a free one
    assert [r["role"] for r in m.rows()] == ["cards"]   # the LLM totals are untouched by art


def test_the_ledger_records_metered_llm_cost(client, app_module, fake_bundle, monkeypatch):
    """A forge whose calls report usage.cost gets the REAL number alongside the rate-table estimate."""
    from models import ForgeUsage

    def fake_forge(concept, **kw):
        kw["on_usage"]({"prompt_tokens": 1000, "completion_tokens": 200, "cost": 0.0123,
                        "_role": "cards", "_model": "z-ai/glm-5.3"})
        return dict(fake_bundle)

    monkeypatch.setattr(app_module, "forge_to_bundle", fake_forge)
    login(client, "metered@example.com")
    ev = sse_events(client.post("/api/forge-class", json={"concept": "m", "mode": "token"}, headers=H))
    with app_module.session_scope() as s:
        row = s.query(ForgeUsage).filter_by(class_id=ev[-1][1]["id"], role="cards").one()
    assert row.metered_cost_micros == 12_300                      # what OpenRouter actually billed
    assert row.est_cost_micros == 1_482                           # the rate-table guess, kept for comparison


def test_art_rows_land_in_the_ledger_and_the_estimate_ignores_them(client, app_module, stub_forge,
                                                                   procedural):
    """One `art:*` row per asset kind, priced by the backend, with zero tokens — and /api/forge-estimate
    (the 'what will this cost MY key' quote) must not see them."""
    _clear(app_module)
    login(client, "artledger@example.com")
    ev = sse_events(client.post("/api/forge-class", json={"concept": "art", "mode": "token"}, headers=H))
    saved = ev[-1][1]
    rows = _usage(app_module, saved["id"])

    assert {"art:splash", "art:sprite", "art:cards"} <= set(rows)
    cards = rows["art:cards"]
    # The procedural backend reports no model slug, so the row falls back to the backend name.
    assert cards.calls == len(saved["cards"]) and cards.model == "procedural"
    assert (cards.input_tokens, cards.output_tokens, cards.cached_tokens) == (0, 0, 0)
    assert cards.metered_cost_micros == 0 and cards.est_cost_micros is None   # procedural is really free
    assert rows["art:splash"].calls == 1 and rows["art:sprite"].calls == 1

    # The forge's own "this used…" summary stays an LLM number (the stub meters exactly two calls).
    assert saved["usage"] == {"calls": 2, "input_tokens": 1500, "cached_tokens": 300, "output_tokens": 300}
    est = client.get("/api/forge-estimate").get_json()
    assert est["forges_sampled"] == 1 and est["calls"] == 2 and est["input_tokens"] == 1500
    _clear(app_module)


def test_admin_stats_prefers_metered_cost_and_skips_art_calls(client, app_module):
    from models import ForgeJob, ForgeUsage
    from datetime import datetime, timezone
    login(client, ADMIN)
    _clear(app_module)
    uid = _user_id(app_module, ADMIN)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with app_module.session_scope() as s:
        s.add(ForgeJob(id="ab" * 16, user_id=uid, mode="token", token_kind="free", status="done",
                       concept="seeded", started_at=now))
        # metered wins over est on the row that has both...
        s.add(ForgeUsage(user_id=uid, forge_id="ab" * 16, mode="token", provider="hosted",
                         model="z-ai/glm-5.3", role="cards", calls=30, input_tokens=1000,
                         output_tokens=200, cached_tokens=300, est_cost_micros=1_000_000,
                         metered_cost_micros=400_000, ok=1, created_at=now))
        # ...and est is still used on the row nobody metered (the Ollama tier).
        s.add(ForgeUsage(user_id=uid, forge_id="ab" * 16, mode="token", provider="hosted",
                         model="glm-5.2", role="structure", calls=5, input_tokens=100,
                         output_tokens=20, cached_tokens=0, est_cost_micros=250_000,
                         metered_cost_micros=None, ok=1, created_at=now))
        # the art row pays its way but is not 34 more LLM "calls"
        s.add(ForgeUsage(user_id=uid, forge_id="ab" * 16, mode="token", provider="hosted",
                         model="openai/gpt-5-image-mini", role="art:cards", calls=34, input_tokens=0,
                         output_tokens=0, cached_tokens=0, est_cost_micros=None,
                         metered_cost_micros=150_000, ok=1, created_at=now))

    hosted = client.get("/api/admin/stats?days=30").get_json()["hosted"]
    assert hosted["est_cost_usd"] == 0.8            # 0.40 metered + 0.25 est + 0.15 art
    assert hosted["calls"] == 35 and hosted["forges"] == 1    # 30 + 5; the 34 images are not calls
    assert hosted["input_tokens"] == 1100
    _clear(app_module)

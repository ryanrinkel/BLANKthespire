"""forge_failures.classify: every failed forge gets a kind, a plain label, and whether the OPERATOR needs to
act. The parametrised rows below are the 62 failed forge_jobs rows on the droplet on 2026-11-13 (one per
distinct shape, with the count each stands for), plus the token-mode twins that must NOT be muted, plus the
server texts pinned to their i18n source. Also /api/admin/failures."""
from __future__ import annotations

import pytest

import forge_failures as ff
import i18n
from conftest import H, login

ADMIN = "unlimited@example.com"


def _cap(text: str) -> str:
    """What the 500-char forge_jobs.error column keeps."""
    return text[:500]


def _explained(raw: str) -> str:
    """forge._bundle_result's '<sentence> (Your provider said: <raw>)' as stored."""
    raw = " ".join(raw.split())
    return _cap(f"{ff.explain_provider_error(raw)} (Your provider said: {raw[:300]})")


CREDITS_429_RAW = ('front-end failed: endpoint returned HTTP 429: { "error": { "message": "You have no credits '
                   'remaining. Add credits to continue using the API.", "type": "insufficient_quota", '
                   '"code": "credit_balance_exhausted" } }')
OPENROUTER_402 = ('class did not generate: front-end failed: endpoint returned HTTP 402: {"error":{"message":"This '
                  'request requires more credits, or fewer max_tokens. You requested up to 48000 tokens, but can '
                  'only afford 8784. To increase, visit https://openrouter.ai/workspaces/default/keys and create a '
                  'key with a higher total limit","code":402,"metadata":{"provider_name":null}},"user_id":"user_x"}')
GROQ_413_RAW = ('front-end failed: endpoint returned HTTP 413: {"error":{"message":"Request too large for model '
                '`openai/gpt-oss-120b` in organization `org_x` service tier `on_demand` on tokens per minute (TPM): '
                'Limit 8000, Requested 10549, please reduce your message size and try again.","type":"tokens",'
                '"code":"rate_limit_exceeded"}}')
# The 413 row was stored BEFORE the plan_limit sentence existed: the sentence says "rate-limited".
GROQ_413_OLD = _cap("Your provider rate-limited the key. Wait a minute and forge again, or raise the limit on your "
                    f"provider account. (Your provider said: {GROQ_413_RAW[:300]})")
KEY_400 = _cap("Your provider rejected the API key. Paste a current key from your provider's dashboard (and check "
               "the provider dropdown matches where the key came from). (Your provider said: front-end failed: "
               'endpoint returned HTTP 400: {"code":"invalid-argument","error":"Incorrect API key provided: xai-***"}')
ANTHROPIC_401 = ("class did not generate: front-end failed: Error code: 401 - {'type': 'error', 'error': {'type': "
                 "'authentication_error', 'message': 'invalid x-api-key'}, 'request_id': 'req_011'}")
GEMINI_QUOTA = ('unexpected error: endpoint returned HTTP 429: [{ "error": { "code": 429, "message": "You exceeded '
                'your current quota, please check your plan and billing details. For more information on this '
                'error, head to: https://ai.google.dev/gemini-api/docs/rate-limits.", "status": '
                '"RESOURCE_EXHAUSTED" } }]')
OPENAI_NO_CREDITS = ('unexpected error: endpoint returned HTTP 429: { "error": { "message": "You have no credits '
                     'remaining. Add credits to continue.", "type": "insufficient_quota", "code": null } }')
UNPARSEABLE = "class did not generate: front-end failed: cloud/cluster failed: unparseable cloud/cluster"
BLUEPRINT = ("class did not generate: front-end failed: blueprint failed: missing 'name'; missing 'description'; "
             "missing 'max_hp'; missing 'archetypes'")
FACETS = ("class did not generate: front-end failed: cloud/cluster failed: need a 'facets' list of at least 1 "
          "entry; got 0")
TOO_LONG = i18n.get_text("en", "server.forge.too_long_job", max_seconds=1200)
RESTARTED = i18n.get_text("en", "server.forge.restarted")

# (count on prod, error, mode, class_id, expected kind, expected attention)
PRODUCTION = [
    (4, _explained(CREDITS_429_RAW), "byok", None, "user_credits", False),
    (37, OPENROUTER_402, "byok", None, "user_credits", False),
    (3, TOO_LONG, "byok", 101, "slow_byok", False),
    (1, TOO_LONG, "token", 102, "slow_hosted", True),
    (1, GROQ_413_OLD, "byok", None, "user_plan_limit", False),
    (1, KEY_400, "byok", None, "user_key", False),
    (1, ANTHROPIC_401, "byok", None, "user_key", False),
    (1, RESTARTED, "token", None, "restart", False),
    (2, GEMINI_QUOTA, "byok", None, "user_credits", False),
    (1, OPENAI_NO_CREDITS, "byok", None, "user_credits", False),
    (1, UNPARSEABLE, "byok", None, "generation", True),
    (7, BLUEPRINT, "token", None, "generation", True),
    (2, FACETS, "token", None, "generation", True),
]


def test_the_production_table_is_all_62_rows():
    assert sum(r[0] for r in PRODUCTION) == 62


@pytest.mark.parametrize("n,error,mode,class_id,kind,attention", PRODUCTION)
def test_every_production_failure_is_classified(n, error, mode, class_id, kind, attention):
    tag = ff.classify(error, mode, class_id)
    assert (tag["kind"], tag["attention"]) == (kind, attention), tag
    assert tag["label"] and tag["label"].startswith(ff.KINDS[kind][0])


def test_production_split():
    rows = []
    for n, error, mode, class_id, _k, _a in PRODUCTION:
        rows += [ff.classify(error, mode, class_id)] * n
    s = ff.summarize(rows)
    assert (s["total"], s["attention"]) == (62, 11)   # 1 slow hosted + 10 generation failures
    assert s["by_kind"][0] == {"kind": "user_credits", "label": "User's key: out of credits",
                               "attention": False, "n": 44}


@pytest.mark.parametrize("error,kind", [
    (OPENROUTER_402, "hosted_credits"),
    (GEMINI_QUOTA, "hosted_credits"),
    (ANTHROPIC_401, "hosted_key"),
    (GROQ_413_OLD, "hosted_plan_limit"),
    ('unexpected error: endpoint returned HTTP 404: {"code": "model_not_found"}', "hosted_model"),
    ("unexpected error: endpoint returned HTTP 429: {}", "hosted_rate_limit"),
    ("unexpected error: endpoint returned HTTP 503: Service Unavailable", "hosted_down"),
])
def test_the_same_refusal_on_our_hosted_route_needs_attention(error, kind):
    for mode in ("token", "fake"):
        tag = ff.classify(error, mode, None)
        assert tag["kind"] == kind and tag["attention"] is True
        assert tag["label"].startswith("Hosted route:")
    user = ff.classify(error, "byok", None)
    assert user["kind"] == "user_" + kind.split("_", 1)[1] and user["attention"] is False


@pytest.mark.parametrize("raw", [
    "class did not generate: front-end failed: endpoint returned HTTP 502: Bad Gateway",
    "unexpected error: endpoint returned HTTP 529: {\"type\":\"error\",\"error\":{\"type\":\"overloaded_error\"}}",
    "class did not generate: front-end failed: Error code: 503 - upstream unavailable",
])
def test_byok_provider_outage_is_the_users_provider(raw):
    tag = ff.classify(raw, "byok", None)
    assert tag["kind"] == "user_down" and tag["attention"] is False


def test_our_sentence_wins_when_the_raw_provider_text_was_cut_off():
    # The 500-char column can cut the provider's words before "no credits remaining": the raw part then only
    # says "HTTP 429", which alone would read as a rate limit.
    cut = ("Your provider account has no credits left, so it refused the request. Add credits on your provider's "
           'billing page, then forge again — nothing was charged here. (Your provider said: front-end failed: '
           'endpoint returned HTTP 429: { "error": { "message": "You have')
    assert ff.classify(cut, "byok", None)["kind"] == "user_credits"
    assert ff.classify(cut, "token", None)["kind"] == "hosted_credits"


def test_slow_labels_say_whether_the_class_landed():
    assert ff.classify(TOO_LONG, "byok", 7)["label"] == "Slow on user's model (class landed late)"
    assert "never finished" in ff.classify(TOO_LONG, "byok", None)["label"]
    hosted = ff.classify(TOO_LONG, "token", 7)
    assert hosted["attention"] is True and "landed late" in hosted["label"]


# --- the server texts, pinned to their i18n source -----------------------------------------------------------

@pytest.mark.parametrize("key,kw,mode,kind,attention", [
    ("server.forge.restarted", {}, "token", "restart", False),
    ("server.forge.restarted", {}, "byok", "restart", False),
    ("server.forge.too_long_job", {"max_seconds": 1200}, "token", "slow_hosted", True),
    ("server.forge.too_long_job", {"max_seconds": 14400}, "byok", "slow_byok", False),
    ("server.forge.queue_timeout", {}, "token", "queue_timeout", True),
    ("server.forge.saving_failed", {"e": "disk full"}, "token", "save_failed", True),
    ("server.forge.saving_failed", {"e": "disk full"}, "byok", "save_failed", True),
    ("server.forge.unexpected", {"e": "KeyError('x')"}, "token", "unexpected", True),
    ("server.forge.unexpected", {"e": "KeyError('x')"}, "byok", "unexpected", True),
])
def test_server_texts_from_i18n(key, kw, mode, kind, attention):
    text = i18n.get_text("en", key, **kw)
    assert text != key, f"{key} missing from the English copy"
    tag = ff.classify(text, mode, None)
    assert (tag["kind"], tag["attention"]) == (kind, attention), (text, tag)


def test_unrecognised_text_needs_attention():
    for text in ("", None, "something nobody has seen before", "Couldn't measure this model: boom"):
        tag = ff.classify(text, "byok", None)
        assert tag["kind"] == "unknown" and tag["attention"] is True


def test_byok_setup_mistakes_are_the_users():
    tag = ff.classify("base URL points at a private or internal address — use a public provider endpoint.",
                      "byok", None)
    assert tag["kind"] == "user_config" and tag["attention"] is False
    assert ff.classify("BYOK needs base_url, api_key, and model together.", "token", None)["attention"] is True


def test_every_kind_has_a_label_and_only_benign_kinds_are_muted():
    muted = {k for k, (_label, att) in ff.KINDS.items() if not att}
    assert muted == {"user_model", "user_routing", "user_credits", "user_key", "user_access", "user_plan_limit",
                     "user_rate_limit", "user_down", "user_config", "slow_byok", "restart"}
    assert all(label for label, _ in ff.KINDS.values())


# --- /api/admin/failures -------------------------------------------------------------------------------------

def _seed_job(app_module, job_id, user_id, *, mode, error, class_id=None, refunded=0, age_days=0.0,
              status="failed"):
    from datetime import datetime, timedelta, timezone
    from models import ForgeJob
    when = (datetime.now(timezone.utc) - timedelta(days=age_days)).replace(tzinfo=None)
    with app_module.session_scope() as s:
        s.add(ForgeJob(id=job_id.ljust(32, "x"), user_id=user_id, mode=mode, status=status, error=error,
                       class_id=class_id, refunded=refunded, concept="TOP SECRET CONCEPT", started_at=when))


def _clear_jobs(app_module):
    from models import ForgeJob
    with app_module.session_scope() as s:
        s.query(ForgeJob).delete()


def test_failures_endpoint_is_admin_only(client):
    client.post("/logout", headers=H)
    assert client.get("/api/admin/failures").status_code == 401
    login(client, "nosy-failures@example.com")
    r = client.get("/api/admin/failures")
    assert r.status_code == 403 and r.get_json() == {"error": "forbidden"}


def test_failures_endpoint_lists_classified_rows_newest_first(client, app_module):
    from models import User
    login(client, "victim@example.com")
    login(client, ADMIN)
    _clear_jobs(app_module)
    with app_module.session_scope() as s:
        uid = s.query(User).filter_by(email="victim@example.com").one().id
    _seed_job(app_module, "f-old", uid, mode="token", error=BLUEPRINT, age_days=2, refunded=1)
    _seed_job(app_module, "f-mid", uid, mode="byok", error=OPENROUTER_402, age_days=1)
    _seed_job(app_module, "f-new", uid, mode="byok", error=TOO_LONG, class_id=None, age_days=0.1)
    _seed_job(app_module, "f-out", uid, mode="token", error=BLUEPRINT, age_days=60)         # outside 30d
    _seed_job(app_module, "f-done", uid, mode="token", error="", status="done")              # not a failure

    body = client.get("/api/admin/failures?days=30").get_json()
    assert (body["total"], body["attention"]) == (3, 1)
    assert {k["kind"]: k["n"] for k in body["by_kind"]} == {"generation": 1, "user_credits": 1, "slow_byok": 1}
    rows = body["failures"]
    assert [r["kind"] for r in rows] == ["slow_byok", "user_credits", "generation"]
    first = rows[0]
    assert set(first) == {"id", "at", "user_id", "email", "mode", "kind", "label", "attention", "error",
                          "landed", "refunded"}
    assert first["email"] == "victim@example.com" and first["landed"] is False
    assert rows[2]["refunded"] is True and rows[2]["attention"] is True
    assert all(len(r["error"]) <= 300 for r in rows)
    assert "TOP SECRET CONCEPT" not in client.get("/api/admin/failures?days=0").get_data(as_text=True)

    assert client.get("/api/admin/failures?days=0").get_json()["total"] == 4
    limited = client.get("/api/admin/failures?days=0&limit=1").get_json()
    assert len(limited["failures"]) == 1 and limited["total"] == 4    # totals cover the window, not the page
    assert client.get("/api/admin/failures?days=banana").get_json()["days"] == 30


def test_generation_text_with_a_refusal_word_is_not_muted_on_byok():
    # No HTTP status / SDK error code => no provider answered; a validator line that happens to say
    # "forbidden" or "not found" must stay a generation failure that needs attention.
    for raw in ("class did not generate: front-end failed: blueprint failed: forbidden keyword in card text",
                "class did not generate: front-end failed: cloud/cluster failed: model answer not found"):
        tag = ff.classify(raw, "byok", None)
        assert tag["kind"] == "generation" and tag["attention"] is True

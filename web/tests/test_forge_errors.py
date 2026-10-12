"""forge.explain_provider_error: a BYOK forge that dies on the player's OWN provider gets one plain sentence
instead of (only) the provider's JSON body. The six strings below are the ones a new account hit on
2026-10-11, eleven times, in under two seconds each."""
from __future__ import annotations

import forge

OPENAI_404 = ('front-end failed: endpoint returned HTTP 404: {\n    "error": {\n        "message": "The model '
             '`gtp-5` does not exist or you do not have access to it.",\n        "type": "invalid_request_error",'
             '\n        "code": "model_not_found"\n    }\n}\n')
OPENAI_429_CREDITS = ('front-end failed: endpoint returned HTTP 429: {"error": {"message": "You have no credits '
                      'remaining. Add credits to continue using the API at https://platform.openai.com/...", '
                      '"type": "insufficient_quota", "code": "credit_balance_exhausted"}}')
OPENAI_401 = ('front-end failed: endpoint returned HTTP 401: {"error": {"message": "Incorrect API key provided: '
              'sk-abcde***ef12. You can find your API key at ...", "code": "invalid_api_key"}, "status": 401}')
ANTHROPIC_401 = ("front-end failed: Error code: 401 - {'type': 'error', 'error': {'type': 'authentication_error', "
                 "'message': 'invalid x-api-key'}, 'request_id': 'req_011'}")
OPENAI_429_RATE = ('front-end failed: endpoint returned HTTP 429: {"error": {"message": "Rate limit reached for '
                   'gpt-5 in organization org-x on requests per min", "type": "rate_limit_error"}}')


def test_mistyped_model_names_the_model_and_the_fix():
    why = forge.explain_provider_error(OPENAI_404)
    assert "“gtp-5”" in why
    assert "Load my model list" in why


def test_model_name_falls_back_to_the_requested_one():
    why = forge.explain_provider_error('endpoint returned HTTP 404: {"code": "model_not_found"}', model="claude-opus-5-5")
    assert "“claude-opus-5-5”" in why


def test_no_credits_is_not_read_as_a_rate_limit():
    why = forge.explain_provider_error(OPENAI_429_CREDITS)
    assert "no credits left" in why and "rate-limited" not in why
    assert "rate-limited" in forge.explain_provider_error(OPENAI_429_RATE)


def test_bad_keys_on_both_wire_shapes():
    for raw in (OPENAI_401, ANTHROPIC_401):
        assert "rejected the API key" in forge.explain_provider_error(raw)


def test_unrecognised_failures_keep_the_old_message():
    assert forge.explain_provider_error("blueprint rejected: 0 cards buildable") is None
    assert forge.explain_provider_error("") is None


def test_bundle_result_leads_with_the_sentence_and_keeps_the_provider_text():
    class Res:
        ok = False
        bundle = None
        log = ["stage map", OPENAI_404]
    try:
        forge._bundle_result(Res())
    except forge.ForgeError as e:
        msg = str(e)
    else:
        raise AssertionError("expected ForgeError")
    assert msg.startswith("Your provider doesn't offer a model called")
    assert "(Your provider said: front-end failed: endpoint returned HTTP 404" in msg
    assert "\n" not in msg

    class Plain(Res):
        log = ["blueprint rejected: 0 cards buildable"]
    try:
        forge._bundle_result(Plain())
    except forge.ForgeError as e:
        assert str(e) == "class did not generate: blueprint rejected: 0 cards buildable"

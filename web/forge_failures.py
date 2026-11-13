"""Failed-forge triage: what a forge_jobs.error text means, and whether the operator needs to act on it.

`classify(error, mode, class_id)` -> {"kind", "label", "attention"}. It is computed at READ time from the
stored row (no column, no migration), so the rules can be tuned and every past failure is relabelled the
next time the admin panel loads.

The rule that matters: a provider refusal on a BYOK forge is the PLAYER'S own account (their credits, their
key, their plan) and is not the operator's problem; the same refusal on a token forge is OUR hosted route and
always is. Only kinds known to be benign are ever muted — anything unrecognised needs attention.

This module also owns the provider-refusal table forge.explain_provider_error uses (forge.py imports it), so
the player's sentence and the operator's label come from one set of patterns. Pure: no DB, no Flask, no
btsgen import — importing it is cheap.
"""
from __future__ import annotations

import re

# (kind, pattern, one-sentence explanation) for the provider refusals a BYOK forge dies on at its FIRST call.
# Order matters: the first match wins, so the specific "no credits" 429 sits above the generic 429. `kind` is
# a stable id the triage below builds on (user_<kind> on BYOK, hosted_<kind> on a token forge).
PROVIDER_REFUSALS: list[tuple[str, re.Pattern, str]] = [
    ("model",
     re.compile(r"model_not_found|does not exist or you do not have access|not_found_error|unknown model|"
                r"no such model|model .{0,80}? (?:is )?not found|models?/?[\w./:-]{0,80} (?:is )?not found",
                re.I),
     "Your provider doesn't offer a model called “{model}” on this key. Open “Bring your own key”, "
     "click “Reload model list” and pick one from the list (check the provider matches the key, too)."),
    # OpenRouter's routing refusals (the account's provider allow/ignore lists; free models without
    # data-sharing providers enabled): above the generic 403/404 so they get their own explanation.
    ("routing",
     re.compile(r"All providers have been ignored|No allowed providers are available|"
                r"not in your account's allowed-providers", re.I),
     "OpenRouter has no provider it is allowed to route this model to on your account. Check Settings → "
     "Privacy on openrouter.ai (free models need data-sharing providers enabled) or pick another model."),
    ("credits",
     re.compile(r"insufficient_quota|credit_balance_exhausted|no credits remaining|exceeded your current quota|"
                r"insufficient[_ ]credits|billing_hard_limit", re.I),
     "Your provider account has no credits left, so it refused the request. Add credits on your provider's "
     "billing page, then forge again — nothing was charged here."),
    # OpenRouter's low-balance refusal (HTTP 402 "This request requires more credits, or fewer max_tokens ...
    # can only afford 8784"): 37 BYOK forges died on it by 2026-11-13 and the player got the raw JSON. The
    # account isn't empty, just below what one forge request reserves, so it gets its own sentence.
    ("credits",
     re.compile(r"requires more credits|can only afford|\bHTTP 402\b|Error code: 402|payment required", re.I),
     "Your provider account doesn't have enough credits left for a forge request, so it refused it. Add "
     "credits on your provider's billing page, then forge again — nothing was charged here."),
    ("key",
     re.compile(r"invalid_api_key|authentication_error|invalid x-api-key|incorrect api key|invalid api key|"
                r"\bHTTP 401\b|Error code: 401|\b401\b.{0,40}unauthorized", re.I),
     "Your provider rejected the API key. Paste a current key from your provider's dashboard (and check the "
     "provider dropdown matches where the key came from)."),
    ("access",
     re.compile(r"\bHTTP 403\b|permission_denied|forbidden", re.I),
     "Your provider says this key isn't allowed to use that model or endpoint. Check the key's permissions "
     "on your provider's dashboard, or pick another model."),
    # A SINGLE request bigger than the key's per-minute token cap (Groq free plan: 8K TPM on gpt-oss-120b,
    # HTTP 413 "Request too large ... Limit 8000, Requested 10549", 2026-10-27). Waiting a minute can't help:
    # the forge's front-end prompt alone is over the cap and the card prompts are bigger still, so it sits
    # above the generic 429 wording that tells the player to retry.
    ("plan_limit",
     re.compile(r"request too large|\bHTTP 413\b|Error code: 413|tokens per minute \(TPM\)|"
                r"reduce (?:your|the) (?:message|prompt|request) size", re.I),
     "Your provider's plan caps how many tokens one request may send per minute, and a single forge prompt "
     "is larger than that cap, so retrying won't help. Upgrade the plan on your provider account (Groq: "
     "Settings → Billing → Plans → Developer) or forge with a key from another provider."),
    ("rate_limit",
     re.compile(r"\bHTTP 429\b|rate[_ ]limit|too many requests", re.I),
     "Your provider rate-limited the key. Wait a minute and forge again, or raise the limit on your "
     "provider account."),
]

MODEL_IN_ERROR = re.compile(r"[Tt]he model [`'\"‘“]([^`'\"’”]+)[`'\"’”]")

# What forge._bundle_result puts between its sentence and the provider's raw text.
PROVIDER_SAID = "(Your provider said:"


def provider_refusal(detail: str) -> tuple[str, str] | None:
    """(kind, sentence template) of the first refusal pattern matching `detail`, or None."""
    if not detail:
        return None
    for kind, pat, text in PROVIDER_REFUSALS:
        if pat.search(detail):
            return kind, text
    return None


def provider_refusal_kind(detail: str) -> str | None:
    """The stable kind (model, routing, credits, key, access, plan_limit, rate_limit) of a provider refusal
    text, or None when it isn't one we recognise."""
    hit = provider_refusal(detail)
    return hit[0] if hit else None


def explain_provider_error(detail: str, model: str | None = None) -> str | None:
    """One plain sentence for a BYOK refusal the player's PROVIDER sent back, or None when the failure isn't
    one we recognise. On 2026-10-11 a new account's 11 forges all died in under two seconds on the user's own
    key (a mistyped model, an Anthropic model id sent to OpenAI, a key with no credits, a placeholder key)
    and every one surfaced as the raw JSON error body, which reads like OUR outage. The raw text still
    follows the sentence so an operator can see what the provider actually said."""
    hit = provider_refusal(detail)
    if hit is None:
        return None
    m = MODEL_IN_ERROR.search(detail)
    name = (m.group(1) if m else None) or model or "that"
    return hit[1].format(model=name)


# --- triage -------------------------------------------------------------------------------------------------

# Provider-side outage (not a refusal): the player's provider was down or overloaded. Not part of
# PROVIDER_REFUSALS on purpose — the player-facing message for these is unchanged.
_PROVIDER_DOWN = re.compile(r"\bHTTP 50[234]\b|Error code: 5(?:02|03|04|29)\b|\bHTTP 529\b|overloaded|"
                            r"service unavailable|bad gateway|gateway time-?out", re.I)

# BYOK setup mistakes forge.py rejects before any call (base URL, missing fields).
_USER_CONFIG = re.compile(r"^(?:base URL must start|base URL needs a hostname|base URL points at a private|"
                          r"could not resolve |BYOK needs |Anthropic BYOK needs )", re.I)

# The server texts (web/COPY.md -> static/i18n/en.json, server.forge.*). Pinned by tests that build the
# string from i18n.get_text("en", ...), so a copy edit fails a test instead of quietly becoming "unknown".
_RESTARTED = re.compile(r"^the server restarted mid-forge", re.I)                  # server.forge.restarted
_TOO_LONG = re.compile(r"^the forge ran past \d+\s*s\b.*abandoned", re.I)         # server.forge.too_long_job
_QUEUE_TIMEOUT = re.compile(r"^the forge stayed at capacity too long", re.I)       # server.forge.queue_timeout
_SAVE_FAILED = re.compile(r"^forged, but saving failed", re.I)                     # server.forge.saving_failed
_UNEXPECTED = re.compile(r"^unexpected error:", re.I)                              # server.forge.unexpected
_GENERATION = re.compile(r"^class did not generate:", re.I)                        # forge._bundle_result

_HTTP_MARK = re.compile(r"\bHTTP \d{3}\b|Error code: \d{3}", re.I)   # a provider actually answered

_REFUSAL_WHAT = {
    "model": "model not found",
    "routing": "no allowed route for the model",
    "credits": "out of credits",
    "key": "key rejected",
    "access": "key not allowed that model",
    "plan_limit": "request over the plan's per-minute cap",
    "rate_limit": "rate-limited",
    "down": "provider down / overloaded",
}

# kind -> (label, attention). The fixed table the API and the tests both read; per-mode kinds are listed
# explicitly so a new kind can't appear without a label.
KINDS: dict[str, tuple[str, bool]] = {
    **{f"user_{k}": (f"User's key: {w}", False) for k, w in _REFUSAL_WHAT.items()},
    **{f"hosted_{k}": (f"Hosted route: {w}", True) for k, w in _REFUSAL_WHAT.items()},
    "user_config": ("User's key: setup mistake (base URL / fields)", False),
    "slow_byok": ("Slow on user's model", False),
    "slow_hosted": ("Slow on our hosted route", True),
    "restart": ("Deploy restart (refunded)", False),
    "queue_timeout": ("Queue full too long (capacity)", True),
    "save_failed": ("Forged, but saving failed", True),
    "generation": ("Generation failed", True),
    "unexpected": ("Unexpected error", True),
    "unknown": ("Unrecognised failure", True),
}

# A refusal sentence forge.py wrote first -> its kind, for rows whose raw provider text was cut off by the
# 500-char error column (the sentence survives; the provider's own words may not).
_SENTENCE_KIND = [(text.split("{", 1)[0][:40], kind) for kind, _pat, text in PROVIDER_REFUSALS]


def _refusal_kind(text: str) -> str | None:
    """The refusal kind of a stored error. When the text is forge's "<sentence> (Your provider said: <raw>)",
    the RAW part decides (the sentence may predate a wording fix, e.g. a 413 explained as a rate limit), but
    the sentence wins over a merely generic raw match (a bare 429) or none at all — the raw part may have been
    truncated before the decisive words."""
    sentence_kind = None
    for prefix, kind in _SENTENCE_KIND:
        if text.startswith(prefix):
            sentence_kind = kind
            break
    if sentence_kind is not None:
        raw = text.split(PROVIDER_SAID, 1)[1] if PROVIDER_SAID in text else ""
        raw_kind = provider_refusal_kind(raw)
        if raw_kind is None or (raw_kind == "rate_limit" and sentence_kind != "rate_limit"):
            return sentence_kind
        return raw_kind
    return provider_refusal_kind(text)


def _result(kind: str, label: str | None = None) -> dict:
    base_label, attention = KINDS[kind]
    return {"kind": kind, "label": label or base_label, "attention": attention}


def classify(error: str | None, mode: str | None, class_id: int | None = None) -> dict:
    """{"kind", "label", "attention"} for one failed forge_jobs row (error text, mode, class_id)."""
    text = " ".join(str(error or "").split())   # one line: stored provider bodies carry newlines
    byok = (mode or "") == "byok"
    landed = class_id is not None

    # Server texts first: they are ours verbatim and can't be confused with a provider body.
    if _RESTARTED.search(text):
        return _result("restart")
    if _TOO_LONG.search(text):
        kind = "slow_byok" if byok else "slow_hosted"
        base = KINDS[kind][0]
        return _result(kind, f"{base} (class landed late)" if landed else f"{base} (never finished)")
    if _QUEUE_TIMEOUT.search(text):
        return _result("queue_timeout")
    if _SAVE_FAILED.search(text):
        return _result("save_failed")

    # A provider refusal anywhere in the text, whatever prefix ("unexpected error:", "class did not
    # generate:") forge put in front of it.
    sub = _refusal_kind(text)
    if sub is None and _PROVIDER_DOWN.search(text):
        sub = "down"
    # A generation failure whose validator text merely CONTAINS a refusal word ("forbidden", "not found")
    # is not a provider refusal: without an HTTP status / SDK error code in it, it stays "generation", so
    # a BYOK row is never muted on a coincidence.
    if sub is not None and _GENERATION.search(text) and not _HTTP_MARK.search(text):
        sub = None
    if sub is not None:
        return _result(f"user_{sub}" if byok else f"hosted_{sub}")

    if byok and _USER_CONFIG.search(text):
        return _result("user_config")
    if _GENERATION.search(text):
        return _result("generation")
    if _UNEXPECTED.search(text):
        return _result("unexpected")
    return _result("unknown")


def summarize(rows) -> dict:
    """Window totals over classified rows (dicts with kind/label/attention): {total, attention, by_kind},
    by_kind = [{kind, label, attention, n}] sorted by n desc (then kind). Grouped by KIND with its base
    label, so the per-row "(class landed late)" detail doesn't split a group."""
    by: dict[str, int] = {}
    attention = 0
    total = 0
    for r in rows:
        total += 1
        attention += int(bool(r["attention"]))
        by[r["kind"]] = by.get(r["kind"], 0) + 1
    by_kind = [{"kind": k, "label": KINDS[k][0], "attention": KINDS[k][1], "n": n}
               for k, n in sorted(by.items(), key=lambda kv: (-kv[1], kv[0]))]
    return {"total": total, "attention": attention, "by_kind": by_kind}

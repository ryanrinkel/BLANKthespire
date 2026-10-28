"""Server-side copy lookups: the same web/static/i18n/<lang>.json files the browser reads (docs/plans/I18N_PLAN.md,
"Source of truth and build"), so an email subject, a Stripe line item and a JSON error come from exactly the
place the site's own text does (docs/copy/COPY.md -> web/tools/build_i18n.py -> <lang>.json).

Every `strings` value in the json is HTML (literal < > & escaped, COPY.md markup turned into <strong>/<em>/<a>/
<code>). get_text() gives plain text for mail bodies, subjects and JSON errors; get_html() gives HTML with the
runtime values escaped. A key the language lacks falls back to English, then to the key itself.

JSON errors: error_body("server.forge.out_of_tokens") -> {"error": <English>, "code": "forge.out_of_tokens"}.
The browser shows t("server." + code, vars) and falls back to `error`. match_error() maps an English message
that was built elsewhere (a ForgeError, a stored job error) back to its code.
"""
from __future__ import annotations

import html as _html
import importlib.util
import json
import re
import threading
from pathlib import Path

WEB_DIR = Path(__file__).resolve().parent
I18N_DIR = WEB_DIR / "static" / "i18n"
BUILD_SCRIPT = WEB_DIR / "tools" / "build_i18n.py"

LANGS = ("en", "zh")
DEFAULT_LANG = "en"
SERVER_PREFIX = "server."

_lock = threading.Lock()
_cache: dict[str, tuple[float | None, dict]] = {}  # lang -> (mtime, strings)
_built_en: dict | None = None
_PH_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
_TAG_RE = re.compile(r"<[^>]+>")


def normalize_lang(value) -> str:
    """'en' | 'zh'; anything else (None, '', 'fr', 'zh-CN'...) is English, except a 'zh-*' tag which is zh."""
    v = str(value or "").strip().lower()
    if v in LANGS:
        return v
    if v.startswith("zh-") or v.startswith("zh_"):
        return "zh"
    return DEFAULT_LANG


def _build_english() -> dict:
    """en strings built in memory from docs/copy/COPY.md, for a checkout where en.json was not written yet."""
    global _built_en
    if _built_en is None:
        try:
            spec = importlib.util.spec_from_file_location("_bts_build_i18n", BUILD_SCRIPT)
            mod = importlib.util.module_from_spec(spec)
            assert spec.loader is not None
            spec.loader.exec_module(mod)
            _built_en = dict(mod.build().outputs["en"]["strings"])
        except Exception:  # noqa: BLE001 - no copy source at all: every lookup returns its key
            _built_en = {}
    return _built_en


def _load(lang: str) -> dict:
    path = I18N_DIR / f"{lang}.json"
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = None
    with _lock:
        hit = _cache.get(lang)
        if hit is not None and hit[0] == mtime and mtime is not None:
            return hit[1]
    strings: dict = {}
    if mtime is not None:
        try:
            strings = dict((json.loads(path.read_text(encoding="utf-8")) or {}).get("strings") or {})
        except (OSError, ValueError):
            strings = {}
    if not strings and lang == DEFAULT_LANG:
        strings = _build_english()
    with _lock:
        _cache[lang] = (mtime, strings)
    return strings


def clear_cache() -> None:
    global _built_en
    with _lock:
        _cache.clear()
    _built_en = None


def get_strings(lang) -> dict:
    """Every string for `lang`, with English filled in for each key the language does not have."""
    lang = normalize_lang(lang)
    en = _load(DEFAULT_LANG)
    if lang == DEFAULT_LANG:
        return dict(en)
    merged = dict(en)
    merged.update(_load(lang))
    return merged


def _raw(lang, key: str) -> str:
    lang = normalize_lang(lang)
    if lang != DEFAULT_LANG:
        s = _load(lang).get(key)
        if s is not None:
            return s
    s = _load(DEFAULT_LANG).get(key)
    return key if s is None else s


def _fill(s: str, vars: dict, escape: bool) -> str:
    def sub(m):
        name = m.group(1)
        if name not in vars or vars[name] is None:
            return m.group(0)
        v = str(vars[name])
        return _html.escape(v, quote=True) if escape else v
    return _PH_RE.sub(sub, s)


def to_text(s: str) -> str:
    """HTML string -> plain text: tags dropped, entities decoded."""
    return _html.unescape(_TAG_RE.sub("", s))


def get_text(lang, key: str, **vars) -> str:
    """Plain text (mail, subjects, JSON errors). Values are inserted after the markup is stripped, as is."""
    return _fill(to_text(_raw(lang, key)), vars, escape=False)


def get_html(lang, key: str, **vars) -> str:
    """HTML (mail bodies). Values are HTML-escaped before they are inserted."""
    return _fill(_raw(lang, key), vars, escape=True)


# ------------------------------------------------------------------------------------------- errors

def code_of(key: str) -> str:
    return key[len(SERVER_PREFIX):] if key.startswith(SERVER_PREFIX) else key


def error_body(key: str, **vars) -> dict:
    """{"error": English text, "code": key minus "server."} (+ "vars" when the text has placeholders)."""
    out = {"error": get_text(DEFAULT_LANG, key, **vars), "code": code_of(key)}
    if vars:
        out["vars"] = {k: ("" if v is None else str(v)) for k, v in vars.items()}
    return out


_match_cache: tuple[int, list] | None = None


def _matchers() -> list:
    global _match_cache
    en = _load(DEFAULT_LANG)
    if _match_cache is not None and _match_cache[0] == id(en):
        return _match_cache[1]
    rules = []
    for key, value in en.items():
        if not key.startswith(SERVER_PREFIX):
            continue
        text = to_text(value)
        names = _PH_RE.findall(text)
        if not names:
            rules.append((key, None, text))
            continue
        pattern, pos, seen = "^", 0, set()
        for m in _PH_RE.finditer(text):
            pattern += re.escape(text[pos:m.start()])
            name = m.group(1)
            pattern += f"(?P={name})" if name in seen else f"(?P<{name}>.*?)"
            seen.add(name)
            pos = m.end()
        pattern += re.escape(text[pos:]) + "$"
        try:
            rules.append((key, re.compile(pattern, re.S), None))
        except re.error:
            continue
    # exact texts first, then templates with the most literal text (the most specific) first
    rules.sort(key=lambda r: (r[1] is not None, -len(r[1].pattern) if r[1] is not None else 0))
    _match_cache = (id(en), rules)
    return rules


def match_error(message) -> tuple[str, dict] | None:
    """(code, vars) for an English server message, or None when it is not one of COPY.md's server.* texts."""
    msg = str(message or "")
    if not msg:
        return None
    for key, rx, exact in _matchers():
        if rx is None:
            if msg == exact:
                return code_of(key), {}
        else:
            m = rx.match(msg)
            if m:
                return code_of(key), {k: v for k, v in m.groupdict().items()}
    return None


def with_code(body: dict) -> dict:
    """Add code (and vars) to a {"error": ...} dict whose message is a known server text. Leaves it alone
    otherwise, and never overwrites a code that is already there."""
    if isinstance(body, dict) and body.get("error") and "code" not in body:
        hit = match_error(body["error"])
        if hit is not None:
            body["code"] = hit[0]
            if hit[1]:
                body["vars"] = hit[1]
    return body

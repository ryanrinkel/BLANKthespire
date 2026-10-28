"""Per-forge creative-text translation (I18N plan, C2) and the bundle `loc` block.

A forge is generated in English. When the player forged in another site language, ONE strict-JSON model
call at the end translates the class's creative strings (names, flavor, model-written prose) into the
GAME's locale, and the result rides the bundle as an optional top-level `loc` block keyed by the game
locale code (`zhs`, never the site's `zh`). English stays the primary strings, so the class still works
in the English UI; any string missing from `loc` falls back to English in the mod. Card rules text is
never translated here: the mod renders it from effects through its own locale tables.

How the web calls it (after assembly, before `encode_class`):

    from btsgen.loc import apply_loc, load_glossary, translate_bundle, translate_concept
    concept_en = translate_concept(concept, make_gen, lang)          # before the pipeline, CJK concepts only
    ...
    loc = translate_bundle(res.bundle, lang, make_gen, glossary=load_glossary(), on_event=on_event)
    if loc:
        apply_loc(res.bundle, lang, loc)
    code = encode_class(json.dumps(res.bundle, separators=(",", ":")))

`gen` is the same `make_gen(contract_mod, *, max_tokens)` factory the staged front-end uses (web/forge.py
`_make_gen_factory`, or `build_ollama_mix()[3]` on the hosted route). The translation contracts resolve to
the "structure" (design) role in `ollama_mix._resolve_role`, so the hosted route runs them on the design
model with its `reasoning_effort: "low"` extra_body, and BYOK runs them on the user's design model. The
offline fake factory (`frontend.fakes._StageFake`) works too: each contract has a `fake_output`.

Nothing here raises out of `translate_bundle` / `translate_concept`: a model, network or parse failure is
logged through `on_event` and the forge carries on in English.

Bundle paths (the flat keys `collect_strings` returns; RFC 6901 style: "/"-joined, "~" -> "~0", "/" -> "~1"):

    character/name                 character.name
    character/description          character.description
    archetypes/<i>/name            bundle.archetypes[i].name   (only if the bundle carries archetypes)
    cards/<card id>/name           cards[].name, keyed by cards[].id
    cards/<card id>/flavor         cards[].flavor (optional)
    relic/name, relic/description  bundle.relic (top-level sibling of character)
    potions/<english name>/name|description    character.potion_pool[]
    statuses/<english name>/name|description   character.status_pool[]
    summons/<english name>/name|description    character.summon_pool[]
    orbs/<english name>/name|description       character.orb_pool[] dict entries (base-orb name strings skip)

`translate_bundle` returns the nested `loc[<locale>]` dict in the plan's schema:
    {"character": {...}, "archetypes": [{"name"}...], "cards": {id: {name, flavor}}, "relic": {...},
     "potions": {english name: {name, description}}, "statuses": {...}, "summons": {...}, "orbs": {...}}
"""
from __future__ import annotations

import json
import os
import re
from collections import Counter
from pathlib import Path

# --- language tables (adding a language = one entry in each) -----------------------------------------
GAME_LOCALE = {"zh": "zhs"}                                   # site language -> game locale code
LANG_NAMES = {"zhs": "Simplified Chinese (简体中文)"}         # game locale -> name used in the prompt
# Per-locale validation rules. script: which script a translated value must contain ("cjk" or None for a
# Latin-script language). name_target / name_cap: card-name length (characters) the card frame holds.
LOCALE_RULES = {"zhs": {"script": "cjk", "name_target": 8, "name_cap": 12}}
_DEFAULT_RULES = {"script": None, "name_target": 20, "name_cap": 30}

# Pool sections: bundle character key -> loc section name.
_POOLS = (("potion_pool", "potions"), ("status_pool", "statuses"),
          ("summon_pool", "summons"), ("orb_pool", "orbs"))

_PLACEHOLDER = re.compile(r"\{[^{}]*\}")
_MARKUP = re.compile(r"\[/?[A-Za-z_][A-Za-z0-9_]*(?:=[^\]]*)?\]|</?[A-Za-z_][A-Za-z0-9_]*(?:\s[^<>]*)?/?>")
_LATIN_RUN = re.compile(r"[A-Za-z]{3,}")
_CJK = re.compile("[㐀-䶿一-鿿豈-﫿\U00020000-\U0002ebef]")

_BASE_MAX_TOKENS = 4000


def game_locale(lang: str | None) -> str | None:
    """Site language ("zh") -> game locale ("zhs"). A game locale passes through. None for en/unknown."""
    if not lang:
        return None
    lang = str(lang).strip().lower()
    if lang in GAME_LOCALE:
        return GAME_LOCALE[lang]
    if lang in LANG_NAMES:
        return lang
    return None


def has_cjk(s) -> bool:
    return bool(s) and bool(_CJK.search(str(s)))


def load_glossary(path: str | os.PathLike | None = None) -> str:
    """docs/copy/GLOSSARY.md (or BTS_GLOSSARY_FILE), or "" when absent/unreadable."""
    p = Path(path or os.environ.get("BTS_GLOSSARY_FILE")
             or Path(__file__).resolve().parents[2] / "docs" / "copy" / "GLOSSARY.md")
    try:
        return p.read_text(encoding="utf-8")
    except OSError:
        return ""


# --- paths --------------------------------------------------------------------------------------------
def _esc(seg) -> str:
    return str(seg).replace("~", "~0").replace("/", "~1")


def _unesc(seg: str) -> str:
    return seg.replace("~1", "/").replace("~0", "~")


def _path(*segs) -> str:
    return "/".join(_esc(s) for s in segs)


def _split(path: str) -> list[str]:
    return [_unesc(s) for s in path.split("/")]


def _text(v) -> str:
    return v.strip() if isinstance(v, str) else ""


def collect_strings(bundle: dict) -> dict:
    """{path: english text} for every non-empty creative string in a class bundle (see module docstring)."""
    out: dict[str, str] = {}
    if not isinstance(bundle, dict):
        return out

    def put(path: str, value) -> None:
        t = _text(value)
        if t:
            out[path] = t

    ch = bundle.get("character") if isinstance(bundle.get("character"), dict) else {}
    put(_path("character", "name"), ch.get("name"))
    put(_path("character", "description"), ch.get("description"))
    for i, a in enumerate(bundle.get("archetypes") or []):
        if isinstance(a, dict):
            put(_path("archetypes", i, "name"), a.get("name"))
    for c in bundle.get("cards") or []:
        if isinstance(c, dict) and _text(c.get("id")):
            cid = _text(c.get("id"))
            put(_path("cards", cid, "name"), c.get("name"))
            put(_path("cards", cid, "flavor"), c.get("flavor"))
    relic = bundle.get("relic")
    if isinstance(relic, dict):
        put(_path("relic", "name"), relic.get("name"))
        put(_path("relic", "description"), relic.get("description"))
    for pool_key, section in _POOLS:
        for e in ch.get(pool_key) or []:
            if isinstance(e, dict) and _text(e.get("name")):  # base-orb name strings are base-game localized
                name = _text(e.get("name"))
                put(_path(section, name, "name"), name)
                put(_path(section, name, "description"), e.get("description") or e.get("text"))
    return out


def _nest(flat: dict) -> dict:
    """{path: value} -> the loc[<locale>] schema. archetypes become a list in bundle order (missing -> {})."""
    loc: dict = {}
    arche: dict[int, dict] = {}
    for path, value in flat.items():
        segs = _split(path)
        if segs[0] == "archetypes" and len(segs) == 3 and segs[1].isdigit():
            arche.setdefault(int(segs[1]), {})[segs[2]] = value
            continue
        node = loc
        for s in segs[:-1]:
            node = node.setdefault(s, {})
        node[segs[-1]] = value
    if arche:
        loc["archetypes"] = [arche.get(i, {}) for i in range(max(arche) + 1)]
    return loc


# --- validation ---------------------------------------------------------------------------------------
def _is_card_name(path: str) -> bool:
    segs = _split(path)
    return len(segs) == 3 and segs[0] == "cards" and segs[2] == "name"


def _check(path: str, en: str, value, rules: dict) -> str | None:
    """None if `value` is an acceptable translation of `en`, else a short ASCII reason."""
    if not isinstance(value, str) or not value.strip():
        return "empty"
    value = value.strip()
    if Counter(_PLACEHOLDER.findall(en)) != Counter(_PLACEHOLDER.findall(value)):
        return "placeholder changed"
    if Counter(_MARKUP.findall(en)) != Counter(_MARKUP.findall(value)):
        return "markup changed"
    wordy = bool(_LATIN_RUN.search(en))  # English with no 3+ letter run is a code/number: may pass through
    if wordy and value == en:
        return "untranslated"
    if rules.get("script") == "cjk" and wordy and not has_cjk(value):
        return "no CJK"
    if _is_card_name(path) and len(value) > int(rules.get("name_cap", 99)):
        return "name too long"
    return None


def validate_translations(strings: dict, got: dict, locale: str) -> tuple[dict, dict]:
    """(kept {path: value}, dropped {path: reason}) — unknown paths are ignored, missing ones are 'missing'."""
    rules = LOCALE_RULES.get(locale, _DEFAULT_RULES)
    kept, dropped = {}, {}
    for path, en in strings.items():
        if path not in got:
            dropped[path] = "missing"
            continue
        why = _check(path, en, got[path], rules)
        if why:
            dropped[path] = why
        else:
            kept[path] = got[path].strip()
    return kept, dropped


# --- prompts / contracts ------------------------------------------------------------------------------
def _system_prompt(locale: str, glossary: str) -> str:
    rules = LOCALE_RULES.get(locale, _DEFAULT_RULES)
    lname = LANG_NAMES.get(locale, locale)
    parts = [
        f"You translate the player-facing creative text of a custom Slay the Spire 2 character class into "
        f"{lname}. The text is game UI: card names, flavor lines, and short item descriptions.",
        "RULES:",
        "1. Reply with ONE JSON object and nothing else: the SAME keys you were given, each value replaced by "
        "its translation. Do not add, drop or rename keys. No prose, no code fences.",
        "2. Keep every {placeholder} (anything in curly braces) byte-for-byte, and every [markup] tag and "
        "<tag> verbatim. Translate only the words around them.",
        "3. Keep \"Blank the Spire\", codes, numbers and identifiers in Latin letters.",
        f"4. Card names (keys like cards/<id>/name) must be short: aim for {rules['name_target']} characters "
        f"or fewer, never more than {rules['name_cap']}. Make them punchy, like the base game's card names.",
        "5. Flavor lines may be translated loosely for tone; keep them one line.",
        "6. Descriptions of relics, potions, statuses, summons and orbs: translate the meaning exactly, "
        "including every number. Use the game's established term for each keyword (see the glossary).",
        "7. Proper nouns that are deliberately English (a person's name, a brand, a pun that only works in "
        "English) may stay as they are or be transliterated, whichever reads naturally to a player. "
        "Everything else must be translated.",
        "8. Use the same translation for the same English term everywhere in the object.",
    ]
    if glossary and glossary.strip():
        parts += ["", "GLOSSARY (use these established terms):", glossary.strip()]
    return "\n".join(parts)


class _TranslateContract:
    """Duck-typed stage contract (system_prompt / user_brief / repair_message / fake_output)."""

    def __init__(self, locale: str, glossary: str = "") -> None:
        self.locale = locale
        self._system = _system_prompt(locale, glossary or "")

    def system_prompt(self) -> str:
        return self._system

    def user_brief(self, brief: dict) -> str:
        ctx = []
        if brief.get("concept"):
            ctx.append(f"Class concept (from the player): {brief['concept']}")
        if brief.get("description"):
            ctx.append(f"Character description: {brief['description']}")
        return ("\n".join(ctx) + "\n\n" if ctx else "") + (
            f"Translate every value into {LANG_NAMES.get(self.locale, self.locale)}. Strings:\n"
            + json.dumps(brief["strings"], ensure_ascii=False, indent=1)
            + "\n\nReturn only the JSON object with the same keys.")

    def repair_message(self, text: str, errors: list[str]) -> str:
        return ("Your reply could not be parsed as a JSON object (" + "; ".join(errors) + "). Return ONLY the "
                "JSON object: the same keys, translated values, no prose and no code fences.")

    def fake_output(self, brief: dict) -> dict:
        out = {}
        for i, (path, en) in enumerate(brief["strings"].items()):
            if _is_card_name(path):
                out[path] = f"测试卡{i}"
            else:
                out[path] = "测试：" + en  # keeps placeholders/markup, contains CJK
        return out


class _ConceptContract:
    """Concept-in translation: any language -> one short English concept (plain text)."""

    def system_prompt(self) -> str:
        return ("You translate a player's concept for a custom Slay the Spire 2 character class into English. "
                "Reply with the English concept only: plain text, at most 60 words, no quotes, no preamble. "
                "Keep every explicit mechanical ask in standard English game terms, verbatim where they "
                "already are English (for example \"orb class\", \"poison\", \"summoner\", \"discard\", "
                "\"exhaust\", \"block\", \"strength\"). Keep names of people, characters and brands.")

    def user_brief(self, concept: str) -> str:
        return f"Concept:\n{concept}"

    def repair_message(self, text: str, errors: list[str]) -> str:
        return "Reply with the English concept only, as plain text."

    def fake_output(self, concept: str) -> dict:
        return {"concept": "an offline fake translated concept"}


# --- calls --------------------------------------------------------------------------------------------
def _say(on_event, msg: str) -> None:
    if on_event is None:
        return
    try:
        on_event(msg.encode("ascii", "replace").decode("ascii"))  # forge log lines are ASCII (CLI console)
    except Exception:  # noqa: BLE001 — a log sink must never break a forge
        pass


def _short(e: BaseException) -> str:
    return " ".join(f"{type(e).__name__}: {e}".split())[:200]


_PAIR = re.compile(r'"((?:[^"\\]|\\.)*)"\s*:\s*"((?:[^"\\]|\\.)*)"')


def _parse(text: str, keys) -> dict | None:
    """The reply's {path: value} object, or None. Unwraps a single wrapper key ({"strings": {...}})."""
    from .generator import extract_card_json
    try:
        obj = extract_card_json(text or "")
    except ValueError:
        return None
    keys = set(keys)
    if not (keys & set(obj)) and len(obj) == 1:
        inner = next(iter(obj.values()))
        if isinstance(inner, dict):
            obj = inner
    return obj


def _salvage(text: str, keys) -> dict:
    """Best-effort "key": "value" pairs out of a truncated/malformed reply (only known keys)."""
    keys = set(keys)
    out = {}
    for k, v in _PAIR.findall(text or ""):
        try:
            k, v = json.loads(f'"{k}"'), json.loads(f'"{v}"')
        except ValueError:
            continue
        if k in keys:
            out[k] = v
    return out


def _reasons(dropped: dict) -> str:
    return ", ".join(f"{n} {why}" for why, n in Counter(dropped.values()).most_common())


def translate_bundle(bundle: dict, lang: str, gen, *, glossary: str | None = None, on_event=None,
                     concept: str | None = None) -> dict | None:
    """The `loc[<locale>]` dict for `lang`, or None (en/unknown lang, nothing to translate, or failure).

    `gen` is a `make_gen(contract_mod, *, max_tokens)` factory. ONE model call, plus ONE retry when the reply
    is not parseable JSON. Each string is validated on its own; a failing string is dropped (the mod falls
    back to English). `concept` (optional) is the player's concept, sent as context. Never raises."""
    locale = game_locale(lang)
    if locale is None:
        return None
    tag = f"translation ({locale})"
    try:
        strings = collect_strings(bundle)
        if not strings:
            return None
        ch = bundle.get("character") or {}
        brief = {"strings": strings, "concept": _text(concept),
                 "description": _text(ch.get("description")) if isinstance(ch, dict) else ""}
        max_tokens = max(_BASE_MAX_TOKENS, min(12000, 2000 + 60 * len(strings)))
        g = gen(_TranslateContract(locale, glossary or ""), max_tokens=max_tokens)
        text, messages = g.first_attempt(brief)
        texts = [text]
        got = _parse(text, strings)
        if got is None:
            text, messages = g.repair(messages, text, ["no JSON object found"])
            texts.append(text)
            got = _parse(text, strings)
        if got is None:  # both unparseable: keep whatever complete pairs a truncated reply still holds
            for t in reversed(texts):
                got = _salvage(t, strings) or None
                if got:
                    break
        if not got:
            _say(on_event, f"{tag} skipped: reply was not a JSON object (2 tries)")
            return None
        kept, dropped = validate_translations(strings, got, locale)
        if not kept:
            _say(on_event, f"{tag} skipped: no string passed validation ({_reasons(dropped)})")
            return None
        line = f"{tag}: {len(kept)}/{len(strings)} strings"
        if dropped:
            line += f", {len(dropped)} fell back to English ({_reasons(dropped)})"
        _say(on_event, line)
        return _nest(kept)
    except Exception as e:  # noqa: BLE001 — the translation can never fail the forge
        _say(on_event, f"{tag} skipped: {_short(e)}")
        return None


def _needs_concept_translation(concept: str, lang: str | None) -> bool:
    if has_cjk(concept):
        return True
    return game_locale(lang) is not None and not _LATIN_RUN.search(concept)


def translate_concept(concept: str, gen, lang: str | None, *, on_event=None) -> str:
    """The English concept to run the pipeline on. Unchanged unless it is CJK (or a non-English forge with no
    Latin words); then ONE small call through the `make_gen` factory `gen`. Any failure returns the original."""
    if not isinstance(concept, str) or not concept.strip() or not _needs_concept_translation(concept, lang):
        return concept
    try:
        g = gen(_ConceptContract(), max_tokens=1500)
        text, _ = g.first_attempt(concept.strip())
        text = (text or "").strip()
        # A JSON-shaped reply (the offline fake, or a model that wrapped it): take the first string value.
        if text.startswith("{") or text.startswith('"'):
            try:
                obj = json.loads(text)
                if isinstance(obj, dict):
                    obj = next((v for v in obj.values() if isinstance(v, str)), "")
                if isinstance(obj, str):
                    text = obj.strip()
            except ValueError:
                pass
        text = re.sub(r"^```\w*\s*|\s*```$", "", text).strip().strip('"').strip()
        if text.lower().startswith("concept:"):
            text = text[len("concept:"):].strip()
        words = text.split()
        if len(words) > 60:
            text = " ".join(words[:60])
        if not _LATIN_RUN.search(text) or has_cjk(text):
            _say(on_event, "concept translation skipped: reply was not English")
            return concept
        _say(on_event, f"concept translated to English: {text}")
        return text
    except Exception as e:  # noqa: BLE001 — a failed translation just keeps the player's own words
        _say(on_event, f"concept translation skipped: {_short(e)}")
        return concept


def _merge(a, b):
    if isinstance(a, dict) and isinstance(b, dict):
        out = dict(a)
        for k, v in b.items():
            out[k] = _merge(a[k], v) if k in a else v
        return out
    if isinstance(a, list) and isinstance(b, list):
        return [_merge(a[i], b[i]) if i < len(a) else b[i] for i in range(len(b))] + a[len(b):]
    return b


def apply_loc(bundle: dict, lang: str, loc_dict: dict | None) -> dict:
    """bundle["loc"][<locale>] = loc_dict (deep-merged into any existing block). Returns the bundle."""
    if not loc_dict or not isinstance(bundle, dict):
        return bundle
    locale = game_locale(lang) or lang
    block = bundle.setdefault("loc", {})
    block[locale] = _merge(block.get(locale) or {}, loc_dict)
    return bundle

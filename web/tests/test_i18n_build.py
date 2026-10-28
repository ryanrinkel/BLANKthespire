"""tools/build_i18n.py: docs/copy/COPY*.md -> web/static/i18n/<lang>.json (docs/plans/I18N_PLAN.md).

Synthetic fixtures check the parser, markup, placeholder normalisation, console regexes and each validation
error; the real COPY.md must build cleanly and match the committed en.json (`--check`).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import build_i18n as bi  # noqa: E402

REPO = Path(__file__).resolve().parents[2]

EN = """# Copy source of truth

Intro prose with a {stray} placeholder and **bold** that is not an entry.

## Conventions
- `{name}` placeholders are runtime values.

    an indented line in the conventions prose, not an entry

## Landing page

### landing.hero.title
Where: static/landing.html:10
Notes: a note.

    Forge **a class** from *one* sentence — see [the help](/help) & `BTSC.` <now>

### landing.hero.body
Where: static/landing.html:11

    First paragraph for {name}.

    Second paragraph.

### app.frag.suffix
Where: static/app.js:1
Notes: fragment, starts with a space.

     · {count} images

### app.tokens.chip.one
Where: static/app.js:2

    1 token

### app.tokens.chip.other
Where: static/app.js:2

    {count} tokens

### server.err.raw
Where: app.py:3

    provider said: {raw[:300]} (HTTP {e.code})

## Steam Workshop

### workshop.description
Where: workshop.json:3

    [h1]Hello **not markdown** & <b>[/h1]

### mod.dialog.imported
Where: ForgeConfig.cs:60

    Imported into class slot {classSlot:00}: {e.Message}

## Forge console stage headers

### console.stage.cloud
Where: builder.py:374

    [1/6] cloud: brainstorming free associations on '{concept}'...

### console.card.ready
Where: class_forge.py:3714

    card {i+1}/{total}: {pres.card.get('name')} ready…

### console.relic.ok
Where: class_forge.py:3902

    relic OK: {relic.get('name')}

### console.collide
Where: x.py:1

    {a.b} and {ab} and {a.b} again

## Out of scope

- static/privacy.html: English-only.

## Inventory

| Section | Entries |
|---|---|
| Landing | 2 |
"""


def write(tmp_path: Path, en: str = EN, **langs: str) -> Path:
    for name, text in (("COPY.md", en), *((f"COPY.{k}.md", v) for k, v in langs.items())):
        with open(tmp_path / name, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    return tmp_path


def entry(key: str, text: str) -> str:
    body = "\n".join("    " + ln if ln else "    " for ln in text.split("\n"))
    return f"### {key}\nWhere: x\n\n{body}\n\n"


def js_to_py(pattern: str) -> str:
    return re.sub(r"\\k<(\w+)>", r"(?P=\1)", pattern.replace("(?<", "(?P<"))


# ------------------------------------------------------------------------------------------- (a) build

def test_synthetic_english_build(tmp_path):
    out = bi.build(write(tmp_path)).outputs
    assert set(out) == {"en"}
    en = out["en"]
    assert en["lang"] == "en"
    s = en["strings"]
    # only ### entries; prose, conventions, out-of-scope and inventory are ignored
    assert set(s) == {"landing.hero.title", "landing.hero.body", "app.frag.suffix", "app.tokens.chip.one",
                      "app.tokens.chip.other", "server.err.raw", "workshop.description", "mod.dialog.imported"}
    assert set(en["console"]) == {"console.stage.cloud", "console.card.ready", "console.relic.ok", "console.collide"}
    assert s["landing.hero.title"] == ('Forge <strong>a class</strong> from <em>one</em> sentence — see '
                                       '<a href="/help">the help</a> &amp; <code>BTSC.</code> &lt;now&gt;')
    assert s["landing.hero.body"] == "First paragraph for {name}.\n\nSecond paragraph."
    assert s["app.frag.suffix"] == " · {count} images"  # leading space of a fragment survives
    assert s["server.err.raw"] == "provider said: {raw300} (HTTP {ecode})"
    # BBCode and C# stay verbatim
    assert s["workshop.description"] == "[h1]Hello **not markdown** & <b>[/h1]"
    assert s["mod.dialog.imported"] == "Imported into class slot {classSlot:00}: {e.Message}"


def test_console_regex_matches_english_lines(tmp_path):
    con = bi.build(write(tmp_path)).outputs["en"]["console"]
    cloud = con["console.stage.cloud"]
    assert cloud["re"] == (r"^\[1/6\] cloud: brainstorming free associations on '(?<concept>.*?)'\.\.\."
                           r"(?<rest>.*)$")
    assert cloud["text"] == "[1/6] cloud: brainstorming free associations on '{concept}'...{rest}"
    m = re.match(js_to_py(cloud["re"]), "[1/6] cloud: brainstorming free associations on 'a sad goose'...")
    assert m.groupdict() == {"concept": "a sad goose", "rest": ""}
    # a conditional suffix the code appends lands in `rest`
    m = re.match(js_to_py(cloud["re"]), "[1/6] cloud: brainstorming free associations on 'x'... [v2]")
    assert m.groupdict() == {"concept": "x", "rest": " [v2]"}
    assert not re.match(js_to_py(cloud["re"]), "[0/6] cloud: brainstorming free associations on 'x'...")

    card = con["console.card.ready"]
    assert card["text"] == "card {i1}/{total}: {prescardgetname} ready…{rest}"
    m = re.match(js_to_py(card["re"]), "card 3/12: Plague Lance ready…")
    assert m.groupdict() == {"i1": "3", "total": "12", "prescardgetname": "Plague Lance", "rest": ""}

    col = con["console.collide"]
    assert col["text"] == "{ab} and {ab_2} and {ab} again{rest}"
    assert col["re"] == "^(?<ab>.*?) and (?<ab_2>.*?) and \\k<ab> again(?<rest>.*)$"
    assert re.match(js_to_py(col["re"]), "x and y and x again")
    assert not re.match(js_to_py(col["re"]), "x and y and z again")

    # a template ending in a placeholder: that group is greedy, so `rest` cannot steal its text
    tail = con["console.relic.ok"]
    assert tail["re"] == "^relic OK: (?<relicgetname>.*)(?<rest>.*)$"
    m = re.match(js_to_py(tail["re"]), "relic OK: Plague Mask, relic 'x'")
    assert m.groupdict() == {"relicgetname": "Plague Mask, relic 'x'", "rest": ""}


def test_derive_name_rule():
    assert bi.derive_name("count") == "count"
    assert bi.derive_name("_harness") == "_harness"
    assert bi.derive_name("i+1") == "i1"
    assert bi.derive_name("card['name']") == "cardname"
    assert bi.derive_name("len(concepts)") == "lenconcepts"
    assert bi.derive_name("'ok' if ok else 'FAILED'") == "okifokelseFAILED"
    assert bi.derive_name("1+n") == "_1n"
    assert bi.derive_name("'!'") == "expr"


def test_translation_build_fallback_and_plural(tmp_path, capsys):
    zh = ("## 落地页\n\n"
          + entry("landing.hero.title", "从一句话**锻造**职业")
          + entry("app.tokens.chip.other", "{count} 个代币")
          + entry("server.err.raw", "服务商说：{raw[:300]}（HTTP {e.code}）")
          + entry("mod.dialog.imported", "已导入职业槽 {classSlot:00}：{e.Message}")
          + entry("console.card.ready", "卡牌 {i+1}/{total}：{pres.card.get('name')} 完成…"))
    d = tmp_path / "copy"
    d.mkdir()
    res = bi.build(write(d, zh=zh))
    zh_doc = res.outputs["zh"]
    s = zh_doc["strings"]
    assert zh_doc["lang"] == "zh"
    assert s["landing.hero.title"] == "从一句话<strong>锻造</strong>职业"
    assert s["app.tokens.chip.one"] == "{count} 个代币"  # .one reuses the translated .other
    assert s["server.err.raw"] == "服务商说：{raw300}（HTTP {ecode}）"
    assert s["mod.dialog.imported"] == "已导入职业槽 {classSlot:00}：{e.Message}"
    assert s["landing.hero.body"] == "First paragraph for {name}.\n\nSecond paragraph."  # English fallback
    card = zh_doc["console"]["console.card.ready"]
    assert card["re"] == res.outputs["en"]["console"]["console.card.ready"]["re"]  # always English
    assert card["text"] == "卡牌 {i1}/{total}：{prescardgetname} 完成…{rest}"
    assert zh_doc["console"]["console.stage.cloud"]["text"].startswith("[1/6] cloud:")
    missing = [w for w in res.warnings if "missing" in w]
    assert len(missing) == 1 and "COPY.zh.md: 6 key(s) missing" in missing[0]
    assert "landing.hero.body" in missing[0] and "app.tokens.chip.one" not in missing[0]

    out = tmp_path / "out"
    assert bi.main(["--copy-dir", str(d), "--out-dir", str(out)]) == 0
    assert json.loads((out / "zh.json").read_text(encoding="utf-8")) == zh_doc
    assert bi.main(["--copy-dir", str(d), "--out-dir", str(out), "--check"]) == 0
    (out / "zh.json").write_text("{}\n", encoding="utf-8")
    assert bi.main(["--copy-dir", str(d), "--out-dir", str(out), "--check"]) == 1
    assert "zh.json" in capsys.readouterr().err


def test_translation_rest_is_stripped_then_appended(tmp_path):
    zh = entry("console.stage.cloud", "[1/6] 云：{rest}联想 '{concept}'...{rest}")
    con = bi.build(write(tmp_path, zh=zh)).outputs["zh"]["console"]["console.stage.cloud"]
    assert con["text"] == "[1/6] 云：联想 '{concept}'...{rest}"
    m = re.match(js_to_py(con["re"]), "[1/6] cloud: brainstorming free associations on 'goose'... (v2)")
    assert con["text"].format(**m.groupdict()) == "[1/6] 云：联想 'goose'... (v2)"


def test_english_console_may_not_use_rest(tmp_path):
    with pytest.raises(bi.BuildError, match=r"'console.x.y' uses the reserved console placeholder \{rest\}"):
        bi.build(write(tmp_path, en=EN + entry("console.x.y", "done {rest}")))


def test_plural_one_may_carry_count(tmp_path):
    zh = entry("app.tokens.chip.one", "{count} 个代币") + entry("app.tokens.chip.other", "{count} 个代币")
    res = bi.build(write(tmp_path, zh=zh))
    assert res.outputs["zh"]["strings"]["app.tokens.chip.one"] == "{count} 个代币"


# ------------------------------------------------------------------------------------- (b) validation

@pytest.mark.parametrize("zh, needle", [
    (entry("landing.hero.nope", "x"), "is not a key in COPY.md"),
    ("### landing.hero.title\nWhere: x\n\n", "has empty text"),
    (entry("landing.hero.body", "没有占位符。"), "missing {name}"),
    (entry("landing.hero.body", "{name} 和 {who}"), "unknown {who}"),
    (entry("console.stage.cloud", "[1/6] 云：'{idea}'..."), "missing {concept}; unknown {idea}"),
    (entry("app.tokens.chip.one", "{count} 个 {extra}"), "unknown {extra}"),
    (entry("mod.dialog.imported", "槽 {classSlot}：{e.Message}"), "missing {classSlot:00}"),
    (entry("landing.hero.title", "a") + entry("landing.hero.title", "b"), "duplicate key 'landing.hero.title'"),
])
def test_translation_errors(tmp_path, zh, needle, capsys):
    with pytest.raises(bi.BuildError, match=re.escape(needle)):
        bi.build(write(tmp_path, zh=zh))
    assert bi.main(["--copy-dir", str(tmp_path), "--out-dir", str(tmp_path / "out")]) == 2
    assert needle in capsys.readouterr().err
    assert not (tmp_path / "out").exists()  # nothing written on error


def test_english_errors(tmp_path):
    with pytest.raises(bi.BuildError, match="duplicate key 'landing.hero.title'"):
        bi.build(write(tmp_path, en=EN + entry("landing.hero.title", "again")))
    with pytest.raises(bi.BuildError, match="'landing.empty' has no indented text block"):
        bi.build(write(tmp_path, en=EN + "### landing.empty\nWhere: x\n\n"))


# ----------------------------------------------------------------------------------------- (c) real copy

def test_real_copy_builds_and_en_json_is_current():
    res = bi.build(REPO / "docs" / "copy")
    assert not [w for w in res.warnings if "COPY.md" in w and "missing" not in w], res.warnings
    en = res.outputs["en"]
    assert len(en["strings"]) > 600 and len(en["console"]) >= 20
    assert all(k.startswith("console.") for k in en["console"])
    assert not any(k.startswith("console.") for k in en["strings"])
    assert bi.main(["--check"]) == 0, "web/static/i18n/en.json is stale: run python web/tools/build_i18n.py"
    raw = (REPO / "web" / "static" / "i18n" / "en.json").read_bytes()
    assert b"\r" not in raw and raw.endswith(b"}\n")
    # every console regex compiles (as Python, after the named-group translation) and matches its own template,
    # with `rest` empty; every text ends with the build-appended {rest}
    for key, c in en["console"].items():
        assert c["text"].endswith("{rest}") and c["text"].count("{rest}") == 1, key
        sample = re.sub(r"\{\w+\}", "X", c["text"][: -len("{rest}")])
        m = re.match(js_to_py(c["re"]), sample)
        assert m and m.group("rest") == "", key
    # the conditional-suffix headers now carry the suffix in `rest`
    harness = re.match(js_to_py(en["console"]["console.stage.harness"]["re"]),
                       "forge harness v7 (vocab v70) [creative harness v2]")
    assert harness.group("rest") == " [creative harness v2]"


# ---------------------------------------------------------------------------- (d) plain placeholders only

def test_real_placeholders_are_identifiers():
    doc = json.loads((REPO / "web" / "static" / "i18n" / "en.json").read_text(encoding="utf-8"))
    values = [(k, v) for k, v in doc["strings"].items() if not k.startswith(("mod.", "workshop."))]
    values += [(k, c["text"]) for k, c in doc["console"].items()]
    bad = [(k, p) for k, v in values for p in re.findall(r"\{([^{}]*)\}", v)
           if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", p)]
    assert not bad, bad

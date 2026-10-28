"""Build web/static/i18n/<lang>.json from docs/copy/COPY.md (English) and docs/copy/COPY.<lang>.md.

docs/plans/I18N_PLAN.md, "Source of truth and build". Run from the repo root:

    python web/tools/build_i18n.py            # write every <lang>.json
    python web/tools/build_i18n.py --check    # exit 1 if any json on disk is out of date (used by a test)

Input format (docs/copy/COPY.md, see its "Conventions" section): an entry is a `### key` heading, a `Where:`
line, an optional `Notes:` line, then the text indented four spaces. A blank line inside the block is a
paragraph break. Anything that is not inside a `### key` entry (the `## Conventions` / `## Voice` prose, the
"Out of scope" and "Inventory" sections, section intros) is ignored. Exactly four spaces of indent are removed
from each block line (a fragment that starts with a space keeps it); trailing whitespace is dropped.

Output shape (one file per language, keys sorted, UTF-8, indent 1):

    {"lang": "en",
     "strings": {"landing.hero.subtitle": "the spire", ...},
     "console": {"console.stage.cloud": {"re": "^\\[1/6\\] cloud: ...'(?<concept>.*?)'\\.\\.\\.(?<rest>.*)$",
                                         "text": "[1/6] cloud: ... '{concept}'...{rest}"}, ...}}

strings
    Every key except console.*. Inline markup becomes HTML: **x** -> <strong>, *x* -> <em>, [t](u) -> <a href>,
    `x` -> <code>. Literal <, >, & in the source are HTML-escaped first. Paragraphs are joined with "\n\n"
    (a single line break inside a paragraph stays "\n"). workshop.* (BBCode) and mod.* (C# format strings)
    are copied verbatim: no escaping, no markup, placeholders untouched.
console
    Every console.* key. `re` is always built from the ENGLISH template: the literal text is regex-escaped,
    each {name} becomes a lazy named group (?<name>.*?) (a repeat of the same name becomes \\k<name>), and the
    pattern ends with a catch-all (?<rest>.*) before the $ anchor. A placeholder that ENDS the template is
    greedy (?<name>.*) instead, so the catch-all cannot steal its text (rest is then empty). JavaScript syntax.
    `text` is that language's template, verbatim except for placeholder normalisation (below), with "{rest}"
    appended, so a conditional English suffix the code adds after the template (" [creative harness v2]",
    the relic / rate-limit suffixes) is carried over verbatim. `rest` is reserved: a COPY.md console template
    that uses {rest} fails the build; a translation's own {rest} is stripped. console.stage.blueprint_ready is
    the one template whose conditional part (" built around {_arche}") sits mid-template; a line without it
    does not match and stays English.

Placeholder normalisation (console.* and every strings key except workshop.* / mod.*):
    {ident} where ident matches [A-Za-z_][A-Za-z0-9_]* is kept as is. Any other {expr} (a Python f-string
    expression such as {i+1}, {len(cards)}, {card['name']}, {raw[:300]}, {e.code}) is renamed to a plain
    identifier: drop every character that is not [A-Za-z0-9_]; prefix "_" if the result starts with a digit;
    use "expr" if nothing is left; if two DIFFERENT expressions in one English entry collapse to the same
    name, the second gets "_2", the third "_3", ... The mapping is fixed by the English entry and reused for
    the translation, so {i+1} in COPY.zh.md becomes the same {i1} as in English. Examples: {i+1} -> {i1},
    {card['name']} -> {cardname}, {len(dossier.candidates)} -> {lendossiercandidates},
    {bp.get('max_hp', '?')} -> {bpgetmax_hp}, {e.Message} -> {eMessage}.

Validation (non-zero exit with a message): duplicate keys in any file; an English entry with no text; a
translation key that is not in COPY.md; a translation entry with empty text; a translation whose placeholder
set differs from the English one for that key (missing or extra). Plurals: when English has K.one and K.other,
a translation may give only K.other (K.one then reuses that translated text), and K.one may use any
placeholder of K.other (Chinese "{count} 个" for the English "1 token"). A translation missing a key falls
back to English and is listed as a warning (count + first 20 keys).
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
COPY_DIR = REPO / "docs" / "copy"
OUT_DIR = REPO / "web" / "static" / "i18n"

KEY_RE = re.compile(r"^[a-z0-9_]+(?:\.[a-z0-9_]+)+$")
IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
PLACEHOLDER_RE = re.compile(r"\{([^{}]+)\}")
LANG_FILE_RE = re.compile(r"^COPY\.([a-z]{2,3}(?:-[A-Za-z0-9]+)?)\.md$")
VERBATIM_PREFIXES = ("workshop.", "mod.")
CONSOLE_PREFIX = "console."
REST = "rest"  # reserved console group: whatever follows the template (a conditional English suffix)
# Characters with a meaning in a JavaScript (and Python) regex outside a character class. Escaping only these
# keeps the pattern valid under JS's `u` flag, which rejects needless escapes such as "\ " or "\-".
_RE_SPECIAL = set("\\^$.*+?()[]{}|")


class BuildError(Exception):
    """A validation failure: the build stops and nothing is written."""


@dataclass
class Entry:
    key: str
    text: str
    line: int
    section: str


@dataclass
class ParsedCopy:
    path: Path
    entries: dict[str, Entry] = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)  # layout oddities worth a warning, not fatal


# --------------------------------------------------------------------------------------------- parsing

def parse_copy(text: str, path: Path | str = "COPY.md") -> ParsedCopy:
    """Parse one COPY*.md file into entries. Raises BuildError on duplicate keys."""
    path = Path(path)
    out = ParsedCopy(path=path)
    errors: list[str] = []
    section = ""
    cur: dict | None = None  # {"key", "line", "section", "block": list|None, "done": bool}

    def finish():
        nonlocal cur
        if cur is None:
            return
        block = cur["block"]
        if block is None:
            out.entries[cur["key"]] = Entry(cur["key"], "", cur["line"], cur["section"])
        else:
            while block and block[-1] == "":
                block.pop()
            # collapse runs of blank lines to one paragraph break
            lines: list[str] = []
            for ln in block:
                if ln == "" and lines and lines[-1] == "":
                    continue
                lines.append(ln)
            out.entries[cur["key"]] = Entry(cur["key"], "\n".join(lines), cur["line"], cur["section"])
        cur = None

    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.rstrip("\r").rstrip(" \t")
        if raw.startswith("## ") or raw.startswith("# "):
            finish()
            section = raw.lstrip("#").strip()
            continue
        if raw.startswith("### "):
            finish()
            key = raw[4:].strip()
            if not KEY_RE.match(key):
                out.issues.append(f"{path.name}:{lineno}: key {key!r} does not look like page.section.item")
            if key in out.entries:
                errors.append(f"{path.name}:{lineno}: duplicate key {key!r} "
                              f"(first at line {out.entries[key].line})")
            cur = {"key": key, "line": lineno, "section": section, "block": None, "done": False}
            continue
        if cur is None:
            continue  # prose outside an entry
        indented = raw.startswith("    ") or raw.startswith("\t")
        if cur["done"]:
            if line:
                out.issues.append(f"{path.name}:{lineno}: stray text after the block of {cur['key']!r} ignored: "
                                  f"{line.strip()[:60]!r}")
            continue
        if cur["block"] is None:
            if indented and line.strip():
                cur["block"] = [_dedent(raw.rstrip("\r").rstrip(" \t"))]
            # else: Where:/Notes: metadata or blank lines before the block
            continue
        # inside a block
        if indented or not line:
            cur["block"].append(_dedent(line) if line else "")
        else:
            cur["done"] = True
            out.issues.append(f"{path.name}:{lineno}: text right after the block of {cur['key']!r} "
                              f"ignored: {line.strip()[:60]!r}")
    finish()
    if errors:
        raise BuildError("\n".join(errors))
    return out


def _dedent(line: str) -> str:
    if line.startswith("    "):
        return line[4:]
    if line.startswith("\t"):
        return line[1:]
    return line.strip() if not line.strip() else line


# ----------------------------------------------------------------------------------------- placeholders

def is_verbatim(key: str) -> bool:
    return key.startswith(VERBATIM_PREFIXES)


def derive_name(expr: str) -> str:
    """Plain identifier for a placeholder body: kept if already one, else non-[A-Za-z0-9_] chars dropped."""
    if IDENT_RE.match(expr):
        return expr
    name = re.sub(r"[^A-Za-z0-9_]", "", expr)
    if not name:
        name = "expr"
    if name[0].isdigit():
        name = "_" + name
    return name


def placeholder_map(english: str) -> dict[str, str]:
    """English expression -> derived name, with _2/_3 suffixes for collisions between different expressions."""
    mapping: dict[str, str] = {}
    used: set[str] = set()
    for m in PLACEHOLDER_RE.finditer(english):
        expr = m.group(1)
        if expr in mapping:
            continue
        base = derive_name(expr)
        name, n = base, 1
        while name in used:
            n += 1
            name = f"{base}_{n}"
        mapping[expr] = name
        used.add(name)
    return mapping


def normalise(text: str, mapping: dict[str, str]) -> str:
    return PLACEHOLDER_RE.sub(lambda m: "{" + mapping.get(m.group(1), derive_name(m.group(1))) + "}", text)


def placeholder_set(text: str) -> set[str]:
    return {m.group(1) for m in PLACEHOLDER_RE.finditer(text)}


# ------------------------------------------------------------------------------------------------ markup

_CODE_RE = re.compile(r"`([^`\n]+)`")
_LINK_RE = re.compile(r"\[([^\[\]\n]+)\]\(([^()\s]+)\)")
_BOLD_RE = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*")
_EM_RE = re.compile(r"(?<![*\w])\*(?=[^\s*])(.+?)(?<=[^\s*])\*(?![*\w])")


def markdown_to_html(text: str) -> str:
    """Inline markup -> HTML. Escapes literal < > & first; `code` contents are protected from other markup."""
    text = html.escape(text, quote=False)
    stash: list[str] = []

    def keep(s: str) -> str:
        stash.append(s)
        return f"\x00{len(stash) - 1}\x00"

    text = _CODE_RE.sub(lambda m: keep(f"<code>{m.group(1)}</code>"), text)
    text = _LINK_RE.sub(lambda m: keep(f'<a href="{m.group(2).replace(chr(34), "&quot;")}">')
                        + m.group(1) + keep("</a>"), text)
    text = _BOLD_RE.sub(r"<strong>\1</strong>", text)
    text = _EM_RE.sub(r"<em>\1</em>", text)
    return re.sub(r"\x00(\d+)\x00", lambda m: stash[int(m.group(1))], text)


def string_value(key: str, text: str, mapping: dict[str, str]) -> str:
    if is_verbatim(key):
        return text
    return markdown_to_html(normalise(text, mapping))


# --------------------------------------------------------------------------------------------- console

def _re_escape_js(s: str) -> str:
    return "".join("\\" + c if c in _RE_SPECIAL else c for c in s)


def console_regex(english: str, mapping: dict[str, str]) -> str:
    parts = ["^"]
    seen: set[str] = set()
    pos = 0
    for m in PLACEHOLDER_RE.finditer(english):
        parts.append(_re_escape_js(english[pos:m.start()]))
        name = mapping[m.group(1)]
        if name in seen:
            parts.append(f"\\k<{name}>")
        elif m.end() == len(english):
            # the template ends with this placeholder: greedy, or the catch-all below would take its text
            parts.append(f"(?<{name}>.*)")
        else:
            parts.append(f"(?<{name}>.*?)")
        seen.add(name)
        pos = m.end()
    parts.append(_re_escape_js(english[pos:]))
    parts.append(f"(?<{REST}>.*)$")
    return "".join(parts)


# ----------------------------------------------------------------------------------------------- build

@dataclass
class BuildResult:
    outputs: dict[str, dict]  # lang -> json document
    warnings: list[str]


def _plural_base(key: str) -> str | None:
    for suf in (".one", ".other"):
        if key.endswith(suf):
            return key[: -len(suf)]
    return None


def build(copy_dir: Path = COPY_DIR) -> BuildResult:
    copy_dir = Path(copy_dir)
    en_path = copy_dir / "COPY.md"
    if not en_path.is_file():
        raise BuildError(f"{en_path} not found")
    en = parse_copy(en_path.read_text(encoding="utf-8"), en_path)
    warnings = list(en.issues)
    errors: list[str] = []
    for e in en.entries.values():
        if not e.text.strip():
            errors.append(f"COPY.md:{e.line}: {e.key!r} has no indented text block")
    if errors:
        raise BuildError("\n".join(errors))

    maps = {k: ({} if is_verbatim(k) else placeholder_map(e.text)) for k, e in en.entries.items()}
    reserved = [f"COPY.md:{e.line}: {k!r} uses the reserved console placeholder {{{REST}}}"
                for k, e in en.entries.items() if k.startswith(CONSOLE_PREFIX) and REST in maps[k].values()]
    if reserved:
        raise BuildError("\n".join(reserved))
    en_sets = {k: (placeholder_set(e.text) if is_verbatim(k) else set(maps[k].values()))
               for k, e in en.entries.items()}

    def doc(lang: str, texts: dict[str, str]) -> dict:
        strings, console = {}, {}
        for key in sorted(en.entries):
            text = texts.get(key, en.entries[key].text)
            if key.startswith(CONSOLE_PREFIX):
                console[key] = {"re": console_regex(en.entries[key].text, maps[key]),
                                "text": normalise(text, maps[key]) + "{" + REST + "}"}
            else:
                strings[key] = string_value(key, text, maps[key])
        return {"lang": lang, "strings": strings, "console": console}

    outputs = {"en": doc("en", {})}

    for path in sorted(copy_dir.glob("COPY.*.md")):
        m = LANG_FILE_RE.match(path.name)
        if not m:
            warnings.append(f"{path.name}: not a COPY.<lang>.md name, skipped")
            continue
        lang = m.group(1)
        if lang == "en":
            raise BuildError(f"{path.name}: English lives in COPY.md, not COPY.en.md")
        tr = parse_copy(path.read_text(encoding="utf-8"), path)
        warnings.extend(tr.issues)
        errs: list[str] = []
        texts: dict[str, str] = {}
        for key, e in tr.entries.items():
            where = f"{path.name}:{e.line}: {key!r}"
            if key not in en.entries:
                errs.append(f"{where} is not a key in COPY.md")
                continue
            if key.startswith(CONSOLE_PREFIX):  # {rest} is appended by the build; a translator's copy is dropped
                e.text = e.text.replace("{" + REST + "}", "")
            if not e.text.strip():
                errs.append(f"{where} has empty text")
                continue
            if is_verbatim(key):
                got = placeholder_set(e.text)
            else:
                got = {maps[key].get(x, derive_name(x)) for x in placeholder_set(e.text)}
            want = en_sets[key]
            base = _plural_base(key)
            if key.endswith(".one") and base + ".other" in en.entries:
                allowed = want | en_sets[base + ".other"]
                missing, extra = want - got, got - allowed
            else:
                missing, extra = want - got, got - want
            if missing or extra:
                detail = []
                if missing:
                    detail.append("missing " + ", ".join("{%s}" % x for x in sorted(missing)))
                if extra:
                    detail.append("unknown " + ", ".join("{%s}" % x for x in sorted(extra)))
                errs.append(f"{where} placeholders differ from English: {'; '.join(detail)}")
                continue
            texts[key] = e.text
        if errs:
            raise BuildError("\n".join(errs))
        # plural: a translation that gives only K.other reuses it for K.one
        for key in en.entries:
            base = _plural_base(key)
            if key.endswith(".one") and key not in texts and (base + ".other") in texts:
                texts[key] = texts[base + ".other"]
        missing_keys = [k for k in sorted(en.entries) if k not in texts]
        if missing_keys:
            head = ", ".join(missing_keys[:20]) + (" ..." if len(missing_keys) > 20 else "")
            warnings.append(f"{path.name}: {len(missing_keys)} key(s) missing, English used: {head}")
        outputs[lang] = doc(lang, texts)
    return BuildResult(outputs, warnings)


def render(document: dict) -> str:
    return json.dumps(document, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--check", action="store_true", help="exit 1 if any json on disk differs; write nothing")
    ap.add_argument("--copy-dir", type=Path, default=COPY_DIR)
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):  # a Windows console is cp1252; never crash printing a key's text
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    try:
        result = build(args.copy_dir)
    except BuildError as exc:
        print(f"build_i18n: ERROR\n{exc}", file=sys.stderr)
        return 2
    for w in result.warnings:
        print(f"build_i18n: warning: {w}", file=sys.stderr)
    stale = []
    for lang, document in sorted(result.outputs.items()):
        target = args.out_dir / f"{lang}.json"
        body = render(document)
        current = target.read_bytes().decode("utf-8") if target.is_file() else None
        if args.check:
            if current != body:
                stale.append(str(target))
            continue
        if current != body:
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(body)
        print(f"build_i18n: {target} ({len(document['strings'])} strings, {len(document['console'])} console)")
    if stale:
        print("build_i18n: out of date (run python web/tools/build_i18n.py): " + ", ".join(stale), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

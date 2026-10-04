"""Codegen: validated BLANK the spire card JSON -> Slay the Spire 2 C# DataCard classes + localization.

Part of the STS2 mod pipeline (offline-authoring path). Because BaseLib binds each card's identity to a
compiled .NET type (one class per card, registered at load), LLM/authored JSON cannot be loaded as live
data — it must become compiled C#. This step turns each card JSON into a thin `DataCard` subclass holding
a `CardSpec` literal (the shared EffectRunner interprets it at play time) plus its localization entry.

Pure stdlib. Run:
    python generation/btsgen/cardgen.py \
        --in mod/content/cards \
        --out-cs "mod/BlankTheSpireCode/Cards/Generated" \
        --out-loc "mod/BlankTheSpire/localization/eng/cards.json"
"""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path

MOD_PREFIX = "BLANKTHESPIRE"
NAMESPACE_ROOT = "BlankTheSpire.BlankTheSpireCode"
NAMESPACE = f"{NAMESPACE_ROOT}.Cards.Generated"
ENGINE_NS = f"{NAMESPACE_ROOT}.Engine"

# JSON vocabulary value -> STS2 enum literal. Keep in lockstep with EffectRunner / the schema enum.
TYPE_MAP = {"attack": "CardType.Attack", "skill": "CardType.Skill", "power": "CardType.Power"}
RARITY_MAP = {
    "basic": "CardRarity.Basic", "common": "CardRarity.Common",
    "uncommon": "CardRarity.Uncommon", "rare": "CardRarity.Rare",
}
TARGET_MAP = {
    "enemy": "TargetType.AnyEnemy", "self": "TargetType.Self",
    "all_enemies": "TargetType.AllEnemies", "random_enemy": "TargetType.RandomEnemy",
    "none": "TargetType.Self",
}

# Status display names (the prototype JSON has no card text; we synthesize it from effects + target).
STATUS_NAME = {
    "vulnerable": "Vulnerable", "weak": "Weak", "frail": "Frail", "poison": "Poison",
    "strength": "Strength", "dexterity": "Dexterity", "thorns": "Thorns", "regen": "Regen",
    "metallicize": "Metallicize", "artifact": "Artifact", "buffer": "Buffer",
    "intangible": "Intangible", "ritual": "Ritual", "blur": "Blur",
    "temp_strength": "Strength", "temp_dexterity": "Dexterity", "barricade": "Barricade",
    "focus": "Focus",
    "temp_thorns": "Thorns", "temp_focus": "Focus",  # Phase AN (v44): worded like the temp stats (ForgedCards.StatusName)
    "vigor": "Vigor", "double_damage": "Double Damage",  # Phase BF (v60, gap #54): the base-game next-attack amplifiers
    # Phase BL (v64, gaps #66/#67): enemy Strength loss + Doom (mirrors ForgedCards.StatusDisplay / StatusName).
    "temp_strength_down": "Strength Down", "strength_down": "Strength Down", "doom": "Doom",
    # Phase BM (v65, gaps #68/#69): the self statuses (their card text is _BM_SENTENCES; mirrors ForgedCards.StatusDisplay).
    "no_draw": "No Draw", "no_energy_gain": "No Energy Gain", "no_block_gain": "No Block", "dex_decay": "Wraith Form",
    "focus_decay": "Biased Cognition", "lose_strength": "Strength", "lose_dexterity": "Dexterity", "lose_focus": "Focus",
    "echo_form": "Echo Form",
}
# Phase BM (v65, gaps #68/#69): the self-drawbacks + Echo Form read as their own sentences (the "Gain X." idiom would
# misread a drawback). The {vars} are the names DataCard declares. Byte-lockstep with ForgedCards.BmStatusSentence.
_BM_SENTENCES = {
    "no_draw": "You cannot draw additional cards this turn.",
    "no_energy_gain": "You cannot gain energy this turn.",
    "no_block_gain": "You cannot gain Block from cards for {NoBlockTurns} turns.",
    "dex_decay": "At the start of your turn, lose {DexDecay} Dexterity.",
    "focus_decay": "At the start of your turn, lose {FocusDecay} Focus.",
    "lose_strength": "Lose {SelfStrengthLoss} Strength.",
    "lose_dexterity": "Lose {SelfDexterityLoss} Dexterity.",
    "lose_focus": "Lose {SelfFocusLoss} Focus.",
    "echo_form": "The first card you play each turn is played twice.",
}
# Self-buffs are worded "Gain" and always land on the player; debuffs are "Apply"-ed to the target.
# Keep in lockstep with EffectRunner.SelfBuffStatuses (the C# single source of truth for buff-vs-debuff side).
_BUFFS = {
    "strength", "dexterity", "thorns", "regen", "metallicize", "artifact", "buffer",
    "intangible", "ritual", "blur", "temp_strength", "temp_dexterity", "barricade", "focus",
    "temp_thorns", "temp_focus",  # Phase AN (v44)
    "vigor", "double_damage",  # Phase BF (v60)
}


def _orb_display(orb) -> str:
    """Display name for an orb in card text. Base orbs are title-cased; 'random' stays lowercase; a custom
    orb name (Phase I, declared in the class orb_pool) is title-cased from its lowercase id."""
    base = {"lightning": "Lightning", "frost": "Frost", "dark": "Dark", "random": "random"}
    if orb in base:
        return base[orb]
    return str(orb or "orb").replace("_", " ").title()


def _pile_phrase(pile) -> str:
    # The human phrase for an add_card / add_status_card destination pile, or a retrieve_card source pile (Phase Q;
    # Phase AP adds the exhaust pile). Mirrors ForgedCards.PilePhrase.
    return {"discard": "discard pile", "draw": "draw pile", "exhaust": "exhaust pile"}.get(pile, "hand")


# Phase AP (v46): the display names of the base-game Status cards add_status_card may generate. Mirrors
# ForgedCards.StatusCardName (an unknown kind reads as Wound, the engine default).
STATUS_CARD_NAME = {"dazed": "Dazed", "wound": "Wound", "burn": "Burn"}


def _retrieve_sentence(e: dict) -> str:
    # Phase AP (v46): the retrieve_card sentence — "Return a random card from your discard pile to your hand." /
    # "Return 2 cards of your choice from your exhaust pile to your hand." Literal numbers (no var, like add_card); an
    # absent/unknown pile reads as the discard pile, an absent mode as random. Mirrors ForgedCards.RetrieveSentence.
    n = max(1, int(e.get("amount", 1) or 1))
    pile = "exhaust pile" if str(e.get("pile", "")).lower() == "exhaust" else "discard pile"
    if str(e.get("cards", "")).lower() == "choose":
        what = f"{n} cards of your choice" if n > 1 else "a card of your choice"
    else:
        what = f"{n} random cards" if n > 1 else "a random card"
    return f"Return {what} from your {pile} to your hand."


def _status_card_sentence(e: dict) -> str:
    # Phase AP (v46): the add_status_card sentence — "Add a Wound to your discard pile." / "Add 2 Wounds to your hand." /
    # "Add 2 Dazed to your draw pile." (Dazed is its own plural). Literal numbers (no var). Mirrors
    # ForgedCards.StatusCardSentence.
    n = max(1, int(e.get("amount", 1) or 1))
    name = STATUS_CARD_NAME.get(str(e.get("card", "")).lower(), "Wound")
    what = f"{n} {name if name == 'Dazed' else name + 's'}" if n > 1 else f"a {name}"
    return f"Add {what} to your {_pile_phrase(e.get('pile'))}."


def _hand_kind_words(kind) -> tuple[str, str]:
    # Phase BC (v57): the singular / plural words for a hand filter. Mirrors ForgedCards.HandKindWords.
    return {
        "attack": ("an Attack", "Attacks"),
        "skill": ("a Skill", "Skills"),
        "power": ("a Power", "Powers"),
        "non_attack": ("a non-Attack card", "non-Attack cards"),
    }.get(str(kind or "").lower(), ("a card", "cards"))


def _exhaust_card_sentence(e: dict) -> str:
    # Phase BC (v57, gap #52): "Exhaust a card in your hand." / "Exhaust 2 random cards in your hand." / "Exhaust up to 3
    # cards in your hand." / "Exhaust all non-Attack cards in your hand." Literal numbers (no var); an absent/unknown mode
    # reads as choose. Mirrors ForgedCards.ExhaustCardSentence.
    one, many = _hand_kind_words(e.get("card_type"))
    n = max(1, int(e.get("amount", 1) or 1))
    mode = str(e.get("cards", "")).lower()
    if mode == "all":
        what = f"all {many}"
    elif mode == "random":
        what = f"{n} random {many}" if n > 1 else f"a random {one.split(' ', 1)[1]}"
    elif mode == "up_to":
        what = f"up to {n} {many}"
    else:
        what = f"{n} {many}" if n > 1 else one
    return f"Exhaust {what} in your hand."


def _draw_until_sentence(e: dict) -> str:
    # Phase BC (v57, gap #53): "Draw cards until you draw a non-Attack card." Mirrors ForgedCards.DrawUntilSentence.
    return f"Draw cards until you draw {_hand_kind_words(e.get('card_type'))[0]}."


def _add_card_name(card_id) -> str:
    # Display title for an add_card's referenced card: the snake_case id, title-cased (no sibling-name context
    # in describe(), same choice as _orb_display). Mirrors ForgedCards.AddCardName.
    cid = str(card_id or "").strip()
    return cid.replace("_", " ").title() if cid else "a card"


def _add_card_sentence(e: dict, capitalize: bool) -> str:
    # Phase Q (gap #16): the add_card sentence (card-level, capitalize=True → "Add … ." with a period) or the
    # trigger-payload fragment (capitalize=False → "add …", no period). Mirrors ForgedCards.AddCardSentence.
    verb = "Add" if capitalize else "add"
    name = _add_card_name(e.get("card_id"))
    pile = _pile_phrase(e.get("pile"))
    n = max(1, e.get("amount", 1) or 1)
    body = (f"{verb} {n} copies of {name} to your {pile}" if n > 1
            else f"{verb} a copy of {name} to your {pile}")
    return body + "." if capitalize else body


def _balance_sentence(e: dict, capitalize: bool) -> str:
    # Phase S (gap #1): the balance_step sentence (card-level, capitalize=True → "Shift N toward the Dark." with a
    # period) or the trigger-payload fragment (capitalize=False → "shift …", no period). An unknown/absent pole
    # reads as Dark (matching the engine default). Mirrors ForgedCards.BalanceSentence.
    verb = "Shift" if capitalize else "shift"
    pole = "Light" if str(e.get("pole", "")).lower() == "light" else "Dark"
    n = max(1, int(e.get("amount", 0) or 0))
    body = f"{verb} {n} toward the {pole}"
    return body + "." if capitalize else body


def _upgrade_sentence(e: dict, capitalize: bool) -> str:
    # Phase V (gap #18): the upgrade_card sentence (card-level, capitalize=True → "Upgrade … ." with a period) or
    # the trigger-payload fragment (capitalize=False → "upgrade …", no period). COMBAT-SCOPED (the trailing "for
    # the rest of this combat" says so). An absent/unknown scope reads as `random`. Mirrors ForgedCards.UpgradeSentence.
    verb = "Upgrade" if capitalize else "upgrade"
    scope = str(e.get("cards", "")).lower()
    what = {"all": "ALL cards", "choose": "a card of your choice"}.get(scope, "a random card")
    body = f"{verb} {what} in your hand for the rest of this combat"
    return body + "." if capitalize else body


def pascal(card_id: str) -> str:
    return "".join(w.capitalize() for w in re.split(r"[_\-]+", card_id))


def condition_literal(w: dict) -> str:
    # positional Condition(Kind, Value, Status, Negate) — keep in lockstep with CardSpec.cs / ForgedCards parse.
    status = w.get("status")
    status_lit = f'"{status}"' if status else "null"
    negate = "true" if w.get("negate") else "false"
    return f'new Condition("{w.get("kind", "")}", {int(w.get("value", 0) or 0)}, {status_lit}, {negate})'


def effect_literal(e: dict) -> str:
    op = e["op"]
    if op == "apply_status":
        lit = f'new EffectSpec("apply_status", {e["amount"]}, "{e["status"]}")'
        if str(e.get("scale", "")).strip():  # Phase BL (v64): Blight Strike — doom scaled by damage_dealt_unblocked
            lit = f'new EffectSpec("apply_status", {e["amount"]}, "{e["status"]}", 1, "{str(e["scale"]).strip().lower()}")'
    elif op == "channel_orb":
        # positional shape (Op, Amount, Status, Hits, Scale, Orb) — Scale is null here (F5: was ScaleX bool).
        lit = f'new EffectSpec("channel_orb", {e.get("amount", 0)}, null, 1, null, "{e["orb"]}")'
    elif op == "add_trigger":
        # Phase H3: named Trigger/Triggered args; the nested payload reuses effect_literal. The optional
        # fire-time When is appended below by the shared When-append (named arg, order-independent in C#).
        nested = "[" + ", ".join(effect_literal(x) for x in e.get("effects", [])) + "]"
        # Amount carries the "ripen" countdown (turns to wait); 0/unused for turn_start/turn_end.
        lit = f'new EffectSpec("add_trigger", {e.get("amount", 0)}, Trigger: "{e.get("trigger", "")}", Triggered: {nested})'
        # Phase BI (v61, gap #62): the trigger filters as named args, lockstep with ForgedCards.ParseEffects.
        if e.get("card_type"):
            lit = f'{lit[:-1]}, CardKind: "{str(e["card_type"]).lower()}")'
        if e.get("scope"):
            lit = f'{lit[:-1]}, Scope: "{str(e["scope"]).lower()}")'
        if e.get("every_n"):
            lit = f"{lit[:-1]}, EveryN: {int(e['every_n'])})"
    elif op == "apply_status_custom":
        # Phase J: named StatusName arg (the class status_pool entry, resolved against the class at runtime).
        name = str(e.get("status_name", "")).replace("\\", "\\\\").replace('"', '\\"')
        lit = f'new EffectSpec("apply_status_custom", {e.get("amount", 0)}, StatusName: "{name}")'
    elif op == "summon":
        # Phase K: named SummonName arg (the class summon_pool entry, resolved against the class at runtime).
        name = str(e.get("summon_name", "")).replace("\\", "\\\\").replace('"', '\\"')
        lit = f'new EffectSpec("summon", {e.get("amount", 0)}, SummonName: "{name}")'
    elif op == "summon_attack":
        # Phase K (v15 true-Osty): damage dealt THROUGH the summon (positional Op, Amount, Status=null, Hits).
        lit = f'new EffectSpec("summon_attack", {e.get("amount", 0)}, null, {e.get("hits", 1)})'
    elif op == "buff_summon":
        # Phase K (v15 true-Osty): a self-buff on the summon (positional Op, Amount, Status; default Strength).
        st = str(e.get("status") or "strength")
        lit = f'new EffectSpec("buff_summon", {e.get("amount", 0)}, "{st}")'
    elif op == "add_card":
        # Phase Q (gap #16): named CardId/Pile args (order-independent in C#). Amount = copies (default 1).
        cid = str(e.get("card_id", "")).replace("\\", "\\\\").replace('"', '\\"')
        pile = str(e.get("pile", "hand")).replace("\\", "\\\\").replace('"', '\\"')
        lit = f'new EffectSpec("add_card", {e.get("amount", 1)}, CardId: "{cid}", Pile: "{pile}")'
    elif op == "transform_card":
        # Phase AH (gaps #35/#38): named CardId arg (the same-class card this card becomes). No amount, no pile.
        cid = str(e.get("card_id", "")).replace("\\", "\\\\").replace('"', '\\"')
        lit = f'new EffectSpec("transform_card", CardId: "{cid}")'
    elif op == "graft_card":
        # Phase AI (gap #7): named CardId arg (the same-class card the PICKED hand card becomes). No amount, no pile.
        cid = str(e.get("card_id", "")).replace("\\", "\\\\").replace('"', '\\"')
        lit = f'new EffectSpec("graft_card", CardId: "{cid}")'
    elif op == "balance_step":
        # Phase S (gap #1): named Pole arg (order-independent in C#). Amount = step size (default 1).
        pole = str(e.get("pole", "dark")).replace("\\", "\\\\").replace('"', '\\"')
        lit = f'new EffectSpec("balance_step", {e.get("amount", 1)}, Pole: "{pole}")'
    elif op == "upgrade_card":
        # Phase V (gap #18): named Cards arg (order-independent in C#). No amount. Default scope `random`.
        cards = str(e.get("cards", "random")).replace("\\", "\\\\").replace('"', '\\"')
        lit = f'new EffectSpec("upgrade_card", Cards: "{cards}")'
    elif op == "cost_shift":
        # Phase AO (v45): named CardKind / Scope (+ Count) args, lockstep with ForgedCards.ParseEffects. Amount = the discount.
        ck = str(e.get("card_type", "all")).replace("\\", "\\\\").replace('"', '\\"')
        sc = str(e.get("scope", "this_turn")).replace("\\", "\\\\").replace('"', '\\"')
        lit = f'new EffectSpec("cost_shift", {e.get("amount", 1)}, CardKind: "{ck}", Scope: "{sc}")'
        if e.get("count"):
            lit = f"{lit[:-1]}, Count: {int(e['count'])})"
    elif op == "discard" and str(e.get("cards", "")).lower() == "choose":
        # Phase AP (v46): the chosen form carries the named Cards arg; the random form stays the plain literal below.
        lit = f'new EffectSpec("discard", {e.get("amount", 0)}, Cards: "choose")'
    elif op == "exhaust_card":
        # Phase BC (v57, gap #52): named Cards (+ CardKind) args. Amount = cards exhausted (0 for the `all` mode).
        cards = str(e.get("cards", "choose")).replace("\\", "\\\\").replace('"', '\\"')
        lit = f'new EffectSpec("exhaust_card", {e.get("amount", 0) if cards != "all" else 0}, Cards: "{cards}")'
        if e.get("card_type"):
            ck = str(e["card_type"]).replace("\\", "\\\\").replace('"', '\\"')
            lit = f'{lit[:-1]}, CardKind: "{ck}")'
    elif op == "replay_next":
        # Phase BM (v65, gap #69): named CardKind / Count args (the cost_shift idiom). No amount.
        ck = str(e.get("card_type", "skill")).replace("\\", "\\\\").replace('"', '\\"')
        lit = f'new EffectSpec("replay_next", 0, CardKind: "{ck}", Count: {int(e.get("count", 1) or 1)})'
    elif op == "draw_until":
        # Phase BC (v57, gap #53): named CardKind arg (the type that stops the draw). No amount.
        ck = str(e.get("card_type", "non_attack")).replace("\\", "\\\\").replace('"', '\\"')
        lit = f'new EffectSpec("draw_until", CardKind: "{ck}")'
    elif op == "retrieve_card":
        # Phase AP (v46): named Pile / Cards args (order-independent in C#). Amount = cards returned (default 1).
        pile = str(e.get("pile", "discard")).replace("\\", "\\\\").replace('"', '\\"')
        cards = str(e.get("cards", "random")).replace("\\", "\\\\").replace('"', '\\"')
        lit = f'new EffectSpec("retrieve_card", {e.get("amount", 1)}, Pile: "{pile}", Cards: "{cards}")'
    elif op == "add_status_card":
        # Phase AP (v46): named StatusCard / Pile args. Amount = Status cards added (default 1).
        kind = str(e.get("card", "wound")).replace("\\", "\\\\").replace('"', '\\"')
        pile = str(e.get("pile", "discard")).replace("\\", "\\\\").replace('"', '\\"')
        lit = f'new EffectSpec("add_status_card", {e.get("amount", 1)}, Pile: "{pile}", StatusCard: "{kind}")'
    else:
        amount = e.get("amount", 0)
        hits = e.get("hits", 1)
        scale = str(e.get("scale", "")).lower()
        if scale:
            # F5: a scaled effect's amount is a live scalar (x/cards_in_hand/cards_retained/
            # unspent_energy_last_turn); positional (Op, Amount, Status, Hits, Scale). Amount is ignored at runtime.
            lit = f'new EffectSpec("{op}", {amount}, null, {hits}, "{scale}")'
            if e.get("status"):  # Phase BJ (v62): target_status_stacks carries its status positionally (Status slot).
                st = str(e["status"]).replace("\\", "\\\\").replace('"', '\\"')
                lit = f'new EffectSpec("{op}", {amount}, "{st}", {hits}, "{scale}")'
            if scale == "tag_cards_owned":  # Phase AE (gap #25): the counted tag as a named arg (order-independent in C#).
                tag = str(e.get("tag", "")).replace("\\", "\\\\").replace('"', '\\"')
                lit = f'{lit[:-1]}, Tag: "{tag}")'
        elif op == "damage" and e.get("grow", 0):
            # Phase U (gap #23, Rampage): named Grow arg (order-independent in C#). grow ⊥ scale (validator-enforced).
            lit = f'new EffectSpec("damage", {amount}, Grow: {e["grow"]})'
        elif op in ("damage", "block") and e.get("grow_held", 0):
            # Phase BD (v58, gap #57, Windmill Strike): named GrowHeld arg. grow_held ⊥ scale/grow (validator-enforced).
            lit = f'new EffectSpec("{op}", {amount}, GrowHeld: {int(e["grow_held"])})'
        elif op == "damage" and hits > 1:
            lit = f'new EffectSpec("damage", {amount}, null, {hits})'
        elif op == "damage" and e.get("hits_scale"):
            # Phase BK (v63, gap #65): named HitsScale arg (the hit-count read). ⊥ hits/scale/grow (validator-enforced).
            hs = str(e["hits_scale"]).strip().lower().replace("\\", "\\\\").replace('"', '\\"')
            lit = f'new EffectSpec("damage", {amount}, HitsScale: "{hs}")'
        else:
            lit = f'new EffectSpec("{op}", {amount})'
    # Phase H: append the optional per-effect `when` guard as the named `When:` arg (after the positionals).
    when = e.get("when")
    if isinstance(when, dict):
        lit = f"{lit[:-1]}, When: {condition_literal(when)})"
    # H4: once_per_turn (on an add_trigger op) + target (on a targeted trigger payload effect) as named args
    # (order-independent in C#). Kept in lockstep with ForgedCards.ParseEffects.
    if e.get("once_per_turn"):
        lit = f"{lit[:-1]}, OncePerTurn: true)"
    if e.get("once_per_combat"):  # Phase AK (v41): named arg, lockstep with ForgedCards.ParseEffects
        lit = f"{lit[:-1]}, OncePerCombat: true)"
    if e.get("unblockable") is True:  # Phase AN (v44): the damage flag as a named arg, lockstep with ForgedCards.ParseEffects
        lit = f"{lit[:-1]}, Unblockable: true)"
    tgt = e.get("target")
    if tgt:
        lit = f'{lit[:-1]}, Target: "{tgt}")'
    return lit


def effects_array(effects: list[dict]) -> str:
    return "[" + ", ".join(effect_literal(e) for e in effects) + "]"


def _scale_phrase(scale: str) -> str:
    # The human phrase for a non-X scalar (F5). Mirrors ForgedCards.ScalePhrase.
    return {
        "cards_in_hand": "the cards in your hand",
        "cards_retained": "the cards you retained",
        "unspent_energy_last_turn": "your unspent energy last turn",
        "target_debuff_count": "the debuffs on the target",    # Phase P (gap #22)
        "damage_dealt_unblocked": "the unblocked damage dealt",  # Phase P (gap #21, lifesteal heal)
        # Phase AM (v43): five more live player reads (replace-semantics). Mirrors ForgedCards.ScalePhrase.
        "block": "your Block",
        "hp_lost_this_turn": "the HP you have lost this turn",
        "draw_pile_count": "the cards in your draw pile",
        "energy": "your energy",
        "plays_this_combat": "the cards you have played this combat",
        # Phase BJ (v62, gap #63): the combat-history / pile reads. Mirrors ForgedCards.ScalePhrase.
        "exhaust_pile_size": "the cards in your exhaust pile",
        "discard_pile_size": "the cards in your discard pile",
        "discards_this_turn": "the cards you have discarded this turn",
        "cards_drawn_this_turn": "the cards you have drawn this turn",
        "cards_drawn_this_combat": "the cards you have drawn this combat",
        "energy_spent_this_turn": "the energy you have spent this turn",
        "hp_loss_events_this_combat": "the times you have lost HP this combat",
        "cards_generated_this_combat": "the cards you have created this combat",
        "total_enemy_poison": "the total Poison on ALL enemies",
    }.get(scale, "X")


# Phase BK (v63, gap #65): the singular noun a `hits_scale` damage counts — "Deal {Damage} damage for each <noun>."
# Mirrors ForgedCards.HitsPhrase + render.js HITS_NOUN (byte-match; `x` reads "X times" instead).
_HITS_PHRASE = {
    "attacks_played_this_turn": "Attack you played this turn",
    "cards_in_hand": "other card in your hand",
    "skills_in_hand": "Skill in your hand",
    "plays_this_combat": "card you have played this combat",
    "exhaust_pile_size": "card in your exhaust pile",
    "hp_loss_events_this_combat": "time you have lost HP this combat",
    "energy_spent_this_turn": "energy you have spent this turn",
    "orb_count": "orb you have channeled",
}


def _hits_phrase(src: str) -> str:
    return _HITS_PHRASE.get(src, "X")


def _effect_scale_phrase(e: dict) -> str:
    # Phase BJ (v62): target_status_stacks names its status ("the enemy's Vulnerable"). Mirrors ForgedCards.ScalePhrase(EffectSpec).
    scale = str(e.get("scale", "")).lower()
    if scale == "target_status_stacks":
        st = str(e.get("status", ""))
        return f"the enemy's {STATUS_NAME.get(st, st)}"
    return _scale_phrase(scale)


def cond_phrase(w: dict) -> str:
    # The bare predicate phrase for card text; the caller prefixes "if "/"unless ". Mirrors Conditions.Phrase.
    kind = w.get("kind", "")
    if kind == "orbs_match":
        return "your orbs match"
    if kind == "orb_count_ge":
        return f"you have {int(w.get('value', 0) or 0)}+ orbs"
    if kind == "target_has_status":
        return f"the enemy has {w.get('status')}"
    if kind == "no_block":
        return "you have no Block"
    if kind == "hp_below_half":
        return "your HP is below half"
    if kind == "has_block":  # L-4 (now also a card condition)
        v = int(w.get("value", 0) or 0)
        return f"you have {v}+ Block" if v > 1 else "you have Block"
    if kind == "enemy_count_ge":  # L-4 (now also a card condition)
        return f"there are {int(w.get('value', 0) or 0)}+ enemies"
    if kind == "turn_at_least":  # L-4 (now also a card condition)
        return f"it is turn {int(w.get('value', 0) or 0)}+"
    if kind == "turn_at_most":  # Phase BB (v56, gap #59): the opener's window. Mirrors Conditions.Phrase.
        return f"it is turn {int(w.get('value', 0) or 0)} or earlier"
    if kind == "hand_size_ge":  # F5
        return f"you hold {int(w.get('value', 0) or 0)}+ cards"
    if kind == "retained_last_turn":  # F5
        return "you held this card"
    if kind == "forged_ge":  # Phase M (gap #36): the Forge-gated payoff
        return f"your Forge is {int(w.get('value', 0) or 0)}+"
    if kind == "draw_pile_empty":  # Phase P (gap #24): Grand-Finale gate
        return "your draw pile is empty"
    if kind == "dark_ge":  # Phase S (gap #1): the Balance gauge reads
        return f"your Dark is {int(w.get('value', 0) or 0)}+"
    if kind == "light_ge":
        return f"your Light is {int(w.get('value', 0) or 0)}+"
    if kind == "centered":
        return f"you are centered (within {int(w.get('value', 0) or 0)})"
    if kind == "hp_lost_ge":  # Phase AD (gap #12): the HP-spent threshold (Ice Shatter)
        return f"you have lost {int(w.get('value', 0) or 0)} or more HP this turn"
    # Phase AM (v43): two chosen-target reads + two player reads. Mirrors Conditions.Phrase.
    if kind == "target_hp_below_half":
        return "the enemy is below half HP"
    if kind == "target_has_block":
        return "the enemy has Block"
    if kind == "energy_ge":
        return f"you have {int(w.get('value', 0) or 0)}+ energy"
    if kind == "cards_played_this_turn_ge":
        return f"you have played {int(w.get('value', 0) or 0)}+ cards this turn"
    # Phase BJ (v62, gap #64): two combat-history reads + one chosen-target read. Mirrors Conditions.Phrase.
    if kind == "exhausted_this_turn":
        return "you have Exhausted a card this turn"
    if kind == "played_cards_last_turn_ge":
        return f"you played {int(w.get('value', 0) or 0)}+ cards last turn"
    if kind == "target_intends_attack":
        return "the enemy intends to attack"
    return kind


def _trigger_scale_phrase(scale: str) -> str:
    # Phase AL (v42): the "equal to …" phrase for a REPLACE-semantics payload scalar. cards_retained keeps its F5
    # wording; the two new player reads reuse the card-level phrase. Mirrors ForgedCards.TriggerScalePhrase.
    return {
        "cards_retained": "cards retained",
        "cards_in_hand": "the cards in your hand",
        "unspent_energy_last_turn": "your unspent energy last turn",
        "exhaust_pile_size": "the cards in your exhaust pile",  # Phase BJ (v62)
        "total_enemy_poison": "the total Poison on ALL enemies",  # Phase BJ (v62)
    }.get(scale, "X")


def _trigger_fragment(e: dict) -> str:
    # A single payload-effect phrase inside a trigger sentence. Mirrors ForgedCards.TriggerFragment.
    op = e["op"]
    amt = e.get("amount", 0)
    scale = str(e.get("scale", "") or "").lower()
    # F5 / Phase AL (v42): a numeric payload may scale to a player read → phrase it instead of a fixed number;
    # `forged` is the ADDITIVE exception ("gain 2 Block, plus your Forge" — the card-level wording).
    sc = bool(scale) and scale != "forged"
    fg = scale == "forged"
    eq = _trigger_scale_phrase(scale)
    hits = e.get("hits", 1)
    hits = hits if isinstance(hits, int) and not isinstance(hits, bool) else 1
    tgt = e.get("target")
    # H4: targeted AoE suffix (single enemy → none); Phase AK (v41): the riposte target reads "to the attacker".
    # Phase BI (v61): "… to a random enemy" for the Juggernaut target.
    to = (" to ALL enemies" if tgt == "all_enemies" else " to the attacker" if tgt == "attacker"
          else " to a random enemy" if tgt == "random_enemy" else "")
    if op == "damage":  # H4 (gap #14): only meaningful with a target
        if not tgt:
            return ""
        if sc:
            return f"deal damage equal to {eq}{to}"
        if fg:
            return f"deal {amt} damage{to}, plus your Forge"
        if hits > 1:  # Phase AL (v42): a multi-hit payload
            return f"deal {amt} damage {hits} times{to}"
        return f"deal {amt} damage{to}"
    if op == "block":
        return f"gain Block equal to {eq}" if sc else f"gain {amt} Block, plus your Forge" if fg else f"gain {amt} Block"
    if op == "draw":
        return f"draw cards equal to {eq}" if sc else f"draw {amt} card(s)"
    if op == "gain_energy":
        return f"gain energy equal to {eq}" if sc else f"gain {amt} energy"
    if op == "heal":
        return f"heal HP equal to {eq}" if sc else f"heal {amt} HP"
    if op == "lose_hp":
        return f"lose HP equal to {eq}" if sc else f"lose {amt} HP"
    if op == "gain_orb_slot":
        return f"gain orb slots equal to {eq}" if sc else f"gain {amt} orb slot(s)"
    if op == "forge":  # Phase M (gap #36): fixed-amount income ("At the start of your turn, Forge 2.")
        return f"Forge {amt}"
    if op == "apply_status":
        nm = STATUS_NAME.get(e.get('status'), e.get('status'))
        if e.get("target"):  # H4 (gap #14): a targeted enemy debuff
            return f"apply {amt} {nm}{to}"
        return f"gain {nm} equal to {eq}" if sc else f"gain {amt} {nm}"
    # Phase AL (v42): the class engines as payload fragments. Mirrors ForgedCards.TriggerFragment (no class context —
    # a custom status is worded by its name: GAIN when untargeted (buff form) / APPLY when targeted (debuff form)).
    if op == "summon_attack":
        return f"deal {amt} damage {hits} times with your summon{to}" if hits > 1 else f"deal {amt} damage with your summon{to}"
    if op == "buff_summon":
        bst = e.get("status") or "strength"
        return f"your summon gains {max(1, amt)} {STATUS_NAME.get(bst, bst)}"
    if op == "apply_status_custom":
        nm = e.get("status_name", "")
        return f"apply {max(1, amt)} {nm}{to}" if tgt else f"gain {max(1, amt)} {nm}"
    if op == "channel_orb":
        name = _orb_display(e.get("orb"))
        oc = max(1, amt)
        return f"channel {oc} {name} orbs" if oc > 1 else f"channel a {name} orb"
    if op == "evoke":
        ec = max(1, amt)
        return f"evoke {ec} times" if ec > 1 else "evoke your next orb"
    if op == "add_card":  # Phase Q (gap #16): the compost-loop fragment. Mirrors ForgedCards.TriggerFragment.
        return _add_card_sentence(e, capitalize=False)
    if op == "discard":  # Phase R (gap #17): forced-churn payload. Mirrors ForgedCards.TriggerFragment.
        return f"discard {amt} random card(s)"
    if op == "balance_step":  # Phase S (gap #1): the Balance-engine fragment. Mirrors ForgedCards.TriggerFragment.
        return _balance_sentence(e, capitalize=False)
    if op == "summon_blade":  # Phase T: blade-retrieval fragment. Mirrors ForgedCards.TriggerFragment.
        return "put your blade into your hand from anywhere"
    if op == "upgrade_card":  # Phase V (gap #18): trigger-side upgrade (random only). Mirrors ForgedCards.TriggerFragment.
        return _upgrade_sentence(e, capitalize=False)
    if op == "heal_summon":  # Phase AC (gap #2): the medic-engine fragment. Mirrors ForgedCards.TriggerFragment.
        return f"heal your summon {amt} HP"
    if op == "shield_summon":  # Phase AC (gap #2). Mirrors ForgedCards.TriggerFragment.
        return f"your summon gains {amt} Block"
    return ""


# Phase BI (v61, gap #62): the add_trigger card filter as a noun phrase. Mirrors ForgedCards.TriggerKindWord.
_TRIGGER_KIND_WORDS = {"attack": "an Attack", "skill": "a Skill", "power": "a Power",
                       "non_attack": "a non-Attack card", "status": "a Status"}


def _ordinal(n: int) -> str:
    # Phase BI (v61): 2nd / 3rd / 4th … (every_n is 2..9). Mirrors ForgedCards.Ordinal.
    return f"{n}{'nd' if n == 2 else 'rd' if n == 3 else 'th'}"


def _trigger_head(t: dict, when: str) -> str:
    """Phase BI (v61, gap #62): reword the trigger head for the filters — "Whenever you play an Attack" /
    "Whenever you draw a Status"; "Every 3rd time you play an Attack" / "Every 5th card you play"; and the
    "This turn, whenever …" prefix. Mirrors the Phase BI block of ForgedCards.TriggerSentence."""
    trig = t.get("trigger")
    kind = str(t.get("card_type") or "").lower() or None
    if kind and trig in ("on_card_played", "on_card_drawn"):
        when = f"Whenever you {'draw' if trig == 'on_card_drawn' else 'play'} {_TRIGGER_KIND_WORDS.get(kind, 'a card')}"
    n = t.get("every_n")
    if isinstance(n, int) and not isinstance(n, bool) and n > 1:
        nth = _ordinal(n)
        if not kind and trig == "on_card_played":
            when = f"Every {nth} card you play"
        elif not kind and trig == "on_card_drawn":
            when = f"Every {nth} card you draw"
        elif when.startswith("Whenever "):
            when = f"Every {nth} time {when[len('Whenever '):]}"
    if str(t.get("scope") or "").lower() == "this_turn":
        when = f"This turn, {when[0].lower()}{when[1:]}"
    return when


def trigger_sentence(t: dict) -> str:
    # The trigger sentence WITHOUT its condition (the caller weaves When). Mirrors ForgedCards.TriggerSentence.
    trig = t.get("trigger")
    if trig == "turn_start":
        when = "At the start of your turn"
    elif trig == "ripen":  # gap #6: one-shot after N turns
        n = t.get("amount", 0)
        when = "After 1 turn" if n == 1 else f"After {n} turns"
    elif trig == "on_hp_lost":  # gap #9: bleed/sacrifice payoff
        when = "Whenever you lose HP"
    elif trig == "on_exhaust":  # H4 reactive kinds (mirror the relic hooks)
        when = "Whenever a card is Exhausted"
    elif trig == "on_card_played":
        when = "Whenever you play a card"
    elif trig == "on_card_drawn":
        when = "Whenever you draw a card"
    elif trig == "on_damage_dealt":
        when = "Whenever you deal damage"
    elif trig == "on_block_gained":
        when = "Whenever you gain Block"
    elif trig == "attacked":
        when = "Whenever you are attacked"
    elif trig == "on_discard":  # Phase R (gap #17): CARD-LATENT Reflex
        when = "Whenever this card is discarded"
    elif trig == "on_blade_played":  # Phase T: Parry analogue (fires on the token blade)
        when = "Whenever you play your blade"
    elif trig == "on_poison_damage":  # Phase BE (v59, gap #56): the Venom engine. Mirrors ForgedCards.TriggerSentence.
        when = "Whenever an enemy takes Poison damage"
    else:
        when = "At the end of your turn"
    when = _trigger_head(t, when)
    frags = [f for f in (_trigger_fragment(x) for x in t.get("effects", [])) if f]
    # H4 once_per_turn; Phase AK (v41) once_per_combat (never both — the validator rejects the pair)
    once = " (once per combat)" if t.get("once_per_combat") else " (once per turn)" if t.get("once_per_turn") else ""
    return f"{when}, {', '.join(frags) if frags else 'do nothing'}{once}."


def _cost_shift_sentence(e: dict) -> str:
    """Phase AO (v45): "Your Attacks cost 1 less this turn." / "Your next Skill costs 2 less this turn." / "Your next 2
    cards cost 1 less this combat." Byte-lockstep with ForgedCards.CostShiftSentence."""
    kind = str(e.get("card_type", "all")).lower()
    plural = {"attack": "Attacks", "skill": "Skills", "power": "Powers"}.get(kind, "cards")
    single = {"attack": "Attack", "skill": "Skill", "power": "Power"}.get(kind, "card")
    life = "this combat" if str(e.get("scope", "")).lower() == "combat" else "this turn"
    amt = max(1, int(e.get("amount", 1) or 1))
    count = int(e.get("count", 0) or 0)
    if count == 1:
        return f"Your next {single} costs {amt} less {life}."
    if count > 1:
        return f"Your next {count} {plural} cost {amt} less {life}."
    return f"Your {plural} cost {amt} less {life}."


def _replay_next_sentence(e: dict) -> str:
    """Phase BM (v65, gap #69): "This turn, your next Skill is played twice." / "This turn, your next 2 Attacks are played
    twice." / "Your next Power is played twice." (Signal Boost persists until used) / "This turn, your next card is played
    twice." Literal count (no var). Byte-lockstep with ForgedCards.ReplayNextSentence."""
    kind = str(e.get("card_type", "skill")).lower()
    single = {"attack": "Attack", "power": "Power", "all": "card"}.get(kind, "Skill")
    n = max(1, int(e.get("count", 1) or 1))
    what = f"your next {n} {single}s are" if n > 1 else f"your next {single} is"
    return f"{what[0].upper()}{what[1:]} played twice." if kind == "power" else f"This turn, {what} played twice."


def describe(effects: list[dict], target: str) -> str:
    # STS2 AoE cards spell out "to ALL enemies" in their text (the game does not auto-append it), so the
    # target informs the wording. Keep in lockstep with ForgedCards.Describe() (the C# slot-runtime mirror).
    aoe = target == "all_enemies"
    dmg_suffix = " to ALL enemies" if aoe else " to a random enemy" if target == "random_enemy" else ""
    parts: list[str] = []
    for e in effects:
        before = len(parts)
        op = e["op"]
        if op == "damage":
            scale = str(e.get("scale", "")).lower()
            # Phase AN (v44): an unblockable hit reads "…, ignoring Block." — the clause closes the damage sentence in
            # every shape. Byte-match ForgedCards.Describe.
            ub = ", ignoring Block" if e.get("unblockable") is True else ""
            if scale:
                # Phase M (gap #36): "forged" is ADDITIVE — the printed amount is real, plus your Forge.
                parts.append(f"Deal X damage{dmg_suffix}{ub}." if scale == "x"
                             else f"Deal {e.get('amount', 0)} damage{dmg_suffix}, plus your Forge{ub}." if scale == "forged"
                             else f"Deal {e.get('amount', 0)} damage{dmg_suffix}, plus 1 per '{e.get('tag', '')}' card you own{ub}." if scale == "tag_cards_owned"
                             else f"Deal damage equal to {_effect_scale_phrase(e)}{dmg_suffix}{ub}.")
            elif e.get("grow", 0):
                # Phase U (gap #23, Rampage): {CalculatedDamage} (base-game calc-var name) shows the CURRENT grown value (calc-var). Byte-match ForgedCards.Describe.
                parts.append(f"Deal {{CalculatedDamage}} damage{dmg_suffix}{ub}. Grows by {e['grow']} each time it is played this combat.")
            elif e.get("grow_held", 0):
                # Phase BD (v58, gap #57, Windmill Strike): the calc-var climbs per held turn. Byte-match ForgedCards.Describe.
                parts.append(f"Deal {{CalculatedDamage}} damage{dmg_suffix}{ub}. Grows by {int(e['grow_held'])} each turn it is retained.")
            elif e.get("hits_scale"):
                # Phase BK (v63, gap #65): Whirlwind / Finisher. Byte-match ForgedCards.Describe.
                hs = str(e["hits_scale"]).strip().lower()
                parts.append(f"Deal {{Damage}} damage X times{dmg_suffix}{ub}." if hs == "x"
                             else f"Deal {{Damage}} damage for each {_hits_phrase(hs)}{dmg_suffix}{ub}.")
            elif e.get("hits", 1) > 1:
                parts.append(f"Deal {{Damage}} damage {{Hits}} times{dmg_suffix}{ub}.")
            else:
                parts.append(f"Deal {{Damage}} damage{dmg_suffix}{ub}.")
        elif op == "block":
            scale = str(e.get("scale", "")).lower()
            parts.append(f"Gain {{CalculatedBlock}} Block. Grows by {int(e['grow_held'])} each turn it is retained." if e.get("grow_held", 0)  # Phase BD (v58)
                         else "Gain {Block} Block." if not scale
                         else "Gain X Block." if scale == "x"
                         else f"Gain {e.get('amount', 0)} Block, plus your Forge." if scale == "forged"
                         else f"Gain {e.get('amount', 0)} Block, plus 1 per '{e.get('tag', '')}' card you own." if scale == "tag_cards_owned"
                         else f"Gain Block equal to {_effect_scale_phrase(e)}.")
        elif op == "draw":
            scale = str(e.get("scale", "")).lower()
            parts.append("Draw {Cards} card(s)." if not scale
                         else "Draw X cards." if scale == "x"
                         else "Draw cards until you have {Cards} in hand." if scale == "to_hand_size"  # Phase BJ (v62): Expertise
                         else f"Draw cards equal to {_scale_phrase(scale)}.")
        elif op == "gain_energy":
            # Phase BJ (v62): Double Energy. Byte-match ForgedCards.Describe.
            parts.append("Double your energy." if str(e.get("scale", "")).lower() == "energy" else "Gain {Energy} energy.")
        elif op == "heal":
            # Phase P (gap #21): a scaled heal (damage_dealt_unblocked lifesteal) reads a live amount. Lockstep
            # with ForgedCards.Describe's heal case.
            scale = str(e.get("scale", "")).lower()
            parts.append(f"Heal HP equal to {_scale_phrase(scale)}." if scale else "Heal {Heal} HP.")
        elif op == "lose_hp":
            parts.append("Lose {Loss} HP.")
        elif op == "gain_max_hp":
            # Phase AN (v44): the Feed payoff via the {MaxHp} var (a real MaxHpVar). Lockstep with ForgedCards.Describe.
            parts.append("Gain {MaxHp} Max HP.")
        elif op == "discard":
            # Phase R (gap #17): random-discard count via the {Discard} var. Phase AP (v46): the chosen form reads
            # "... card(s) of your choice." Lockstep with ForgedCards.Describe.
            parts.append("Discard {Discard} card(s) of your choice." if str(e.get("cards", "")).lower() == "choose"
                         else "Discard {Discard} random card(s).")
        elif op == "retrieve_card":
            # Phase AP (v46): literal sentence (no var). Lockstep with ForgedCards.Describe / RetrieveSentence.
            parts.append(_retrieve_sentence(e))
        elif op == "add_status_card":
            # Phase AP (v46): literal sentence (no var). Lockstep with ForgedCards.Describe / StatusCardSentence.
            parts.append(_status_card_sentence(e))
        elif op == "exhaust_card":
            # Phase BC (v57, gap #52): literal sentence (no var). Lockstep with ForgedCards.Describe / ExhaustCardSentence.
            parts.append(_exhaust_card_sentence(e))
        elif op == "draw_until":
            # Phase BC (v57, gap #53): literal sentence (no var). Lockstep with ForgedCards.Describe / DrawUntilSentence.
            parts.append(_draw_until_sentence(e))
        elif op == "scry":
            # Phase AA (gap #17 R-2): top-of-draw look count via the {Scry} var. Lockstep with ForgedCards.Describe.
            parts.append("Scry {Scry}. (Look at that many cards from the top of your draw pile and discard any.)")
        elif op == "exhaust":
            parts.append("Exhaust.")
        elif op == "innate":
            parts.append("Innate.")
        elif op == "retain":
            parts.append("Retain.")
        elif op == "ethereal":
            parts.append("Ethereal.")
        elif op == "sly":
            # Phase BB (v56, gap #55): the base-game Sly keyword sentence. Lockstep with ForgedCards.Describe.
            parts.append("Sly.")
        elif op == "held_discount":
            # Phase BD (v58, gap #58): the Sands of Time sentence (literal). Lockstep with ForgedCards.Describe.
            parts.append(f"Costs {max(1, int(e.get('amount', 1) or 1))} less for each turn it is retained.")
        elif op == "purge":
            # Phase W (gap #19): the purge keyword sentence. Lockstep with ForgedCards.Describe.
            parts.append("Purge. (Removed from your deck for the rest of the run.)")
        elif op == "purge_card":
            # Phase Z (gap #19 choose): the choose-a-card purge sentence. Lockstep with ForgedCards.Describe.
            parts.append("Choose a card in your hand and Purge it. (Removed from your deck for the rest of the run.)")
        elif op == "sacrifice_summon":
            # Phase AV (v52): the consume-your-minion flag-op sentence (literal). Lockstep with ForgedCards.Describe.
            parts.append("Sacrifice your summon.")
        elif op == "spend_forge":
            # Phase AX (v53, gap #44): the Forge cash-out sentence (literal, no var). Lockstep with ForgedCards.Describe.
            parts.append(f"Spend {max(1, e.get('amount', 0) or 0)} Forge.")
        elif op == "spread_debuffs":
            # Phase AX (v53, gaps #45-#47): the contagion sentence (flag-op, no var). Lockstep with ForgedCards.Describe.
            parts.append("Copy the target's debuffs to all other enemies.")
        elif op == "strip_block":
            # Phase BL (v64, gap #66): Expose, half one (flag-op, no var). Lockstep with ForgedCards.Describe.
            parts.append("Remove all of the enemy's Block.")
        elif op == "strip_artifact":
            # Phase BL (v64, gap #66): Expose, half two (flag-op, no var). Lockstep with ForgedCards.Describe.
            parts.append("Remove the enemy's Artifact.")
        elif op == "replay_next":
            # Phase BM (v65, gap #69): Burst / One-Two Punch / Signal Boost / Duplication. Lockstep with ForgedCards.Describe.
            parts.append(_replay_next_sentence(e))
        elif op == "block_next_turn":
            # Phase BM (v65, gap #70): Prolong's two forms. Lockstep with ForgedCards.Describe.
            parts.append("Next turn, gain Block equal to your current Block." if str(e.get("scale", "")).lower() == "block"
                         else "Next turn, gain {NextTurnBlock} Block.")
        elif op == "retain_hand":
            # Phase BM (v65, gap #70): Equilibrium. Lockstep with ForgedCards.Describe.
            parts.append("Retain your hand this turn.")
        elif op == "corruption":
            # Phase AB (gap #20): two sentences (joined by the "\n" that separates parts). Lockstep with ForgedCards.Describe.
            parts.append("Your Skills cost 0.")
            parts.append("Your Skills Exhaust when played.")
        elif op == "blade_empower":
            # Phase AF (gap #41): the blade-multiplier sentence (literal). Lockstep with ForgedCards.Describe.
            parts.append(f"Your blade deals {max(2, e.get('amount', 0))}x damage this turn.")
        elif op == "cost_shift":
            # Phase AO (v45): the discount sentence (literal, no var). Lockstep with ForgedCards.CostShiftSentence.
            parts.append(_cost_shift_sentence(e))
        elif op == "transform_card":
            # Phase AH (gaps #35/#38): the target title is title-cased from the card_id (no sibling-name context in
            # describe(), same choice as add_card / ForgedCards.AddCardName). Lockstep with ForgedCards.Describe.
            parts.append(f"Transforms into {_add_card_name(e.get('card_id'))} for the rest of the run.")
        elif op == "graft_card":
            # Phase AI (gap #7): the choose-form transform — target title title-cased from the card_id (like
            # transform_card). Lockstep with ForgedCards.Describe.
            parts.append(f"Choose a card in your hand. It transforms into {_add_card_name(e.get('card_id'))} for the rest of the run.")
        elif op == "channel_orb":
            orb_name = _orb_display(e.get("orb"))
            oc = max(1, e.get("amount", 0))
            parts.append(f"Channel {oc} {orb_name} orbs." if oc > 1 else f"Channel a {orb_name} orb.")
        elif op == "evoke":
            ec = max(1, e.get("amount", 0))
            parts.append(f"Evoke {ec} times." if ec > 1 else "Evoke your next orb.")
        elif op == "gain_orb_slot":
            parts.append(f"Gain {e.get('amount', 0)} orb slot(s).")
        elif op == "forge":
            # Phase M (gap #36): the keyword sentence. Lockstep with ForgedCards.Describe.
            parts.append(f"Forge {e.get('amount', 0)}.")
        elif op == "balance_step":
            # Phase S (gap #1): the balance keyword sentence. Lockstep with ForgedCards.Describe.
            parts.append(_balance_sentence(e, capitalize=True))
        elif op == "add_trigger":
            # Sentence WITHOUT the condition; the generic when-weave below appends it (lockstep w/ ForgedCards).
            parts.append(trigger_sentence(e))
        elif op == "apply_status_custom":
            # Phase J: the card has no class status-pool context here (no emoji), so wording keys off the card's
            # TARGET — a self-target card GAINs the (buff) status, an enemy-target card APPLIES the (debuff).
            # Lockstep with ForgedCards.Describe's apply_status_custom case.
            nm = e.get("status_name", "")
            if target == "self":
                parts.append(f"Gain {e.get('amount', 0)} {nm}.")
            else:
                parts.append(f"Apply {e.get('amount', 0)} {nm}{dmg_suffix}.")  # AJ: ' to a random enemy' too
        elif op == "summon":
            # Phase K (v15 true-Osty): (re)summon the minion or grow its HP. Lockstep with ForgedCards.Describe.
            mn = _orb_display(e.get("summon_name"))
            samt = e.get("amount", 0)
            parts.append(f"Summon a {mn} with {samt} HP." if samt and samt >= 1 else f"Summon a {mn}.")
        elif op == "summon_attack":
            # Phase K (v15 true-Osty): the summon deals the damage (literal). Lockstep with ForgedCards.Describe.
            satk = e.get("amount", 0)
            sh = e.get("hits", 1)
            parts.append(f"Deal {satk} damage {sh} times with your summon{dmg_suffix}." if sh and sh > 1
                         else f"Deal {satk} damage with your summon{dmg_suffix}.")
        elif op == "buff_summon":
            # Phase K (v15 true-Osty): a self-buff on the summon (default Strength). Lockstep with ForgedCards.Describe.
            bst = e.get("status") or "strength"
            parts.append(f"Your summon gains {max(1, e.get('amount', 0))} {STATUS_NAME.get(bst, bst)}.")
        elif op == "heal_summon":
            # Phase AC (gap #2): heal the class's living summon (literal). Lockstep with ForgedCards.Describe.
            parts.append(f"Heal your summon {max(1, e.get('amount', 0))} HP.")
        elif op == "shield_summon":
            # Phase AC (gap #2): grant Block to the class's living summon (literal). Lockstep with ForgedCards.Describe.
            parts.append(f"Your summon gains {max(1, e.get('amount', 0))} Block.")
        elif op == "add_card":
            # Phase Q (gap #16): title derived from the card_id (title-cased). Lockstep with ForgedCards.Describe.
            parts.append(_add_card_sentence(e, capitalize=True))
        elif op == "summon_blade":
            # Phase T: no class context here, so a fixed phrase. Lockstep with ForgedCards.Describe.
            parts.append("Put your blade into your hand from anywhere.")
        elif op == "upgrade_card":
            # Phase V (gap #18): combat-scoped hand upgrade. Lockstep with ForgedCards.Describe.
            parts.append(_upgrade_sentence(e, capitalize=True))
        elif op == "apply_status" and e["status"] == "strength_down":
            # Phase BL (v64, gap #66): the permanent Strength loss reads like Malaise / Piercing Wail's own text (the
            # "StrengthLoss" var). Lockstep with ForgedCards.Describe.
            parts.append("ALL enemies lose {StrengthLoss} Strength." if aoe
                         else "A random enemy loses {StrengthLoss} Strength." if target == "random_enemy"
                         else "The enemy loses {StrengthLoss} Strength.")
        elif op == "apply_status" and e["status"] == "doom" and str(e.get("scale", "")).lower() == "damage_dealt_unblocked":
            # Phase BL (v64, gap #67): Blight Strike. Lockstep with ForgedCards.Describe.
            parts.append("Apply Doom equal to the unblocked damage dealt.")
        elif op == "apply_status" and e["status"] in _BM_SENTENCES:
            # Phase BM (v65, gaps #68/#69): the self statuses' own sentences. Lockstep with ForgedCards.BmStatusSentence.
            parts.append(_BM_SENTENCES[e["status"]])
        elif op == "apply_status":
            name = STATUS_NAME.get(e["status"], e["status"])
            buff = e["status"] in _BUFFS
            verb = "Gain" if buff else "Apply"
            parts.append(f'{verb} {name}{"" if buff else dmg_suffix}.')  # AJ (v40): random_enemy suffix too
        # Phase H: weave the condition into the gated effect's sentence ("… if your orbs match.").
        when = e.get("when")
        if isinstance(when, dict) and len(parts) > before:
            p = parts[-1]
            clause = ("unless " if when.get("negate") else "if ") + cond_phrase(when)
            parts[-1] = f"{p[:-1]} {clause}." if p.endswith(".") else f"{p} {clause}"
    return "\n".join(parts)


CLASS_TMPL = """using {engine};
using MegaCrit.Sts2.Core.Entities.Cards;

namespace {ns};

// GENERATED by btsgen cardgen -- do not edit by hand. Source: content/cards/{id}.json
public sealed class {cls} : DataCard
{{
    private static readonly CardSpec Definition = new(
        Id: "{id}",
        Cost: {cost},
        Type: {type},
        Rarity: {rarity},
        Target: {target},
        Effects: {effects}{upgrade}{costsx});

    public {cls}() : base(Definition) {{ }}
}}
"""


def gen_class(card: dict) -> tuple[str, str]:
    cls = pascal(card["id"])
    upgrade = ""
    if card.get("upgrade", {}).get("effects"):
        upgrade = ",\n        Upgrade: " + effects_array(card["upgrade"]["effects"])
    cost = card["cost"]
    costs_x = isinstance(cost, str) and cost.strip().upper() == "X"
    costsx = ",\n        CostsX: true" if costs_x else ""
    src = CLASS_TMPL.format(
        engine=ENGINE_NS, ns=NAMESPACE, id=card["id"], cls=cls,
        cost=0 if costs_x else cost, type=TYPE_MAP[card["type"]],
        rarity=RARITY_MAP[card["rarity"]], target=TARGET_MAP[card["target"]],
        effects=effects_array(card["effects"]), upgrade=upgrade, costsx=costsx,
    )
    return cls, src


def loc_entries(card: dict) -> dict[str, str]:
    key = f"{MOD_PREFIX}-{card['id'].upper()}"
    return {f"{key}.title": card["name"], f"{key}.description": describe(card["effects"], card["target"])}


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate STS2 C# card classes from card JSON.")
    ap.add_argument("--in", dest="indir", required=True, help="dir of card *.json")
    ap.add_argument("--out-cs", dest="out_cs", required=True, help="dir for generated *.cs")
    ap.add_argument("--out-loc", dest="out_loc", required=True, help="cards.json localization file to write")
    args = ap.parse_args()

    indir, out_cs, out_loc = Path(args.indir), Path(args.out_cs), Path(args.out_loc)
    out_cs.mkdir(parents=True, exist_ok=True)

    # The Generated/ dir holds ONLY codegen output, so clear it first — otherwise a card removed from
    # the source JSON leaves a stale .cs class behind (still compiled & registered into the game).
    for stale in out_cs.glob("*.cs"):
        stale.unlink()

    loc: dict[str, str] = {}
    count = 0
    for jf in sorted(indir.glob("*.json")):
        card = json.loads(jf.read_text(encoding="utf-8"))
        cls, src = gen_class(card)
        (out_cs / f"{cls}.cs").write_text(src, encoding="utf-8")
        loc.update(loc_entries(card))
        count += 1
        print(f"  {jf.name} -> {cls}.cs")

    out_loc.write_text(json.dumps(loc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"generated {count} card classes -> {out_cs}")
    print(f"wrote localization ({len(loc)} keys) -> {out_loc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

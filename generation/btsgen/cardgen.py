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
}
# Self-buffs are worded "Gain" and always land on the player; debuffs are "Apply"-ed to the target.
# Keep in lockstep with EffectRunner.SelfBuffStatuses (the C# single source of truth for buff-vs-debuff side).
_BUFFS = {
    "strength", "dexterity", "thorns", "regen", "metallicize", "artifact", "buffer",
    "intangible", "ritual", "blur", "temp_strength", "temp_dexterity", "barricade", "focus",
}


def _orb_display(orb) -> str:
    """Display name for an orb in card text. Base orbs are title-cased; 'random' stays lowercase; a custom
    orb name (Phase I, declared in the class orb_pool) is title-cased from its lowercase id."""
    base = {"lightning": "Lightning", "frost": "Frost", "dark": "Dark", "random": "random"}
    if orb in base:
        return base[orb]
    return str(orb or "orb").replace("_", " ").title()


def _pile_phrase(pile) -> str:
    # The human phrase for an add_card destination pile (Phase Q). Mirrors ForgedCards.PilePhrase.
    return {"discard": "discard pile", "draw": "draw pile"}.get(pile, "hand")


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
    elif op == "channel_orb":
        # positional shape (Op, Amount, Status, Hits, Scale, Orb) — Scale is null here (F5: was ScaleX bool).
        lit = f'new EffectSpec("channel_orb", {e.get("amount", 0)}, null, 1, null, "{e["orb"]}")'
    elif op == "add_trigger":
        # Phase H3: named Trigger/Triggered args; the nested payload reuses effect_literal. The optional
        # fire-time When is appended below by the shared When-append (named arg, order-independent in C#).
        nested = "[" + ", ".join(effect_literal(x) for x in e.get("effects", [])) + "]"
        # Amount carries the "ripen" countdown (turns to wait); 0/unused for turn_start/turn_end.
        lit = f'new EffectSpec("add_trigger", {e.get("amount", 0)}, Trigger: "{e.get("trigger", "")}", Triggered: {nested})'
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
    else:
        amount = e.get("amount", 0)
        hits = e.get("hits", 1)
        scale = str(e.get("scale", "")).lower()
        if scale:
            # F5: a scaled effect's amount is a live scalar (x/cards_in_hand/cards_retained/
            # unspent_energy_last_turn); positional (Op, Amount, Status, Hits, Scale). Amount is ignored at runtime.
            lit = f'new EffectSpec("{op}", {amount}, null, {hits}, "{scale}")'
            if scale == "tag_cards_owned":  # Phase AE (gap #25): the counted tag as a named arg (order-independent in C#).
                tag = str(e.get("tag", "")).replace("\\", "\\\\").replace('"', '\\"')
                lit = f'{lit[:-1]}, Tag: "{tag}")'
        elif op == "damage" and e.get("grow", 0):
            # Phase U (gap #23, Rampage): named Grow arg (order-independent in C#). grow ⊥ scale (validator-enforced).
            lit = f'new EffectSpec("damage", {amount}, Grow: {e["grow"]})'
        elif op == "damage" and hits > 1:
            lit = f'new EffectSpec("damage", {amount}, null, {hits})'
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
    }.get(scale, "X")


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
    return kind


def _trigger_fragment(e: dict) -> str:
    # A single payload-effect phrase inside a trigger sentence. Mirrors ForgedCards.TriggerFragment.
    op = e["op"]
    amt = e.get("amount", 0)
    cr = str(e.get("scale", "")).lower() == "cards_retained"  # F5: trigger payload may scale to cards_retained
    to = " to ALL enemies" if e.get("target") == "all_enemies" else ""  # H4: targeted AoE suffix (single enemy → none)
    if op == "damage":  # H4 (gap #14): only meaningful with a target
        return f"deal {amt} damage{to}" if e.get("target") else ""
    if op == "block":
        return "gain Block equal to cards retained" if cr else f"gain {amt} Block"
    if op == "draw":
        return "draw cards equal to cards retained" if cr else f"draw {amt} card(s)"
    if op == "gain_energy":
        return "gain energy equal to cards retained" if cr else f"gain {amt} energy"
    if op == "heal":
        return "heal HP equal to cards retained" if cr else f"heal {amt} HP"
    if op == "lose_hp":
        return "lose HP equal to cards retained" if cr else f"lose {amt} HP"
    if op == "gain_orb_slot":
        return "gain orb slots equal to cards retained" if cr else f"gain {amt} orb slot(s)"
    if op == "forge":  # Phase M (gap #36): fixed-amount income ("At the start of your turn, Forge 2.")
        return f"Forge {amt}"
    if op == "apply_status":
        nm = STATUS_NAME.get(e.get('status'), e.get('status'))
        if e.get("target"):  # H4 (gap #14): a targeted enemy debuff
            return f"apply {amt} {nm}{to}"
        return f"gain {nm} equal to cards retained" if cr else f"gain {amt} {nm}"
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
    else:
        when = "At the end of your turn"
    frags = [f for f in (_trigger_fragment(x) for x in t.get("effects", [])) if f]
    once = " (once per turn)" if t.get("once_per_turn") else ""  # H4
    return f"{when}, {', '.join(frags) if frags else 'do nothing'}{once}."


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
            if scale:
                # Phase M (gap #36): "forged" is ADDITIVE — the printed amount is real, plus your Forge.
                parts.append(f"Deal X damage{dmg_suffix}." if scale == "x"
                             else f"Deal {e.get('amount', 0)} damage{dmg_suffix}, plus your Forge." if scale == "forged"
                             else f"Deal {e.get('amount', 0)} damage{dmg_suffix}, plus 1 per '{e.get('tag', '')}' card you own." if scale == "tag_cards_owned"
                             else f"Deal damage equal to {_scale_phrase(scale)}{dmg_suffix}.")
            elif e.get("grow", 0):
                # Phase U (gap #23, Rampage): {Damage} shows the CURRENT grown value (calc-var). Byte-match ForgedCards.Describe.
                parts.append(f"Deal {{Damage}} damage{dmg_suffix}. Grows by {e['grow']} each time it is played this combat.")
            elif e.get("hits", 1) > 1:
                parts.append(f"Deal {{Damage}} damage {{Hits}} times{dmg_suffix}.")
            else:
                parts.append(f"Deal {{Damage}} damage{dmg_suffix}.")
        elif op == "block":
            scale = str(e.get("scale", "")).lower()
            parts.append("Gain {Block} Block." if not scale
                         else "Gain X Block." if scale == "x"
                         else f"Gain {e.get('amount', 0)} Block, plus your Forge." if scale == "forged"
                         else f"Gain {e.get('amount', 0)} Block, plus 1 per '{e.get('tag', '')}' card you own." if scale == "tag_cards_owned"
                         else f"Gain Block equal to {_scale_phrase(scale)}.")
        elif op == "draw":
            scale = str(e.get("scale", "")).lower()
            parts.append("Draw {Cards} card(s)." if not scale
                         else "Draw X cards." if scale == "x"
                         else f"Draw cards equal to {_scale_phrase(scale)}.")
        elif op == "gain_energy":
            parts.append("Gain {Energy} energy.")
        elif op == "heal":
            # Phase P (gap #21): a scaled heal (damage_dealt_unblocked lifesteal) reads a live amount. Lockstep
            # with ForgedCards.Describe's heal case.
            scale = str(e.get("scale", "")).lower()
            parts.append(f"Heal HP equal to {_scale_phrase(scale)}." if scale else "Heal {Heal} HP.")
        elif op == "lose_hp":
            parts.append("Lose {Loss} HP.")
        elif op == "discard":
            # Phase R (gap #17): random-discard count via the {Discard} var. Lockstep with ForgedCards.Describe.
            parts.append("Discard {Discard} random card(s).")
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
        elif op == "purge":
            # Phase W (gap #19): the purge keyword sentence. Lockstep with ForgedCards.Describe.
            parts.append("Purge. (Removed from your deck for the rest of the run.)")
        elif op == "purge_card":
            # Phase Z (gap #19 choose): the choose-a-card purge sentence. Lockstep with ForgedCards.Describe.
            parts.append("Choose a card in your hand and Purge it. (Removed from your deck for the rest of the run.)")
        elif op == "corruption":
            # Phase AB (gap #20): two sentences (joined by the "\n" that separates parts). Lockstep with ForgedCards.Describe.
            parts.append("Your Skills cost 0.")
            parts.append("Your Skills Exhaust when played.")
        elif op == "blade_empower":
            # Phase AF (gap #41): the blade-multiplier sentence (literal). Lockstep with ForgedCards.Describe.
            parts.append(f"Your blade deals {max(2, e.get('amount', 0))}x damage this turn.")
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
                parts.append(f"Apply {e.get('amount', 0)} {nm}{' to ALL enemies' if aoe else ''}.")
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
        elif op == "apply_status":
            name = STATUS_NAME.get(e["status"], e["status"])
            buff = e["status"] in _BUFFS
            verb = "Gain" if buff else "Apply"
            parts.append(f'{verb} {name}{" to ALL enemies" if aoe and not buff else ""}.')
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

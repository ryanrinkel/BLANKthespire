using BaseLib.Abstracts;

namespace BlankTheSpire.BlankTheSpireCode.Engine;

/// <summary>
/// i18n (I18N_PLAN C2): the localization payloads of the forged models, built in the active game language. The
/// creative strings (names, descriptions) come from the spec, overridden per field by the bundle's <c>loc</c> block for
/// the game language; the fixed defaults (pronouns, banter) go through the <see cref="ForgedText"/> tables. English
/// returns exactly the strings the shells used to build inline.
/// </summary>
public static partial class ForgedText
{
    /// <summary>A forged class's <see cref="BaseLib.Abstracts.CharacterLoc"/> (called by the generated
    /// <c>ForgedCharacterSlotKK.Localization</c>). Field order: Title, TitleObject, Description, PronounObject,
    /// PronounSubject, PronounPossessive, PossessiveAdjective, AromaPrinciple, EndTurnPingAlive, EndTurnPingDead,
    /// EventDeathPrevention, GoldMonologue, CardsModifierTitle, CardsModifierDescription.</summary>
    public static List<(string, string)> CharacterLoc(CharacterSpec spec)
    {
        string lang = Lang;
        string name = spec.Loc.LocName(lang) ?? spec.Name;
        string desc = spec.Loc.LocDescription(lang) ?? spec.Description;
        return new BaseLib.Abstracts.CharacterLoc(
            name, name, desc,
            T("char.pronoun_object", "them"), T("char.pronoun_subject", "they"),
            T("char.pronoun_possessive", "theirs"), T("char.possessive_adjective", "their"),
            T("char.aroma", "Forged from the effect vocabulary."),
            T("char.banter_alive", "Your move."), T("char.banter_dead", "..."),
            T("char.death_prevention", "Not yet. There is more to compose."), T("char.gold_monologue", "It all adds up."),
            T("char.cards_modifier_title", "Forged"), T("char.cards_modifier_description", "Composed from the effect vocabulary."));
    }

    /// <summary>The display name of a spec in the active language (its <c>loc</c> name, else the English).</summary>
    public static string Name(IReadOnlyDictionary<string, LocText>? loc, string english) => loc.LocName(Lang) ?? english;

    /// <summary>The model-written description of a spec in the active language (its <c>loc</c> description, else the English).</summary>
    public static string Description(IReadOnlyDictionary<string, LocText>? loc, string english) => loc.LocDescription(Lang) ?? english;
}

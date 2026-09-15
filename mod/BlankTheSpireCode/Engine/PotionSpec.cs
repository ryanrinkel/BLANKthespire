namespace BlankTheSpire.BlankTheSpireCode.Engine;

/// <summary>
/// Phase BA: the data definition of a forged POTION — the single custom potion every forged class carries,
/// read from the class bundle's <c>potion_pool</c> array by <see cref="ForgedCharacters"/> and fed to the
/// compiled <c>ForgedClassKKPotion</c> shell (see <see cref="Powers.ForgedPotion"/>).
///
/// A potion is the cheapest content type in the whole forge, for one reason found by reflection (BA-0):
/// <c>PotionModel.OnUse</c> is handed a <c>PlayerChoiceContext</c>, which is exactly the first argument of
/// <see cref="EffectRunner.RunRelicEffects"/>. A potion is therefore "a relic hook that fires once, on
/// demand" — the same no-card effect sub-vocabulary, the same runner, no new effect path.
///
/// The class's potion lands in that class's OWN <c>ForgedClassPotionPoolKK</c>, which
/// <c>PotionFactory.GetPotionOptions</c> concatenates with the base game's <c>SharedPotionPool</c> — so the
/// class's potion is an ADDITION to the normal drop table, never a replacement (BA-0 confirmed).
/// </summary>
/// <param name="Rarity">common | uncommon | rare — the three tiers <c>PotionFactory</c> rolls (10% rare,
/// 25% uncommon, 65% common, then a uniform pick within the rolled tier). Event/Token are base-game-internal
/// and stay out of the vocabulary.</param>
/// <param name="Usage">combat (<c>PotionUsage.CombatOnly</c>) | any (<c>AnyTime</c>). <c>Automatic</c> is a
/// different fantasy (a potion that fires itself) and is out of scope.</param>
/// <param name="Target">self | enemy | all_enemies, mapped to <c>TargetType</c>. NOTE potions target
/// differently from cards: <c>TargetType.Self</c> DOES receive a target (the owner), per PotionModel's own
/// "Do not try to unify this with CardModel.IsValidTarget" comment.</param>
public sealed record PotionSpec(
    string Id,
    string Name,
    string Description,
    string Emoji,
    string Rarity,
    string Usage,
    string Target,
    EffectSpec[] Effects);

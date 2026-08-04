namespace BlankTheSpire.BlankTheSpireCode.Engine;

/// <summary>
/// The data definition of a forged CLASS (Phase B). Like <see cref="CardSpec"/> for cards, this is read
/// from JSON in the writable user-data dir at startup (<c>user://forged/characters/KK.json</c>) by
/// <see cref="ForgedCharacters"/> and fed to the pre-compiled <c>ForgedCharacterSlotKK</c> shells.
///
/// A class's cards live in its own card slots (<c>user://forged/characters/KK/cards/NN.json</c>), each bound
/// to the class's isolated pool. <see cref="StartingDeck"/> references those slots by 1-based index + count
/// (slot indices, not card ids — the registered card id is type-derived, so the slot index is the stable key).
/// <see cref="IsEmpty"/> marks an unfilled class: its character is hidden from select until JSON fills it.
/// </summary>
public sealed record CharacterSpec(
    string Name,
    string Description,
    int MaxHp,
    int MaxEnergy,
    (int Slot, int Count)[] StartingDeck,
    float PoolH,
    float PoolS,
    float PoolV,
    int OrbSlots = 0,
    bool IsEmpty = false)
{
    /// <summary>The class's orb pool (Phase I): the ordered base/custom orb list its cards channel by name.
    /// Empty = not a forged-orb class (channel_orb, if any, uses the base lightning/frost/dark behaviour). Set
    /// via object initializer by <see cref="ForgedCharacters"/>; defaults to empty (incl. the empty-class spec).</summary>
    public OrbPoolEntry[] OrbPool { get; init; } = [];

    /// <summary>The class's status pool (Phase J): the ordered list of ≤4 custom (forged) statuses its cards can
    /// apply by name via <c>apply_status_custom</c>. Empty = the class only uses base-game statuses. Indexed by
    /// position (slot M = index+1, mapping to the compiled <c>ForgedClassKStatusM</c> shell). Set via object
    /// initializer by <see cref="ForgedCharacters"/>; defaults to empty (incl. the empty-class spec).</summary>
    public StatusSpec[] StatusPool { get; init; } = [];

    /// <summary>The class's summon pool (Phase K): the ordered list of ≤<see cref="ForgedCharacters.MaxSummons"/>
    /// forged minions its cards can summon by name via the <c>summon</c> op. Empty = the class has no summons.
    /// Indexed by position (slot M = index+1, mapping to the compiled <c>ForgedClassKSummonM</c> shell). Set via
    /// object initializer by <see cref="ForgedCharacters"/>; defaults to empty (incl. the empty-class spec).</summary>
    public SummonSpec[] SummonPool { get; init; } = [];

    /// <summary>The class's forged relic (Phase L): a single custom starting relic, or null if the class uses the
    /// default (Burning Blood). Parsed from the class bundle's optional <c>relic</c> object by
    /// <see cref="ForgedCharacters"/>; fed to the compiled <c>ForgedClassKKRelic</c> shell via
    /// <see cref="ForgedCharacters.RelicSpecFor"/>. Defaults to null (incl. the empty-class spec).</summary>
    public RelicSpec? Relic { get; init; } = null;

    /// <summary>The spec for an unfilled class slot: harmless defaults, hidden from character select.</summary>
    public static CharacterSpec EmptyClass() => new(
        Name: "Forged Class (empty)", Description: "", MaxHp: 70, MaxEnergy: 3,
        StartingDeck: [], PoolH: 0f, PoolS: 0f, PoolV: 1f, OrbSlots: 0, IsEmpty: true);
}

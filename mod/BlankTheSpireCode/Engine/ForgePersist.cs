using System.Threading.Tasks;
using BaseLib.Abstracts;
using BaseLib.Utils;
using BlankTheSpire.BlankTheSpireCode.Powers;
using MegaCrit.Sts2.Core.Entities.Players;
using MegaCrit.Sts2.Core.GameActions.Multiplayer;

namespace BlankTheSpire.BlankTheSpireCode.Engine;

/// <summary>
/// Phase AY (v54): RUN-PERSISTENT FORGE — the bank behind the opt-in class flag <c>forge_persist</c>.
///
/// The Forge counter is a power, and powers die at combat end (that was the Phase M decision, and it stays the
/// default). A class that sets <c>forge_persist</c> instead keeps a small carry between fights:
///   <list type="bullet">
///   <item>at combat end <see cref="ForgedForgePower.Bank"/> stores <c>min(Forge, PersistCap)</c>;</item>
///   <item>at the start of the player's FIRST turn of the next combat this model pays it back through
///         <see cref="ForgedForgePower.Stoke"/> — so the restore also summons the signature blade, exactly as a
///         first Forge income would, and the bank is emptied (it is re-banked at the end of THIS combat).</item>
///   </list>
///
/// AY-0 spike findings, baked in:
/// <list type="number">
/// <item>STS2 DOES expose run-persistent per-model state: <c>[SavedProperty]</c> on a card/relic model, carried in
///   <c>SerializableCard/Relic.Props</c>. The PLAYER has no props bag — but BaseLib's <c>SavedSpireField</c> adds
///   one (<c>ExtendedSaveTypes</c> patches <c>SerializablePlayer</c>'s JSON + packet round-trip), so a plain
///   <c>SavedSpireField&lt;Player, int&gt;</c> is the whole store: it rides the RUN SAVE, survives save-and-quit,
///   and is scoped to the run because a new run is a new Player. BaseLib registers it for us — a STATIC field of a
///   mod type is force-initialized in its post-mod-init scan, then sorted into the save handlers.</item>
/// <item>No combat-start hook hands out a (ctx, player) — the same L-0 finding the relic's <c>start_combat_block</c>
///   lives with — so the restore rides <c>AfterPlayerTurnStart</c> on turn 1, guarded to once per combat.</item>
/// <item>Nothing but a card/relic/power is a hook listener, and not every forge class ships a relic, so the restore
///   needs a listener of its own: BaseLib's <see cref="CustomSingletonModel"/> with <c>HookType.Combat</c>
///   (<c>ModHelper.SubscribeForCombatStateHooks</c> — the combat listener list is what <c>AfterPlayerTurnStart</c>
///   iterates; run-state subscribers never see it).</item>
/// </list>
/// </summary>
public sealed class ForgePersist : CustomSingletonModel
{
    public ForgePersist() : base(HookType.Combat) { }

    /// <summary>The banked Forge, per Player, in the RUN SAVE (BaseLib <c>SavedSpireField</c>: written into
    /// <c>SerializablePlayer</c> by the extended-save handlers, so a save-and-quit between floors keeps the carry).
    /// STATIC on purpose — that is what BaseLib's post-mod-init scan looks for to register the field.</summary>
    internal static readonly SavedSpireField<Player, int> Banked = new(() => 0, "forge_bank");

    /// <summary>Whether this combat's restore has already run (reset at combat start). The turn-start hook fires
    /// every turn; the carry is paid back ONCE, on the first.</summary>
    private bool _restored;

    public override Task BeforeCombatStart()
    {
        _restored = false;
        return Task.CompletedTask;
    }

    /// <summary>Pay the carry back at the start of the player's first turn. Routed through <c>Stoke</c> so the
    /// restore behaves exactly like a first Forge income of the combat — the blade is summoned, the counter starts
    /// at the carry. The bank is emptied as it is paid out: a mid-combat save/reload must not pay it twice, and the
    /// end of THIS combat re-banks whatever the counter holds then.</summary>
    public override async Task AfterPlayerTurnStart(PlayerChoiceContext ctx, Player player)
    {
        if (_restored) return;
        _restored = true;
        if (!ForgedCharacters.IsForgePersistPlayer(player)) return;
        int carry = Banked.Get(player);
        if (carry <= 0) return;
        Banked.Set(player, 0);
        MainFile.Logger.Info($"[AY] forge restored: carried {carry} into this combat (the blade remembers).");
        await ForgedForgePower.Stoke(ctx, player, carry);
    }
}

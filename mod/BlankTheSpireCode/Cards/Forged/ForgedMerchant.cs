using System;
using System.Collections.Generic;
using BaseLib.Utils.NodeFactories;
using BlankTheSpire.BlankTheSpireCode.Engine;
using BlankTheSpire.BlankTheSpireCode.Extensions;
using Godot;
using HarmonyLib;
using MegaCrit.Sts2.Core.Entities.Players;
using MegaCrit.Sts2.Core.Nodes.Rooms;
using MegaCrit.Sts2.Core.Nodes.Screens.Shops;

namespace BlankTheSpire.BlankTheSpireCode.Cards.Forged;

/// <summary>
/// Merchant-screen identity: a forged class inherits PlaceholderCharacterModel's IRONCLAD shopper.
/// The asset hook (CustomMerchantAnimPath) can't fix this — NMerchantRoom hard-casts the loaded asset
/// to PackedScene, so the path must be a real scene and can never carry the runtime-downloaded sprite.
/// Instead, after the room spawns its shoppers, swap each forged player's NMerchantCharacter for one
/// built from the class's cached sprite.png (the same art as the combat model) via BaseLib's
/// NodeFactory, falling back to the shared "?" texture. Best-effort: any failure leaves the vanilla
/// shopper in place.
/// </summary>
public static class ForgedMerchant
{
    /// <summary>Meta flag marking a swapped-in static shopper, so the guards below can no-op the
    /// Spine-driving vanilla methods (they wrap GetChild(0) in a MegaSprite unconditionally).</summary>
    internal const string MetaFlag = "bts_forged_merchant";

    internal static NMerchantCharacter? TryCreate(int slot)
    {
        try
        {
            Texture2D? tex = ForgedSprite.TryLoadTexture(slot)
                             ?? ResourceLoader.Load<Texture2D>("char_select_char_name.png".CharacterUiPath());
            if (tex == null) return null;
            var shopper = NodeFactory<NMerchantCharacter>.CreateFromResource(tex);
            shopper.SetMeta(MetaFlag, true);
            // The vanilla relaxed_loop is Spine-only; give the static sprite the same idle bob as combat.
            if (shopper.GetChildOrNull<Node2D>(0) is { } body)
                shopper.Connect(Node.SignalName.Ready,
                    Callable.From(() => ForgedSpriteAnimator.StartIdle(body)),
                    (uint)GodotObject.ConnectFlags.OneShot);
            return shopper;
        }
        catch (Exception e)
        {
            MainFile.Logger.Warn($"[ForgedMerchant] shopper for slot {slot:00} failed, keeping vanilla: {e.Message}");
            return null;
        }
    }
}

/// <summary>Swaps the freshly spawned shoppers: _playerVisuals[i] pairs with _players[i] (both filled
/// in the same loop by the original method).</summary>
[HarmonyPatch(typeof(NMerchantRoom), "AfterRoomIsLoaded")]
internal static class ForgedMerchantSwapPatch
{
    [HarmonyPostfix]
    private static void Postfix(NMerchantRoom __instance)
    {
        try
        {
            List<Player> players = __instance._players;
            List<NMerchantCharacter> visuals = __instance._playerVisuals;
            for (int i = 0; i < players.Count && i < visuals.Count; i++)
            {
                if (players[i].Character is not IForgedCharacterSlot forged) continue;
                NMerchantCharacter old = visuals[i];
                if (old == null || !GodotObject.IsInstanceValid(old)) continue;
                NMerchantCharacter? shopper = ForgedMerchant.TryCreate(forged.ClassSlot);
                if (shopper == null) continue;
                Node parent = old.GetParent();
                parent.AddChild(shopper);
                parent.MoveChild(shopper, old.GetIndex());
                shopper.Position = old.Position;
                shopper.Modulate = old.Modulate;
                visuals[i] = shopper;
                old.QueueFree();
                MainFile.Logger.Info($"[ForgedMerchant] swapped shopper {i} for forged slot {forged.ClassSlot:00}.");
            }
        }
        catch (Exception e)
        {
            MainFile.Logger.Warn($"[ForgedMerchant] swap failed, vanilla shoppers stand: {e.Message}");
        }
    }
}

/// <summary>NMerchantCharacter._Ready starts a spine-ready poll that error-spams every frame on a
/// non-Spine body; skip it for swapped shoppers (their idle starts from the Ready signal instead).</summary>
[HarmonyPatch(typeof(NMerchantCharacter), "_Ready")]
internal static class ForgedMerchantReadyGuard
{
    [HarmonyPrefix]
    private static bool Prefix(NMerchantCharacter __instance) => !__instance.HasMeta(ForgedMerchant.MetaFlag);
}

/// <summary>PlayAnimation drives Spine unconditionally (GetAnimationState throws on a static body).
/// The one cue that reaches shoppers outside the room's own scene is the game-over "die" — fake it
/// with the same tip-and-fade the combat sprite uses; ignore everything else.</summary>
[HarmonyPatch(typeof(NMerchantCharacter), nameof(NMerchantCharacter.PlayAnimation))]
internal static class ForgedMerchantAnimGuard
{
    [HarmonyPrefix]
    private static bool Prefix(NMerchantCharacter __instance, string anim)
    {
        if (!__instance.HasMeta(ForgedMerchant.MetaFlag)) return true;
        if (anim == "die" && __instance.GetChildOrNull<Node2D>(0) is { } body && body.IsInsideTree())
        {
            body.CreateTween().TweenProperty(body, "rotation", -0.25f, 0.5)
                .SetTrans(Tween.TransitionType.Cubic).SetEase(Tween.EaseType.Out);
            body.CreateTween().TweenProperty(body, "modulate", new Color(0.65f, 0.65f, 0.65f, 0.3f), 0.5);
        }
        return false;
    }
}

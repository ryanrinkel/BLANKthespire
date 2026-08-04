using System;
using BlankTheSpire.BlankTheSpireCode.Cards.Forged;
using Godot;
using HarmonyLib;
using MegaCrit.Sts2.Core.Nodes.Combat;

namespace BlankTheSpire.BlankTheSpireCode.Engine;

/// <summary>
/// Tier 2 of the sprite spike: fake "animations" for a flat generated sprite using Godot tweens.
/// The game funnels combat animation cues through <c>NCreature.SetAnimationTrigger</c> (Hit comes from
/// CreatureCmd.Damage, Attack from AttackCommand; Cast/PowerUp are fired per-card — DataCards do it in
/// EffectRunner.Execute). For a body with no Spine skeleton those calls are designed no-ops
/// (<c>_spineAnimator?.SetTrigger</c>), so postfixes can safely translate the cues into tweens.
///
/// Choreography rule learned the hard way: keep every tween SEQUENTIAL and give each animated property
/// its own tween (SetParallel/Chain step composition silently produced no visible motion in-game — two
/// tweeners contesting one property in the same step cancel out). The idle bob animates SCALE only and
/// trigger tweens animate position/rotation/modulate only, so idle never contests a trigger either.
/// </summary>
public static class ForgedSpriteAnimator
{
    /// <summary>Rest pose of the body, captured before the first trigger tween. Our feet-pivot container
    /// rests at (0,0), but the "?" fallback (BaseLib factory) makes the body the centered Sprite2D itself,
    /// resting at (0,-h/2) — so remember rather than assume.</summary>
    private const string BasePosMeta = "bts_base_pos";
    private const string TweensMeta = "bts_trigger_tweens";

    /// <summary>Looping breath: stretch up 3.5% / narrow 1.5%, pivoting at the feet. Called via the
    /// visuals root's ready signal (see ForgedSprite.BuildVisuals).</summary>
    public static void StartIdle(Node2D body)
    {
        if (!GodotObject.IsInstanceValid(body) || !body.IsInsideTree()) return;
        var tw = body.CreateTween().SetLoops();
        tw.TweenProperty(body, "scale", new Vector2(0.985f, 1.035f), 1.2)
            .SetTrans(Tween.TransitionType.Sine).SetEase(Tween.EaseType.InOut);
        tw.TweenProperty(body, "scale", Vector2.One, 1.2)
            .SetTrans(Tween.TransitionType.Sine).SetEase(Tween.EaseType.InOut);
    }

    /// <summary>True when this creature is a forged-class player whose body we animate (no Spine).</summary>
    internal static bool IsForgedStaticPlayer(NCreature creature)
    {
        if (creature.Entity?.Player?.Character is not IForgedCharacterSlot) return false;
        return !creature.HasSpineAnimation; // if a forged class ever gets real Spine art, defer to it
    }

    /// <summary>Translate one animation trigger into canned tweens on the sprite body.</summary>
    public static void PlayTrigger(NCreature creature, string trigger)
    {
        if (trigger is not ("Attack" or "Hit" or "Cast" or "PowerUp" or "Dead" or "Idle" or "Revive")) return;

        Node2D? body = creature.Visuals?.GetCurrentBody();
        if (body == null || !GodotObject.IsInstanceValid(body) || !body.IsInsideTree()) return;

        if (!body.HasMeta(BasePosMeta)) body.SetMeta(BasePosMeta, body.Position);
        Vector2 basePos = body.GetMeta(BasePosMeta).AsVector2();

        KillTriggerTweens(body); // one cue at a time; a new one animates on from the current pose

        switch (trigger)
        {
            case "Attack": // lunge at the enemy line (the player faces right), settle back
            {
                var pos = NewTween(body);
                pos.TweenProperty(body, "position:x", basePos.X + 46f, 0.10)
                    .SetTrans(Tween.TransitionType.Cubic).SetEase(Tween.EaseType.Out);
                pos.TweenProperty(body, "position:x", basePos.X, 0.28)
                    .SetTrans(Tween.TransitionType.Sine).SetEase(Tween.EaseType.InOut);
                break;
            }
            case "Hit": // recoil + tip back + over-bright red flash, wobble back upright
            {
                // Hit plays during the noisiest frame on screen (screen shake, hit spark, damage number),
                // so it needs to be LOUD to read. The flash goes over-bright (>1 modulate brightens; a
                // plain red MULTIPLY just muddies dark sprite colors).
                var pos = NewTween(body);
                pos.TweenProperty(body, "position:x", basePos.X - 38f, 0.11)
                    .SetTrans(Tween.TransitionType.Cubic).SetEase(Tween.EaseType.Out);
                pos.TweenProperty(body, "position:x", basePos.X, 0.60)
                    .SetTrans(Tween.TransitionType.Elastic).SetEase(Tween.EaseType.Out);
                var rot = NewTween(body);
                rot.TweenProperty(body, "rotation", -0.09f, 0.11)
                    .SetTrans(Tween.TransitionType.Cubic).SetEase(Tween.EaseType.Out);
                rot.TweenProperty(body, "rotation", 0f, 0.55)
                    .SetTrans(Tween.TransitionType.Elastic).SetEase(Tween.EaseType.Out);
                var col = NewTween(body);
                col.TweenProperty(body, "modulate", new Color(2.4f, 0.9f, 0.9f), 0.08);
                col.TweenInterval(0.14); // hold the flash a beat so it registers
                col.TweenProperty(body, "modulate", Colors.White, 0.60);
                break;
            }
            case "Cast":
            case "PowerUp": // small hop + brightening flash
            {
                var pos = NewTween(body);
                pos.TweenProperty(body, "position:y", basePos.Y - 18f, 0.12)
                    .SetTrans(Tween.TransitionType.Cubic).SetEase(Tween.EaseType.Out);
                pos.TweenProperty(body, "position:y", basePos.Y, 0.26)
                    .SetTrans(Tween.TransitionType.Bounce).SetEase(Tween.EaseType.Out);
                var col = NewTween(body);
                col.TweenProperty(body, "modulate", new Color(1.5f, 1.5f, 1.9f), 0.10);
                col.TweenProperty(body, "modulate", Colors.White, 0.35);
                break;
            }
            case "Dead": // tip back at the feet and fade down
            {
                NewTween(body).TweenProperty(body, "rotation", -0.25f, 0.5)
                    .SetTrans(Tween.TransitionType.Cubic).SetEase(Tween.EaseType.Out);
                NewTween(body).TweenProperty(body, "modulate", new Color(0.65f, 0.65f, 0.65f, 0.3f), 0.5);
                break;
            }
            case "Idle":
            case "Revive": // back to the rest pose
            {
                NewTween(body).TweenProperty(body, "position", basePos, 0.2);
                NewTween(body).TweenProperty(body, "rotation", 0f, 0.2);
                NewTween(body).TweenProperty(body, "modulate", Colors.White, 0.2);
                break;
            }
        }
    }

    private static Tween NewTween(Node2D body)
    {
        var tw = body.CreateTween();
        var arr = body.HasMeta(TweensMeta) ? body.GetMeta(TweensMeta).AsGodotArray() : new Godot.Collections.Array();
        arr.Add(tw);
        body.SetMeta(TweensMeta, arr);
        return tw;
    }

    private static void KillTriggerTweens(Node2D body)
    {
        if (!body.HasMeta(TweensMeta)) return;
        foreach (var v in body.GetMeta(TweensMeta).AsGodotArray())
        {
            var t = v.As<Tween>();
            if (t != null && GodotObject.IsInstanceValid(t)) t.Kill();
        }
        body.SetMeta(TweensMeta, new Godot.Collections.Array());
    }
}

/// <summary>
/// The main seam: most animation cues (CreatureCmd.TriggerAnim → Hit/Attack/Cast/PowerUp) end in
/// NCreature.SetAnimationTrigger. Gated to forged-class players whose body has no Spine skeleton, so
/// real characters, monsters, and pets are untouched.
/// </summary>
[HarmonyPatch(typeof(NCreature), nameof(NCreature.SetAnimationTrigger))]
internal static class ForgedSpriteAnimPatch
{
    [HarmonyPostfix]
    private static void Postfix(NCreature __instance, string trigger)
    {
        try
        {
            if (!ForgedSpriteAnimator.IsForgedStaticPlayer(__instance)) return;
            ForgedSpriteAnimator.PlayTrigger(__instance, trigger);
        }
        catch (Exception e)
        {
            MainFile.Logger.Warn($"[ForgedSprite] trigger '{trigger}' anim failed: {e.Message}");
        }
    }
}

/// <summary>Death fires SetAnimationTrigger("Dead") only when a Spine animator exists (StartDeathAnim
/// gates it), so the death cue needs its own postfix for static sprites.</summary>
[HarmonyPatch(typeof(NCreature), nameof(NCreature.StartDeathAnim))]
internal static class ForgedSpriteDeathPatch
{
    [HarmonyPostfix]
    private static void Postfix(NCreature __instance)
    {
        try
        {
            if (!ForgedSpriteAnimator.IsForgedStaticPlayer(__instance)) return;
            ForgedSpriteAnimator.PlayTrigger(__instance, "Dead");
        }
        catch (Exception e)
        {
            MainFile.Logger.Warn($"[ForgedSprite] death anim failed: {e.Message}");
        }
    }
}

/// <summary>Same gating exists on revive (StartReviveAnim only fires the trigger for Spine bodies with a
/// Revive clip); without this the sprite would stay tipped over + faded after a death-prevention revive.</summary>
[HarmonyPatch(typeof(NCreature), nameof(NCreature.StartReviveAnim))]
internal static class ForgedSpriteRevivePatch
{
    [HarmonyPostfix]
    private static void Postfix(NCreature __instance)
    {
        try
        {
            if (!ForgedSpriteAnimator.IsForgedStaticPlayer(__instance)) return;
            ForgedSpriteAnimator.PlayTrigger(__instance, "Revive");
        }
        catch (Exception e)
        {
            MainFile.Logger.Warn($"[ForgedSprite] revive anim failed: {e.Message}");
        }
    }
}

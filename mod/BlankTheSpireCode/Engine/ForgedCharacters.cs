using System.Linq;
using BlankTheSpire.BlankTheSpireCode.Cards.Forged; // Phase Q: IForgedCharacterSlot (the player's class index)
using MegaCrit.Sts2.Core.Entities.Players;
using MegaCrit.Sts2.Core.Models; // Phase Q: ModelDb / CardModel (resolve a sibling card model for add_card)

namespace BlankTheSpire.BlankTheSpireCode.Engine;

/// <summary>
/// The data-driven CLASS runtime (Phase B) — the character analogue of <see cref="ForgedCards"/>. The mod
/// ships a fixed set of pre-compiled <c>ForgedCharacterSlotKK</c> classes, each with its own isolated card
/// pool (<c>ForgedClassPoolKK</c>) and a block of card slots statically bound to that pool. At startup each
/// shell asks this loader for its <see cref="CharacterSpec"/> / per-slot <see cref="CardSpec"/>, read from
/// JSON in the writable user-data dir:
///   <c>user://forged/characters/KK.json</c>             — the class (name/desc/hp/energy/starting deck/color)
///   <c>user://forged/characters/KK/cards/NN.json</c>    — that class's cards (same shape as forged cards)
///
/// Card JSON is re-validated through <see cref="ForgedCards.TryParseCardJson"/> (one validator, one vocab).
/// Unfilled classes return <see cref="CharacterSpec.EmptyClass"/> and their shell hides itself from character
/// select. Read once at startup (Q2: pools freeze at init), so new files need a restart.
/// </summary>
public static class ForgedCharacters
{
    /// <summary>How many <c>ForgedCharacterSlotKK</c> classes the mod ships. Keep in sync with slotgen.py.</summary>
    public const int ClassCount = 4;

    /// <summary>Card slots per class (each a compiled type bound to the class pool). Keep in sync with slotgen.py.</summary>
    public const int CardsPerClass = 40;

    private const string Root = "user://forged/characters";

    private static Dictionary<int, CharacterSpec>? _classes;
    private static Dictionary<(int Class, int Slot), CardSpec>? _cards;

    // --- public accessors used by the generated shells -------------------------------------------

    /// <summary>The filled spec for class <paramref name="k"/> (1-based), or an empty (hidden) spec.</summary>
    public static CharacterSpec SpecForClass(int k)
    {
        _classes ??= LoadClasses();
        return _classes.TryGetValue(k, out var s) ? s : CharacterSpec.EmptyClass();
    }

    /// <summary>The filled card spec for class <paramref name="k"/> slot <paramref name="n"/>, or an empty slot.</summary>
    public static CardSpec CardSpecFor(int k, int n)
    {
        _cards ??= LoadCards();
        return _cards.TryGetValue((k, n), out var s) ? s : CardSpec.EmptySlot($"forged_class{k:00}_card{n:00}");
    }

    /// <summary>True if class <paramref name="k"/> has a real (non-empty) definition.</summary>
    public static bool IsClassFilled(int k) => !SpecForClass(k).IsEmpty;

    /// <summary>Phase T: the card id of class <paramref name="k"/>'s signature blade (the one filled slot whose
    /// spec is a TOKEN), or null if the class ships no blade (a pre-v20 class). Scanned by the first-Forge summon
    /// (<see cref="ForgedForgePower.SummonBlade"/>) and the <c>summon_blade</c> op to know WHICH card to create.
    /// At most one token per class (generation enforces exactly one), so the first hit is authoritative.</summary>
    public static string? BladeCardId(int k)
    {
        if (k < 1 || k > ClassCount) return null;
        for (int n = 1; n <= CardsPerClass; n++)
        {
            var spec = CardSpecFor(k, n);
            if (!spec.IsEmpty && spec.IsToken) return spec.Id;
        }
        return null;
    }

    // --- Phase Q (gap #16): add_card resolution -----------------------------------------------------

    /// <summary>The 1-based forged-class index the player is currently playing (their character shell's
    /// <c>ClassSlot</c>), or 0 if they are not a forged class. add_card is a CLASS mechanic — the id it copies
    /// resolves against THIS class — so both the card path (EffectRunner) and the trigger path (TriggerRunner)
    /// read the class off the player, uniformly, with no per-card wiring.</summary>
    public static int ClassIndexOfPlayer(Player? player) =>
        player?.Character is IForgedCharacterSlot slot ? slot.ClassSlot : 0;

    /// <summary>Resolve a SAME-CLASS <paramref name="cardId"/> to a fresh, combat-ready <see cref="CardModel"/>
    /// copy OWNED by <paramref name="owner"/> for add_card (the caller drops it into a combat pile), or null when
    /// class <paramref name="k"/> has no such (non-empty) card, or — LOOP DISCIPLINE (depth-1) — when the
    /// referenced card is a DIFFERENT card that itself contains an add_card op (that would chain A→B→C; refused so
    /// generation can't run away). A SELF-copy (<paramref name="adderId"/> == cardId, the Anger pattern) is EXEMPT:
    /// it re-adds itself, gated by the deck cycle — not a chain — and add_card only PLACES cards (never executes
    /// recursively), so there is no runaway.</summary>
    public static CardModel? ResolveClassCardModel(int k, string? cardId, Player owner, string? adderId = null)
    {
        if (k < 1 || k > ClassCount || string.IsNullOrWhiteSpace(cardId)) return null;
        for (int n = 1; n <= CardsPerClass; n++)
        {
            var spec = CardSpecFor(k, n);
            if (spec.IsEmpty || spec.Id != cardId) continue;
            if (spec.Id != adderId && spec.Effects.Any(e => e.Op == "add_card"))
            {
                MainFile.Logger.Warn($"[Q] add_card refused: '{cardId}' itself contains add_card (depth-1 — no add_card chains; self-copies are exempt).");
                return null;
            }
            // The compiled slot shell (ForgedClassKKCardNN) is this assembly's canonical model for the slot.
            var type = typeof(ForgedCharacters).Assembly.GetType(
                $"BlankTheSpire.BlankTheSpireCode.Cards.Forged.ForgedClass{k:D2}Card{n:D2}");
            if (type == null) return null;
            try
            {
                // Build the copy the SAME way every base-game generator does (Anger, Infernal Blade): route the
                // canonical through CombatState.CreateCard, which ToMutable()s it, binds Owner, registers it in the
                // combat scope, and runs AfterCreated(). A BARE ToMutable() clone has a NULL Owner and no scope, so
                // CardPileCmd.AddGeneratedCardToCombat crashes dereferencing card.Owner.Creature.CombatState (Q's
                // native runtime crash — see autoslay-vocab-runtime-2026-07-09).
                return owner.Creature.CombatState.CreateCard((CardModel)ModelDb.Get(type), owner);
            }
            catch (System.Exception ex)
            {
                MainFile.Logger.Warn($"[Q] add_card: could not build model for '{cardId}' (class {k} slot {n}): {ex.Message}.");
                return null;
            }
        }
        return null;
    }

    /// <summary>Phase AH (gaps #35/#38): resolve a SAME-CLASS <paramref name="cardId"/> to a fresh, combat-ready
    /// <see cref="CardModel"/> copy OWNED by <paramref name="owner"/> for <c>transform_card</c> (the replacement
    /// passed to <c>CardCmd.Transform</c>). Like <see cref="ResolveClassCardModel"/> it builds the copy through
    /// <c>CombatState.CreateCard</c> (owner-bound, scoped), but the LOOP DISCIPLINE differs: transform refuses a
    /// target that itself carries <c>transform_card</c> UNLESS that target transforms straight BACK to
    /// <paramref name="adderId"/> — i.e. a two-card MODE-SWAP (A↔B) is allowed (each is a leaf w.r.t. the other),
    /// but a CHAIN (A→B→C, C≠A) is refused, so a run can't cascade through three+ cards on a single play. A
    /// SELF-transform (target == <paramref name="adderId"/>) is refused (a card becoming itself is a no-op).
    /// Returns null (logged) on any refusal or an unknown/empty id.</summary>
    public static CardModel? ResolveTransformTarget(int k, string? cardId, Player owner, string? adderId = null)
    {
        if (k < 1 || k > ClassCount || string.IsNullOrWhiteSpace(cardId)) return null;
        if (cardId == adderId)
        {
            MainFile.Logger.Warn($"[AH] transform refused: '{cardId}' transforms into itself (no-op).");
            return null;
        }
        for (int n = 1; n <= CardsPerClass; n++)
        {
            var spec = CardSpecFor(k, n);
            if (spec.IsEmpty || spec.Id != cardId) continue;
            // No transform CHAINS: the target may carry transform_card ONLY if it transforms back to the adder
            // (a mode-swap A↔B). Any other transform_card target is a chain (A→B→C) — refuse the copy.
            var tgtXform = spec.Effects.Concat(spec.Upgrade ?? []).FirstOrDefault(e => e.Op == "transform_card");
            if (tgtXform != null && tgtXform.CardId != adderId)
            {
                MainFile.Logger.Warn($"[AH] transform refused: '{cardId}' itself transforms into '{tgtXform.CardId}' (chain — a target may only carry transform_card if it swaps back; mode-swap A↔B only).");
                return null;
            }
            var type = typeof(ForgedCharacters).Assembly.GetType(
                $"BlankTheSpire.BlankTheSpireCode.Cards.Forged.ForgedClass{k:D2}Card{n:D2}");
            if (type == null) return null;
            try
            {
                return owner.Creature.CombatState.CreateCard((CardModel)ModelDb.Get(type), owner);
            }
            catch (System.Exception ex)
            {
                MainFile.Logger.Warn($"[AH] transform_card: could not build model for '{cardId}' (class {k} slot {n}): {ex.Message}.");
                return null;
            }
        }
        MainFile.Logger.Warn($"[AH] transform_card: class {k} has no card '{cardId}' — transform skipped.");
        return null;
    }

    // --- file-store paths -------------------------------------------------------------------------

    public static string ClassPath(int k) => $"{Root}/{k:00}.json";
    public static string ClassCardsDir(int k) => $"{Root}/{k:00}/cards";
    public static string ClassCardPath(int k, int n) => $"{ClassCardsDir(k)}/{n:00}.json";

    // --- loading ----------------------------------------------------------------------------------

    private static Dictionary<int, CharacterSpec> LoadClasses()
    {
        var result = new Dictionary<int, CharacterSpec>();
        try
        {
            if (!Godot.DirAccess.DirExistsAbsolute(Root))
            {
                Godot.DirAccess.MakeDirRecursiveAbsolute(Root);
                MainFile.Logger.Info($"[ForgedClass] created {Root}; no forged classes yet.");
                return result;
            }

            for (int k = 1; k <= ClassCount; k++)
            {
                if (!Godot.FileAccess.FileExists(ClassPath(k))) continue;
                using var file = Godot.FileAccess.Open(ClassPath(k), Godot.FileAccess.ModeFlags.Read);
                if (file == null)
                {
                    MainFile.Logger.Warn($"[ForgedClass] cannot open {ClassPath(k)}: {Godot.FileAccess.GetOpenError()}.");
                    continue;
                }
                if (TryParseClassJson(file.GetAsText(), k, out var spec, out var err) && spec != null)
                {
                    result[k] = spec;
                    MainFile.Logger.Info($"[ForgedClass] class {k:00} <- '{spec.Name}' (HP {spec.MaxHp}, deck {spec.StartingDeck.Length} entries).");
                }
                else
                {
                    MainFile.Logger.Warn($"[ForgedClass] class {k:00} rejected: {err}");
                }
            }
        }
        catch (Exception e)
        {
            MainFile.Logger.Error($"[ForgedClass] class load failed: {e}");
        }
        MainFile.Logger.Info($"[ForgedClass] loaded {result.Count} forged class(es).");
        return result;
    }

    private static Dictionary<(int, int), CardSpec> LoadCards()
    {
        var result = new Dictionary<(int, int), CardSpec>();
        for (int k = 1; k <= ClassCount; k++)
        {
            for (int n = 1; n <= CardsPerClass; n++)
            {
                if (!Godot.FileAccess.FileExists(ClassCardPath(k, n))) continue;
                using var file = Godot.FileAccess.Open(ClassCardPath(k, n), Godot.FileAccess.ModeFlags.Read);
                if (file == null) continue;
                if (ForgedCards.TryParseCardJson(file.GetAsText(), n, out var spec, out var err, allowBasic: true, allowCustomOrbs: true) && spec != null)
                {
                    result[(k, n)] = spec;
                    MainFile.Logger.Info($"[ForgedClass] class {k:00} card {n:00} <- '{spec.Title}'.");
                }
                else
                {
                    MainFile.Logger.Warn($"[ForgedClass] class {k:00} card {n:00} rejected: {err}");
                }
            }
        }
        return result;
    }

    /// <summary>Parse a class JSON. Default pool hue is spread across the class slots when color is omitted.</summary>
    private static bool TryParseClassJson(string json, int k, out CharacterSpec? spec, out string error)
    {
        spec = null;
        var parser = new Godot.Json();
        if (parser.Parse(json) != Godot.Error.Ok)
        {
            error = $"invalid JSON (line {parser.GetErrorLine()}): {parser.GetErrorMessage()}";
            return false;
        }
        if (parser.Data.VariantType != Godot.Variant.Type.Dictionary)
        {
            error = "root is not a JSON object.";
            return false;
        }
        return TryValidateCharacterDict(parser.Data.AsGodotDictionary(), k, out spec, out error);
    }

    /// <summary>Validate a parsed character object (shared by the startup loader and the bundle importer).</summary>
    private static bool TryValidateCharacterDict(Godot.Collections.Dictionary d, int k, out CharacterSpec? spec, out string error)
    {
        spec = null;
        string name = Str(d, "name", $"Forged Class {k:00}");
        string desc = d.ContainsKey("description") ? Str(d, "description") : Str(d, "text");
        int maxHp = Int(d, "max_hp", 70);
        int maxEnergy = Int(d, "max_energy", 3);
        if (maxHp < 1 || maxHp > 999) { error = $"max_hp {maxHp} out of range (1..999)."; return false; }
        if (maxEnergy < 1 || maxEnergy > 10) { error = $"max_energy {maxEnergy} out of range (1..10)."; return false; }

        var deck = new List<(int, int)>();
        if (d.ContainsKey("starting_deck") && d["starting_deck"].VariantType == Godot.Variant.Type.Array)
        {
            foreach (var item in d["starting_deck"].AsGodotArray())
            {
                if (item.VariantType != Godot.Variant.Type.Dictionary) continue;
                var e = item.AsGodotDictionary();
                int slot = Int(e, "slot");
                int count = Int(e, "count", 1);
                if (slot < 1 || slot > CardsPerClass)
                { error = $"starting_deck slot {slot} out of range (1..{CardsPerClass})."; return false; }
                if (count >= 1) deck.Add((slot, count));
            }
        }

        // Pool color: explicit {h,s,v} or a distinct default hue per class slot.
        float h = (k - 1) / (float)ClassCount, s = 0.8f, v = 1f;
        if (d.ContainsKey("color") && d["color"].VariantType == Godot.Variant.Type.Dictionary)
        {
            var c = d["color"].AsGodotDictionary();
            h = Flt(c, "h", h); s = Flt(c, "s", s); v = Flt(c, "v", v);
        }

        // Orb class (Phase G): starting orb slots become an override of CharacterModel.BaseOrbSlotCount.
        int orbSlots = Int(d, "orb_slots", 0);
        if (orbSlots < 0 || orbSlots > 10) { error = $"orb_slots {orbSlots} out of range (0..10)."; return false; }

        // Forged-orb pool (Phase I): the ordered base/custom orb list this class channels by name.
        OrbPoolEntry[] orbPool = [];
        if (d.ContainsKey("orb_pool") && d["orb_pool"].VariantType == Godot.Variant.Type.Array)
        {
            if (!TryParseOrbPool(d["orb_pool"].AsGodotArray(), k, out orbPool, out error)) return false;
        }
        if (orbPool.Length > 0 && orbSlots < 1)
        { error = "a class with an orb_pool needs orb_slots >= 1 (otherwise it has nowhere to channel)."; return false; }

        // Forged-status pool (Phase J): the ≤4 custom statuses this class's cards can apply by name.
        StatusSpec[] statusPool = [];
        if (d.ContainsKey("status_pool") && d["status_pool"].VariantType == Godot.Variant.Type.Array)
        {
            if (!TryParseStatusPool(d["status_pool"].AsGodotArray(), out statusPool, out error)) return false;
        }

        // Forged-summon pool (Phase K): the ≤MaxSummons minions this class's cards can summon by name.
        SummonSpec[] summonPool = [];
        if (d.ContainsKey("summon_pool") && d["summon_pool"].VariantType == Godot.Variant.Type.Array)
        {
            if (!TryParseSummonPool(d["summon_pool"].AsGodotArray(), out summonPool, out error)) return false;
        }

        // Forged relic (Phase L): the class's single custom starting relic (else it defaults to Burning Blood).
        RelicSpec? relicSpec = null;
        if (d.ContainsKey("relic") && d["relic"].VariantType == Godot.Variant.Type.Dictionary)
        {
            if (!TryParseRelic(d["relic"].AsGodotDictionary(), out relicSpec, out error)) return false;
        }

        // Forged potion (Phase BA, v55): the class's own potion, added to (not replacing) the base drop table.
        // Parsed AFTER the orb/status/summon pools so a potion effect can be checked against the class's own
        // content — apply_status_custom / channel_orb / summon are rejected unless that pool exists.
        PotionSpec[] potionPool = [];
        if (d.ContainsKey("potion_pool") && d["potion_pool"].VariantType == Godot.Variant.Type.Array)
        {
            if (!TryParsePotionPool(d["potion_pool"].AsGodotArray(), orbPool, statusPool, summonPool,
                                    out potionPool, out error)) return false;
        }

        // Run-persistent Forge (Phase AY, v54): opt-in per class. A forge class with this set banks its Forge at
        // combat end and gets it back (capped) at the start of its next combat — see ForgePersist. Absent => false,
        // so every pre-v54 class keeps the per-combat counter.
        bool forgePersist = Bool(d, "forge_persist", false);

        spec = new CharacterSpec(name, desc, maxHp, maxEnergy, deck.ToArray(), h, s, v, OrbSlots: orbSlots)
            { OrbPool = orbPool, StatusPool = statusPool, SummonPool = summonPool, Relic = relicSpec,
              ForgePersist = forgePersist, PotionPool = potionPool };
        error = "";
        return true;
    }

    // --- Phase J: status pool parsing + validation + resolvers --------------------------------------

    /// <summary>The max custom statuses a single class may forge (keep in sync with slotgen STATUSES_PER_CLASS).</summary>
    public const int MaxCustomStatuses = 4;

    /// <summary>The hooks a forged status may bind to: the J-1 Modify* additive set, plus (Phase AQ, v47)
    /// <c>damage_over_time</c> (a Poison-shaped debuff tick at the afflicted enemy's turn start) and <c>hit_count</c>
    /// (a buff: +stacks hits on the owner's card attacks — the J-1 cut is lifted because <c>AttackCommand.Attacker</c>
    /// is a public accessor, so the hook gates on the attacker cleanly). Reactive After* hooks stay with add_trigger.</summary>
    private static readonly HashSet<string> StatusHooks =
        ["damage_dealt", "damage_taken", "block_gained", "energy_gain", "card_draw", "damage_over_time", "hit_count"];

    private static readonly HashSet<string> StatusDecays = ["none", "lose_one_eot", "lose_all_eot"];
    /// <summary>Modifier modes. <c>multiplicative</c> (Phase AQ) is legal on the two damage hooks only: the status
    /// multiplies powered-attack damage by (1 + 0.1·stacks), capped at ×2 (<see cref="Powers.ForgedStatusPower"/>).</summary>
    private static readonly HashSet<string> StatusModes = ["additive", "multiplicative"];
    private static readonly HashSet<string> MultiplicativeHooks = ["damage_dealt", "damage_taken"];
    /// <summary>Hooks whose stacks would be degenerate as a permanent counter (an endless burn / a permanent extra hit):
    /// they must declare a decay (lose_one_eot / lose_all_eot). Mirrored in class_forge._validate_status_pool.</summary>
    private static readonly HashSet<string> MustDecayHooks = ["damage_over_time", "hit_count"];

    private static bool TryParseStatusPool(Godot.Collections.Array arr, out StatusSpec[] pool, out string error)
    {
        pool = [];
        var entries = new List<StatusSpec>();
        var seen = new HashSet<string>();
        foreach (var item in arr)
        {
            if (item.VariantType != Godot.Variant.Type.Dictionary)
            { error = "status_pool entries must be objects."; return false; }
            if (entries.Count >= MaxCustomStatuses)
            { error = $"status_pool has more than {MaxCustomStatuses} custom statuses."; return false; }
            if (!TryParseStatus(item.AsGodotDictionary(), entries.Count + 1, out var spec, out error)) return false;
            string key = spec!.Name.Trim().ToLowerInvariant();
            if (key.Length == 0) { error = "a custom status needs a non-empty name."; return false; }
            if (!seen.Add(key)) { error = $"status_pool has duplicate status name '{key}'."; return false; }
            entries.Add(spec);
        }
        pool = entries.ToArray();
        error = "";
        return true;
    }

    private static bool TryParseStatus(Godot.Collections.Dictionary d, int index, out StatusSpec? spec, out string error)
    {
        spec = null;
        string name = Str(d, "name", $"Status {index}").Trim();
        string emoji = Str(d, "emoji").Trim();
        string desc = d.ContainsKey("description") ? Str(d, "description") : Str(d, "text");

        string type = (d.ContainsKey("type") ? Str(d, "type") : "buff").Trim().ToLowerInvariant();
        if (type != "buff" && type != "debuff") { error = $"status '{name}': type must be buff/debuff (got '{type}')."; return false; }
        bool isBuff = type == "buff";

        string stack = (d.ContainsKey("stack") ? Str(d, "stack") : "counter").Trim().ToLowerInvariant();
        if (stack != "counter" && stack != "single") { error = $"status '{name}': stack must be counter/single (got '{stack}')."; return false; }

        string decay = (d.ContainsKey("decay") ? Str(d, "decay") : "none").Trim().ToLowerInvariant();
        if (!StatusDecays.Contains(decay)) { error = $"status '{name}': decay must be one of {string.Join("/", StatusDecays)} (got '{decay}')."; return false; }

        string hook = Str(d, "hook").Trim().ToLowerInvariant();
        if (!StatusHooks.Contains(hook)) { error = $"status '{name}': hook must be one of {string.Join("/", StatusHooks)} (got '{hook}')."; return false; }

        string mode = (d.ContainsKey("mode") ? Str(d, "mode") : "additive").Trim().ToLowerInvariant();
        if (!StatusModes.Contains(mode)) { error = $"status '{name}': mode must be one of {string.Join("/", StatusModes)} (got '{mode}')."; return false; }
        // Phase AQ: multiplicative scaling is a damage-pipeline concept (Hook.ModifyDamageMultiplicative); the
        // block/energy/draw/DoT/hit-count hooks have no multiplicative reading.
        if (mode == "multiplicative" && !MultiplicativeHooks.Contains(hook))
        { error = $"status '{name}': mode multiplicative is only valid on {string.Join("/", MultiplicativeHooks)} (got hook '{hook}')."; return false; }

        // damage_dealt only makes sense as a buff (it boosts the owner's attacks); damage_taken as a debuff
        // (it makes the afflicted enemy take more). Block/energy/draw are owner-only → buffs.
        if (hook == "damage_dealt" && !isBuff) { error = $"status '{name}': damage_dealt must be a buff."; return false; }
        if (hook is "block_gained" or "energy_gain" or "card_draw" && !isBuff) { error = $"status '{name}': {hook} must be a buff (it changes your own numbers)."; return false; }
        if (hook == "damage_taken" && isBuff) { error = $"status '{name}': damage_taken should be a debuff (it makes the afflicted creature take more damage)."; return false; }
        // Phase AQ: a DoT lands on the enemy (debuff); an extra-hit stance is yours (buff); both must burn out.
        if (hook == "damage_over_time" && isBuff) { error = $"status '{name}': damage_over_time must be a debuff (the afflicted enemy loses HP at its turn start)."; return false; }
        if (hook == "hit_count" && !isBuff) { error = $"status '{name}': hit_count must be a buff (it adds hits to your own attacks)."; return false; }
        if (MustDecayHooks.Contains(hook) && decay == "none")
        { error = $"status '{name}': {hook} must decay (lose_one_eot or lose_all_eot) — a permanent {hook} is degenerate."; return false; }

        spec = new StatusSpec(name, emoji, desc, isBuff, stack == "single", decay, hook, mode);
        error = "";
        return true;
    }

    /// <summary>True if class <paramref name="k"/> declares a forged-status pool (so its cards may apply by name).</summary>
    public static bool IsStatusClass(int k) => SpecForClass(k).StatusPool.Length > 0;

    /// <summary>The custom <see cref="StatusSpec"/> for class <paramref name="k"/> status slot <paramref name="m"/>
    /// (1-based), or null (an unfilled <c>ForgedClassKStatusM</c> shell).</summary>
    public static StatusSpec? StatusSpecFor(int k, int m)
    {
        var pool = SpecForClass(k).StatusPool;
        return m >= 1 && m <= pool.Length ? pool[m - 1] : null;
    }

    /// <summary>Resolve a status name to the canonical registered <c>ForgedStatusPower</c> instance for class
    /// <paramref name="k"/> (whose <c>ApplyStacks</c> applies the right compiled type), or null if unknown.</summary>
    public static Powers.ForgedStatusPower? ResolveStatusInstance(int k, string? name)
    {
        if (string.IsNullOrEmpty(name)) return null;
        string n = name.Trim().ToLowerInvariant();
        var pool = SpecForClass(k).StatusPool;
        for (int m = 1; m <= pool.Length; m++)
            if (pool[m - 1].Name.Trim().ToLowerInvariant() == n) return Powers.ForgedStatusPower.ForKey(k, m);
        return null;
    }

    // --- Phase L: forged relic parsing + validation + resolvers -------------------------------------

    /// <summary>The max relics a single class may declare (keep in sync with slotgen RELICS_PER_CLASS) — one, the
    /// class's single starting relic.</summary>
    public const int MaxRelics = 1;

    /// <summary>Relic-hook triggers v1 supports — turn hooks hand the relic a (ctx, player) (see RelicRunner). A
    /// "combat start" effect is a turn_start hook with once_per_combat (L-0: BeforeCombatStart passes no ctx).
    /// L-3 adds the reactive <c>attacked</c> (enemy damages you; AfterDamageReceived), <c>on_exhaust</c> (one of your
    /// cards is Exhausted; AfterCardExhausted), and <c>on_card_played</c> (you play a card; AfterCardPlayed). L-4 adds
    /// <c>combat_end</c> (AfterCombatVictory — heal-only), <c>on_card_drawn</c> (AfterCardDrawn),
    /// <c>on_damage_dealt</c> (AfterDamageGiven; your card attacks — and, Phase AT (v50), your pet's summon_attack hits),
    /// <c>on_block_gained</c> (AfterBlockGained).
    /// Phase P adds <c>on_hp_lost</c> (AfterDamageReceived; your own unblocked, self/card-caused HP loss — the
    /// relic twin of the v17 card-side trigger).</summary>
    private static readonly HashSet<string> RelicTriggers =
        ["turn_start", "turn_end", "attacked", "on_exhaust", "on_card_played",
         "combat_end", "on_card_drawn", "on_damage_dealt", "on_block_gained",
         "on_hp_lost"]; // Phase P (gap #9 relic mirror): your own unblocked, self/card-caused HP loss
    /// <summary>Effect ops a relic hook may run with no card (see <see cref="EffectRunner.RunRelicEffects"/>).
    /// Phase L compose: <c>channel_orb</c>/<c>summon</c> are accepted syntactically but are CLASS-CONDITIONAL — they
    /// no-op at runtime unless the class declares orbs / summons (the generator gates them on class content).</summary>
    private static readonly HashSet<string> RelicEffectOps =
        ["damage", "block", "draw", "gain_energy", "heal", "lose_hp", "apply_status", "channel_orb", "summon",
         "forge", // Phase M (gap #36): relic-side Forge income (the "smoldering heirloom" keystone)
         "cost_shift", // Phase AO (v45): a this-turn card-type discount ("at turn start, your first card costs 1 less")
         "discard"]; // Phase AS (v48): discard N random cards from hand (1..2) — a DRAWBACK op (the price of a boon)
    /// <summary>Phase AS (v48): the <c>card_type</c> filter values an <c>on_card_played</c> hook may carry.</summary>
    private static readonly HashSet<string> RelicCardTypes = ["attack", "skill", "power"];
    /// <summary>Phase AS (v48): <c>every_n</c> bounds (a counter relic fires on every Nth occurrence).</summary>
    public const int MinEveryN = 2, MaxEveryN = 9;
    /// <summary><c>attacker</c> (the creature that just hit you) is valid only on the <c>attacked</c> trigger.</summary>
    private static readonly HashSet<string> RelicTargets = ["self", "enemy", "all_enemies", "attacker"];
    /// <summary>Fire-time condition kinds valid with NO target (target_has_status / orb conditions forbidden here).
    /// L-4 adds the player-state reads has_block / enemy_count_ge / turn_at_least / hand_size_ge.</summary>
    private static readonly HashSet<string> RelicConditionKinds =
        ["hp_below_half", "no_block", "has_block", "enemy_count_ge", "turn_at_least", "hand_size_ge"];
    private static readonly HashSet<string> RelicModifierStats =
        ["max_energy", "first_attack", "cost_reduction", "start_combat_block",
         "attack_base", "max_hp"]; // Phase AS (v48): +N every card attack; ±N Max HP once on obtain (negative = the drawback)

    /// <summary>The forged <see cref="RelicSpec"/> for class <paramref name="k"/>, or null if it has no relic.</summary>
    public static RelicSpec? RelicSpecFor(int k) => SpecForClass(k).Relic;

    /// <summary>True if class <paramref name="k"/> declares a forged relic (so the slot equips it instead of the
    /// default Burning Blood).</summary>
    public static bool HasForgedRelic(int k) => SpecForClass(k).Relic != null;

    /// <summary>Phase AY (v54): true if class <paramref name="k"/> keeps its Forge between combats (the opt-in
    /// <c>forge_persist</c> flag). Read by <see cref="ForgePersist"/> at the bank/restore sites.</summary>
    public static bool IsForgePersistClass(int k) => SpecForClass(k).ForgePersist;

    /// <summary>Phase AY (v54): true if <paramref name="player"/> is playing a run-persistent-Forge class. Null /
    /// a non-forged character (a base-game class in the same run) => false.</summary>
    public static bool IsForgePersistPlayer(Player? player)
    {
        int k = ClassIndexOfPlayer(player);
        return k >= 1 && k <= ClassCount && IsForgePersistClass(k);
    }

    private static bool TryParseRelic(Godot.Collections.Dictionary d, out RelicSpec? spec, out string error)
    {
        spec = null;
        string name = Str(d, "name", "Forged Relic").Trim();
        if (name.Length == 0) { error = "relic needs a non-empty name."; return false; }
        string id = Str(d, "id", name.ToLowerInvariant().Replace(' ', '_'));
        string desc = d.ContainsKey("description") ? Str(d, "description") : Str(d, "text");
        string tier = (d.ContainsKey("tier") ? Str(d, "tier") : "starter").Trim().ToLowerInvariant();

        var hooks = new List<RelicHook>();
        if (d.ContainsKey("hooks") && d["hooks"].VariantType == Godot.Variant.Type.Array)
        {
            foreach (var item in d["hooks"].AsGodotArray())
            {
                if (item.VariantType != Godot.Variant.Type.Dictionary)
                { error = "relic 'hooks' entries must be objects."; return false; }
                if (!TryParseRelicHook(item.AsGodotDictionary(), out var hook, out error)) return false;
                hooks.Add(hook!);
            }
        }

        var mods = new List<RelicModifier>();
        if (d.ContainsKey("modifiers") && d["modifiers"].VariantType == Godot.Variant.Type.Array)
        {
            foreach (var item in d["modifiers"].AsGodotArray())
            {
                if (item.VariantType != Godot.Variant.Type.Dictionary)
                { error = "relic 'modifiers' entries must be objects."; return false; }
                var m = item.AsGodotDictionary();
                string stat = Str(m, "stat").Trim().ToLowerInvariant();
                if (!RelicModifierStats.Contains(stat))
                { error = $"relic modifier stat '{stat}' is not supported (v1: {string.Join("/", RelicModifierStats)})."; return false; }
                int mamt = Int(m, "amount");
                if (mamt == 0) { error = $"relic modifier '{stat}' needs a non-zero amount."; return false; }
                // Phase AS (v48): max_hp is the ONLY signed modifier (a negative Max HP is the sanctioned drawback); every
                // other stat is a bonus. Bounds keep an import from bricking a run (a -80 max_hp starter dies on floor 1).
                if (stat != "max_hp" && mamt < 0)
                { error = $"relic modifier '{stat}' must be positive (only max_hp may be negative)."; return false; }
                if (stat == "max_hp" && System.Math.Abs(mamt) > 30)
                { error = "relic modifier 'max_hp' must be within -30..30."; return false; }
                if (stat == "attack_base" && mamt > 5)
                { error = "relic modifier 'attack_base' must be 1..5 (it is always-on Strength)."; return false; }
                mods.Add(new RelicModifier(stat, mamt));
            }
        }

        if (hooks.Count == 0 && mods.Count == 0)
        { error = "relic has no hooks and no modifiers (it would do nothing)."; return false; }

        spec = new RelicSpec(id, name, desc, tier, hooks.ToArray(), mods.ToArray());
        error = "";
        return true;
    }

    private static bool TryParseRelicHook(Godot.Collections.Dictionary d, out RelicHook? hook, out string error)
    {
        hook = null;
        string trigger = Str(d, "trigger").Trim().ToLowerInvariant();
        if (!RelicTriggers.Contains(trigger))
        { error = $"relic hook trigger '{trigger}' is not supported (v1: {string.Join("/", RelicTriggers)})."; return false; }
        if (!d.ContainsKey("effects") || d["effects"].VariantType != Godot.Variant.Type.Array)
        { error = $"relic hook ({trigger}) needs an 'effects' array."; return false; }

        string target = (d.ContainsKey("target") ? Str(d, "target") : "self").Trim().ToLowerInvariant();
        if (!RelicTargets.Contains(target))
        { error = $"relic hook target '{target}' must be self/enemy/all_enemies/attacker."; return false; }
        if (target == "attacker" && trigger != "attacked")
        { error = "relic hook target 'attacker' is only valid on the 'attacked' trigger."; return false; }

        // Phase AS (v48): the card-type filter (on_card_played only) + the every_n counter (any trigger but combat_end).
        string? cardType = null;
        if (d.ContainsKey("card_type"))
        {
            cardType = Str(d, "card_type").Trim().ToLowerInvariant();
            if (!RelicCardTypes.Contains(cardType))
            { error = $"relic hook card_type '{cardType}' must be attack/skill/power."; return false; }
            if (trigger != "on_card_played")
            { error = "relic hook 'card_type' is only valid on the 'on_card_played' trigger."; return false; }
        }
        int everyN = d.ContainsKey("every_n") ? Int(d, "every_n") : 0;
        if (everyN != 0 && (everyN < MinEveryN || everyN > MaxEveryN))
        { error = $"relic hook 'every_n' must be {MinEveryN}..{MaxEveryN} (a counter relic fires on every Nth occurrence)."; return false; }
        if (everyN != 0 && trigger == "combat_end")
        { error = "relic hook 'every_n' is meaningless on 'combat_end' (it fires once per combat)."; return false; }

        var effects = new List<EffectSpec>();
        foreach (var item in d["effects"].AsGodotArray())
        {
            if (item.VariantType != Godot.Variant.Type.Dictionary)
            { error = "relic 'effects' entries must be objects."; return false; }
            if (!TryParseRelicEffect(item.AsGodotDictionary(), target, out var eff, out error)) return false;
            effects.Add(eff!);
        }
        if (effects.Count == 0) { error = $"relic hook ({trigger}) has no effects."; return false; }
        // combat_end fires from AfterCombatVictory with no ctx and no live enemies → only ctx-free self heal is safe.
        if (trigger == "combat_end" && effects.Any(e => e.Op != "heal"))
        { error = "relic 'combat_end' hooks may only use the 'heal' effect (combat is over)."; return false; }

        Condition? when = null;
        if (d.ContainsKey("when") && d["when"].VariantType == Godot.Variant.Type.Dictionary)
            if (!TryParseRelicCondition(d["when"].AsGodotDictionary(), out when, out error)) return false;

        hook = new RelicHook(trigger, effects.ToArray(), when, target, Bool(d, "once_per_combat", false), cardType, everyN);
        error = "";
        return true;
    }

    private static bool TryParseRelicEffect(Godot.Collections.Dictionary d, string hookTarget, out EffectSpec? eff, out string error)
    {
        eff = null;
        string op = Str(d, "op").Trim().ToLowerInvariant();
        if (!RelicEffectOps.Contains(op))
        { error = $"relic effect op '{op}' is not supported (v1: {string.Join("/", RelicEffectOps)})."; return false; }
        int amount = Int(d, "amount", 1);
        string? status = null, orb = null, summonName = null;
        string? cardKind = null, scope = null; // Phase AO (v45): cost_shift fields
        int count = 0;
        if (op == "apply_status")
        {
            status = Str(d, "status").Trim().ToLowerInvariant();
            bool isBuff = EffectRunner.SelfBuffStatuses.Contains(status);
            bool isDebuff = SummonEnemyStatuses.Contains(status);
            if (!isBuff && !isDebuff) { error = $"relic apply_status: unsupported status '{status}'."; return false; }
            // Phase AS (v48): a debuff on a SELF-target hook is now legal — it lands on YOU (the "you gain 1 Weak" price of a
            // boon). poison on yourself is not (no self-poison fantasy; it would also fight the DoT status path).
            if (isDebuff && hookTarget == "self" && status == "poison")
            { error = "relic apply_status 'poison' needs an enemy target (a relic never poisons its owner)."; return false; }
        }
        else if (op == "discard")
        {
            // Phase AS (v48): a random hand discard (the drawback op). 1..2, random only (a relic never opens a picker).
            if (amount < 1 || amount > 2) { error = "relic 'discard' amount must be 1..2."; return false; }
            string cards = d.ContainsKey("cards") ? Str(d, "cards").Trim().ToLowerInvariant() : "random";
            if (cards != "random") { error = "relic 'discard' must be random ('cards':'choose' is card-only)."; return false; }
        }
        else if (op == "channel_orb")
        {
            orb = Str(d, "orb").Trim();   // "random" or a pool orb name (resolved per-class at runtime)
            if (orb.Length == 0) { error = "relic 'channel_orb' needs an 'orb' (\"random\" or a pool orb name)."; return false; }
        }
        else if (op == "summon")
        {
            summonName = Str(d, "summon_name").Trim();
            if (summonName.Length == 0) { error = "relic 'summon' needs a 'summon_name' (a class minion)."; return false; }
        }
        else if (op == "cost_shift")
        {
            // Phase AO (v45): the same shape rules as the card op, plus the hook-side this_turn-only rule.
            cardKind = d.ContainsKey("card_type") ? Str(d, "card_type").Trim().ToLowerInvariant() : null;
            scope = d.ContainsKey("scope") ? Str(d, "scope").Trim().ToLowerInvariant() : null;
            count = d.ContainsKey("count") ? Int(d, "count") : 0;
            var cserr = ForgedCards.ValidateCostShift(new EffectSpec(op, amount, CardKind: cardKind, Scope: scope, Count: count), relic: true);
            if (cserr != null) { error = "relic " + cserr; return false; }
        }
        else if (amount < 1) { error = $"relic effect '{op}' needs amount >= 1."; return false; }
        if (op == "damage" && hookTarget == "self")
        { error = "relic 'damage' needs an enemy target (set the hook 'target' to enemy/all_enemies)."; return false; }

        eff = new EffectSpec(op, amount, status, Orb: orb, SummonName: summonName,
                             CardKind: cardKind, Scope: scope, Count: count); // Phase AO (v45)
        error = "";
        return true;
    }

    private static bool TryParseRelicCondition(Godot.Collections.Dictionary d, out Condition? cond, out string error)
    {
        cond = null;
        string kind = Str(d, "kind").Trim().ToLowerInvariant();
        if (!RelicConditionKinds.Contains(kind))
        { error = $"relic hook 'when' kind '{kind}' is not supported (v1: {string.Join("/", RelicConditionKinds)})."; return false; }
        cond = new Condition(kind, Int(d, "value"), null, Bool(d, "negate", false));
        error = "";
        return true;
    }


    // --- Phase BA (v55): forged potion parsing + validation + resolvers -----------------------------

    /// <summary>The max potions a single class may declare (keep in sync with slotgen POTIONS_PER_CLASS) — one,
    /// the class's signature potion. It rides that class's OWN potion pool, which the game concatenates with the
    /// base game's SharedPotionPool at roll time (PotionFactory.GetPotionOptions), so it is an EXTRA entry in the
    /// drop table rather than a replacement.</summary>
    public const int MaxPotions = 1;

    /// <summary>The three drop tiers PotionFactory rolls (10% rare / 25% uncommon / 65% common, then a uniform
    /// pick inside the rolled tier). None/Event/Token are base-game-internal and stay out of the vocabulary.</summary>
    private static readonly HashSet<string> PotionRarities = ["common", "uncommon", "rare"];
    /// <summary><c>combat</c> => PotionUsage.CombatOnly, <c>any</c> => AnyTime. <c>Automatic</c> (a potion that
    /// fires itself) is a different fantasy and is out of scope for v1.</summary>
    private static readonly HashSet<string> PotionUsages = ["combat", "any"];
    private static readonly HashSet<string> PotionTargets = ["self", "enemy", "all_enemies"];
    /// <summary>Effect ops a potion may run. This is the RELIC sub-vocabulary (no card, a ctx + a target — see
    /// <see cref="EffectRunner.RunRelicEffects"/>) MINUS the relic drawback ops (a potion is a boon you choose to
    /// drink; <c>discard</c> as a price makes no sense) PLUS <c>apply_status_custom</c>, so a status class's potion
    /// can hand out its OWN signature status. The last four are CLASS-CONDITIONAL: rejected below unless the class
    /// actually declares the orb / summon / status content they reach for.</summary>
    private static readonly HashSet<string> PotionEffectOps =
        ["damage", "block", "draw", "gain_energy", "heal", "lose_hp", "apply_status",
         "apply_status_custom", "channel_orb", "summon", "forge"];

    /// <summary>The forged <see cref="PotionSpec"/> for class <paramref name="k"/> potion slot <paramref name="m"/>
    /// (1-based), or null (an unfilled <c>ForgedClassKKPotionM</c> shell — every pre-v55 class).</summary>
    public static PotionSpec? PotionSpecFor(int k, int m)
    {
        var pool = SpecForClass(k).PotionPool;
        return m >= 1 && m <= pool.Length ? pool[m - 1] : null;
    }

    /// <summary>True if class <paramref name="k"/> declares a forged potion (so its shell joins the drop table).</summary>
    public static bool HasForgedPotions(int k) => SpecForClass(k).PotionPool.Length > 0;

    private static bool TryParsePotionPool(Godot.Collections.Array arr, OrbPoolEntry[] orbPool,
                                           StatusSpec[] statusPool, SummonSpec[] summonPool,
                                           out PotionSpec[] pool, out string error)
    {
        pool = [];
        var entries = new List<PotionSpec>();
        var seen = new HashSet<string>();
        foreach (var item in arr)
        {
            if (item.VariantType != Godot.Variant.Type.Dictionary)
            { error = "potion_pool entries must be objects."; return false; }
            if (entries.Count >= MaxPotions)
            { error = $"potion_pool has more than {MaxPotions} potion(s)."; return false; }
            if (!TryParsePotion(item.AsGodotDictionary(), entries.Count + 1, orbPool, statusPool, summonPool,
                                out var spec, out error)) return false;
            string key = spec!.Name.Trim().ToLowerInvariant();
            if (key.Length == 0) { error = "a potion needs a non-empty name."; return false; }
            if (!seen.Add(key)) { error = $"potion_pool has duplicate potion name '{key}'."; return false; }
            entries.Add(spec);
        }
        pool = entries.ToArray();
        error = "";
        return true;
    }

    private static bool TryParsePotion(Godot.Collections.Dictionary d, int index, OrbPoolEntry[] orbPool,
                                       StatusSpec[] statusPool, SummonSpec[] summonPool,
                                       out PotionSpec? spec, out string error)
    {
        spec = null;
        string name = Str(d, "name", $"Potion {index}").Trim();
        if (name.Length == 0) { error = "a potion needs a non-empty name."; return false; }
        string id = Str(d, "id", name.ToLowerInvariant().Replace(' ', '_'));
        string emoji = Str(d, "emoji").Trim();
        string desc = d.ContainsKey("description") ? Str(d, "description") : Str(d, "text");

        string rarity = (d.ContainsKey("rarity") ? Str(d, "rarity") : "common").Trim().ToLowerInvariant();
        if (!PotionRarities.Contains(rarity))
        { error = $"potion '{name}': rarity must be one of {string.Join("/", PotionRarities)} (got '{rarity}')."; return false; }

        string usage = (d.ContainsKey("usage") ? Str(d, "usage") : "combat").Trim().ToLowerInvariant();
        if (!PotionUsages.Contains(usage))
        { error = $"potion '{name}': usage must be one of {string.Join("/", PotionUsages)} (got '{usage}')."; return false; }

        string target = (d.ContainsKey("target") ? Str(d, "target") : "self").Trim().ToLowerInvariant();
        if (!PotionTargets.Contains(target))
        { error = $"potion '{name}': target must be one of {string.Join("/", PotionTargets)} (got '{target}')."; return false; }

        if (!d.ContainsKey("effects") || d["effects"].VariantType != Godot.Variant.Type.Array)
        { error = $"potion '{name}' needs an 'effects' array."; return false; }

        var effects = new List<EffectSpec>();
        foreach (var item in d["effects"].AsGodotArray())
        {
            if (item.VariantType != Godot.Variant.Type.Dictionary)
            { error = $"potion '{name}': 'effects' entries must be objects."; return false; }
            if (!TryParsePotionEffect(item.AsGodotDictionary(), name, target, orbPool, statusPool, summonPool,
                                      out var eff, out error)) return false;
            effects.Add(eff!);
        }
        if (effects.Count == 0) { error = $"potion '{name}' has no effects (it would do nothing)."; return false; }

        // An out-of-combat potion ("any") must still work out of combat: every op except heal reads a live
        // CombatState (draw/energy/block/damage/statuses/orbs/summons). Keep `any` to the one op that works on the
        // map — the same reasoning as the relic combat_end rule.
        if (usage == "any" && effects.Any(e => e.Op != "heal"))
        { error = $"potion '{name}': usage 'any' may only use the 'heal' effect (everything else needs a combat)."; return false; }

        spec = new PotionSpec(id, name, desc, emoji, rarity, usage, target, effects.ToArray());
        error = "";
        return true;
    }

    private static bool TryParsePotionEffect(Godot.Collections.Dictionary d, string potion, string target,
                                             OrbPoolEntry[] orbPool, StatusSpec[] statusPool, SummonSpec[] summonPool,
                                             out EffectSpec? eff, out string error)
    {
        eff = null;
        string op = Str(d, "op").Trim().ToLowerInvariant();
        if (!PotionEffectOps.Contains(op))
        { error = $"potion '{potion}': effect op '{op}' is not supported (v1: {string.Join("/", PotionEffectOps)})."; return false; }
        int amount = Int(d, "amount", 1);
        if (amount < 1) { error = $"potion '{potion}': effect '{op}' needs amount >= 1."; return false; }

        string? status = null, statusName = null, orb = null, summonName = null;
        if (op == "damage" && target == "self")
        { error = $"potion '{potion}': 'damage' needs an enemy target (set the potion 'target' to enemy/all_enemies)."; return false; }

        if (op == "apply_status")
        {
            status = Str(d, "status").Trim().ToLowerInvariant();
            bool isBuff = EffectRunner.SelfBuffStatuses.Contains(status);
            bool isDebuff = SummonEnemyStatuses.Contains(status);
            if (!isBuff && !isDebuff) { error = $"potion '{potion}': apply_status: unsupported status '{status}'."; return false; }
            // A potion is a boon you CHOOSE to drink, so (unlike a relic hook) it never carries a self-debuff price:
            // a buff belongs on a self potion, a debuff on a targeted one.
            if (isBuff && target != "self")
            { error = $"potion '{potion}': buff '{status}' belongs on a self-target potion (a buff always lands on you)."; return false; }
            if (isDebuff && target == "self")
            { error = $"potion '{potion}': debuff '{status}' needs an enemy target (a potion never debuffs its drinker)."; return false; }
        }
        else if (op == "apply_status_custom")
        {
            statusName = Str(d, "status_name").Trim();
            if (statusName.Length == 0) { error = $"potion '{potion}': 'apply_status_custom' needs a 'status_name'."; return false; }
            if (statusPool.Length == 0)
            { error = $"potion '{potion}': 'apply_status_custom' is status-class only (this class declares no status_pool)."; return false; }
            var st = statusPool.FirstOrDefault(s => s.Name.Trim().ToLowerInvariant() == statusName.ToLowerInvariant());
            if (st == null)
            { error = $"potion '{potion}': status '{statusName}' is not in this class's status_pool."; return false; }
            if (st.IsBuff && target != "self")
            { error = $"potion '{potion}': custom buff '{statusName}' belongs on a self-target potion."; return false; }
            if (!st.IsBuff && target == "self")
            { error = $"potion '{potion}': custom debuff '{statusName}' needs an enemy target."; return false; }
        }
        else if (op == "channel_orb")
        {
            orb = Str(d, "orb").Trim();
            if (orb.Length == 0) { error = $"potion '{potion}': 'channel_orb' needs an 'orb' (\"random\" or a pool orb name)."; return false; }
            if (orbPool.Length == 0)
            { error = $"potion '{potion}': 'channel_orb' is orb-class only (this class declares no orb_pool)."; return false; }
        }
        else if (op == "summon")
        {
            summonName = Str(d, "summon_name").Trim();
            if (summonName.Length == 0) { error = $"potion '{potion}': 'summon' needs a 'summon_name' (a class minion)."; return false; }
            if (summonPool.Length == 0)
            { error = $"potion '{potion}': 'summon' is summon-class only (this class declares no summon_pool)."; return false; }
            if (!summonPool.Any(s => s.Name.Trim().ToLowerInvariant() == summonName.ToLowerInvariant()))
            { error = $"potion '{potion}': summon '{summonName}' is not in this class's summon_pool."; return false; }
        }

        eff = new EffectSpec(op, amount, status, StatusName: statusName, Orb: orb, SummonName: summonName);
        error = "";
        return true;
    }

    // --- Phase K: summon pool parsing + validation + resolvers --------------------------------------

    /// <summary>The max forged minions a single class may declare (keep in sync with slotgen SUMMONS_PER_CLASS).</summary>
    public const int MaxSummons = 2;

    /// <summary>The per-turn action sub-vocabulary a summon move may use (see <see cref="SummonRunner"/>).</summary>
    private static readonly HashSet<string> SummonOps = ["attack", "block", "apply_status", "heal_self"];
    private static readonly HashSet<string> SummonTargets = ["self", "enemy", "all_enemies"];
    private static readonly HashSet<string> SummonEnemyStatuses = ["vulnerable", "weak", "frail", "poison"];

    /// <summary>Phase AV (v52): the legal band for <c>on_nth_attack</c>'s <c>n</c> (1 would be "every hit" — that is
    /// what a move is for; past 5 the payoff never lands in a real fight). Mirrors class_forge._SUMMON_NTH_RANGE.</summary>
    private const int SummonNthMin = 2;
    private const int SummonNthMax = 5;

    private static bool TryParseSummonPool(Godot.Collections.Array arr, out SummonSpec[] pool, out string error)
    {
        pool = [];
        var entries = new List<SummonSpec>();
        var seen = new HashSet<string>();
        foreach (var item in arr)
        {
            if (item.VariantType != Godot.Variant.Type.Dictionary)
            { error = "summon_pool entries must be objects."; return false; }
            if (entries.Count >= MaxSummons)
            { error = $"summon_pool has more than {MaxSummons} summons."; return false; }
            if (!TryParseSummon(item.AsGodotDictionary(), entries.Count + 1, out var spec, out error)) return false;
            string key = spec!.Name.Trim().ToLowerInvariant();
            if (key.Length == 0) { error = "a summon needs a non-empty name."; return false; }
            if (!seen.Add(key)) { error = $"summon_pool has duplicate summon name '{key}'."; return false; }
            entries.Add(spec);
        }
        pool = entries.ToArray();
        error = "";
        return true;
    }

    private static bool TryParseSummon(Godot.Collections.Dictionary d, int index, out SummonSpec? spec, out string error)
    {
        spec = null;
        string name = Str(d, "name", $"Summon {index}").Trim();
        string desc = d.ContainsKey("description") ? Str(d, "description") : Str(d, "text");
        int maxHp = Int(d, "max_hp", 10);
        if (maxHp < 1 || maxHp > 999) { error = $"summon '{name}': max_hp {maxHp} out of range (1..999)."; return false; }
        if (!TryParseSummonMoves(d, $"summon '{name}'", out var moves, out error)) return false;
        // K-3a: an ethereal summon (attackable:false) is an untargetable striker — no HP bar, never meat-shields.
        bool attackable = Bool(d, "attackable", true);
        // K-3b: optional on_summon ("battle cry", full sub-vocab) + on_death ("death rattle", enemy-facing only).
        SummonAction[]? onSummon = null, onDeath = null;
        if (d.ContainsKey("on_summon") && d["on_summon"].VariantType == Godot.Variant.Type.Array)
        {
            if (!TryParseSummonActions(d["on_summon"].AsGodotArray(), $"summon '{name}' on_summon", out var os, out error)) return false;
            onSummon = os.Length > 0 ? os : null;
        }
        if (d.ContainsKey("on_death") && d["on_death"].VariantType == Godot.Variant.Type.Array)
        {
            if (!TryParseSummonActions(d["on_death"].AsGodotArray(), $"summon '{name}' on_death", out var od, out error, enemyFacingOnly: true)) return false;
            onDeath = od.Length > 0 ? od : null;
        }
        // Phase AV (v52): optional on_nth_attack — { "n": 2..5, "actions": [...] }: every Nth hit this minion DEALS
        // runs the payload (full sub-vocab, the minion is the actor). Driven by ForgedSummonPower.AfterDamageGiven.
        SummonNthAttack? onNth = null;
        if (d.ContainsKey("on_nth_attack") && d["on_nth_attack"].VariantType == Godot.Variant.Type.Dictionary)
        {
            var nd = d["on_nth_attack"].AsGodotDictionary();
            int n = Int(nd, "n", 0);
            if (n < SummonNthMin || n > SummonNthMax)
            { error = $"summon '{name}' on_nth_attack: 'n' {n} out of range ({SummonNthMin}..{SummonNthMax})."; return false; }
            var nActs = nd.ContainsKey("actions") ? nd["actions"].AsGodotArray() : [];
            if (!TryParseSummonActions(nActs, $"summon '{name}' on_nth_attack", out var na, out error)) return false;
            if (na.Length == 0) { error = $"summon '{name}' on_nth_attack: needs at least one action."; return false; }
            onNth = new SummonNthAttack(n, na);
        }
        spec = new SummonSpec(name, desc, maxHp, moves, attackable, onSummon, onDeath, onNth);
        error = "";
        return true;
    }

    /// <summary>A summon's move cycle: a <c>moves</c> array (each <c>{ "actions": [...] }</c>) OR a single
    /// top-level <c>actions</c> array (one move, repeated every turn).</summary>
    private static bool TryParseSummonMoves(Godot.Collections.Dictionary d, string where, out SummonMove[] moves, out string error)
    {
        moves = [];
        var list = new List<SummonMove>();
        if (d.ContainsKey("moves") && d["moves"].VariantType == Godot.Variant.Type.Array)
        {
            foreach (var item in d["moves"].AsGodotArray())
            {
                if (item.VariantType != Godot.Variant.Type.Dictionary)
                { error = $"{where}: each move must be an object with an 'actions' list."; return false; }
                var mv = item.AsGodotDictionary();
                var actArr = mv.ContainsKey("actions") ? mv["actions"].AsGodotArray() : [];
                if (!TryParseSummonActions(actArr, where, out var acts, out error)) return false;
                if (acts.Length == 0) { error = $"{where}: a move needs at least one action."; return false; }
                list.Add(new SummonMove(acts));
            }
        }
        else if (d.ContainsKey("actions") && d["actions"].VariantType == Godot.Variant.Type.Array)
        {
            if (!TryParseSummonActions(d["actions"].AsGodotArray(), where, out var acts, out error)) return false;
            if (acts.Length == 0) { error = $"{where}: needs at least one action."; return false; }
            list.Add(new SummonMove(acts));
        }
        // True-Osty (v15): a PASSIVE summon (no moves/actions) is allowed — it does nothing on its own turn; the
        // class's summon_attack cards strike through it. Empty list ⇒ empty Moves ⇒ ForgedSummonPower.AfterSideTurnEnd
        // no-ops. Phase AV (v52): the K-3 autonomous move cycle is LIVE again — a class may opt ONE pool entry into
        // `moves`/`actions` (the generator gates that; the engine happily runs either shape).
        moves = list.ToArray();
        error = "";
        return true;
    }

    private static bool TryParseSummonActions(Godot.Collections.Array arr, string where, out SummonAction[] actions, out string error,
                                              bool enemyFacingOnly = false)
    {
        actions = [];
        var list = new List<SummonAction>(arr.Count);
        foreach (var item in arr)
        {
            if (item.VariantType != Godot.Variant.Type.Dictionary)
            { error = $"{where}: each action must be an object."; return false; }
            var a = item.AsGodotDictionary();
            string op = Str(a, "op").Trim().ToLowerInvariant();
            if (!SummonOps.Contains(op))
            { error = $"{where}: action op '{op}' is not one of {string.Join("/", SummonOps)}."; return false; }
            // K-3b: a death rattle is dealt by the player after the minion is gone, so only enemy-facing actions
            // make sense there (no block / heal_self / self-buff on a dead minion).
            if (enemyFacingOnly && (op == "block" || op == "heal_self"))
            { error = $"{where}: '{op}' can't run on death (the minion is gone) — use attack or a debuff."; return false; }

            int amount = Int(a, "amount");
            int hits = a.ContainsKey("hits") ? Int(a, "hits", 1) : 1;
            string? status = a.ContainsKey("status") ? Str(a, "status").Trim().ToLowerInvariant() : null;
            string target = a.ContainsKey("target") ? Str(a, "target").Trim().ToLowerInvariant() : "";

            if (target.Length > 0 && !SummonTargets.Contains(target))
            { error = $"{where}: target '{target}' is not one of {string.Join("/", SummonTargets)}."; return false; }
            if (amount < 1) { error = $"{where}: action '{op}' needs amount >= 1."; return false; }
            if (hits < 1) { error = $"{where}: hits must be >= 1."; return false; }
            if (hits > 1 && op != "attack") { error = $"{where}: 'hits' only applies to attack."; return false; }

            switch (op)
            {
                case "attack":
                    if (target.Length == 0) target = "enemy";
                    if (target == "self") { error = $"{where}: attack can't target self."; return false; }
                    break;
                case "block":
                case "heal_self":
                    if (target.Length == 0) target = "self";
                    if (target != "self") { error = $"{where}: '{op}' runs on the minion (target must be self)."; return false; }
                    break;
                case "apply_status":
                    bool selfBuff = EffectRunner.SelfBuffStatuses.Contains(status ?? "");
                    if (status == null || !(selfBuff || SummonEnemyStatuses.Contains(status)))
                    { error = $"{where}: unsupported status '{status}'."; return false; }
                    if (enemyFacingOnly && selfBuff)
                    { error = $"{where}: self-buff '{status}' can't run on death (the minion is gone) — use a debuff."; return false; }
                    if (selfBuff) { if (target.Length == 0) target = "self"; if (target != "self") { error = $"{where}: self-buff '{status}' must target self (the minion)."; return false; } }
                    else { if (target.Length == 0) target = "enemy"; if (target == "self") { error = $"{where}: debuff '{status}' can't target self."; return false; } }
                    break;
            }
            if (op != "apply_status" && status != null)
            { error = $"{where}: 'status' only applies to apply_status (op '{op}')."; return false; }

            list.Add(new SummonAction(op, amount, hits, status, target));
        }
        actions = list.ToArray();
        error = "";
        return true;
    }

    /// <summary>True if class <paramref name="k"/> declares a summon pool (so its cards may summon by name).</summary>
    public static bool IsSummonClass(int k) => SpecForClass(k).SummonPool.Length > 0;

    /// <summary>The <see cref="SummonSpec"/> for class <paramref name="k"/> summon slot <paramref name="m"/>
    /// (1-based), or null (an unfilled <c>ForgedClassKSummonM</c> shell).</summary>
    public static SummonSpec? SummonSpecFor(int k, int m)
    {
        var pool = SpecForClass(k).SummonPool;
        return m >= 1 && m <= pool.Length ? pool[m - 1] : null;
    }

    /// <summary>Map a summon name to its compiled <c>ForgedClassKSummonM</c> Type for class <paramref name="k"/>,
    /// or null if the name isn't in the class's pool.</summary>
    public static System.Type? ResolveSummonType(int k, string? name)
    {
        if (string.IsNullOrEmpty(name)) return null;
        string n = name.Trim().ToLowerInvariant();
        var pool = SpecForClass(k).SummonPool;
        for (int m = 1; m <= pool.Length; m++)
            if (pool[m - 1].Name.Trim().ToLowerInvariant() == n) return Powers.ForgedSummon.TypeForKey(k, m);
        return null;
    }

    // --- Phase I: orb pool parsing + validation ----------------------------------------------------

    /// <summary>Base orbs a class pool may reference by name (the stock STS2 orbs we map in EffectRunner).</summary>
    private static readonly HashSet<string> BaseOrbs = ["lightning", "frost", "dark"];

    /// <summary>The op sub-vocabulary an orb effect (passive/evoke) may use. Single-target damage and enemy
    /// debuffs ARE allowed (an orb has a target, unlike a turn-trigger); the rest run on the player.</summary>
    private static readonly HashSet<string> OrbOps =
        ["damage", "block", "apply_status", "draw", "gain_energy", "heal", "gain_orb_slot", "channel_orb"];

    private static readonly HashSet<string> OrbEnemyStatuses = ["vulnerable", "weak", "frail", "poison"];
    private static readonly HashSet<string> OrbTargets = ["self", "enemy", "all_enemies"];

    /// <summary>Phase AR (v49): when a custom orb's passive list ticks. <c>turn_end</c> = the game's
    /// <c>BeforeTurnEndOrbTrigger</c> (Lightning/Frost/Glass; the default); <c>turn_start</c> = its
    /// <c>AfterTurnStartOrbTrigger</c> (Plasma). Mirrors class_forge._ORB_PASSIVE_TIMINGS.</summary>
    public static readonly HashSet<string> OrbPassiveTimings = ["turn_end", "turn_start"];

    /// <summary>Phase AR (v49): passive ops that are DEAD at turn end (energy gained there evaporates; cards drawn
    /// there are discarded) — a passive carrying one of these must declare <c>passive_timing: turn_start</c>.
    /// Mirrors class_forge._ORB_TURN_START_ONLY_OPS.</summary>
    public static readonly HashSet<string> OrbTurnStartOnlyOps = ["gain_energy", "draw"];

    /// <summary>Phase AR (v49): condition kinds an orb effect's <c>when</c> may NOT use — an orb fires with no card
    /// and no chosen target (the passive's supplied Creature is null on our tick; an evoke enumerates the board),
    /// so the card-instance read and every chosen-target read are meaningless there — the same rule a trigger's
    /// fire-time gate follows (<see cref="ForgedCards"/>.ValidateTrigger). Every other <see cref="Conditions.Kinds"/>
    /// entry is legal (orbs_match / orb_count_ge included: "if you have 3+ orbs, shatter for 12").
    /// Mirrors class_forge._ORB_FORBIDDEN_CONDITION_KINDS.</summary>
    public static readonly HashSet<string> OrbForbiddenConditionKinds =
        ["target_has_status", "retained_last_turn", .. Conditions.TargetKinds];

    /// <summary>The max custom orb defs a single class may forge (the rest of its pool is base orbs).</summary>
    public const int MaxCustomOrbs = 3;

    private static bool TryParseOrbPool(Godot.Collections.Array arr, int k, out OrbPoolEntry[] pool, out string error)
    {
        pool = [];
        var entries = new List<OrbPoolEntry>();
        var seenNames = new HashSet<string>();
        int customCount = 0;
        foreach (var item in arr)
        {
            if (item.VariantType == Godot.Variant.Type.String)
            {
                string nm = item.AsString().Trim().ToLowerInvariant();
                if (!BaseOrbs.Contains(nm))
                { error = $"orb_pool base orb '{nm}' is not one of {string.Join("/", BaseOrbs)}."; return false; }
                if (!seenNames.Add(nm)) { error = $"orb_pool has duplicate orb name '{nm}'."; return false; }
                entries.Add(new OrbPoolEntry(nm));
            }
            else if (item.VariantType == Godot.Variant.Type.Dictionary)
            {
                if (++customCount > MaxCustomOrbs)
                { error = $"orb_pool has more than {MaxCustomOrbs} custom orbs."; return false; }
                if (!TryParseCustomOrb(item.AsGodotDictionary(), k, customCount, out var entry, out error)) return false;
                string key = entry!.Name.Trim().ToLowerInvariant();
                if (!seenNames.Add(key)) { error = $"orb_pool has duplicate orb name '{key}'."; return false; }
                entries.Add(entry);
            }
            else { error = "orb_pool entries must be a base-orb name string or a custom-orb object."; return false; }
        }
        pool = entries.ToArray();
        error = "";
        return true;
    }

    private static bool TryParseCustomOrb(Godot.Collections.Dictionary d, int k, int customIndex,
        out OrbPoolEntry? entry, out string error)
    {
        entry = null;
        string name = Str(d, "name", $"Orb {customIndex}").Trim();
        if (name.Length == 0) { error = "a custom orb needs a non-empty name."; return false; }
        string desc = d.ContainsKey("description") ? Str(d, "description") : Str(d, "text");
        // Hue: explicit "hue", else color.h, else a WIDE spread so a class's custom orbs are visibly distinct
        // colors (≈1/3 of the wheel apart, plus a small per-class offset), wrapped into [0,1).
        float hue = (k - 1) * 0.11f + (customIndex - 1) * 0.31f;
        if (d.ContainsKey("hue")) hue = Flt(d, "hue", hue);
        else if (d.ContainsKey("color") && d["color"].VariantType == Godot.Variant.Type.Dictionary)
            hue = Flt(d["color"].AsGodotDictionary(), "h", hue);
        hue = (hue % 1f + 1f) % 1f; // wrap into [0,1)

        int passiveVal = Int(d, "passive_val", 0);
        int evokeVal = Int(d, "evoke_val", 0);

        if (!TryParseOrbEffects(d.ContainsKey("passive") ? d["passive"].AsGodotArray() : [], $"orb '{name}' passive", out var passive, out error)) return false;
        if (!TryParseOrbEffects(d.ContainsKey("evoke") ? d["evoke"].AsGodotArray() : [], $"orb '{name}' evoke", out var evoke, out error)) return false;
        if (passive.Length == 0 && evoke.Length == 0)
        { error = $"custom orb '{name}' has neither a passive nor an evoke effect."; return false; }

        // Phase AR (v49): when the passive ticks. Default turn_end (the Lightning/Frost shape); turn_start is the
        // Plasma shape — and REQUIRED for a passive that grants energy or draws (dead at turn end).
        string timing = d.ContainsKey("passive_timing") ? Str(d, "passive_timing").Trim().ToLowerInvariant() : "turn_end";
        if (!OrbPassiveTimings.Contains(timing))
        { error = $"custom orb '{name}': passive_timing '{timing}' is not one of {string.Join("/", OrbPassiveTimings)}."; return false; }
        foreach (var pe in passive)
            if (OrbTurnStartOnlyOps.Contains(pe.Effect.Op) && timing != "turn_start")
            { error = $"custom orb '{name}': a passive '{pe.Effect.Op}' needs passive_timing \"turn_start\" (at turn end the energy/cards are lost)."; return false; }

        var spec = new OrbSpec(name, desc, hue, passiveVal, evokeVal, passive, evoke, timing);
        entry = new OrbPoolEntry(name, spec, customIndex);
        error = "";
        return true;
    }

    private static bool TryParseOrbEffects(Godot.Collections.Array arr, string where, out OrbEffect[] effects, out string error)
    {
        effects = [];
        var list = new List<OrbEffect>(arr.Count);
        foreach (var item in arr)
        {
            if (item.VariantType != Godot.Variant.Type.Dictionary)
            { error = $"{where}: each effect must be an object."; return false; }
            var e = item.AsGodotDictionary();
            string op = Str(e, "op").Trim().ToLowerInvariant();
            if (!OrbOps.Contains(op))
            { error = $"{where}: op '{op}' is not allowed in an orb (one of {string.Join("/", OrbOps)})."; return false; }

            int amount = Int(e, "amount");
            string? status = e.ContainsKey("status") ? Str(e, "status").Trim().ToLowerInvariant() : null;
            string? orb = e.ContainsKey("orb") ? Str(e, "orb").Trim().ToLowerInvariant() : null;
            string target = e.ContainsKey("target") ? Str(e, "target").Trim().ToLowerInvariant() : "";

            if (target.Length > 0 && !OrbTargets.Contains(target))
            { error = $"{where}: target '{target}' is not one of {string.Join("/", OrbTargets)}."; return false; }

            bool selfBuff = op == "apply_status" && EffectRunner.SelfBuffStatuses.Contains(status ?? "");
            // Default + constrain the target per op modality.
            switch (op)
            {
                case "damage":
                    if (target.Length == 0) target = "enemy";
                    if (target == "self") { error = $"{where}: damage can't target self."; return false; }
                    break;
                case "apply_status":
                    if (status == null || !(EffectRunner.SelfBuffStatuses.Contains(status) || OrbEnemyStatuses.Contains(status)))
                    { error = $"{where}: unsupported status '{status}'."; return false; }
                    if (selfBuff) { if (target.Length == 0) target = "self"; if (target != "self") { error = $"{where}: self-buff '{status}' must target self."; return false; } }
                    else { if (target.Length == 0) target = "enemy"; if (target == "self") { error = $"{where}: debuff '{status}' can't target self."; return false; } }
                    break;
                default: // block/draw/gain_energy/heal/gain_orb_slot/channel_orb run on the player
                    if (target.Length == 0) target = "self";
                    if (target != "self") { error = $"{where}: op '{op}' always runs on yourself (target must be self)."; return false; }
                    break;
            }

            if (op == "channel_orb")
            {
                if (string.IsNullOrEmpty(orb)) { error = $"{where}: channel_orb needs an 'orb' name (a pool entry or 'random')."; return false; }
            }
            else if (orb != null) { error = $"{where}: 'orb' only applies to channel_orb (op '{op}')."; return false; }

            if (op != "channel_orb" && amount < 1)
            { error = $"{where}: op '{op}' needs amount >= 1."; return false; }

            // Phase AR (v49): an optional fire-time gate — the same JSON shape as a card effect's `when`, validated by
            // the shared Conditions.Validate plus the no-card/no-target rule (OrbForbiddenConditionKinds).
            Condition? when = null;
            if (e.ContainsKey("when"))
            {
                if (e["when"].VariantType != Godot.Variant.Type.Dictionary)
                { error = $"{where}: 'when' must be an object {{ \"kind\": ... }}."; return false; }
                var w = e["when"].AsGodotDictionary();
                when = new Condition(
                    Str(w, "kind").Trim().ToLowerInvariant(),
                    Int(w, "value"),
                    w.ContainsKey("status") ? Str(w, "status").Trim().ToLowerInvariant() : null,
                    Bool(w, "negate", false));
                var cerr = Conditions.Validate(when);
                if (cerr != null) { error = $"{where}: {cerr}"; return false; }
                if (OrbForbiddenConditionKinds.Contains(when.Kind))
                { error = $"{where}: an orb effect's 'when' can't use {when.Kind} (an orb fires with no card/chosen target)."; return false; }
            }

            list.Add(new OrbEffect(new EffectSpec(op, amount, status, Orb: orb, When: when), target));
        }
        effects = list.ToArray();
        error = "";
        return true;
    }

    // --- Phase I: orb resolvers (used by ForgedOrb shells + the class-aware channel path) -----------

    /// <summary>True if class <paramref name="k"/> declares a forged-orb pool (so its cards channel by pool name).</summary>
    public static bool IsOrbClass(int k) => SpecForClass(k).OrbPool.Length > 0;

    /// <summary>The custom <see cref="OrbSpec"/> for class <paramref name="k"/> custom-orb slot <paramref name="m"/>
    /// (1-based), or null (an unfilled <c>ForgedClassKOrbM</c> shell).</summary>
    public static OrbSpec? OrbSpecFor(int k, int m)
    {
        foreach (var e in SpecForClass(k).OrbPool)
            if (e.IsCustom && e.CustomIndex == m) return e.CustomSpec;
        return null;
    }

    /// <summary>Map a pool orb name to its compiled .NET Type for class <paramref name="k"/> (a base orb type, or
    /// the registered custom <c>ForgedClassKOrbM</c> type), or null if the name isn't in the class's pool.</summary>
    public static System.Type? ResolveOrbType(int k, string? name)
    {
        if (string.IsNullOrEmpty(name)) return null;
        string n = name.Trim().ToLowerInvariant();
        foreach (var e in SpecForClass(k).OrbPool)
        {
            if (e.Name.Trim().ToLowerInvariant() != n) continue;
            return e.IsCustom ? Powers.ForgedOrb.TypeForKey(k, e.CustomIndex) : EffectRunner.OrbTypeFor(e.Name);
        }
        return null;
    }

    /// <summary>A random orb Type from class <paramref name="k"/>'s OWN pool (class-scoped <c>random</c>), via the
    /// run's dedicated orb-generation RNG stream, or null if the class has no pool.</summary>
    public static System.Type? RandomOrbType(int k, Player player)
    {
        var pool = SpecForClass(k).OrbPool;
        if (pool.Length == 0) return null;
        var e = pool[player.RunState.Rng.CombatOrbGeneration.NextInt(pool.Length)];
        return e.IsCustom ? Powers.ForgedOrb.TypeForKey(k, e.CustomIndex) : EffectRunner.OrbTypeFor(e.Name);
    }

    // --- class file-store + bundle import (used by the in-game "Import a class code" screen) --------

    public static bool ClassFileExists(int k) => Godot.FileAccess.FileExists(ClassPath(k));

    /// <summary>Lowest 1-based class slot with no class file yet, or null if all <see cref="ClassCount"/> are taken.</summary>
    public static int? FirstFreeClassSlot()
    {
        for (int k = 1; k <= ClassCount; k++)
            if (!ClassFileExists(k)) return k;
        return null;
    }

    /// <summary>The class slot already holding a class with this name, or null. Used to update-in-place on re-import.</summary>
    public static int? FindClassSlotByName(string name)
    {
        for (int k = 1; k <= ClassCount; k++)
        {
            if (!ClassFileExists(k)) continue;
            using var f = Godot.FileAccess.Open(ClassPath(k), Godot.FileAccess.ModeFlags.Read);
            if (f == null) continue;
            var p = new Godot.Json();
            if (p.Parse(f.GetAsText()) != Godot.Error.Ok) continue;
            if (p.Data.VariantType != Godot.Variant.Type.Dictionary) continue;
            var d = p.Data.AsGodotDictionary();
            if (d.ContainsKey("name") && d["name"].AsString() == name) return k;
        }
        return null;
    }

    /// <summary>Deletes a class slot: its KK.json, its card files, and the KK/ dir. Returns true if anything was removed.</summary>
    public static bool DeleteClass(int k)
    {
        bool removed = false;
        var cardsDir = ClassCardsDir(k);
        if (Godot.DirAccess.DirExistsAbsolute(cardsDir))
        {
            using (var dir = Godot.DirAccess.Open(cardsDir))
                if (dir != null)
                    foreach (var fn in dir.GetFiles()) Godot.DirAccess.RemoveAbsolute($"{cardsDir}/{fn}");
            Godot.DirAccess.RemoveAbsolute(cardsDir);
            Godot.DirAccess.RemoveAbsolute($"{Root}/{k:00}");
        }
        if (ClassFileExists(k)) { Godot.DirAccess.RemoveAbsolute(ClassPath(k)); removed = true; }
        return removed;
    }

    /// <summary>Deletes every forged class. Returns how many class files were removed.</summary>
    public static int ClearAllClasses()
    {
        int n = 0;
        for (int k = 1; k <= ClassCount; k++)
            if (DeleteClass(k)) n++;
        return n;
    }

    private static void WriteClassFiles(int k, string characterJson, List<string> cardJsons)
    {
        var cardsDir = ClassCardsDir(k);
        if (!Godot.DirAccess.DirExistsAbsolute(cardsDir)) Godot.DirAccess.MakeDirRecursiveAbsolute(cardsDir);
        // Clear stale card files so a re-import never leaves a previous class's cards behind.
        using (var dir = Godot.DirAccess.Open(cardsDir))
            if (dir != null)
                foreach (var fn in dir.GetFiles()) Godot.DirAccess.RemoveAbsolute($"{cardsDir}/{fn}");

        using (var cf = Godot.FileAccess.Open(ClassPath(k), Godot.FileAccess.ModeFlags.Write))
        {
            if (cf == null) throw new IOException($"{Godot.FileAccess.GetOpenError()} opening {ClassPath(k)}");
            cf.StoreString(characterJson);
        }
        for (int i = 0; i < cardJsons.Count; i++)
        {
            using var f = Godot.FileAccess.Open(ClassCardPath(k, i + 1), Godot.FileAccess.ModeFlags.Write);
            if (f == null) throw new IOException($"{Godot.FileAccess.GetOpenError()} opening {ClassCardPath(k, i + 1)}");
            f.StoreString(cardJsons[i]);
        }
    }

    /// <summary>
    /// Import a decoded class bundle (<c>{ "kind":"class", "character":{…}, "cards":[…], "relic":{…}? }</c>):
    /// re-validate the character + every card against the live vocab, then write into a free (or explicit) class
    /// slot. Cards are written to slots 1..N in array order — the character's <c>starting_deck</c> references those
    /// indices. Safe by construction (data only). Restart applies it. On success returns the chosen 1-based slot.
    /// </summary>
    public static bool TryImportClassBundle(string bundleJson, int explicitSlot, out int classSlot, out string error)
    {
        classSlot = -1;
        var parser = new Godot.Json();
        if (parser.Parse(bundleJson) != Godot.Error.Ok)
        { error = $"invalid bundle JSON (line {parser.GetErrorLine()}): {parser.GetErrorMessage()}"; return false; }
        if (parser.Data.VariantType != Godot.Variant.Type.Dictionary)
        { error = "bundle root is not a JSON object."; return false; }
        var bundle = parser.Data.AsGodotDictionary();

        if (!bundle.ContainsKey("character") || bundle["character"].VariantType != Godot.Variant.Type.Dictionary)
        { error = "bundle has no 'character' object."; return false; }
        if (!bundle.ContainsKey("cards") || bundle["cards"].VariantType != Godot.Variant.Type.Array)
        { error = "bundle has no 'cards' array."; return false; }

        var charDict = bundle["character"].AsGodotDictionary();
        // Phase L: a bundle may carry the forged relic as a TOP-LEVEL sibling of 'character'; fold it into the
        // character dict so it validates (TryValidateCharacterDict reads character.relic) AND persists with the
        // class file (the startup loader reads the same field).
        if (bundle.ContainsKey("relic") && bundle["relic"].VariantType == Godot.Variant.Type.Dictionary
            && !charDict.ContainsKey("relic"))
            charDict["relic"] = bundle["relic"];
        var cardsArr = bundle["cards"].AsGodotArray();
        if (cardsArr.Count == 0) { error = "bundle has no cards."; return false; }
        if (cardsArr.Count > CardsPerClass)
        { error = $"bundle has {cardsArr.Count} cards (max {CardsPerClass} per class)."; return false; }

        // Validate the character (k here only affects the default hue when color is omitted).
        if (!TryValidateCharacterDict(charDict, explicitSlot > 0 ? explicitSlot : 1, out var cspec, out error))
            return false;
        foreach (var (slot, _) in cspec!.StartingDeck)
            if (slot > cardsArr.Count)
            { error = $"starting_deck references slot {slot} but the bundle has only {cardsArr.Count} cards."; return false; }

        // Validate every card against the live vocab (basics allowed for class starters). Phase AJ (v40): the class's
        // declared CUSTOM orb names are handed to the card validator so a channel_orb naming an orb outside base ∪ pool
        // is rejected at import (it used to import fine and silently channel Lightning at runtime).
        var poolOrbNames = cspec.OrbPool.Where(o => o.IsCustom).Select(o => o.Name.ToLowerInvariant()).ToHashSet();
        var cardJsons = new List<string>(cardsArr.Count);
        for (int i = 0; i < cardsArr.Count; i++)
        {
            if (cardsArr[i].VariantType != Godot.Variant.Type.Dictionary)
            { error = $"card {i + 1} is not a JSON object."; return false; }
            string cj = Godot.Json.Stringify(cardsArr[i]);
            if (!ForgedCards.TryParseCardJson(cj, i + 1, out _, out var cerr, allowBasic: true, allowCustomOrbs: true, orbNames: poolOrbNames))
            { error = $"card {i + 1}: {cerr}"; return false; }
            cardJsons.Add(cj);
        }

        int k = explicitSlot > 0 ? explicitSlot
              : (FindClassSlotByName(cspec.Name) ?? FirstFreeClassSlot() ?? -1);
        if (k < 1 || k > ClassCount)
        { error = $"all {ClassCount} class slots are full — clear one first."; return false; }

        try { WriteClassFiles(k, Godot.Json.Stringify(charDict), cardJsons); }
        catch (Exception e) { error = $"failed to write class files: {e.Message}"; return false; }

        classSlot = k;
        error = "";
        return true;
    }

    /// <summary>The file-drop twin of the settings screen's "Import" button (see <see cref="ImportQueuedCode"/>).</summary>
    public const string QueuedImportPath = "user://forged/import_code.txt";

    /// <summary>
    /// Boot-time queued import: if <see cref="QueuedImportPath"/> exists at mod init, its contents go through EXACTLY
    /// the two stages the "Import" button runs — <see cref="BTS1Codec.TryDecode"/>, then
    /// <see cref="TryImportClassBundle"/> — and the outcome is logged under <c>[IMPORT]</c>. An optional first line
    /// <c>slot=N</c> pins the class slot (otherwise auto, like the slider at 0). The file is renamed to
    /// <c>.imported</c> / <c>.rejected</c> so it runs once. Called BEFORE any class spec is read, so the imported
    /// class is playable in the SAME launch — which is what lets the AutoSlay smoke push a REAL generated code
    /// through the codec + importer with no hand on the UI (the Phase BA "importer has only ever parsed
    /// hand-staged JSON" gap). Splash art is not fetched here (no scene tree yet); the button path still does that.
    /// </summary>
    public static void ImportQueuedCode()
    {
        if (!Godot.FileAccess.FileExists(QueuedImportPath)) return;
        string text;
        using (var f = Godot.FileAccess.Open(QueuedImportPath, Godot.FileAccess.ModeFlags.Read))
        {
            if (f == null)
            { MainFile.Logger.Warn($"[IMPORT] could not open {QueuedImportPath}: {Godot.FileAccess.GetOpenError()}"); return; }
            text = f.GetAsText();
        }

        string code = text.Trim();
        int slot = 0;
        int nl = code.IndexOf('\n');
        string first = (nl >= 0 ? code[..nl] : code).Trim();
        if (first.StartsWith("slot=", StringComparison.OrdinalIgnoreCase) && int.TryParse(first[5..], out int pinned))
        {
            slot = pinned;
            code = nl >= 0 ? code[(nl + 1)..] : "";
        }

        bool ok = false;
        string outcome;
        if (!BTS1Codec.TryDecode(code, out var json, out var kind, out var decodeError))
            outcome = $"decode FAILED: {decodeError}";
        else if (kind != BTS1Codec.BtsKind.Class)
            outcome = "decoded, but it is a card (BTS1) code, not a class (BTSC) code";
        else if (!TryImportClassBundle(json, slot, out int k, out var err))
            outcome = $"decoded ({json.Length} chars of bundle JSON) but the importer REJECTED it: {err}";
        else
        {
            ok = true;
            outcome = $"decoded ({json.Length} chars of bundle JSON) and imported into class slot {k:00}";
        }
        MainFile.Logger.Info($"[IMPORT] queued code ({code.Length} chars): {outcome}.");

        // The class loader caches on first read; make sure the freshly written files are what this launch sees.
        _classes = null;
        _cards = null;

        string done = QueuedImportPath + (ok ? ".imported" : ".rejected");
        if (Godot.FileAccess.FileExists(done)) Godot.DirAccess.RemoveAbsolute(done);
        Godot.DirAccess.RenameAbsolute(QueuedImportPath, done);
    }

    private static string Str(Godot.Collections.Dictionary d, string key, string fallback = "") =>
        d.ContainsKey(key) ? d[key].AsString() : fallback;

    private static int Int(Godot.Collections.Dictionary d, string key, int fallback = 0) =>
        d.ContainsKey(key) ? d[key].AsInt32() : fallback;

    private static bool Bool(Godot.Collections.Dictionary d, string key, bool fallback) =>
        d.ContainsKey(key) ? d[key].AsBool() : fallback;

    private static float Flt(Godot.Collections.Dictionary d, string key, float fallback) =>
        d.ContainsKey(key) ? (float)d[key].AsDouble() : fallback;
}

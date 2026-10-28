# Simplified Chinese glossary (zhs)

Used by (1) whoever translates `docs/copy/COPY.md` into `COPY.zh.md`, (2) the mod's `zhs` rules-text templates
(`ForgedText.zhs.cs`, see `docs/plans/I18N_PLAN.md` section C1), (3) the forge's end-of-run translation call (C2),
and (4) a `mod/BlankTheSpire/localization/zhs/` table set.

## Where the official terms come from

- The game loads its tables from `res://localization/<lang>/*.json` (`LocManager.LoadTablesFromPath`,
  `LocalizationAssetDir => "res://localization"`). Each file is a flat JSON `{"KEY": "text"}` map. Simplified
  Chinese is the `zhs` folder. Mods merge their own `localization/zhs/<same file>.json` on top
  (`ModManager.GetModdedLocTables`), and missing keys fall back to `eng`.
- The tables sit inside `SlayTheSpire2.pck` as `localization/zhs/cards.json`, `powers.json`, `card_keywords.json`,
  `static_hover_tips.json`, `orbs.json`, `gameplay_ui.json`, `card_library.json`, `relics.json`, `potions.json`,
  `characters.json`, `main_menu_ui.json`, `intents.json`, ... (46 JSON files). The pack directory stores them
  without the `res://` prefix, so a grep for `res://localization` finds nothing. Pack format: Godot 4.5 `GDPC`
  v3, pack flags 2 (offsets relative to file base 112), no encryption, files stored uncompressed. A 40-line
  Python reader (header, directory at the v3 directory offset, `path | offset | size | md5 | flags` per entry)
  pulls them out. Read-only, nothing under the Steam folder is modified.
- Extracted from the build installed on 2026-10-27 (its `zhs/patch_notes/2026_03_26.md` is the newest note).
  Re-check after a big game patch.
- Source column: `file:KEY` = taken verbatim from that game table. "derived" = built only from verified pieces
  by the game's own pattern. "STS1 convention" = no STS2 term exists, so we use the classic Slay the Spire 1
  Chinese term. UNVERIFIED = no game source, our own choice. "product" = our own product word.

## 1. Game keywords, statuses and nouns

### Card keywords (the game prints these as `[gold]词[/gold]。` on their own line)

| English | 简体中文 | source | note |
|---|---|---|---|
| Exhaust | 消耗 | card_keywords:EXHAUST.title | Also the verb: "[gold]消耗[/gold]1张牌" |
| Ethereal | 虚无 | card_keywords:ETHEREAL.title | |
| Retain | 保留 | card_keywords:RETAIN.title | "Retain your hand" = 保留你的手牌 |
| Innate | 固有 | card_keywords:INNATE.title | |
| Unplayable | 不能被打出 | card_keywords:UNPLAYABLE.title | |
| Sly | 奇巧 | card_keywords:SLY.title | STS2-only |
| Eternal | 永恒 | card_keywords:ETERNAL.title | |
| Fatal | 斩杀 | static_hover_tips:FATAL.title | "If Fatal, ..." = "[gold]斩杀[/gold]时，..." (Feed) |
| Replay | 重放 | static_hover_tips:REPLAY_STATIC.title | |
| Upgrade / Upgraded | 升级 | static_hover_tips:ROOM_REST + cards:ARMAMENTS | "Upgraded" card = 升级的牌; a "+" suffix on names (小刀+) |
| Transform | 变化 | static_hover_tips:TRANSFORM.title | not 变形 |
| Remove (from deck) | 移除 | static_hover_tips:COOK.description | |
| Enchant | 附魔 | relics:BEAUTIFUL_BRACELET | |
| Purge (our op: removed from the deck for the rest of the run) | 移除 | derived | STS2 has no Purge keyword; write "从你的[gold]牌组[/gold]中移除" |
| Scry | 预见 | STS1 convention | Not in STS2 at all. Keep the mod's explanation in brackets |
| Stun | 击晕 | static_hover_tips:STUN.title | intents:STUN.title = 击晕 too |
| Forge (Regent keyword) | 铸造 | static_hover_tips:FORGE.title | "[gold]铸造[/gold]{Forge:diff()}。" CLASHES with our product verb, see section 3 |
| Summon | 召唤 | static_hover_tips:SUMMON_STATIC.title | "[gold]召唤[/gold]{Summon:diff()}。" |
| Channel | 生成 | static_hover_tips:CHANNELING.title | "[gold]生成[/gold]1个[gold]闪电[/gold]充能球" |
| Evoke | 激发 | static_hover_tips:EVOKE.title | |
| create (a card) | 生成 | powers:ARSENAL_POWER | Same word as Channel; context separates them |

### Statuses (powers) the mod applies

Measure word: 点 for stat-like amounts, 层 for stacking debuffs, counted from all base-game card/relic/potion text.

| English | 简体中文 | source | note |
|---|---|---|---|
| Strength | 力量 | powers:STRENGTH_POWER.title | 点 (81 of 82 uses) |
| Dexterity | 敏捷 | powers:DEXTERITY_POWER.title | 点 |
| Focus | 集中 | powers:FOCUS_POWER.title | 点 |
| Vigor | 活力 | powers:VIGOR_POWER.title | 点 |
| Thorns | 荆棘 | powers:THORNS_POWER.title | 点 |
| Vulnerable | 易伤 | powers:VULNERABLE_POWER.title | 层 |
| Weak | 虚弱 | powers:WEAK_POWER.title | 层 |
| Frail | 脆弱 | powers:FRAIL_POWER.title | 层 |
| Poison | 中毒 | powers:POISON_POWER.title | 层 |
| Doom | 灾厄 | powers:DOOM_POWER.title | 层. STS2-only |
| Intangible | 无实体 | powers:INTANGIBLE_POWER.title | 层 |
| Artifact | 人工制品 | powers:ARTIFACT_POWER.title | the power text counts it with 次 ("免疫{Amount}次负面效果"); the mod's card text counts it with 层 like the other stacking statuses (mod v0.5.0 (ForgedText.zhs.cs), unit.artifact = 层) |
| Buffer | 缓冲 | powers:BUFFER_POWER.title | 层 |
| Regen | 再生 | powers:REGEN_POWER.title | 层 (potion text) |
| Ritual | 仪式 | powers:RITUAL_POWER.title | 层 |
| Metallicize (mod name; it applies the game's `PlatingPower`) | 覆甲 | powers:PLATING_POWER.title | 层. STS2's English word is "Plating". STS1's 金属化 / 多层护甲 are not in STS2. Use 覆甲 so the hover tip matches |
| Plated Armor | 覆甲 | powers:PLATING_POWER.title | same power in STS2 |
| Blur | 残影 | powers:BLUR_POWER.title | |
| Barricade | 壁垒 | powers:BARRICADE_POWER.title | |
| Double Damage | 双倍伤害 | powers:DOUBLE_DAMAGE_POWER.title | |
| Strength Down (temporary) | 力量下降 | derived | Game has 敏捷下降 / 集中下降. The game's own text for the temp loss is "在本回合结束前失去{Amount}点力量" (TEMPORARY_STRENGTH_DOWN) |
| Dexterity Down | 敏捷下降 | powers:DEXTERITY_DOWN_POWER.title | |
| Focus Down | 集中下降 | powers:FOCUS_DOWN.title | |
| No Draw | 不可抽牌 | powers:NO_DRAW_POWER.title | |
| No Energy Gain | 无法获得能量 | powers:NO_ENERGY_GAIN_POWER.title | |
| No Block | 不可格挡 | powers:NO_BLOCK_POWER.title | |
| Wraith Form | 幽魂形态 | powers:WRAITH_FORM_POWER.title | |
| Biased Cognition | 偏差认知 | powers:BIASED_COGNITION_POWER.title | |
| Echo Form | 回响形态 | powers:ECHO_FORM_POWER.title | |
| Loop | 循环 | powers:LOOP_POWER.title | |
| Corruption | 腐化 | powers:CORRUPTION_POWER.title | |
| Burst | 爆发 | powers:BURST_POWER.title | |
| Duplication | 复制 | powers:DUPLICATION_POWER.title | |
| Signal Boost | 信号增强 | powers:SIGNAL_BOOST_POWER.title | |
| One-Two Punch | 连环拳 | powers:ONE_TWO_PUNCH_POWER.title | |
| Retain Hand | 保留手牌 | powers:RETAIN_HAND_POWER.title | |
| Block Next Turn | 下回合格挡 | powers:BLOCK_NEXT_TURN_POWER.title | |
| Minion | 爪牙 | powers:MINION_POWER.title | |
| Sharpen (the mod's Spike-Imp buff) | 磨砺 | mod v0.5.0 (ForgedText.zhs.cs) | power.sharpen.title = "🗡️ 磨砺"; counted with 层 ("获得{n}层🗡️磨砺。") |
| Blade Empower | 利刃强化 | mod v0.5.0 (ForgedText.zhs.cs) | power.blade_empower.title |
| Cost Shift | 耗能变动 | mod v0.5.0 (ForgedText.zhs.cs) | power.cost_shift.title; 耗能 as in the cost row of the cards table |
| Summoned Ally | 召唤盟友 | mod v0.5.0 (ForgedText.zhs.cs) | power.summoned_ally.title (the power on a forged summon) |
| Bodyguard (the summon's shield/guard power) | 护卫 | mod v0.5.0 (ForgedText.zhs.cs) | power.bodyguard.title, English "Bodyguard" (Powers/ForgedSummonShieldPower.cs); summoned_ally.desc calls the summon 一名…护卫 |
| debuff | 负面效果 | intents:DEBUFF.description | "apply a debuff" = 施加负面效果 |
| buff | 强化 | intents:BUFF.title | |

### Orbs, Osty, resources

| English | 简体中文 | source | note |
|---|---|---|---|
| Orb | 充能球 | static_hover_tips:CHANNELING | "Channel 1 Frost" = "[gold]生成[/gold]1个[gold]冰霜[/gold]充能球" |
| Orb Slot | 充能球栏位 | orbs:EMPTY_SLOT.title | |
| Lightning | 闪电 | orbs:LIGHTNING_ORB.title | |
| Frost | 冰霜 | orbs:FROST_ORB.title | |
| Dark | 黑暗 | orbs:DARK_ORB.title | |
| Plasma | 等离子 | orbs:PLASMA_ORB.title | |
| Glass | 玻璃 | orbs:GLASS_ORB.title | |
| passive (orb) | 被动 / 被动能力 | cards:DARKNESS, cards:LOOP | |
| rightmost / leftmost Orb | 最右侧 / 最左侧的充能球 | cards:DUALCAST, cards:CONSUMING_SHADOW | the mod's "next orb" = the rightmost one |
| Osty | 奥斯提 | monsters:OSTY.name | |
| summon (our minion, noun) | 召唤物 | UNVERIFIED | the game only names Osty. 召唤物 is the usual Chinese game word |
| Spike Imp (the mod's spike summon) | 尖刺小鬼 | mod v0.5.0 (ForgedText.zhs.cs) | power.spike_imp.title, monster.spike_imp.name; "[gold]召唤[/gold]一个尖刺小鬼。" |
| Ethereal (summon that cannot be attacked) | 灵体 | mod v0.5.0 (ForgedText.zhs.cs) | summon.ethereal = "灵体（无法被攻击）". NOT the card keyword Ethereal (虚无) |
| Sovereign Blade | 君王之剑 | cards:SOVEREIGN_BLADE.title | |
| Shiv | 小刀 | cards:SHIV.title | 张 |
| Soul | 灵魂 | cards:SOUL.title | |
| Stars | 辉星 | static_hover_tips:STAR_COUNT.title | written as `{Stars:starIcons()}` in card text |
| Energy | 能量 | static_hover_tips:ENERGY.title | card text never writes the word: `获得{Energy:energyIcons()}。` |
| Block | 格挡 | static_hover_tips:BLOCK.title | 点 |
| HP | 生命 / 生命值 | static_hover_tips:HIT_POINTS.title (生命值（HP）) | card text: "失去{HpLoss:diff()}点生命" |
| Max HP | 最大生命值 | cards:FEED, relics:BIG_MUSHROOM | BRIGHTEST_FLAME shortens it to 最大生命 |
| Heal | 回复 | cards:NOT_YET | "回复{Heal:diff()}点生命。" |
| Gold | 金币 | static_hover_tips:MONEY_POUCH.title | no measure word: "失去{Gold:diff()}[gold]金币[/gold]" |
| Potion | 药水 | cards:ALCHEMIZE | 瓶: 一瓶随机药水 |
| Potion Slot | 药水栏位 | static_hover_tips:POTION_SLOT.title | |
| Relic | 遗物 | gameplay_ui:RELIC_RARITY.NONE | |
| Starter Relic | 初始遗物 | gameplay_ui:RELIC_RARITY.STARTER | |
| damage | 伤害 | cards:STRIKE_IRONCLAD | 点 |
| unblocked damage | 未被格挡的伤害 | cards:ENVENOM | |
| ignoring Block (unblockable hit) | 无视格挡 | UNVERIFIED | the game has no such card. Sentence: "造成{Damage}点伤害，无视格挡。" |
| Light / Dark (the mod's balance poles) | 光明 / 黑暗 | mod v0.5.0 (ForgedText.zhs.cs) | power.balance.title_light/title_dark = "☀️ 光明" / "🌑 黑暗"; "Shift N toward the Light" = 向光明偏移N. Our own mechanic. 黑暗 matches the Dark orb's word, which may confuse. Review when a balance class ships in Chinese |

### Cards, piles, types, rarities

| English | 简体中文 | source | note |
|---|---|---|---|
| card | 牌 / 卡牌 | cards:* | rules text uses 牌 (张); UI and menus use 卡牌 |
| Attack / Skill / Power (type) | 攻击 / 技能 / 能力 | gameplay_ui:CARD_TYPE.* | as a noun in rules text add 牌: 攻击牌, 技能牌, 能力牌 |
| Status / Curse | 状态 / 诅咒 | gameplay_ui:CARD_TYPE.STATUS / CURSE | 状态牌 |
| non-Attack card | 非攻击牌 | cards:SECOND_WIND | |
| Colorless | 无色 | card_library:POOL_COLORLESS_TIP | |
| Token (card) | 衍生 | gameplay_ui:CARD_RARITY.TOKEN | 衍生牌. The site's rarity label uses it too (app.rarity.token in COPY.zh.md) |
| Common / Uncommon / Rare | 普通 / 罕见 / 稀有 | card_library:RARITY_* | |
| Basic / Starter (rarity) | 基础 / 初始 | gameplay_ui:CARD_RARITY.BASIC, main_menu_ui:CARD_LIBRARY_RARITY_BASIC | |
| Ancient (rarity) | 先古 | gameplay_ui:CARD_RARITY.ANCIENT | the beings are 先古之民 |
| Wound / Dazed / Burn / Slimed / Void | 伤口 / 晕眩 / 灼伤 / 黏液 / 虚空 | cards:WOUND/DAZED/BURN/SLIMED/VOID.title | |
| Hand | 手牌 | card_keywords:INNATE.description | |
| Deck | 牌组 | static_hover_tips:DECK.title | also the site's "deck" page |
| Draw Pile | 抽牌堆 | static_hover_tips:DRAW_PILE.title | top of = 抽牌堆顶部 |
| Discard Pile | 弃牌堆 | static_hover_tips:DISCARD_PILE.title | |
| Exhaust Pile | 消耗牌堆 | static_hover_tips:EXHAUST_PILE.title, cards:BOMBARDMENT | |
| draw (verb) | 抽 | cards:ACROBATICS | "抽2张牌" |
| discard (verb) | 丢弃 | cards:ACROBATICS, gameplay_ui:POTION_POPUP.discard | |
| shuffle into | 洗入 | cards:CHRYSALIS | |
| cost (energy) | 耗能 / 费用 | cards:CORRUPTION; gameplay_ui:SORT_COST | rules text: 耗能. "1-cost card" = 1费牌 |
| copy (of a card) | 复制品 | cards:ANGER | "将一张此牌的复制品加入你的[gold]弃牌堆[/gold]" |
| free to play this turn | 在本回合可以免费打出 | cards:DISCOVERY | |
| Character | 角色 | characters:RANDOM_CHARACTER | |
| The Ironclad / Silent / Defect / Regent / Necrobinder | 铁甲战士 / 静默猎手 / 故障机器人 / 储君 / 亡灵契约师 | characters:*.title | |

### Time and run structure

| English | 简体中文 | source | note |
|---|---|---|---|
| turn | 回合 | static_hover_tips:END_TURN | |
| this turn | 本回合 / 在本回合 | cards:EQUILIBRIUM | |
| next turn | 下个回合 / 下一回合 | cards:OUTMANEUVER, cards:GLITTERSTREAM | both appear. Prefer 下个回合 |
| At the start of your turn | 在你的回合开始时 | cards:DEMON_FORM | |
| At the end of your turn | 在你的回合结束时 | cards:BURN | |
| combat | 战斗 | static_hover_tips:EXHAUST_PILE | this combat = 本场战斗; each combat = 每场战斗 |
| At the start of each combat | 在每场战斗开始时 | relics:AKABEKO | |
| (once per combat) | （每场战斗一次） | powers:CURL_UP_POWER | |
| run | 一局游戏 / 本局游戏 | characters:SILENT.unlockText, cards:THE_SCYTHE | "for the rest of the run" = 在本局游戏中 / 永久 |
| Act | 阶段 | static_hover_tips:BOSS | |
| Floor | 楼层 | static_hover_tips:FLOOR.title | |
| Rest Site / Shop / Elite / Boss | 休息处 / 商店 / 精英 / Boss | static_hover_tips:ROOM_* | Boss stays Latin |
| the Spire | 高塔 | static_hover_tips:MONEY_POUCH | 尖塔 also appears (characters:NECROBINDER.description) |
| enemy / ALL enemies / a random enemy | 敌人 / 所有敌人 / 随机敌人 | cards:BREAKTHROUGH, cards:JUGGERNAUT | see the phrasing table for word order |
| Mod / mods | 模组 | main_menu_ui:MODDING_POPUP.load_mods | |
| Slot (class slot, potion slot) | 栏位 | static_hover_tips:POTION_SLOT.title | |
| Abandon Run | 放弃当前游戏 | main_menu_ui:ABANDON_RUN | settings_ui says 放弃这局游戏 |
| Custom (mode) | 自定义 | game_modes:SINGLE_PLAYER_CUSTOM.title | |
| Cancel / Confirm / Continue / Back | 取消 / 确认 / 继续 / 返回 | main_menu_ui:MODDING_POPUP.cancel, timeline:UNLOCK_CONFIRM, game_over_screen:BUTTON.continue, main_menu_ui:MULTIPLAYER_WARNING_POPUP.back | |

## 2. Card-text phrasing patterns (copied from the game's own cards)

The game's conventions, all visible below:
- **No spaces at all** between Chinese characters, `{placeholders}`, digits and `[gold]` tags:
  `造成{Damage:diff()}点伤害。` (not `造成 {Damage} 点伤害。`). This corrects the example in I18N_PLAN C1.
- Measure word after the number: 点 for damage, Block, Strength, Dexterity, Focus, Vigor, Thorns and HP;
  层 for Vulnerable, Weak, Frail, Poison, Doom, Intangible and Plating; 张 for cards; 个 for orbs and slots;
  次 for repeats.
- Full-width 。，： inside rules text. Each sentence ends in 。 and sentences are split with `\n` exactly as in English.
- Keyword and status names are wrapped in `[gold]…[/gold]` around the **Chinese** word. That BBCode is literal text
  in each locale's string. There is no locale-independent keyword tag. Hover tips come from the keywords and
  powers the card declares, not from the text. Keyword lines (Exhaust, Retain, Ethereal, Innate, Sly, Unplayable)
  are added by the game itself, from `card_keywords.json`, as `[gold]消耗[/gold]。`
  (`CardKeywordExtensions.GetCardText`, plus `card_keywords:PERIOD` = `。`).
- Dynamic vars keep their names and get `:diff()` (the upgrade-diff colouring). Energy and Stars are icons:
  `{Energy:energyIcons()}`, `{Stars:starIcons()}`. Literal numbers in power or relic text are `[blue]N[/blue]`.
- The mod's English templates today emit bare `{Damage}` and no `[gold]`. The zhs templates should follow the game:
  `{Damage:diff()}` and `[gold]力量[/gold]`. Check that the mod's DataCard vars resolve with `:diff()` first.

| # | English (game markup) | 简体中文 (game markup) | source |
|---|---|---|---|
| 1 | `Deal {Damage:diff()} damage.` | `造成{Damage:diff()}点伤害。` | cards:STRIKE_IRONCLAD |
| 2 | `Gain {Block:diff()} [gold]Block[/gold].` | `获得{Block:diff()}点[gold]格挡[/gold]。` | cards:DEFEND_IRONCLAD |
| 3 | `Apply {VulnerablePower:diff()} [gold]Vulnerable[/gold].` | `给予{VulnerablePower:diff()}层[gold]易伤[/gold]。` | cards:BASH |
| 4 | `Apply {WeakPower:diff()} [gold]Weak[/gold].` / `Apply {PoisonPower:diff()} [gold]Poison[/gold].` | `给予{WeakPower:diff()}层[gold]虚弱[/gold]。` / `给予{PoisonPower:diff()}层[gold]中毒[/gold]。` | cards:NEUTRALIZE, cards:DEADLY_POISON |
| 5 | `Gain {StrengthPower:diff()} [gold]Strength[/gold].` | `获得{StrengthPower:diff()}点[gold]力量[/gold]。` | cards:INFLAME |
| 6 | `Draw {Cards:diff()} cards.` | `抽{Cards:diff()}张牌。` | cards:ACROBATICS (plural forms collapse: POMMEL_STRIKE drops `{Cards:plural:…}`) |
| 7 | `Deal {Damage:diff()} damage {Repeat:diff()} times.` | `造成{Damage:diff()}点伤害{Repeat:diff()}次。` | cards:PECK. "twice" = 两次 (TWIN_STRIKE) |
| 8 | `Deal {Damage:diff()} damage to ALL enemies.` | `对所有敌人造成{Damage:diff()}点伤害。` | cards:BREAKTHROUGH |
| 9 | `Deal {Damage:diff()} damage to a random enemy {Repeat:diff()} times.` | `随机对敌人造成{Damage:diff()}点伤害{Repeat:diff()}次。` | cards:SWORD_BOOMERANG. A one-hit form is `对随机敌人造成…点伤害。` (JUGGERNAUT) |
| 10 | `Deal {Damage:diff()} damage and apply {VulnerablePower:diff()} [gold]Vulnerable[/gold] to ALL enemies.` | `对所有敌人造成{Damage:diff()}点伤害，给予{VulnerablePower:diff()}层[gold]易伤[/gold]。` | cards:THUNDERCLAP. "Apply X to ALL enemies" = `给予所有敌人X层…` (NOXIOUS_FUMES) |
| 11 | `[gold]Exhaust[/gold] 1 card.` / `… 1 card at random.` / `[gold]Exhaust[/gold] your [gold]Hand[/gold].` | `[gold]消耗[/gold]1张牌。` / `随机[gold]消耗[/gold]1张牌。` / `[gold]消耗[/gold]所有[gold]手牌[/gold]。` | cards:BURNING_PACT, CINDER, FIEND_FIRE |
| 12 | `Discard 1 card.` / `Discard your [gold]Hand[/gold].` | `丢弃1张牌。` / `丢弃你的所有[gold]手牌[/gold]。` | cards:SURVIVOR, CALCULATED_GAMBLE |
| 13 | `Gain {Energy:energyIcons()}.` | `获得{Energy:energyIcons()}。` | cards:ALIGNMENT |
| 14 | `Lose {HpLoss:diff()} HP.` / `Heal {Heal:diff()} HP.` | `失去{HpLoss:diff()}点生命。` / `回复{Heal:diff()}点生命。` | cards:BLOODLETTING, NOT_YET |
| 15 | `If [gold]Fatal[/gold], raise your Max HP by {MaxHp:diff()}.` | `[gold]斩杀[/gold]时，永久获得{MaxHp:diff()}点最大生命值。` | cards:FEED |
| 16 | `[gold]Channel[/gold] 1 [gold]Lightning[/gold].` / `[gold]Evoke[/gold] your rightmost Orb twice.` | `[gold]生成[/gold]1个[gold]闪电[/gold]充能球。` / `[gold]激发[/gold]你最右侧的充能球两次。` | cards:ZAP, DUALCAST |
| 17 | `At the start of your turn, gain {StrengthPower:diff()} [gold]Strength[/gold].` | `在你的回合开始时，获得{StrengthPower:diff()}点[gold]力量[/gold]。` | cards:DEMON_FORM |
| 18 | `Whenever you play a card, gain {AfterimagePower:diff()} [gold]Block[/gold].` | `你每打出一张牌，都获得{AfterimagePower:diff()}点[gold]格挡[/gold]。` | cards:AFTERIMAGE. Other "Whenever" forms use 每当…时，… (CALAMITY, JUGGERNAUT, DARK_EMBRACE) |
| 19 | `Whenever you are attacked, deal {ThornsPower:diff()} damage back.` | `每当你被攻击时，对攻击者造成{ThornsPower:diff()}点伤害。` | cards:CALTROPS |
| 20 | `Next turn, gain {Block:diff()} [gold]Block[/gold].` | `在下个回合，获得{Block:diff()}点[gold]格挡[/gold]。` | cards:DODGE_AND_ROLL |
| 21 | `Add a copy of this card into your [gold]Discard Pile[/gold].` | `将一张此牌的复制品加入你的[gold]弃牌堆[/gold]。` | cards:ANGER |
| 22 | `[gold]Upgrade[/gold] {IfUpgraded:show:ALL cards\|a card} in your [gold]Hand[/gold].` | `[gold]升级[/gold]你[gold]手牌[/gold]中的{IfUpgraded:show:所有牌\|一张牌}。` | cards:ARMAMENTS (the pipe is escaped only for this table; the JSON has a plain one) |
| 23 | `Deal damage equal to your [gold]Block[/gold].` | `造成你当前[gold]格挡[/gold]值的伤害。` | cards:BODY_SLAM. "Apply Doom equal to damage dealt" = `给予等量于所造成伤害的[gold]灾厄[/gold]。` (BLIGHT_STRIKE) |
| 24 | `[gold]Retain[/gold] your [gold]Hand[/gold] this turn.` | `在本回合[gold]保留[/gold]你的[gold]手牌[/gold]。` | cards:EQUILIBRIUM |
| 25 | `Enemy loses {StrengthLoss:diff()} [gold]Strength[/gold] this turn.` / `ALL enemies lose …` | `使一名敌人在本回合失去{StrengthLoss:diff()}点[gold]力量[/gold]。` / `所有敌人在本回合失去{StrengthLoss:diff()}点[gold]力量[/gold]。` | cards:DARK_SHACKLES, PIERCING_WAIL |
| 26 | `Put a card from your [gold]Discard Pile[/gold] on top of your [gold]Draw Pile[/gold].` | `将你[gold]弃牌堆[/gold]中的一张牌放到[gold]抽牌堆[/gold]顶部。` | cards:HEADBUTT |
| 27 | `Add a random Attack into your [gold]Hand[/gold]. It's free to play this turn.` | `将一张随机攻击牌加入你的[gold]手牌[/gold]。那张牌在本回合内可以免费打出。` | cards:INFERNAL_BLADE |
| 28 | `[gold]Stun[/gold] the enemy.` | `[gold]击晕[/gold]该敌人。` | cards:WHISTLE |
| 29 | `[gold]Forge[/gold] {Forge:diff()}.` / `[gold]Summon[/gold] {Summon:diff()}.` | `[gold]铸造[/gold]{Forge:diff()}。` / `[gold]召唤[/gold]{Summon:diff()}。` | cards:BIG_BANG, AFTERLIFE |

The conditional suffix the mod weaves in ("… if …") is a fronted clause in the game:
`如果你在本回合失去过生命值，\n则攻击{Repeat:diff()}次。` (cards:SPITE). Put 如果…，则… in front, never at the end.

## 3. Product terms (our own words, chosen here)

| English | 简体中文 | source | note |
|---|---|---|---|
| Blank the Spire | Blank the Spire | product | Never translate or transliterate. The game keeps its own name Latin in zhs ("《Slay the Spire 2》", credits:EXIT_MESSAGE) |
| Slay the Spire 2 | Slay the Spire 2 | credits:EXIT_MESSAGE | Latin, like the game. 杀戮尖塔2 is the common Chinese name; it may appear once in page meta for search (UNVERIFIED as the store name) |
| forge (verb) / Forge (button) | 锻造 | product | NOT 铸造: that is the Regent's in-game Forge keyword (static_hover_tips:FORGE), and forged classes can use it. Considered 生成 (= the game's Channel), 打造 (fine, more casual), 创造 |
| a forge (one generation run) | 一次锻造 | product | "your forge is running" = 锻造进行中 |
| forge token | 锻造券 | product | Considered 代币 (sounds like crypto or purchase), 点数, 次数. 券 reads as a voucher, which fits the donation framing |
| Get a forge token | 获取锻造券 | product | 获取, never 购买 (never say "buy") |
| donate / donation | 赞助 | product | 捐赠 also natural. Never 购买 / 充值 |
| class (a forged character) | 角色 | product (game: characters = 角色) | The game calls the five heroes 角色. In descriptive copy, 自制角色 marks ours. Considered 职业 (the community's word for the heroes) and 人物 (as in the mod scene's 人物mod). 角色 wins because it matches the game UI |
| import code / class code | 角色码 | product | One term for both. Confirmed in the mod v0.5.0 (zhs/settings_ui.json IMPORT_CLASS_CODE, IMPORT_SECTION 导入角色码; ForgedText.zhs.cs mod.dialog.*); the mod.codec.* errors say 代码 for a code of unknown type. "Paste the class code" = 粘贴角色码. `BTSC.` stays Latin |
| Import / Import class | 导入 / 导入角色 | product | |
| Copy (code) | 复制 | product | |
| class slot | 角色栏位 | product (栏位 from static_hover_tips:POTION_SLOT) | |
| Restart game | 重启游戏 | product | The game's long form is 重新启动游戏 (main_menu_ui:MODDING_POPUP.description). Use that in sentences |
| Sign in / Sign out | 登录 / 退出登录 | product | |
| The Archive | 档案馆 | product | Considered 资料库, 归档 (sounds like a file action). 档案馆 keeps "The Archive" as a place |
| featured | 精选 | product | |
| nominate / nomination | 提名 | product | |
| remix (a featured deck) | 改编 | product | 二创 is too slangy |
| deck (the site's deck page) | 牌组 | static_hover_tips:DECK.title | |
| concept (what the user types) | 构想 | product | Considered 创意, 概念 (stiff) |
| hosted (we run the model) | 托管模式 | product | In a sentence: 由我们提供模型 |
| bring your own key (BYOK) | 自带密钥（BYOK） | product | Keep "BYOK" in brackets the first time; "API key" = API密钥 |
| Authored / invented by the class (custom orbs, statuses, mechanics) | 自创 | product (web copy: app.mech.head, console.stage orb line) | not in ForgedText.zhs.cs as of v0.5.0; "自创充能球" = a custom orb |
| Design model / Card-coding model | 设计模型 / 卡牌编码模型 | product | |
| splash art | 立绘 | product | the standard Chinese game word for character key art |
| card art | 卡图 | product | |
| Steam Workshop | Steam创意工坊 | product (Steam's own Chinese name) | "Subscribe" = 订阅 (Steam's term) |
| archetype | 流派 | product | the word Chinese STS players use for builds (力量流, 中毒流). Considered 套路, 原型 |
| starter relic | 初始遗物 | gameplay_ui:RELIC_RARITY.STARTER | |
| starter deck | 初始牌组 | derived | |
| tier (donation tier) | 档位 | product | |
| magic link (email sign-in) | 登录链接 | product | |

## 4. Rules for translators

1. Keep every `{placeholder}`, `[gold]…[/gold]`/`[blue]` tag, `**markup**`, link URL and BBCode exactly as written. Translate only the words around them.
2. "Blank the Spire", "Slay the Spire 2", "BTSC.", "BYOK", "Boss", "API" and "Steam" stay Latin.
3. Game words must come from section 1 exactly (力量, 格挡, 易伤, 消耗, 覆甲 ...). Never use a synonym, because the in-game hover tips use these words.
4. 锻造 = our forge. 铸造 = only the Regent's in-game keyword. Never swap them.
5. Prose uses full-width punctuation: ，。：；！？（）and “”. Card text follows section 2 (。 at the end of every sentence, `\n` kept).
6. No spaces between Chinese characters and Latin words, numbers or placeholders (the game writes `Slay the Spire 2伙伴`, `造成{Damage:diff()}点伤害`). Spaces inside a Latin run stay ("Blank the Spire").
7. Numbers are Arabic digits with the right measure word (2张牌, 3点伤害, 1层易伤). Don't use 两 for a counted variable.
8. Address the player as 你 (the game does), not 您. Never write 购买 / 买 for tokens.
9. When a COPY.md entry has `.one` / `.other` plural keys, give both the same Chinese text.
10. When the game has no term (Scry, ignoring Block, our own mechanics), use the section 1 entry marked STS1 convention / UNVERIFIED. If the term is missing, add it here first, then use it.

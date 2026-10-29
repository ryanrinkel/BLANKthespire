# 文案（简体中文）

Simplified Chinese translation of `docs/copy/COPY.md`. Same keys, same order. Terms follow
`docs/copy/GLOSSARY.md`. `Where:` lines are omitted (see COPY.md). Plural pairs give only `.other`; the build
copies it into `.one`. Machine draft 2026-10-27, needs native review before `zh` auto-selects.

## Shared (header, footer, toasts)

### common.brand.name
Notes: 产品名，不翻译。

    Blank the Spire

### common.title_suffix

    {page} — Blank the Spire

### common.nav.back_to_forge

    ← 返回锻造

### common.nav.get_mod

    获取模组 ⬇

### common.nav.archive

    档案馆

### common.nav.help

    帮助

### common.nav.forge_your_own

    锻造你自己的角色 →

### common.nav.back_home

    ← 返回首页

### common.footer.terms

    服务条款

### common.footer.privacy

    隐私政策

### common.footer.support

    支持

### common.footer.get_mod

    获取模组

### common.footer.github

    GitHub

### common.footer.disclaimer

    非官方粉丝项目，与Mega Crit无关，也未获其认可。

### common.dismiss

    关闭

### common.close

    关闭

### common.toast.copied

    已复制！

### common.toast.copy_failed

    复制失败，请手动选中文本。

### common.http_error

    HTTP {status}

## Landing page (landing.html, landing.js, signup-event.js)

### landing.meta.title

    Blank the Spire

### landing.meta.description

    Blank the Spire：为《Slay the Spire 2》（杀戮尖塔2）创造你自己的可玩自制角色！

### landing.meta.og_title

    Blank the Spire — 锻造你自己的《Slay the Spire 2》角色

### landing.meta.og_description

    用一句话描述一个角色，然后在游戏里玩它。也可以直接玩档案馆里的角色，无需注册账号。

### landing.hero.board_label

    Blank the Spire

### landing.hero.board_first_word
Notes: 必须是5个A–Z字母（翻牌板只有5格，只能滚动A–Z），保持英文原样。

    BLANK

### landing.hero.board_words
Notes: 每个词必须是5个A–Z字母（翻牌板限制），保持英文原样。

    FORGE, BUILD, CRAFT, CLIMB, SHAPE, DREAM, BLAZE, STORM, BRAVE, SCALE, SLASH, RAISE, CRAVE, GOOSE, MOOSE

### landing.hero.subtitle
Notes: 与上方英文翻牌板连读成“_____ the Spire”，保持英文。

    the Spire

### landing.hero.pc_note

    《Slay the Spire 2》的免费Steam模组。在任何设备的浏览器上锻造，在PC上游玩。

### landing.hero.tagline

    你会在空白处填上什么？

### landing.hero.cta

    创造你的角色

### landing.hero.signin_note

    永远不需要密码。使用Google、GitHub或邮箱登录，即可锻造并保存你的角色。

### landing.hero.signin_note_webview

    请用邮箱登录：{who}无法使用Google登录。或者点按{menu} → 在{browser}中打开。

### landing.hero.webview_who_app

    {app}内置浏览器

### landing.hero.webview_who_generic

    此应用内浏览器

### landing.event.ribbon.other

    **{label}**：在{when}之前注册，前{count}次锻造由我们请客。

### landing.archive.title

    档案馆

### landing.archive.sub

    其他Blank玩家创造的角色。现在就玩一个，无需注册账号。

### landing.archive.more

    浏览档案馆 →

### landing.how.label

    玩法说明

### landing.how.title

    这到底是怎么回事？？

### landing.how.sub

    只需三步：

### landing.how.step_1_title

    订阅模组

### landing.how.step_1_body

    在[Steam创意工坊](/workshop)订阅Blank the Spire，完全免费。

### landing.how.step_2_title

    玩档案馆里的角色，或者描述你自己的

### landing.how.step_2_body

    从[档案馆](#featured)打开一个角色，或者登录后用大白话讲讲你的点子。机器人霸主会为你打造一个可玩的角色：卡牌、机制、个性，一应俱全。🤖

### landing.how.step_3_title

    把代码粘贴到模组的设置菜单里

### landing.how.step_3_body
Notes: {word}是翻牌板当前的英文单词（Blank、Forge……），与“the Spire”连成英文短语，因此整句保留英文结构。

    重启游戏，然后{word} the Spire！

### landing.pricing.label

    价格

### landing.pricing.title

    要花多少钱？

### landing.pricing.byok

    **自带API密钥（BYOK）**：免费，无限次锻造。支持Anthropic、OpenAI、Google、OpenRouter等，费用由你的服务商向你收取。你的密钥只保存在你的浏览器里。

### landing.pricing.hosted

    **或者让我们用自己的模型来运行。**赞助3美元得2张锻造券，5美元得4张，10美元得10张（结账时另加刷卡手续费）。在我们的模型上，1张锻造券锻造1个角色。

### landing.pricing.free

    **模组免费**且开源，没有任何东西需要付费。没有API密钥时，赞助用来支付锻造券的成本。

## App shell (index.html)

### app.meta.title

    锻造角色

### app.nav.forge

    锻造

### app.nav.library

    我的角色

### app.nav.account

    账号

### app.nav.help

    帮助 ?

### app.nav.help_tip

    角色码要粘贴到哪里？

### app.header.tokens_tip

    选择“使用锻造券”锻造时会消耗锻造券。点“锻造”即可获取。

### app.header.signout

    退出登录

### app.gate.title

    填上空白。

### app.gate.body

    描述可以很详细，也可以很随意。最后你会得到一段角色码，复制它，粘贴到游戏内的模组菜单里。

### app.gate.signin

    登录

### app.gate.get_mod

    获取模组和安装指南

### app.gate.help

    帮助：角色码要粘贴到哪里？

### app.concept.label

    描述你的角色

### app.concept.placeholder

    例如：一位剧毒瘟疫医生，牺牲生命来叠加中毒，再把鲜血化为护甲

### app.concept.lang_label

    角色语言

### app.concept.lang_en

    English

### app.concept.lang_zh

    中文（简体）

### app.concept.lang_hint

    名称和描述会在设计完成后翻译；设计本身用英文进行。

### app.pay.label

    由谁提供算力？

### app.pay.label_hint

    二选一。

### app.pay.token.summary

    使用锻造券

### app.pay.token.get

    获取锻造券

### app.pay.token.unavailable

    目前无法赞助。使用自带API密钥即可继续锻造。

### app.pay.token.byok_hint

    有API密钥？用它锻造完全免费，展开下方的“自带密钥”即可。

### app.byok.summary

    自带密钥

### app.byok.provider_label

    服务商

### app.byok.provider.anthropic

    Anthropic (Claude)

### app.byok.provider.openai

    OpenAI

### app.byok.provider.ollama

    Ollama Cloud

### app.byok.provider.openrouter

    OpenRouter

### app.byok.provider.groq

    Groq

### app.byok.provider.google

    Google Gemini

### app.byok.provider.xai

    xAI (Grok)

### app.byok.provider.deepseek

    DeepSeek

### app.byok.provider.together

    Together

### app.byok.provider.custom

    其他（兼容OpenAI的URL）

### app.byok.key_label

    API密钥

### app.byok.key_placeholder

    粘贴你的密钥

### app.byok.base_url_placeholder

    Base URL，例如 https://api.openai.com/v1

### app.byok.key_safety_link

    你的密钥只保存在此浏览器中

### app.byok.key_safety_body

    我们从不存储你的密钥。它保存在此浏览器里，免得你重复输入（清空输入框即可让浏览器忘记它）。锻造时它会直接发送给你的服务商，绝不会写入我们的数据库或日志。

### app.byok.models_label

    模型

### app.byok.load_models

    加载我的模型列表

### app.byok.design_label

    设计

### app.byok.design_placeholder

    先输入密钥，再加载模型

### app.byok.design_hint

    少量塑造角色的调用。请用你最聪明的模型。

### app.byok.card_label

    卡牌编码

### app.byok.card_same

    与设计模型相同

### app.byok.card_hint

    用严格的JSON写出每一张牌，占了大部分费用。一个靠谱的编码模型就够了。

### app.byok.estimate_link

    估算费用

### app.forge.button

    锻造角色

### app.pay.open_link

    更换算力来源

### app.tutorial.body

    描述一个角色，点“锻造”，复制角色码，粘贴到游戏里（主菜单 → 模组配置 → BlankTheSpire → 导入角色码 → 导入 → 重启游戏）。[带截图的完整指南](/help)

### app.phone_banner.body

    在用手机？尽管锻造，角色会保存在“我的角色”里。在运行《Slay the Spire 2》的电脑上打开blankthespire.com获取角色码，或者用下方按钮发给自己。

### app.advanced.summary

    高级选项

### app.advanced.interactive_label

    交互式锻造

### app.advanced.interactive_hint

    通常，锻造会把你的主题对应到游戏的构筑引擎（即流派）上，并自行挑选最强的组合。开启**交互式锻造**后，主题对应完成时它会暂停一次，列出候选引擎，让你最多挑选两个。你只有很短的时间；如果没有作答，就由锻造替你决定。

### app.progress.title

    锻造中……

### app.choice.prompt

    你来决定：最多选2个引擎作为角色的核心

### app.choice.go

    按我的选择锻造

### app.choice.skip

    让锻造决定

### app.lost.open_library

    打开“我的角色”

### app.result.share

    🔗 复制分享链接

### app.result.share_tip

    复制此角色的公开链接

### app.result.nominate

    ☆ 提名进入档案馆

### app.result.back

    ← 返回锻造

### app.handoff.lede

    在电脑上玩：把角色发送过去：

### app.handoff.send_pc

    📲 发送到我的电脑

### app.handoff.send_pc_tip

    把角色链接分享到你的电脑（AirDrop、信息、备忘录、邮件……）

### app.handoff.email_me

    ✉️ 发邮件给我

### app.handoff.email_me_tip

    把链接和角色码发送到你账号的邮箱

### app.result.code_label

    角色码

### app.result.copy_code

    复制角色码

### app.play.title

    开始游玩

### app.play.step_1

    [在Steam创意工坊订阅模组](/workshop)（只需一次）。

### app.play.step_2

    在《Slay the Spire 2》中：主菜单 → 模组配置 → BlankTheSpire → *导入角色码* → 粘贴 → 导入。

### app.play.step_3

    重启游戏，选择你的角色。

### app.play.where

    要粘贴到哪里？

### app.library.show_art

    显示美术

### app.library.show_art_tip

    隐藏立绘、角色形象和卡图，更快浏览列表

### app.library.empty

    还没有角色，去锻造一个吧！

### app.account.balance_unit

    张锻造券

### app.account.balance_hint

    在我们的模型上，1张锻造券锻造1个角色。自带API密钥的话，锻造免费且不限次数，无需锻造券。

### app.account.donate_hint

    Blank the Spire免费且开源，但每次托管模式的锻造都要我自掏腰包。你的赞助用来支付我们的算力成本。

### app.account.stripe_note

    支付由Stripe处理，我们永远看不到你的银行卡信息。

### app.account.history_title

    赞助记录

### app.account.history_empty

    还没有赞助记录。

### app.account.signin_title

    登录方式

### app.account.signin_hint

    以下任何一种方式都会登录到同一个账号。

### app.account.link_another

    关联其他方式：

### app.feedback.title_card

    这张牌怎么样？

### app.feedback.note_placeholder

    可选：告诉我们原因（你的意见能帮助改进今后的生成）

### app.feedback.submit

    提交反馈

## App JS strings (app.js, render.js)

### app.tokens.chip_unlimited

    ∞张锻造券

### app.tokens.chip.other

    {count}张锻造券

### app.tokens.line_unlimited

    ∞张锻造券：你的账号可以免费锻造。

### app.tokens.line_have.other

    你有{count}张锻造券。

### app.tokens.line_none

    你没有锻造券。在下方获取锻造券，1张锻造券锻造1个角色。

### app.tokens.hide_options

    收起锻造券选项

### app.welcome.text.other

    欢迎！{label}送了你{count}张免费锻造券。1张锻造券锻造1个角色，在下方描述你的角色，然后点“锻造”。

### app.welcome.label_fallback

    注册活动

### app.remix.hint

    正在改编“{name}”：修改描述，然后锻造。

### app.remix.name_fallback

    一个分享的角色

### app.account.identity_row

    {provider}（{label}）

### app.account.identity.google

    Google

### app.account.identity.discord

    Discord

### app.account.identity.github

    GitHub

### app.account.identity.email

    邮箱

### app.account.toast_load_failed

    无法加载你的账号，请检查网络连接。

### app.forge.button_byok

    锻造角色（使用你的API密钥）

### app.forge.button_unlimited

    锻造角色（免费，无限账号）

### app.forge.button_token.other

    锻造角色（消耗1张锻造券，你共有{count}张）

### app.forge.why_byok_list

    输入你的API密钥，然后从服务商的列表里选一个模型。

### app.forge.why_byok

    输入你的API密钥和模型。

### app.forge.why_no_tokens

    你没有锻造券。在下方获取锻造券，或者使用自带密钥。

### app.forge.why_no_mode

    选择支付方式：“使用锻造券”或“自带密钥”。

### app.pay.reason_byok

    输入你的API密钥并选择模型

### app.pay.reason_token

    选择这次锻造的支付方式

### app.forge.toast_no_concept

    请先描述一个角色。

### app.forge.toast_no_tokens

    没有可用的锻造券。在下方获取锻造券，或者使用自带密钥。

### app.forge.confirm_token

    这将消耗1张锻造券。你现有{count}张。要锻造这个角色吗？

### app.forge.toast_load_models

    请先加载你的模型列表并选择一个模型。

### app.forge.toast_need_key

    请输入你的API密钥和模型，或者改用“使用锻造券”。

### app.forge.confirm_byok

    这次锻造的费用会记在你的{provider}密钥上。

    {estimate}

    要锻造这个角色吗？

### app.forge.toast_need_base_url

    请输入你的服务商的Base URL。

### app.forge.err_http_nonjson

    服务器返回了HTTP {status}，没有锻造任何内容，请重试

### app.forge.err_stream_ended

    进度流提前结束了

### app.byok.get_key_at

    在{where}获取密钥

### app.byok.key_from_openai

    platform.openai.com（需要API密钥，不是ChatGPT账号登录）

### app.byok.key_from_custom

    你的服务商

### app.byok.provider_label_custom

    其他

### app.byok.art_chip_yes

    包含美术

### app.byok.art_chip_no

    不生成美术

### app.byok.art_tip_yes

    立绘、角色形象和卡图也会用这个密钥生成。

### app.byok.art_tip_no

    {provider}无法生成图片，所以用这个密钥锻造的角色会使用游戏自带的卡牌涂鸦。

### app.byok.model_placeholder_typed

    模型ID

### app.byok.no_models

    这个密钥没有可用的模型

### app.byok.group_tested

    已测试

### app.byok.group_all

    全部模型

### app.byok.reload_models

    重新加载模型列表

### app.byok.loading

    加载中……

### app.byok.toast_need_key

    请先选择服务商并输入你的API密钥。

### app.byok.toast_saved_gone

    你保存的模型“{model}”在这个密钥上已不再提供，请另选一个。

### app.byok.toast_loaded

    已加载{count}个模型{hidden}。

### app.byok.toast_loaded_hidden
Notes: 英文版以空格开头；中文不需要空格。

    （隐藏了{count}个无法运行锻造的模型）

### app.byok.toast_typed_fallback

    无法列出此端点的模型（{error}），请改为手动输入模型ID。

### app.estimate.title

    每次锻造的预估费用

### app.estimate.total

    合计

### app.estimate.row_design_cards

    设计 + 卡牌

### app.estimate.row_art

    美术

### app.estimate.art_images

    {count}张图片

### app.estimate.art_tip

    {model}：立绘、角色形象和{count}张卡图

### app.estimate.art_tip_model_fallback

    {provider}图像API

### app.estimate.art_none

    此服务商不支持

### app.estimate.art_none_tip

    用这个密钥锻造的角色会使用游戏自带的卡牌涂鸦。

### app.estimate.pick_model

    选择模型

### app.estimate.no_model

    （未选模型）

### app.estimate.tokens_line

    约{calls}次调用 · 约{input}输入（约{cached}命中缓存） · 约{output}输出

### app.estimate.note_fallback

    一次锻造约需50次模型调用、约1.4M输入token，请查看你的服务商的价格。

### app.estimate.note_unpriced

    没有{models}的价格记录，请查看你的服务商的费率。

### app.estimate.note_openrouter

    用OpenRouter密钥生成同样的美术约需{price}。

### app.estimate.note_caching

    按启用提示缓存估算，不启用时最高可达{price}。

### app.estimate.confirm_model

    模型：{model}

### app.estimate.confirm_models

    设计：{design} · 卡牌：{cards}

### app.estimate.confirm_cost

    每次锻造预估 ≈ {total}{split}

### app.estimate.confirm_split
Notes: 英文版以空格开头；中文不需要空格。

    （文本{text} + 美术{art}）

### app.estimate.confirm_unknown

    预估费用：此模型未知。

### app.console.requested

    • 已请求：{mode}{interactive}

### app.console.requested_interactive

     · 交互式

### app.console.done

    ✓ 完成

### app.console.lost

    ✗ 连接中断（{reason}），锻造仍在服务器上继续；正在重新连接……

### app.console.unreachable

    ✗ 无法连接服务器（{reason}）

### app.console.never_started

    ✗ 锻造没有开始

### app.console.done_reconnected

    ✓ 完成（已重新连接）

### app.console.done_open_library

    ✓ 完成，请在“我的角色”中打开

### app.console.choice_timeout

    • 选择超时，由锻造决定

### app.console.picked

    • 你选择了：{picks}

### app.console.skipped

    • 已跳过，由锻造决定

### app.console.pick_failed

    • 选择未能送达，由锻造决定

### app.lost.still_running

    与锻造的连接中断了。手机锁屏或切换网络时会出现这种情况。锻造仍在我们的服务器上运行，完成后此页面会自动接上并显示角色。如果你离开，它也会在“我的角色”里等你。

### app.lost.refund_note

    如果锻造失败，锻造券会自动退还。

### app.lost.toast_reconnecting

    连接中断，正在重新连接锻造……

### app.lost.unreachable

    无法连接服务器（{reason}）。正在检查锻造是否已开始……

### app.lost.toast_unreachable

    无法连接服务器，正在检查你的网络连接……

### app.lost.never_started

    锻造没有开始，所以没有任何消耗。请检查网络连接后重新锻造。

### app.lost.toast_ready

    你的角色已在“我的角色”中准备就绪。

### app.lost.failed_fallback

    锻造失败

### app.lost.refunded_suffix

    ，锻造券已退还。

### app.lost.gave_up

    仍然没有锻造的消息。如果它完成了，会出现在“我的角色”里。

### app.lost.gave_up_token

    仍然没有锻造的消息。如果它完成了，会出现在“我的角色”里；如果失败，锻造券会自动退还。

### app.choice.requested_badge

    你点名要的

### app.choice.needs_vocab

    需要新词汇，部分卡牌可能会被替换

### app.choice.toast_max

    最多选2个，请先取消一个。

### app.choice.timer

    （{seconds}秒后由锻造决定）

### app.result.view_saved

    正在查看已保存的角色

### app.result.view_new

    你的新角色

### app.share.text

    {name}：{description}。来玩：{url}

### app.share.text_no_description

    {name}。来玩：{url}

### app.share.name_fallback

    一个锻造的角色

### app.nominate.featured

    ★ 已入选档案馆

### app.nominate.nominated

    ★ 已提名 · 撤回

### app.nominate.tip_featured

    已入选档案馆

### app.nominate.tip_nominated

    等待审核，点击撤回提名

### app.nominate.tip_nominate

    申请让这个角色在档案馆（公开展示区）中展出

### app.nominate.prompt

    要提名这个角色进入档案馆吗？

    可选：它为什么应该入选？（最多200个字符，只有审核者能看到）

### app.nominate.toast_withdrawn

    提名已撤回。

### app.nominate.toast_nominated

    已提名。如果入选，你会在档案馆里看到它。

### app.common.toast_retry

    没有成功，请重试。

### app.handoff.no_mail_server

    此服务器尚未配置邮件。请使用“发送到我的电脑”，或复制角色码。

### app.handoff.no_email

    此账号没有邮箱地址。请使用“发送到我的电脑”，或复制角色码。

### app.handoff.open_from_library

    请从“我的角色”中打开此角色，再通过邮件发送。

### app.handoff.email_tip

    把链接和角色码发送到{email}

### app.handoff.email_tip_fallback

    你的邮箱

### app.handoff.toast_sent

    已发送到{email}，请在电脑上打开。

### app.handoff.toast_sent_fallback

    你的收件箱

### app.handoff.toast_failed

    邮件没有发出，请改为复制角色码。

### app.result.usage

    这次锻造在你的密钥上用了{calls}次调用 · 输入{input}个token{cached} · 输出{output}个{art}。

### app.result.usage_cached

    （{cached}命中缓存）

### app.result.usage_images.other

     · {count}张图片

### app.result.usage_art_cost

    （${cost}，{kind}）

### app.result.usage_metered

    实际计量

### app.result.usage_est

    估算

### app.library.cards_meta

    {count}张牌 · v{vocab}

### app.library.share

    🔗 分享链接

### app.library.code_tip

    复制游戏内使用的角色码

### app.library.rename

    重命名

### app.library.open

    打开

### app.library.delete

    删除

### app.library.splash_alt

    {name}的立绘

### app.library.sprite_alt

    {name}的角色形象

### app.library.toast_load_failed

    无法加载你的角色，请检查网络连接。

### app.library.rename_prompt

    新名称：

### app.library.delete_confirm

    要删除“{name}”吗？此操作无法撤销。

### app.donate.tier_label.other

    {amount} → {count}张锻造券

### app.donate.fee_line

    实际扣款{gross}，含{fee}刷卡手续费

### app.donate.custom_reveal

    输入其他自定义金额

### app.donate.custom_aria

    自定义金额（美元）

### app.donate.custom_placeholder

    {min}+

### app.donate.custom_button

    获取锻造券

### app.donate.custom_button_n.other

    获取{count}张锻造券

### app.donate.custom_rule

    整数美元，${min}到${max}：每1美元1张锻造券。

### app.donate.toast_bad_amount

    请输入${min}到${max}之间的整数美元金额。

### app.donate.redirecting

    正在跳转……

### app.history.donated_split

    赞助{gross}（{net} + {fee}刷卡手续费）

### app.history.donated

    赞助{gross}

### app.history.pack

    锻造券包，{gross}

### app.history.tokens.other

    +{count}张锻造券 · {date}

### app.history.refunded

    已退款

### app.checkout.toast_canceled

    赞助已取消，没有扣款。

### app.checkout.added.other

    已添加{count}张锻造券

### app.checkout.toast_thanks_draft

    谢谢你！{added}，你的角色可以锻造了。

### app.checkout.toast_thanks

    谢谢你！{added}，可以开始锻造了。

### app.checkout.toast_thanks_plain

    谢谢你！你的赞助已完成。

### app.checkout.toast_processing

    付款处理中，你的余额很快就会更新。

### app.share_sheet.title

    {name} — Blank the Spire

### app.share_sheet.text

    {name}：一个《Slay the Spire 2》角色。在电脑上打开此链接获取角色码。

### app.share_sheet.name_fallback

    一个角色

### app.result.sprite_alt

    {name}的战斗形象

### app.result.feedback_tip

    提供反馈

### app.result.archetype_badge

    ⚙ 流派

### app.result.relic_badge

    ⬦ 核心遗物

### app.result.relic_fallback_title

    核心遗物

### app.relic.mod.max_energy

    最大能量{amount}

### app.relic.mod.first_attack

    首次攻击伤害{amount}

### app.relic.mod.cost_reduction

    卡牌耗能减少{amount}

### app.relic.mod.start_combat_block

    战斗开始时的格挡{amount}

### app.relic.mod.attack_base

    每次攻击的伤害{amount}

### app.relic.mod.max_hp

    最大生命值{amount}

### app.relic.trigger.turn_start

    回合开始

### app.relic.trigger.turn_end

    回合结束

### app.relic.trigger.attacked

    受到攻击时

### app.relic.trigger.on_exhaust

    消耗牌时

### app.relic.trigger.on_card_played

    打出牌时

### app.relic.trigger.combat_end

    战斗结束

### app.relic.trigger.on_card_drawn

    抽牌时

### app.relic.trigger.on_damage_dealt

    造成伤害时

### app.relic.trigger.on_block_gained

    获得格挡时

### app.relic.trigger.on_hp_lost

    失去生命时

### app.relic.trigger.on_type_played

    打出{type}牌时

### app.relic.every_nth

    （每{n}次）

### app.relic.once_per_combat

     · 每场战斗一次

### app.mech.head

    角色机制：这个角色自创的自定义元素。

### app.mech.head_rate

    点击任意一项，查看效果并评分。

### app.mech.badge_orb

    ◉ 充能球

### app.mech.badge_status

    ✦ 状态效果

### app.mech.badge_summon

    ⚔ 召唤物

### app.mech.badge_potion

    🧪 药水

### app.mech.forge_badge
Notes: 这里是储君的游戏内关键词Forge，按术语表用“铸造”，不是我们的产品动词“锻造”。

    ⚒ 铸造

### app.mech.forge_name

    锋芒不减

### app.mech.forge_teaser

    这个角色的铸造计数在战斗之间不会完全重置。

### app.mech.forge_line_1

    每场战斗结束时，最多储存5点铸造

### app.mech.forge_line_2

    下一场战斗的第一个回合会返还这么多铸造（并召唤你的剑）

### app.mech.orb_passive

    生成后每回合

### app.mech.orb_passive_turn_start

    生成后在每个回合开始时

### app.mech.orb_evoke

    激发时

### app.mech.status_hook.damage_dealt

    你的攻击

### app.mech.status_hook.damage_taken

    你受到的伤害

### app.mech.status_hook.block_gained

    你获得的格挡

### app.mech.status_hook.turn_start

    回合开始

### app.mech.status_hook.turn_end

    回合结束

### app.mech.status_hook.energy_gain

    你获得的能量

### app.mech.status_hook.card_draw

    你抽的牌

### app.mech.status_hook.damage_over_time

    其回合开始时失去的生命

### app.mech.status_hook.hit_count

    每次攻击的命中次数

### app.mech.status_buff

    强化

### app.mech.status_debuff

    负面效果

### app.mech.status_line

    {kind}：影响{hook}{mode}

### app.mech.status_multiplicative

    （每层+10%，最多翻倍）

### app.mech.status_decays

    衰减：{decay}

### app.mech.potion_line

    {rarity}药水：{when}可用

### app.mech.potion_any_time

    任何时候

### app.mech.potion_in_combat

    战斗中

### app.mech.potion_drops

    在这个角色的游戏中，会与普通药水一同掉落

### app.mech.summon_ethereal

    虚无（无法被攻击）

### app.mech.summon_max_hp

    最大生命值：{hp}

### app.mech.summon_passive

    被动的爪牙：先召唤它，再用卡牌让它攻击。

### app.mech.summon_each_turn

    每回合：{actions}

### app.mech.summon_turn_n

    第{n}回合：{actions}

### app.mech.summon_on_summon

    召唤时：{actions}

### app.mech.summon_on_death

    死亡时：{actions}

### app.mech.summon_every_nth

    每{n}次命中：{actions}

### app.card.show_upgraded

    显示升级后

### app.card_type.attack

    攻击

### app.card_type.skill

    技能

### app.card_type.power

    能力

### app.rarity.basic

    基础

### app.rarity.common

    普通

### app.rarity.uncommon

    罕见

### app.rarity.rare

    稀有

### app.rarity.token

    衍生

### app.decay.lose_one_eot

    每回合结束时减少1层

### app.decay.lose_all_eot

    回合结束时全部清除

### app.feedback.cat.great

    不错

### app.feedback.cat.overpowered

    好像太强了

### app.feedback.cat.underpowered

    太弱了

### app.feedback.cat.off_theme

    不符合主题

### app.feedback.cat.confusing

    看不懂

### app.feedback.cat.doesnt_work

    不起作用

### app.feedback.title_relic

    这件遗物怎么样？

### app.feedback.title_orb

    这个充能球怎么样？

### app.feedback.title_status

    这个状态效果怎么样？

### app.feedback.title_summon

    这个召唤物怎么样？

### app.feedback.title_potion

    这瓶药水怎么样？

### app.feedback.title_fallback

    这个怎么样？

### app.feedback.rated_tip

    你的评价：{label}，点击修改

### app.feedback.sent_tip

    反馈已发送，点击修改

### app.feedback.toast_thanks

    感谢你的反馈！

## Help page (help.html)

### help.meta.title

    帮助

### help.header.sub

    帮助

### help.intro.title

    角色码要粘贴到哪里？

### help.intro.body
Notes: 游戏内路径统一写作“主菜单 → 模组配置 → BlankTheSpire → 导入角色码 → 导入 → 重启游戏”（句子只需要前几步时从末尾截短）。模组列表显示的是BlankTheSpire（BaseLib找不到mod_title时用命名空间），不是清单里的“Blank the Spire”。“模组配置”是BaseLib自带的简体中文名称（BaseLib localization/zhs/main_menu_ui.json）。

    在游戏里，而不是在这个网站上。先在这里锻造一个角色，复制它的角色码（以`BTSC.`开头），然后在《Slay the Spire 2》中打开主菜单 → **模组配置** → **BlankTheSpire**，在**导入角色码**下方的**角色码**输入框中粘贴，再点**导入**。重启游戏后，你的角色就会出现在角色选择界面。

### help.steps.title

    分步说明

### help.steps.step_1

    **在网站上锻造一个角色，然后点“复制角色码”。**角色码以`BTSC.`开头，以一段简短的哈希结尾，请完整复制。

### help.steps.step_1_alt

    blankthespire.com上的锻造结果，带有“复制角色码”按钮

### help.steps.step_1_caption

    网站上的结果页面：角色码输入框和它的“复制角色码”按钮。

### help.steps.step_2

    **启动《Slay the Spire 2》，打开主菜单 → 模组配置。**（需要先在[Steam创意工坊](/workshop)订阅模组，只需一次）

### help.steps.step_2_alt

    《Slay the Spire 2》主菜单，“模组配置”一项被高亮显示

### help.steps.step_2_caption

    主菜单：“模组配置”一项。

### help.steps.step_3

    **在左侧的已安装模组列表中选择BlankTheSpire。**

### help.steps.step_3_alt

    模组列表中选中了BlankTheSpire，并打开了它的设置

### help.steps.step_3_caption

    模组列表：选择BlankTheSpire，打开它的设置。

### help.steps.step_4

    **把角色码粘贴到“角色码”输入框，然后点“导入”。**（输入框位于*导入角色码*下方；“角色栏位”保持为0，模组会自动为你挑选空栏位）

### help.steps.step_4_alt

    “角色码”输入框中粘贴了一段BTSC角色码，“导入”按钮已就绪

### help.steps.step_4_caption

    已粘贴角色码的“角色码”输入框，随时可以点“导入”。

### help.steps.step_5

    **重启游戏**：在同一界面点**重启游戏（应用更改）**。

### help.steps.step_5_callout

    **必须重启。**导入后模组会立即提醒你。新导入的角色只在游戏启动时加载，在你完全退出并重新启动游戏之前，它**不会**出现在角色选择界面。

### help.steps.step_5_alt

    导入成功后，模组提示需要重启的确认框

### help.steps.step_5_caption

    导入成功后的确认框：先重启，再去找你的角色。

### help.steps.step_6

    **开始新的一局游戏，在角色选择界面选择你的角色。**

### help.steps.step_6_alt

    显示一个锻造角色的角色选择界面

### help.steps.step_6_caption

    角色选择：你锻造的角色和原版角色并列在一起。

### help.trouble.title

    常见问题

### help.trouble.rejected

    **“角色码被拒绝”/“无效代码”。**请确认复制了*完整的*角色码，包括开头的`BTSC.`前缀和最后一个点之后的简短哈希。任何一端被截断的角色码都无法解码。“复制角色码”按钮总是会复制完整内容。

### help.trouble.no_class

    **角色没有出现在角色选择界面。**你没有重启。请完全退出游戏再重新启动，导入的角色只在启动时加载。

### help.trouble.no_mods

    **主菜单里没有“模组配置”／游戏没有加载模组。**模组还没有安装，请查看[获取模组](/download)。

### help.trouble.other

    **其他问题。**请在GitHub上[报告问题](https://github.com/ryanrinkel/BLANKthespire/issues)。如果游戏崩溃了，请附上`%APPDATA%\SlayTheSpire2\logs\godot.log`中的相关内容。

### help.next.title

    下一步

### help.next.forge

    锻造角色

### help.next.get_mod

    获取模组

## Download page (download.html)

### download.meta.title

    获取模组

### download.header.sub

    获取模组

### download.hero.title

    在《Slay the Spire 2》中玩你锻造的角色

### download.hero.lede

    在Steam创意工坊订阅，剩下的交给Steam：不用找文件夹，不用解压，更新也会自动送达。

### download.hero.subscribe

    ⬈ 在Steam创意工坊订阅

### download.hero.step_1

    在创意工坊**订阅**Blank the Spire。

### download.hero.step_2

    **启动《Slay the Spire 2》。**Steam会在游戏启动前下载模组。

### download.hero.step_3

    **模组会自动加载。****BaseLib**（模组加载器）作为创意工坊依赖项会自动一起安装，你永远不需要手动安装它。

### download.hero.requires

    需要Steam版《Slay the Spire 2》。

### download.hero.sidelink

    角色码要粘贴到哪里？→ [带截图的分步说明](/help)

### download.play.title

    锻造角色，开始游玩

### download.play.step_1

    在本网站[锻造一个角色](/app) → 复制**角色码**（以`BTSC.`开头）。

### download.play.step_2

    在游戏中：主菜单 → **模组配置** → **BlankTheSpire** → 粘贴到**导入角色码** → **导入** → **重启游戏**。（[角色码要粘贴到哪里？](/help)）

### download.play.step_3

    开始新的一局游戏，选择你的角色。（加载新角色必须重启，这很正常。）

### download.manual.summary

    手动安装（进阶）：下载zip压缩包

### download.manual.who

    仅适用于无法使用Steam创意工坊的玩家（没有Steam版游戏、电脑离线，或自己手动管理`mods`文件夹）。其他人请直接在上方订阅。

### download.manual.button

    ⬇ 下载 BlankTheSpire-{version}.zip

### download.manual.one_download

    只需下载一次（此zip已附带BaseLib）。解压到游戏的`mods`文件夹即可。

### download.manual.install_title

    安装（一步到位）

### download.manual.step_1

    **找到STS2的`mods`文件夹。**在Steam中：右键点击*Slay the Spire 2* → *管理* → *浏览本地文件*。如果那里没有`mods`文件夹，就新建一个。

### download.manual.step_2

    **把下载的文件解压到这个`mods`文件夹中**，结构如下：

### download.manual.tree

    Slay the Spire 2\
      mods\
        BaseLib\        ← 来自压缩包
        BlankTheSpire\  ← 来自压缩包

### download.manual.step_3

    **启动游戏。**游戏会以加载模组的状态启动。（想确认的话，`%APPDATA%\SlayTheSpire2\logs\godot.log`日志里会写着`RUNNING MODDED`。）

### download.manual.updating

    以后要更新？把新版本解压到同一个文件夹，覆盖旧文件即可。

### download.linux.title

    Linux（Ubuntu / Steam，包括Steam Deck）

### download.linux.lede

    步骤相同：模组不分平台，只是路径不同。原生运行或通过Proton运行都可以。

### download.linux.step_1

    **找到`mods/`：**右键点击*Slay the Spire 2* → *管理* → *浏览本地文件*（原生和Proton都适用）。通常是`~/.steam/steam/steamapps/common/Slay the Spire 2/`或`~/.local/share/Steam/steamapps/common/Slay the Spire 2/`。如有需要，新建一个`mods`文件夹。

### download.linux.step_2

    **解压到其中：**`unzip BlankTheSpire-{version}.zip -d "<game dir>/mods"` → 你会得到`mods/BaseLib/`和`mods/BlankTheSpire/`。

### download.linux.step_3

    **启动。**日志位于你的用户数据目录下，而不是`%APPDATA%`。最快的查找方法：`find ~ -name godot.log 2>/dev/null`。（原生：`~/.local/share/Godot/app_userdata/SlayTheSpire2/logs/`；Proton：在`steamapps/compatdata/2868840/pfx/…/AppData/Roaming/SlayTheSpire2/logs/`中。）

### download.linux.loader_issue

    如果游戏在你的发行版上无法加载模组，那是**BaseLib**（加载器）的问题，与卡牌无关。告诉我，我们一起解决。

### download.starters.title

    入门角色

### download.starters.lede

    第一个角色不必自己锻造：把下面任意一个粘贴到**导入角色码**，马上就能玩。

### download.starters.tempest_name
Notes: 角色码内的角色名是英文数据，游戏里显示英文名，所以标题保留英文。

    The Tempest

### download.starters.tempest_blurb

    —— 呼风唤雨者；生成闪电和冰霜充能球，再一口气释放

### download.starters.jackpot_name

    The Jackpot

### download.starters.jackpot_blurb

    —— 老虎机赌徒；转动转轴、凑齐图案、一把兑现，大起大落

### download.starters.broodmind_name

    The Broodmind

### download.starters.broodmind_blurb

    —— 虫巢女王；召唤虫群，随着族群壮大散播中毒

### download.issues.title

    已知问题（早期版本）

### download.issues.art

    **占位美术**：充能球只是彩色圆圈，部分美术比较通用。仅影响外观。

### download.issues.relics

    **“遗物收集”界面可能出错**：打开游戏内的“遗物收集”图鉴可能会报一个无害的错误。不影响游戏，退出即可。

### download.issues.restart

    **重启才会加载新角色**：模组会提醒你，这很正常。

### download.issues.balance

    锻造的角色**平衡性比较随意**：难免会有忽强忽弱、甚至超标的卡牌。这也是乐趣的一半。

### download.issues.report

    发现了bug或卡死？[提交issue]({github_url}/issues)。如果游戏崩溃了，请附上`%APPDATA%\SlayTheSpire2\logs\godot.log`中的相关内容。

### download.source.title

    源代码与问题反馈

### download.source.body

    Blank the Spire是一个开源的粉丝模组。全部内容（模组、网站、生成器）都在GitHub上。

### download.source.code

    GitHub上的源代码

### download.source.report

    报告问题

## Deck page (deck.html, deck.js)

### deck.meta.title

    {name}

### deck.meta.description

    {description}

### deck.header.sub

    一个锻造的角色

### deck.header.sub_featured

    来自档案馆

### deck.lede

    有人用Blank the Spire锻造了这个角色。复制下面的角色码就能玩，或者[锻造你自己的](/app)。

### deck.lede_featured

    来自档案馆的角色，免费游玩。复制角色码，粘贴到游戏里，或者自己做一个。

### deck.play.send_pc_tip

    把这个角色分享到你的电脑（AirDrop、信息、备忘录、邮件……）

### deck.play.remix

    改编成你自己的版本

### deck.play.title

    已经有模组了？

### deck.play.step_1

    在[Steam创意工坊](/workshop)订阅。

### deck.play.step_2

    在《Slay the Spire 2》中：*主菜单 → 模组配置 → BlankTheSpire → 导入角色码* → 粘贴 → *导入*。

### deck.play.step_3

    重启游戏，选择这个角色。

### deck.play.full_guide

    带截图的完整指南

### deck.dead.title

    这个角色链接已失效

### deck.dead.body

    它可能已被删除，或者链接输错了。请分享者给你一个新链接，或者锻造你自己的角色。

### deck.dead.forge

    锻造你自己的角色

### deck.dead.get_mod

    获取模组

### deck.notfound.title

    找不到角色

### deck.notfound.body

    这个角色链接已失效：它可能已被删除，或者链接输错了。

### deck.rules_in_english

    此处卡牌规则文字以英文显示；游戏内会显示为中文。

## Archive (archive.html, archive.js, featured.js)

### archive.meta.title

    档案馆

### archive.meta.description

    用Blank the Spire锻造的角色，免费游玩。

### archive.lede

    用Blank the Spire锻造的角色，免费游玩。复制角色码，粘贴到游戏里，或者[锻造你自己的](/app)。

### archive.empty

    档案馆里还什么都没有。

### archive.tile.caption
Notes: {word}是翻牌板上的5字母英文单词，与“the Spire”连成英文短语，保留英文。

    {word} the Spire

### archive.tile.splash_alt

    {name}的立绘

### archive.tile.cards

    {count}张牌

## Sign-in pages (signin.html, signin-continue.html, signin-expired.html, signin.js, webview.js)

### signin.meta.title

    登录

### signin.header.sub

    登录

### signin.lede

    选择一种登录方式：我们只会看到它提供的邮箱地址和显示名称。永远不需要密码。

### signin.open_browser

    在{browser}中打开

### signin.none

    此服务器尚未配置登录。

### signin.or

    或

### signin.email.label

    通过邮件获取登录链接

### signin.email.placeholder

    you@example.com

### signin.email.button

    给我发送链接

### signin.email.error

    没有成功，请稍后再试。

### signin.email.sending

    正在发送……

### signin.email.sent

    请查收邮件，链接15分钟后失效。

### signin.try_instead

    只想玩一个？[试试精选角色](/#featured)，无需注册账号。

### signin.back_app

    返回应用

### signin.back_splash

    返回首页

### signin.provider.continue

    使用{provider}继续

### signin.provider.link

    关联{provider}

### signin.link.title

    关联其他登录方式

### signin.link.lede

    你当前以{who}的身份登录。关联后，以后可以用其中任何一种方式登录。

### signin.link.who_fallback

    此账号

### signin.link.all_linked

    此服务器提供的所有登录方式都已关联到你的账号。

### signin.webview.head

    你正在使用{where}，Google无法在这里为你登录。

### signin.webview.where_app

    {app}应用的内置浏览器

### signin.webview.where_generic

    应用内浏览器

### signin.webview.menu_ios

    或者点按右上角的···菜单，选择“在Safari中打开”。

### signin.webview.menu_android

    或者点按右上角的⋮菜单，选择“在Chrome中打开”（或“在浏览器中打开”）。

### signin.webview.email_label

    输入你的邮箱，我们会发送一个链接；它会在{browser}中打开，点开即可登录。

### signin.continue.title

    继续登录

### signin.continue.heading

    再点一下

### signin.continue.body

    你的登录链接验证通过。点击按钮完成登录。

### signin.continue.button

    继续前往Blank the Spire

### signin.continue.expiry

    链接在发送15分钟后失效，且只能使用一次。

### signin.expired.title

    链接已过期

### signin.expired.heading

    这个链接已失效

### signin.expired.body

    这个登录链接已过期或已被使用。请重新申请一个：每个链接有效期15分钟，只能使用一次。

### signin.expired.button

    获取新的登录链接

### signin.code.label

    或者输入邮件中的6位验证码：

### signin.code.hint

    如果链接在别处打开（另一个浏览器，或邮件应用自带的浏览器），就在这里输入验证码。验证码15分钟内有效，只能使用一次。

### signin.code.button

    登录

### signin.code.checking

    正在验证……

### signin.code.wrong

    验证码不正确，请查看最新的一封邮件后重试。

### signin.code.expired

    验证码已过期或已被使用。请在下方重新发送链接。

### signin.code.too_many

    尝试次数过多。请在下方重新发送链接。

### signin.code.resend

    重新发送链接

### signin.continue.code_handoff

    是在另一个浏览器里开始登录的？回到那里输入邮件中的验证码即可。这个按钮只会在当前窗口登录。

## Email

### email.magic.subject

    你的Blank the Spire登录链接

### email.magic.body

    这是你的Blank the Spire登录链接：

    {url}

    此链接15分钟后失效。如果这不是你本人的请求，请忽略这封邮件。

### email.magic.body_code

    这是你的Blank the Spire登录链接：

    {url}

    或者在你开始登录的页面输入此验证码：{code}

    链接和验证码15分钟后失效，且只能使用一次。如果这不是你本人的请求，请忽略这封邮件。

### email.class.subject

    你的《Slay the Spire 2》角色：{name}

### email.class.intro

    这是你在Blank the Spire上锻造的角色：{name}。

### email.class.open_on_pc

    请在运行《Slay the Spire 2》的电脑上打开：

### email.class.paste_code

    或者在游戏中粘贴这段角色码（主菜单 → 模组配置 → BlankTheSpire → *导入角色码* → 导入，然后重启游戏）：

### email.class.no_mod_text

    还没有模组？{url}

### email.class.no_mod_html

    还没有模组？[在Steam创意工坊获取]({url})。

### email.class.footer

    这封邮件是你在“我的角色”页面中申请发送的，我们不会发送其他邮件。

## Server errors

### server.auth.sign_in_required

    需要登录

### server.auth.unknown_provider

    未知的登录方式。

### server.auth.provider_not_configured

    此服务器尚未配置{provider}登录。

### server.auth.email_not_configured

    此服务器尚未配置邮箱登录

### server.auth.check_inbox

    请查收邮件。

### server.csrf

    缺少X-Requested-With请求头（已拦截跨站请求）

### server.not_found

    未找到

### server.forge.no_concept

    请先描述一个角色。

### server.forge.hosted_retired

    托管的Anthropic通道已停用。请使用锻造券，或自带API密钥。

### server.forge.unknown_mode

    未知的锻造模式。

### server.forge.at_capacity

    锻造目前已满负荷，请过几分钟再试。

### server.forge.already_running

    你已经有一次锻造在进行中，请等它完成。

### server.forge.out_of_tokens

    你的锻造券用完了。请在“锻造”按钮下方获取锻造券，或自带API密钥继续锻造。

### server.forge.saving_failed

    已锻造，但保存失败：{e}

### server.forge.too_long

    这次锻造耗时太久，已被放弃，锻造券已退还。如果它最终完成了，角色会出现在“我的角色”里。

### server.forge.too_long_job

    锻造运行超过{max_seconds}秒，已被放弃

### server.forge.restarted

    锻造途中服务器重启了，锻造券已退还

### server.forge.queue_timeout

    锻造满负荷的时间太长，什么都没有锻造（也没有消耗锻造券）。请稍后再试。

### server.forge.unexpected

    意外错误：{e}

### server.forge.no_such_forge

    没有这次锻造。

### server.forge.choice_gone

    这次锻造没有待选的选项，可能已经超时。

### server.forge.not_yours

    这不是你的锻造。

### server.class.name_required

    名称不能为空

### server.email.not_configured

    此服务器尚未配置邮件。请复制角色码，或使用分享链接

### server.email.no_address

    此账号没有邮箱地址。请使用Google、GitHub或邮箱登录后再使用此功能，或改为复制角色码

### server.email.rate_limited

    邮件发得太多了。请一小时后再试，或复制角色码

### server.email.send_failed

    邮件没有发出。请稍后再试，或复制角色码

### server.archive.already_featured

    已在档案馆中

### server.feedback.class_required

    缺少class_id

### server.feedback.unknown_category

    未知的反馈类别

### server.feedback.card_required

    缺少card_id

### server.feedback.unknown_kind

    未知的元素类型

### server.feedback.too_fast

    反馈提交得太快了，请过一会儿再试。

### server.feedback.card_missing

    角色中找不到这张牌

### server.feedback.element_missing

    角色中找不到这个元素

### server.feedback.not_recorded

    无法记录反馈

### server.billing.unavailable

    目前无法赞助。

### server.billing.both

    请选择一个档位或输入自定义金额，不能同时提交。

### server.billing.custom_range

    自定义金额须为${CUSTOM_MIN_DOLLARS}到${CUSTOM_MAX_DOLLARS}之间的整数美元。

### server.billing.pick_tier

    请选择一个赞助金额。

### server.billing.checkout_failed

    无法开始结账，请过一分钟再试。

### server.billing.session_required

    缺少session_id

### server.billing.unknown_session

    未知的结账会话

### server.billing.not_your_session

    这不是你的结账会话

### server.byok.model_not_offered

    你的服务商在这个密钥上没有名为“{m}”的模型。请重新加载模型列表，并从中选择一个。

### server.byok.refusal.model_not_found

    你的服务商在这个密钥上没有名为“{model}”的模型。请展开“自带密钥”，点击“重新加载模型列表”，从列表中选择一个（同时确认服务商与密钥对应）。

### server.byok.refusal.openrouter_routing

    在你的账号设置下，OpenRouter没有可以路由此模型的服务商。请在openrouter.ai检查Settings → Privacy（免费模型需要启用允许数据共享的服务商），或者换一个模型。

### server.byok.refusal.no_credits

    你的服务商账号余额不足，因此拒绝了请求。请在服务商的账单页面充值后重新锻造，这里没有产生任何费用。

### server.byok.refusal.bad_key

    你的服务商拒绝了这个API密钥。请从服务商的控制台粘贴一个有效的密钥（并确认服务商下拉菜单与密钥来源一致）。

### server.byok.refusal.forbidden

    你的服务商表示这个密钥无权使用该模型或端点。请在服务商的控制台检查密钥权限，或者换一个模型。

### server.byok.refusal.request_too_large

    你的服务商套餐限制了单个请求每分钟可发送的token数量，而一次锻造的提示词超过了这个上限，所以重试也没用。请在服务商账号中升级套餐（Groq：Settings → Billing → Plans → Developer），或者换用其他服务商的密钥锻造。

### server.byok.refusal.rate_limited

    你的服务商对这个密钥进行了限速。请等一分钟再锻造，或者在服务商账号中提高限额。

### server.byok.refusal_suffix
Notes: 英文版以空格开头；中文不需要空格。

    （你的服务商返回：{raw[:300]}）

### server.byok.not_generated

    角色未能生成：{tail}

### server.byok.url_scheme

    Base URL必须以http://或https://开头。

### server.byok.url_host

    Base URL需要包含主机名。

### server.byok.url_resolve

    无法解析{parsed.hostname}。

### server.byok.url_private

    Base URL指向私有或内部地址，请使用公开的服务商端点。

### server.byok.anthropic_incomplete

    Anthropic BYOK需要同时提供api_key和model。

### server.byok.anthropic_unavailable

    Anthropic生成不可用：{e}

### server.byok.incomplete

    BYOK需要同时提供base_url、api_key和model。

### server.byok.server_anthropic_retired

    服务器端的Anthropic通道已停用。请使用锻造券，或自带API密钥。

### server.byok.no_path

    未选择生成通道（需要BYOK密钥、锻造券或fake）。

### server.byok.list_needs_key

    列出模型需要同时提供Base URL和API密钥。

### server.byok.list_http

    端点返回了HTTP {e.code}，请检查密钥、URL和模型权限。

### server.byok.list_unreachable

    无法连接端点：{e.reason}

### server.forge.concept_empty

    构想为空。

### server.forge.hosted_unavailable

    托管生成不可用：{e}

## Stripe checkout

### stripe.line_item.donation

    赞助 — Blank the Spire

### stripe.line_item.fee

    刷卡手续费

## Steam Workshop

### workshop.title
Notes: 标题保留“Blank the Spire”，后接中文标语。

    Blank the Spire — 一句话锻造一个角色

### workshop.description

    [h1]为《Slay the Spire 2》打造的可玩自制角色！[/h1]

    在[url=https://blankthespire.com]blankthespire.com[/url]用日常语言描述一个角色，比如[i]“一位剧毒瘟疫医生，牺牲生命来叠加中毒，再把鲜血化为护甲”[/i]，锻造就会把它变成一个真正可玩的《Slay the Spire 2》角色，拥有自己的卡牌、遗物、机制、药水和个性。你会得到一段角色码，粘贴到游戏里就能玩。

    [b]非官方粉丝模组。与Mega Crit无关，也未获其认可。[/b]

    [h2]玩法[/h2]
    [olist]
    [*]订阅此模组（BaseLib是依赖项，会自动安装）。
    [*]前往[url=https://blankthespire.com]blankthespire.com[/url]锻造一个角色，你会得到一段以[b]BTSC.[/b]开头的角色码。（没时间锻造？网站上列出了现成的入门角色，直接复制即可。）
    [*]在游戏中：主菜单 → 模组配置 → BlankTheSpire → 把角色码粘贴到[b]导入角色码[/b] → 导入 → 重启游戏。
    [*]开始新的一局游戏，选择你锻造的角色。
    [/olist]

    锻造在网站上进行，而不是在这个模组里。自带LLM API密钥即可随意锻造，也可以使用网站托管的模型。这个创意工坊物品免费且开源，不含任何付费内容。你也可以随时访问网站，玩其他玩家的角色。

    [h2]透明度说明：AI生成内容[/h2]
    锻造的角色（卡牌文字、名称、立绘）由网站上的AI应你的要求生成，只会通过你的角色码进入游戏。这个创意工坊包本身不含任何AI生成的素材：它只包含人工编写的模组运行时，以及生成器被允许使用的机制词汇表。生成过程受该词汇表约束并经过结构校验，因此锻造的角色保证可以加载和游玩。

    [h2]已知问题（早期版本）[/h2]
    [list]
    [*]部分地方使用占位美术：充能球只是纯色圆圈，部分卡图比较通用。
    [*]游戏内的“遗物收集”图鉴可能会报一个无害的模组加载器错误；退出后继续玩即可。
    [*]导入角色后必须重启游戏：模组会提醒你，这很正常。
    [*]平衡性有意放得很宽：偶尔会出现忽强忽弱、甚至强得离谱的卡牌。坏了什么，请告诉我们。
    [/list]

    [h2]反馈与源代码[/h2]
    bug、卡死或坏掉的卡牌：请[url=https://github.com/ryanrinkel/BLANKthespire/issues]在GitHub上提交issue[/url]。模组开源（MIT），地址为[url=https://github.com/ryanrinkel/BLANKthespire]github.com/ryanrinkel/BLANKthespire[/url]。其中不包含任何游戏代码、二进制文件或受版权保护的游戏数据，你需要拥有《Slay the Spire 2》。

### workshop.change_note

    恢复了预览截图（模组无改动；仍为v0.4.0）。

## In-game mod UI

### mod.manifest.name

    Blank the Spire

### mod.manifest.description

    一个数据驱动、可由LLM扩展的《Slay the Spire 2》自定义角色。

### mod.section.import

    导入角色码

### mod.section.apply

    应用更改

### mod.button.import
Notes: BaseLib按钮宽度固定为324px，文字要非常短。

    导入

### mod.button.clear_slot

    清除栏位

### mod.button.clear_all

    全部清除

### mod.button.restart

    重启游戏

### mod.settings.class_code

    角色码

### mod.settings.class_slot

    角色栏位（0 = 自动）

### mod.settings.import_title

    将角色导入栏位

### mod.settings.import_tip

    将来自blankthespire.com的角色码（BTSC）粘贴到“角色码”栏中，然后按“导入”。栏位0会自动选择：更新同名角色，或占用编号最小的空栏位。

### mod.settings.clear_title

    清除一个角色栏位

### mod.settings.clear_tip

    移除所选栏位中的锻造角色。请先将上方的“角色栏位”设为1或更大。

### mod.settings.clear_all_title

    删除所有锻造角色

### mod.settings.clear_all_tip

    一次性移除所有已导入的角色。此操作无法撤销。

### mod.settings.restart_title

    重启游戏（应用更改）

### mod.settings.restart_tip

    关闭游戏并通过Steam自动重新打开。导入或清除的角色只有在重启后才会生效。

### mod.dialog.import_title

    导入角色

### mod.dialog.import_empty

    请先将角色码粘贴到上方的“角色码”栏中。

### mod.dialog.import_failed_title

    导入失败

### mod.dialog.wrong_type_title

    代码类型错误

### mod.dialog.wrong_type_body

    这不是角色码。请粘贴来自blankthespire.com的角色码（BTSC）。

### mod.dialog.rejected_title

    导入被拒绝

### mod.dialog.rejected_body

    代码已解码，但这个角色无法在此游玩：
    {err}

### mod.dialog.imported_title

    角色已导入

### mod.dialog.imported_body

    已导入到角色栏位{slot}。

    请按下方的“重启游戏”，然后在角色选择界面选择该角色。

### mod.dialog.clear_title

    清除角色

### mod.dialog.clear_need_slot

    请先将上方的“角色栏位”设为要清除的栏位（1..{max}），然后再点击一次。

### mod.dialog.cleared

    已清除角色栏位{slot}。
    请按“重启游戏”以更新游戏。

### mod.dialog.already_empty

    角色栏位{slot}本来就是空的。

### mod.dialog.clear_all_title

    清除所有锻造角色

### mod.dialog.clear_all_body

    已移除{n}个锻造角色。空的角色栏位会保持隐藏。
    请按“重启游戏”以更新游戏。

### mod.dialog.restart_title

    重启

### mod.dialog.restart_nothing

    本次运行中尚未导入任何角色。
    （重启仍会应用之前导入的角色。）

### mod.dialog.restart_failed

    无法自动重新启动：
    {err}

    请退出并自行重新启动游戏以应用更改。

### mod.codec.empty

    代码为空。

### mod.codec.not_bts

    这不是Blank the Spire的代码。

### mod.codec.bad_magic

    这不是Blank the Spire的代码（BTS1/BTSC）。

### mod.codec.bad_version

    代码格式错误（版本字段无效）。

### mod.codec.needs_update

    这个代码需要更新版本的Blank the Spire（代码为v{ver}，本模组支持v{max}）。请更新模组。

### mod.codec.corrupted

    代码已损坏（{err}）。

### mod.codec.checksum

    代码已损坏（校验和不匹配——请重新复制）。

### mod.import.slots_full

    所有{n}个角色栏位都已占满——请先清除一个。

### mod.import.write_failed

    写入角色文件失败：{err}

## Forge console stage headers

### console.start

    开始……

### console.start_interactive

    开始……（交互式锻造：映射阶段之后由你挑选引擎）

### console.queue.busy

    锻造繁忙：你正在排队，位置第{last_pos}位（你的位置已保留，请稍候）……

### console.queue.position

    排队中：第{pos}位……

### console.queue.turn

    轮到你了，正在锻造……

### console.stage.harness
Notes: 版本标记；条件后缀“ [creative harness v2]”由{rest}原样带过。

    锻造框架 v{_harness}（词汇 v{VOCAB_VERSION}）

### console.stage.front_end

    正在运行分阶段的创意前端...

### console.stage.cloud

    [1/6] 联想云：围绕'{concept}'自由联想头脑风暴...

### console.stage.map

    [2/6] 映射：把每条思路对应到游戏的机制流派...

### console.stage.your_call

    [2.5/6] 你来决定：从匹配到的引擎中最多挑选2个作为核心...

### console.stage.compose
Notes: {fuse_desc}是英文代码里的短语（“three archetypes in a tension triangle”等），目前不经翻译，会以英文出现。

    [3/6] 构思：勾勒{len(dossier.candidates)}个角色设定，每个都融合了{fuse_desc}：

### console.stage.pick

    [4/6] 挑选：比较候选设定的独特性，选出最大胆且可实现的一个...

### console.stage.relic_intent

    [5/6] 遗物：设计体现这套构筑的核心遗物...

### console.stage.orbs

    [5/6] 充能球：决定这个角色生成什么（自创充能球还是基础元素）...

### console.stage.blueprint

    [6/6] 蓝图：把'{chosen.name}'转化为卡牌简述、卡池和数值...

### console.stage.blueprint_ready

    蓝图就绪：'{bp['name']}'（{bp.get('max_hp', '?')} HP），围绕{_arche}构建 - 现在逐张设计{len(bp['cards'])}张牌：

### console.card.designing
Notes: 稀有度和类型是英文原始值（Common、Attack……），保持原样。

    第{i+1}/{total}张牌：正在设计'{plan.get('name_hint', '?')}' - {plan.get('rarity', '?')} {plan.get('type', '?')}，耗能{plan.get('cost', '?')}

### console.card.ready

    第{i+1}/{total}张牌：{pres.card.get('name')}已完成（{pres.card.get('rarity')} {pres.card.get('type', '')}）

### console.stage.relic

    正在设计核心初始遗物...

### console.relic.ok

    遗物通过：{relic.get('name')}

### console.relic.fallback

    修复后遗物仍无效；不附带锻造遗物（默认使用燃烧之血）：

### console.done.bundle

    组装完成：{len(cards)}张牌，初始牌组{sum(d['count'] for d in starting_deck)}张牌

### console.art.cards_start

    卡图：{total}张牌……

### console.art.cards_progress

    卡图 {done}/{total}……

### console.art.cards_packed

    卡图：已打包{len(made)}/{total}张卡图

### console.fail.front_end

    前端失败：{e}

### console.fail.too_few_cards

    存活的卡牌太少；终止角色锻造

### console.loc.concept

    构思已译为英文：{text}

### console.loc.translating

    正在翻译角色的名称和描述…

### console.loc.done

    翻译（{locale}）：{len(kept)}/{len(strings)} 条

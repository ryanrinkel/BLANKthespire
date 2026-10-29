# Copy source of truth

This file holds every user-facing English string on the Blank the Spire website, its Steam Workshop page, the
mod's in-game settings screen and the headline lines of the forge console. Each string has one stable key and
its current text, copied verbatim from the code on 2026-10-27, so it can be rewritten here first. A later build
step turns this file into `web/static/i18n/en.json` (and a Chinese sibling file into `zh.json`). Until that step
exists, the code is still what ships: editing a string here does not change the site by itself.

How to edit: change only the indented text under a key. Leave the `### key` line, the `Where:` line and the
`Notes:` line alone unless the string moved. To add a string, add a new `###` entry under the right section and
pick a new key; never reuse or rename an old key (translations hang off it). Paths in `Where:` are relative to
`web/` for the website (`static/...`, `app.py`, `auth.py`, `billing.py`, `forge.py`) and relative to the repo
root for everything else (`mod/...`, `generation/...`, `workshop/...`).

## Conventions
- One entry per string. Key = `page.section.item`, lowercase, dots only, stable forever.
- The text block is the string. Inline markup allowed: **bold**, *italic*, [link text](url), `code`. Line breaks inside a block are paragraph breaks.
- `{name}` placeholders are runtime values (counts, card names, the user's concept). Keep them verbatim and in every translation.
- Never say "buy" (donation framing: tokens are "a thank-you"; see docs/plans/PRICING_V3_COPY.md). Use something like 'get tokens' instead of 'buy tokens'.
- Text blocks are indented 4 spaces. A blank line between paragraphs inside a block also carries the 4-space indent, so a block ends at the first line that is not indented.
- Plurals: where the code builds "token" / "tokens" from a count, the entry is split into `.one` (count is 1) and `.other` (every other count). A Chinese file can give both the same text.
- One text used in several places with the same role shares one key; its `Where:` line lists every place.
- Leading and trailing spaces matter in fragment entries (they are glued to other strings); they are called out in Notes.
- The Workshop description is BBCode and stays BBCode (do not convert it to the markup above).
- Forge console entries (last section) are Python templates: `{...}` there is a Python expression, not a simple name. Rewrite the words around them, never the braces.

## Voice
- tone: second person, present tense, short sentences, an em dash for the aside; a little playful ("Robot Overlords", "That's half the fun").
- how we refer to the mod: Blank the Spire; the game's own mod list shows "BlankTheSpire".
- how we refer to the game: "Slay the Spire 2" in full; "STS2" acceptable when need shorthand, in the Linux install steps.
- how we refer to tokens: "Get a forge token", "one token forges one class"; never "buy" (the only "buy" today is "there is nothing to buy").
- how we refer to the thing a player makes: a "class" they "forge"; it gives an "import code" / "class code" that starts with `BTSC.`; the public showcase is "The Archive".
- how we refer to the in-game path: "main menu → Mod Configuration → BlankTheSpire → Import a class code → Import → Restart game", one spelling everywhere (see Notes on `help.intro.body`). Shorten by dropping hops, never by renaming one.

## Shared (header, footer, toasts)

### common.brand.name
Where: static/index.html:14 (header sub); static/help.html:24, static/download.html:31, static/deck.html:30, static/archive.html:25, static/signin.html:14, static/signin-continue.html:14, static/signin-expired.html:14 (header brand)
Notes: product name; never translated.

    Blank the Spire

### common.title_suffix
Where: every page's `<title>` except the landing page (e.g. static/help.html:6)
Notes: {page} is the page's own title key (help.meta.title, download.meta.title, ...).

    {page} — Blank the Spire

### common.nav.back_to_forge
Where: static/help.html:26; static/download.html:33 (header nav link)

    ← Back to Forge

### common.nav.get_mod
Where: static/index.html:20; static/help.html:27; static/deck.html:34; static/archive.html:28 (header nav link)

    Get the mod ⬇

### common.nav.archive
Where: static/index.html:18; static/help.html:28; static/download.html:35; static/deck.html:32 (header nav link)

    The Archive

### common.nav.help
Where: static/download.html:34; static/archive.html:29 (header nav link); footers of download, deck, archive pages

    Help

### common.nav.forge_your_own
Where: static/deck.html:33; static/archive.html:27 (header nav link)

    Forge your own →

### common.nav.back_home
Where: static/signin.html:15; static/signin-continue.html:15; static/signin-expired.html:15 (header nav link)

    ← Back home

### common.footer.terms
Where: every page's footer (e.g. static/landing.html:96)

    Terms

### common.footer.privacy
Where: every page's footer (e.g. static/landing.html:96)

    Privacy

### common.footer.support
Where: every page's footer (e.g. static/landing.html:97)
Notes: mailto link.

    Support

### common.footer.get_mod
Where: static/help.html:122 (footer)

    Get the mod

### common.footer.github
Where: static/help.html:123; static/download.html:156; static/deck.html:88; static/archive.html:46 (footer)

    GitHub

### common.footer.disclaimer
Where: static/landing.html:98; static/help.html:125; static/download.html:158; static/deck.html:90; static/archive.html:48; static/signin.html:67; static/signin-continue.html:36; static/signin-expired.html:36 (footer note)

    Unofficial fan project — not affiliated with or endorsed by Mega Crit.

### common.dismiss
Where: static/index.html:48, 175, 184 (aria-label on the × buttons)
Notes: screen-reader label only.

    Dismiss

### common.close
Where: static/index.html:474 (aria-label on the feedback popup ×)
Notes: screen-reader label only.

    Close

### common.toast.copied
Where: static/render.js:824 (toast)

    Copied!

### common.toast.copy_failed
Where: static/render.js:825 (toast)

    Copy failed — select the text manually.

### common.http_error
Where: static/app.js:879, 1109, 1146, 1595, 1649, 1941; static/render.js:493 (error fallback when the server sent no message)
Notes: {status} = HTTP status number.

    HTTP {status}

## Landing page (landing.html, landing.js, signup-event.js)

### landing.meta.title
Where: static/landing.html:6 (title); og:site_name static/landing.html:9

    Blank the Spire

### landing.meta.description
Where: static/landing.html:7 (meta description)

    Blank the Spire: Create your own custom, playable classes for Slay the Spire 2!

### landing.meta.og_title
Where: static/landing.html:10 (og:title); static/landing.html:15 (twitter:title)

    Blank the Spire — forge your own Slay the Spire 2 class

### landing.meta.og_description
Where: static/landing.html:11 (og:description); static/landing.html:16 (twitter:description)

    Describe a class in a sentence and play it in-game. Or play a class from The Archive — no account needed.

### landing.hero.board_label
Where: static/landing.html:26 (aria-label on the split-flap board)
Notes: screen-reader label for the five-tile board.

    Blank the Spire

### landing.hero.board_first_word
Where: static/landing.js:8 (FIRST, the word the board lands on first)
Notes: exactly five letters A–Z: the board has five tiles and rolls only through A–Z. A translation cannot use other characters without changing landing.js.

    BLANK

### landing.hero.board_words
Where: static/landing.js:9-13 (WORDS, the idle loop)
Notes: comma-separated list; each word exactly five letters A–Z and reads as "_____ the Spire". GOOSE / MOOSE / CRAVE are featured classes' words.

    FORGE, BUILD, CRAFT, CLIMB, SHAPE, DREAM, BLAZE, STORM, BRAVE, SCALE, SLASH, RAISE, CRAVE, GOOSE, MOOSE

### landing.hero.subtitle
Where: static/landing.html:28 (p.splash-sub under the board)

    the Spire

### landing.hero.pc_note
Where: static/landing.html:31 (p.splash-pc)
Notes: says "PC" first on purpose: ad visitors arrive on phones.

    A free mod for Slay the Spire 2 on Steam. Forge from your browser on any device; play on your PC.

### landing.hero.tagline
Where: static/landing.html:33 (p.splash-tag)

    How will you fill in the Blank?

### landing.hero.cta
Where: static/landing.html:38 (primary button)
Notes: button label, keep short.

    Create Your Own Class

### landing.hero.signin_note
Where: static/landing.html:42 (p#splash-note under the button)

    No passwords, ever. Sign in with Google, GitHub or email to forge and keep your classes.

### landing.hero.signin_note_webview
Where: static/landing.js:139-140 (replaces landing.hero.signin_note inside an in-app browser)
Notes: built from fragments. {who} = landing.hero.webview_who_app or landing.hero.webview_who_generic; {menu} = "···" on iOS, "⋮" on Android; {browser} = "Safari" (iOS) or "Chrome" (Android).

    Sign in by email — {who} can't do Google sign-in. Or tap {menu} → Open in {browser}.

### landing.hero.webview_who_app
Where: static/landing.js:138
Notes: {app} = the app name detected from the user agent or utm_source (YouTube, Instagram, Facebook, Discord, Reddit, TikTok, Snapchat, LinkedIn).

    the {app} browser

### landing.hero.webview_who_generic
Where: static/landing.js:138

    this in-app browser

### landing.event.ribbon.one
Where: static/signup-event.js:45-46 (the sign-up event ribbon, above the landing button and under the /login lede)
Notes: shown only to signed-out visitors while a sign-up event is live. Built from fragments: {label} is the event's admin-typed label (bold, shown as is, not translated); {when} = the end time in the viewer's locale ("Mon, Nov 2, 6:00 AM"). This is the 1-token variant.

    **{label}**: sign up before {when} and your first forge is on us.

### landing.event.ribbon.other
Where: static/signup-event.js:45-46
Notes: as above; {count} = tokens per signup (2 or more).

    **{label}**: sign up before {when} and your first {count} forges are on us.

### landing.archive.title
Where: static/landing.html:48 (h2); static/landing.html:47 (section aria-label)

    The Archive

### landing.archive.sub
Where: static/landing.html:49 (p.how-sub)

    Classes from other Blankers. Play one now — no account needed.

### landing.archive.more
Where: static/landing.html:51 (link to /archive)

    Browse The Archive →

### landing.how.label
Where: static/landing.html:54 (section aria-label)
Notes: screen-reader label only.

    How it works

### landing.how.title
Where: static/landing.html:55 (h2)

    What is going on here??

### landing.how.sub
Where: static/landing.html:56 (p.how-sub)

    Three steps:

### landing.how.step_1_title
Where: static/landing.html:62 (h3)

    Subscribe to the mod

### landing.how.step_1_body
Where: static/landing.html:63 (p)

    Grab Blank the Spire on the [Steam Workshop](/workshop) — it’s free.

### landing.how.step_2_title
Where: static/landing.html:70 (h3)

    Play a class from The Archive — or describe your own

### landing.how.step_2_body
Where: static/landing.html:71-72 (p)

    Open one from [The Archive](#featured), or sign in and explain your idea in plain language. Robot Overlords build a playable class — cards, mechanics, identity and all. 🤖

### landing.how.step_3_title
Where: static/landing.html:79 (h3)

    Paste the code into the mod’s settings menu

### landing.how.step_3_body
Where: static/landing.html:80 (p)
Notes: {word} is the board's current word in title case ("Blank", "Forge", ...), kept in sync by landing.js setFill (static/landing.js:73); starts as "Blank".

    Restart the game, and {word} the Spire!

### landing.pricing.label
Where: static/landing.html:86 (section aria-label)
Notes: screen-reader label only.

    Pricing

### landing.pricing.title
Where: static/landing.html:87 (h2)

    What does it cost?

### landing.pricing.byok
Where: static/landing.html:89 (li)

    **Bring your own API key** — free, unlimited forging. Anthropic, OpenAI, Google, OpenRouter and more; your provider bills you. Your key stays only in your browser.

### landing.pricing.hosted
Where: static/landing.html:90 (li)
Notes: the tier amounts are typed here by hand; they must match billing.py _LIVE_TIERS (t3/t5/t10). The custom $11+ amount is not mentioned.

    **Or let us run it on our models.** $3 → 2 tokens, $5 → 4, $10 → 10 (card fee added at checkout). One token forges one class on our models.

### landing.pricing.free
Where: static/landing.html:91 (li)
Notes: the one place the site says "buy" (as "nothing to buy").

    **The mod is free** and open source — there is nothing to buy. Donations cover the cost of tokens when you run them without an API key.

## App shell (index.html)

### app.meta.title
Where: static/index.html:6 (title, before common.title_suffix); static/index.html:14 (header brand, bold)

    Forge a Class

### app.nav.forge
Where: static/index.html:16 (tab button)

    Forge

### app.nav.library
Where: static/index.html:17 (tab button); static/index.html:280 (h2 of the My Classes view)

    My Classes

### app.nav.account
Where: static/index.html:19 (tab button); static/index.html:293 (h2 of the Account view)

    Account

### app.nav.help
Where: static/index.html:21 (tab link)

    Help ?

### app.nav.help_tip
Where: static/index.html:21 (title tooltip on the Help tab)

    Where do I paste my class code?

### app.header.tokens_tip
Where: static/index.html:23 (title tooltip on the token chip)

    Tokens are spent by the 'Use a token' forge option. Press Forge to get one.

### app.header.signout
Where: static/index.html:25 (button)

    Sign out

### app.gate.title
Where: static/index.html:31 (h1, signed-out gate)

    Fill in the Blank.

### app.gate.body
Where: static/index.html:32 (p, signed-out gate)

    Be as detailed or as vague as you like. At the end you will get a code. Copy the code it generates to paste into the mod menu in-game.

### app.gate.signin
Where: static/index.html:33 (primary button)

    Sign in

### app.gate.get_mod
Where: static/index.html:34 (button); static/signin.html:59 (button)

    Get the mod & install guide

### app.gate.help
Where: static/index.html:35 (button)

    Help — where does my code go?

### app.concept.label
Where: static/index.html:59 (label for the concept box)

    Describe your class

### app.concept.placeholder
Where: static/index.html:61 (textarea placeholder)
Notes: the same example sentence opens the Workshop description.

    e.g. a venomous plague doctor who sacrifices health to stack poison, then turns blood into armor

### app.concept.lang_label
Where: static/index.html (label of the per-forge language selector under the concept box)
Notes: added 2026-10-27 by the i18n build, owner to review

    Class language

### app.concept.lang_en
Where: static/index.html (option in the per-forge language selector)
Notes: added 2026-10-27 by the i18n build, owner to review. Each option names its language in that language.

    English

### app.concept.lang_zh
Where: static/index.html (option in the per-forge language selector)
Notes: added 2026-10-27 by the i18n build, owner to review. Each option names its language in that language.

    中文（简体）

### app.concept.lang_hint
Where: static/index.html (hint under the selector; app.js shows it only when the class language is not English)
Notes: added 2026-10-27 by the i18n build, owner to review

    Names and descriptions are translated after the design; the design itself runs in English.

### app.pay.label
Where: static/index.html:73 (p.lbl above the two pay boxes)

    Who provides your compute?

### app.pay.label_hint
Where: static/index.html:73 (muted span after app.pay.label)

    Pick one.

### app.pay.token.summary
Where: static/index.html:77 (details summary)

    Use a token

### app.pay.token.get
Where: static/index.html:84 (button); static/app.js:165 (same button, folded state); static/index.html:300 (h2 on the Account view)

    Get a forge token

### app.pay.token.unavailable
Where: static/index.html:91 (forge tab note); static/index.html:306 (Account view note)
Notes: shown when Stripe is switched off.

    Donations aren't available right now — bring your own API key to keep forging.

### app.pay.token.byok_hint
Where: static/index.html:93 (hint)

    Have an API key? Forging with it is free — open “Bring your own key” below.

### app.byok.summary
Where: static/index.html:97 (details summary)

    Bring your own key

### app.byok.provider_label
Where: static/index.html:100 (label)

    Provider

### app.byok.provider.anthropic
Where: static/index.html:102 (select option)
Notes: brand name.

    Anthropic (Claude)

### app.byok.provider.openai
Where: static/index.html:103 (select option)
Notes: brand name.

    OpenAI

### app.byok.provider.ollama
Where: static/index.html:104 (select option)
Notes: brand name.

    Ollama Cloud

### app.byok.provider.openrouter
Where: static/index.html:105 (select option)
Notes: brand name.

    OpenRouter

### app.byok.provider.groq
Where: static/index.html:106 (select option)
Notes: brand name.

    Groq

### app.byok.provider.google
Where: static/index.html:107 (select option)
Notes: brand name.

    Google Gemini

### app.byok.provider.xai
Where: static/index.html:108 (select option)
Notes: brand name.

    xAI (Grok)

### app.byok.provider.deepseek
Where: static/index.html:109 (select option)
Notes: brand name.

    DeepSeek

### app.byok.provider.together
Where: static/index.html:110 (select option)
Notes: brand name.

    Together

### app.byok.provider.custom
Where: static/index.html:111 (select option)

    Other (OpenAI-compatible URL)

### app.byok.key_label
Where: static/index.html:115 (label)

    API key

### app.byok.key_placeholder
Where: static/index.html:116 (input placeholder)

    Paste your key

### app.byok.base_url_placeholder
Where: static/index.html:119 (input placeholder, "Other" provider only)

    Base URL — e.g. https://api.openai.com/v1

### app.byok.key_safety_link
Where: static/index.html:125 (link-style button)

    Your key stays in this browser

### app.byok.key_safety_body
Where: static/index.html:126-128 (hint revealed by app.byok.key_safety_link)
Notes: must stay TRUE: the key is in this browser's localStorage, reaches our server only inside the forge / model-list request, and is never written to the database or logs.

    We never store it. It's kept in this browser so you don't have to retype it (clear the box to forget it), and when you forge it goes straight to your provider — it's never written to our database or our logs.

### app.byok.models_label
Where: static/index.html:136 (label)

    Models

### app.byok.load_models
Where: static/index.html:137 (link-style button); static/app.js:731 (same button before a list is loaded)

    Load my model list

### app.byok.design_label
Where: static/index.html:141 (label); static/app.js:429 (row label in the cost estimate)

    Design

### app.byok.design_placeholder
Where: static/index.html:142 (disabled select option); static/app.js:682

    Enter your key, then load models

### app.byok.design_hint
Where: static/index.html:143 (hint)

    A few calls that shape the class. Use your smartest model.

### app.byok.card_label
Where: static/index.html:146 (label); static/app.js:429 (row label in the cost estimate)

    Card coding

### app.byok.card_same
Where: static/index.html:147 (select option); static/app.js:650 (placeholder of the typed fallback), 675, 697 (select option)

    Same as design

### app.byok.card_hint
Where: static/index.html:148 (hint)

    Writes every card in strict JSON — most of the cost. A reliable coder is enough.

### app.byok.estimate_link
Where: static/index.html:156 (link-style button)

    Estimate cost

### app.forge.button
Where: static/index.html:163 (primary button); static/app.js:213 (default label)

    Forge the class

### app.pay.open_link
Where: static/index.html:165 (link-style button under the Forge button)

    Change my tokens provider

### app.tutorial.body
Where: static/index.html:172-174 (one-line tutorial banner under the Forge button)
Notes: shown until dismissed.

    Describe a class, press Forge, copy the code, paste it in-game (main menu → Mod Configuration → BlankTheSpire → Import a class code → Import → Restart game). [Full guide with screenshots](/help)

### app.phone_banner.body
Where: static/index.html:182-183 (phone banner)
Notes: shown only on phones.

    On a phone? Forge away — the class is saved to My Classes. Open blankthespire.com on the PC that runs Slay the Spire 2 to grab the code, or send it to yourself below.

### app.advanced.summary
Where: static/index.html:190 (details summary)

    Advanced options

### app.advanced.interactive_label
Where: static/index.html:193 (checkbox label)

    Interactive forge

### app.advanced.interactive_hint
Where: static/index.html:195-198 (hint)

    Normally the forge maps your theme onto the game's build engines (the archetypes) and picks the strongest combination itself. With **Interactive forge** on, it pauses once your theme is mapped, shows you the candidate engines, and lets you pick up to two of them. You get a short timer; if you don't answer, the forge decides for you.

### app.progress.title
Where: static/index.html:207 (h3 above the forge console)

    Forging…

### app.choice.prompt
Where: static/index.html:209 (label of the interactive engine pick)
Notes: followed by app.choice.timer.

    Your call — pick up to 2 engines to build the class around

### app.choice.go
Where: static/index.html:212 (primary button)

    Forge with my picks

### app.choice.skip
Where: static/index.html:213 (button)

    Let the forge decide

### app.lost.open_library
Where: static/index.html:223 (button in the lost-connection banner)

    Open My Classes

### app.result.share
Where: static/index.html:232 (button)

    🔗 Copy share link

### app.result.share_tip
Where: static/index.html:232 (title tooltip); static/app.js:1308 (title on the library row's share button)

    Copy a public link to this class

### app.result.nominate
Where: static/index.html:234 (button); static/app.js:1085 (not-nominated state, result bar and library rows)

    ☆ Nominate for The Archive

### app.result.back
Where: static/index.html:235 (button)

    ← Back to the forge

### app.handoff.lede
Where: static/index.html:242 (p, phones only)

    Play it on your PC — send the class there:

### app.handoff.send_pc
Where: static/index.html:245 (button); static/deck.html:61 (button); static/app.js:1309 (library row button)
Notes: phones only.

    📲 Send to my PC

### app.handoff.send_pc_tip
Where: static/index.html:245 (title tooltip)

    Share the class link to your PC (AirDrop, Messages, Notes, Mail…)

### app.handoff.email_me
Where: static/index.html:247 (button); static/app.js:1310 (library row button)
Notes: phones only.

    ✉️ Email it to me

### app.handoff.email_me_tip
Where: static/index.html:247 (title tooltip, before app.js replaces it)

    Email the link and the import code to your account's address

### app.result.code_label
Where: static/index.html:257 (label); static/deck.html:55 (label)

    Class import code

### app.result.copy_code
Where: static/index.html:259 (button); static/deck.html:58 (button); static/app.js:1311 (library row button)

    Copy code

### app.play.title
Where: static/index.html:263 (h3 under the import code)

    Play it

### app.play.step_1
Where: static/index.html:265 (li)

    [Subscribe to the mod on Steam Workshop](/workshop) (once).

### app.play.step_2
Where: static/index.html:266 (li)

    In Slay the Spire 2: main menu → Mod Configuration → BlankTheSpire → *Import a class code* → paste → Import.

### app.play.step_3
Where: static/index.html:267 (li)

    Restart the game and pick your class.

### app.play.where
Where: static/index.html:269 (link to /help)

    Where do I paste this?

### app.library.show_art
Where: static/index.html:283 (checkbox label)

    Show art

### app.library.show_art_tip
Where: static/index.html:282 (title tooltip)

    Hide the splash, sprite and card art to scan the list faster

### app.library.empty
Where: static/index.html:285 (empty state)

    No classes yet — forge one!

### app.account.balance_unit
Where: static/index.html:295 (after the balance number)

    tokens

### app.account.balance_hint
Where: static/index.html:296 (hint)

    One token forges one class on our models. Bring your own API key and forging is free and unlimited — no token needed.

### app.account.donate_hint
Where: static/index.html:301 (hint under app.pay.token.get on the Account view)

    Blank the Spire is free and open source, but every hosted forge costs me real money. Your donations cover the cost of our compute.

### app.account.stripe_note
Where: static/index.html:307 (hint)

    Payments are handled by Stripe — we never see your card details.

### app.account.history_title
Where: static/index.html:453 (h2)

    Donation history

### app.account.history_empty
Where: static/index.html:454 (empty state)

    No donations yet.

### app.account.signin_title
Where: static/index.html:462 (h2)

    Sign-in methods

### app.account.signin_hint
Where: static/index.html:463 (hint)

    Any of these signs you in to this same account.

### app.account.link_another
Where: static/index.html:466 (hint before the provider buttons)

    Link another:

### app.feedback.title_card
Where: static/index.html:475 (h3); static/render.js:442 (FB_TITLES.card)

    How's this card?

### app.feedback.note_placeholder
Where: static/index.html:480 (textarea placeholder)

    Optional — tell us why (your words help tune future generations)

### app.feedback.submit
Where: static/index.html:482 (primary button)

    Submit feedback

## App JS strings (app.js, render.js)

### app.tokens.chip_unlimited
Where: static/app.js:133 (header token chip)

    ∞ tokens

### app.tokens.chip.one
Where: static/app.js:133 (header token chip)

    1 token

### app.tokens.chip.other
Where: static/app.js:133 (header token chip)
Notes: {count} = token balance (0 or 2+).

    {count} tokens

### app.tokens.line_unlimited
Where: static/app.js:139 (balance line in "Use a token")

    ∞ tokens — your account forges free.

### app.tokens.line_have.one
Where: static/app.js:140 (balance line)

    You have 1 token.

### app.tokens.line_have.other
Where: static/app.js:140 (balance line)
Notes: {count} = 2 or more.

    You have {count} tokens.

### app.tokens.line_none
Where: static/app.js:141 (balance line)

    You have no tokens. Get a forge token below — one token forges one class.

### app.tokens.hide_options
Where: static/app.js:165 (the Get a forge token button while the tiers are open)

    Hide token options

### app.welcome.text.one
Where: static/app.js:337-338 (sign-up event welcome banner)
Notes: {label} = the event's label, falling back to app.welcome.label_fallback.

    Welcome! {label} gave you 1 free forge token. One token forges one class — describe yours below and press Forge.

### app.welcome.text.other
Where: static/app.js:337-338
Notes: {label} as above; {count} = tokens granted.

    Welcome! {label} gave you {count} free forge tokens. One token forges one class — describe yours below and press Forge.

### app.welcome.label_fallback
Where: static/app.js:337

    A sign-up event

### app.remix.hint
Where: static/app.js:122 (hint under the concept box after "Forge your own twist")
Notes: {name} = the remixed class's name, or app.remix.name_fallback.

    Remixing “{name}” — edit the description, then forge.

### app.remix.name_fallback
Where: static/app.js:122

    a shared class

### app.account.identity_row
Where: static/app.js:1423-1424 (one row of the Sign-in methods list)
Notes: {provider} = one of the app.account.identity.* labels; {label} = the masked address ("r…@gmail.com"). Without a label the row is just {provider}.

    {provider} ({label})

### app.account.identity.google
Where: static/app.js:1407 (IDENTITY_LABELS; also the Link another buttons)

    Google

### app.account.identity.discord
Where: static/app.js:1407

    Discord

### app.account.identity.github
Where: static/app.js:1407

    GitHub

### app.account.identity.email
Where: static/app.js:1407

    Email

### app.account.toast_load_failed
Where: static/app.js:1397 (toast)

    Couldn't load your account — check your connection.

### app.forge.button_byok
Where: static/app.js:217 (Forge button label, key box can pay)

    Forge the class (uses your API key)

### app.forge.button_unlimited
Where: static/app.js:223 (Forge button label)

    Forge the class (free — unlimited account)

### app.forge.button_token.one
Where: static/app.js:226 (Forge button label)

    Forge the class (uses 1 of your 1 token)

### app.forge.button_token.other
Where: static/app.js:226 (Forge button label)
Notes: {count} = balance, 2 or more.

    Forge the class (uses 1 of your {count} tokens)

### app.forge.why_byok_list
Where: static/app.js:219 (Forge button tooltip when the key box can't pay yet)

    Enter your API key, then pick a model from your provider's list.

### app.forge.why_byok
Where: static/app.js:220 (Forge button tooltip)

    Enter your API key and a model.

### app.forge.why_no_tokens
Where: static/app.js:227 (Forge button tooltip)

    You have no tokens — get a forge token below, or bring your own key.

### app.forge.why_no_mode
Where: static/app.js:230 (Forge button tooltip)

    Pick how to pay: 'Use a token' or 'Bring your own key'.

### app.pay.reason_byok
Where: static/app.js:312 (one-line reason on top of the pay step; also a toast on a repeat click)

    Enter your API key and pick a model

### app.pay.reason_token
Where: static/app.js:312, 877 (one-line reason on top of the pay step; also a toast on a repeat click)

    Pick how to pay for this forge

### app.forge.toast_no_concept
Where: static/app.js:796 (toast)

    Describe a class first.

### app.forge.toast_no_tokens
Where: static/app.js:821 (toast)

    No tokens to spend — get a forge token below, or bring your own key.

### app.forge.confirm_token
Where: static/app.js:825 (confirm dialog)
Notes: {count} = current balance.

    This will use 1 token. You have {count}. Forge this class?

### app.forge.toast_load_models
Where: static/app.js:832 (toast)

    Load your model list and pick a model first.

### app.forge.toast_need_key
Where: static/app.js:835 (toast)

    Enter your API key and a model — or switch to 'Use a token'.

### app.forge.confirm_byok
Where: static/app.js:836 (confirm dialog)
Notes: {provider} = the provider's short label (Anthropic, OpenAI, Ollama Cloud, OpenRouter, Groq, Google Gemini, xAI (Grok), DeepSeek, Together, or app.byok.provider_label_custom); {estimate} = the app.estimate.confirm_* lines joined by line breaks.

    This forge bills your {provider} key.
    
    {estimate}
    
    Forge this class?

### app.forge.toast_need_base_url
Where: static/app.js:845 (toast)

    Enter the base URL for your provider.

### app.forge.err_http_nonjson
Where: static/app.js:882 (console line + toast when nginx answers with an HTML error page)
Notes: {status} = HTTP status number.

    the server answered HTTP {status} — nothing was forged; try again

### app.forge.err_stream_ended
Where: static/app.js:889 (internal reason, shown inside app.lost.* and app.console.lost as {reason})

    the progress stream ended early

### app.byok.get_key_at
Where: static/app.js:597 (hint under the key box)
Notes: {where} = the provider's key page (console.anthropic.com, ollama.com/settings/keys, ...), app.byok.key_from_openai, or app.byok.key_from_custom.

    Get a key at {where}

### app.byok.key_from_openai
Where: static/app.js:545 (PROVIDERS.openai.keyFrom)

    platform.openai.com (an API key, not a ChatGPT login)

### app.byok.key_from_custom
Where: static/app.js:572 (PROVIDERS.custom.keyFrom)

    your provider

### app.byok.provider_label_custom
Where: static/app.js:572 (PROVIDERS.custom.label, used as {provider} in confirm and tooltip text)

    Other

### app.byok.art_chip_yes
Where: static/app.js:601 (chip)

    Art included

### app.byok.art_chip_no
Where: static/app.js:601 (chip)

    No generated art

### app.byok.art_tip_yes
Where: static/app.js:604 (chip tooltip)

    The splash, sprite and card portraits are generated on this key too.

### app.byok.art_tip_no
Where: static/app.js:605 (chip tooltip)
Notes: {provider} = provider short label.

    {provider} can't make images, so classes forged on this key use the game's built-in card doodles.

### app.byok.model_placeholder_typed
Where: static/app.js:650 (placeholder of the typed-id fallback for "Other")

    Model id

### app.byok.no_models
Where: static/app.js:699 (disabled select option)

    No usable models on this key

### app.byok.group_tested
Where: static/app.js:705 (optgroup label)

    Tested

### app.byok.group_all
Where: static/app.js:705 (optgroup label)

    All models

### app.byok.reload_models
Where: static/app.js:731 (link-style button once a list is loaded)

    Reload model list

### app.byok.loading
Where: static/app.js:1934 (button label while loading)

    Loading…

### app.byok.toast_need_key
Where: static/app.js:1929 (toast)

    Pick a provider and enter your API key first.

### app.byok.toast_saved_gone
Where: static/app.js:1949 (toast)
Notes: {model} = the saved model id.

    Your saved model “{model}” isn't offered on this key any more — pick another.

### app.byok.toast_loaded
Where: static/app.js:1950 (toast)
Notes: {count} = models listed; {hidden} = app.byok.toast_loaded_hidden or empty. Not pluralised in the code.

    Loaded {count} models{hidden}.

### app.byok.toast_loaded_hidden
Where: static/app.js:1948
Notes: fragment, starts with a space. {count} = models filtered out.

     (hid {count} that can't run a forge)

### app.byok.toast_typed_fallback
Where: static/app.js:1957 (toast, "Other" provider only)
Notes: {error} = the server's error text.

    Couldn't list models on this endpoint ({error}) — type the model ids instead.

### app.estimate.title
Where: static/app.js:495 (estimate panel heading)

    Estimated cost per forge

### app.estimate.total
Where: static/app.js:499 (table row label)

    Total

### app.estimate.row_design_cards
Where: static/app.js:428 (table row label when one model does both)

    Design + cards

### app.estimate.row_art
Where: static/app.js:447, 450 (table row label)

    Art

### app.estimate.art_images
Where: static/app.js:447 (table cell)
Notes: {count} = images per forge (~36).

    {count} images

### app.estimate.art_tip
Where: static/app.js:448 (row tooltip)
Notes: {model} = image model id, or app.estimate.art_tip_model_fallback; {count} = card portraits (images minus 2).

    {model}: splash, sprite and {count} card portraits

### app.estimate.art_tip_model_fallback
Where: static/app.js:448
Notes: {provider} = provider short label.

    {provider} image API

### app.estimate.art_none
Where: static/app.js:450 (table cell)

    not on this provider

### app.estimate.art_none_tip
Where: static/app.js:451 (row tooltip)

    Classes forged on this key use the game's built-in card doodles.

### app.estimate.pick_model
Where: static/app.js:437 (table cell when no model is picked)

    pick a model

### app.estimate.no_model
Where: static/app.js:434 (inside app.estimate.note_unpriced)

    (no model)

### app.estimate.tokens_line
Where: static/app.js:414-415 (row tooltip, after "{model}: ")
Notes: {calls}, {input}, {cached}, {output} are rounded counts like "1.4M" or "650K".

    ~{calls} calls · ~{input} in (~{cached} cached) · ~{output} out

### app.estimate.note_fallback
Where: static/app.js:423 (note when the estimate could not load)

    A forge is ~50 model calls and ~1.4M input tokens — check your provider's pricing.

### app.estimate.note_unpriced
Where: static/app.js:460 (note)
Notes: {models} = model ids joined by " / ".

    No price on file for {models} — check your provider's rates.

### app.estimate.note_openrouter
Where: static/app.js:462 (note)
Notes: {price} = dollars, e.g. "$0.48".

    An OpenRouter key makes the same art for ~{price}.

### app.estimate.note_caching
Where: static/app.js:463 (note)
Notes: {price} = dollars.

    Assumes prompt caching — up to {price} without it.

### app.estimate.confirm_model
Where: static/app.js:470 (first line of the BYOK confirm dialog, one model)

    Model: {model}

### app.estimate.confirm_models
Where: static/app.js:470 (first line of the BYOK confirm dialog, two models)

    Design: {design} · Cards: {cards}

### app.estimate.confirm_cost
Where: static/app.js:472 (second line of the BYOK confirm dialog)
Notes: {total} = dollars; {split} = app.estimate.confirm_split when art has a price, else empty.

    Estimated ≈ {total} per forge{split}

### app.estimate.confirm_split
Where: static/app.js:472
Notes: fragment, starts with a space.

     (text {text} + art {art})

### app.estimate.confirm_unknown
Where: static/app.js:473 (second line of the BYOK confirm dialog)

    Estimated cost: unknown for this model.

### app.console.requested
Where: static/app.js:860 (first console line, printed by the browser)
Notes: {mode} = the raw wire mode (token, byok, anthropic, fake), not translated; {interactive} = app.console.requested_interactive or empty. Console glyphs: "•" progress, "✗" error, "✓" done; the server's own lines are printed as "• {message}" and errors as "✗ {error}".

    • requested: {mode}{interactive}

### app.console.requested_interactive
Where: static/app.js:860
Notes: fragment, starts with a space.

     · interactive

### app.console.done
Where: static/app.js:1028 (console line)

    ✓ done

### app.console.lost
Where: static/app.js:922 (console line)
Notes: {reason} = the browser's error text (e.g. "network error" or app.forge.err_stream_ended).

    ✗ lost the connection ({reason}) — the forge continues on the server; reconnecting…

### app.console.unreachable
Where: static/app.js:926 (console line)

    ✗ couldn't reach the server ({reason})

### app.console.never_started
Where: static/app.js:941 (console line)

    ✗ the forge never started

### app.console.done_reconnected
Where: static/app.js:963 (console line)

    ✓ done (reconnected)

### app.console.done_open_library
Where: static/app.js:965 (console line)

    ✓ done — open it from My Classes

### app.console.choice_timeout
Where: static/app.js:1244 (console line)

    • choice timed out — the forge decides

### app.console.picked
Where: static/app.js:1254 (console line)
Notes: {picks} = archetype ids joined by ", ".

    • you picked: {picks}

### app.console.skipped
Where: static/app.js:1254 (console line)

    • skipped — the forge decides

### app.console.pick_failed
Where: static/app.js:1263 (console line, when the server sent no message)

    • the pick didn't land — the forge decides

### app.lost.still_running
Where: static/app.js:916-918 (lost-connection banner)
Notes: followed by app.lost.refund_note on the token path.

    Lost the connection to your forge — this happens when a phone locks or switches networks. It's still running on our server, and this page will pick it back up and show the class when it's done. If you leave, it'll be waiting in My Classes.

### app.lost.refund_note
Where: static/app.js:919
Notes: fragment, starts with a space; token forges only.

     If the forge fails, your token is refunded automatically.

### app.lost.toast_reconnecting
Where: static/app.js:923 (toast)

    Connection lost — reconnecting to your forge…

### app.lost.unreachable
Where: static/app.js:925 (lost-connection banner)

    Couldn't reach the server ({reason}). Checking whether your forge started…

### app.lost.toast_unreachable
Where: static/app.js:927 (toast)

    Couldn't reach the server — checking your connection…

### app.lost.never_started
Where: static/app.js:940 (lost-connection banner)

    No forge was started, so nothing was spent. Check your connection and forge again.

### app.lost.toast_ready
Where: static/app.js:966 (toast)

    Your class is ready in My Classes.

### app.lost.failed_fallback
Where: static/app.js:969 (console line + toast when the failed job carries no error)

    the forge failed

### app.lost.refunded_suffix
Where: static/app.js:969
Notes: fragment glued after the job's error text.

     — your token was refunded.

### app.lost.gave_up
Where: static/app.js:974-975 (lost-connection banner, BYOK)

    Still no word from your forge. If it finishes, it'll appear in My Classes.

### app.lost.gave_up_token
Where: static/app.js:974-975 (lost-connection banner, token path)

    Still no word from your forge. If it finishes, it'll appear in My Classes; if it fails, your token is refunded automatically.

### app.choice.requested_badge
Where: static/app.js:1213 (badge on an engine option)

    you asked for this

### app.choice.needs_vocab
Where: static/app.js:1214 (warning on an engine option)

    needs new vocab — some cards may substitute

### app.choice.toast_max
Where: static/app.js:1232 (toast)

    Pick at most 2 — deselect one first.

### app.choice.timer
Where: static/app.js:1242 (after app.choice.prompt)
Notes: {seconds} = countdown.

    ({seconds}s — then the forge decides)

### app.result.view_saved
Where: static/app.js:1073 (result bar title)

    Viewing a saved class

### app.result.view_new
Where: static/app.js:1073 (result bar title)

    Your new class

### app.share.text
Where: static/app.js:1054 (what Copy share link puts on the clipboard)
Notes: {name} = class name or app.share.name_fallback; {description} = first ~140 characters of the description, trailing punctuation stripped; {url} = the /deck link.

    {name} — {description}. Play it: {url}

### app.share.text_no_description
Where: static/app.js:1054

    {name}. Play it: {url}

### app.share.name_fallback
Where: static/app.js:1053; also web/app.py:400 (deck page title fallback)

    A forged class

### app.nominate.featured
Where: static/app.js:1085 (button, disabled)

    ★ In The Archive

### app.nominate.nominated
Where: static/app.js:1085 (button)

    ★ Nominated · withdraw

### app.nominate.tip_featured
Where: static/app.js:1086 (tooltip)

    Picked for The Archive

### app.nominate.tip_nominated
Where: static/app.js:1087 (tooltip)

    Waiting for review — click to withdraw the nomination

### app.nominate.tip_nominate
Where: static/app.js:1088 (tooltip)

    Ask for this class to be featured in The Archive, the public showcase

### app.nominate.prompt
Where: static/app.js:1097-1098 (prompt dialog)

    Nominate this class for The Archive?
    
    Optional: why should it be picked? (up to 200 characters; only the reviewer sees it)

### app.nominate.toast_withdrawn
Where: static/app.js:1113 (toast)

    Nomination withdrawn.

### app.nominate.toast_nominated
Where: static/app.js:1113 (toast)

    Nominated — you'll see it in The Archive if it's picked.

### app.common.toast_retry
Where: static/app.js:1115 (toast when a nomination request fails without a message)

    That didn't go through — try again.

### app.handoff.no_mail_server
Where: static/app.js:1126 (note + disabled-button tooltip)

    Email isn't set up on this server yet — use Send to my PC, or copy the code.

### app.handoff.no_email
Where: static/app.js:1127 (note + disabled-button tooltip)

    This account has no email address — use Send to my PC, or copy the code.

### app.handoff.open_from_library
Where: static/app.js:1135 (disabled-button tooltip)

    Open this class from My Classes to email it.

### app.handoff.email_tip
Where: static/app.js:1137 (button tooltip)
Notes: {email} = the account's address, or app.handoff.email_tip_fallback.

    Email the link and the import code to {email}

### app.handoff.email_tip_fallback
Where: static/app.js:1137

    your address

### app.handoff.toast_sent
Where: static/app.js:1147 (toast)
Notes: {email} = the address it went to, or app.handoff.toast_sent_fallback.

    Sent to {email} — open it on your PC.

### app.handoff.toast_sent_fallback
Where: static/app.js:1147

    your inbox

### app.handoff.toast_failed
Where: static/app.js:1149 (toast when the server sent no message)

    The email didn't go out — copy the code instead.

### app.result.usage
Where: static/app.js:1169-1171 (line under the import code, BYOK forges only)
Notes: built from fragments. {calls}, {input}, {output} are counts ("1.4M", "650K"); {cached} = app.result.usage_cached or empty; {art} = app.result.usage_images.* plus optional app.result.usage_art_cost, or empty.

    This forge used {calls} calls · {input} tokens in{cached} · {output} out{art} on your key.

### app.result.usage_cached
Where: static/app.js:1170
Notes: fragment, starts with a space.

     ({cached} cached)

### app.result.usage_images.one
Where: static/app.js:1165
Notes: fragment, starts with a space.

     · 1 image

### app.result.usage_images.other
Where: static/app.js:1165
Notes: fragment, starts with a space.

     · {count} images

### app.result.usage_art_cost
Where: static/app.js:1167
Notes: fragment, starts with a space. {cost} = dollars with 2 decimals; {kind} = app.result.usage_metered or app.result.usage_est.

     (${cost} {kind})

### app.result.usage_metered
Where: static/app.js:1167

    metered

### app.result.usage_est
Where: static/app.js:1167

    est.

### app.library.cards_meta
Where: static/app.js:1305 (library row meta)
Notes: {count} = cards in the class; {vocab} = vocabulary version number.

    {count} cards · v{vocab}

### app.library.share
Where: static/app.js:1308 (library row button)

    🔗 Share link

### app.library.code_tip
Where: static/app.js:1311 (tooltip on the row's Copy code button)

    Copy the in-game import code

### app.library.rename
Where: static/app.js:1313 (library row button)

    Rename

### app.library.open
Where: static/app.js:1314 (library row button)

    Open

### app.library.delete
Where: static/app.js:1315 (library row button)

    Delete

### app.library.splash_alt
Where: static/app.js:1321 (img alt); static/render.js:88 (img alt)
Notes: {name} = class name.

    {name} splash art

### app.library.sprite_alt
Where: static/app.js:1322 (img alt)

    {name} sprite

### app.library.toast_load_failed
Where: static/app.js:1286 (toast)

    Couldn't load your classes — check your connection.

### app.library.rename_prompt
Where: static/app.js:1364 (prompt dialog)

    New name:

### app.library.delete_confirm
Where: static/app.js:1373 (confirm dialog)

    Delete "{name}"? This cannot be undone.

### app.donate.tier_label.one
Where: static/app.js:1558-1559 (tier button headline)
Notes: {amount} = "$3" style amount. No live tier gives 1 token today.

    {amount} → 1 token

### app.donate.tier_label.other
Where: static/app.js:1558-1559 (tier button headline)

    {amount} → {count} tokens

### app.donate.fee_line
Where: static/app.js:1560-1561 (small line under each tier); static/app.js:1530-1531 (after app.donate.custom_rule)
Notes: {gross} = what the card is charged; {fee} = the card fee inside it.

    {gross} charged, incl. {fee} card fee

### app.donate.custom_reveal
Where: static/app.js:1513 (button)

    Enter another custom amount

### app.donate.custom_aria
Where: static/app.js:1520 (aria-label on the amount box)

    Custom amount in dollars

### app.donate.custom_placeholder
Where: static/app.js:1520 (amount box placeholder)
Notes: {min} = minimum dollars (11).

    {min}+

### app.donate.custom_button
Where: static/app.js:1521, 1527 (button, no valid amount yet)

    Get tokens

### app.donate.custom_button_n.one
Where: static/app.js:1527 (button)

    Get 1 token

### app.donate.custom_button_n.other
Where: static/app.js:1527 (button)

    Get {count} tokens

### app.donate.custom_rule
Where: static/app.js:1524 (line under the amount box; followed by app.donate.fee_line once an amount is valid)
Notes: {min} = minimum dollars (11), {max} = maximum dollars (500), both from /api/billing (web/billing.py CUSTOM_MIN_DOLLARS / CUSTOM_MAX_DOLLARS). Says "whole dollars" because app.donate.toast_bad_amount asks for one.

    Whole dollars, ${min} to ${max} — one token per dollar.

### app.donate.toast_bad_amount
Where: static/app.js:1578 (toast)

    Enter a whole dollar amount between ${min} and ${max}.

### app.donate.redirecting
Where: static/app.js:1588 (button label while Stripe loads)

    Redirecting…

### app.history.donated_split
Where: static/app.js:1623 (Donation history row)

    Donated {gross} ({net} + {fee} card fee)

### app.history.donated
Where: static/app.js:1624 (Donation history row, pre-v3 donations)

    Donated {gross}

### app.history.pack
Where: static/app.js:1625 (Donation history row, retired token packs)

    Token pack, {gross}

### app.history.tokens.one
Where: static/app.js:1627 (row meta)
Notes: {date} = locale date.

    +1 token · {date}

### app.history.tokens.other
Where: static/app.js:1627 (row meta)

    +{count} tokens · {date}

### app.history.refunded
Where: static/app.js:1628 (row meta suffix, after " · ")

    refunded

### app.checkout.toast_canceled
Where: static/app.js:1642 (toast after returning from Stripe)

    Donation canceled — you weren't charged.

### app.checkout.added.one
Where: static/app.js:1653 (inside the thank-you toasts)

    1 token added

### app.checkout.added.other
Where: static/app.js:1653

    {count} tokens added

### app.checkout.toast_thanks_draft
Where: static/app.js:1655 (toast; the concept box was restored)
Notes: {added} = app.checkout.added.*.

    Thank you! {added} — your class is ready to forge.

### app.checkout.toast_thanks
Where: static/app.js:1656 (toast)

    Thank you! {added} — you're ready to forge.

### app.checkout.toast_thanks_plain
Where: static/app.js:1657 (toast when the donation carried no tokens)

    Thank you! Your donation went through.

### app.checkout.toast_processing
Where: static/app.js:1674 (toast)

    Payment is processing — your balance will update shortly.

### app.share_sheet.title
Where: static/render.js:28 (OS share sheet title, "Send to my PC")
Notes: {name} = class name or app.share_sheet.name_fallback.

    {name} — Blank the Spire

### app.share_sheet.text
Where: static/render.js:29 (OS share sheet text)

    {name}: a Slay the Spire 2 class. Open this on your PC to grab the import code.

### app.share_sheet.name_fallback
Where: static/render.js:28-29

    A class

### app.result.sprite_alt
Where: static/render.js:89 (img alt)

    {name} combat sprite

### app.result.feedback_tip
Where: static/render.js:144, 252, 387 (title + aria-label on the 💬 button)

    Give feedback

### app.result.archetype_badge
Where: static/render.js:130 (badge)

    ⚙ Archetype

### app.result.relic_badge
Where: static/render.js:145 (badge)

    ⬦ Keystone relic

### app.result.relic_fallback_title
Where: static/render.js:154 (feedback popup title when the relic has no name)

    Keystone relic

### app.relic.mod.max_energy
Where: static/render.js fmtMod (relic effect line)
Notes: {amount} = the signed amount ("+1", "-8": max_hp may be negative). A whole template since 2026-10-27 (was a fragment after "+{amount} "), so a language can put the number where it reads naturally.

    {amount} max energy

### app.relic.mod.first_attack
Where: static/render.js fmtMod (relic effect line)
Notes: {amount} = the signed amount, as app.relic.mod.max_energy.

    {amount} first-attack damage

### app.relic.mod.cost_reduction
Where: static/render.js fmtMod (relic effect line)
Notes: {amount} = the signed amount, as app.relic.mod.max_energy.

    {amount} card cost reduction

### app.relic.mod.start_combat_block
Where: static/render.js fmtMod (relic effect line)
Notes: {amount} = the signed amount, as app.relic.mod.max_energy.

    {amount} block at combat start

### app.relic.mod.attack_base
Where: static/render.js fmtMod (relic effect line)
Notes: {amount} = the signed amount, as app.relic.mod.max_energy.

    {amount} damage on every attack

### app.relic.mod.max_hp
Where: static/render.js fmtMod (relic effect line)
Notes: {amount} = the signed amount, as app.relic.mod.max_energy.

    {amount} max HP

### app.relic.trigger.turn_start
Where: static/render.js:176 (relic hook line head, followed by ": {effects}")

    Turn start

### app.relic.trigger.turn_end
Where: static/render.js:176

    Turn end

### app.relic.trigger.attacked
Where: static/render.js:176

    When attacked

### app.relic.trigger.on_exhaust
Where: static/render.js:177

    On exhaust

### app.relic.trigger.on_card_played
Where: static/render.js:177

    On card played

### app.relic.trigger.combat_end
Where: static/render.js:177

    Combat end

### app.relic.trigger.on_card_drawn
Where: static/render.js:178

    On card drawn

### app.relic.trigger.on_damage_dealt
Where: static/render.js:178

    On damage dealt

### app.relic.trigger.on_block_gained
Where: static/render.js:178

    On block gained

### app.relic.trigger.on_hp_lost
Where: static/render.js:179

    On HP lost

### app.relic.trigger.on_type_played
Where: static/render.js fmtHook
Notes: {type} = app.card_type.<type> with its first letter capitalised (Attack, Skill, Power).

    On {type} played

### app.relic.every_nth
Where: static/render.js fmtHook
Notes: fragment, starts with a space. {n} = the count as the language writes it: English gets an ordinal from render.js nthLabel() ("3rd"); every other language gets the bare number, so its template carries the counter word (zh: 每{n}次).

     (every {n})

### app.relic.once_per_combat
Where: static/render.js:189
Notes: fragment, starts with a space.

     · once/combat

### app.mech.head
Where: static/render.js:221 (heading of the Class mechanics panel)

    Class mechanics — custom elements this class invents.

### app.mech.head_rate
Where: static/render.js:222 (appended to app.mech.head in the app, not on the public deck page)
Notes: fragment, starts with a space.

     Click one to see what it does and rate it.

### app.mech.badge_orb
Where: static/render.js:198 (badge)

    ◉ Orb

### app.mech.badge_status
Where: static/render.js:199 (badge)

    ✦ Status

### app.mech.badge_summon
Where: static/render.js:200 (badge)

    ⚔ Summon

### app.mech.badge_potion
Where: static/render.js:203 (badge)

    🧪 Potion

### app.mech.forge_badge
Where: static/render.js:234 (badge on the Forge-persist chip)

    ⚒ Forge

### app.mech.forge_name
Where: static/render.js:235

    Keeps its edge

### app.mech.forge_teaser
Where: static/render.js:236

    This class's Forge counter does not fully reset between fights.

### app.mech.forge_line_1
Where: static/render.js:237 (bullet)

    At the end of each combat it banks up to 5 Forge

### app.mech.forge_line_2
Where: static/render.js:238 (bullet)

    Your first turn of the next combat gets that much Forge back (and summons your blade)

### app.mech.orb_passive
Where: static/render.js:275 (orb line head, followed by ": {effects}")

    Each turn while channeled

### app.mech.orb_passive_turn_start
Where: static/render.js:275

    At the start of each turn while channeled

### app.mech.orb_evoke
Where: static/render.js:275

    On evoke

### app.mech.status_hook.damage_dealt
Where: static/render.js:286 (inside app.mech.status_line as {hook})

    your attacks

### app.mech.status_hook.damage_taken
Where: static/render.js:286

    damage you take

### app.mech.status_hook.block_gained
Where: static/render.js:287

    block you gain

### app.mech.status_hook.turn_start
Where: static/render.js:287

    turn start

### app.mech.status_hook.turn_end
Where: static/render.js:287

    turn end

### app.mech.status_hook.energy_gain
Where: static/render.js:288

    energy you gain

### app.mech.status_hook.card_draw
Where: static/render.js:288

    cards you draw

### app.mech.status_hook.damage_over_time
Where: static/render.js:289

    HP lost at its turn start

### app.mech.status_hook.hit_count
Where: static/render.js:289

    hits per attack

### app.mech.status_buff
Where: static/render.js:317 ({kind} in app.mech.status_line)

    Buff

### app.mech.status_debuff
Where: static/render.js:317 ({kind} in app.mech.status_line)

    Debuff

### app.mech.status_line
Where: static/render.js:321 (first line of a status chip)
Notes: {kind} = app.mech.status_buff / _debuff; {hook} = an app.mech.status_hook.* label (an unknown hook is shown with underscores turned into spaces); {mode} = app.mech.status_multiplicative or empty. Without a hook the line is just {kind}.

    {kind} — affects {hook}{mode}

### app.mech.status_multiplicative
Where: static/render.js:320
Notes: fragment, starts with a space.

     (+10% per stack, up to double)

### app.mech.status_decays
Where: static/render.js statusLines
Notes: {decay} = app.decay.<value> (an unknown value prints raw, underscores as spaces).

    Decays: {decay}

### app.mech.potion_line
Where: static/render.js potionLines (first line of a potion chip)
Notes: {rarity} = app.rarity.<rarity> with its first letter capitalised (Common, Uncommon, Rare); {when} = app.mech.potion_any_time or app.mech.potion_in_combat.

    {rarity} potion — usable {when}

### app.mech.potion_any_time
Where: static/render.js:297

    any time

### app.mech.potion_in_combat
Where: static/render.js:297

    in combat

### app.mech.potion_drops
Where: static/render.js:301 (last line of a potion chip)

    Drops alongside the usual potions on runs of this class

### app.mech.summon_ethereal
Where: static/render.js:350 (summon chip line)

    Ethereal (cannot be attacked)

### app.mech.summon_max_hp
Where: static/render.js:351 (summon chip line)
Notes: {hp} = max HP or "?".

    Max HP: {hp}

### app.mech.summon_passive
Where: static/render.js:353 (summon chip line)

    A passive minion — summon it, then spend cards to make it attack.

### app.mech.summon_each_turn
Where: static/render.js:355
Notes: {actions} = effect phrases from the card-text renderer (see Out of scope).

    Each turn: {actions}

### app.mech.summon_turn_n
Where: static/render.js:357

    Turn {n}: {actions}

### app.mech.summon_on_summon
Where: static/render.js:359

    On summon: {actions}

### app.mech.summon_on_death
Where: static/render.js:360

    On death: {actions}

### app.mech.summon_every_nth
Where: static/render.js summonLines
Notes: {n} = as app.relic.every_nth (English: an ordinal, "3rd"). Was "Every {n}th hit" with a hard-coded "th" ("Every 3th hit"); the ordinal now comes from render.js nthLabel(), so the English reads "Every 1st / 2nd / 3rd / 4th hit".

    Every {n} hit: {actions}

### app.card.show_upgraded
Where: static/render.js:405 (checkbox label on a card chip)

    Show upgraded

### app.card_type.attack
Where: static/render.js (card type: the card chip's meta line and, capitalised, {type} in app.relic.trigger.on_type_played)
Notes: added 2026-10-27 by the i18n build, owner to review. Lowercase, as the data value; the code capitalises where the line needs it.

    attack

### app.card_type.skill
Where: static/render.js (same table as the entry above)
Notes: added 2026-10-27 by the i18n build, owner to review. Lowercase, as the data value; the code capitalises where the line needs it.

    skill

### app.card_type.power
Where: static/render.js (same table as the entry above)
Notes: added 2026-10-27 by the i18n build, owner to review. Lowercase, as the data value; the code capitalises where the line needs it.

    power

### app.rarity.basic
Where: static/render.js (rarity: the card chip's meta line and, capitalised, {rarity} in app.mech.potion_line)
Notes: added 2026-10-27 by the i18n build, owner to review. Lowercase, as the data value; the code capitalises where the line needs it.

    basic

### app.rarity.common
Where: static/render.js (same table as the entry above)
Notes: added 2026-10-27 by the i18n build, owner to review. Lowercase, as the data value; the code capitalises where the line needs it.

    common

### app.rarity.uncommon
Where: static/render.js (same table as the entry above)
Notes: added 2026-10-27 by the i18n build, owner to review. Lowercase, as the data value; the code capitalises where the line needs it.

    uncommon

### app.rarity.rare
Where: static/render.js (same table as the entry above)
Notes: added 2026-10-27 by the i18n build, owner to review. Lowercase, as the data value; the code capitalises where the line needs it.

    rare

### app.rarity.token
Where: static/render.js (same table as the entry above)
Notes: added 2026-10-27 by the i18n build, owner to review. Lowercase, as the data value; the code capitalises where the line needs it.

    token

### app.decay.lose_one_eot
Where: static/render.js (status decay: {decay} in app.mech.status_decays. The English is the raw value as the site printed it before (underscores as spaces); worth rewording)
Notes: added 2026-10-27 by the i18n build, owner to review. Lowercase, as the data value; the code capitalises where the line needs it.

    loses 1 at end of each turn

### app.decay.lose_all_eot
Where: static/render.js (same table as the entry above)
Notes: added 2026-10-27 by the i18n build, owner to review. Lowercase, as the data value; the code capitalises where the line needs it.

    wears off at end of turn

### app.feedback.cat.great
Where: static/render.js:429 (feedback category button)

    Good

### app.feedback.cat.overpowered
Where: static/render.js:430

    Seems OP

### app.feedback.cat.underpowered
Where: static/render.js:431

    Underpowered

### app.feedback.cat.off_theme
Where: static/render.js:432

    Off-theme

### app.feedback.cat.confusing
Where: static/render.js:433

    Doesn't make sense

### app.feedback.cat.doesnt_work
Where: static/render.js:434

    Doesn't work

### app.feedback.title_relic
Where: static/render.js:442 (popup title)

    How's this relic?

### app.feedback.title_orb
Where: static/render.js:442

    How's this orb?

### app.feedback.title_status
Where: static/render.js:443

    How's this status?

### app.feedback.title_summon
Where: static/render.js:443

    How's this summon?

### app.feedback.title_potion
Where: static/render.js:443

    How's this potion?

### app.feedback.title_fallback
Where: static/render.js:450

    How's this?

### app.feedback.rated_tip
Where: static/render.js:500 (tooltip on the ✓ after rating)
Notes: {label} = the chosen app.feedback.cat.* label.

    You rated this: {label} — click to change

### app.feedback.sent_tip
Where: static/render.js:500 (tooltip fallback)

    Feedback sent — click to change

### app.feedback.toast_thanks
Where: static/render.js:504 (toast)

    Thanks for the feedback!

## Help page (help.html)

### help.meta.title
Where: static/help.html:6 (title, before common.title_suffix)

    Help

### help.header.sub
Where: static/help.html:24 (header brand sub)

    help

### help.intro.title
Where: static/help.html:34 (h1)

    Where do I paste my code?

### help.intro.body
Where: static/help.html:35-39 (p)
Notes: the ONE in-game path spelling, used by every page, the email and the Workshop description: "main menu → Mod Configuration → BlankTheSpire → Import a class code → Import → Restart game" (shortened by dropping hops where a sentence needs fewer). "Mod Configuration" is BaseLib's English main-menu label (BaseLib/localization/eng/main_menu_ui.json, BASELIB-MOD_CONFIGURATION). The mod list shows "BlankTheSpire", not the manifest name "Blank the Spire": BaseLib's NModConfigSubmenu.GetModTitle reads settings_ui `BLANKTHESPIRE.mod_title`, which the mod does not define, and falls back to the config class's root namespace. The last three hops are the mod's own settings_ui.json labels (IMPORT_SECTION, IMPORT_BUTTON, RESTART_BUTTON).

    Inside the game, not on this site. Forge a class here, copy its import code (it starts with `BTSC.`), then in Slay the Spire 2 open the main menu → **Mod Configuration** → **BlankTheSpire** → paste it into the **Class code** field under **Import a class code** and press **Import**. Restart the game and your class appears at character select.

### help.steps.title
Where: static/help.html:43 (h2)

    Step by step

### help.steps.step_1
Where: static/help.html:46-47 (li)

    **Forge a class on the site and press Copy code.** The code starts with `BTSC.` and ends with a short hash — copy all of it.

### help.steps.step_1_alt
Where: static/help.html:49 (img alt)

    The forge result on blankthespire.com with the Copy code button

### help.steps.step_1_caption
Where: static/help.html:50 (figcaption)

    The result view on the site — the import code box and its Copy code button.

### help.steps.step_2
Where: static/help.html:54-55 (li)

    **Launch Slay the Spire 2 and open the main menu → Mod Configuration.** (the mod must be subscribed on [Steam Workshop](/workshop) first — once)

### help.steps.step_2_alt
Where: static/help.html:57 (img alt)

    The Slay the Spire 2 main menu with the Mod Configuration entry highlighted

### help.steps.step_2_caption
Where: static/help.html:58 (figcaption)

    Main menu — the Mod Configuration entry.

### help.steps.step_3
Where: static/help.html:62 (li)

    **Choose BlankTheSpire** from the list of installed mods on the left.

### help.steps.step_3_alt
Where: static/help.html:64 (img alt)

    The mod list with BlankTheSpire selected and its settings open

### help.steps.step_3_caption
Where: static/help.html:65 (figcaption)

    The mod list — pick BlankTheSpire to open its settings.

### help.steps.step_4
Where: static/help.html:69-70 (li)
Notes: names the in-game labels mod.settings.class_code and mod.settings.class_slot; keep them in sync.

    **Paste the code into the "Class code" field and press Import.** (the field sits under *Import a class code*; leave "Class slot" at 0 and the mod picks a free slot for you)

### help.steps.step_4_alt
Where: static/help.html:72 (img alt)

    The Class code field with a BTSC code pasted in and the Import button ready

### help.steps.step_4_caption
Where: static/help.html:73 (figcaption)

    The Class code field with the code pasted and Import ready to press.

### help.steps.step_5
Where: static/help.html:77 (li)
Notes: names the in-game label mod.settings.restart_title.

    **Restart the game** — press **Restart game (applies changes)** on the same screen.

### help.steps.step_5_callout
Where: static/help.html:78-80 (callout box)

    **The restart is REQUIRED.** The mod will say so right after the import. A newly imported class is only loaded at startup — it will **not** appear at character select until you fully quit and relaunch the game.

### help.steps.step_5_alt
Where: static/help.html:82 (img alt)

    The mod's restart-required confirmation after a successful import

### help.steps.step_5_caption
Where: static/help.html:83 (figcaption)

    The confirmation after a successful import — restart before you look for the class.

### help.steps.step_6
Where: static/help.html:87 (li)

    **Start a new run and pick your class** from the character select screen.

### help.steps.step_6_alt
Where: static/help.html:89 (img alt)

    The character select screen showing a forged class

### help.steps.step_6_caption
Where: static/help.html:90 (figcaption)

    Character select — your forged class sits alongside the base-game characters.

### help.trouble.title
Where: static/help.html:97 (h2)

    Troubleshooting

### help.trouble.rejected
Where: static/help.html:99-101 (li)

    **"Code rejected" / "invalid code".** Make sure the *whole* code was copied — including the `BTSC.` prefix at the front and the short hash after the final dot. A code cut off at either end can't be decoded. The Copy code button always copies the whole thing.

### help.trouble.no_class
Where: static/help.html:102-103 (li)

    **The class doesn't appear at character select.** You didn't restart. Quit the game completely and relaunch — imported classes only load at startup.

### help.trouble.no_mods
Where: static/help.html:104-105 (li)

    **There's no Mod Configuration entry / the game isn't modded.** The mod isn't installed yet — see [Get the mod](/download).

### help.trouble.other
Where: static/help.html:106-108 (li)

    **Anything else.** [Report a bug](https://github.com/ryanrinkel/BLANKthespire/issues) on GitHub. If the game crashed, include the lines from `%APPDATA%\SlayTheSpire2\logs\godot.log`.

### help.next.title
Where: static/help.html:113 (h2)

    Next

### help.next.forge
Where: static/help.html:114 (primary button); static/download.html:60 (inline link)

    Forge a class

### help.next.get_mod
Where: static/help.html:115 (button)

    Get the mod

## Download page (download.html)

### download.meta.title
Where: static/download.html:6 (title, before common.title_suffix)

    Get the mod

### download.header.sub
Where: static/download.html:31 (header brand sub)

    get the mod

### download.hero.title
Where: static/download.html:41 (h1)

    Play your forged classes in Slay the Spire 2

### download.hero.lede
Where: static/download.html:42-43 (p)

    Subscribe on the Steam Workshop and Steam does the rest — no folders, no unzipping, and updates arrive automatically.

### download.hero.subscribe
Where: static/download.html:44-46 (primary button)
Notes: links to {workshop_url} (stamped server-side as `{{WORKSHOP_URL}}`).

    ⬈ Subscribe on the Steam Workshop

### download.hero.step_1
Where: static/download.html:48 (li)

    **Subscribe** to Blank the Spire on the Workshop.

### download.hero.step_2
Where: static/download.html:49 (li)

    **Launch Slay the Spire 2.** Steam downloads the mod before the game starts.

### download.hero.step_3
Where: static/download.html:50-51 (li)

    **The mod loads itself.** **BaseLib** (the mod loader) comes along automatically as a Workshop dependency — you never install it by hand.

### download.hero.requires
Where: static/download.html:53 (hint)

    Requires Slay the Spire 2 on Steam.

### download.hero.sidelink
Where: static/download.html:54 (p)

    Where do I paste my code? → [Step-by-step with screenshots](/help)

### download.play.title
Where: static/download.html:58 (h2)

    Forge a class & play it

### download.play.step_1
Where: static/download.html:60 (li)

    [Forge a class](/app) on this site → copy the **import code** (starts with `BTSC.`).

### download.play.step_2
Where: static/download.html:61-63 (li)

    In-game: main menu → **Mod Configuration** → **BlankTheSpire** → paste into **Import a class code** → **Import** → **Restart game**. ([Where do I paste my code?](/help))

### download.play.step_3
Where: static/download.html:64 (li)

    Start a new run and pick your class. (The restart is required to load a new class — that's normal.)

### download.manual.summary
Where: static/download.html:69 (details summary)

    Manual install (advanced) — zip download

### download.manual.who
Where: static/download.html:70-71 (hint)

    Only for people who can't use the Steam Workshop (no Steam copy of the game, an offline machine, or a hand-managed `mods` folder). Everyone else: subscribe above.

### download.manual.button
Where: static/download.html:73-75 (button)
Notes: {version} is stamped server-side as `{{VERSION}}`.

    ⬇ Download BlankTheSpire-{version}.zip

### download.manual.one_download
Where: static/download.html:76 (hint)

    One download (BaseLib is bundled in this zip). Unzip into the game's `mods` folder.

### download.manual.install_title
Where: static/download.html:78 (h3)

    Install (one drop)

### download.manual.step_1
Where: static/download.html:80-81 (li)

    **Find your STS2 `mods` folder.** In Steam: right-click *Slay the Spire 2* → *Manage* → *Browse local files*. Make a `mods` folder there if it doesn't exist.

### download.manual.step_2
Where: static/download.html:82 (li, followed by download.manual.tree)

    **Unzip the download into that `mods` folder** so it looks like:

### download.manual.tree
Where: static/download.html:83-86 (preformatted folder tree)
Notes: preformatted; keep the folder names and alignment, only "← from the zip" is prose.

    Slay the Spire 2\
      mods\
        BaseLib\        ← from the zip
        BlankTheSpire\  ← from the zip

### download.manual.step_3
Where: static/download.html:88-89 (li)

    **Launch the game.** It'll start modded. (The log at `%APPDATA%\SlayTheSpire2\logs\godot.log` says `RUNNING MODDED` if you want to check.)

### download.manual.updating
Where: static/download.html:91 (hint)

    Updating later? Re-unzip a newer version over the same folder, overwriting.

### download.linux.title
Where: static/download.html:93 (h3)

    On Linux (Ubuntu / Steam, incl. Steam Deck)

### download.linux.lede
Where: static/download.html:94 (p)

    Same steps — the mod is platform-neutral; only the paths differ. Works natively or via Proton.

### download.linux.step_1
Where: static/download.html:96-99 (li)

    **Find `mods/`:** right-click *Slay the Spire 2* → *Manage* → *Browse local files* (works for native & Proton). Usually `~/.steam/steam/steamapps/common/Slay the Spire 2/` or `~/.local/share/Steam/steamapps/common/Slay the Spire 2/`. Make a `mods` folder if needed.

### download.linux.step_2
Where: static/download.html:100-101 (li)

    **Unzip into it:** `unzip BlankTheSpire-{version}.zip -d "<game dir>/mods"` → you get `mods/BaseLib/` and `mods/BlankTheSpire/`.

### download.linux.step_3
Where: static/download.html:102-105 (li)

    **Launch.** The log lives under your user data, not `%APPDATA%` — fastest way to find it: `find ~ -name godot.log 2>/dev/null`. (Native: `~/.local/share/Godot/app_userdata/SlayTheSpire2/logs/`; Proton: inside `steamapps/compatdata/2868840/pfx/…/AppData/Roaming/SlayTheSpire2/logs/`.)

### download.linux.loader_issue
Where: static/download.html:107-108 (hint)

    If the game won't load mods on your distro, that's a **BaseLib** (loader) issue, not the cards — tell me and we'll sort it.

### download.starters.title
Where: static/download.html:112 (h2)

    Starter classes

### download.starters.lede
Where: static/download.html:113 (p)

    No need to forge your first — paste any of these into **Import a class code** to play now.

### download.starters.tempest_name
Where: static/download.html:116 (h4)
Notes: the class name inside the code stays English (the code is data); this is only the heading.

    The Tempest

### download.starters.tempest_blurb
Where: static/download.html:116 (muted span after the name)

    — storm-caller; channels lightning & frost orbs, unleashes them in bursts

### download.starters.jackpot_name
Where: static/download.html:121 (h4)

    The Jackpot

### download.starters.jackpot_blurb
Where: static/download.html:121 (muted span)

    — slot-machine gambler; spin reels, match symbols, cash out for huge swings

### download.starters.broodmind_name
Where: static/download.html:126 (h4)

    The Broodmind

### download.starters.broodmind_blurb
Where: static/download.html:126 (muted span)

    — hive-queen; summons swarms and spreads poison as the brood grows

### download.issues.title
Where: static/download.html:132 (h2)

    Known issues (early build)

### download.issues.art
Where: static/download.html:134 (li)

    **Placeholder art** — orbs are colored circles, some art is generic. Cosmetic only.

### download.issues.relics
Where: static/download.html:135-136 (li)

    **Relic-collection screen may glitch** — opening the in-game Relics compendium can throw a harmless error. Doesn't affect runs; just back out.

### download.issues.restart
Where: static/download.html:137 (li)

    **Restart loads a new class** — the mod tells you; it's normal.

### download.issues.balance
Where: static/download.html:138 (li)

    Forged classes are **loosely balanced** — expect swingy/overpowered cards. That's half the fun.

### download.issues.report
Where: static/download.html:140-141 (hint)
Notes: {github_url} is stamped server-side as `{{GITHUB_URL}}`.

    Found a bug or a hang? [Open an issue]({github_url}/issues) — and if it crashed, include the lines from `%APPDATA%\SlayTheSpire2\logs\godot.log`.

### download.source.title
Where: static/download.html:145 (h2)

    Source & bug reports

### download.source.body
Where: static/download.html:146-147 (p)

    Blank the Spire is an open-source fan mod. The whole thing — mod, website, generator — is on GitHub.

### download.source.code
Where: static/download.html:148 (button); static/help.html:116 is the shorter common.footer.github

    Source code on GitHub

### download.source.report
Where: static/download.html:149 (button); static/help.html:106 (inline link in help.trouble.other)

    Report a bug

## Deck page (deck.html, deck.js)

### deck.meta.title
Where: static/deck.html:6 (title, before common.title_suffix); og:title / twitter:title :15, :20
Notes: {name} = the class name, stamped server-side (`{{TITLE}}`, web/app.py:400) with app.share.name_fallback when empty; deck.js:57 rewrites document.title the same way.

    {name}

### deck.meta.description
Where: static/deck.html:16, 21, 23 (og/twitter/meta description)
Notes: {description} = the class description (or concept), cut to 200 characters by web/app.py:403-404. Data, not copy.

    {description}

### deck.header.sub
Where: static/deck.html:30 (header brand sub)

    a forged class

### deck.header.sub_featured
Where: static/deck.js:75 (replaces deck.header.sub for a class in The Archive)

    from The Archive

### deck.lede
Where: static/deck.html:42-43 (p)

    Someone forged this class with Blank the Spire — copy the code below to play it, or [forge your own](/app).

### deck.lede_featured
Where: static/deck.js:72 (replaces deck.lede for a class in The Archive)

    A class from The Archive, free to play. Copy the code, paste it in-game — or make your own.

### deck.play.send_pc_tip
Where: static/deck.html:61 (title tooltip on Send to my PC)

    Share this class to your PC (AirDrop, Messages, Notes, Mail…)

### deck.play.remix
Where: static/deck.html:62 (primary button)

    Forge your own twist

### deck.play.title
Where: static/deck.html:66 (h3)

    Already have the mod?

### deck.play.step_1
Where: static/deck.html:68 (li)

    Subscribe on [Steam Workshop](/workshop).

### deck.play.step_2
Where: static/deck.html:69 (li)

    In Slay the Spire 2: *main menu → Mod Configuration → BlankTheSpire → Import a class code* → paste → *Import*.

### deck.play.step_3
Where: static/deck.html:70 (li)

    Restart the game and pick the class.

### deck.play.full_guide
Where: static/deck.html:72 (link to /help)

    Full guide with screenshots

### deck.dead.title
Where: static/deck.js:19 (h1 when /api/deck fails)

    This class link is no longer valid

### deck.dead.body
Where: static/deck.js:96-97 (p)

    It may have been deleted, or the link was mistyped. Ask whoever shared it for a fresh link — or forge your own class.

### deck.dead.forge
Where: static/deck.js:27 (primary button); web/app.py:381 (404 page button)

    Forge your own

### deck.dead.get_mod
Where: static/deck.js:31 (button); web/app.py:381 (404 page button)

    Get the mod

### deck.notfound.title
Where: web/app.py:377 (title of the server-rendered 404 page, before common.title_suffix); web/app.py:379 (h1)

    Class not found

### deck.notfound.body
Where: web/app.py:380 (p of the server-rendered 404 page)

    This class link is no longer valid — it may have been deleted, or the link was mistyped.

### deck.rules_in_english
Where: static/render.js renderRulesNote (under the cards of the result view and the /deck page; shown only when the site language is not English)
Notes: added 2026-10-27 by the i18n build, owner to review

    Card rules text is shown in English here; the game shows it in Chinese.

## Archive (archive.html, archive.js, featured.js)

### archive.meta.title
Where: static/archive.html:6 (title, before common.title_suffix); og:title / twitter:title :13, :19; header sub :25; h1 :36
Notes: the same text as landing.archive.title.

    The Archive

### archive.meta.description
Where: static/archive.html:7, 14, 20 (meta / og / twitter description)

    Classes forged with Blank the Spire, free to play.

### archive.lede
Where: static/archive.html:37-38 (p)

    Classes forged with Blank the Spire, free to play. Copy a code, paste it in-game, or [forge your own](/app).

### archive.empty
Where: static/archive.html:40 (empty state)

    Nothing in The Archive yet.

### archive.tile.caption
Where: static/featured.js:58 (tile caption on the landing strip and /archive)
Notes: {word} = the class's five-letter board word, upper case.

    {word} the Spire

### archive.tile.splash_alt
Where: static/featured.js:40 (img alt)

    Splash art for {name}

### archive.tile.cards
Where: static/featured.js:73 (tile meta)
Notes: {count} = cards in the class (always many, so no .one form).

    {count} cards

## Sign-in pages (signin.html, signin-continue.html, signin-expired.html, signin.js, webview.js)

### signin.meta.title
Where: static/signin.html:6 (title, before common.title_suffix); static/signin.html:22 (h1)

    Sign in

### signin.header.sub
Where: static/signin.html:14; static/signin-continue.html:14; static/signin-expired.html:14 (header brand sub)

    sign in

### signin.lede
Where: static/signin.html:23-24 (p)

    Pick a provider — we only ever see the email address and display name it shares. No passwords, ever.

### signin.open_browser
Where: static/signin.html:30 (button, before signin.js rewrites it); static/signin.js:33 (button)
Notes: {browser} = "Safari" (iOS) or "Chrome" (Android); the HTML default reads "Open in Safari".

    Open in {browser}

### signin.none
Where: static/signin.html:37 (hint)

    Sign-in is not configured on this server.

### signin.or
Where: static/signin.html:41 (divider)

    or

### signin.email.label
Where: static/signin.html:43 (label)

    Get a sign-in link by email

### signin.email.placeholder
Where: static/signin.html:44 (input placeholder)

    you@example.com

### signin.email.button
Where: static/signin.html:46 (button); static/signin.js:78 (restored after a failure)

    Email me a link

### signin.email.error
Where: static/signin.html:47 (hint)

    That didn’t go through — try again in a moment.

### signin.email.sending
Where: static/signin.js:64 (button while sending)

    Sending…

### signin.email.sent
Where: static/signin.js:86 (replaces the form)

    Check your inbox — the link expires in 15 minutes.

### signin.try_instead
Where: static/signin.html:51 (p)

    Just want to play one? [Try a featured class](/#featured) — no account needed.

### signin.back_app
Where: static/signin.html:57 (button, link mode only)

    Back to the app

### signin.back_splash
Where: static/signin.html:58 (button); static/signin-expired.html:28 (button)

    Back to the splash

### signin.provider.continue
Where: static/signin.js:134 (provider button)
Notes: {provider} = Google, Discord or GitHub (brand names, static/signin.js:7).

    Continue with {provider}

### signin.provider.link
Where: static/signin.js:134 (provider button in link mode)

    Link {provider}

### signin.link.title
Where: static/signin.js:117 (replaces signin.meta.title's h1 in link mode)

    Link another sign-in

### signin.link.lede
Where: static/signin.js:118-119 (replaces signin.lede in link mode)
Notes: {who} = the account's name, email, or signin.link.who_fallback.

    You're signed in as {who}. Linking lets you sign in with any of these later.

### signin.link.who_fallback
Where: static/signin.js:118

    this account

### signin.link.all_linked
Where: static/signin.js:149 (replaces signin.none in link mode)

    Every sign-in method this server offers is already linked to your account.

### signin.webview.head
Where: static/signin.js:29 (in-app browser box)
Notes: {where} = signin.webview.where_app or signin.webview.where_generic.

    You're in {where} — Google can't sign you in here.

### signin.webview.where_app
Where: static/webview.js:42
Notes: {app} = YouTube, Instagram, Facebook, Discord, Reddit, TikTok, Snapchat or LinkedIn.

    the {app} app's browser

### signin.webview.where_generic
Where: static/webview.js:42

    an in-app browser

### signin.webview.menu_ios
Where: static/webview.js (hint under the Open in Safari button, shown by signin.js)
Notes: a whole sentence with its own full stop (signin.js appended an English "." until 2026-10-27).

    or tap the ··· menu at the top right and choose Open in Safari.

### signin.webview.menu_android
Where: static/webview.js (hint, shown by signin.js)
Notes: a whole sentence with its own full stop, as signin.webview.menu_ios.

    or tap the ⋮ menu at the top right and choose Open in Chrome (or Open in browser).

### signin.webview.email_label
Where: static/signin.js:45-46 (replaces signin.email.label inside an in-app browser)
Notes: {browser} = "Safari" or "Chrome".

    Enter your email and we'll send a link; it opens in {browser} and you're in.

### signin.continue.title
Where: static/signin-continue.html:6 (title, before common.title_suffix)

    Continue sign-in

### signin.continue.heading
Where: static/signin-continue.html:20 (h1)

    One more click

### signin.continue.body
Where: static/signin-continue.html:21 (p)

    Your sign-in link checks out. Press the button to finish signing in.

### signin.continue.button
Where: static/signin-continue.html:26 (primary button)

    Continue to Blank the Spire

### signin.continue.expiry
Where: static/signin-continue.html:29 (hint)

    Links expire 15 minutes after they are sent and work only once.

### signin.expired.title
Where: static/signin-expired.html:6 (title, before common.title_suffix)

    Link expired

### signin.expired.heading
Where: static/signin-expired.html:20 (h1)

    This link is no longer valid

### signin.expired.body
Where: static/signin-expired.html:21-22 (p)

    This sign-in link has expired or was already used. Request a new one — they last 15 minutes and work once.

### signin.expired.button
Where: static/signin-expired.html:25 (primary button)

    Get a new sign-in link

### signin.code.label
Where: static/signin.html (label in the code box, shown once the link is sent)

    Or type the 6-digit code from the email:

### signin.code.hint
Where: static/signin.html (hint under the code box)

    Use it when the link opens somewhere else — another browser, or your mail app's own. It works once, for 15 minutes.

### signin.code.button
Where: static/signin.html (code box button); static/signin.js (restored after a failure)

    Sign in

### signin.code.checking
Where: static/signin.js (code box button while checking)

    Checking…

### signin.code.wrong
Where: static/signin.js (code box error)

    That code doesn't match — check the newest email and try again.

### signin.code.expired
Where: static/signin.js (code box error)

    That code has expired or was already used. Send a new link below.

### signin.code.too_many
Where: static/signin.js (code box error)

    Too many tries. Send a new link below.

### signin.code.resend
Where: static/signin.html (button under the code box; brings the email form back)

    Send a new link

### signin.continue.code_handoff
Where: static/signin-continue.html (hint under the Continue button)

    Started signing in on another browser? Go back there and type the code from the email instead — this button only signs you in here.

## Email

### email.magic.subject
Where: web/auth.py:353 (magic-link subject)

    Your Blank the Spire sign-in link

### email.magic.body
Where: web/auth.py:350-352 (magic-link body, plain text only)
Notes: {url} = the single-use link. Deliberately plain text with one URL (HTML mail lands sign-in links in spam); keep it short.

    Here is your sign-in link for Blank the Spire:
    
    {url}
    
    This link expires in 15 minutes. If you didn't ask for it, ignore this email.

### email.magic.body_code
Where: web/auth.py _send_magic_link (magic-link body with the sign-in code, plain text only; replaces email.magic.body since 2026-10-29)
Notes: {url} = the single-use link; {code} = the 6-digit code, printed as "482 913". Same rules as email.magic.body: plain text, one URL, short.

    Here is your sign-in link for Blank the Spire:

    {url}

    Or enter this code where you started signing in: {code}

    The link and the code expire in 15 minutes and work once. If you didn't ask for them, ignore this email.

### email.class.subject
Where: web/app.py:1888 ("Email it to me" subject)
Notes: {name} = class name.

    Your Slay the Spire 2 class: {name}

### email.class.intro
Where: web/app.py:1889 (text), web/app.py:1897 (HTML, with {name} in bold)

    Here is {name}, the class you forged on Blank the Spire.

### email.class.open_on_pc
Where: web/app.py:1890 (text), web/app.py:1898 (HTML); followed by the /deck link

    Open it on the PC that runs Slay the Spire 2:

### email.class.paste_code
Where: web/app.py:1891-1892 (text, with "->" arrows), web/app.py:1899-1900 (HTML, with → arrows and *Import a class code* in italics); followed by the import code

    Or paste this import code in-game (main menu → Mod Configuration → BlankTheSpire → *Import a class code* → Import, then restart the game):

### email.class.no_mod_text
Where: web/app.py:1894 (text version)
Notes: {url} = the /workshop link.

    Don't have the mod yet? {url}

### email.class.no_mod_html
Where: web/app.py:1902 (HTML version)

    Don't have the mod yet? [Get it on Steam Workshop]({url}).

### email.class.footer
Where: web/app.py:1895 (text), web/app.py:1903 (HTML, grey)

    You asked for this email from your My Classes page; nothing else is sent.

## Server errors

### server.auth.sign_in_required
Where: web/auth.py:424 (JSON error, 401 on any signed-in API call)

    sign in required

### server.auth.unknown_provider
Where: web/auth.py:485, 500 (plain-text page, 404)

    Unknown sign-in provider.

### server.auth.provider_not_configured
Where: web/auth.py:488, 503 (plain-text page, 503)
Notes: {provider} = provider name title-cased (Google, Github, Discord).

    {provider} sign-in is not configured on this server.

### server.auth.email_not_configured
Where: web/auth.py:527 (JSON error, 503)

    email sign-in is not configured on this server

### server.auth.check_inbox
Where: web/auth.py:528 (JSON message)
Notes: not shown today; signin.js shows signin.email.sent instead.

    Check your inbox.

### server.csrf
Where: web/app.py:133 (JSON error, 403; a stale or cross-site page)

    missing X-Requested-With header (cross-site request blocked)

### server.not_found
Where: web/app.py:516-552, 1818-1872, 1919, 1948, 1952, 2081, 2110, 2121, 2175, 2232 (JSON error, 404)

    not found

### server.forge.no_concept
Where: web/app.py:1258 (JSON error, 400)

    describe a class first.

### server.forge.hosted_retired
Where: web/app.py:1261-1262 (JSON error, 410)

    the hosted Anthropic path is retired — use a token or bring your own API key.

### server.forge.unknown_mode
Where: web/app.py:1264 (JSON error, 400)

    unknown forge mode.

### server.forge.at_capacity
Where: web/app.py:1289-1290 (JSON error, 503)

    the forge is at full capacity right now — please try again in a few minutes.

### server.forge.already_running
Where: web/app.py:1294 (JSON error, 429)

    you already have a forge in progress — wait for it to finish.

### server.forge.out_of_tokens
Where: web/app.py:1318-1319, 1324-1325 (JSON error, 402)

    you're out of tokens — get a forge token under the Forge button, or bring your own API key to keep forging.

### server.forge.saving_failed
Where: web/app.py:1386 (forge error event)
Notes: {e} = the exception text.

    forged, but saving failed: {e}

### server.forge.too_long
Where: web/app.py:1427-1428 (forge error event)

    this forge is taking far too long — it's been abandoned and your token refunded. If it does finish, the class will appear in My Classes.

### server.forge.too_long_job
Where: web/app.py:1425 (stored job error, shown when a lost browser polls)
Notes: {max_seconds} = the cap in whole seconds (BTSWEB_FORGE_MAX_SECONDS).

    the forge ran past {max_seconds}s and was abandoned

### server.forge.restarted
Where: web/app.py:1067 (stored job error after a deploy restart, shown when a lost browser polls)

    the server restarted mid-forge — token refunded

### server.forge.queue_timeout
Where: web/app.py:1468-1469 (forge error event)

    the forge stayed at capacity too long — nothing was forged (and no token was spent); please try again later.

### server.forge.unexpected
Where: web/app.py:1492 (forge error event)

    unexpected error: {e}

### server.forge.no_such_forge
Where: web/app.py:1558 (JSON error, 404, job poll)

    no such forge.

### server.forge.choice_gone
Where: web/app.py:1588 (JSON error, 404; printed in the console after "• ")

    no pending choice for this forge — it may have already timed out.

### server.forge.not_yours
Where: web/app.py:1590 (JSON error, 403)

    this isn't your forge.

### server.class.name_required
Where: web/app.py:1856 (JSON error, 400, rename)

    name is required

### server.email.not_configured
Where: web/app.py:1914 (JSON error, 503)

    email isn't set up on this server — copy the code or use the share link

### server.email.no_address
Where: web/app.py:1923-1924 (JSON error, 400)

    this account has no email address — sign in with Google, GitHub or email to use this, or copy the code instead

### server.email.rate_limited
Where: web/app.py:1929 (JSON error, 429)

    that's a lot of emails — try again in an hour, or copy the code

### server.email.send_failed
Where: web/app.py:1935 (JSON error, 502)

    the email didn't go out — try again later, or copy the code

### server.archive.already_featured
Where: web/app.py:2083 (JSON error, 409, nominate)

    already in The Archive

### server.feedback.class_required
Where: web/app.py:2163, 2220 (JSON error, 400)

    class_id is required

### server.feedback.unknown_category
Where: web/app.py:2166, 2223 (JSON error, 400)

    unknown feedback category

### server.feedback.card_required
Where: web/app.py:2168 (JSON error, 400)

    card_id is required

### server.feedback.unknown_kind
Where: web/app.py:2225 (JSON error, 400)

    unknown element kind

### server.feedback.too_fast
Where: web/app.py:2170, 2227 (JSON error, 429)

    too much feedback too fast — try again in a while.

### server.feedback.card_missing
Where: web/app.py:2179 (JSON error, 404)

    card not found in class

### server.feedback.element_missing
Where: web/app.py:2236 (JSON error, 404)

    element not found in class

### server.feedback.not_recorded
Where: web/app.py:2184, 2242 (JSON error, 503)

    could not record feedback

### server.billing.unavailable
Where: web/billing.py:248, 320 (JSON error, 503)

    donations aren't available right now.

### server.billing.both
Where: web/billing.py:256 (JSON error, 400)

    send either a tier or a custom amount, not both.

### server.billing.custom_range
Where: web/billing.py:260-261 (JSON error, 400)
Notes: {CUSTOM_MIN_DOLLARS} = 11, {CUSTOM_MAX_DOLLARS} = 500.

    custom amounts are whole dollars from ${CUSTOM_MIN_DOLLARS} to ${CUSTOM_MAX_DOLLARS}.

### server.billing.pick_tier
Where: web/billing.py:265 (JSON error, 400)

    pick one of the donation amounts.

### server.billing.checkout_failed
Where: web/billing.py:298 (JSON error, 502)

    couldn't start checkout — try again in a minute.

### server.billing.session_required
Where: web/billing.py:324 (JSON error, 400, return from Stripe)

    session_id is required

### server.billing.unknown_session
Where: web/billing.py:328 (JSON error, 404)

    unknown checkout session

### server.billing.not_your_session
Where: web/billing.py:330 (JSON error, 403)

    not your checkout session

### server.byok.model_not_offered
Where: web/forge.py:681-682 (JSON error at forge start, 400)
Notes: {m} = the model id.

    Your provider doesn't offer a model called “{m}” on this key. Reload your model list and pick one from it.

### server.byok.refusal.model_not_found
Where: web/forge.py:790-791 (forge error, a provider refusal explained)
Notes: every server.byok.refusal.* sentence is followed by server.byok.refusal_suffix. {model} = the model id.

    Your provider doesn't offer a model called “{model}” on this key. Open “Bring your own key”, click “Reload model list” and pick one from the list (check the provider matches the key, too).

### server.byok.refusal.openrouter_routing
Where: web/forge.py:796-797

    OpenRouter has no provider it is allowed to route this model to on your account. Check Settings → Privacy on openrouter.ai (free models need data-sharing providers enabled) or pick another model.

### server.byok.refusal.no_credits
Where: web/forge.py:800-801

    Your provider account has no credits left, so it refused the request. Add credits on your provider's billing page, then forge again — nothing was charged here.

### server.byok.refusal.bad_key
Where: web/forge.py:804-805

    Your provider rejected the API key. Paste a current key from your provider's dashboard (and check the provider dropdown matches where the key came from).

### server.byok.refusal.forbidden
Where: web/forge.py:807-808

    Your provider says this key isn't allowed to use that model or endpoint. Check the key's permissions on your provider's dashboard, or pick another model.

### server.byok.refusal.request_too_large
Where: web/forge.py:815-817

    Your provider's plan caps how many tokens one request may send per minute, and a single forge prompt is larger than that cap, so retrying won't help. Upgrade the plan on your provider account (Groq: Settings → Billing → Plans → Developer) or forge with a key from another provider.

### server.byok.refusal.rate_limited
Where: web/forge.py:819-820

    Your provider rate-limited the key. Wait a minute and forge again, or raise the limit on your provider account.

### server.byok.refusal_suffix
Where: web/forge.py:852
Notes: fragment, starts with a space. {raw[:300]} = the provider's own error text, cut to 300 characters.

     (Your provider said: {raw[:300]})

### server.byok.not_generated
Where: web/forge.py:853 (forge error when no refusal matched)
Notes: {tail} = the forge's last log line.

    class did not generate: {tail}

### server.byok.url_scheme
Where: web/forge.py:165 (JSON error from /api/models, or a forge error)

    base URL must start with http:// or https://.

### server.byok.url_host
Where: web/forge.py:167

    base URL needs a hostname.

### server.byok.url_resolve
Where: web/forge.py:174

    could not resolve {parsed.hostname}.

### server.byok.url_private
Where: web/forge.py:178-179

    base URL points at a private or internal address — use a public provider endpoint.

### server.byok.anthropic_incomplete
Where: web/forge.py:289, 524

    Anthropic BYOK needs api_key and model together.

### server.byok.anthropic_unavailable
Where: web/forge.py:302

    Anthropic generation unavailable: {e}

### server.byok.incomplete
Where: web/forge.py:314, 537

    BYOK needs base_url, api_key, and model together.

### server.byok.server_anthropic_retired
Where: web/forge.py:347, 556

    the server-side Anthropic path is retired — use a token or bring your own API key.

### server.byok.no_path
Where: web/forge.py:349, 557

    no generation path selected (need a BYOK key, a token, or fake).

### server.byok.list_needs_key
Where: web/forge.py:638 (JSON error from /api/models)

    base URL and API key are both required to list models.

### server.byok.list_http
Where: web/forge.py:647 (JSON error from /api/models)

    endpoint returned HTTP {e.code} — check the key, URL, and model access.

### server.byok.list_unreachable
Where: web/forge.py:649 (JSON error from /api/models)

    could not reach the endpoint: {e.reason}

### server.forge.concept_empty
Where: web/forge.py:719

    concept is empty.

### server.forge.hosted_unavailable
Where: web/forge.py:750 (forge error on the token path)

    hosted generation unavailable: {e}

## Stripe checkout

### stripe.line_item.donation
Where: web/billing.py:278 (Checkout line item name; also on Stripe's receipt)

    Donation — Blank the Spire

### stripe.line_item.fee
Where: web/billing.py:285 (Checkout line item name; also on Stripe's receipt)

    Card processing fee

## Steam Workshop

### workshop.title
Where: workshop/workspace/workshop.json:2 (title)

    Blank the Spire — forge a class from a sentence

### workshop.description
Where: workshop/workspace/workshop.json:3 (description, BBCode)
Notes: canonical copy. workshop/DESCRIPTION.bbcode has the same text; it differs only in line endings (the json escapes CRLF as \r\n) and one trailing newline at the end of the .bbcode file. Keep BBCode tags verbatim. Contains "contains no purchases".

    [h1]Custom playable classes for Slay the Spire 2![/h1]
    
    Describe a class in plain English at [url=https://blankthespire.com]blankthespire.com[/url] — [i]"a venomous plague doctor who sacrifices health to stack poison, then turns blood into armor"[/i] — and the forge turns it into a real, playable Slay the Spire 2 character with its own cards, relic, mechanics, potion and identity. You get an import code; paste it in-game and play.
    
    [b]Unofficial fan mod. Not affiliated with or endorsed by Mega Crit.[/b]
    
    [h2]How to play[/h2]
    [olist]
    [*]Subscribe to this mod (BaseLib is a dependency and installs automatically).
    [*]Go to [url=https://blankthespire.com]blankthespire.com[/url] and forge a class — you'll get an import code starting with [b]BTSC.[/b] (No time to forge? The site lists ready-made starter classes to copy.)
    [*]In-game: main menu → Mod Configuration → BlankTheSpire → paste the code into [b]Import a class code[/b] → Import → Restart game.
    [*]Start a new run and pick your forged class.
    [/olist]
    
    Forging happens on the website, not in this mod. Bring your own LLM API key and forge as much as you like, or use the site's hosted models. This Workshop item is free and open source, and contains no purchases. You are free to visit the site and play other user's classes.
    
    [h2]Transparency: AI-generated content[/h2]
    Forged classes (card text, names, splash art) are generated by AI on the website, at your request, and enter the game only through your import code. This Workshop package itself contains no AI-generated assets — it is the mod's human-written runtime plus the vocabulary of mechanics the generator is allowed to use. Generation is constrained to that vocabulary and schema-validated, so forged classes are guaranteed to load and play.
    
    [h2]Known issues (early build)[/h2]
    [list]
    [*]Placeholder art in places — orbs are plain colored circles; some card art is generic.
    [*]The in-game Relics compendium can throw a harmless mod-loader error; back out and keep playing.
    [*]You must restart after importing a class — the mod tells you; it's normal.
    [*]Balance is loose by design — expect the occasional swingy or hilariously broken card. Tell us what breaks.
    [/list]
    
    [h2]Feedback and source[/h2]
    Bugs, hangs, or broken cards: [url=https://github.com/ryanrinkel/BLANKthespire/issues]open a GitHub issue[/url]. The mod is open source (MIT) at [url=https://github.com/ryanrinkel/BLANKthespire]github.com/ryanrinkel/BLANKthespire[/url]. It includes no game code, binaries, or copyrighted game data — you need to own Slay the Spire 2.

### workshop.change_note
Where: workshop/workspace/workshop.json:5 (changeNote, shown in the item's change log)
Notes: rewritten per upload, not stable copy.

    Restored the preview screenshots (no mod changes; still v0.4.0).

## In-game mod UI

### mod.manifest.name
Where: mod/BlankTheSpire.json:3 (name in the game's mod list)

    Blank the Spire

### mod.manifest.description
Where: mod/BlankTheSpire.json:5 (description in the game's mod list)

    A data-driven, LLM-extensible custom character for Slay the Spire 2.

### mod.section.import
Where: mod/BlankTheSpire/localization/eng/settings_ui.json:2 (ConfigSection header)
Notes: lives in the game's localization folder since v0.5.0 (localization/eng/settings_ui.json, Chinese in localization/zhs/settings_ui.json; ForgeConfig.cs:24 names the key); the help page and site copy name it, keep them in sync.

    Import a class code

### mod.section.apply
Where: mod/BlankTheSpire/localization/eng/settings_ui.json:3 (ConfigSection header)

    Apply changes

### mod.button.import
Where: mod/BlankTheSpire/localization/eng/settings_ui.json:4 (button)
Notes: BaseLib buttons are a fixed 324px texture: keep button text very short.

    Import

### mod.button.clear_slot
Where: mod/BlankTheSpire/localization/eng/settings_ui.json:5 (button)

    Clear slot

### mod.button.clear_all
Where: mod/BlankTheSpire/localization/eng/settings_ui.json:6 (red button)

    Clear ALL

### mod.button.restart
Where: mod/BlankTheSpire/localization/eng/settings_ui.json:7 (button)

    Restart game

### mod.settings.class_code
Where: mod/BlankTheSpire/localization/eng/settings_ui.json:9 (row label of the code field)
Notes: every mod.settings.* / mod.section.* / mod.button.* string lives in the game's own localization folder (localization/eng/settings_ui.json); the Chinese is the sibling localization/zhs/settings_ui.json. The mod.dialog.* / mod.codec.* / mod.import.* strings are ForgedText defaults, Chinese in Engine/ForgedText.zhs.cs.

    Class code

### mod.settings.class_slot
Where: mod/BlankTheSpire/localization/eng/settings_ui.json:10 (row label of the slot slider)

    Class slot (0 = auto)

### mod.settings.import_title
Where: mod/BlankTheSpire/localization/eng/settings_ui.json:12 (row label of the Import button)

    Import class into a slot

### mod.settings.import_tip
Where: mod/BlankTheSpire/localization/eng/settings_ui.json:13 (hover tip)

    Paste a class (BTSC) code from blankthespire.com into the "Class code" field, then press Import. Slot 0 picks automatically: it updates a same-named class, or takes the lowest empty slot.

### mod.settings.clear_title
Where: mod/BlankTheSpire/localization/eng/settings_ui.json:15 (row label)

    Clear one class slot

### mod.settings.clear_tip
Where: mod/BlankTheSpire/localization/eng/settings_ui.json:16 (hover tip)

    Removes the forged class in the selected slot. Set "Class slot" above to 1 or higher first.

### mod.settings.clear_all_title
Where: mod/BlankTheSpire/localization/eng/settings_ui.json:18 (row label)

    Delete ALL forged classes

### mod.settings.clear_all_tip
Where: mod/BlankTheSpire/localization/eng/settings_ui.json:19 (hover tip)

    Removes every imported class at once. This cannot be undone.

### mod.settings.restart_title
Where: mod/BlankTheSpire/localization/eng/settings_ui.json:21 (row label); named on the help page (help.steps.step_5)

    Restart game (applies changes)

### mod.settings.restart_tip
Where: mod/BlankTheSpire/localization/eng/settings_ui.json:22 (hover tip)

    Closes the game and reopens it automatically via Steam. Imported or cleared classes only take effect after a restart.

### mod.dialog.import_title
Where: mod/BlankTheSpireCode/ForgeConfig.cs:40 (dialog title)

    Import class

### mod.dialog.import_empty
Where: mod/BlankTheSpireCode/ForgeConfig.cs:41 (dialog body)

    Paste a class code into the "Class code" field above first.

### mod.dialog.import_failed_title
Where: mod/BlankTheSpireCode/ForgeConfig.cs:47 (dialog title)
Notes: the body is one of the mod.codec.* messages.

    Import failed

### mod.dialog.wrong_type_title
Where: mod/BlankTheSpireCode/ForgeConfig.cs:52 (dialog title)

    Wrong code type

### mod.dialog.wrong_type_body
Where: mod/BlankTheSpireCode/ForgeConfig.cs:53 (dialog body)

    That code isn't a class code. Paste a class (BTSC) code from blankthespire.com.

### mod.dialog.rejected_title
Where: mod/BlankTheSpireCode/ForgeConfig.cs:59 (dialog title)

    Import rejected

### mod.dialog.rejected_body
Where: mod/BlankTheSpireCode/ForgeConfig.cs:60 (dialog body)
Notes: {err} = one of the mod.import.* messages (or a card-validation message, see Notes on mod.import.slots_full).

    The code decoded, but the class isn't playable here:
    {err}

### mod.dialog.imported_title
Where: mod/BlankTheSpireCode/ForgeConfig.cs:70 (dialog title)

    Class imported

### mod.dialog.imported_body
Where: mod/BlankTheSpireCode/ForgeConfig.cs:71 (dialog body; the "restart" prompt)
Notes: {slot} = the slot number, two digits. "Restart game" names mod.button.restart.

    Imported into class slot {slot}.
    
    Press "Restart game" below, then pick the class on the character-select screen.

### mod.dialog.clear_title
Where: mod/BlankTheSpireCode/ForgeConfig.cs:82, 88 (dialog title)

    Clear class

### mod.dialog.clear_need_slot
Where: mod/BlankTheSpireCode/ForgeConfig.cs:83 (dialog body)
Notes: {max} = number of class slots.

    Set "Class slot" above to the class slot to clear (1..{max}), then click again.

### mod.dialog.cleared
Where: mod/BlankTheSpireCode/ForgeConfig.cs:89 (dialog body)
Notes: {slot} = the slot number, two digits.

    Cleared class slot {slot}.
    Press "Restart game" to update the game.

### mod.dialog.already_empty
Where: mod/BlankTheSpireCode/ForgeConfig.cs:90 (dialog body)
Notes: {slot} = the slot number, two digits.

    Class slot {slot} was already empty.

### mod.dialog.clear_all_title
Where: mod/BlankTheSpireCode/ForgeConfig.cs:98 (dialog title)

    Clear all forged classes

### mod.dialog.clear_all_body
Where: mod/BlankTheSpireCode/ForgeConfig.cs:99 (dialog body)
Notes: {n} = classes removed; "class(es)" is the code's plural.

    Removed {n} forged class(es). Empty class slots stay hidden.
    Press "Restart game" to update the game.

### mod.dialog.restart_title
Where: mod/BlankTheSpireCode/ForgeConfig.cs:111, 127 (dialog title)

    Restart

### mod.dialog.restart_nothing
Where: mod/BlankTheSpireCode/ForgeConfig.cs:112 (dialog body)

    Nothing imported yet this session.
    (Restarting will still apply any classes imported earlier.)

### mod.dialog.restart_failed
Where: mod/BlankTheSpireCode/ForgeConfig.cs:128 (dialog body)
Notes: {err} = the system error.

    Couldn't auto-relaunch:
    {err}
    
    Please quit and start the game yourself to apply changes.

### mod.codec.empty
Where: mod/BlankTheSpireCode/Engine/BTS1Codec.cs:52 (body of mod.dialog.import_failed_title)
Notes: the codec messages start lower case because they were written as log fragments; they are the only text a player sees for a bad code.

    empty code.

### mod.codec.not_bts
Where: mod/BlankTheSpireCode/Engine/BTS1Codec.cs:59

    not a Blank the Spire code.

### mod.codec.bad_magic
Where: mod/BlankTheSpireCode/Engine/BTS1Codec.cs:62

    not a Blank the Spire (BTS1/BTSC) code.

### mod.codec.bad_version
Where: mod/BlankTheSpireCode/Engine/BTS1Codec.cs:65

    malformed code (bad version field).

### mod.codec.needs_update
Where: mod/BlankTheSpireCode/Engine/BTS1Codec.cs:68
Notes: {ver} = the code's vocabulary version; {max} = the mod's.

    this code needs a newer Blank the Spire (code is v{ver}, this mod supports v{max}). Update the mod.

### mod.codec.corrupted
Where: mod/BlankTheSpireCode/Engine/BTS1Codec.cs:75
Notes: {err} = the decoder's error message.

    corrupted code ({err}).

### mod.codec.checksum
Where: mod/BlankTheSpireCode/Engine/BTS1Codec.cs:78

    corrupted code (checksum mismatch — try copying it again).

### mod.import.slots_full
Where: mod/BlankTheSpireCode/Engine/ForgedCharacters.cs:1547 ({err} in mod.dialog.rejected_body)
Notes: {n} = number of class slots. The other importer messages in ForgedCharacters.cs (bad bundle JSON, card N invalid, too many cards, ...) are validator output for a malformed code, not copy; they are left out.

    all {n} class slots are full — clear one first.

### mod.import.write_failed
Where: mod/BlankTheSpireCode/Engine/ForgedCharacters.cs:1550 ({err} in mod.dialog.rejected_body)
Notes: {err} = the system error.

    failed to write class files: {err}

## Forge console stage headers

These are the progress lines a player watches in the forge console (static/index.html #log), in the order they
appear. Each text block is the Python template as written in the code, without the `f` prefix and quotes;
`{...}` are Python expressions. The browser prints each one after "• ". Besides these 27 headers, about 110
other detail templates reach the same console: 56 `note(...)` calls in generation/btsgen/class_forge.py, 63
`self._note(...)` calls in generation/btsgen/frontend/builder.py, the card-art notes in web/app.py:822-902
(including the multi-line rate-limit explainer at web/app.py:734), and 8 more in generation/btsgen/art/card.py
and art/enrich.py. Splash and sprite art lines (generation/btsgen/art/splash.py) are NOT streamed to the
browser: web/app.py:652 calls them without a progress sink, so they only reach the server log.

### console.start
Where: web/app.py:1509-1510 (first event of stream(), normal forge)

    starting…

### console.start_interactive
Where: web/app.py:1509 (first event of stream(), Interactive forge on)

    starting… (interactive forge: you'll pick the engines after the map stage)

### console.queue.busy
Where: web/app.py:1462-1463 (worker, when every forge slot is taken)
Notes: two adjacent f-strings joined.

    the forge is busy — you're in line at position {last_pos} (your spot is held, hang tight)…

### console.queue.position
Where: web/app.py:1476

    in line: position {pos}…

### console.queue.turn
Where: web/app.py:1477

    it's your turn — forging now…

### console.stage.harness
Where: generation/btsgen/class_forge.py:3462 (first line the generator writes)
Notes: full expression: `f"forge harness v{_harness} (vocab v{VOCAB_VERSION})" + (" [creative harness v2]" if _v2 else "")`. A version stamp; it may not need translating.

    forge harness v{_harness} (vocab v{VOCAB_VERSION})

### console.stage.front_end
Where: generation/btsgen/class_forge.py:3487

    running the staged creative front-end...

### console.stage.cloud
Where: generation/btsgen/frontend/builder.py:374

    [1/6] cloud: brainstorming free associations on '{concept}'...

### console.stage.map
Where: generation/btsgen/frontend/builder.py:397

    [2/6] map: matching each thread to the game's mechanical archetypes...

### console.stage.your_call
Where: generation/btsgen/frontend/builder.py:775 (Interactive forge only)

    [2.5/6] your call: pick up to 2 of the matched engines to build around...

### console.stage.compose
Where: generation/btsgen/frontend/builder.py:419-420
Notes: {fuse_desc} = "three archetypes in a tension triangle" (triad, every web forge) or "two archetypes in tension" (builder.py:418); both are copy too.

    [3/6] compose: sketching {len(dossier.candidates)} class identities, each fusing {fuse_desc}:

### console.stage.pick
Where: generation/btsgen/frontend/builder.py:425

    [4/6] pick: weighing the candidates for distinctiveness, taking the boldest buildable one...

### console.stage.relic_intent
Where: generation/btsgen/frontend/builder.py:435

    [5/6] relic: designing the keystone relic that embodies this build...

### console.stage.orbs
Where: generation/btsgen/frontend/builder.py:450 (orb classes only)

    [5/6] orbs: deciding what this class channels (its own orbs vs the base elements)...

### console.stage.blueprint
Where: generation/btsgen/frontend/builder.py:462

    [6/6] blueprint: translating '{chosen.name}' into card briefs, pools, and numbers...

### console.stage.blueprint_ready
Where: generation/btsgen/class_forge.py:3529-3531
Notes: full expression: `f"blueprint ready: '{bp['name']}' ({bp.get('max_hp', '?')} HP)" + (f" built around {_arche}" if _arche else "") + f" - now designing {len(bp['cards'])} cards one by one:"`.

    blueprint ready: '{bp['name']}' ({bp.get('max_hp', '?')} HP) built around {_arche} - now designing {len(bp['cards'])} cards one by one:

### console.card.designing
Where: generation/btsgen/class_forge.py:3633-3635 (per-card counter, before the card is designed)
Notes: full expression appends `(f" - {str(plan.get('theme'))[:90]}" if plan.get("theme") else "")`.

    card {i+1}/{total}: designing '{plan.get('name_hint', '?')}' - {plan.get('rarity', '?')} {plan.get('type', '?')}, cost {plan.get('cost', '?')}

### console.card.ready
Where: generation/btsgen/class_forge.py:3714-3715 (per-card counter, after the card passes)

    card {i+1}/{total}: {pres.card.get('name')} ready ({pres.card.get('rarity')} {pres.card.get('type', '')})

### console.stage.relic
Where: generation/btsgen/class_forge.py:3872

    designing the keystone starter relic...

### console.relic.ok
Where: generation/btsgen/class_forge.py:3902

    relic OK: {relic.get('name')}

### console.relic.fallback
Where: generation/btsgen/class_forge.py:3897-3898
Notes: followed by up to three validator errors joined by "; ".

    relic invalid after repair; shipping without a forged relic (defaults to Burning Blood):

### console.done.bundle
Where: generation/btsgen/class_forge.py:4030-4031 (the generator's success line)
Notes: full expression appends `(f", relic '{relic['name']}'" if relic is not None else "")`.

    bundle assembled: {len(cards)} cards, starting deck {sum(d['count'] for d in starting_deck)} cards

### console.art.cards_start
Where: web/app.py:822 (card-art step, after the class is saved)

    card art: {total} cards…

### console.art.cards_progress
Where: web/app.py:872

    card art {done}/{total}…

### console.art.cards_packed
Where: web/app.py:899-900 (last server line before the browser prints app.console.done)
Notes: full expression appends `(f" — {len(throttled)} refused by the provider's rate limit" if throttled else "")`.

    card art: packed {len(made)}/{total} portraits

### console.fail.front_end
Where: generation/btsgen/class_forge.py:3491 (abort)

    front-end failed: {e}

### console.fail.too_few_cards
Where: generation/btsgen/class_forge.py:3735 (abort)

    too few cards survived; aborting class

### console.loc.concept
Where: generation/btsgen/loc.py translate_concept (before the forge; a Chinese concept, or any concept on a non-English forge with no Latin words)
Notes: added 2026-10-27 by the i18n build, owner to review. {text} = the English concept the design runs on.

    concept translated to English: {text}

### console.loc.translating
Where: web/forge.py _translate_result (after the bundle is assembled, non-English forges only)
Notes: added 2026-10-27 by the i18n build, owner to review

    translating the class's names and descriptions…

### console.loc.done
Where: generation/btsgen/loc.py translate_bundle (the translation's result line)
Notes: added 2026-10-27 by the i18n build, owner to review. {locale} = the game locale (zhs). The code may append ", N fell back to English (reasons)".

    translation ({locale}): {len(kept)}/{len(strings)} strings

## Out of scope

- static/privacy.html and static/terms.html: English-only legal pages, not extracted.
- The admin panel: the Forge stats, Site traffic, Users, Archive nominations and Sign-up events cards on the Account view (static/index.html:310-450 and their app.js builders, loadStats through endAdminEvent), every /api/admin/* route, the reauth message at web/app.py:2401 and the GoAccess 404 at web/app.py:2492.
- Dev-only strings that never show on the live site: "Dev sign-in (local)" (static/index.html:37, static/signin.html:54), "Offline demo (no key)" (static/index.html:201), "Forge the class (offline demo)" (static/app.js:215), "Open the sign-in link (local dev)" (static/signin.js:92), "Dev" (static/app.js:1407), "the offline demo forge is dev-only." (web/app.py:1266), "one-shot forge: no triad prompt on this path — forging a classic 2-archetype class" (web/forge.py:727, CLI path).
- The card-text renderer in static/render.js:511-818 (STATUS_NAMES, BM_PHRASES, TRIGGER_PREFIX, REACTIVE_HEAD, SCALE_SUFFIX, SCALE_NOUN, HITS_NOUN, condCore, effPhrase and potionEffectText's "Summon {name}"): about 200 phrase fragments that print a card's effects the way the card reads in game. They are kept in lockstep with generation/btsgen/cardgen.py and the mod's ForgedCards, so they should be localized together with the in-game card text, not here.
- The mod's generated card text and picker prompts (mod/BlankTheSpireCode/Engine/DataCard.cs) and the base character's localization (mod/BlankTheSpire/localization/eng/characters.json and the other files there besides settings_ui.json).
- Server lines a player never reads: log lines, the Stripe webhook's "billing disabled" / "bad signature" (answered to Stripe, not a browser), the import-code payloads in download.html, and Stripe's own hosted-page text (submit_type "donate" makes its button read "Donate").
- Purely decorative alt text and emoji (banner icons, 🎁 / ⚒ / ⚠ / 📱), developer comments, and everything in web/static/forged/ and web/static/img/.

## Inventory

| Section | Entries |
|---|---|
| Shared (header, footer, toasts) | 19 |
| Landing page (landing.html, landing.js, signup-event.js) | 34 |
| App shell (index.html) | 94 |
| App JS strings (app.js, render.js) | 263 |
| Help page (help.html) | 32 |
| Download page (download.html) | 48 |
| Deck page (deck.html, deck.js) | 20 |
| Archive (archive.html, archive.js, featured.js) | 7 |
| Sign-in pages (signin.html, signin-continue.html, signin-expired.html, signin.js, webview.js) | 36 |
| Email | 9 |
| Server errors | 68 |
| Stripe checkout | 2 |
| Steam Workshop | 3 |
| In-game mod UI | 45 |
| Forge console stage headers | 30 |
| **Total** | **710** |

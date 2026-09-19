# Pricing v3 copy: edit the NEW blocks, leave the rest

How to use this file: each numbered item is one user-facing string. **CURRENT** is what is live today
(for reference, don't edit). **NEW** is the proposed replacement. Edit the text inside the NEW block
freely; keep the fenced block markers so the strings can be lifted out verbatim. `N` is a number the code
fills in. `<b>...</b>` is bold in the page. Where an item says "delete", leave it unless you want the
line kept.

Fixed tiers used throughout (the donor is charged the gross; the fee line covers Stripe's 2.9% + 30c):

| You give | Tokens | Charged |
|---|---|---|
| $3 | 2 | $3.40 |
| $5 | 4 | $5.46 |
| $10 | 10 | $10.61 |
| $20 | 20 | $20.91 |
| $50 | 50 | $51.81 |

The $20 and $50 tiers are my suggestion for "anything over $10 is one token per dollar" now that there is
no custom-amount box. Strike them here if you don't want them.

---

## Landing page (`web/static/landing.html`, "What does it cost?")

### 1. Pricing bullet 1: bring your own key

CURRENT
```
Bring your own API key — free, unlimited forging. Anthropic, OpenAI, Google, OpenRouter and more; your provider bills you and your key stays in your browser.
```
NEW
```
<b>Bring your own API key</b> — free, unlimited forging. Anthropic, OpenAI, Google, OpenRouter and more; your provider bills you. Your key stays only in your browser.
```

### 2. Pricing bullet 2 (replaces "One free token a day")

CURRENT
```
One free token a day on our models, for every account. One token forges one class. Might have to limit if my bank account breaks 😅
```
NEW
```
<b>Or let us run it.</b> Support the forge and get tokens as a thank-you: $3 → 2 tokens, $5 → 4, $10 → 10 (card fee added at checkout). One token forges one class on our models.
```

### 3. Pricing bullet 3

CURRENT
```
Want to help? BLANK the spire is totally free — the mod is open source and there is nothing to buy. Donations cover the cost of the forges, and every whole dollar adds a thank-you token to your balance.
```
NEW
```
<b>The mod is free</b> and open source — there is nothing to buy. Donations cover the cost of tokens when you run them without an API key.
```

---

## App header (`web/static/index.html`)

### 4. Token chip tooltip (hover text on the "N tokens" chip)

CURRENT
```
Tokens are spent by the 'Use a token' forge option — every account gets a free token each day.
```
NEW
```
Tokens are spent by the 'Use a token' forge option. Account tab to get more.
```

---

## Forge tab: onboarding chooser (NEW element, shown when you have 0 tokens and no saved key)

### 5. Chooser headline

NEW
```
How will you fill in the blank?
```

### 6. Card A title

NEW
```
I have an API key
```

### 7. Card A body

NEW
```
Forging is free (but compute is not). Paste a key from Anthropic, OpenAI, OpenRouter and more — it stays in your browser.
```

### 8. Card A button

NEW
```
Use my key
```

### 9. Card B title

NEW
```
Use a token
```

### 10. Card B body

NEW
```
We run it on our models. Each token is one forge: $3 → 2 tokens, $5 → 4 tokens, $10 → 10 tokens.
```

### 11. Card B button

NEW
```
Support the forge
```

### 12. Collapsed strip after a choice is made (two variants; "change" is a link)

NEW
```
Forging with your key · change
```
```
Forging with tokens · change
```

### 13. Warning banner on the forge tab (dismissible; hidden once a key is saved; two variants by balance)

NEW (has tokens)
```
Enter an API key or use a token to forge!
```
NEW (no tokens)
```
Enter an API key or get tokens to forge.
```

---

## Forge tab: Generation settings

### 14. Mode radio labels

CURRENT
```
Use a token
```
```
Bring your own key
```
NEW (keep or tweak)
```
Use a token
```
```
Bring your own key
```

### 15. Token status line, when you have tokens

CURRENT
```
Forges on our models. Uses 1 of your N tokens — today's free token is spent; another arrives tomorrow (UTC).
```
NEW
```
Forges on our models. Uses 1 of your N tokens.
```

### 16. Token status line, when you have 0 tokens ("bring your own key" is bold, "account page" is a link)

CURRENT
```
Today's free token is spent — another arrives tomorrow (UTC). Until then, <b>bring your own key</b> below (free, unlimited), or support the forge.
```
NEW
```
You have no tokens. <b>Bring your own key</b> below (free, unlimited), or account page to get some.
```

### 17. Forge button label, with tokens (the part in parentheses)

CURRENT
```
Forge the class (uses 1 of your N tokens)
```
NEW
```
Forge the class (uses 1 of your N tokens)
```

### 18. Forge button label, 0 tokens

CURRENT
```
Forge the class (no tokens left)
```
NEW
```
Forge the class (no tokens — get some or bring a key)
```

### 19. Toast when clicking Forge with 0 tokens

CURRENT
```
No tokens to spend — wait for tomorrow's free token, or bring your own key.
```
NEW
```
No tokens to spend — get some, or bring your own key.
```

### 20. Confirm dialog before a token forge

CURRENT
```
This will use today's free token (your N other tokens stay untouched). Forge this class?
```
NEW
```
This will use 1 token. You have N. Forge this class?
```

### 21. Server error when out of tokens (HTTP 402)

CURRENT
```
you're out of tokens — your free daily token arrives tomorrow (UTC), or bring your own API key to keep forging.
```
NEW
```
you're out of tokens — get more on the Account tab, or bring your own API key to keep forging.
```

### 22. Server error when the per-network free cap is hit: DELETE (the cap goes away)

CURRENT
```
get more or bring your own API key to keep forging.
```

---

## Account tab (`web/static/index.html`)

### 23. Line under the balance ("Today's free token: ..."): DELETE

CURRENT
```
Today's free token: available.
```

### 24. Account blurb

CURRENT
```
One token forges one class with the "Use a token" option. Every account gets a <b>free token each day</b>, on top of any it holds — forging never costs money. Bring your own API key and it never costs a token either.
```
NEW
```
One token forges one class on our models. Bring your own API key and forging is free and unlimited — no token needed.
```

### 25. "Support the forge" blurb

CURRENT
```
BLANK the spire is totally free, but each Forge costs money and I fear for my bank account! Your donations cover the cost of tokens directly — and as a thank-you, every whole dollar adds a token to your balance. Give $10 or more and we add a bonus on top: <b>$10 → 11 tokens, $20 → 24, $50 → 65</b>.
```
NEW
```
BLANK the spire is free and open source, but every hosted forge costs me real money. Your donations cover the cost of our compute.
```

### 26. Tier button label (one per tier; N and $ filled in)

NEW
```
$3 → 2 tokens
```

### 27. Small line under each tier button

NEW
```
$3.40 charged, incl. $0.40 card fee
```

### 28. Note when donations are switched off

CURRENT
```
Donations aren't available right now — your free daily token and BYOK forging both keep working.
```
NEW
```
Donations aren't available right now — bring your own API key to keep forging.
```

### 29. Stripe line (unchanged, here for context)

CURRENT
```
Payments are handled by Stripe — we never see your card details.
```
NEW
```
Payments are handled by Stripe — we never see your card details.
```

### 30. Donation history row

CURRENT
```
Donated $5.00 · +5 tokens · Sep 18, 2026
```
NEW
```
Donated $5.46 ($5.00 + $0.46 card fee) · +4 tokens · Sep 18, 2026
```

### 31. Toast after coming back from Stripe

CURRENT
```
Thank you for supporting the forge — N tokens added!
```
NEW
```
Thank you! N tokens added — you're ready to forge.
```

### 32. Toast if checkout was canceled (unchanged)

CURRENT
```
Donation canceled — you weren't charged.
```
NEW
```
Donation canceled — you weren't charged.
```

### 33. Stripe checkout line items (what the donor sees on Stripe's page and receipt)

NEW
```
Donation — BLANK the spire
```
```
Card processing fee
```

---

## Terms (`web/static/terms.html`, "Tokens & donations")

### 34. Tokens bullet

CURRENT
```
<b>One token = one class generation</b> with the "Use a token" option, which runs on our models. Every account receives <b>one free token per day</b> (UTC), on top of any tokens it already holds; the free token is always spent first. New accounts also receive free starter tokens.
```
NEW
```
<b>One token = one class generation</b> with the "Use a token" option, which runs on our models. Tokens are received as a thank-you for donations (below).

### 35. Donations bullet

CURRENT
```
<b>The site is donation-based.</b> There is nothing to buy: the mod is free and open source, and every generated class is yours to use and share regardless of how it was generated. Donations are optional, one-time payments processed by <b>Stripe</b> (we never see or store your card details). As a thank-you, each whole dollar donated adds one bonus token to your balance, and larger donations add a bonus on top of that (10% from $10, 20% from $20, 30% from $50).
```
NEW
```
<b>The site is donation-based.</b> There is nothing to buy: the mod is free and open source, and every generated class is yours to use and share regardless of how it was generated. Donations are optional, one-time payments in fixed amounts processed by <b>Stripe</b> (we never see or store your card details); Stripe's card processing fee is shown separately and added to the amount charged. As a thank-you, each donation adds tokens to your balance: $3 adds 2, $5 adds 4, $10 adds 10, $20 adds 20, $50 adds 50. I will keep trying to make this more effecient!
```

### 36. Suspension bullet (wording only)

CURRENT
```
We may suspend accounts that violate these terms; unspent paid tokens on a suspended account are refunded on request unless the suspension is for payment abuse.
```
NEW
```
We may suspend accounts that violate these terms; unspent thank-you tokens on a suspended account are refunded on request unless the suspension is for payment abuse.
```

### 37. Refund bullet (add the fee)

CURRENT
```
Donations are refundable within 14 days on request — contact support from the email on your account. A refunded donation's still-unspent thank-you tokens are removed from your balance.
```
NEW
```
Donations are refundable within 14 days on request — contact support from the email on your account. Refunds are for the full amount charged, including the card processing fee. A refunded donation's still-unspent thank-you tokens are removed from your balance.
```

---

## Privacy (`web/static/privacy.html`)

### 38. "What we store" account bullet: drop the free-token clause

CURRENT
```
... plus your token balance, the day you last used your free daily token, and when your account was created.
```
NEW
```
... plus your token balance and when your account was created.
```

### 39. "How your data is used" bullet

CURRENT
```
To run the service: sign you in, save your classes, track your token balance (including the free daily token), and show your donation history.
```
NEW
```
To run the service: sign you in, save your classes, track your token balance, and show your donation history.
```

---

## Docs and Workshop

### 40. `INSTALL.md` section 3, step 2 sub-bullet

CURRENT
```
**Use a token** forges on the site's hosted models: every account gets one free token a day, and you can buy more. Or pick **Bring your own key** (Anthropic, OpenAI, and others) to forge for free with your own API key — unlimited, billed by your provider.
```
NEW
```
**Use a token** forges on the site's hosted models (tokens come as a thank-you for supporting the site). Or pick **Bring your own key** (Anthropic, OpenAI, and others) to forge for free with your own API key — unlimited, billed by your provider.
```

### 41. Root `README.md`, the `web/` row (last sentence)

CURRENT
```
Forging is free with your own API key, one free hosted forge a day otherwise, and paid token packs beyond that (tokens buy generation compute — the mod itself is free).
```
NEW
```
Forging is free and unlimited with your own API key; the hosted models run on tokens received as a thank-you for donations (the mod itself is free).
```

### 42. `web/README.md` "Use a token" bullet

CURRENT
```
**Use a token** forges on the server's hosted Ollama mix behind a token economy: every account gets one free token per UTC day (tracked separately from the balance, so donors never lose it) plus a few starter tokens. Nothing is sold: optional Stripe donations grant a thank-you token per whole dollar (`billing.py`). Free-token forges are capped per IP per day; one forge per account at a time; token forges dequeue before BYOK.
```
NEW
```
**Use a token** forges on the server's hosted models behind a token economy. Accounts start with no tokens; fixed-amount Stripe donations grant thank-you tokens ($3 → 2, $5 → 4, $10 → 10, $20 → 20, $50 → 50, card fee passed through; `billing.py`). One forge per account at a time; token forges dequeue before BYOK.
```

### 43. `workshop/DESCRIPTION.bbcode`, "How to play" paragraph (must stay price-free: no amounts here)

CURRENT
```
Forging happens on the website, not in this mod. Bring your own LLM API key and forge as much as you like, or use the site's hosted models with the free daily forge every account gets. This Workshop item is free and open source, and contains no purchases.
```
NEW
```
Forging happens on the website, not in this mod. Bring your own LLM API key and forge as much as you like, or use the site's hosted models. This Workshop item is free and open source, and contains no purchases.
```

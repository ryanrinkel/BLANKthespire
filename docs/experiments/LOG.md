# Page experiments log

The written record of every page experiment (A/B test) on the site, kept forever. The live registry is
`web/experiments.py`; how experiments are served and read is `docs/plans/AB_TESTING_PLAN.md`. The admin
Experiments card drops an experiment 30 days after it ends; this file is the archive.

Rule: the row is written here, with the hypothesis and the primary metric, BEFORE the deploy that starts
the experiment. The registry entry carries the same hypothesis text, so the card and this log never
disagree. When an experiment ends, fill in `result` (the P read and exposures per arm on the planned end
or the day the rule was met) and `decision` (winner shipped, or control kept) in the same commit that sets
`ended` + `winner`.

Decision rule (the default, `rule="must_win"`): call a winner when P(beats control) >= 0.95 AND every arm has
at least 200 exposures AND the experiment has run at least 14 days; otherwise, at the planned end, keep the
control. An experiment may instead declare `rule="ship_unless_worse"` (two arms): once it has 200 exposures per
arm and 14 days, P(b beats a) <= 0.10 stops it with the control kept; otherwise B ships at the planned end.

| name | page | arms | primary metric | started | planned end | result | decision |
|---|---|---|---|---|---|---|---|
| hero | `/` | a: "Create Your Own Class" (control) / b: "Forge a class — free with your own API key" | `/login` opened | 2026-11-04 | 2026-12-16 | read 2026-11-10 (6 full days): a 19 / 278 exposures (6.8%), b 15 / 304 (4.9%); P(b beats a) = 0.165; no winner by rule | ended 2026-11-11, early, by the owner's decision to free `/` for the sitewide skin test; control kept (arm b and `landing.hero.cta_b` removed) |
| skin | `/` (sitewide: the arm applies on every page) | a: today's look (control) / b: departure-board skin on every page: new hero order, "Blank the Spire" under the board, no sign-in note, menu button, tiles beside the steps | `/login` opened | 2026-11-12 | 2026-12-24 | (running) | — rule `ship_unless_worse`: B ships unless P(b beats a) <= 0.10 with ≥200 exposures/arm and ≥14 days |

**hero** hypothesis: Saying 'free with your own API key' on the button lifts /login opens, because the cost question stops people before the pricing section far below the fold.

**skin** hypothesis: The departure-board look (flat black and amber, a sentence-style hero that opens with 'How will you fill in the…', a top-right menu) gets visitors to open /login at least as often as today's look.

# Page experiments log

The written record of every page experiment (A/B test) on the site, kept forever. The live registry is
`web/experiments.py`; how experiments are served and read is `docs/plans/AB_TESTING_PLAN.md`. The admin
Experiments card drops an experiment 30 days after it ends; this file is the archive.

Rule: the row is written here, with the hypothesis and the primary metric, BEFORE the deploy that starts
the experiment. The registry entry carries the same hypothesis text, so the card and this log never
disagree. When an experiment ends, fill in `result` (the P read and exposures per arm on the planned end
or the day the rule was met) and `decision` (winner shipped, or control kept) in the same commit that sets
`ended` + `winner`.

Decision rule: call a winner when P(beats control) >= 0.95 AND every arm has at least 200 exposures AND the
experiment has run at least 14 days; otherwise, at the planned end, keep the control.

| name | page | arms | primary metric | started | planned end | result | decision |
|---|---|---|---|---|---|---|---|
| hero | `/` | a: "Create Your Own Class" (control) / b: "Forge a class — free with your own API key" | `/login` opened | 2026-11-03 | 2026-12-15 | (running) | — |

**hero** hypothesis: Saying 'free with your own API key' on the button lifts /login opens, because the cost question stops people before the pricing section far below the fold.

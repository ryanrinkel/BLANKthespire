# A transient DNS blip to ollama.com aborts an entire in-flight forge (no backoff, no resume)

Found 2026-07-05 during an 8h back-to-back `btsgen-forge-class --ollama` test suite (the website's
"Use a token" path, ollama-cloud mixture: `ministral-3:8b` brainstorm + `glm-5.2` structure/cards).
**2 of the first 5 forges (40%) died to this**, each after minutes of successful work. It is a
**robustness gap in the generator's retry**, triggered by an **environmental** DNS flake on this box —
not a content, schema, or logic bug.

## Symptom
A forge that has already made many successful cloud calls dies mid-run with:

```
RuntimeError: could not reach endpoint https://ollama.com/v1: [Errno -3] Temporary failure in name resolution
```

`[Errno -3]` is `EAI_AGAIN` — the local resolver momentarily failed to resolve `ollama.com`. The whole
forge aborts and **all prior work (front-end stages + already-coded cards) is discarded**; the CLI
returns exit 1 with no `.btsc` output.

### Two instances, two different stages (so it's stage-agnostic — any call can be the victim)
| run | when | stage that hit it | wasted |
|---|---|---|---|
| `cleopatra` | 196s in | card generation (`generate_card → first_attempt → _post_translated`) | full front-end + N coded cards |
| `ramsay` | 15s in | front-end map stage (`[2/6] map … running the staged creative front-end`) | full brainstorm/cluster stage |

Trace tail (cleopatra):
```
class_forge.py:1203 forge_class → pipeline.py:52 generate_card → generator.py:325 first_attempt
  → generator.py:303 _complete → generator.py:271 _post_translated
RuntimeError: could not reach endpoint https://ollama.com/v1: [Errno -3] Temporary failure in name resolution
```

## Root cause — the retry is single, immediate, and no-backoff
`OpenAICompatGenerator._post_with_retry` (generator.py) *does* catch `urllib.error.URLError` (which a DNS
failure raises) and retries — but **exactly once, with no delay**:

```python
try:
    return self._post(payload)
except urllib.error.HTTPError:
    raise
except (TimeoutError, ConnectionError, urllib.error.URLError):
    return self._post(payload)   # one immediate re-attempt, then give up
```

A systemd-resolved `EAI_AGAIN` blip on this box typically lasts a beat longer than the gap between two
back-to-back `getaddrinfo` calls, so **both** attempts land inside the same blip and the second re-raises.
Because the whole forge is a single linear sequence of ~30 calls with no checkpoint, one unlucky call
throws away the entire run.

## Scope — confirmed ENVIRONMENTAL trigger, not the mod/content/model
- **DNS is intermittently flaky on this box, not down.** Right after the failures, 5/5 `getent hosts
  ollama.com` succeeded and a live `GET /v1/models` returned HTTP 200 in 0.15s. Resolver is
  systemd-resolved (`/etc/resolv.conf` → `nameserver 127.0.0.53`). `EAI_AGAIN` from 127.0.0.53 is the
  classic intermittent-systemd-resolved / flaky-upstream signature.
- **Not model/content:** both concepts are ordinary; the error is a transport/DNS layer failure with
  zero bytes exchanged, unrelated to what was being generated. Neighboring runs (caesar, genghis,
  bobross) on the *same* concepts-style input passed cleanly with 27 cards each.
- **Not the key / not rate limiting:** an HTTP 429/403 would surface as `HTTPError` (which is *not*
  retried and prints a status), not as name-resolution failure.
- **Not a code regression:** the retry logic is as designed; the design just isn't resilient to a
  multi-hundred-ms DNS outage.

## Impact
~40% early failure rate against a flaky resolver, each failure wasting minutes of glm-5.2 cloud calls
(real spend) and producing no class. On the live website this same path would surface as "class did not
generate" to a paying/token-spending user for a blip entirely outside their control.

## Fixes (in rough priority)
1. **Backoff + a few attempts on transport errors.** Make `_post_with_retry` try ~3× with small
   escalating sleeps (e.g. 0.5s, 1.5s, 3s). A sub-second DNS blip then clears on attempt 2/3. Cheapest,
   highest-leverage, product-code change; helps the live site too.
2. **Forge-level resilience for the front-end/card loop.** A single failed card call shouldn't nuke a
   20-card forge — skip-and-continue (the pipeline already has a `skipped` concept for card briefs) or a
   per-call retry wrapper so one blip costs one card, not the class.
3. **Env mitigation for this box (test runs):** pin `ollama.com` in `/etc/hosts`, or point
   `/etc/resolv.conf` at a caching resolver, to take the flaky local path out of the loop. Reversible;
   needs root.

## Workaround used in the current test run
The driver (`run_forge_suite.sh`) continues past a failed forge and records it; failed concepts are
collected and **re-run in a retry sweep after the main list** (a transient blip almost always clears on
the next attempt). No product code was changed during the run.

## Confirmed recoverable (2026-07-06 retry sweep)
Both DNS-failed concepts re-forged cleanly on a single retry: `cleopatra` → "Venomous Sovereign" (27
cards), `ramsay` → "The Burning Kitchen" (26 cards). Same concepts, same `--ollama` path, zero code
changes — proving the failures were purely the transient-DNS abort, not the content or pipeline. So of
36 distinct concepts attempted overnight, **0 had a genuine (non-transient) generation failure**; the
only fix needed is retry resilience.

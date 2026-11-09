# Walk-away forges: slow and small BYOK models become a wait, not a failure

Status: PLAN (written 2026-11-09, replaces SLOW_FORGE_LATE_FINISH_PLAN.md). Nothing built yet.

## 0. Why

User 2581607309@qq.com ran three BYOK forges on 2026-11-08 (Volcengine Doubao x2, DeepSeek v4 pro x1). All
three were "abandoned" by the 1200 s watchdog, all three finished 46-60 min in and were saved as classes
#100/#101/#102 (35 cards each, import codes, lang zh). The browser had shown a failure, the user never opened
My Classes, retried twice, and left.

The backend already IS a walk-away system: the worker thread runs to completion whether or not a browser is
attached and the class lands in My Classes. The product does not admit it. Four gaps:

1. The watchdog turns "slow" into "failed" and the stream says so.
2. The page is built as wait-and-watch: close the tab or reload and nothing reattaches.
3. Nobody is warned beforehand that the model they picked will take an hour.
4. A deploy mid-forge kills the job (boot reconciliation marks it failed).

Decisions taken in the design discussion (Ryan, 2026-11-09): no completion email. Warn in the log while it
runs and in the picker before it starts. Card-stage parallelism is out of scope (separate plan if wanted).

### 0.1 What the ledger says (calibration for sections 4 and 5)

Per-forge totals, LLM rows only (no art, no Jev), last 60 days, from `forge_usage` joined to `forge_jobs`
(late finishes measured to the class row's `created_at`):

| mode | n | median wall | median output tokens | median calls | effective tok/s (median, range) |
|---|---|---|---|---|---|
| token (hosted) | 55 | 296 s | 23K | 47 | 74 (12-121) |
| byok | 6 | 1736 s | 73K | 43 | 45 (39-56) |

The six BYOK forges individually:

| provider : card model | wall | output tokens | calls | tok/s |
|---|---|---|---|---|
| api.openai.com : gpt-5.6-sol | 515 s | 26K | 43 | 50 |
| api.openai.com : gpt-6.1-sol | 570 s | 25K | 40 | 44 |
| api.openai.com : gpt-6.1-sol | 693 s | 32K | 43 | 46 |
| ark.cn-beijing.volces.com : doubao-seed-evolving | 2780 s | 114K | 43 | 41 |
| ark.cn-beijing.volces.com : doubao-seed-evolving | 3159 s | 123K | 42 | 39 |
| api.deepseek.com : deepseek-v4-pro | 3570 s | 200K | 54 | 56 |

Two conclusions that shape the warning design:

- **Speed is not the variable.** Every BYOK provider streamed at 39-56 tok/s. Call counts were the same.
- **Volume is.** The reasoning models emitted 4-8x the output tokens (thinking tokens are billed and
  streamed as completion tokens by Doubao and DeepSeek). A speed-only probe would have rated Doubao the
  same as OpenAI. The probe must measure a model's **verbosity multiplier** as well as its speed.

Duration model used below: `seconds ≈ calls × first_token_latency + V × M / S`, with V = visible output a
forge needs (~25K tokens, the OpenAI/hosted figure), M = the model's completion-to-visible multiplier
(1.0 for a plain model, 4-8 for a reasoning model), S = streamed tok/s. Doubao: 43×2 + 25K×4.6/45 ≈ 44 min.
OpenAI: 43×2 + 25K×1.0/45 ≈ 11 min. Both match the table.

---

## 1. Server: slow is not a failure (BYOK)

Files: `web/app.py`, `docs/copy/COPY.md`, `docs/copy/COPY.zh.md`, `web/tests/test_forge_jobs.py`,
`web/tests/conftest.py`, `web/DEPLOY-DIGITALOCEAN.md`.

1.1 **Separate ceiling for BYOK.** `FORGE_MAX_SECONDS_BYOK = float(env BTSWEB_FORGE_MAX_SECONDS_BYOK, 14400)`
next to `FORGE_MAX_SECONDS` (app.py ~182). Four hours is a stuck-job sanity ceiling, not a product limit. In
`forge_class_route`, after `ollama_mix = mode == "token"` (~1333): `max_seconds = FORGE_MAX_SECONDS if
ollama_mix else FORGE_MAX_SECONDS_BYOK`; `on_wall_clock` and the `threading.Timer` in `worker()` (~1501)
use it, including the `too_long_job` text. Token forges are unchanged (a reserved token is what the
20-minute cap protects).

1.2 **BYOK-worded ceiling copy.** `server.forge.too_long` says "your token refunded", wrong on BYOK today.
Add `server.forge.too_long_byok`, chosen with `if reserved else`:
- en: `this forge has run for hours without finishing — the page has stopped waiting. If your provider does
  finish it, the class will appear in My Classes.`
- zh: `这次锻造已运行数小时仍未完成，页面已停止等待。如果你的服务商最终完成了它，角色会出现在“我的角色”里。`

1.3 **Per-user lock must outlive the forge.** `USER_ACTIVE_STALE_S = FORGE_QUEUE_TIMEOUT_S + 900` (~257) is
45 min: with the watchdog no longer freeing the slot at 20 min, a 60-minute BYOK forge would let the same
account start a second one at minute 45. Change to
`max(FORGE_QUEUE_TIMEOUT_S, FORGE_MAX_SECONDS, FORGE_MAX_SECONDS_BYOK) + 900`.

1.4 **BYOK concurrency pool.** The 3-slot limit protects the hosted route; a BYOK forge is a thread waiting
on someone else's API. Add `FORGE_MAX_CONCURRENT_BYOK = int(env BTSWEB_FORGE_MAX_CONCURRENT_BYOK, 4)` and
make admission two independent pools in `_forge_enqueue` / `_forge_release` / `_forge_abandon` /
`_forge_position` (~192-250): `_forge_running_token` vs `_forge_running_byok`, each line only waits on its
own pool. `_waiting_total()` (the 503 up-front check) stays the sum. The token-first dequeue rule becomes
moot and goes. Queue-position progress lines keep working per pool.

1.5 **Tests.** Add both env names to the cleared list in `conftest.py:37`. Keep
`test_wall_clock_cap_refunds_and_frees_the_slot` (token path). New:
- `test_byok_ceiling_is_separate`: `FORGE_MAX_SECONDS=0.3`, `FORGE_MAX_SECONDS_BYOK=5`, gate held 1 s → BYOK
  forge ends in `result`, job `done`; a token forge under the same gate still ends in `error`.
- `test_byok_ceiling_copy`: `FORGE_MAX_SECONDS_BYOK=0.3` → `error` with `code == "forge.too_long_byok"`, no
  `token_balance` key, `refunded == 0`, late class still saved.
- `test_byok_pool_does_not_block_token`: `FORGE_MAX_CONCURRENT_BYOK=1`, two BYOK forges gated, a token forge
  runs immediately; the second BYOK forge sees a queue-position progress line.
- `test_user_lock_outlives_cap`: with the BYOK ceiling at 5 s and a forge gated, a second forge from the same
  account 429s (`server.forge.already_running`).

1.6 **Docs.** DEPLOY-DIGITALOCEAN.md ~264-279: both knobs, the two pools, the ceiling semantics.

---

## 2. Browser: reattach on load, in-progress row, late finish

Files: `web/static/app.js`, `web/static/index.html`, `web/app.py` (status + classes endpoints), copy, smoke.

2.1 **Status endpoint carries what a viewer needs** (`forge_job_status`, app.py ~1562). Add:
- `late`: `status == "failed" and class_id is not None`.
- `eta_s`: from `_forge_eta.get(forge_id)` (set by section 3), else null.
- `concept`: first 120 chars, for the banner and the library row.
- `started_at` ISO (age_s already there).
- The `latest` lookup's non-running window (`FORGE_LATEST_WINDOW_S`) must also admit a cap-settled job
  (`error` code too_long*) without a class yet, else a reload after the ceiling cannot follow it. Simplest:
  `job.status == "running" or (job.error matches too_long and job.class_id is None) or age <= window`.

2.2 **`/api/classes` gains `running`** (`list_classes`, ~1822): the account's `ForgeJob` rows with
`status == "running"` as `[{forge_id, concept, started_at, age_s, message, eta_s}]`. `paintLibrary()`
(app.js ~1320) renders one "in progress" card per entry at the top: concept, "started 34 min ago", the live
progress line, the ETA when known, and a "Watch" button that opens the forge view and follows it (2.4).

2.3 **One follower.** Refactor `recoverForge` (app.js ~936) into `followJob(forgeId, {token, reason})`
that owns the banner and the poll loop, and is the only thing that polls `/api/forge-jobs/*`. Terminal
states:
- `class_id` present (done OR late) → load `/api/classes/<id>`, `renderResult`, log `app.console.done_late`
  when `late`, toast `app.lost.toast_ready`, refresh the library if visible.
- `failed` with a too_long code and no class → keep following (the forge is still running), banner text
  `app.late.banner`.
- any other `failed` → today's behaviour.
- give-up: `FOLLOW_GIVE_UP_MS` = 5 h (above the BYOK ceiling). Poll interval 5 s for the first minute, then
  20 s. Both overridable via `window.__FOLLOW_*` for the smoke.
A module-level `followGen` counter cancels an older follower when a new forge starts or a new follow begins.
`pollPause` (wakes on tab visible / online) stays.

2.4 **Reattach on load.** In the `BTS_I18N.ready.then(...)` boot (app.js ~2654), after the signed-in state
is known: `GET /api/forge-jobs/latest`; if 200 and (`running` or late-eligible) → show the banner with
`app.resume.banner` ("Still forging: {concept} — started {age} ago{eta}. You can close this tab; it will be
in My Classes.") and `followJob(id)`. The forge button stays enabled only if the server would allow another
forge (it will not while running: `already_running`), so disable it with the tooltip `app.resume.one_at_a_time`
while a follow of a running job is active.

2.5 **Stream end on the cap** (`onForgeEvent` ~1048): when `data.code` is `forge.too_long` or
`forge.too_long_byok`, after the stream closes call `followJob(run.forgeId)` (not awaited; `FORGING` goes
false as the server freed the slot). This is the only remnant of the earlier late-finish design.

2.6 **Copy** (COPY.md + COPY.zh.md, then `python web/tools/build_i18n.py`):

| key | en | zh |
|---|---|---|
| `app.resume.banner` | Still forging: {concept} — started {age} ago{eta}. You can close this tab; the class will be in My Classes when it's done. | 仍在锻造：{concept} — 开始于{age}前{eta}。你可以关闭此页，完成后角色会出现在“我的角色”里。 |
| `app.resume.eta` | , about {min} min to go | ，大约还需{min}分钟 |
| `app.resume.one_at_a_time` | One forge at a time — this one is still running. | 一次只能锻造一个 — 当前的还在进行。 |
| `app.late.banner` | Your provider is slow, so the page stopped waiting — but the forge is still running. If it finishes, the class will appear here and in My Classes. | 你的服务商比较慢，页面已停止等待，但锻造仍在进行。如果完成了，角色会出现在这里和“我的角色”里。 |
| `app.library.in_progress` | In progress | 进行中 |
| `app.library.watch` | Watch | 查看进度 |
| `app.console.done_late` | ✓ finished late — here it is | ✓ 迟到但完成了 — 就在这里 |

2.7 **Smoke** (`web/tools/ui_smoke.mjs`, modelled on `lost`, fetch stubbed per case, a `fake` forge seeds a
real class):
- `resume`: load `/app` with `/api/forge-jobs/latest` stubbed `running` (message, eta_s) → banner text,
  forge button disabled; flip the stub to `done` + class id → result rendered, banner hidden.
- `late`: forge stream ends in `error {code: "forge.too_long_byok"}` → `FORGING === false`, banner
  `app.late.banner`; stub status `failed, late:false` twice then `late:true, class_id` → result rendered,
  `done_late` in the log.
- `library-running`: `/api/classes` stubbed with one `running` entry → an in-progress card on top.
- Rerun `lost`, `forge`, `forge-zh`.

2.8 **Cache-bust.** Bump `?v=` for `app.js` and `i18n.js` in `index.html` (~523-525) and `VERSION` in
`i18n.js` line 47.

---

## 3. In the log: the forge announces its own pace

Files: `generation/btsgen/class_forge.py` (card loop ~3618-3650), `web/app.py` (`on_event`), app.js
console rules, copy.

3.1 **Measure.** In the `for i, plan in enumerate(bp["cards"])` loop, time each `generate_card(...)` call
(synthesized basics/blade excluded). Keep a running mean of LLM-designed card seconds and the count of
LLM-designed cards remaining.

3.2 **Emit.** After the 3rd timed card, and again every 10th, when the projected remainder exceeds
`PACE_WARN_MIN` (10 min; the hosted median forge is 5), emit one progress line in a fixed machine shape:

    pace: 75s/card, ~40 min to go (32 cards left)

`note()` already fans progress out to the CLI log and `on_event`. The CLI benefits too.

3.3 **Web side.** `on_event` in app.py (~1486) regex-parses `^pace: .*~(\d+) min to go` and stores
`_forge_eta[forge_id] = time.time() + min*60` (cleared with `_forge_progress`). The status endpoint turns it
into `eta_s` (2.1). The progress line itself still goes to the stream unchanged.

3.4 **Browser.** `BTS_I18N.console()` gets a rule for `pace:` that renders the translated line and appends
the walk-away hint:

| key | en | zh |
|---|---|---|
| `console.pace` | ⏱ {secs} s per card on this provider — about {min} min to go. Safe to close this tab; the class lands in My Classes. | ⏱ 这个服务商每张卡约 {secs} 秒 — 大约还需 {min} 分钟。可以关闭此页，角色完成后会出现在“我的角色”里。 |

When a pace line arrives, the banner from 2.4 (if visible) updates its ETA too.

3.5 **Test.** `generation/tests`: a fake card generator that sleeps 0.05 s per card with
`PACE_WARN_MIN` monkeypatched to 0 → the log contains a `pace:` line after card 3 and the projected minutes
are within 2x of the real remainder. Web: `test_forge_jobs.py` feeds a `pace:` progress line through the
stub's `on_event` and asserts `eta_s` on the status endpoint.

---

## 4. Before the forge: a projection in the model picker

Files: `web/app.py` (two endpoints), `web/forge.py` (probe), `web/static/app.js` (picker ~628-740),
`web/static/index.html` (`#forge-byok` ~107-160), copy, tests.

Two sources, used together; history wins when it exists, the probe fills the gaps, actual durations
calibrate the probe over time.

4.1 **History: `GET /api/model-history?provider=<host>&model=<id>`.** From `forge_usage` rows with
`role='cards'` joined to `forge_jobs` (+ the class `created_at` for late finishes, as in 0.1): count,
median wall seconds, median output tokens, p90 wall. Any user's forges count (no concepts or keys are
exposed, only timings). Cached 10 min in-process. Returns `{n, median_s, p90_s}` or `{n: 0}`.

4.2 **Probe: `POST /api/model-probe {base_url, api_key, model}`.** Reuses the `/api/models` pattern (the key
is used once and never stored; same login requirement, same error shaping). In `web/forge.py`:
`probe_model(base_url, api_key, model) -> dict`:
- One streamed chat completion via `OpenAICompatGenerator` (so param adaptation, the btsgen User-Agent and
  the provider blocklist all apply) with a fixed forge-shaped prompt: design one Slay the Spire card as a
  short JSON object (name, cost, type, rarity, ~40-word description). `max_tokens` 2000 (a reasoning model
  must be allowed to think — that IS the measurement), hard timeout 45 s.
- Measures: `first_token_s` (first content chunk), `stream_s` (first to last chunk), `completion_tokens`
  (usage chunk when present, else `len(content)/4`), `visible_tokens = len(content)/4`.
- Derives: `S = completion_tokens / stream_s`, `M = max(1, completion_tokens / visible_tokens)`.
- Projects: `seconds = PROBE_CALLS × first_token_s + PROBE_VISIBLE × M / S`, with `PROBE_CALLS = 43` and
  `PROBE_VISIBLE = 25000` as module constants (0.1), reported as a range `[0.7×, 1.4×]`.
- A timeout is itself a verdict: `{timed_out: true, projected_s: null}` → "very slow or unreachable".
- Cached in-process per `(base_url, model)` for 1 h (never keyed by the API key).
- Cost to the user: ≤ 2000 output tokens, under a cent on every provider seen so far; the picker says so.

4.3 **Picker.** When the card model select changes (`onPick`, app.js ~675) and the key is present:
1. Call history; if `n >= 2` show `app.pick.history` ("Last {n} forges with this model took about {min} min")
   and stop unless the user clicks "measure anyway".
2. Else call the probe with a spinner line `app.pick.probing`; show `app.pick.projection`
   ("Measured {tps} tokens/s{reasoning}. A forge with this model should take roughly {lo}-{hi} min.
   You can close the tab once it starts; it will be in My Classes."), where `{reasoning}` is
   `app.pick.reasoning_note` (" and it thinks a lot before answering") when `M > 2`.
3. Over `PICK_CONFIRM_MIN` (60), the Forge button asks once: `app.pick.confirm` ("This model is projected
   to take about {min} min. The forge keeps running if you close the tab. Forge anyway?"). Not a gate below.
The design model is not probed (cards are ~97% of a forge's tokens). The projection line also appears in the
forge-estimate panel next to the token/cost figures for BYOK.

4.4 **Copy.**

| key | en | zh |
|---|---|---|
| `app.pick.probing` | Measuring this model's speed (a tiny test request on your key, under a cent)… | 正在测量该模型的速度（在你的密钥上发送一个很小的测试请求，不到一美分）… |
| `app.pick.projection` | Measured ~{tps} tokens/s{reasoning}. A forge with this model should take roughly {lo}-{hi} min. You can close the tab once it starts; it will be in My Classes. | 测得约 {tps} tokens/秒{reasoning}。用这个模型锻造大约需要 {lo}-{hi} 分钟。开始后可以关闭页面，完成后会出现在“我的角色”里。 |
| `app.pick.reasoning_note` |  and it thinks a lot before answering | ，而且它回答前会思考很久 |
| `app.pick.history` | The last {n} forges with this model took about {min} min. | 最近 {n} 次用这个模型锻造大约花了 {min} 分钟。 |
| `app.pick.timed_out` | This model didn't answer a tiny test in 45 s. A forge would take a very long time or not finish. | 这个模型 45 秒内没有回应一个很小的测试。锻造会非常慢，或无法完成。 |
| `app.pick.confirm` | This model is projected to take about {min} min. The forge keeps running if you close the tab, and the class will be in My Classes. Forge anyway? | 这个模型预计需要约 {min} 分钟。关闭页面后锻造仍会继续，完成后会出现在“我的角色”里。仍要锻造吗？ |
| `server.probe.failed` | Couldn't measure this model: {detail} | 无法测量这个模型：{detail} |

4.5 **Tests.** `web/tests`: probe endpoint against a stub HTTP server that streams N tokens at a chosen
rate with a chosen hidden-token share → projected range brackets the analytic value; timeout path; cache
hit does not re-call. History endpoint over seeded `forge_usage` + `forge_jobs` rows incl. one late finish.
Smoke `slow-pick`: `/api/model-probe` stubbed with `M=5, S=45` → projection line says ~40-80 min and the
Forge click shows the confirm; stubbed `M=1` → no confirm.

4.6 **Calibrate later.** After ~20 BYOK forges with a stored probe, compare projected vs actual
(`forge_jobs` gets two nullable columns: `projected_s`, `probe_json`; written at forge start when the
browser sends the probe result along) and adjust `PROBE_VISIBLE` / the range multipliers. Until then the
range is deliberately wide.

---

## 5. Deploys must not kill hour-long forges

Files: `web/deploy/deploy.sh`, `web/DEPLOY-DIGITALOCEAN.md`, droplet-deploy-path memory.

5.1 **Drain before restart.** New step between tests and restart: count `forge_jobs` with
`status='running'` (a `python -c` against the live DB via `web/db.py`, read-only). If > 0, print each
job's age/mode/concept and poll every 30 s until 0 or `BTSWEB_DEPLOY_DRAIN_MAX_S` (default 5400) elapses;
then restart anyway (boot reconciliation refunds what is left, as today). `--now` skips the wait. The
script already aborts before restart on any failure, so a drain timeout is just a loud log line.

5.2 **Later, if slow forges become common:** a separate `btsweb-forge` worker service fed from `forge_jobs`
so web deploys never touch running forges and an account could queue more than one. Not now; the drain
covers the current volume (~1 BYOK forge a week).

---

## 6. Rollout

Order matters only in that 2 depends on 1's codes and 3's eta field; 4 and 5 are independent.

1. Branch `feat/walk-away-forge`. Commits per section: (1) server ceiling + pools, (2) browser
   follow/resume/library row, (3) pace line, (4) history + probe + picker, (5) deploy drain. Code edits and
   test runs go to an Opus agent per the usual split; the main session reviews.
2. Green: `uv run python -m pytest web/tests -q` and `generation` tests from `generation/`
   (`uv run python -m pytest`); `python web/tools/build_i18n.py --check`; smoke `resume`, `late`,
   `library-running`, `slow-pick`, `lost`, `forge`, `forge-zh`.
3. Deploy with `sudo /opt/btsweb/deploy.sh` (the new drain step is live from this deploy on). No env
   changes needed; no mod/Workshop release (the codec is untouched).
4. Verify live: a `fake` forge streams and lands; reload mid-forge shows the resume banner; the three
   2026-11-08 jobs answer `late: true` on the status endpoint; `/api/model-history` for
   `ark.cn-beijing.volces.com / doubao-seed-evolving` returns n=2, median ≈ 50 min.
5. Update memory + DEPLOY doc; note the probe constants and the calibration follow-up (4.6) with a date.

## 7. Acceptance

- A BYOK forge that takes 50 minutes finishes on screen with no error, the log having said at card 3 that
  it would take about that long and that the tab can be closed.
- Reloading `/app` mid-forge shows "Still forging … about N min to go" and renders the class when it lands;
  My Classes shows the in-progress row meanwhile.
- Picking doubao-seed-evolving or deepseek-v4-pro in the picker shows a 40-80 min projection (history once
  it exists, probe before that) and a confirm on Forge; picking gpt-6.1-sol shows ~8-15 min and no confirm.
- A token forge behaves exactly as today past 20 minutes (refund, abandon), plus the follow.
- A BYOK forge never blocks a token forge's slot.
- A deploy while a forge runs waits for it (or is told to go now) instead of refunding/failing it.
- Chinese UI shows every new string in Chinese.

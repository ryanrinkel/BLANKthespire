// UI smoke driver for the web app: boots headless Chrome, signs in through /dev-login, clicks through the
// forge / library / account / public pages and writes screenshots + any console errors. Needs a dev server:
//   BTSWEB_DEV_AUTH=1 BTSWEB_NO_DOTENV=1 BTSWEB_UNLIMITED_EMAILS=unlimited@example.com \
//     STRIPE_SECRET_KEY=sk_test_smoke PORT=5077 uv run --project ../generation python app.py
// (the dummy Stripe key only flips /api/billing to {enabled:true} so the donate tiers + custom-amount row
//  render; nothing in these scenarios ever hits Stripe)
// then, from web/tools:  node ui_smoke.mjs http://127.0.0.1:5077 <outdir> forge|library|account|pages|art|lost
// (needs a package.json with {"type":"module"} next to it, or rename to .mjs — it is already .mjs).

// Minimal Chrome DevTools Protocol driver (Node 24 has a global WebSocket). Usage:
//   node cdp.mjs <base> <outdir> <scenario>
// Scenarios drive the signed-in app and take screenshots; console errors / exceptions are printed.
import { spawn } from "node:child_process";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const [base, outdir, scenario] = process.argv.slice(2);
const CHROME = "C:/Program Files/Google/Chrome/Application/chrome.exe";
const port = 9333 + Math.floor(Math.random() * 500);
const profile = mkdtempSync(join(tmpdir(), "cdp-"));
const chrome = spawn(CHROME, ["--headless=new", "--disable-gpu", "--no-sandbox", `--remote-debugging-port=${port}`,
  `--user-data-dir=${profile}`, "--window-size=1200,1400", "about:blank"], { stdio: "ignore" });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function getTarget() {
  for (let i = 0; i < 40; i++) {
    try {
      const r = await fetch(`http://127.0.0.1:${port}/json/list`);
      const list = await r.json();
      const t = list.find((x) => x.type === "page");
      if (t) return t;
    } catch (_) {}
    await sleep(250);
  }
  throw new Error("chrome did not come up");
}

const target = await getTarget();
const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((r) => (ws.onopen = r));
let id = 0; const pending = new Map(); const errors = [];
ws.onmessage = (m) => {
  const msg = JSON.parse(m.data);
  if (msg.id && pending.has(msg.id)) { pending.get(msg.id)(msg); pending.delete(msg.id); }
  if (msg.method === "Runtime.exceptionThrown") errors.push("EXC " + (msg.params.exceptionDetails.exception?.description || msg.params.exceptionDetails.text));
  if (msg.method === "Runtime.consoleAPICalled" && (msg.params.type === "error" || msg.params.type === "warning"))
    errors.push(msg.params.type.toUpperCase() + " " + msg.params.args.map((a) => a.value ?? a.description).join(" "));
  if (msg.method === "Log.entryAdded" && msg.params.entry.level === "error") errors.push("LOG " + msg.params.entry.text + " " + (msg.params.entry.url || ""));
};
const send = (method, params = {}) => new Promise((res, rej) => {
  const i = ++id; pending.set(i, (m) => (m.error ? rej(new Error(method + ": " + JSON.stringify(m.error))) : res(m.result)));
  ws.send(JSON.stringify({ id: i, method, params }));
});
const evaluate = async (expr) => {
  const r = await send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true });
  if (r.exceptionDetails) throw new Error("eval failed: " + JSON.stringify(r.exceptionDetails).slice(0, 300));
  return r.result.value;
};
const nav = async (url) => { await send("Page.navigate", { url }); await sleep(1500); };
const shot = async (name, fullPage = true) => {
  const r = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: fullPage });
  writeFileSync(join(outdir, name + ".png"), Buffer.from(r.data, "base64"));
  console.log("shot", name);
};

// Assertions are logged, not thrown: the run finishes and every failure also lands in `errors`, which is
// printed at the end (and is what a caller greps for).
const check = (ok, name, detail = "") => {
  console.log(`${ok ? "OK  " : "FAIL"} ${name}${detail ? ": " + detail : ""}`);
  if (!ok) errors.push("assertion failed: " + name);
};
const json = async (expr) => JSON.parse(await evaluate(`JSON.stringify(${expr})`));

await send("Page.enable"); await send("Runtime.enable"); await send("Log.enable");
await nav(`${base}/dev-login?email=unlimited@example.com`);

if (scenario === "forge") {
  // 2026-09-21: the mode radios are gone. The forge card is textarea -> interactive toggle -> two
  // <details> payment boxes (#forge-byok / #forge-token, mutually exclusive) -> the centred #forge-btn,
  // which is DISABLED until the open box can pay for a forge. Sign in as a plain (non-unlimited) address
  // so the gating is real, on a fresh browser profile so nothing is remembered.
  await nav(`${base}/dev-login?email=smoke-forge@example.com`);
  await nav(`${base}/app`);
  await evaluate(`localStorage.clear()`);
  await nav(`${base}/app`);

  // (a) fresh account, no tokens, nothing remembered: both boxes shut, button disabled.
  const fresh = await json(`({unlimited: !!ME.unlimited, balance: ME.token_balance,
    disabled: document.getElementById('forge-btn').disabled,
    label: document.getElementById('forge-btn').textContent,
    title: document.getElementById('forge-btn').title,
    byok_open: document.getElementById('forge-byok').open,
    token_open: document.getElementById('forge-token').open,
    balance_line: document.getElementById('token-balance-line').textContent})`);
  check(!fresh.unlimited && fresh.balance === 0 && fresh.disabled && !fresh.byok_open && !fresh.token_open
        && fresh.label === "Forge the class",
        "fresh 0-token account: button disabled, both boxes closed", JSON.stringify(fresh));

  // (d) the interactive toggle is a property of the forge, not of how it is paid for: it sits in the card
  // but inside neither box.
  // Since 2026-09-26 it is folded into "Advanced options" under the forge button, closed by default.
  const where = await json(`(() => { const i = document.getElementById('interactive'); const a = document.getElementById('forge-advanced'); return {
    in_card: document.getElementById('forge-input').contains(i),
    in_byok: document.getElementById('forge-byok').contains(i),
    in_token: document.getElementById('forge-token').contains(i),
    in_advanced: a.contains(i), advanced_open: a.open,
    below_button: !!(document.getElementById('forge-btn').compareDocumentPosition(a) & Node.DOCUMENT_POSITION_FOLLOWING)}; })()`);
  check(where.in_card && !where.in_byok && !where.in_token && where.in_advanced && !where.advanced_open && where.below_button,
        "interactive checkbox is in the closed Advanced options under the button", JSON.stringify(where));
  await shot("forge-fresh");

  // (b) open the key box and fill it in: the button enables and says whose money it spends.
  await evaluate(`document.getElementById('forge-byok').open = true`); await sleep(300);
  const keyed = await json(`(() => {
    const k = document.getElementById('api_key'); k.value = 'sk-ant-smoke'; k.dispatchEvent(new Event('input'));
    const m = document.getElementById('model'); m.value = 'claude-sonnet-4-6'; m.dispatchEvent(new Event('input'));
    return {disabled: document.getElementById('forge-btn').disabled,
            label: document.getElementById('forge-btn').textContent,
            token_open: document.getElementById('forge-token').open,
            pref: localStorage.getItem('bts_forge_pref')}; })()`);
  check(!keyed.disabled && keyed.label.includes("uses your API key") && !keyed.token_open,
        "byok box open + key + model: button enabled", JSON.stringify(keyed));
  // The pay boxes read as a radio pair (2026-09-26): the selected one carries the accent border and a
  // "Selected" tag, the other neither; clicking the selected header does not fold it.
  const radio = await json(`(() => {
    const tag = (id) => getComputedStyle(document.querySelector('#' + id + ' > summary'), '::after').content;
    const border = (id) => getComputedStyle(document.getElementById(id)).borderTopColor;
    document.querySelector('#forge-byok > summary').click();
    return {byok_tag: tag('forge-byok'), token_tag: tag('forge-token'),
            byok_border: border('forge-byok'), token_border: border('forge-token'),
            still_open: document.getElementById('forge-byok').open}; })()`);
  check(radio.byok_tag === '"Selected"' && radio.token_tag === "none" && radio.byok_border !== radio.token_border
        && radio.still_open, "selected pay box is highlighted and can't be clicked shut", JSON.stringify(radio));
  // The quote is behind a button (2026-09-21): hidden until clicked, and a model/provider change hides it
  // again until the button is clicked once more.
  const est = JSON.parse(await evaluate(`(() => {
    const box = document.getElementById('byok-estimate'), btn = document.getElementById('estimate-btn');
    const before = box.classList.contains('hidden') && !btn.classList.contains('hidden');
    btn.click();
    const shown = !box.classList.contains('hidden') && btn.classList.contains('hidden') && box.textContent.includes('Estimated cost');
    const m = document.getElementById('model'); m.value = 'gpt-5'; m.dispatchEvent(new Event('input'));
    const folded = box.classList.contains('hidden') && !btn.classList.contains('hidden');
    return JSON.stringify({before, shown, folded, text: box.textContent.slice(0, 120)}); })()`));
  check(est.before && est.shown && est.folded, "estimate hidden behind its button, folds on a settings change", JSON.stringify(est));
  // 2026-09-28: the estimate is a link in the box's footer, beside the art chip.
  const foot = await json(`(() => { const b = document.getElementById('estimate-btn');
    return {in_foot: b.parentElement.classList.contains('byok-foot'), linkish: b.classList.contains('linkish'),
            chip: document.getElementById('byok-art').textContent}; })()`);
  check(foot.in_foot && foot.linkish && ["No generated art", "Art included"].includes(foot.chip),
        "estimate link + art chip in the footer", JSON.stringify(foot));
  await evaluate(`document.getElementById('estimate-btn').click()`);
  await shot("forge-byok");
  // The pre-go quote (2026-09-28): a table with one row per model (one "Design + cards" row when the card
  // box is blank), an Art row, and a Total; at most one note. An art provider with a cheaper OpenRouter
  // route says so; a provider with no image API says "not on this provider" in the Art row.
  const pickProvider = (id, model, cardModel = "") => `(() => {
    const p = document.getElementById('provider'); p.value = ${JSON.stringify(id)};
    p.dispatchEvent(new Event('change'));
    const m = document.getElementById('model'); m.value = ${JSON.stringify(model)};
    m.dispatchEvent(new Event('input'));
    const c = document.getElementById('card_model'); c.value = ${JSON.stringify(cardModel)};
    c.dispatchEvent(new Event('input'));
    document.getElementById('estimate-btn').click();
    const box = document.getElementById('byok-estimate');
    return JSON.stringify({labels: [...box.querySelectorAll('.est-table th')].map(e => e.textContent),
                           rows: [...box.querySelectorAll('.est-table tr')].map(e => e.textContent),
                           notes: [...box.querySelectorAll('.est-note')].map(e => e.textContent)});
  })()`;
  for (const [id, model, cardModel, want] of [
      ["google", "gemini-2.5-flash-lite", "", ["Design + cards", "Art", "Total"]],
      ["xai", "grok-4.20-0309-non-reasoning", "", ["Design + cards", "Art", "Total"]],
      ["groq", "llama-3.3-70b-versatile", "", ["Design + cards", "Art", "Total"]],
      ["anthropic", "claude-opus-4-8", "claude-haiku-4-5", ["Design", "Card coding", "Art", "Total"]]]) {
    const got = JSON.parse(await evaluate(pickProvider(id, model, cardModel)));
    const noteOk = id === "google" || id === "xai" ? got.notes.some((n) => n.includes("OpenRouter key makes"))
                 : got.notes.length <= 1;
    const artOk = id === "groq" || id === "anthropic" ? got.rows.some((r) => r.includes("not on this provider")) : true;
    const priced = !got.rows.some((r) => r.includes("?"));
    const ok = got.labels.join() === want.join() && noteOk && artOk && priced;
    console.log(`${ok ? "OK  " : "FAIL"} estimate/${id}: ${JSON.stringify(got.rows)} ${JSON.stringify(got.notes)}`);
    if (!ok) errors.push(`estimate for ${id} did not render as expected`);
    if (id === "google") await shot("forge-byok-gemini-estimate");
    if (id === "anthropic") await shot("forge-byok-two-models");
  }
  // The confirm dialog carries both models and the same total.
  const confirmText = await evaluate(`estimateText()`);
  check(confirmText.includes("Design: claude-opus-4-8 · Cards: claude-haiku-4-5") && confirmText.includes("≈ $"),
        "confirm text names both models and a total", JSON.stringify(confirmText));
  // (c) opening the token box closes the key box; with no tokens the button goes back to disabled, and
  // the custom-amount row prices a typed $25 live.
  await evaluate(`document.getElementById('forge-token').open = true`); await sleep(400);
  const tok = await json(`({byok_open: document.getElementById('forge-byok').open,
    disabled: document.getElementById('forge-btn').disabled,
    label: document.getElementById('forge-btn').textContent,
    title: document.getElementById('forge-btn').title,
    balance_line: document.getElementById('token-balance-line').textContent,
    tiers: [...document.querySelectorAll('#forge-donate-tiers .donate-tier')].map(b => b.textContent.replace(/\\s+/g, ' ').trim()),
    custom_hidden: document.getElementById('forge-donate-custom').classList.contains('hidden')})`);
  check(!tok.byok_open && tok.disabled && tok.label === "Forge the class"
        && tok.title.includes("no tokens"),
        "token box open with 0 tokens: byok closed, button disabled", JSON.stringify(tok));
  // "Get tokens" (2026-09-26): with 0 tokens the tiers are already unfolded; with tokens in hand they fold
  // behind the button, which unfolds them on click.
  const gt = await json(`(() => {
    const wrap = document.getElementById('forge-donate-wrap'), b = document.getElementById('forge-get-tokens');
    const zero = {shown: !wrap.classList.contains('hidden'), label: b.textContent};
    ME.token_balance = 3; renderTokens();
    const some = {shown: !wrap.classList.contains('hidden'), label: b.textContent};
    b.click();
    const clicked = {shown: !wrap.classList.contains('hidden'), label: b.textContent};
    ME.token_balance = 0; GET_TOKENS_OPEN = null; renderTokens();
    return {zero, some, clicked}; })()`);
  check(gt.zero.shown && gt.zero.label === "Hide token options" && !gt.some.shown && gt.some.label === "Get tokens"
        && gt.clicked.shown, "tier buttons fold behind Get tokens when the account has tokens", JSON.stringify(gt));
  if (tok.custom_hidden) {
    check(false, "custom-amount row rendered (needs /api/billing enabled + custom block)", "row hidden");
  } else {
    // The row is collapsed behind "Enter another custom amount" (2026-09-21) — open it first.
    const collapsed = await json(`(() => ({
      reveal: !!document.getElementById('forge-donate-custom-open'),
      row: !!document.getElementById('forge-donate-custom-input')}))()`);
    check(collapsed.reveal && !collapsed.row, "custom amount collapsed behind its button",
          JSON.stringify(collapsed));
    const cc = await json(`(() => { const b = document.getElementById('forge-donate-custom-open');
      const r = b.getBoundingClientRect(), p = b.parentElement.getBoundingClientRect();
      return {off: Math.round((r.left - p.left) - (p.right - r.right)),
              w: Math.round(r.width), pw: Math.round(p.width)}; })()`);
    check(Math.abs(cc.off) <= 2 && cc.w < cc.pw - 40, "custom-amount button centred, not stretched",
          JSON.stringify(cc));
    await shot("forge-token-collapsed");
    await evaluate(`document.getElementById('forge-donate-custom-open').click()`);
    const custom = await json(`(() => {
      const i = document.getElementById('forge-donate-custom-input');
      i.value = '25'; i.dispatchEvent(new Event('input'));
      return {btn: document.getElementById('forge-donate-custom-btn').textContent,
              line: document.getElementById('forge-donate-custom-line').textContent,
              min: i.min, max: i.max, step: i.step}; })()`);
    check(custom.btn === "Get 25 tokens" && /\$\d+\.\d\d charged, incl\. \$\d+\.\d\d card fee/.test(custom.line),
          "custom amount: $25 prices live", JSON.stringify(custom));
  }
  await shot("forge-token");
} else if (scenario === "byok-narrow") {
  // The BYOK box at phone width: both two-column rows stack, nothing scrolls sideways.
  await send("Emulation.setDeviceMetricsOverride", { width: 390, height: 1400, deviceScaleFactor: 1, mobile: true });
  await nav(`${base}/dev-login?email=smoke-narrow@example.com`);
  await nav(`${base}/app`);
  await evaluate(`(() => { document.getElementById('forge-byok').open = true;
    const p = document.getElementById('provider'); p.value = 'openrouter'; p.dispatchEvent(new Event('change'));
    const k = document.getElementById('api_key'); k.value = 'sk-or-smoke'; k.dispatchEvent(new Event('input'));
    const m = document.getElementById('model'); m.value = 'anthropic/claude-sonnet-4.6'; m.dispatchEvent(new Event('input'));
    const c = document.getElementById('card_model'); c.value = 'openai/gpt-4o'; c.dispatchEvent(new Event('input'));
    document.getElementById('estimate-btn').click(); })()`);
  await sleep(300);
  const narrow = await json(`({scrollW: document.documentElement.scrollWidth, w: window.innerWidth,
    stacked: document.getElementById('card_model').getBoundingClientRect().top
             > document.getElementById('model').getBoundingClientRect().bottom})`);
  check(narrow.scrollW <= narrow.w && narrow.stacked, "byok box stacks at 390px with no sideways scroll",
        JSON.stringify(narrow));
  await evaluate(`document.getElementById('forge-byok').scrollIntoView()`);
  await shot("byok-narrow");
} else if (scenario === "lost") {
  // 2026-09-26: a dropped progress stream (phone locked / network hop -> Chrome's bare "network error") must
  // read as "still forging", then recover on its own by polling /api/forge-jobs/<id>. window.fetch is stubbed
  // per case: /api/forge-class plays the scripted stream, /api/forge-jobs/* answers from a scripted list of
  // job states (404 = the number 404), everything else (the finished class) goes to the real server. Each
  // poll waits RECOVER_POLL_MS (5 s), so this scenario takes ~a minute.
  await nav(`${base}/app`);
  // A real class for the "done" polls to point at: the dev-only offline forge makes one in seconds.
  const classId = await evaluate(`(async () => {
    await (await fetch('/api/forge-class', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({concept: 'lost-scenario seed', mode: 'fake'})})).text();
    return (await (await fetch('/api/classes')).json()).classes[0].id; })()`);
  // escaped newlines: the frame is pasted into a '...' literal inside the evaluated source
  const sse = (ev, data) => `event: ${ev}\\ndata: ${JSON.stringify(data)}\\n\\n`;
  const enc = "const e = new TextEncoder();";
  const state = () => json(`({lost: !document.getElementById('forge-lost').classList.contains('hidden'),
    text: document.getElementById('forge-lost-text').textContent,
    log: document.getElementById('log').textContent,
    result: !document.getElementById('result').classList.contains('hidden'),
    choice: !document.getElementById('choice').classList.contains('hidden'),
    choice_opts: document.querySelectorAll('#choice-options button').length,
    forging: FORGING, polled: window.__jobUrls})`);
  // Start a forge against the stubs WITHOUT awaiting it; finish() awaits it and returns the end state.
  const start = async (forgeBody, jobs) => {
    await evaluate(`(() => {
      document.getElementById('result').classList.add('hidden');
      document.getElementById('concept').value = 'An evil lemon';
      currentMode = () => 'token'; window.confirm = () => true;
      window.__realFetch = window.__realFetch || window.fetch;
      window.__jobs = ${JSON.stringify(jobs)}; window.__jobUrls = [];
      window.fetch = async (url, opts) => {
        url = String(url);
        if (url.startsWith('/api/forge-jobs/')) {
          window.__jobUrls.push(url);
          const j = window.__jobs.length > 1 ? window.__jobs.shift() : window.__jobs[0];
          return j === 404 ? new Response('{"error":"no such forge."}', {status: 404})
            : new Response(JSON.stringify(j), {status: 200, headers: {'content-type': 'application/json'}});
        }
        if (url === '/api/forge-class') { ${forgeBody} }
        return window.__realFetch(url, opts);
      };
      window.__forgeP = forge();
    })()`);
  };
  const finish = async () => { await evaluate(`window.__forgeP`); return state(); };
  const dropStream = `${enc} let n = 0; return new Response(new ReadableStream({ pull(c) {
      if (n++ === 0) c.enqueue(e.encode('${sse("progress", {message: "starting…", forge_id: "f1"})}'));
      else c.error(new TypeError('network error')); } }), {status: 200, headers: {'content-type': 'text/event-stream'}});`;
  const opts = [{id: "poison", name: "Poison", pitch: "stack it"}, {id: "block", name: "Block", pitch: "turtle"}];

  // (1) drop mid-stream -> notice -> polls show progress + re-show the engine pick -> the class renders.
  await start(dropStream, [
    {forge_id: "f1", status: "running", message: "writing cards…",
     choice: {forge_id: "f1", options: opts, timeout_s: 60}},
    {forge_id: "f1", status: "running", message: "painting portraits…"},
    {forge_id: "f1", status: "done", class_id: classId, error: "", refunded: false}]);
  await sleep(1000);
  const s1 = await state();
  check(s1.lost && /pick it back up/.test(s1.text) && /My Classes/.test(s1.text) && /refunded/.test(s1.text) && s1.forging,
        "drop: still-running notice while it reconnects", JSON.stringify(s1));
  await shot("lost-dropped");
  await sleep(5500);
  const s1b = await state();
  check(s1b.choice && s1b.choice_opts === 2 && /writing cards/.test(s1b.log),
        "drop: a poll re-shows the pending engine pick and the progress line", JSON.stringify(s1b));
  await shot("lost-choice");
  const d1 = await finish();
  check(!d1.lost && d1.result && /done \(reconnected\)/.test(d1.log) && /painting portraits/.test(d1.log)
        && !d1.forging && d1.polled.every((u) => u.endsWith("/f1")),
        "drop: recovers to the finished class on its own", JSON.stringify(d1));
  await shot("lost-recovered");

  // (2) the stream just ends without a result, and the forge failed: the error and refund show, no notice.
  await start(`${enc} return new Response(new ReadableStream({ start(c) {
      c.enqueue(e.encode('${sse("progress", {message: "starting…", forge_id: "f2"})}')); c.close(); } }), {status: 200});`,
    [{forge_id: "f2", status: "failed", class_id: null, error: "blueprint failed", refunded: true}]);
  const d2 = await finish();
  check(!d2.lost && /blueprint failed — your token was refunded/.test(d2.log), "early EOF then failure: error + refund", JSON.stringify(d2));

  // (3) the POST never got an answer, and no forge exists: three 404s on "latest" -> "nothing was spent".
  await start(`throw new TypeError('Failed to fetch');`, [404]);
  await sleep(800);
  const s3 = await state();
  check(s3.lost && /Couldn't reach the server/.test(s3.text), "unreachable: checking notice", JSON.stringify(s3));
  const d3 = await finish();
  check(d3.lost && /No forge was started/.test(d3.text) && d3.polled.length === 3 && d3.polled.every((u) => u.endsWith("/latest")),
        "unreachable + nothing started: says so after 3 polls", JSON.stringify(d3));
  await shot("lost-unreachable");

  // (4) the POST died but the forge DID start: "latest" finds it, pins to its id, and recovers.
  await start(`throw new TypeError('Failed to fetch');`, [
    {forge_id: "f4", status: "running", message: "mapping your theme…"},
    {forge_id: "f4", status: "done", class_id: classId, error: "", refunded: false}]);
  const d4 = await finish();
  check(d4.result && !d4.lost && d4.polled[0].endsWith("/latest") && d4.polled[1].endsWith("/f4"),
        "unreachable but started: found via latest, then recovers", JSON.stringify(d4));

  // (5) a non-JSON 502 page and (6) a real error event stay plain errors: no notice, no polling.
  await start(`return new Response('<html>bad gateway</html>', {status: 502, headers: {'content-type': 'text/html'}});`, [404]);
  const d5 = await finish();
  check(!d5.lost && /HTTP 502/.test(d5.log) && d5.polled.length === 0, "a 502 page is an error, not a lost stream", JSON.stringify(d5));
  await start(`${enc} return new Response(new ReadableStream({ start(c) {
      c.enqueue(e.encode('${sse("error", {error: "blueprint failed"})}')); c.close(); } }), {status: 200});`, [404]);
  const d6 = await finish();
  check(!d6.lost && /blueprint failed/.test(d6.log) && d6.polled.length === 0, "a real forge error does not poll", JSON.stringify(d6));
} else if (scenario === "library") {
  await nav(`${base}/app`);
  await evaluate(`document.getElementById('nav-library').click()`); await sleep(800);
  await shot("library");
  await evaluate(`document.querySelector('[data-act=open]').click()`); await sleep(1000);
  console.log(await evaluate(`JSON.stringify({input_hidden: document.getElementById('forge-input').classList.contains('hidden'), title: document.getElementById('view-title').textContent, share: document.getElementById('share-link').dataset.url, share_hidden: document.getElementById('share-link').classList.contains('hidden'), fb_buttons: document.querySelectorAll('#result .cc-fb').length})`));
  await shot("viewing");
  await evaluate(`document.getElementById('view-back').click()`); await sleep(300);
  console.log("after back, input hidden:", await evaluate(`document.getElementById('forge-input').classList.contains('hidden')`));
} else if (scenario === "account") {
  await nav(`${base}/app`); await evaluate(`document.getElementById('nav-account').click()`); await sleep(1500);
  await shot("account");
  console.log(await evaluate(`JSON.stringify({stats_hidden: document.getElementById('stats').classList.contains('hidden'), tiles: document.querySelectorAll('.stat-tile').length, chart: document.getElementById('stats-chart').innerHTML.slice(0,80), note: document.getElementById('stats-note').textContent})`));

  // Operator user panel: it renders for an admin, search filters it, and both writes round-trip. The
  // target is a throwaway account the driver signs in as first, so this never edits a real row.
  await nav(`${base}/dev-login?email=smoke-target@example.com`);
  await nav(`${base}/dev-login?email=unlimited@example.com`);
  await nav(`${base}/app`); await evaluate(`document.getElementById('nav-account').click()`); await sleep(1500);
  console.log("panel:", await evaluate(`JSON.stringify({hidden: document.getElementById('admin-users').classList.contains('hidden'), rows: document.querySelectorAll('#admin-users-table tr[data-uid]').length, note: document.getElementById('admin-users-note').textContent, log: document.getElementById('admin-actions').children.length})`));
  await evaluate(`el('admin-users-q').value = 'smoke-target'; el('admin-users-q').dispatchEvent(new Event('input'))`); await sleep(900);
  console.log("searched:", await evaluate(`JSON.stringify([...document.querySelectorAll('#admin-users-table tr[data-uid]')].map(r => r.querySelector('.who-cell').innerText))`));
  await shot("admin-users");
  // Set the balance to 7, then grant unlimited, watching the inline row notes.
  await evaluate(`{const r = document.querySelector('#admin-users-table tr[data-uid]'); r.querySelector('.tok').value = '7'; r.querySelector('.tok-save').click();}`); await sleep(800);
  console.log("after save:", await evaluate(`JSON.stringify({note: document.querySelector('#admin-users-table tr[data-uid] .row-note').textContent, val: document.querySelector('#admin-users-table tr[data-uid] .tok').value, log: document.getElementById('admin-actions').firstElementChild?.innerText})`));
  await evaluate(`{const b = document.querySelector('#admin-users-table tr[data-uid] .unl-box'); b.checked = true; b.dispatchEvent(new Event('change', {bubbles: true}));}`); await sleep(800);
  console.log("after unlimited:", await evaluate(`JSON.stringify({note: document.querySelector('#admin-users-table tr[data-uid] .row-note').textContent, log: document.getElementById('admin-actions').firstElementChild?.innerText})`));
  await shot("admin-users-edited");
} else if (scenario === "dbg") {
  await nav(`${base}/app#account`); await sleep(1500);
  console.log(await evaluate(`JSON.stringify({admin: ME && ME.admin, hash: location.hash, acct_hidden: document.getElementById('view-account').classList.contains('hidden')})`));
  console.log(await evaluate(`loadStats().then(() => 'loadStats ok: hidden=' + document.getElementById('stats').classList.contains('hidden') + ' tiles=' + document.querySelectorAll('.stat-tile').length).catch(e => 'loadStats threw: ' + e.message)`));
  await shot("account2");
} else if (scenario === "v3") {
  // Pricing v3: a fresh (0-token, non-unlimited) account sees the key-or-token chooser + the launch banner;
  // "Support the forge" opens the inline tier buttons; the Account tab shows the same tiers; public pages.
  await nav(`${base}/dev-login?email=newbie@example.com`);
  await nav(`${base}/app`); await sleep(1200);
  console.log(await evaluate(`JSON.stringify({balance: ME.token_balance, chip: document.getElementById('tokens').textContent, chooser_hidden: document.getElementById('chooser').classList.contains('hidden'), banner_hidden: document.getElementById('v3-banner').classList.contains('hidden'), head: document.getElementById('chooser-head')?.textContent, forge_btn: document.getElementById('forge-btn').textContent, balance_line: document.getElementById('token-balance-line').textContent})`));
  await shot("v3-chooser");
  await evaluate(`document.getElementById('choose-token').click()`); await sleep(1200);
  console.log(await evaluate(`JSON.stringify({pref: localStorage.getItem('bts_forge_pref'), strip: document.getElementById('chooser-strip')?.textContent, token_open: document.getElementById('forge-token').open, tiers: [...document.querySelectorAll('#forge-donate-tiers .donate-tier')].map(b => b.textContent.trim().replace(/\\s+/g,' '))})`));
  await shot("v3-inline-donate");
  await evaluate(`document.getElementById('choose-byok')?.click()`); await sleep(500);
  console.log("after byok:", await evaluate(`JSON.stringify({pref: localStorage.getItem('bts_forge_pref'), strip: document.getElementById('chooser-strip')?.textContent, byok_open: document.getElementById('forge-byok').open, token_open: document.getElementById('forge-token').open})`));
  await evaluate(`document.getElementById('nav-account').click()`); await sleep(1500);
  console.log(await evaluate(`JSON.stringify({acct_tiers: document.querySelectorAll('#donate-tiers .donate-tier').length, custom_reveal: document.getElementById('donate-custom-open')?.textContent, history: document.getElementById('purchases-empty').textContent})`));
  await shot("v3-account");
  await evaluate(`document.getElementById('nav-forge').click()`); await sleep(300);
  await evaluate(`document.getElementById('v3-banner-x').click()`); await sleep(300);
  console.log("banner dismissed:", await evaluate(`document.getElementById('v3-banner').classList.contains('hidden') + ' ' + localStorage.getItem('bts_v3_banner_dismissed')`));
  for (const p of ["terms", "privacy", ""]) { await nav(`${base}/${p}`); await sleep(500); await shot("v3-page-" + (p || "landing")); }
  console.log("landing pricing:", await evaluate(`[...document.querySelectorAll('.pricing li')].map(l => l.innerText.replace(/\\s+/g, ' ')).join(' || ')`));
} else if (scenario === "pages") {
  for (const p of ["download", "help"]) { await nav(`${base}/${p}`); await shot(p); }
  const slug = await evaluate(`fetch('/api/classes').then(r => r.json()).then(d => d.classes[0].slug)`);
  await nav(`${base}/deck/${slug}`); await sleep(800);
  console.log(await evaluate(`JSON.stringify({name: document.getElementById('r-name').textContent, cards: document.querySelectorAll('#r-cards .cardchip').length, fb: document.querySelectorAll('.cc-fb').length, og: document.querySelector('meta[property="og:title"]')?.content, code: document.getElementById('r-code').value.slice(0,12)})`));
  await shot("deck");
  await nav(`${base}/deck/nope-not-here`); console.log("404 page:", (await evaluate(`document.body.innerText.slice(0,120)`)).replace(/\n/g, " "));
} else if (scenario === "art") {
  // 2026-09-24: My Classes rows lead with splash + sprite thumbnails and carry a share-link button; the
  // "Show art" checkbox (localStorage bts_show_art) repaints the list without images and hides the art in
  // an open class view; the opened class (and the public /deck page) shows the splash/sprite strip and
  // one portrait per card. Needs a server with BTSGEN_IMAGE_BACKEND=procedural so a fake forge ships art.
  await nav(`${base}/app`);
  await evaluate(`localStorage.clear()`);
  const forged = await evaluate(`fetch('/api/forge-class', {method: 'POST',
    headers: {'Content-Type': 'application/json', 'X-Requested-With': 'fetch'},
    body: JSON.stringify({concept: 'a smoke-test alchemist', mode: 'fake'})})
    .then(r => r.text()).then(t => ({len: t.length, done: t.includes('event: result'), art: t.includes('card art')}))`);
  check(forged.done, "fake forge finished (procedural art)", JSON.stringify(forged));
  await evaluate(`document.getElementById('nav-library').click()`); await sleep(2500);
  const imgOk = (sel) => `(() => { const i = li.querySelector('${sel}'); return !!i && i.complete && i.naturalWidth > 0; })()`;
  const rows = await json(`[...document.querySelectorAll('#lib-list .lib-row')].map(li => ({
    art: !!li.querySelector('.lr-art'), splash: ${imgOk(".lr-splash")}, sprite: ${imgOk(".lr-sprite")},
    share: !!li.querySelector('[data-act=share]'), code: !!li.querySelector('[data-act=code]')}))`);
  check(rows.length > 0 && rows.every((r) => r.art && r.splash && r.sprite && r.share && r.code),
        "library rows: splash + sprite thumbs loaded, share + code buttons", JSON.stringify(rows));
  const toggle = await json(`({checked: document.getElementById('lib-show-art').checked, no_art: document.body.classList.contains('no-art')})`);
  check(toggle.checked && !toggle.no_art, "show art defaults on", JSON.stringify(toggle));
  await shot("art-library");

  await evaluate(`document.getElementById('lib-show-art').click()`); await sleep(400);
  const off = await json(`({no_art: document.body.classList.contains('no-art'), imgs: document.querySelectorAll('#lib-list img').length,
    pref: localStorage.getItem('bts_show_art'), rows: document.querySelectorAll('#lib-list .lib-row').length})`);
  check(off.no_art && off.imgs === 0 && off.pref === "0" && off.rows === rows.length,
        "show art off: rows repaint without images, pref stored", JSON.stringify(off));
  await shot("art-library-off");

  // an open class view rendered with art off has no strip and no portraits at all
  await evaluate(`document.querySelector('[data-act=open]').click()`); await sleep(1500);
  const viewOff = await json(`({strip_hidden: document.getElementById('r-art').classList.contains('hidden'),
    portraits: document.querySelectorAll('#r-cards .cc-art').length, cards: document.querySelectorAll('#r-cards .cardchip').length})`);
  check(viewOff.strip_hidden && viewOff.portraits === 0 && viewOff.cards > 0, "class view with art off: no strip, no portraits", JSON.stringify(viewOff));

  // back on: the list repaints with images, and the opened class shows the strip + every portrait
  await evaluate(`document.getElementById('nav-library').click()`); await sleep(800);
  await evaluate(`document.getElementById('lib-show-art').click()`); await sleep(400);
  check(await evaluate(`document.querySelectorAll('#lib-list img').length`) === rows.length * 2, "show art on again: images back");
  await evaluate(`document.querySelector('[data-act=open]').click()`); await sleep(1500);
  await evaluate(`window.scrollTo(0, document.body.scrollHeight)`); await sleep(2500);  // lazy portraits below the fold
  await evaluate(`window.scrollTo(0, 0)`); await sleep(300);
  const view = await json(`({strip: !document.getElementById('r-art').classList.contains('hidden'),
    splash_w: document.querySelector('.r-splash')?.naturalWidth || 0, sprite_w: document.querySelector('.r-sprite')?.naturalWidth || 0,
    cards: document.querySelectorAll('#r-cards .cardchip').length, portraits: document.querySelectorAll('#r-cards .cc-art').length,
    loaded: [...document.querySelectorAll('#r-cards .cc-art')].filter((i) => i.complete && i.naturalWidth > 0).length})`);
  check(view.strip && view.splash_w > 0 && view.sprite_w > 0 && view.portraits === view.cards && view.loaded === view.portraits,
        "class view: strip + one loaded portrait per card", JSON.stringify(view));
  await shot("art-viewing");

  // the public share page renders the same art without a session
  const share = await evaluate(`document.getElementById('share-link').dataset.url`);
  check(/\/deck\/[A-Za-z0-9_-]{20,}$/.test(share), "share link shape", share);
  await nav(share); await sleep(1500);
  await evaluate(`window.scrollTo(0, document.body.scrollHeight)`); await sleep(2500);
  const pub = await json(`({strip: !document.getElementById('r-art').classList.contains('hidden'),
    splash_w: document.querySelector('.r-splash')?.naturalWidth || 0,
    cards: document.querySelectorAll('#r-cards .cardchip').length, portraits: document.querySelectorAll('#r-cards .cc-art').length,
    loaded: [...document.querySelectorAll('#r-cards .cc-art')].filter((i) => i.complete && i.naturalWidth > 0).length})`);
  check(pub.strip && pub.splash_w > 0 && pub.portraits === pub.cards && pub.loaded === pub.portraits, "public deck page shows the art", JSON.stringify(pub));
  await shot("art-deck");
}
console.log(errors.length ? "CONSOLE ERRORS:\n" + errors.join("\n") : "no console errors");
ws.close(); chrome.kill();

// UI smoke driver for the web app: boots headless Chrome, signs in through /dev-login, clicks through the
// forge / library / account / public pages and writes screenshots + any console errors. Needs a dev server:
//   BTSWEB_DEV_AUTH=1 BTSWEB_NO_DOTENV=1 BTSWEB_UNLIMITED_EMAILS=unlimited@example.com \
//     STRIPE_SECRET_KEY=sk_test_smoke PORT=5077 uv run --project ../generation python app.py
// (the dummy Stripe key only flips /api/billing to {enabled:true} so the donate tiers + custom-amount row
//  render; nothing in these scenarios ever hits Stripe)
// then, from web/tools:  node ui_smoke.mjs http://127.0.0.1:5077 <outdir> forge|library|account|pages
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
  const where = await json(`(() => { const i = document.getElementById('interactive'); return {
    in_card: document.getElementById('forge-input').contains(i),
    in_byok: document.getElementById('forge-byok').contains(i),
    in_token: document.getElementById('forge-token').contains(i)}; })()`);
  check(where.in_card && !where.in_byok && !where.in_token,
        "interactive checkbox is outside both payment boxes", JSON.stringify(where));
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
  // Both on-demand buttons must sit centred in their box, not stretched across it.
  const centred = await json(`(() => {
    const out = {};
    for (const [k, id] of [["estimate", "estimate-btn"], ["custom", "forge-donate-custom-open"]]) {
      const b = document.getElementById(id);
      if (!b) { out[k] = null; continue; }
      const r = b.getBoundingClientRect(), p = b.parentElement.getBoundingClientRect();
      out[k] = {off: Math.round((r.left - p.left) - (p.right - r.right)), w: Math.round(r.width),
                pw: Math.round(p.width)};
    }
    return out; })()`);
  check(centred.estimate && Math.abs(centred.estimate.off) <= 2 && centred.estimate.w < centred.estimate.pw - 40,
        "estimate button centred, not stretched", JSON.stringify(centred.estimate));
  await evaluate(`document.getElementById('estimate-btn').click()`);
  await shot("forge-byok");
  // The pre-go quote (2026-09-20): an art provider renders the three-line Text/Art/Total table plus the
  // OpenRouter comparison; a provider with no image API renders the text line and says so instead.
  const pickProvider = (id, model) => `(() => {
    const p = document.getElementById('provider'); p.value = ${JSON.stringify(id)};
    p.dispatchEvent(new Event('change'));
    const m = document.getElementById('model'); m.value = ${JSON.stringify(model)};
    m.dispatchEvent(new Event('input'));
    document.getElementById('estimate-btn').click();
    const box = document.getElementById('byok-estimate');
    return JSON.stringify({rows: [...box.querySelectorAll('pre')].map(e => e.textContent),
                           notes: [...box.querySelectorAll('.est-note')].map(e => e.textContent)});
  })()`;
  for (const [id, model, wantArt] of [["google", "gemini-2.5-flash-lite", true],
                                      ["xai", "grok-4.20-0309-non-reasoning", true],
                                      ["groq", "llama-3.3-70b-versatile", false]]) {
    const got = JSON.parse(await evaluate(pickProvider(id, model)));
    const table = (got.rows[0] || "");
    const labels = ["Text", "Art", "Total"].filter((l) => table.includes(l));
    const ok = wantArt ? labels.length === 3 && got.notes.some((n) => n.includes("OpenRouter key makes"))
                       : labels.join() === "Text" && got.notes.some((n) => n.includes("No generated art"));
    console.log(`${ok ? "OK  " : "FAIL"} estimate/${id}: [${labels}] ${JSON.stringify(got.notes).slice(0, 220)}`);
    if (!ok) errors.push(`estimate for ${id} did not render as expected`);
    if (id === "google") await shot("forge-byok-gemini-estimate");
  }
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
}
console.log(errors.length ? "CONSOLE ERRORS:\n" + errors.join("\n") : "no console errors");
ws.close(); chrome.kill();

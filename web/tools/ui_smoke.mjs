// UI smoke driver for the web app: boots headless Chrome, signs in through /dev-login, clicks through the
// forge / library / account / public pages and writes screenshots + any console errors. Needs a dev server:
//   BTSWEB_DEV_AUTH=1 BTSWEB_NO_DOTENV=1 BTSWEB_UNLIMITED_EMAILS=unlimited@example.com PORT=5077 \
//     uv run --project ../generation python app.py
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

await send("Page.enable"); await send("Runtime.enable"); await send("Log.enable");
await nav(`${base}/dev-login?email=unlimited@example.com`);

if (scenario === "forge") {
  await nav(`${base}/app`);
  await evaluate(`(async () => { document.querySelector('details.settings').open = true;
    document.querySelector('input[name=mode][value=byok]').click();
    const m = document.getElementById('model'); m.value = 'claude-sonnet-5'; m.dispatchEvent(new Event('input'));
    await new Promise(r => setTimeout(r, 300)); return document.getElementById('forge-btn').textContent + ' | ' + document.getElementById('byok-estimate').textContent; })()`).then(console.log);
  await shot("forge-byok");
  console.log(await evaluate(`(() => { const m = document.getElementById('model'); m.value = 'gpt-5'; m.dispatchEvent(new Event('input')); return document.getElementById('byok-estimate').textContent; })()`));
  // The pre-go quote (2026-09-20): an art provider renders the three-line Text/Art/Total table plus the
  // OpenRouter comparison; a provider with no image API renders the text line and says so instead.
  const pickProvider = (id, model) => `(() => {
    const p = document.getElementById('provider'); p.value = ${JSON.stringify(id)};
    p.dispatchEvent(new Event('change'));
    const m = document.getElementById('model'); m.value = ${JSON.stringify(model)};
    m.dispatchEvent(new Event('input'));
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
  console.log(await evaluate(`(() => { document.querySelector('input[name=mode][value=token]').click(); return document.getElementById('forge-btn').textContent; })()`));
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
  console.log(await evaluate(`JSON.stringify({balance: ME.token_balance, chip: document.getElementById('tokens').textContent, chooser_hidden: document.getElementById('chooser').classList.contains('hidden'), banner_hidden: document.getElementById('v3-banner').classList.contains('hidden'), head: document.getElementById('chooser-head')?.textContent, forge_btn: document.getElementById('forge-btn').textContent, status: document.getElementById('token-status').textContent})`));
  await shot("v3-chooser");
  await evaluate(`document.getElementById('choose-token').click()`); await sleep(1200);
  console.log(await evaluate(`JSON.stringify({pref: localStorage.getItem('bts_forge_pref'), strip: document.getElementById('chooser-strip')?.textContent, donate_open: document.getElementById('forge-donate').open, tiers: [...document.querySelectorAll('#forge-donate-tiers .donate-tier')].map(b => b.textContent.trim().replace(/\\s+/g,' '))})`));
  await shot("v3-inline-donate");
  await evaluate(`document.getElementById('choose-byok')?.click(); document.querySelector('input[name=mode][value=byok]').click()`); await sleep(500);
  console.log("after byok:", await evaluate(`JSON.stringify({pref: localStorage.getItem('bts_forge_pref'), strip: document.getElementById('chooser-strip')?.textContent, settings_open: document.getElementById('forge-settings').open})`));
  await evaluate(`document.getElementById('nav-account').click()`); await sleep(1500);
  console.log(await evaluate(`JSON.stringify({acct_tiers: document.querySelectorAll('#donate-tiers .donate-tier').length, custom_gone: !document.getElementById('donate-amount'), history: document.getElementById('purchases-empty').textContent})`));
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

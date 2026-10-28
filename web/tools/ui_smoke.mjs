// UI smoke driver for the web app: boots headless Chrome, signs in through /dev-login, clicks through the
// forge / library / account / public pages and writes screenshots + any console errors. Needs a dev server:
//   BTSWEB_DEV_AUTH=1 BTSWEB_NO_DOTENV=1 BTSWEB_UNLIMITED_EMAILS=unlimited@example.com \
//     STRIPE_SECRET_KEY=sk_test_smoke PORT=5077 uv run --project ../generation python app.py
// (the dummy Stripe key only flips /api/billing to {enabled:true} so the donate tiers + custom-amount row
//  render; nothing in these scenarios ever hits Stripe)
// then, from web/tools:  node ui_smoke.mjs http://127.0.0.1:5077 <outdir> forge|v3|byok-narrow|byok-models|library|account|pages|art|lost|archive|featured|webview|phone|events|lang
// (`archive` needs BTSWEB_ADMIN_EMAILS=unlimited@example.com and is best run first on a fresh DB: it puts a class
//  in The Archive through the UI, which is what `featured` then shows on the landing strip)
// (`lang` needs a web/static/i18n/zh.json with at least one translated landing string and one console.* rule)
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
const listeners = [];  // extra CDP event handlers a scenario registers (e.g. Fetch.requestPaused stubs)
ws.onmessage = (m) => {
  const msg = JSON.parse(m.data);
  for (const fn of listeners) fn(msg);
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
// Screenshot one element (page coordinates, so it works below the fold).
const shotEl = async (name, sel) => {
  const b = JSON.parse(await evaluate(`(() => { const e = document.querySelector(${JSON.stringify(sel)});
    e.scrollIntoView({block: 'start'}); const r = e.getBoundingClientRect();
    return JSON.stringify({x: r.left + scrollX, y: r.top + scrollY, w: r.width, h: r.height}); })()`));
  const r = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: true,
    clip: { x: b.x, y: b.y, width: Math.max(1, b.w), height: Math.max(1, b.h), scale: 1 } });
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
// The BYOK model fields are <select>s filled from the provider's own listing (2026-10-23). Scenarios that
// drive them by hand call this first: it turns the auto-load off (no real /api/models calls on smoke keys)
// and installs window.__pickModel(id, value), which adds the option as if the list had loaded.
const MANUAL_MODELS = `(() => { window.loadModels = async () => {};
  window.__pickModel = (id, v) => { const s = document.getElementById(id);
    if (s.tagName === 'SELECT' && v && ![...s.options].some(o => o.value === v)) s.add(new Option(v, v));
    s.disabled = false; s.value = v; }; })()`;

await send("Page.enable"); await send("Runtime.enable"); await send("Log.enable");
await nav(`${base}/dev-login?email=unlimited@example.com`);

if (scenario === "forge") {
  // 2026-10-26 forge-first screen (docs/plans/FORGE_FIRST_PLAN.md Phase A): the card is the concept textarea,
  // then #pay-step (HIDDEN until the first Forge click that can't pay; inside it the two <details> payment
  // boxes #forge-token / #forge-byok, mutually exclusive, unchanged), then the one #forge-btn, which is NEVER
  // disabled (except mid-forge). Sign in as a plain (non-unlimited) address so the 0-token path is real, on a
  // fresh browser profile so nothing is remembered.
  await nav(`${base}/dev-login?email=smoke-forge@example.com`);
  await nav(`${base}/app`);
  await evaluate(`localStorage.clear()`);
  await nav(`${base}/app`);
  await sleep(500);  // /api/billing (the tier buttons) lands after boot

  // (a) fresh account, no tokens, nothing remembered: the token box is the armed default (since 2026-10-12;
  // not written to bts_forge_pref), the pay step is hidden, the button is enabled and says plain "Forge the class".
  const fresh = await json(`({unlimited: !!ME.unlimited, balance: ME.token_balance,
    disabled: document.getElementById('forge-btn').disabled,
    label: document.getElementById('forge-btn').textContent,
    title: document.getElementById('forge-btn').title,
    byok_open: document.getElementById('forge-byok').open,
    token_open: document.getElementById('forge-token').open,
    pref: localStorage.getItem('bts_forge_pref'),
    step_hidden: document.getElementById('pay-step').classList.contains('hidden'),
    step_visible: document.getElementById('pay-step').offsetParent !== null,
    chooser: !!document.getElementById('chooser'),
    pay_open: document.getElementById('pay-open').offsetParent !== null && document.getElementById('pay-open').textContent,
    pay_lbl: document.querySelector('#pay-step .pay-lbl').textContent,
    key_hint: [...document.querySelectorAll('#forge-token > .hint')].map(p => p.textContent).join(' | '),
    token_first: !!(document.getElementById('forge-token').compareDocumentPosition(document.getElementById('forge-byok')) & Node.DOCUMENT_POSITION_FOLLOWING),
    step_above_btn: !!(document.getElementById('pay-step').compareDocumentPosition(document.getElementById('forge-btn')) & Node.DOCUMENT_POSITION_FOLLOWING),
    banner: document.getElementById('v3-banner').textContent.replace(/\\s+/g, ' ').trim(),
    balance_line: document.getElementById('token-balance-line').textContent})`);
  check(!fresh.unlimited && fresh.balance === 0 && fresh.disabled === false && fresh.token_open && !fresh.byok_open
        && fresh.label === "Forge the class" && fresh.title.includes("no tokens") && fresh.pref === null,
        "fresh 0-token account: Forge enabled, token box armed by default, no pref stored", JSON.stringify(fresh));
  check(fresh.step_hidden && !fresh.step_visible && !fresh.chooser && fresh.pay_open === "Change my tokens provider",
        "pay step hidden, no #chooser, 'Change my tokens provider' link under the button", JSON.stringify(fresh));
  check(fresh.pay_lbl.startsWith("Who provides your compute?") && fresh.token_first && fresh.step_above_btn
        && fresh.key_hint.includes("Have an API key? Forging with it is free — open “Bring your own key” below."),
        "inside the step: compute label, token box above the key box, key hint; step above the button", JSON.stringify(fresh));
  check(fresh.banner.includes("press Forge") && fresh.banner.includes("Full guide with screenshots"),
        "one-line tutorial under the button", JSON.stringify(fresh.banner));
  await shot("forge-first-screen", false);

  // Empty concept: a toast, no pay step.
  const empty = await json(`(() => { document.getElementById('concept').value = '';
    document.getElementById('forge-btn').click();
    return {toast: document.getElementById('toast').textContent,
            step_hidden: document.getElementById('pay-step').classList.contains('hidden')}; })()`);
  check(empty.toast === "Describe a class first." && empty.step_hidden, "empty concept: toast, step stays hidden", JSON.stringify(empty));

  // Text + Forge on 0 tokens: the step unfolds on the token box with the tiers open, the reason on top, focus on
  // the first tier button, and the Forge button still enabled.
  await evaluate(`(() => { const c = document.getElementById('concept'); c.value = 'a smoke-test lighthouse keeper who hoards light';
    document.getElementById('forge-btn').click(); })()`);
  await sleep(900);
  const rev = await json(`(() => { const step = document.getElementById('pay-step'), r = step.getBoundingClientRect();
    return {step_visible: !step.classList.contains('hidden') && step.offsetParent !== null,
      token_open: document.getElementById('forge-token').open, byok_open: document.getElementById('forge-byok').open,
      wrap_visible: document.getElementById('forge-donate-wrap').offsetParent !== null,
      tiers: document.querySelectorAll('#forge-donate-tiers .donate-tier').length,
      reason: document.getElementById('pay-reason').textContent,
      reason_visible: document.getElementById('pay-reason').offsetParent !== null,
      active_tier: !!document.activeElement && document.activeElement.classList.contains('donate-tier'),
      active: document.activeElement && (document.activeElement.id || document.activeElement.className),
      disabled: document.getElementById('forge-btn').disabled,
      step_top: Math.round(r.top), inner: window.innerHeight,
      pay_open_hidden: document.getElementById('pay-open').offsetParent === null,
      concept: document.getElementById('concept').value}; })()`);
  check(rev.step_visible && rev.token_open && !rev.byok_open && rev.wrap_visible && rev.tiers >= 3,
        "Forge on 0 tokens: pay step visible, token box open, tier buttons shown", JSON.stringify(rev));
  check(rev.reason === "Pick how to pay for this forge" && rev.reason_visible && rev.active_tier && rev.disabled === false,
        "reason line, focus on the first tier, Forge still enabled", JSON.stringify(rev));
  check(rev.step_top >= 0 && rev.step_top < rev.inner / 2 && rev.pay_open_hidden && rev.concept.includes("lighthouse"),
        "step scrolled into view near the top, opener link gone, concept intact", JSON.stringify(rev));
  await shot("forge-pay-step", false);
  // Pressing Forge again while unsatisfied repeats the reason as a toast.
  const again = await json(`(() => { document.getElementById('toast').textContent = '';
    document.getElementById('forge-btn').click();
    return {toast: document.getElementById('toast').textContent, disabled: document.getElementById('forge-btn').disabled}; })()`);
  check(again.toast === "Pick how to pay for this forge" && again.disabled === false, "second click: reason as a toast", JSON.stringify(again));
  // Opening the key box inside the step closes the token box and remembers the pick.
  await evaluate(`document.getElementById('forge-byok').open = true`); await sleep(300);
  const sw = await json(`({token_open: document.getElementById('forge-token').open, byok_open: document.getElementById('forge-byok').open,
    pref: localStorage.getItem('bts_forge_pref'), disabled: document.getElementById('forge-btn').disabled,
    step_visible: document.getElementById('pay-step').offsetParent !== null})`);
  check(!sw.token_open && sw.byok_open && sw.pref === "byok" && sw.disabled === false && sw.step_visible,
        "key box opened in the step: token box closed, pref byok, step stays", JSON.stringify(sw));
  // Forge with the key box open but no key: the reason changes and focus goes to the key field.
  const kr = await json(`(() => { document.getElementById('forge-btn').click();
    return {reason: document.getElementById('pay-reason').textContent, active: document.activeElement && document.activeElement.id}; })()`);
  check(kr.reason === "Enter your API key and pick a model" && kr.active === "api_key", "key box, no key: reason + focus on the key field", JSON.stringify(kr));

  // A saved key with no stored pref still lands on the key box (and still writes no pref); the step stays
  // hidden on load, and with a model picked the click goes straight to the confirm dialog (no unfold).
  await evaluate(`localStorage.clear(); localStorage.setItem('bts_byok', JSON.stringify({provider: 'anthropic', api_key: 'sk-ant-saved', model: 'claude-sonnet-4-6'}))`);
  await nav(`${base}/app`);
  const saved = await json(`({byok_open: document.getElementById('forge-byok').open,
    token_open: document.getElementById('forge-token').open, pref: localStorage.getItem('bts_forge_pref'),
    step_hidden: document.getElementById('pay-step').classList.contains('hidden')})`);
  check(saved.byok_open && !saved.token_open && saved.pref === null && saved.step_hidden,
        "saved key + no pref: key box armed by default, step hidden", JSON.stringify(saved));
  await evaluate(MANUAL_MODELS);
  const direct = await json(`(() => { __pickModel('model', 'claude-sonnet-4-6'); document.getElementById('model').dispatchEvent(new Event('input'));
    window.__confirmed = null; window.confirm = (m) => { window.__confirmed = m; return false; };
    document.getElementById('concept').value = 'a saved-key smoke class';
    document.getElementById('forge-btn').click();
    return {confirmed: window.__confirmed, label: document.getElementById('forge-btn').textContent,
            step_hidden: document.getElementById('pay-step').classList.contains('hidden')}; })()`);
  check(!!direct.confirmed && direct.confirmed.includes("bills your") && direct.step_hidden && direct.label.includes("uses your API key"),
        "saved key + model: Forge goes straight to the confirm dialog, step stays hidden", JSON.stringify(direct));
  // A stored "byok" pref (no saved key) still restores the key box.
  await evaluate(`localStorage.clear(); localStorage.setItem('bts_forge_pref', 'byok')`);
  await nav(`${base}/app`);
  const pb = await json(`({byok_open: document.getElementById('forge-byok').open,
    token_open: document.getElementById('forge-token').open, pref: localStorage.getItem('bts_forge_pref')})`);
  check(pb.byok_open && !pb.token_open && pb.pref === "byok", "stored byok pref restores the key box", JSON.stringify(pb));
  await evaluate(`localStorage.clear()`);
  await nav(`${base}/app`);
  await sleep(400);
  // The rest of this scenario drives the boxes directly: "Change my tokens provider" opens the step with no reason
  // line and no forge.
  const po = await json(`(() => { document.getElementById('pay-open').click();
    return {step_visible: document.getElementById('pay-step').offsetParent !== null,
      reason_hidden: document.getElementById('pay-reason').classList.contains('hidden'),
      progress_hidden: document.getElementById('progress').classList.contains('hidden')}; })()`);
  check(po.step_visible && po.reason_hidden && po.progress_hidden, "'Change my tokens provider' opens the step, no reason, no forge", JSON.stringify(po));

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
  await evaluate(MANUAL_MODELS);
  await evaluate(`document.getElementById('forge-byok').open = true`); await sleep(300);
  const keyed = await json(`(() => {
    const k = document.getElementById('api_key'); k.value = 'sk-ant-smoke'; k.dispatchEvent(new Event('input'));
    __pickModel('model', 'claude-sonnet-4-6'); document.getElementById('model').dispatchEvent(new Event('input'));
    return {disabled: document.getElementById('forge-btn').disabled,
            label: document.getElementById('forge-btn').textContent,
            token_open: document.getElementById('forge-token').open,
            pref: localStorage.getItem('bts_forge_pref')}; })()`);
  check(!keyed.disabled && keyed.label.includes("uses your API key") && !keyed.token_open && keyed.pref === "byok",
        "byok box open + key + model: button enabled, pick remembered", JSON.stringify(keyed));
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
    __pickModel('model', 'gpt-5'); document.getElementById('model').dispatchEvent(new Event('input'));
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
    __pickModel('model', ${JSON.stringify(model)});
    document.getElementById('model').dispatchEvent(new Event('input'));
    __pickModel('card_model', ${JSON.stringify(cardModel)});
    document.getElementById('card_model').dispatchEvent(new Event('input'));
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
  // (c) opening the token box closes the key box; with no tokens the button stays ENABLED (2026-10-26: a click
  // would unfold the pay step) with plain "Forge the class", and the custom-amount row prices a typed $25 live.
  await evaluate(`document.getElementById('forge-token').open = true`); await sleep(400);
  const tok = await json(`({byok_open: document.getElementById('forge-byok').open,
    disabled: document.getElementById('forge-btn').disabled,
    label: document.getElementById('forge-btn').textContent,
    title: document.getElementById('forge-btn').title,
    balance_line: document.getElementById('token-balance-line').textContent,
    tiers: [...document.querySelectorAll('#forge-donate-tiers .donate-tier')].map(b => b.textContent.replace(/\\s+/g, ' ').trim()),
    custom_hidden: document.getElementById('forge-donate-custom').classList.contains('hidden')})`);
  check(!tok.byok_open && tok.disabled === false && tok.label === "Forge the class"
        && tok.title.includes("no tokens"),
        "token box open with 0 tokens: byok closed, button enabled with plain label", JSON.stringify(tok));
  // "Get a forge token" (2026-09-26, renamed 2026-10-26): with 0 tokens the tiers are already unfolded; with tokens in hand they fold
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
  check(gt.zero.shown && gt.zero.label === "Hide token options" && !gt.some.shown && gt.some.label === "Get a forge token"
        && gt.clicked.shown, "tier buttons fold behind 'Get a forge token' when the account has tokens", JSON.stringify(gt));
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
  await evaluate(MANUAL_MODELS);
  await evaluate(`(() => { document.getElementById('forge-byok').open = true;
    const p = document.getElementById('provider'); p.value = 'openrouter'; p.dispatchEvent(new Event('change'));
    const k = document.getElementById('api_key'); k.value = 'sk-or-smoke'; k.dispatchEvent(new Event('input'));
    __pickModel('model', 'anthropic/claude-sonnet-4.6'); __pickModel('card_model', 'openai/gpt-4o');
    document.getElementById('estimate-btn').click(); })()`);
  await sleep(300);
  const narrow = await json(`({scrollW: document.documentElement.scrollWidth, w: window.innerWidth,
    stacked: document.getElementById('card_model').getBoundingClientRect().top
             > document.getElementById('model').getBoundingClientRect().bottom})`);
  check(narrow.scrollW <= narrow.w && narrow.stacked, "byok box stacks at 390px with no sideways scroll",
        JSON.stringify(narrow));
  await evaluate(`document.getElementById('forge-byok').scrollIntoView()`);
  await shot("byok-narrow");
} else if (scenario === "byok-models") {
  // 2026-10-23: the model fields are selects filled from the provider's own listing. /api/models is
  // stubbed in the page (window.fetch, installed before app.js on every load): "nolist" URLs 404 like an
  // endpoint without /models, everything else returns two models, one of them tested.
  await send("Page.addScriptToEvaluateOnNewDocument", { source: `(() => {
    const real = window.fetch.bind(window);
    window.__modelCalls = 0;
    window.fetch = (u, o) => {
      if (String(u).includes('/api/models')) {
        window.__modelCalls++;
        const body = JSON.parse((o && o.body) || '{}');
        const r = (body.base_url || '').includes('nolist')
          ? new Response(JSON.stringify({error: 'endpoint returned HTTP 404 — check the key, URL, and model access.'}), {status: 400, headers: {'Content-Type': 'application/json'}})
          : new Response(JSON.stringify({models: ['gpt-6.1-sol', 'gpt-5.6-sol'], recommended: ['gpt-6.1-sol'], hidden: 3}), {status: 200, headers: {'Content-Type': 'application/json'}});
        return Promise.resolve(r);
      }
      return real(u, o);
    };
  })()` });
  await nav(`${base}/dev-login?email=smoke-models@example.com`);
  await nav(`${base}/app`);
  await evaluate(`localStorage.clear()`);
  await nav(`${base}/app`);
  const state = `(() => { const m = document.getElementById('model'), c = document.getElementById('card_model');
    const groups = (s) => s.tagName === 'SELECT' ? [...s.querySelectorAll('optgroup')].map(g => g.label + ':' + g.children.length) : null;
    return {tag: m.tagName, disabled: m.disabled, value: m.value, card_value: c.value, card_disabled: c.disabled,
      options: m.tagName === 'SELECT' ? [...m.options].map(o => o.value + '=' + o.textContent) : null,
      card_options: c.tagName === 'SELECT' ? [...c.options].map(o => o.value + '=' + o.textContent) : null,
      groups: groups(m), card_groups: groups(c),
      load: document.getElementById('load-models').textContent,
      load_shown: document.getElementById('load-models').style.display !== 'none',
      btn_disabled: document.getElementById('forge-btn').disabled, calls: window.__modelCalls,
      toast: document.getElementById('toast').textContent,
      saved: JSON.parse(localStorage.getItem('bts_byok') || '{}')}; })()`;

  // (a) OpenAI, no key yet: both pickers disabled on their placeholders, nothing fetched.
  await evaluate(`(() => { document.getElementById('forge-byok').open = true;
    const p = document.getElementById('provider'); p.value = 'openai'; p.dispatchEvent(new Event('change')); })()`);
  await sleep(600);
  const pre = await json(state);
  check(pre.tag === "SELECT" && pre.disabled && pre.options.join() === "=Enter your key, then load models"
        && pre.card_disabled && pre.card_options.join() === "=Same as design" && pre.calls === 0
        && pre.load_shown && pre.load === "Load my model list" && pre.btn_disabled,
        "openai before a key: pickers disabled on their placeholders, no listing fetched", JSON.stringify(pre));
  // The submit guard refuses a forge with no model picked.
  await evaluate(`(() => { document.getElementById('concept').value = 'a smoke test class'; forge(); })()`);
  await sleep(200);
  check((await evaluate(`document.getElementById('toast').textContent`)) === "Load your model list and pick a model first.",
        "forge() refuses while the picker is on its placeholder");

  // (b) typing a key (input + the blur's change) auto-loads the list: Tested group first, tested model picked.
  await evaluate(`(() => { const k = document.getElementById('api_key'); k.value = 'sk-smoke-openai';
    k.dispatchEvent(new Event('input')); k.dispatchEvent(new Event('change')); })()`);
  await sleep(900);
  const loaded = await json(state);
  check(loaded.tag === "SELECT" && !loaded.disabled && loaded.value === "gpt-6.1-sol" && loaded.calls === 1
        && loaded.groups.join() === "Tested:1,All models:1" && loaded.card_groups.join() === "Tested:1,All models:1"
        && !loaded.card_disabled && loaded.card_value === "" && loaded.load === "Reload model list"
        && !loaded.btn_disabled && loaded.saved.model === "gpt-6.1-sol" && loaded.saved.card_model === "",
        "key entered: list auto-loaded, two optgroups, gpt-6.1-sol selected, card = same as design", JSON.stringify(loaded));
  await evaluate(`document.getElementById('forge-byok').scrollIntoView()`);
  await shot("byok-models-loaded", false);
  // Same URL + key again: no second request.
  await evaluate(`document.getElementById('api_key').dispatchEvent(new Event('change'))`); await sleep(900);
  check((await evaluate(`window.__modelCalls`)) === 1, "the same URL + key is not listed twice");
  // A pick sticks and is saved.
  await evaluate(`(() => { const c = document.getElementById('card_model'); c.value = 'gpt-5.6-sol'; c.dispatchEvent(new Event('change')); })()`);
  check((await json(state)).saved.card_model === "gpt-5.6-sol", "a card-model pick is saved");

  // (c) a saved model the key no longer offers: the tested model is picked instead, with a toast.
  await evaluate(`localStorage.setItem('bts_byok', JSON.stringify({provider: 'openai', api_key: 'sk-smoke-openai', model: 'gpt-4o', card_model: 'gpt-5.6-sol'}));
    localStorage.setItem('bts_forge_pref', 'byok')`);
  await nav(`${base}/app`); await sleep(900);
  const stale = await json(state);
  check(stale.value === "gpt-6.1-sol" && stale.card_value === "gpt-5.6-sol" && stale.calls === 1
        && stale.toast === "Your saved model “gpt-4o” isn't offered on this key any more — pick another.",
        "reload with a stale saved model: list auto-loads, saved card model kept, stale design model toasted", JSON.stringify(stale));

  // (d) Anthropic: no listing — the static list, enabled at once, no load button.
  await evaluate(`(() => { const p = document.getElementById('provider'); p.value = 'anthropic'; p.dispatchEvent(new Event('change')); })()`);
  await sleep(600);
  const ant = await json(state);
  check(!ant.disabled && ant.options.join() === "claude-sonnet-5=claude-sonnet-5,claude-opus-5-5=claude-opus-5-5"
        && ant.value === "claude-sonnet-5" && !ant.load_shown && ant.calls === 1,
        "anthropic: static models, enabled, no load button, nothing fetched", JSON.stringify(ant));

  // (e) Other, on an endpoint without /models: falls back to typed ids, and the forge button follows them.
  await evaluate(`(() => { const p = document.getElementById('provider'); p.value = 'custom'; p.dispatchEvent(new Event('change'));
    const u = document.getElementById('base_url'); u.value = 'https://nolist.example.com/v1';
    u.dispatchEvent(new Event('input')); u.dispatchEvent(new Event('change')); })()`);
  await sleep(900);
  const custom = await json(state);
  check(custom.tag === "INPUT" && custom.calls === 2 && custom.toast.startsWith("Couldn't list models on this endpoint")
        && custom.btn_disabled, "custom without /models: typed-id fallback + toast", JSON.stringify(custom));
  await evaluate(`(() => { const m = document.getElementById('model'); m.value = 'my-local-model';
    m.dispatchEvent(new Event('input')); m.dispatchEvent(new Event('change')); })()`);
  const typed = await json(state);
  check(!typed.btn_disabled && typed.saved.model === "my-local-model", "a typed custom model enables the forge button",
        JSON.stringify(typed));
  await shot("byok-models-custom-fallback", false);
  // ...and an endpoint that does list models swaps the selects back in.
  await evaluate(`(() => { const u = document.getElementById('base_url'); u.value = 'https://lists.example.com/v1';
    u.dispatchEvent(new Event('change')); })()`);
  await sleep(900);
  const back = await json(state);
  check(back.tag === "SELECT" && !back.disabled && back.calls === 3 && back.value === "gpt-6.1-sol",
        "custom endpoint with /models: selects come back", JSON.stringify(back));
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
  // Share link copies a blurb + the URL (2026-10-26, FORGE_FIRST_PLAN.md 5.5): copy() is stubbed to capture it.
  const blurb = /^".+"( — .+)?\. Play it: https?:\/\/\S+\/deck\/[A-Za-z0-9_-]{20,}$/;
  const rowShare = await evaluate(`(() => { window.__copied = null; window.copy = async (t) => { window.__copied = t; };
    document.querySelector('#lib-list [data-act=share]').click(); return window.__copied; })()`);
  check(blurb.test(rowShare || ""), "library row share copies a blurb + link", JSON.stringify(rowShare));
  await evaluate(`document.querySelector('[data-act=open]').click()`); await sleep(1000);
  const barShare = await evaluate(`(() => { window.__copied = null; document.getElementById('share-link').click(); return window.__copied; })()`);
  check(blurb.test(barShare || ""), "result bar share copies a blurb + link", JSON.stringify(barShare));
  const play = await json(`(() => { const p = document.querySelector('#result .play-how');
    return {visible: !!p && p.offsetParent !== null, title: p && p.querySelector('.play-title').textContent,
      steps: p ? p.querySelectorAll('ol.play-steps li').length : 0, workshop: !!(p && p.querySelector('a[href="/workshop"]')),
      after_copy: !!(document.getElementById('copy-code').compareDocumentPosition(p) & Node.DOCUMENT_POSITION_FOLLOWING)}; })()`);
  check(play.visible && play.title === "Play it" && play.steps === 3 && play.workshop && play.after_copy,
        "result: 'Play it' block under the code with the Workshop link", JSON.stringify(play));
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
  // Pricing v3 on the forge-first screen (2026-10-26, FORGE_FIRST_PLAN.md): a fresh (0-token, non-unlimited)
  // account sees the concept box, the enabled Forge button and the one-line tutorial; the pay step is hidden
  // until "Change my tokens provider" (or a Forge click) opens it on the token box with the inline tiers; the
  // Account tab shows the same tiers under "Get a forge token"; public pages.
  await nav(`${base}/dev-login?email=newbie@example.com`);
  await nav(`${base}/app`); await sleep(1200);
  const v0 = await json(`({balance: ME.token_balance, chip: document.getElementById('tokens').textContent,
    chip_title: document.getElementById('tokens').title, chooser: !!document.getElementById('chooser'),
    step_hidden: document.getElementById('pay-step').classList.contains('hidden'),
    banner_hidden: document.getElementById('v3-banner').classList.contains('hidden'),
    banner: document.getElementById('v3-banner').textContent.replace(/\\s+/g, ' ').trim(),
    forge_btn: document.getElementById('forge-btn').textContent, disabled: document.getElementById('forge-btn').disabled,
    balance_line: document.getElementById('token-balance-line').textContent})`);
  check(v0.balance === 0 && !v0.chooser && v0.step_hidden && !v0.banner_hidden && v0.banner.includes("press Forge")
        && v0.forge_btn === "Forge the class" && v0.disabled === false && v0.chip_title.includes("Press Forge to get one"),
        "fresh account: no chooser, step hidden, one-line banner, Forge enabled", JSON.stringify(v0));
  await shot("v3-forge-first");
  await evaluate(`document.getElementById('pay-open').click()`); await sleep(1200);
  const v1 = await json(`({pref: localStorage.getItem('bts_forge_pref'), token_open: document.getElementById('forge-token').open,
    step_visible: document.getElementById('pay-step').offsetParent !== null,
    get_btn: document.getElementById('forge-get-tokens').textContent,
    tiers: [...document.querySelectorAll('#forge-donate-tiers .donate-tier')].map(b => b.textContent.trim().replace(/\\s+/g,' '))})`);
  check(v1.step_visible && v1.token_open && v1.tiers.length >= 3 && v1.get_btn === "Hide token options" && v1.pref === null,
        "'Change my tokens provider': token box open with the inline tiers", JSON.stringify(v1));
  await shot("v3-inline-donate");
  await evaluate(`document.getElementById('forge-byok').open = true`); await sleep(500);
  const v2 = await json(`({pref: localStorage.getItem('bts_forge_pref'), byok_open: document.getElementById('forge-byok').open,
    token_open: document.getElementById('forge-token').open})`);
  check(v2.pref === "byok" && v2.byok_open && !v2.token_open, "opening the key box switches the pick", JSON.stringify(v2));
  await evaluate(`document.getElementById('forge-token').open = true`); await sleep(500);
  check(await evaluate(`localStorage.getItem('bts_forge_pref') === 'token' && !document.getElementById('forge-byok').open`),
        "and back to the token box");
  await evaluate(`document.getElementById('nav-account').click()`); await sleep(1500);
  const acct = await json(`({acct_tiers: document.querySelectorAll('#donate-tiers .donate-tier').length,
    custom_reveal: document.getElementById('donate-custom-open')?.textContent,
    heading: [...document.querySelectorAll('#view-account h2')].map(h => h.textContent),
    history: document.getElementById('purchases-empty').textContent})`);
  check(acct.acct_tiers >= 3 && acct.heading.includes("Get a forge token") && !acct.heading.some((h) => /support/i.test(h)),
        "Account tab: tiers under 'Get a forge token'", JSON.stringify(acct));
  await shot("v3-account");
  await evaluate(`document.getElementById('nav-forge').click()`); await sleep(300);
  const back = await evaluate(`document.getElementById('pay-step').offsetParent !== null`);
  check(back, "back on the forge tab the pay step stays open for the visit");
  await evaluate(`document.getElementById('v3-banner-x').click()`); await sleep(300);
  const dism = await evaluate(`document.getElementById('v3-banner').classList.contains('hidden') + ' ' + localStorage.getItem('bts_tutorial_banner_dismissed')`);
  check(dism === "true 1", "banner dismissed and remembered", dism);
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
} else if (scenario === "archive") {
  // 2026-10-26 The Archive (docs/plans/FORGE_FIRST_PLAN.md Phase B): an owner nominates a class from the result
  // bar (and withdraws one from My Classes), the operator features it from the Account tab's "Archive
  // nominations" card, and it shows on /archive and as "from The Archive" on its /deck page. window.prompt is
  // stubbed for the note and the five-letter word. Needs BTSWEB_ADMIN_EMAILS=unlimited@example.com.
  const OWNER = "smoke-archive@example.com";
  await nav(`${base}/dev-login?email=${OWNER}`);
  await nav(`${base}/app`);
  const seeded = JSON.parse(await evaluate(`(async () => {
    for (const concept of ['a goose knight who honks at the spire', 'a moose monk with antler wards']) {
      await (await fetch('/api/forge-class', {method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({concept, mode: 'fake'})})).text();
    }
    return (await (await fetch('/api/classes')).json()).classes.slice(0, 2); })().then(JSON.stringify)`));
  check(seeded.length === 2 && seeded.every((c) => c.id && c.slug && c.nominated === false && c.featured === false),
        "two fake classes, neither nominated nor featured", JSON.stringify(seeded.map((c) => [c.id, c.name, c.nominated, c.featured])));
  const [target, other] = seeded;   // newest first: target = the moose monk, other = the goose knight

  // (a) result bar: open the class, nominate it with a note
  await evaluate(`document.getElementById('nav-library').click()`); await sleep(800);
  await evaluate(`document.querySelector('#lib-list .lib-row [data-act=open]').click()`); await sleep(1200);
  const bar0 = await json(`(() => { const b = document.getElementById('nominate');
    return {visible: b.offsetParent !== null, text: b.textContent, disabled: b.disabled,
      next_to_share: b.previousElementSibling && b.previousElementSibling.id === 'share-link'}; })()`);
  check(bar0.visible && bar0.text === "☆ Nominate for The Archive" && !bar0.disabled && bar0.next_to_share,
        "result bar: '☆ Nominate for The Archive' next to the share button", JSON.stringify(bar0));
  await evaluate(`window.prompt = () => 'great class'; document.getElementById('nominate').click()`); await sleep(900);
  const bar1 = await json(`({text: document.getElementById('nominate').textContent, toast: document.getElementById('toast').textContent})`);
  check(bar1.text === "★ Nominated · withdraw" && bar1.toast === "Nominated — you'll see it in The Archive if it's picked.",
        "nominated from the result bar: button flips, toast", JSON.stringify(bar1));
  await shotEl("archive-nominate-result", "#view-bar");

  // (b) My Classes rows carry the same control; the other class: nominate then withdraw from its row
  await evaluate(`document.getElementById('nav-library').click()`); await sleep(900);
  const rows0 = await json(`[...document.querySelectorAll('#lib-list .lib-row')].map((li) => ({
    name: li.querySelector('.lr-name').textContent, nom: li.querySelector('[data-act=nominate]').textContent}))`);
  check(rows0.length >= 2 && rows0[0].nom === "★ Nominated · withdraw" && rows0[1].nom === "☆ Nominate for The Archive",
        "library rows: nominated / not-nominated states", JSON.stringify(rows0));
  await evaluate(`document.querySelectorAll('#lib-list .lib-row')[1].querySelector('[data-act=nominate]').click()`); await sleep(800);
  const rowNom = await evaluate(`document.querySelectorAll('#lib-list .lib-row')[1].querySelector('[data-act=nominate]').textContent`);
  await evaluate(`document.querySelectorAll('#lib-list .lib-row')[1].querySelector('[data-act=nominate]').click()`); await sleep(800);
  const rowW = await json(`({text: document.querySelectorAll('#lib-list .lib-row')[1].querySelector('[data-act=nominate]').textContent,
    toast: document.getElementById('toast').textContent})`);
  check(rowNom === "★ Nominated · withdraw" && rowW.text === "☆ Nominate for The Archive" && rowW.toast === "Nomination withdrawn.",
        "library row: nominate then withdraw", JSON.stringify({rowNom, rowW}));
  await shot("archive-library", false);

  // (c) the operator's queue
  await nav(`${base}/dev-login?email=unlimited@example.com`);
  await nav(`${base}/app`); await evaluate(`document.getElementById('nav-account').click()`); await sleep(1800);
  const q0 = await json(`(() => { const card = document.getElementById('admin-archive');
    const row = document.querySelector('#admin-nominations tr[data-cid="${target.id}"]');
    return {visible: card.offsetParent !== null, heading: card.querySelector('h2').textContent,
      pending: document.querySelectorAll('#admin-nominations tr[data-cid]').length,
      other_pending: !!document.querySelector('#admin-nominations tr[data-cid="${other.id}"]'),
      row: row ? row.innerText.replace(/\\s+/g, ' ') : null,
      link: row ? row.querySelector('a')?.getAttribute('href') : null,
      target: row ? row.querySelector('a')?.getAttribute('target') : null}; })()`);
  check(q0.visible && q0.heading === "Archive nominations" && q0.row && q0.row.includes("great class")
        && q0.row.includes(OWNER) && q0.link === `/deck/${target.slug}` && q0.target === "_blank" && !q0.other_pending,
        "admin card: the nomination is pending with its note, owner and deck link; the withdrawn one is not", JSON.stringify(q0));
  const tiles0 = await evaluate(`[...document.querySelectorAll('#stats-tiles .stat-tile')].map((t) => t.querySelector('.k').textContent + '=' + t.querySelector('.v').textContent).join(' | ')`);
  check(/Nominations pending=\d+/.test(tiles0) && /In The Archive=\d+/.test(tiles0), "forge stats: Archive tiles", tiles0);
  await shotEl("archive-admin-pending", "#admin-archive");

  // Feature it as GOOSE
  await evaluate(`window.prompt = () => 'GOOSE';
    document.querySelector('#admin-nominations tr[data-cid="${target.id}"] [data-act=feature]').click()`); await sleep(1500);
  const q1 = await json(`(() => { const f = document.querySelector('#admin-featured tr[data-cid="${target.id}"]');
    return {still_pending: !!document.querySelector('#admin-nominations tr[data-cid="${target.id}"]'),
      featured_row: f ? f.innerText.replace(/\\s+/g, ' ') : null,
      note: document.getElementById('admin-archive-note').textContent,
      log: document.getElementById('admin-actions').firstElementChild?.innerText || ''}; })()`);
  check(!q1.still_pending && q1.featured_row && q1.featured_row.includes("GOOSE") && q1.note.includes("GOOSE"),
        "Feature moves the row to 'In The Archive' with its word", JSON.stringify(q1));
  check(/featured class #\d+ .*GOOSE/.test(q1.log) && q1.log.includes(OWNER), "audit trail shows the feature", q1.log);
  await shotEl("archive-admin-featured", "#admin-archive");

  // (d) /archive, desktop then phone
  await nav(`${base}/archive`); await sleep(1500);
  const api = JSON.parse(await evaluate(`fetch('/api/featured').then((r) => r.json()).then((d) => JSON.stringify(d.featured.map((f) => f.word)))`));
  const page = await json(`(() => { const tiles = [...document.querySelectorAll('#archive-grid .featured-tile')];
    return {title: document.title, h1: document.querySelector('h1').textContent, tiles: tiles.length,
      words: tiles.map((t) => t.querySelector('.featured-word').textContent),
      hrefs: tiles.map((t) => t.getAttribute('href')),
      empty_hidden: document.getElementById('archive-empty').classList.contains('hidden'),
      nav: [...document.querySelectorAll('header nav a')].map((a) => a.textContent.trim())}; })()`);
  check(page.title === "The Archive — BLANK the spire" && page.h1 === "The Archive" && page.tiles >= 1
        && page.words[0] === "GOOSE" && page.hrefs[0] === `/deck/${target.slug}` && page.tiles === api.length && page.empty_hidden,
        "/archive: newest tile is GOOSE, one tile per featured class", JSON.stringify(page));
  console.log("archive tiles:", page.tiles, JSON.stringify(page.words));
  check(page.nav.join("|") === "Forge your own →|Get the mod ⬇|Help", "/archive header nav", JSON.stringify(page.nav));
  await shot("archive-desktop");
  await send("Emulation.setDeviceMetricsOverride", { width: 390, height: 844, deviceScaleFactor: 2, mobile: true });
  await nav(`${base}/archive`); await sleep(1500);
  const phone = await json(`(() => { const tiles = [...document.querySelectorAll('#archive-grid .featured-tile')];
    const g = document.getElementById('archive-grid').getBoundingClientRect();
    return {overflow: document.documentElement.scrollWidth > innerWidth, gutter: Math.round(g.left),
      lefts: tiles.map((t) => Math.round(t.getBoundingClientRect().left)),
      widths: tiles.map((t) => Math.round(t.getBoundingClientRect().width))}; })()`);
  check(!phone.overflow && phone.gutter === 16 && phone.lefts.every((l) => l === 16), "/archive at 390: one column, 16px gutters, no sideways scroll", JSON.stringify(phone));
  await shot("archive-phone");
  await send("Emulation.clearDeviceMetricsOverride"); await sleep(300);

  // (e) its /deck page now speaks as The Archive
  await nav(`${base}/deck/${target.slug}`); await sleep(1500);
  const deck = await json(`({lede: document.getElementById('lede').textContent.trim(), sub: document.querySelector('header .sub').textContent.trim(),
    tab: !!document.querySelector('header nav a[href="/archive"]') && document.querySelector('header nav a[href="/archive"]').offsetParent !== null})`);
  check(deck.lede.includes("from The Archive") && deck.sub === "from The Archive" && deck.tab,
        "deck page: 'A class from The Archive' lede + header, The Archive tab", JSON.stringify(deck));

  // (f) the owner now sees "★ In The Archive", disabled
  await nav(`${base}/dev-login?email=${OWNER}`);
  await nav(`${base}/app`); await evaluate(`document.getElementById('nav-library').click()`); await sleep(900);
  const own = await json(`(() => { const b = document.querySelectorAll('#lib-list .lib-row')[0].querySelector('[data-act=nominate]');
    return {text: b.textContent, disabled: b.disabled, title: b.title}; })()`);
  check(own.text === "★ In The Archive" && own.disabled && own.title === "Picked for The Archive",
        "owner's row: '★ In The Archive', disabled", JSON.stringify(own));
} else if (scenario === "featured") {
  // 2026-10-05: the landing's featured strip (/api/featured), the deck page's featured mode + "Forge your own
  // twist" prefill, and the sign-in page's no-account escape hatch. Since 2026-10-26 the strip is "The Archive"
  // (the newest four, ?limit=4) and the list lives in the DB: run `archive` first (or boot a DB whose classes
  // featured.json names) so there is something to show. The harness's own sign-in is undone first because the
  // strip is for strangers.
  await send("Network.clearBrowserCookies");
  await nav(`${base}/`); await sleep(2500);
  const hero = await json(`({primary: document.getElementById('signin')?.textContent.trim(), href: document.getElementById('signin')?.getAttribute('href'),
    buttons: document.querySelectorAll('.splash-actions .btn').length,
    og: document.querySelector('meta[property="og:image"]')?.content})`);
  // landing.js repoints the primary button at /dev-login on a dev-auth server (and /app when signed in).
  // One button only (2026-10-05): the strip sits right below, so a "Try a featured class" button was redundant.
  check(hero.primary === "Create Your Own Class" && /^\/(login|dev-login)/.test(hero.href || "") && hero.buttons === 1,
        "hero: single primary CTA", JSON.stringify(hero));
  check(/\/static\/img\/og-landing\.png$/.test(hero.og || ""), "landing og:image", hero.og);
  const strip = await json(`(() => { const s = document.getElementById('featured'); const tiles = [...document.querySelectorAll('#featured-grid .featured-tile')];
    return {hidden: s.classList.contains('hidden'), tiles: tiles.length, hrefs: tiles.map(t => t.getAttribute('href')),
      words: tiles.map(t => t.querySelector('.featured-word')?.textContent),
      heading: s.querySelector('h2')?.textContent, sub: s.querySelector('.how-sub')?.textContent,
      more: s.querySelector('.featured-more a')?.getAttribute('href'), more_text: s.querySelector('.featured-more a')?.textContent,
      // a tile with art must have loaded it; a tile without art shows the word placeholder instead
      imgs: tiles.map(t => { const i = t.querySelector('img'); return i ? (i.complete && i.naturalWidth > 0) : !!t.querySelector('.featured-ph'); }),
      with_art: tiles.filter(t => t.querySelector('img')).length}; })()`);
  check(!strip.hidden && strip.tiles > 0 && strip.tiles <= 4 && strip.hrefs.every((h) => /^\/deck\/[A-Za-z0-9_-]{20,}$/.test(h)),
        "Archive strip rendered (at most 4) with deck links", JSON.stringify(strip));
  check(strip.heading === "The Archive" && strip.sub === "Classes other players forged. Play one now — no account needed."
        && strip.more === "/archive" && strip.more_text === "Browse The Archive →",
        "strip heading, sub-line and 'Browse The Archive' link", JSON.stringify(strip));
  check(strip.imgs.length > 0 && strip.imgs.every(Boolean), "tile art loaded (or the placeholder where a class has none)",
        JSON.stringify({imgs: strip.imgs, with_art: strip.with_art}));
  await shot("featured-landing");

  // hovering a tile flips the split-flap board to its word
  await evaluate(`document.querySelector('#featured-grid .featured-tile').dispatchEvent(new PointerEvent('pointerenter'))`);
  await sleep(4500);
  const board = await evaluate(`[...document.querySelectorAll('#board .flap')].map((f) => f.textContent).join('')`);
  check(board === strip.words[0], "board flips to the hovered word", board + " vs " + strip.words[0]);

  await send("Emulation.setDeviceMetricsOverride", { width: 390, height: 844, deviceScaleFactor: 2, mobile: true });
  await sleep(600); await shot("featured-landing-phone");
  await send("Emulation.clearDeviceMetricsOverride"); await sleep(300);

  // the deck page in featured mode: lede + header swap, The Archive tab, code above the cards, checklist
  await nav(`${base}${strip.hrefs[0]}`); await sleep(1500);
  const deck = await json(`({lede: document.getElementById('lede')?.textContent.trim(), sub: document.querySelector('header .sub')?.textContent.trim(),
    more: !!document.querySelector('header nav a[href="/archive"]'), remix: !!document.getElementById('remix'),
    code_first: !!(document.getElementById('r-code').compareDocumentPosition(document.getElementById('r-cards')) & Node.DOCUMENT_POSITION_FOLLOWING),
    cards: document.querySelectorAll('#r-cards .cardchip').length, steps: document.querySelectorAll('.play-steps li').length})`);
  check(deck.lede.startsWith("A class from The Archive") && deck.sub === "from The Archive" && deck.more, "deck page featured mode", JSON.stringify(deck));
  check(deck.remix && deck.code_first && deck.cards > 0 && deck.steps === 3, "deck page: code above cards, remix + checklist", JSON.stringify(deck));
  await shot("featured-deck");

  // "Forge your own twist" → /login (signed out) with the prefill stashed; the sign-in page shows the escape hatch
  await evaluate(`document.getElementById('remix').click()`); await sleep(1500);
  const login = await json(`({path: location.pathname, hatch: !document.getElementById('try-instead')?.classList.contains('hidden'),
    prefill: localStorage.getItem('bts_prefill')})`);
  check(login.path === "/login" && login.hatch && !!login.prefill, "remix lands on /login with the prefill stashed + escape hatch", JSON.stringify(login));
  await shot("featured-login");

  // sign in: the concept box is seeded once and the key is cleared
  await nav(`${base}/dev-login?email=unlimited@example.com`); await sleep(2500);
  const app = await json(`({path: location.pathname, concept: document.getElementById('concept').value,
    hint: document.getElementById('concept').nextElementSibling?.textContent, left: localStorage.getItem('bts_prefill')})`);
  check(app.path === "/app" && app.concept.length > 0 && /Remixing/.test(app.hint || "") && app.left === null,
        "remix prefill applied once in the app", JSON.stringify(app));
  await shot("featured-remix-app", false);

  // a class that is NOT featured keeps the plain share-page copy
  const plain = await evaluate(`fetch('/api/classes').then((r) => r.json()).then((d) =>
    d.classes.map((c) => c.slug).find((s) => !${JSON.stringify(strip.hrefs)}.some((h) => h.endsWith(s))) || '')`);
  if (plain) {
    await nav(`${base}/deck/${plain}`); await sleep(1200);
    const p = await json(`({lede: document.getElementById('lede')?.textContent.trim(), sub: document.querySelector('header .sub')?.textContent.trim(),
      tab: !!document.querySelector('header nav a[href="/archive"]')})`);
    check(p.lede.startsWith("Someone forged") && p.sub === "a forged class" && p.tab,
          "non-featured deck keeps the plain lede (The Archive tab is always there)", JSON.stringify(p));
  } else {
    console.log("skip: no non-featured class in this DB");
  }
} else if (scenario === "webview") {
  // 2026-10-13 (docs/plans/PHONE_FUNNEL_PLAN.md phases 1 + 3): inside an in-app browser (no `Safari/` token
  // on iOS, `; wv)` on Android) /login drops Google (it 403s embedded webviews), puts the email form first and
  // offers an Open-in-Safari/Chrome hand-off; a real browser keeps the old order. The dev server has no OAuth
  // credentials, so /api/me is stubbed to report google + github + email; /api/featured is stubbed too so the
  // phone hero order (featured strip above the CTA) has tiles to show. Signed out: the top-level dev-login is
  // undone by clearing cookies.
  const IOS_WEBVIEW = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148";
  const IOS_SAFARI = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1";
  const ANDROID_WEBVIEW = "Mozilla/5.0 (Linux; Android 14; Pixel 8 Build/AP2A; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/129.0.6668.100 Mobile Safari/537.36";
  await send("Network.enable"); await send("Network.clearBrowserCookies");
  const stubs = {
    "/api/me": { user: null, dev_auth: false, providers: ["google", "github"], email_login: true },
    "/api/featured": { featured: [
      { word: "CRAVE", name: "The Glutton", share_url: "/deck/smokeAAAAAAAAAAAAAAAAAAAA", card_count: 75,
        description: "Eats cards to grow stronger; every meal is a gamble on what the next draw brings." },
      { word: "GOOSE", name: "Honk Knight", share_url: "/deck/smokeBBBBBBBBBBBBBBBBBBBB", card_count: 75,
        description: "A goose with a sword and absolutely no plan. Chaos stacks into damage." },
      { word: "MOOSE", name: "Antler Warden", share_url: "/deck/smokeCCCCCCCCCCCCCCCCCCCC", card_count: 75,
        description: "Slow, huge and impossible to move; block turns into antler charges." } ] },
  };
  listeners.push((msg) => {
    if (msg.method !== "Fetch.requestPaused") return;
    const body = stubs[new URL(msg.params.request.url).pathname];
    if (!body) { send("Fetch.continueRequest", { requestId: msg.params.requestId }); return; }
    send("Fetch.fulfillRequest", { requestId: msg.params.requestId, responseCode: 200,
      responseHeaders: [{ name: "Content-Type", value: "application/json" }],
      body: Buffer.from(JSON.stringify(body)).toString("base64") });
  });
  await send("Fetch.enable", { patterns: [{ urlPattern: "*/api/me*" }, { urlPattern: "*/api/featured*" }] });
  const phone = () => send("Emulation.setDeviceMetricsOverride", { width: 390, height: 844, deviceScaleFactor: 2, mobile: true });
  const ua = (userAgent) => send("Emulation.setUserAgentOverride",
    { userAgent, platform: userAgent.includes("Android") ? "Linux armv8l" : "iPhone" });
  const loginState = `(() => { const pos = (a, b) => !!(a && b && (a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING));
    const form = document.getElementById('email-form'), gh = document.querySelector('a[href="/login/github"]'),
      g = document.querySelector('a[href="/login/google"]'), box = document.getElementById('webview-box'),
      open = document.getElementById('open-browser'), vis = (e) => !!e && !e.classList.contains('hidden') && e.offsetParent !== null;
    return {path: location.pathname, google: !!g, github: !!gh, form_visible: vis(form), box_visible: vis(box),
      form_before_github: pos(form, gh), google_before_form: pos(g, form), google_before_github: pos(g, gh),
      box_before_form: pos(box, form), head: document.getElementById('webview-head').textContent,
      label: form.querySelector('label').textContent, open_visible: vis(open), open_href: open.getAttribute('href'),
      open_text: open.textContent, menu: document.getElementById('webview-menu').textContent,
      menu_visible: vis(document.getElementById('webview-menu')), lede_visible: vis(document.getElementById('lede')),
      hatch: vis(document.getElementById('try-instead')), host: location.host,
      email_primary: form.querySelector('button').classList.contains('primary'), github_primary: !!gh && gh.classList.contains('primary'),
      overflow: document.documentElement.scrollWidth > window.innerWidth}; })()`;

  // (a) iPhone WKWebView, arriving from the ad: landing first (remembers utm_source=youtube for the tab).
  await ua(IOS_WEBVIEW); await phone();
  await nav(`${base}/?utm_source=youtube&utm_campaign=smoke`); await sleep(800);
  const land = await json(`(() => { const top = (el) => el.getBoundingClientRect().top;
    return {wv: window.BTS_WEBVIEW, note: document.getElementById('splash-note').textContent,
      pc: document.querySelector('.splash-pc')?.textContent, featured_hidden: document.getElementById('featured').classList.contains('hidden'),
      featured_top: top(document.getElementById('featured')), cta_top: top(document.getElementById('signin')),
      board_top: top(document.getElementById('board')), pc_top: top(document.querySelector('.splash-pc')),
      overflow: document.documentElement.scrollWidth > window.innerWidth}; })()`);
  check(land.wv.ios && land.wv.any && land.wv.app === "YouTube", "webview.js: iPhone WKWebView detected, YouTube from utm", JSON.stringify(land.wv));
  check(land.note === "Sign in by email — the YouTube browser can't do Google sign-in. Or tap ··· → Open in Safari.",
        "landing note swapped for the webview copy", land.note);
  check(land.pc === "A free mod for Slay the Spire 2 on Steam. Forge on any device; play on your PC." && land.pc_top > land.board_top,
        "PC line under the board", JSON.stringify(land));
  check(!land.featured_hidden && land.board_top < land.featured_top && land.featured_top < land.cta_top && !land.overflow,
        "phone hero order: board, featured strip, then the CTA; no sideways scroll", JSON.stringify(land));
  await shot("webview-landing-390");
  await shot("webview-landing-390-fold", false);

  await nav(`${base}/login`); await sleep(500);
  const wv = await json(loginState);
  check(wv.path === "/login" && !wv.google && wv.github, "webview /login: no Google button, GitHub kept", JSON.stringify(wv));
  check(wv.form_visible && wv.form_before_github && wv.box_visible && wv.box_before_form && !wv.lede_visible,
        "webview /login: notice, then the email form, then GitHub", JSON.stringify(wv));
  check(wv.head === "You're in the YouTube app's browser — Google can't sign you in here."
        && wv.label === "Enter your email and we'll send a link; it opens in Safari and you're in.",
        "webview /login: plan 4.2 heading copy", wv.head + " | " + wv.label);
  check(wv.open_visible && wv.open_text === "Open in Safari" && wv.open_href === `x-safari-https://${wv.host}/login`
        && wv.menu_visible && wv.menu.includes("··· menu at the top right and choose Open in Safari"),
        "webview /login: Open in Safari via x-safari-https + the menu fallback", JSON.stringify(wv));
  check(wv.email_primary && !wv.github_primary, "webview /login: the email button is the primary one", JSON.stringify(wv));
  check(wv.hatch && !wv.overflow, "webview /login: featured-class escape hatch kept; no sideways scroll", JSON.stringify(wv));
  await shot("webview-login-390");

  // (b) Android System WebView: the hand-off is an intent:// URL that keeps the path + query.
  await ua(ANDROID_WEBVIEW);
  await nav(`${base}/login?from=smoke`); await sleep(500);
  const an = await json(loginState);
  check(!an.google && an.form_before_github && an.open_text === "Open in Chrome"
        && an.open_href === `intent://${an.host}/login?from=smoke#Intent;scheme=https;end`,
        "android webview /login: email first, intent:// hand-off", JSON.stringify(an));

  // (c) real iPhone Safari: the old order (Google, GitHub, then "or" + the email form), no webview notice.
  await evaluate(`sessionStorage.clear()`);
  await ua(IOS_SAFARI);
  await nav(`${base}/login`); await sleep(500);
  const sf = await json(loginState);
  check(sf.google && sf.github && sf.google_before_github && sf.google_before_form && !sf.form_before_github
        && !sf.box_visible && sf.lede_visible && sf.form_visible && sf.github_primary && !sf.email_primary, "Safari /login: old order, Google first", JSON.stringify(sf));
  await shot("safari-login-390");
  await nav(`${base}/`); await sleep(800);
  const sl = await json(`({note: document.getElementById('splash-note').textContent, any: window.BTS_WEBVIEW.any})`);
  check(!sl.any && sl.note.startsWith("No password. Sign in with Google"), "Safari landing keeps the default note", JSON.stringify(sl));

  // (d) desktop keeps the old hero order: CTA above the featured strip.
  await send("Emulation.clearDeviceMetricsOverride");
  await send("Emulation.setUserAgentOverride", { userAgent: "" });
  await nav(`${base}/`); await sleep(800);
  const desk = await json(`({cta: document.getElementById('signin').getBoundingClientRect().top,
    featured: document.getElementById('featured').getBoundingClientRect().top})`);
  check(desk.cta < desk.featured, "desktop hero order unchanged (CTA above featured)", JSON.stringify(desk));
  await shot("desktop-landing", false);
  await send("Fetch.disable");
} else if (scenario === "phone") {
  // 2026-10-13 (docs/plans/PHONE_FUNNEL_PLAN.md phase 2): iPhone Safari at 390 px with touch emulation (so
  // `pointer: coarse` matches). The app leads with the concept box and shows the one-line phone banner
  // (dismissible) UNDER the Forge button (2026-10-26, FORGE_FIRST_PLAN.md D10); a forged class's result page carries "Send to my PC" + "Email it to me" ABOVE the
  // art and the card gallery; every library row carries both; /deck/<slug> carries the share-sheet button.
  // The dev server has no mail, so the email button is first checked disabled-with-a-reason, then /api/me is
  // rewritten (Fetch response stage) to say mail is configured and the POST is stubbed. navigator.share is
  // replaced with a capture stub (headless has no real sheet). Desktop is checked last: none of it shows.
  const IOS_SAFARI = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1";
  await send("Emulation.setDeviceMetricsOverride", { width: 390, height: 844, deviceScaleFactor: 2, mobile: true });
  await send("Emulation.setTouchEmulationEnabled", { enabled: true, maxTouchPoints: 5 });
  await send("Emulation.setUserAgentOverride", { userAgent: IOS_SAFARI, platform: "iPhone" });
  await nav(`${base}/dev-login?email=unlimited@example.com`);
  await evaluate(`localStorage.clear()`);
  await nav(`${base}/app`); await sleep(500);
  const vis = `(e) => !!e && e.offsetParent !== null && getComputedStyle(e).display !== 'none'`;
  const noScroll = `document.documentElement.scrollWidth <= window.innerWidth`;
  const top = `(e) => e ? e.getBoundingClientRect().top + window.scrollY : -1`;

  // (a0) a fresh 0-token account at 390 (the common case, FORGE_FIRST_PLAN.md case d): Forge with text unfolds the
  // pay step on the tiers, scrolled so the step's top sits under the header area, focus on the first tier.
  await nav(`${base}/dev-login?email=smoke-phone0@example.com`);
  await evaluate(`localStorage.clear()`);
  await nav(`${base}/app`); await sleep(800);
  await shot("phone-0token-390-fold", false);
  await evaluate(`(() => { document.getElementById('concept').value = 'a phone-smoke tide witch'; document.getElementById('forge-btn').click(); })()`);
  await sleep(1200);
  const p0 = await json(`(() => { const s = document.getElementById('pay-step'), r = s.getBoundingClientRect();
    return {visible: s.offsetParent !== null, top: Math.round(r.top), inner: window.innerHeight,
      tier_focus: !!document.activeElement && document.activeElement.classList.contains('donate-tier'),
      reason: document.getElementById('pay-reason').textContent, disabled: document.getElementById('forge-btn').disabled,
      no_scroll: ${noScroll}}; })()`);
  check(p0.visible && p0.top >= 0 && p0.top < 200 && p0.tier_focus && p0.reason === "Pick how to pay for this forge"
        && p0.disabled === false && p0.no_scroll, "phone 0-token: Forge unfolds the step at the top, focus on a tier", JSON.stringify(p0));
  await shot("phone-0token-pay-step-390-fold", false);
  await nav(`${base}/dev-login?email=unlimited@example.com`);
  await evaluate(`localStorage.clear()`);
  await nav(`${base}/app`); await sleep(500);

  // (a) the concept box is the first thing under the header; the phone banner sits under the Forge button
  const b = await json(`(() => { const vis = ${vis};
    const rect = (id) => document.getElementById(id).getBoundingClientRect();
    const concept = rect('concept').top;
    // every other visible block in the forge view (sections, banners, the pay step, the button row)
    const others = [...document.querySelectorAll('#view-forge > section, #view-forge .banner, #pay-step, .forge-actions, #forge-advanced')]
      .filter((e) => vis(e) && !e.contains(document.getElementById('concept')))
      .map((e) => ({id: e.id || e.className, top: Math.round(e.getBoundingClientRect().top)}));
    return {coarse: matchMedia('(pointer: coarse)').matches, is_phone: document.body.classList.contains('is-phone'),
      banner: vis(document.getElementById('phone-banner')), text: document.querySelector('#phone-banner p').textContent.replace(/\\s+/g, ' ').trim(),
      banner_top: Math.round(rect('phone-banner').top), btn_top: Math.round(rect('forge-btn').top),
      concept_top: Math.round(concept), concept_first: others.every((o) => o.top > concept), others,
      header_bottom: Math.round(document.querySelector('header').getBoundingClientRect().bottom),
      step_hidden: document.getElementById('pay-step').classList.contains('hidden'),
      btn_disabled: document.getElementById('forge-btn').disabled,
      tutorial: document.getElementById('v3-banner').textContent.replace(/\\s+/g, ' ').trim(),
      no_scroll: ${noScroll}}; })()`);
  check(b.coarse && b.is_phone, "touch emulation: pointer coarse + body.is-phone", JSON.stringify(b));
  check(b.banner && b.banner_top > b.btn_top && b.text.startsWith("On a phone? Forge away") && b.text.includes("send it to yourself below"),
        "phone banner visible, below the Forge button", JSON.stringify(b));
  check(b.concept_first && b.concept_top > b.header_bottom && b.step_hidden && b.btn_disabled === false,
        "phone: concept box first under the header, pay step hidden, Forge enabled", JSON.stringify(b));
  check(b.tutorial.includes("press Forge") && !/Subscribe/.test(b.tutorial), "tutorial is the one-liner (no subscribe step)", JSON.stringify(b.tutorial));
  check(b.no_scroll, "app at 390: no sideways scroll");
  await shot("phone-app-390-fold", false);
  // the pay step at 390: open it, no sideways scroll, then reload so the rest starts from a fresh visit
  await evaluate(`document.getElementById('pay-open').click()`); await sleep(800);
  check(await evaluate(`document.getElementById('pay-step').offsetParent !== null && ${noScroll}`), "phone: pay step opens, no sideways scroll");
  await shot("phone-pay-step-390-fold", false);
  await nav(`${base}/app`); await sleep(300);
  await evaluate(`document.getElementById('phone-banner-x').click()`); await sleep(200);
  const dis = await json(`({hidden: document.getElementById('phone-banner').classList.contains('hidden'),
    key: localStorage.getItem('bts_phone_banner_dismissed'), tutorial: !document.getElementById('v3-banner').classList.contains('hidden')})`);
  await nav(`${base}/app`); await sleep(300);
  const after = await evaluate(`document.getElementById('phone-banner').classList.contains('hidden')`);
  check(dis.hidden && dis.key === "1" && dis.tutorial && after, "phone banner dismisses (and stays dismissed), tutorial untouched", JSON.stringify(dis));

  // (b) forge a class through the UI (dev-only offline demo) and look at the result page
  await evaluate(`(() => { document.getElementById('forge-advanced').open = true;
    document.getElementById('mode-fake').checked = true;
    document.getElementById('concept').value = 'a phone-smoke lighthouse keeper';
    document.getElementById('forge-btn').click(); })()`);
  let done = false;
  for (let i = 0; i < 90 && !done; i++) {
    await sleep(1000);
    done = await evaluate(`!document.getElementById('result').classList.contains('hidden') && !!document.getElementById('r-code').value`);
  }
  check(done, "fake forge reached the result page");
  const r = await json(`(() => { const vis = ${vis}, top = ${top};
    const ho = document.getElementById('r-handoff'), send = document.getElementById('send-pc'), mail = document.getElementById('email-me');
    const art = document.getElementById('r-art'), cards = document.getElementById('r-cards');
    return {handoff: vis(ho), send: vis(send), mail: vis(mail), send_text: send.textContent, mail_text: mail.textContent,
      mail_disabled: mail.disabled, mail_title: mail.title, note: document.getElementById('r-handoff-note').textContent,
      before_cards: top(ho) < top(cards), before_art: !!(ho.compareDocumentPosition(art) & Node.DOCUMENT_POSITION_FOLLOWING),
      fold: send.getBoundingClientRect().bottom, inner: window.innerHeight, no_scroll: ${noScroll},
      name: document.getElementById('r-name').textContent}; })()`);
  check(r.handoff && r.send && r.mail && r.send_text.includes("Send to my PC") && r.mail_text.includes("Email it to me"),
        "result page: both hand-off buttons", JSON.stringify(r));
  check(r.before_cards && r.before_art, "result page: hand-off sits before the art and the card gallery", JSON.stringify(r));
  check(r.mail_disabled && /isn't set up/.test(r.mail_title) && /isn't set up/.test(r.note),
        "no mail on this server: email button disabled with the reason", JSON.stringify(r));
  check(r.no_scroll, "result at 390: no sideways scroll");
  check(r.fold > 0 && r.fold <= r.inner, "result page: scrolled into view, Send to my PC above the fold", JSON.stringify({fold: r.fold, inner: r.inner}));
  await shot("phone-result-390-fold", false);
  await evaluate(`window.scrollTo(0, 0)`);
  await shot("phone-result-390");

  // share sheet: stubbed navigator.share receives the class name + the /deck/<slug> link
  await evaluate(`Object.defineProperty(navigator, 'share', {configurable: true, value: async (d) => { window.__shared = d; }})`);
  await evaluate(`document.getElementById('send-pc').click()`); await sleep(300);
  const shared = await json(`window.__shared || null`);
  check(!!shared && /\/deck\/[A-Za-z0-9_-]{20,}$/.test(shared.url) && shared.title.includes(r.name),
        "Send to my PC opens the share sheet with the deck link", JSON.stringify(shared));
  // no share sheet: falls back to copying the link (headless clipboard may refuse; either toast is the fallback)
  await evaluate(`Object.defineProperty(navigator, 'share', {configurable: true, value: undefined})`);
  await evaluate(`document.getElementById('send-pc').click()`); await sleep(400);
  const fb = await evaluate(`document.getElementById('toast').textContent`);
  check(/Copied|Copy failed/.test(fb), "no share sheet: falls back to copying the link", fb);
  // the code box selects all on tap
  const sel = await json(`(() => { const t = document.getElementById('r-code'); t.blur(); t.focus(); t.click();
    return {start: t.selectionStart, end: t.selectionEnd, len: t.value.length, ro: t.readOnly}; })()`);
  check(sel.ro && sel.start === 0 && sel.end === sel.len && sel.len > 0, "code box: readonly, select-all on tap", JSON.stringify(sel));

  // (c) library rows
  await evaluate(`document.getElementById('nav-library').click()`); await sleep(1200);
  const lib = await json(`(() => { const vis = ${vis}; return [...document.querySelectorAll('#lib-list .lib-row')].map(li => ({
    send: vis(li.querySelector('[data-act=sendpc]')), mail: vis(li.querySelector('[data-act=email]')),
    mail_disabled: li.querySelector('[data-act=email]')?.disabled})); })()`);
  check(lib.length > 0 && lib.every((x) => x.send && x.mail && x.mail_disabled), "library rows: both hand-off buttons (email disabled: no mail)", JSON.stringify(lib));
  check(await evaluate(noScroll), "library at 390: no sideways scroll");
  await shot("phone-library-390", false);

  // (d) mail configured (rewritten /api/me) + a stubbed send: the button enables and the toast names the address
  const posted = [];
  listeners.push(async (msg) => {
    if (msg.method !== "Fetch.requestPaused") return;
    const p = msg.params, path = new URL(p.request.url).pathname;
    if (path === "/api/me" && p.responseStatusCode) {
      const body = await send("Fetch.getResponseBody", { requestId: p.requestId });
      const data = JSON.parse(body.base64Encoded ? Buffer.from(body.body, "base64").toString() : body.body);
      data.mail = true;
      send("Fetch.fulfillRequest", { requestId: p.requestId, responseCode: 200,
        responseHeaders: [{ name: "Content-Type", value: "application/json" }],
        body: Buffer.from(JSON.stringify(data)).toString("base64") });
    } else if (/^\/api\/classes\/\d+\/email$/.test(path)) {
      posted.push(path);
      send("Fetch.fulfillRequest", { requestId: p.requestId, responseCode: 200,
        responseHeaders: [{ name: "Content-Type", value: "application/json" }],
        body: Buffer.from(JSON.stringify({ sent: true, to: "unlimited@example.com" })).toString("base64") });
    } else {
      send("Fetch.continueRequest", { requestId: p.requestId });
    }
  });
  await send("Fetch.enable", { patterns: [{ urlPattern: "*/api/me*", requestStage: "Response" },
                                          { urlPattern: "*/api/classes/*/email*", requestStage: "Request" }] });
  await nav(`${base}/app`); await sleep(500);
  await evaluate(`document.getElementById('nav-library').click()`); await sleep(1200);
  const en = await json(`(() => { const m = document.querySelector('#lib-list [data-act=email]'); return {disabled: m.disabled, title: m.title}; })()`);
  check(!en.disabled && en.title.includes("unlimited@example.com"), "mail configured: email button enabled", JSON.stringify(en));
  await evaluate(`document.querySelector('#lib-list [data-act=email]').click()`); await sleep(800);
  const toastText = await evaluate(`document.getElementById('toast').textContent`);
  check(posted.length === 1 && /Sent to unlimited@example.com/.test(toastText), "Email it to me posts and confirms", toastText);
  await send("Fetch.disable");

  // (e) the public share page at 390: the share-sheet button, no email, no sideways scroll
  const slug = shared && shared.url.split("/deck/")[1];
  await nav(`${base}/deck/${slug}`); await sleep(1000);
  const d = await json(`(() => { const vis = ${vis}, top = ${top};
    return {send: vis(document.getElementById('send-pc')), email: !!document.getElementById('email-me'),
      before_cards: top(document.getElementById('send-pc')) < top(document.getElementById('r-cards')),
      no_scroll: ${noScroll}}; })()`);
  check(d.send && !d.email && d.before_cards && d.no_scroll, "/deck at 390: share-sheet button, no email, no sideways scroll", JSON.stringify(d));
  await evaluate(`Object.defineProperty(navigator, 'share', {configurable: true, value: async (x) => { window.__shared = x; }})`);
  await evaluate(`document.getElementById('send-pc').click()`); await sleep(300);
  const ds = await json(`window.__shared || null`);
  check(!!ds && ds.url.endsWith("/deck/" + slug), "/deck Send to my PC shares this page", JSON.stringify(ds));
  await shot("phone-deck-390-fold", false);
  await shot("phone-deck-390");

  // (f) desktop: none of it shows
  await send("Emulation.setTouchEmulationEnabled", { enabled: false });
  await send("Emulation.clearDeviceMetricsOverride");
  await send("Emulation.setUserAgentOverride", { userAgent: "" });
  await nav(`${base}/app`); await sleep(500);
  await evaluate(`localStorage.clear()`); await nav(`${base}/app`); await sleep(500);
  const desk = await json(`(() => { const vis = ${vis}; return {is_phone: document.body.classList.contains('is-phone'),
    banner: vis(document.getElementById('phone-banner')),
    tutorial: document.getElementById('v3-banner').textContent.replace(/\\s+/g, ' ').trim()}; })()`);
  await evaluate(`document.getElementById('nav-library').click()`); await sleep(1000);
  const deskLib = await evaluate(`[...document.querySelectorAll('#lib-list [data-act=sendpc], #lib-list [data-act=email]')].some(e => e.offsetParent !== null)`);
  check(!desk.is_phone && !desk.banner && desk.tutorial.includes("press Forge") && !deskLib,
        "desktop: no phone banner, one-line tutorial, no hand-off buttons", JSON.stringify(desk));
  await nav(`${base}/deck/${slug}`); await sleep(800);
  check(!(await evaluate(`document.getElementById('send-pc').offsetParent !== null`)), "desktop /deck: no share-sheet button");
} else if (scenario === "events") {
  // Sign-up events (docs/plans/SIGNUP_EVENTS_PLAN.md). Needs BTSWEB_ADMIN_EMAILS=unlimited@example.com and a
  // FRESH DB (no events). (a) no event: no ribbon anywhere; (b) a live event: the ribbon on the splash and
  // /login for a signed-out visitor only; (c) a new account made during it gets the welcome banner once, and a
  // welcome consumed by the splash is still shown by the app; (d) the admin Events card with an ended, a live
  // and a scheduled event; (e) End now from the card: the ribbon is gone. The browser cache is off, so the
  // 60 s Cache-Control on /api/promo/active does not hold the old answer between steps.
  await send("Network.enable");
  await send("Network.setCacheDisabled", { cacheDisabled: true });
  const phone = () => send("Emulation.setDeviceMetricsOverride", { width: 390, height: 844, deviceScaleFactor: 2, mobile: true });
  const desktop = () => send("Emulation.clearDeviceMetricsOverride");
  const signOut = async () => {
    await evaluate(`fetch('/logout', {method: 'POST', headers: {'X-Requested-With': 'fetch'}}).then(() => 1)`);
  };
  const ribbonState = `(() => { const r = document.querySelector('.event-ribbon');
    return {ribbon: r ? r.textContent.replace(/\\s+/g, ' ').trim() : null,
            overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
            cta_top: Math.round(document.querySelector('.splash-actions, #providers').getBoundingClientRect().top + scrollY)}; })()`;
  const api = async (path, body) => JSON.parse(await evaluate(`(async () => { const r = await fetch(${JSON.stringify(path)}, {method: 'POST',
    headers: {'Content-Type': 'application/json', 'X-Requested-With': 'fetch'}, body: ${JSON.stringify(JSON.stringify(body || {}))}});
    return JSON.stringify({status: r.status, body: await r.json()}); })()`));

  // (a) no event
  await signOut();
  await phone();
  await nav(`${base}/`); await sleep(800);
  const noneLanding = await json(ribbonState);
  check(noneLanding.ribbon === null && !noneLanding.overflow, "(a) splash, no event: no ribbon, no sideways scroll", JSON.stringify(noneLanding));
  await shot("events-a-landing-none-390", false);
  await nav(`${base}/login`); await sleep(800);
  const noneLogin = await json(ribbonState);
  check(noneLogin.ribbon === null, "(a) /login, no event: no ribbon", JSON.stringify(noneLogin));
  await shot("events-a-signin-none-390", false);
  await desktop();
  await nav(`${base}/`); await sleep(800);
  check((await json(ribbonState)).ribbon === null, "(a) splash desktop, no event: no ribbon");
  await shot("events-a-landing-none-desktop", false);

  // (d, setup) an ended, a live and a scheduled event, through the admin API
  await nav(`${base}/dev-login?email=unlimited@example.com`);
  const iso = (ms) => new Date(Date.now() + ms).toISOString();
  const H = 3600 * 1000;
  const ended = await api("/api/admin/promos", { label: "Soft launch", tokens_per_signup: 1, max_grants: 10,
    starts_at: iso(-2 * H), ends_at: iso(H) });
  await api(`/api/admin/promos/${ended.body.id}/end`);
  const live = await api("/api/admin/promos", { label: "Launch weekend", tokens_per_signup: 1, max_grants: 50,
    starts_at: iso(-10 * 60 * 1000), ends_at: iso(48 * H) });
  const sched = await api("/api/admin/promos", { label: "Holiday forge", tokens_per_signup: 2, max_grants: 25,
    starts_at: iso(72 * H), ends_at: iso(96 * H) });
  check(ended.status === 201 && live.status === 201 && sched.status === 201, "(d) three events created",
        JSON.stringify([ended.status, live.status, sched.status, live.body.error || "", sched.body.error || ""]));

  // (b) live: ribbon for a signed-out visitor, never for a signed-in one
  await nav(`${base}/`); await sleep(800);
  check((await json(ribbonState)).ribbon === null, "(b) signed-in visitor on the splash: no ribbon");
  await signOut();
  await phone();
  await nav(`${base}/`); await sleep(800);
  const liveLanding = await json(ribbonState);
  check(liveLanding.ribbon && liveLanding.ribbon.includes("Launch weekend: sign up before")
        && liveLanding.ribbon.endsWith("your first forge is on us.") && !liveLanding.overflow,
        "(b) splash 390: ribbon, no sideways scroll", JSON.stringify(liveLanding));
  await shot("events-b-landing-live-390", false);
  await nav(`${base}/login`); await sleep(800);
  const liveLogin = await json(ribbonState);
  check(liveLogin.ribbon && liveLogin.ribbon.includes("Launch weekend"), "(b) /login 390: ribbon", JSON.stringify(liveLogin));
  await shot("events-b-signin-live-390", false);
  await desktop();
  await nav(`${base}/`); await sleep(800);
  await shot("events-b-landing-live-desktop", false);

  // (c) a new account during the event: the banner once, balance 1; a reload has no banner
  await nav(`${base}/dev-login?email=newbie-${Date.now()}@example.com`); await sleep(800);
  const c1 = await json(`({banner: document.getElementById('welcome-banner').offsetParent !== null,
    text: document.getElementById('welcome-text').textContent, balance: ME.token_balance,
    chip: document.getElementById('tokens').textContent})`);
  check(c1.banner && c1.text.startsWith("Welcome! Launch weekend gave you 1 free forge token.") && c1.balance === 1,
        "(c) new account: welcome banner, balance 1", JSON.stringify(c1));
  await shot("events-c-welcome-desktop", false);
  await nav(`${base}/app`); await sleep(800);
  const c2 = await json(`({banner: document.getElementById('welcome-banner').offsetParent !== null, balance: ME.token_balance})`);
  check(!c2.banner && c2.balance === 1, "(c) reload: banner gone, balance still 1", JSON.stringify(c2));
  // The splash reads /api/me first (here: before the app ever does) -> signup-event.js parks the grant.
  await signOut();
  await phone();
  await evaluate(`localStorage.clear()`);
  // fetch (not a navigation): the cookie is set and the redirect to /app is fetched as text, so no app.js runs.
  await evaluate(`fetch('/dev-login?email=newbie3-${Date.now()}@example.com').then(() => 1)`);
  await nav(`${base}/`); await sleep(800);
  const parked = await evaluate(`localStorage.getItem('bts_welcome_grant')`);
  await nav(`${base}/app`); await sleep(800);
  const c3 = await json(`({banner: document.getElementById('welcome-banner').offsetParent !== null,
    text: document.getElementById('welcome-text').textContent, left: localStorage.getItem('bts_welcome_grant')})`);
  check(!!parked && c3.banner && c3.text.includes("Launch weekend") && c3.left === null,
        "(c) welcome consumed by the splash is shown by the app, then cleared", JSON.stringify({ parked, ...c3 }));
  await shot("events-c-welcome-390", false);

  // (d) the admin card
  await signOut();
  await desktop();
  await nav(`${base}/dev-login?email=unlimited@example.com`); await sleep(500);
  await evaluate(`document.getElementById('nav-account').click()`); await sleep(1500);
  const d1 = await json(`({rows: [...document.querySelectorAll('#admin-events-table tr[data-id]')].map(r => r.querySelector('.ev-pill').textContent),
    ends: document.querySelectorAll('#admin-events-table [data-act=end]').length})`);
  check(JSON.stringify(d1.rows) === JSON.stringify(["scheduled", "live", "ended"]) && d1.ends === 2,
        "(d) Events card: scheduled, live, ended; End now on the two open ones", JSON.stringify(d1));
  await shotEl("events-d-admin-card-desktop", "#admin-events");
  // An overlapping create answers 409; the message lands in the form.
  await evaluate(`document.getElementById('admin-events-new').click()`);
  await evaluate(`document.getElementById('ev-label').value = 'Clash'; document.getElementById('ev-cap').value = '5';
    document.getElementById('admin-event-save').click()`);
  await sleep(800);
  const err = await evaluate(`document.getElementById('admin-event-note').textContent`);
  check(err.includes("overlaps event"), "(d) overlapping create: the 409 message inline", err);
  await shotEl("events-d-admin-form-error", "#admin-events");
  await evaluate(`document.getElementById('admin-event-cancel').click()`);
  await phone();
  await sleep(300);
  await shotEl("events-d-admin-card-390", "#admin-events");
  await desktop();

  // (e) End now on the live event, then the splash has no ribbon
  await evaluate(`window.confirm = () => true`);
  await evaluate(`document.querySelector('#admin-events-table tr[data-id="${live.body.id}"] [data-act=end]').click()`);
  await sleep(1000);
  const e1 = await json(`({pill: document.querySelector('#admin-events-table tr[data-id="${live.body.id}"] .ev-pill').textContent,
    note: document.getElementById('admin-events-note').textContent,
    log: document.getElementById('admin-actions').textContent})`);
  check(e1.pill === "ended" && e1.note.startsWith("Ended") && e1.log.includes("ended sign-up event #"),
        "(e) End now: row ended, note, audit line", JSON.stringify(e1));
  await signOut();
  await phone();
  await nav(`${base}/`); await sleep(800);
  const after = await json(ribbonState);
  check(after.ribbon === null, "(e) after End now: no ribbon", JSON.stringify(after));
  await shot("events-e-landing-ended-390", false);
  await desktop();
} else if (scenario === "lang") {
  // 2026-10-28 (docs/plans/I18N_PLAN.md phase 1): the EN | 中文 toggle and i18n.js. Needs a web/static/i18n/zh.json
  // with at least one translated landing string and one console.* rule (the real one comes from the translation
  // build; a hand-made stub is enough). ?lang=zh picks Chinese and persists it, a reload without ?lang keeps it,
  // clicking EN brings the English page back. English text in the HTML is never touched in English.
  await send("Network.enable");
  await send("Network.setCacheDisabled", { cacheDisabled: true });
  const phone = () => send("Emulation.setDeviceMetricsOverride", { width: 390, height: 844, deviceScaleFactor: 2, mobile: true });
  const desktop = () => send("Emulation.clearDeviceMetricsOverride");
  const noScroll = `document.documentElement.scrollWidth <= window.innerWidth`;
  // Elements whose visible text differs from the English string of their key (en.json, tags stripped).
  const diffCount = `(async () => {
    await BTS_I18N.ready;
    const en = (await (await fetch('/static/i18n/en.json')).json()).strings;
    const plain = (h) => { const d = document.createElement('div'); d.innerHTML = h; return d.textContent.replace(/\\s+/g, ' ').trim(); };
    const els = [...document.querySelectorAll('[data-i18n], [data-i18n-html]')];
    const keys = els.map((e) => e.getAttribute('data-i18n') || e.getAttribute('data-i18n-html'));
    const missing = [...new Set(keys.filter((k) => !(k in en)))];
    const differ = keys.filter((k, i) => (k in en) && !/\\{\\w+\\}/.test(en[k])
      && els[i].textContent.replace(/\\s+/g, ' ').trim() !== plain(en[k]));
    return JSON.stringify({tagged: els.length, differ: differ.length, differKeys: differ.slice(0, 8), missing});
  })()`;
  const diffs = async () => JSON.parse(await evaluate(diffCount));
  const state = `({lang: document.documentElement.lang, i18n: window.BTS_I18N && BTS_I18N.lang,
    toggle: !!document.querySelector('[data-lang-toggle]'),
    inHeader: !!document.querySelector('header nav [data-lang-toggle]'),
    active: (document.querySelector('[data-lang-toggle] .lang-opt.active') || {}).dataset?.lang || null,
    opts: [...document.querySelectorAll('[data-lang-toggle] [data-lang]')].map((b) => b.dataset.lang + '=' + b.textContent),
    stored: localStorage.getItem('bts.lang'), url: location.search,
    tag: (document.querySelector('.splash-tag') || {}).textContent || null,
    word: !!document.querySelector('[data-i18n-html="landing.how.step_3_body"] [data-i18n-slot="word"]')})`;

  await nav(`${base}/`);
  await evaluate(`fetch('/logout', {method: 'POST', headers: {'X-Requested-With': 'fetch'}}).then(() => 1)`);
  await nav(`${base}/`);
  await evaluate(`localStorage.clear()`);
  await nav(`${base}/`); await sleep(500);
  const en0 = await json(state);
  check(en0.lang === "en" && en0.i18n === "en" && en0.toggle && en0.active === "en" && en0.stored === null
        && en0.opts.join(",") === "en=EN,zh=中文", "(a) fresh visitor: English, toggle shows EN active, nothing stored", JSON.stringify(en0));
  const enTag = en0.tag;

  await nav(`${base}/?lang=zh`); await sleep(800);
  const zh = await json(state);
  check(zh.lang === "zh" && zh.i18n === "zh" && zh.toggle && zh.active === "zh" && zh.stored === "zh",
        "(b) ?lang=zh: <html lang=zh>, toggle active zh, choice stored", JSON.stringify(zh));
  const zd = await diffs();
  check(zd.differ >= 1 && zh.tag !== enTag, "(b) at least one data-i18n element is translated", JSON.stringify({zd, tag: zh.tag}));
  check(zd.missing.length === 0, "(b) every data-i18n key on the landing page exists in en.json", JSON.stringify(zd.missing));
  check(zh.word, "(b) the step-3 {word} slot survives the translation (landing.js keeps its node)", JSON.stringify(zh));
  const cons = await json(`({hit: BTS_I18N.console("[1/6] cloud: brainstorming free associations on 'a smoke toaster'..."),
    miss: BTS_I18N.console("some detail line nobody translates")})`);
  check(cons.hit.includes("a smoke toaster") && !cons.hit.startsWith("[1/6] cloud: brainstorming") && cons.miss === "some detail line nobody translates",
        "(b) console stage header localised with the concept carried over; detail line unchanged", JSON.stringify(cons));
  await shot("lang-b-landing-zh", false);
  await phone(); await sleep(300);
  const ph = await json(`({noScroll: ${noScroll}, box: (() => { const r = document.querySelector('[data-lang-toggle]').getBoundingClientRect(); return [Math.round(r.left), Math.round(r.right), Math.round(r.top)]; })(), vw: innerWidth})`);
  check(ph.noScroll && ph.box[1] <= ph.vw && ph.box[0] >= 0, "(b) phone 390: toggle on screen, no horizontal scroll", JSON.stringify(ph));
  await shot("lang-b-landing-zh-390", false);
  await desktop();

  await nav(`${base}/`); await sleep(800);
  const kept = await json(state);
  check(kept.lang === "zh" && kept.active === "zh" && kept.url === "", "(c) reload without ?lang keeps zh", JSON.stringify(kept));

  // the other pages in zh: html lang, toggle in the header, no console errors (collected at the end)
  for (const p of ["help", "download", "archive", "login"]) {
    await nav(`${base}/${p}`); await sleep(500);
    const s = await json(state);
    const d = await diffs();
    check(s.lang === "zh" && s.inHeader && s.active === "zh" && d.missing.length === 0,
          `(c) /${p} in zh: lang, toggle in header nav, all keys known`, JSON.stringify({s: {lang: s.lang, inHeader: s.inHeader}, d}));
  }
  await nav(`${base}/dev-login?email=unlimited@example.com`);
  await nav(`${base}/app`); await sleep(800);
  const app = await json(state);
  check(app.lang === "zh" && app.inHeader, "(c) /app in zh boots with the toggle in the header", JSON.stringify(app));
  await shot("lang-c-app-zh", false);
  await phone(); await sleep(300);
  const aph = await json(`({noScroll: ${noScroll}, vis: (() => { const r = document.querySelector('[data-lang-toggle]').getBoundingClientRect(); return r.width > 0 && r.right <= innerWidth; })()})`);
  check(aph.noScroll && aph.vis, "(c) /app at 390: toggle visible, no horizontal scroll", JSON.stringify(aph));
  await shot("lang-c-app-zh-390", false);
  await desktop();

  // (d) click EN: English back, stored, ?lang gone
  await nav(`${base}/?lang=zh`); await sleep(600);
  await evaluate(`document.querySelector('[data-lang-toggle] [data-lang="en"]').click()`);
  await sleep(1500);
  const back = await json(state);
  const bd = await diffs();
  check(back.lang === "en" && back.active === "en" && back.stored === "en" && back.url === "" && back.tag === enTag && bd.differ === 0,
        "(d) clicking EN: English page back, choice stored, no ?lang in the URL", JSON.stringify({back, bd}));
  await shot("lang-d-landing-en", false);
  // (e) English drift: on every page the static English of each tagged element equals its en.json string
  // (COPY.md is the source; a mismatch means the HTML and COPY.md disagree). Keys with {placeholders} skipped.
  // app.js relabels the Forge button at boot (token count), so that one key is expected to differ on /app.
  const RUNTIME = ["app.forge.button"];
  await evaluate(`fetch('/logout', {method: 'POST', headers: {'X-Requested-With': 'fetch'}}).then(() => 1)`);
  for (const p of ["login", "help", "download", "archive", "app"]) {
    if (p === "app") await nav(`${base}/dev-login?email=unlimited@example.com`);
    await nav(`${base}/${p}`); await sleep(500);
    const d = await diffs();
    const real = d.differKeys.filter((k) => !RUNTIME.includes(k));
    check(real.length === 0 && d.missing.length === 0, `(e) /${p} in English matches en.json`, JSON.stringify(d));
  }
}
console.log(errors.length ? "CONSOLE ERRORS:\n" + errors.join("\n") : "no console errors");
ws.close(); chrome.kill();

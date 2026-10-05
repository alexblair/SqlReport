// 导出对话框交叉选择实测（真实点击 + 每例前重置状态）
import { writeFileSync } from 'node:fs';
const BASE = 'http://127.0.0.1:8099';
const port = process.env.CDP_PORT || 9411;
const out = process.argv[2];
const list = await (await fetch(`http://127.0.0.1:${port}/json/new?about:blank`, { method: 'PUT' })).json();
const ws = new WebSocket(list.webSocketDebuggerUrl);
let id = 0; const pending = new Map();
const send = (m, p = {}) => new Promise((res, rej) => {
  const i = ++id; pending.set(i, { res, rej });
  ws.send(JSON.stringify({ id: i, method: m, params: p }));
  setTimeout(() => { if (pending.has(i)) { pending.delete(i); rej(new Error('t ' + m)); } }, 60000);
});
ws.onmessage = e => { const m = JSON.parse(e.data); if (m.id && pending.has(m.id)) { const x = pending.get(m.id); pending.delete(m.id); m.error ? x.rej(new Error(m.error.message)) : x.res(m.result); } };
const ev = async e => (await send('Runtime.evaluate', { returnByValue: true, expression: e, awaitPromise: true })).result.value;
const sleep = ms => new Promise(r => setTimeout(r, ms));

await new Promise((r, j) => { ws.onopen = r; ws.onerror = j; });
await send('Page.enable'); await send('Runtime.enable');
await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });
await send('Page.navigate', { url: BASE + '/login' }); await sleep(700);
await ev(`document.querySelector('input[name=username]').value='admin';document.querySelector('input[name=password]').value='admin123';document.querySelector('form').submit();`);
await sleep(1500);

const READ = `(() => {
  const f = document.getElementById('export-modal-form');
  const qs = new URLSearchParams(new FormData(f));
  const fmtVals = qs.getAll('format');
  const smarts = [...document.querySelectorAll('#export-smart-panel .smart-quote-cb')];
  return {
    fmt: fmtVals, fmtSelect: (document.getElementById('export-format-select')||{}).value,
    fmtMatch: fmtVals.length > 1 ? fmtVals.every(v => v === fmtVals[0]) : true,
    charset: qs.get('charset'), zip: qs.get('zip'), smartHidden: qs.get('smart_quotes'),
    useCustom: qs.get('use_custom_cols'), cols: qs.get('cols'),
    smartDisabled: smarts.every(c => c.disabled), smartChecked: smarts.filter(c => c.checked).length,
    charsetDisabled: [...document.querySelectorAll('input[name="charset"]')].every(r => r.disabled),
    charsetHint: (() => { const h = document.getElementById('export-charset-json-hint');
      return h ? getComputedStyle(h).display : '无'; })(),
    qs: qs.toString()
  };
})()`;
const DO_FETCH = `(async () => {
  const f = document.getElementById('export-modal-form');
  const qs = new URLSearchParams(new FormData(f)).toString();
  const res = await fetch('/export?' + qs, { credentials: 'same-origin' });
  const ct = res.headers.get('content-type') || '';
  const cd = res.headers.get('content-disposition') || '';
  const buf = await res.arrayBuffer();
  const head = new TextDecoder('utf-8').decode(buf.slice(0, 100)).replace(/\\s+/g, ' ');
  return { status: res.status, ct, cd: cd.slice(0, 48), bytes: buf.byteLength, head,
           magic: [...new Uint8Array(buf.slice(0,4))].join(',') };
})()`;

const cases = [
  ['默认（CSV+GBK）', ``],
  ['切 UTF-8', `document.querySelector('input[name="charset"][value="utf8"]').click()`],
  ['切 JSON', `document.getElementById('export-format-json').click()`],
  ['JSON+UTF8', `document.getElementById('export-format-json').click();document.querySelector('input[name="charset"][value="utf8"]').click()`],
  ['JSON+智能去引号(十进制)', `document.getElementById('export-format-json').click();
      document.querySelectorAll('#export-smart-panel .smart-quote-cb')[0].click()`],
  ['勾 ZIP', `document.querySelector('input[name="zip"]').click()`],
  ['勾 自定义列', `document.querySelector('input[name="use_custom_cols"]').click()`],
  ['回 CSV（智能去引号应禁用并清零）', `document.getElementById('export-format-csv').click()`],
];

const report = {};
for (const [label, action] of cases) {
  // 每例重置：重新加载页面并打开导出对话框（避免状态残留）
  await send('Page.navigate', { url: BASE + '/report?id=1&page_size=20&cols=customer,amount,id&sort=amount&dir=desc' });
  await sleep(1100);
  await ev(`openPanel('modal-export')`); await sleep(250);
  if (action) { await ev(`(()=>{${action}})()`); await sleep(250); }
  const state = await ev(READ);
  const fetched = await ev(DO_FETCH);
  report[label] = { state, fetched };
  if (out) { const s = await send('Page.captureScreenshot', { format: 'png' });
    writeFileSync(`${out}/export-${label.replace(/[^\w\u4e00-\u9fa5]/g, '_')}.png`, Buffer.from(s.data, 'base64')); }
}
console.log(JSON.stringify(report, null, 1));
ws.close(); process.exit(0);

// 严格复现用户步骤：id=4 → 隐藏 id → 应用 → 还原 id → 应用 → 再排序（看是否报废）
import { writeFileSync } from 'node:fs';
const BASE = 'http://127.0.0.1:8099';
const port = process.env.CDP_PORT || 9440;
const out = process.argv[2];
const list = await (await fetch(`http://127.0.0.1:${port}/json/new?about:blank`, { method: 'PUT' })).json();
const ws = new WebSocket(list.webSocketDebuggerUrl);
let id = 0; const pending = new Map(); const exc = []; const errs = [];
const send = (m, p = {}) => new Promise((res, rej) => {
  const i = ++id; pending.set(i, { res, rej });
  ws.send(JSON.stringify({ id: i, method: m, params: p }));
  setTimeout(() => { if (pending.has(i)) { pending.delete(i); rej(new Error('t ' + m)); } }, 40000);
});
ws.onmessage = e => {
  const m = JSON.parse(e.data);
  if (m.id && pending.has(m.id)) { const x = pending.get(m.id); pending.delete(m.id); m.error ? x.rej(new Error(m.error.message)) : x.res(m.result); }
  else if (m.method === 'Runtime.exceptionThrown') exc.push((m.params.exceptionDetails.exception?.description || JSON.stringify(m.params.exceptionDetails)).slice(0, 220));
  else if (m.method === 'Log.entryAdded' && m.params.entry.level === 'error') errs.push(m.params.entry.text.slice(0, 160));
};
const ev = async e => (await send('Runtime.evaluate', { returnByValue: true, expression: e, awaitPromise: true })).result.value;
const sleep = ms => new Promise(r => setTimeout(r, ms));

await new Promise((r, j) => { ws.onopen = r; ws.onerror = j; });
await send('Page.enable'); await send('Runtime.enable'); await send('Log.enable');
await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });
await send('Page.navigate', { url: BASE + '/login' }); await sleep(700);
await ev(`document.querySelector('input[name=username]').value='admin';document.querySelector('input[name=password]').value='admin123';document.querySelector('form').submit();`);
await sleep(1500);
await send('Page.navigate', { url: BASE + '/report?id=4' }); await sleep(1300);

const TOOLS = `window.__t = {
  items: () => [...document.querySelectorAll('#fieldList .field-item')],
  colOf: it => it.querySelector('input[name=col_order]').value,
  order: () => window.__t.items().map(window.__t.colOf).join(','),
  checked: () => window.__t.items().map(it => window.__t.colOf(it) + ':' + (it.querySelector('input[type=checkbox]').checked ? '1' : '0')).join(' '),
  setCheck: (name, on) => { const it = window.__t.items().find(x => window.__t.colOf(x) === name);
    const cb = it.querySelector('input[type=checkbox]'); cb.checked = on; toggleFieldItem(cb); },
  openFields: () => openPanel('fieldSettingsPanel'),
  applyFields: () => applyFieldSettings(),
  sortItems: () => [...document.querySelectorAll('#sortList .sort-item')].map(it =>
    it.querySelector('input[name=sort_col]').value + ':' + it.querySelector('input[name=sort_dir]').value).join(','),
  addSort: (col, dir) => { const s = document.getElementById('newSortCol'); s.value = col;
    document.getElementById('newSortDir').value = dir;
    document.querySelector('button[onclick="addSortItem()"]').click(); },
  hasDrag: () => { const l = document.getElementById('fieldList');
    return l ? (typeof initDragHandlers === 'function') : 'no-list'; },
};`;

const SNAP = `(async()=>({
  url: location.search,
  tableCols: [...document.querySelectorAll('.qf-row td')].map(td=>td.dataset.col).join(','),
  fieldListCount: document.querySelectorAll('#fieldList').length,
  fieldItems: document.querySelectorAll('#fieldList .field-item').length,
  sortListCount: document.querySelectorAll('#sortList').length,
  sortItems: document.querySelectorAll('#sortList .sort-item').length,
  fnApplySort: typeof applySortSettings, fnApplyFields: typeof applyFieldSettings,
}))()`;

const log = {};
await ev(TOOLS); await sleep(200);
log['0 起始'] = await ev(SNAP);

// ① 隐藏 id → 应用
await ev(`window.__t.openFields()`); await sleep(250);
await ev(`window.__t.setCheck('id', false)`);
log['1a 面板勾选状态'] = await ev(`window.__t.checked()`);
await ev(`window.__t.applyFields()`); await sleep(1600);
log['1 隐藏 id 后'] = await ev(SNAP);

// ② 还原 id → 应用
await ev(`window.__t.openFields()`); await sleep(250);
await ev(`window.__t.setCheck('id', true)`);
log['2a 面板勾选状态'] = await ev(`window.__t.checked()`);
await ev(`window.__t.applyFields()`); await sleep(1600);
log['2 还原 id 后'] = await ev(SNAP);

// ③ 再排序：加一个 amount/id 排序并应用（id=4 的列是 id/customer/status）
await ev(`openPanel('sortSettingsPanel')`); await sleep(350);
log['3a 排序面板可选列'] = await ev(`[...document.querySelectorAll('#newSortCol option')].map(o=>o.value).filter(Boolean).join(',')`);
const before = await ev(`window.__t.sortItems()`);
await ev(`window.__t.addSort('customer','desc')`); await sleep(300);
log['3b 添加排序项'] = { before, after: await ev(`window.__t.sortItems()`) };
await ev(`applySortSettings()`); await sleep(1800);
log['3 应用排序后'] = await ev(SNAP);
log['3c 排序条'] = await ev(`(()=>{const b=document.querySelector('.sort-bar');return b?b.textContent.replace(/\\s+/g,' ').trim().slice(0,60):'无'})()`);
if (out) { const s = await send('Page.captureScreenshot', { format: 'png' });
  writeFileSync(`${out}/repro-sort-broken.png`, Buffer.from(s.data, 'base64')); }

// ④ 再试一次排序（拖动排序项容器是否还能响应）
log['4a 拖拽绑定'] = await ev(`window.__t.hasDrag()`);
log['4b 排序项 draggable'] = await ev(`[...document.querySelectorAll('#sortList .sort-item')].map(i=>i.getAttribute('draggable')).join(',')`);
log['4c 面板开合状态'] = await ev(`(()=>{const p=document.getElementById('sortSettingsPanel');return p?getComputedStyle(p).display:'无面板'})()`);

console.log(JSON.stringify({ log, exceptions: exc, consoleErrors: errs }, null, 1));
ws.close(); process.exit(0);

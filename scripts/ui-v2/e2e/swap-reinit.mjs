// 换页重初始化验证：用户步骤（隐藏→还原→排序）+ 换页后拖拽/内联脚本/嵌套筛选是否仍可用
import { writeFileSync } from 'node:fs';
const BASE = 'http://127.0.0.1:8099';
const port = process.env.CDP_PORT || 9450;
const out = process.argv[2];
const list = await (await fetch(`http://127.0.0.1:${port}/json/new?about:blank`, { method: 'PUT' })).json();
const ws = new WebSocket(list.webSocketDebuggerUrl);
let id = 0; const pending = new Map(); const exc = [];
const send = (m, p = {}) => new Promise((res, rej) => {
  const i = ++id; pending.set(i, { res, rej });
  ws.send(JSON.stringify({ id: i, method: m, params: p }));
  setTimeout(() => { if (pending.has(i)) { pending.delete(i); rej(new Error('t ' + m)); } }, 40000);
});
ws.onmessage = e => {
  const m = JSON.parse(e.data);
  if (m.id && pending.has(m.id)) { const x = pending.get(m.id); pending.delete(m.id); m.error ? x.rej(new Error(m.error.message)) : x.res(m.result); }
  else if (m.method === 'Runtime.exceptionThrown') exc.push((m.params.exceptionDetails.exception?.description || '').slice(0, 200));
};
const ev = async e => (await send('Runtime.evaluate', { returnByValue: true, expression: e, awaitPromise: true })).result.value;
const sleep = ms => new Promise(r => setTimeout(r, ms));

await new Promise((r, j) => { ws.onopen = r; ws.onerror = j; });
await send('Page.enable'); await send('Runtime.enable');
await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });
await send('Page.navigate', { url: BASE + '/login' }); await sleep(700);
await ev(`document.querySelector('input[name=username]').value='admin';document.querySelector('input[name=password]').value='admin123';document.querySelector('form').submit();`);
await sleep(1500);
await send('Page.navigate', { url: BASE + '/report?id=4' }); await sleep(1300);

const TOOLS = `window.__t = {
  items: () => [...document.querySelectorAll('#fieldList .field-item')],
  col: it => it.querySelector('input[name=col_order]').value,
  order: () => window.__t.items().map(window.__t.col).join(','),
  setCheck: (name, on) => { const it = window.__t.items().find(x => window.__t.col(x) === name);
    const cb = it.querySelector('input[type=checkbox]'); cb.checked = on; toggleFieldItem(cb); },
  openFields: () => openPanel('fieldSettingsPanel'),
  applyFields: () => applyFieldSettings(),
  sortItems: () => [...document.querySelectorAll('#sortList .sort-item')].map(it =>
    it.querySelector('input[name=sort_col]').value + ':' + it.querySelector('input[name=sort_dir]').value).join(','),
  addSort: (c, d) => { document.getElementById('newSortCol').value = c;
    document.getElementById('newSortDir').value = d;
    document.querySelector('button[onclick="addSortItem()"]').click(); },
  // 用合成拖拽事件把第 i 项拖到第 j 项位置前
  drag: (container, i, j) => { const items = [...document.querySelectorAll(container + ' > *')];
    const src = items[i], dst = items[j]; if (!src || !dst) return 'no-items';
    const dt = new DataTransfer();
    const fire = (el, type) => el.dispatchEvent(new DragEvent(type, { bubbles: true, cancelable: true, dataTransfer: dt }));
    fire(src, 'dragstart'); fire(dst, 'dragover'); fire(dst, 'drop'); fire(src, 'dragend');
    return 'fired'; },
};`;
const ensureTools = () => ev(TOOLS);

const log = {};
await ensureTools();
log['0 起始'] = { url: await ev('location.search'), order: await ev('window.__t.order()') };

// ① 隐藏 id → 应用（客户端换页）
await ev(`window.__t.openFields()`); await sleep(200);
await ev(`window.__t.setCheck('id', false)`);
await ev(`window.__t.applyFields()`); await sleep(1600);
log['1 隐藏 id 后'] = { url: await ev('location.search'), cols: await ev(`[...document.querySelectorAll('.qf-row td')].map(t=>t.dataset.col).join(',')`) };

// ★ 关键：换页后立刻测拖拽（修复前这里失效）
await ev(`window.__t.openFields()`); await sleep(250);
log['1a 换页后拖拽前顺序'] = await ev(`window.__t.order()`);
await ev(`window.__t.drag('#fieldList', 2, 0)`); await sleep(250);
log['1b 换页后拖拽结果'] = await ev(`window.__t.order()`);

// ② 还原 id → 应用
await ev(`window.__t.setCheck('id', true)`); await sleep(150);
await ev(`window.__t.applyFields()`); await sleep(1600);
log['2 还原 id 后'] = { url: await ev('location.search'), cols: await ev(`[...document.querySelectorAll('.qf-row td')].map(t=>t.dataset.col).join(',')`) };
await ev(`window.__t.openFields()`); await sleep(250);
await ev(`window.__t.drag('#fieldList', 0, 2)`); await sleep(250);
log['2a 第二次换页后拖拽'] = await ev(`window.__t.order()`);

// ③ 排序：加两项 + 应用 + 应用后再拖拽排序项
await ev(`openPanel('sortSettingsPanel')`); await sleep(300);
await ev(`window.__t.addSort('customer','desc')`); await sleep(200);
await ev(`window.__t.addSort('status','asc')`); await sleep(200);
log['3a 排序项'] = await ev(`window.__t.sortItems()`);
await ev(`applySortSettings()`); await sleep(1800);
log['3 应用排序后'] = { url: await ev('location.search'), sortItems: await ev(`window.__t.sortItems()`),
  bar: await ev(`(()=>{const b=document.querySelector('.sort-bar');return b?b.textContent.replace(/\\s+/g,' ').trim().slice(0,50):'无'})()`) };
await ev(`openPanel('sortSettingsPanel')`); await sleep(300);
// 注意拖拽语义：moveSortItem 是"插到目标项之前"，所以 0→1 是 no-op（src 本来就在 dst 前面）。
// 要证明换页后拖拽排序项仍可用，必须反向拖（1→0）或跨项拖。曾用 0→1 得出"顺序没变"的假结论。
await ev(`window.__t.drag('#sortList', 1, 0)`); await sleep(250);
log['3b 换页后拖拽排序项（1→0 反向拖）'] = await ev(`window.__t.sortItems()`);

// ④ 换页后：内联脚本是否重放（导出对话框联动）
await ev(`openPanel('modal-export')`); await sleep(250);
await ev(`document.getElementById('export-format-json').click()`); await sleep(250);
log['4 导出联动（换页后）'] = await ev(`(()=>{const sel=document.getElementById('export-format-select');
  const radios=[...document.querySelectorAll('input[name="charset"]')];
  return {selValue:sel?sel.value:'无', charsetDisabled:radios.every(r=>r.disabled),
          hint:(()=>{const h=document.getElementById('export-charset-json-hint');return h?getComputedStyle(h).display:'无'})()}})()`);

// ⑤ 换页后：嵌套筛选构建器是否渲染
await ev(`openPanel('nfPanel')`); await sleep(400);
log['5 嵌套筛选树节点数（换页后）'] = await ev(`document.querySelectorAll('#nf-tree .nf-leaf, #nf-tree .nf-group').length`);

// ⑥ 换页后：页面级胶水函数是否已重放（_reinitAfterSwap 重建 <main> 内联脚本的判据）
// 注：toggleResultIndex 只在「多结果集」报表才随 build_result_selector_html 输出，
// 本用例的 id=4 是单结果集，故不作为判据（此处只查始终存在的页面胶水函数）。
log['6 换页后页面胶水函数'] = await ev(`[typeof applyFieldSettings, typeof applySortSettings, typeof openPanel, typeof navigateTo].join(',')`);

if (out) { const s = await send('Page.captureScreenshot', { format: 'png' });
  writeFileSync(`${out}/swap-reinit-check.png`, Buffer.from(s.data, 'base64')); }
console.log(JSON.stringify({ log, exceptions: exc }, null, 1));
ws.close(); process.exit(0);

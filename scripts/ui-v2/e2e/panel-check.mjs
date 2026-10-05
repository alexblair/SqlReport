// 报表页弹层功能实测：字段设置 / 排序设置 / 导出对话框 必须能开能关
import { writeFileSync } from 'node:fs';
const BASE = 'http://127.0.0.1:8099';
const port = process.env.CDP_PORT || 9395;
const out = process.argv[2];
const list = await (await fetch(`http://127.0.0.1:${port}/json/new?about:blank`, { method: 'PUT' })).json();
const ws = new WebSocket(list.webSocketDebuggerUrl);
let id = 0; const pending = new Map();
const send = (m, p = {}) => new Promise((res, rej) => {
  const i = ++id; pending.set(i, { res, rej });
  ws.send(JSON.stringify({ id: i, method: m, params: p }));
  setTimeout(() => { if (pending.has(i)) { pending.delete(i); rej(new Error('t ' + m)); } }, 40000);
});
ws.onmessage = e => { const m = JSON.parse(e.data); if (m.id && pending.has(m.id)) { const x = pending.get(m.id); pending.delete(m.id); m.error ? x.rej(new Error(m.error.message)) : x.res(m.result); } };
const evaluate = async (expr) => (await send('Runtime.evaluate', { returnByValue: true, expression: expr })).result.value;

await new Promise((r, j) => { ws.onopen = r; ws.onerror = j; });
await send('Page.enable'); await send('Runtime.enable');
await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });
await send('Page.navigate', { url: BASE + '/login' });
await new Promise(r => setTimeout(r, 700));
await evaluate(`document.querySelector('input[name=username]').value='admin';document.querySelector('input[name=password]').value='admin123';document.querySelector('form').submit();`);
await new Promise(r => setTimeout(r, 1500));
await send('Page.navigate', { url: BASE + '/report?id=1' });
await new Promise(r => setTimeout(r, 1200));

const probe = `(sel) => { const el = document.querySelector(sel); if (!el) return '未找到 ' + sel;
  const cs = getComputedStyle(el); const r = el.getBoundingClientRect();
  return cs.display + ' ' + Math.round(r.width) + 'x' + Math.round(r.height) + ' z=' + cs.zIndex; }`;

const results = {};
// 面板初始必须不可见
results['初始 fieldSettingsPanel'] = await evaluate(`(${probe})('#fieldSettingsPanel')`);
results['初始 backdrop'] = await evaluate(`(${probe})('#report-backdrop')`);
// 点「字段设置」
await evaluate(`document.querySelector('button[onclick*="fieldSettingsPanel"]').click()`);
await new Promise(r => setTimeout(r, 350));
results['点开 字段设置'] = await evaluate(`(${probe})('#fieldSettingsPanel')`);
results['backdrop 此时'] = await evaluate(`(${probe})('#report-backdrop')`);
if (out) { const s = await send('Page.captureScreenshot', { format: 'png' }); writeFileSync(`${out}/panel-field-settings.png`, Buffer.from(s.data, 'base64')); }
// ESC 关闭
await send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 });
await new Promise(r => setTimeout(r, 300));
results['ESC 后'] = await evaluate(`(${probe})('#fieldSettingsPanel')`);
// 点「排序设置」
await evaluate(`document.querySelector('button[onclick*="sortSettingsPanel"]').click()`);
await new Promise(r => setTimeout(r, 350));
results['点开 排序设置'] = await evaluate(`(${probe})('#sortSettingsPanel')`);
await evaluate(`closeAllPanels()`);
// 点「导出」
await evaluate(`document.querySelector('button[onclick*="modal-export"]').click()`);
await new Promise(r => setTimeout(r, 350));
results['点开 导出对话框'] = await evaluate(`(${probe})('#modal-export')`);
if (out) { const s = await send('Page.captureScreenshot', { format: 'png' }); writeFileSync(`${out}/panel-export.png`, Buffer.from(s.data, 'base64')); }

for (const [k, v] of Object.entries(results)) console.log(k.padEnd(22), v);
ws.close(); process.exit(0);

// 检查「有没有全屏遮挡物」：遮罩/抽屉/对话框默认必须不可见
// 用法: CDP_PORT=9391 node veil-check.mjs [截图输出目录]
import { writeFileSync } from 'node:fs';
const BASE = 'http://127.0.0.1:8099';
const port = process.env.CDP_PORT || 9390;
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
await new Promise((r, j) => { ws.onopen = r; ws.onerror = j; });
await send('Page.enable'); await send('Runtime.enable');
await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });
await send('Page.navigate', { url: BASE + '/login' });
await new Promise(r => setTimeout(r, 700));
await send('Runtime.evaluate', { expression: `document.querySelector('input[name=username]').value='admin';document.querySelector('input[name=password]').value='admin123';document.querySelector('form').submit();` });
await new Promise(r => setTimeout(r, 1500));
const PAGES = [
  ['center', '/report'], ['detail', '/report?id=1'], ['reports', '/config/reports'],
  ['overview', '/config'], ['pools', '/config/pools'], ['users', '/config/users'],
  ['api', '/config/api-endpoints'], ['scheduler', '/config/scheduler'],
  ['audit', '/audit'], ['report-edit', '/config/reports/1/edit'],
];
const res = {};
for (const [name, path] of PAGES) {
  await send('Page.navigate', { url: BASE + path });
  await new Promise(r => setTimeout(r, 1000));
  const m = await send('Runtime.evaluate', {
    returnByValue: true,
    expression: `(() => {
      const vw = innerWidth, vh = innerHeight, veil = [];
      document.querySelectorAll('body *').forEach(el => {
        const cs = getComputedStyle(el);
        if (cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity) === 0) return;
        const r = el.getBoundingClientRect();
        const covers = r.width >= vw * 0.8 && r.height >= vh * 0.8;
        if (cs.position === 'fixed' && covers) {
          veil.push((el.id ? '#' + el.id : el.tagName.toLowerCase() + '.' + String(el.className).split(' ').slice(0, 2).join('.')) + ' display=' + cs.display + ' bg=' + cs.backgroundColor);
        }
      });
      return { veil, overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth };
    })()`,
  });
  res[name] = m.result.value;
  if (out) {
    const s = await send('Page.captureScreenshot', { format: 'png' });
    writeFileSync(`${out}/veilcheck-${name}.png`, Buffer.from(s.data, 'base64'));
  }
}
console.log(JSON.stringify(res, null, 1));
ws.close(); process.exit(0);

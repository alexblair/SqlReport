// 截图 + 数值断言：表格横向溢出量、操作列是否在视口内
const [url, out, w = '1440', h = '1600'] = process.argv.slice(2);
const list = await (await fetch('http://127.0.0.1:9333/json/new?' + encodeURIComponent('about:blank'), { method: 'PUT' })).json();
const ws = new WebSocket(list.webSocketDebuggerUrl);
let id = 0; const pending = new Map();
const send = (m, p = {}) => new Promise((res, rej) => { const i = ++id; pending.set(i, { res, rej }); ws.send(JSON.stringify({ id: i, method: m, params: p })); setTimeout(() => { if (pending.has(i)) { pending.delete(i); rej(new Error('timeout ' + m)); } }, 30000); });
ws.onmessage = ev => { const m = JSON.parse(ev.data); if (m.id && pending.has(m.id)) { const p = pending.get(m.id); pending.delete(m.id); m.error ? p.rej(new Error(m.error.message)) : p.res(m.result); } };
await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
await send('Page.enable'); await send('Runtime.enable');
await send('Emulation.setDeviceMetricsOverride', { width: +w, height: +h, deviceScaleFactor: 1, mobile: false });
await send('Page.navigate', { url });
await new Promise(r => setTimeout(r, 3000));
const expr = `JSON.stringify({
  tables: Array.from(document.querySelectorAll('.view-list:not(.hidden)')).map(function(t){
    return { over: t.scrollWidth - t.clientWidth };
  }),
  opsRight: (function(){ var o=document.querySelector('.view-list:not(.hidden) .ops-cell'); if(!o) return null; return Math.round(o.getBoundingClientRect().right); })(),
  bodyOver: document.documentElement.scrollWidth - document.documentElement.clientWidth
})`;
const st = await send('Runtime.evaluate', { expression: expr, returnByValue: true });
console.log('CHECK', st.result.value, 'viewportW=' + w);
const { data } = await send('Page.captureScreenshot', { format: 'png' });
const fs = await import('node:fs');
fs.writeFileSync(out, Buffer.from(data, 'base64'));
console.log('OK', out, fs.statSync(out).size);
process.exit(0);

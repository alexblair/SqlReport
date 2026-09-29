// 导航 → 回读视图状态 → 截图（同会话取证，判定截图与 DOM 是否一致）
const [url, out, w = '1440', h = '900'] = process.argv.slice(2);
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
const st = await send('Runtime.evaluate', { expression: `JSON.stringify({listsHidden: document.querySelectorAll('.view-list.hidden').length, cardsHidden: document.querySelectorAll('.view-card.hidden').length, title: document.title})`, returnByValue: true });
console.log('STATE', st.result.value);
const { data } = await send('Page.captureScreenshot', { format: 'png' });
const fs = await import('node:fs');
fs.writeFileSync(out, Buffer.from(data, 'base64'));
console.log('OK', out, fs.statSync(out).size);
process.exit(0);

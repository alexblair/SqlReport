// CDP 截图：导航 → 等待网络空闲与动画稳定 → Page.captureScreenshot
// 用法: node cdp-shot.mjs <url> <outfile> <width> <height> [jsAfter]
const [url, out, w = '1440', h = '900', jsAfter = ''] = process.argv.slice(2);
const list = await (await fetch('http://127.0.0.1:9333/json/new?' + encodeURIComponent('about:blank'), { method: 'PUT' })).json();
const ws = new WebSocket(list.webSocketDebuggerUrl);
let id = 0; const pending = new Map();
const send = (method, params = {}) => new Promise((res, rej) => {
  const i = ++id; pending.set(i, { res, rej });
  ws.send(JSON.stringify({ id: i, method, params }));
  setTimeout(() => { if (pending.has(i)) { pending.delete(i); rej(new Error('timeout ' + method)); } }, 30000);
});
ws.onmessage = (ev) => {
  const m = JSON.parse(ev.data);
  if (m.id && pending.has(m.id)) { const p = pending.get(m.id); pending.delete(m.id); m.error ? p.rej(new Error(m.error.message)) : p.res(m.result); }
};
const fail = (e) => { console.error('ERR', e.message || e); process.exit(1); };
try {
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
  await send('Page.enable');
  await send('Emulation.setDeviceMetricsOverride', { width: +w, height: +h, deviceScaleFactor: 1, mobile: false });
  await send('Page.navigate', { url });
  await new Promise(r => setTimeout(r, 2500));
  if (jsAfter) { await send('Runtime.evaluate', { expression: jsAfter, awaitPromise: true }); await new Promise(r => setTimeout(r, 800)); }
  const { data } = await send('Page.captureScreenshot', { format: 'png' });
  const fs = await import('node:fs');
  fs.writeFileSync(out, Buffer.from(data, 'base64'));
  console.log('OK', out, fs.statSync(out).size);
  process.exit(0);
} catch (e) { fail(e); }

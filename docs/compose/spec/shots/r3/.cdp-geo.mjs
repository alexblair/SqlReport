const [url, w, h] = process.argv.slice(2);
const list = await (await fetch('http://127.0.0.1:9333/json/new?' + encodeURIComponent('about:blank'), { method: 'PUT' })).json();
const ws = new WebSocket(list.webSocketDebuggerUrl);
let id = 0; const pending = new Map();
const send = (m, p = {}) => new Promise((res, rej) => { const i = ++id; pending.set(i, { res, rej }); ws.send(JSON.stringify({ id: i, method: m, params: p })); setTimeout(() => { if (pending.has(i)) { pending.delete(i); rej(new Error('timeout ' + m)); } }, 30000); });
ws.onmessage = ev => { const m = JSON.parse(ev.data); if (m.id && pending.has(m.id)) { const p = pending.get(m.id); pending.delete(m.id); m.error ? p.rej(new Error(m.error.message)) : p.res(m.result); } };
await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
await send('Page.enable'); await send('Runtime.enable');
await send('Emulation.setDeviceMetricsOverride', { width: +w, height: +h, deviceScaleFactor: 1, mobile: false });
await send('Page.navigate', { url });
await new Promise(r => setTimeout(r, 2500));
await send('Runtime.evaluate', { expression: `document.documentElement.classList.add('sb-rail');document.documentElement.classList.remove('sb-wide');` });
await new Promise(r => setTimeout(r, 400));
const expr = `(function(){
  function r(sel){ var e=document.querySelector(sel); if(!e) return null; var b=e.getBoundingClientRect();
    return {t:Math.round(b.top),b:Math.round(b.bottom),l:Math.round(b.left),rt:Math.round(b.right),h:Math.round(b.height),w:Math.round(b.width)}; }
  return JSON.stringify({
    sidebar:r('.sidebar'), acc:r('.sidebar .account'), av:r('.sidebar .avatar'),
    oi:r('.sidebar .out-icon'), arrow:r('.sb-arrow'), handle:r('.sb-handle'),
    arrowStyle:(document.querySelector('.sb-arrow')||{}).style ? document.querySelector('.sb-arrow').style.top : null,
    vh: window.innerHeight
  });
})()`;
const st = await send('Runtime.evaluate', { expression: expr, returnByValue: true });
console.log(st.result.value);
process.exit(0);

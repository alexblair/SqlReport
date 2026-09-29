const url = process.argv[2];
const list = await (await fetch('http://127.0.0.1:9333/json/new?' + encodeURIComponent('about:blank'), { method: 'PUT' })).json();
const ws = new WebSocket(list.webSocketDebuggerUrl);
let id = 0; const pending = new Map();
const send = (m, p = {}) => new Promise((res, rej) => { const i = ++id; pending.set(i, { res, rej }); ws.send(JSON.stringify({ id: i, method: m, params: p })); setTimeout(() => { if (pending.has(i)) { pending.delete(i); rej(new Error('timeout ' + m)); } }, 20000); });
ws.onmessage = ev => { const m = JSON.parse(ev.data); if (m.id && pending.has(m.id)) { const p = pending.get(m.id); pending.delete(m.id); m.error ? p.rej(new Error(m.error.message)) : p.res(m.result); } };
await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
await send('Page.enable'); await send('Runtime.enable');
await send('Page.navigate', { url });
await new Promise(r => setTimeout(r, 2500));
const expr = `JSON.stringify({
  listsHidden: document.querySelectorAll('.view-list.hidden').length,
  lists: document.querySelectorAll('.view-list').length,
  cardsHidden: document.querySelectorAll('.view-card.hidden').length,
  firstListDisplay: (function(){var e=document.querySelector('.view-list'); return e? getComputedStyle(e).display : 'none-el'})(),
  firstCardDisplay: (function(){var e=document.querySelector('.view-card'); return e? getComputedStyle(e).display : 'none-el'})()
})`;
const r = await send('Runtime.evaluate', { expression: expr, returnByValue: true });
console.log(url.split('/').pop(), r.result.value);
process.exit(0);

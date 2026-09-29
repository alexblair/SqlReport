// 视觉层数值断言（同会话回读 DOM 几何）：溢出/重叠/截断/切换
const [url, mode, w, h] = process.argv.slice(2);
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
if (mode === 'card') { await send('Runtime.evaluate', { expression: `setReportsView('card', false);` }); await new Promise(r => setTimeout(r, 400)); }
if (mode === 'rail') { await send('Runtime.evaluate', { expression: `document.documentElement.classList.add('sb-rail');document.documentElement.classList.remove('sb-wide');` }); await new Promise(r => setTimeout(r, 400)); }
const expr = `(function(){
  var out = {};
  // 1) 列表表格横向溢出
  var tws = document.querySelectorAll('.view-list:not(.hidden)');
  out.tables = Array.from(tws).map(function(t){ return t.scrollWidth - t.clientWidth; });
  // 2) body 溢出
  out.bodyOver = document.documentElement.scrollWidth - document.documentElement.clientWidth;
  // 3) 操作列是否在视口内
  var ops = document.querySelector('.view-list:not(.hidden) .ops-cell');
  out.opsRight = ops ? Math.round(ops.getBoundingClientRect().right) : null;
  // 4) pool-chip 单行（不换行、不包圆饼）
  var chips = document.querySelectorAll('.pool-chip');
  out.chips = chips.length;
  out.chipWrap = Array.from(chips).filter(function(c){ return c.getBoundingClientRect().height > 30; }).length;
  // 5) SQL 列窄 + title 预览存在
  var sqlCell = document.querySelector('.sql-cell');
  out.sqlW = sqlCell ? Math.round(sqlCell.getBoundingClientRect().width) : null;
  out.sqlTitle = sqlCell ? (sqlCell.getAttribute('title') || '').length : 0;
  // 6) 视图切换状态
  out.listsHidden = document.querySelectorAll('.view-list.hidden').length;
  out.cardsHidden = document.querySelectorAll('.view-card.hidden').length;
  // 7) rail 账号区：头像与退出图标纵向排列、互不重叠、不与手柄箭头重叠
  var acc = document.querySelector('.sidebar .account');
  if (acc && document.documentElement.classList.contains('sb-rail')) {
    var av = acc.querySelector('.avatar'), oi = acc.querySelector('.out-icon'), arrow = document.querySelector('.sb-arrow');
    if (av && oi) {
      var a = av.getBoundingClientRect(), b = oi.getBoundingClientRect();
      out.railGap = Math.round(b.top - a.bottom);           // >0 即纵向排列不重叠
      out.railOverlap = !(b.top >= a.bottom || a.top >= b.bottom); // 纵向重叠判定
      if (arrow) { var ar = arrow.getBoundingClientRect();
        out.arrowOverlapsAccount = !(ar.bottom <= acc.getBoundingClientRect().top || ar.top >= acc.getBoundingClientRect().bottom); }
      out.accW = Math.round(acc.getBoundingClientRect().width);
    }
  }
  return JSON.stringify(out);
})()`;
const st = await send('Runtime.evaluate', { expression: expr, returnByValue: true });
console.log(mode, 'w=' + w, st.result.value);
process.exit(0);

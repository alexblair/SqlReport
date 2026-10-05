// 报表页组合场景端到端测试：字段可见性 / 字段顺序 / 筛选 / 排序 / 导出选项交叉
// 用法: CDP_PORT=9403 node e2e-combo.mjs
const BASE = 'http://127.0.0.1:8099';
const port = process.env.CDP_PORT || 9403;
const list = await (await fetch(`http://127.0.0.1:${port}/json/new?about:blank`, { method: 'PUT' })).json();
const ws = new WebSocket(list.webSocketDebuggerUrl);
let id = 0; const pending = new Map(); const logs = [];
const send = (m, p = {}) => new Promise((res, rej) => {
  const i = ++id; pending.set(i, { res, rej });
  ws.send(JSON.stringify({ id: i, method: m, params: p }));
  setTimeout(() => { if (pending.has(i)) { pending.delete(i); rej(new Error('t ' + m)); } }, 60000);
});
ws.onmessage = e => {
  const m = JSON.parse(e.data);
  if (m.id && pending.has(m.id)) { const x = pending.get(m.id); pending.delete(m.id); m.error ? x.rej(new Error(m.error.message)) : x.res(m.result); }
  else if (m.method === 'Log.entryAdded' && m.params.entry.level === 'error') logs.push(m.params.entry.text.slice(0, 120));
};
const ev = async e => (await send('Runtime.evaluate', { returnByValue: true, expression: e, awaitPromise: true })).result.value;
const sleep = ms => new Promise(r => setTimeout(r, ms));

const COLS = `[...document.querySelectorAll('.qf-row td')].map(td=>td.dataset.col)`;
const ROWS = `[...document.querySelectorAll('.table-wrap table tbody tr')].filter(r=>!r.classList.contains('qf-row')).map(r=>[...r.children].map(td=>td.textContent.trim()))`;
const SNAP = `(async()=>({url:location.search, cols:await (${COLS}), rows:await (${ROWS})}))()`;

await new Promise((r, j) => { ws.onopen = r; ws.onerror = j; });
await send('Page.enable'); await send('Runtime.enable'); await send('Log.enable');
await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });
await send('Page.navigate', { url: BASE + '/login' }); await sleep(700);
await ev(`document.querySelector('input[name=username]').value='admin';document.querySelector('input[name=password]').value='admin123';document.querySelector('form').submit();`);
await sleep(1500);

const TOOLS = `window.__t = {
  item: (name) => [...document.querySelectorAll('#fieldList .field-item')]
      .find(it => it.querySelector('input[name="col_order"]').value === name),
  check: (name, on) => { const it = window.__t.item(name); const cb = it.querySelector('input[type=checkbox]');
      cb.checked = on; toggleFieldItem(cb); },
  up: (name) => { const it = window.__t.item(name); it.querySelector('.field-up').click(); },
  openFields: () => openPanel('fieldSettingsPanel'),
  applyFields: () => applyFieldSettings(),
  order: () => [...document.querySelectorAll('#fieldList input[name="col_order"]')].map(i => i.value),
};`;
const ensureTools = async () => { await ev(TOOLS); };

const report = {};
// 页面内工具：按列名定位字段项
await send('Page.navigate', { url: BASE + '/report?id=1&page_size=20' }); await sleep(1400);
await ensureTools();

report['0 起始'] = await ev(SNAP);

// ① 字段可见性：隐藏 customer
await ev(`window.__t.openFields()`); await sleep(250);
await ev(`window.__t.check('customer', false)`);
await ev(`window.__t.applyFields()`); await sleep(1200);
report['1 隐藏 customer'] = await ev(SNAP);

// ② 字段顺序：全选状态下把 amount 上移到 customer 之前（回归：旧实现不发 cols）
await send('Page.navigate', { url: BASE + '/report?id=1&page_size=20' }); await sleep(1200);
await ensureTools();
await ev(`window.__t.openFields()`); await sleep(250);
await ev(`window.__t.up('amount')`);            // amount 上移一格
report['2a 面板顺序'] = await ev(`window.__t.order()`);
await ev(`window.__t.applyFields()`); await sleep(1200);
report['2 仅调顺序(全选)'] = await ev(SNAP);

// ③ 组合：顺序 + 快捷筛选（customer 包含 o）
await ev(`(()=>{const sel=document.querySelector('select[name="op_customer"]');sel.value='contains';
  sel.dispatchEvent(new Event('change',{bubbles:true}));
  const inp=document.querySelector('[name="f_customer"]'); if(inp){inp.disabled=false; inp.value='o';}
  const form=document.getElementById('ff')||document.querySelector('form[action="/report"][method="get"]');
  form.submit();})()`); await sleep(1800);
report['3 顺序+筛选'] = await ev(SNAP);

// ④ 组合：在当前 URL 上再加排序（amount 降序）
await ev(`openPanel('sortSettingsPanel')`); await sleep(300);
await ev(`(()=>{document.getElementById('newSortCol').value='amount';
  document.getElementById('newSortDir').value='desc';
  document.querySelector('button[onclick="addSortItem()"]').click();})()`);
await sleep(250);
await ev(`applySortSettings()`); await sleep(1500);
report['4 顺序+筛选+排序'] = await ev(SNAP);

// ⑤ 再改一次字段顺序（保持筛选/排序/cols 都不丢）
await ev(`window.__t.openFields()`); await sleep(250);
await ev(`window.__t.up('created_at')`);
report['5a 面板顺序'] = await ev(`window.__t.order()`);
await ev(`window.__t.applyFields()`); await sleep(1500);
report['5 再调顺序(应保留筛选+排序)'] = await ev(SNAP);

// ⑥ 导出选项交叉：读表单序列化结果（验证 JS 联动是否正确）
await ev(`openPanel('modal-export')`); await sleep(300);
const exportCase = async (fmt, extra = {}) => {
  await ev(`(()=>{
    const r=document.querySelector('input[name="format"][value="${fmt}"]');
    if(r){ r.checked=true; r.dispatchEvent(new Event('change',{bubbles:true})); }
    ${extra.zip ? `{const z=document.getElementById('export-zip'); if(z){z.checked=true; z.dispatchEvent(new Event('change',{bubbles:true}));}}` : ''}
    ${extra.charset ? `{const c=document.querySelector('input[name="charset"][value="${extra.charset}"]'); if(c){c.checked=true; c.dispatchEvent(new Event('change',{bubbles:true}));}}` : ''}
    ${extra.smart ? `document.querySelectorAll('.smart-quote-cb').forEach((cb,i)=>{cb.checked=true; cb.dispatchEvent(new Event('change',{bubbles:true}));})` : ''}
    ${extra.custom ? `{const u=document.getElementById('use_custom_cols'); if(u){u.checked=true; u.dispatchEvent(new Event('change',{bubbles:true}));}}` : ''}
  })()`);
  await sleep(200);
  const state = await ev(`(()=>{
    const f=document.getElementById('export-form') || document.querySelector('#modal-export form');
    const qs=new URLSearchParams(new FormData(f)).toString();
    const smart=[...document.querySelectorAll('.smart-quote-cb')];
    return {qs, smartDisabled: smart.every(cb=>cb.disabled), smartChecked: smart.filter(cb=>cb.checked).length,
            hiddenSmart:(document.getElementById('smart_quotes')||{}).value};
  })()`);
  const fetched = await ev(`(async()=>{
    const f=document.getElementById('export-form') || document.querySelector('#modal-export form');
    const qs=new URLSearchParams(new FormData(f)).toString();
    try { const res=await fetch('/export?'+qs, {credentials:'same-origin'});
      const ct=res.headers.get('content-type')||''; const cd=res.headers.get('content-disposition')||'';
      const buf=await res.arrayBuffer(); const head=new TextDecoder('utf-8').decode(buf.slice(0,120)).replace(/\\s+/g,' ');
      return {status:res.status, ct, cd:cd.slice(0,60), bytes:buf.byteLength, head};
    } catch(e){ return {error:String(e)}; }
  })()`);
  return { state, fetched };
};
report['6 导出 CSV+UTF8'] = await exportCase('csv', { charset: 'utf8' });
report['7 导出 CSV+GBK+智能去引号'] = await exportCase('csv', { charset: 'gbk', smart: true });
report['8 导出 JSON(智能去引号应禁用)'] = await exportCase('json', {});
report['9 导出 CSV+ZIP'] = await exportCase('csv', { zip: true });
report['10 导出 自定义列'] = await exportCase('csv', { custom: true });

report.__consoleErrors = logs;
console.log(JSON.stringify(report, null, 1));
ws.close(); process.exit(0);

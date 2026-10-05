// /config/api-endpoints「展开 / 收起」实测（真实浏览器 + CDP）。
//
// 覆盖硬性 #17 要求的四种情形：
//   ① 整页加载态     ② 无刷新换页态（navigateTo）
//   ③ 第二/三次操作   ④ 组合序列（主行点击 + 多行并行 + 跨页分类树/详情页签）
// 判据只看 computedStyle.display 与行高（类名切换不算数——历史事故正是
// 「按钮文案变了、面板不动」：CSS 收 .api-row.open，JS 却切 .api-more.on）。
//
// 前置：本地实例 + headless Chrome（见同目录 README.md）
// 运行：CDP_PORT=9411 [BASE=http://127.0.0.1:8099] node scripts/ui-v2/e2e/api-row-expand-check.mjs
const BASE = process.env.BASE || 'http://127.0.0.1:8099';
const port = process.env.CDP_PORT || 9411;

const list = await (await fetch(`http://127.0.0.1:${port}/json/new?about:blank`, { method: 'PUT' })).json();
const ws = new WebSocket(list.webSocketDebuggerUrl);
let id = 0; const pending = new Map();
const send = (m, p = {}) => new Promise((res, rej) => {
  const i = ++id; pending.set(i, { res, rej });
  ws.send(JSON.stringify({ id: i, method: m, params: p }));
  setTimeout(() => { if (pending.has(i)) { pending.delete(i); rej(new Error('超时 ' + m)); } }, 40000);
});
ws.onmessage = e => { const m = JSON.parse(e.data); if (m.id && pending.has(m.id)) { const x = pending.get(m.id); pending.delete(m.id); m.error ? x.rej(new Error(m.error.message)) : x.res(m.result); } };
const evaluate = async (expr) => (await send('Runtime.evaluate', { returnByValue: true, expression: expr })).result.value;
const sleep = ms => new Promise(r => setTimeout(r, ms));

let failed = 0;
const check = (name, ok, detail) => {
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? '   ' + detail : ''}`);
  if (!ok) failed += 1;
};

// 页面内取状态的小工具（注入一次，后续复用）
const PROBE = `(function(){
  window.__mx = function(sel, i){
    var rows = document.querySelectorAll(sel || '.api-row');
    var row = rows[i || 0];
    if (!row) return null;
    var more = row.querySelector('.api-more');
    var btn = row.querySelector('.api-more-btn');
    return { row: row.className, more: more ? more.className : null,
             display: more ? getComputedStyle(more).display : null,
             h: more ? Math.round(more.getBoundingClientRect().height) : null,
             btn: btn ? btn.textContent.trim() : null };
  };
  return 'ready';
})()`;

await new Promise((r, j) => { ws.onopen = r; ws.onerror = j; });
await send('Page.enable'); await send('Runtime.enable');
await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });
await send('Page.navigate', { url: BASE + '/login' });
await sleep(700);
await evaluate(`document.querySelector('input[name=username]').value='admin';document.querySelector('input[name=password]').value='admin123';document.querySelector('form').submit();`);
await sleep(1500);

// ---------------------------------------------------------------- ① 整页加载
await send('Page.navigate', { url: BASE + '/config/api-endpoints' });
await sleep(1400);
await evaluate(PROBE);

let s = await evaluate(`window.__mx()`);
check('① 整页加载：展开区默认收起', s && s.display === 'none' && s.h === 0, JSON.stringify(s));

await evaluate(`document.querySelectorAll('.api-row')[0].querySelector('.api-more-btn').click()`);
await sleep(250);
s = await evaluate(`window.__mx()`);
check('① 点「展开」→ 面板可见', s && s.display === 'block' && s.h > 0 && s.btn.indexOf('收起') === 0, JSON.stringify(s));

await evaluate(`document.querySelectorAll('.api-row')[0].querySelector('.api-more-btn').click()`);
await sleep(250);
s = await evaluate(`window.__mx()`);
check('① 再点一次 → 面板收起（第 2 轮）', s && s.display === 'none' && s.h === 0 && s.btn.indexOf('展开') === 0, JSON.stringify(s));

await evaluate(`document.querySelectorAll('.api-row')[0].querySelector('.api-more-btn').click()`);
await sleep(250);
s = await evaluate(`window.__mx()`);
check('① 第 3 轮点开 → 仍可见（多轮不脱节）', s && s.display === 'block' && s.h > 0, JSON.stringify(s));

// 收起，准备组合测试
await evaluate(`document.querySelectorAll('.api-row')[0].querySelector('.api-more-btn').click()`);
await sleep(200);

// ---------------------------------------------------------------- ④ 组合序列
const rowCount = await evaluate(`document.querySelectorAll('.api-row').length`);
if (rowCount >= 2) {
  await evaluate(`document.querySelectorAll('.api-row')[0].querySelector('.api-more-btn').click()`);
  await evaluate(`document.querySelectorAll('.api-row')[1].querySelector('.api-more-btn').click()`);
  await sleep(250);
  const a = await evaluate(`window.__mx('.api-row', 0)`);
  const b = await evaluate(`window.__mx('.api-row', 1)`);
  check('④ 两行并行展开互不干扰', a && b && a.display === 'block' && b.display === 'block',
        `row0=${a && a.display} row1=${b && b.display}`);
  await evaluate(`document.querySelectorAll('.api-row')[0].querySelector('.api-more-btn').click()`);
  await sleep(200);
  const a2 = await evaluate(`window.__mx('.api-row', 0)`);
  const b2 = await evaluate(`window.__mx('.api-row', 1)`);
  check('④ 只收起第 1 行，第 2 行保持展开', a2 && b2 && a2.display === 'none' && b2.display === 'block',
        `row0=${a2 && a2.display} row1=${b2 && b2.display}`);
  await evaluate(`document.querySelectorAll('.api-row')[1].querySelector('.api-more-btn').click()`);
  await sleep(200);
} else {
  console.log(`SKIP  ④ 组合序列（接口行只有 ${rowCount} 行，无法并行验证）`);
}

// 主行非交互区点击（apiMainClick 路径）
await evaluate(`document.querySelectorAll('.api-row')[0].querySelector('.path-chip').click()`);
await sleep(250);
s = await evaluate(`window.__mx()`);
check('④ 点主行路径区 → 展开（apiMainClick 路径）', s && s.display === 'block' && s.h > 0, JSON.stringify(s));
await evaluate(`document.querySelectorAll('.api-row')[0].querySelector('.path-chip').click()`);
await sleep(250);
s = await evaluate(`window.__mx()`);
check('④ 再点主行路径区 → 收起', s && s.display === 'none', JSON.stringify(s));

// ---------------------------------------------------------------- ② 无刷新换页态
const nav = await evaluate(`(typeof window.navigateTo === 'function') ? (window.navigateTo('/config/api-endpoints'), 'ok') : 'no navigateTo'`);
await sleep(1600);
await evaluate(PROBE);
s = await evaluate(`window.__mx()`);
check('② 换页后初始态：仍默认收起', s && s.display === 'none', `${nav} ${JSON.stringify(s)}`);
await evaluate(`document.querySelectorAll('.api-row')[0].querySelector('.api-more-btn').click()`);
await sleep(250);
s = await evaluate(`window.__mx()`);
check('② 换页后点「展开」→ 面板可见', s && s.display === 'block' && s.h > 0, JSON.stringify(s));
await evaluate(`document.querySelectorAll('.api-row')[0].querySelector('.api-more-btn').click()`);
await sleep(250);
s = await evaluate(`window.__mx()`);
check('② 换页后收起 → 面板隐藏', s && s.display === 'none', JSON.stringify(s));

// ---------------------------------------------------------------- ③ 分类树折叠（/config/reports）
await send('Page.navigate', { url: BASE + '/config/reports' });
await sleep(1600);
let k = await evaluate(`(function(){
  var c = document.querySelector('.tree .cat[data-kids]');
  if (!c) return {err: 'no .cat[data-kids]'};
  window.__k = c;
  var el = document.getElementById(c.getAttribute('data-kids'));
  return {cls: el.className, display: getComputedStyle(el).display, h: Math.round(el.getBoundingClientRect().height)};
})()`);
check('③ 分类树：初始展开（markup 带 on）', k && k.display === 'block' && k.h > 0, JSON.stringify(k));
await evaluate(`window.__k.click()`);
await sleep(250);
k = await evaluate(`(function(){var el=document.getElementById(window.__k.getAttribute('data-kids'));return {cls:el.className,display:getComputedStyle(el).display,h:Math.round(el.getBoundingClientRect().height)};})()`);
const kFolded = k && k.display === 'none' && k.h === 0;
check('③ 点父分类行 → 子分类收起', kFolded, JSON.stringify(k));
await evaluate(`window.__k.click()`);
await sleep(250);
k = await evaluate(`(function(){var el=document.getElementById(window.__k.getAttribute('data-kids'));return {cls:el.className,display:getComputedStyle(el).display,h:Math.round(el.getBoundingClientRect().height)};})()`);
check('③ 再点一次 → 子分类展开（第 2 轮）', kFolded && k && k.display === 'block' && k.h > 0, JSON.stringify(k));

// ---------------------------------------------------------------- ③ 报表中心分类树（/report）
await send('Page.navigate', { url: BASE + '/report' });
await sleep(1600);
const rc = await evaluate(`(function(){
  var c = document.querySelector('#rc-tree .cat[data-has-kids="1"]');
  var k = c && c.nextElementSibling;
  if (!c || !k) return {err: 'no rc-tree kids'};
  window.__rc = c;
  return {cls: k.className, display: getComputedStyle(k).display};
})()`);
const rcFolded = rc && rc.display === 'none';
check('③ 报表中心：子分类默认收起（chevron 朝右）', rcFolded, JSON.stringify(rc));
// SVGElement 没有 .click()，必须发真实冒泡事件（事件委托靠 e.target.closest 命中）
await evaluate(`window.__rc.querySelector('[data-chevron]').dispatchEvent(new MouseEvent('click', {bubbles: true}))`);
await sleep(300);
const rc2 = await evaluate(`(function(){var k=window.__rc.nextElementSibling;return {cls:k.className,display:getComputedStyle(k).display,h:Math.round(k.getBoundingClientRect().height)};})()`);
check('③ 报表中心：点 chevron → 子分类展开', rcFolded && rc2 && rc2.display === 'block' && rc2.h > 0, JSON.stringify(rc2));

// ---------------------------------------------------------------- ③ 报表详情页 API 页签
await send('Page.navigate', { url: BASE + '/report?id=1' });
await sleep(2000);
const tab = await evaluate(`(typeof gotoTab === 'function') ? (gotoTab('api'), 'ok') : 'no gotoTab'`);
await sleep(400);
const det = await evaluate(`(function(){
  var rows = document.querySelectorAll('.api-row');
  if (!rows.length) return {err: 'no api-row（该报表可能无接口）'};
  var m = rows[0].querySelector('.api-more');
  var before = getComputedStyle(m).display;
  rows[0].querySelector('.api-more-btn').click();
  return {before: before, cls: m.className, row: rows[0].className, display: getComputedStyle(m).display,
          h: Math.round(m.getBoundingClientRect().height), rows: rows.length};
})()`);
check('③ 详情页 API 页签：点展开 → 面板可见', det && det.before === 'none' && det.display === 'block' && det.h > 0, `${tab} ${JSON.stringify(det)}`);

console.log(failed ? `\n结果：${failed} 项 FAIL` : '\n结果：全部 PASS');
ws.close();
process.exit(failed ? 1 : 0);

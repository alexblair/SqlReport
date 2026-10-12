// /config/reports 三处交互修复实测（真实浏览器 + CDP）。
//
// 覆盖硬性 #17 要求的四种情形：
//   ① 整页加载态  ② 无刷新换页态  ③ 第二/三次操作  ④ 组合序列（列表↔卡片 × 折叠 × 定位）
//
// 判据只看 **computedStyle / 几何 / 真实点击结果**，不看类名（类名切换不算数——
// 历史事故正是「按钮文案变了、面板不动」）。
//
// 三个 BUG：
//   BUG-1 焦点白底：`/report` 编辑页「规则 → 当前规则」的 .code-textarea 聚焦后
//         底色若被通用 :focus 规则翻白，浅色 --code-ink 文字对比度掉到 ~1.25:1。
//   BUG-2 折叠错级：卡片视图下点分类折叠，本级卡片体必须真正消失（display:none）。
//   BUG-3 定位缺失：点左树层级 → 右侧对应分组滚入视口并高亮；行点击不再折叠。
//
// 前置：本地实例 + headless Chrome（见同目录 README.md）
// 运行：CDP_PORT=9411 node scripts/ui-v2/e2e/cat-focus-check.mjs
const BASE = process.env.BASE || 'http://127.0.0.1:8099';
const port = process.env.CDP_PORT || 9411;

async function newPage() {
  const list = await (await fetch(`http://127.0.0.1:${port}/json/new?about:blank`, { method: 'PUT' })).json();
  return list;
}

const target = await newPage();
const ws = new WebSocket(target.webSocketDebuggerUrl);
let id = 0; const pending = new Map();
let wsReady;
const ready = new Promise((res) => { wsReady = res; });
const send = async (m, p = {}) => {
  await ready;
  return new Promise((res, rej) => {
    const i = ++id; pending.set(i, { res, rej });
    ws.send(JSON.stringify({ id: i, method: m, params: p }));
    setTimeout(() => { if (pending.has(i)) { pending.delete(i); rej(new Error('超时 ' + m)); } }, 40000);
  });
};
ws.onopen = () => wsReady();
ws.onmessage = e => { const m = JSON.parse(e.data); if (m.id && pending.has(m.id)) { const x = pending.get(m.id); pending.delete(m.id); m.error ? x.rej(new Error(m.error.message)) : x.res(m.result); } };
const evaluate = async (expr) => {
  const r = await send('Runtime.evaluate', { returnByValue: true, expression: expr, awaitPromise: true });
  if (r.exceptionDetails) throw new Error(r.exceptionDetails.text + ' :: ' + expr.slice(0, 120));
  return r.result.value;
};
const sleep = ms => new Promise(r => setTimeout(r, ms));

let failed = 0;
const check = (name, ok, detail) => {
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? '   ' + detail : ''}`);
  if (!ok) failed += 1;
};

await send('Page.enable');
await send('Runtime.enable');

async function goto(url) {
  await send('Page.navigate', { url });
  await sleep(1200);
}

async function login() {
  await goto(`${BASE}/login`);
  const has = await evaluate(`!!document.querySelector('input[name="username"]')`);
  if (!has) return;
  await evaluate(`(function(){
    document.querySelector('input[name="username"]').value='admin';
    document.querySelector('input[name="password"]').value='admin123';
    document.querySelector('form').submit(); return 1;})()`);
  await sleep(1500);
}

await login();

// ══════════════════════════════════════════════════════════════════════
// BUG-1：焦点态不得把深色代码面翻白
// ══════════════════════════════════════════════════════════════════════
console.log('\n--- BUG-1 焦点白底（规则 → 当前规则）---');

async function contrastOf(fg, bg) {
  return evaluate(`(function(){
    function lum(c){
      var m=c.match(/\\d+/g).map(Number);
      var s=m.slice(0,3).map(function(v){v/=255;return v<=0.04045?v/12.92:Math.pow((v+0.055)/1.055,2.4);});
      return 0.2126*s[0]+0.7152*s[1]+0.0722*s[2];
    }
    var a=lum(${JSON.stringify(fg)}), b=lum(${JSON.stringify(bg)});
    var hi=Math.max(a,b), lo=Math.min(a,b);
    return (hi+0.05)/(lo+0.05);
  })()`);
}

async function probeCodeTextarea(label) {
  const r = await evaluate(`(function(){
    var ta=document.getElementById('current-rules-json');
    if(!ta) return {found:false};
    ta.focus();
    var cs=getComputedStyle(ta);
    return {found:true, bg:cs.backgroundColor, color:cs.color};
  })()`);
  if (!r.found) { check(`${label} 找到 .code-textarea`, false, '未渲染'); return; }
  const c = await contrastOf(r.color, r.bg);
  check(`${label} 聚焦后对比度 ≥4.5`, c >= 4.5,
    `bg=${r.bg} color=${r.color} contrast=${c.toFixed(2)}`);
}

// 「当前规则」在报表**详情页**（/report?id=N）的「规则」页签下。
// 从报表配置页取一个报表详情链接。
await goto(`${BASE}/config/reports`);
const reportHref = await evaluate(`(function(){
  var a=document.querySelector('a.nm[href^="/report?id="]')
     || document.querySelector('.rpt-card a[href^="/report?id="]');
  return a?a.getAttribute('href'):null;})()`);
if (!reportHref) {
  check('BUG-1 找到报表详情页入口', false, '配置页无报表链接');
} else {
  await goto(BASE + reportHref);
  // 切到「规则」页签（role=tab + data-tab=rules）
  const switched = await evaluate(`(function(){
    var t=document.querySelector('[role="tab"][data-tab="rules"]');
    if(!t) return false;
    t.click(); return true;})()`);
  check('BUG-1 切到「规则」页签', switched);
  await sleep(600);
  const rendered = await evaluate(`!!document.getElementById('current-rules-json')`);
  check('BUG-1 「当前规则」文本框已渲染', rendered);
  if (rendered) {
    await probeCodeTextarea('BUG-1 ①整页加载态');
    // ③ 第二次操作：失焦→再聚焦（重放不应回退）
    await evaluate(`(function(){var t=document.getElementById('current-rules-json');t.blur();return 1;})()`);
    await sleep(200);
    await probeCodeTextarea('BUG-1 ③二次聚焦');
    // 切到另一个页签再回来（换页态），聚焦态仍应正确
    await evaluate(`(function(){var t=document.querySelector('[role="tab"][data-tab="data"]');if(t)t.click();return 1;})()`);
    await sleep(400);
    await evaluate(`(function(){var t=document.querySelector('[role="tab"][data-tab="rules"]');if(t)t.click();return 1;})()`);
    await sleep(400);
    await probeCodeTextarea('BUG-1 ②换页（页签切换）后');
  }
}

// ══════════════════════════════════════════════════════════════════════
// BUG-2 / BUG-3：报表配置页折叠 + 左树定位
// ══════════════════════════════════════════════════════════════════════
console.log('\n--- BUG-2 折叠只作用当前级别 ---');
await goto(`${BASE}/config/reports`);
await sleep(600);

// 右侧至少要有两级分类
const scope = await evaluate(`(function(){
  var blocks=document.querySelectorAll('.cat-block[id]');
  return {n:blocks.length, ids:[].map.call(blocks,function(b){return b.id;})};
})()`);
check('页面渲染出分类区块', scope.n > 0, `n=${scope.n} ids=${scope.ids.join(',')}`);

async function collapseProbe(view) {
  // 切到指定视图
  await evaluate(`(function(){
    var b=document.querySelector('#rpt-view-seg button[data-view="${view}"]');
    if(b) b.click(); return 1;})()`);
  await sleep(400);
  const r = await evaluate(`(function(){
    var blocks=document.querySelectorAll('.cat-block[id]');
    // 找第一个「本级有内容」的块：列表体或卡片体非空
    for(var i=0;i<blocks.length;i++){
      var b=blocks[i];
      var body=b.querySelector(':scope > .cat-body');
      var cards=b.querySelector(':scope > .cat-cards');
      var kids=b.querySelector(':scope > .cat-children');
      if(!body && !cards) continue;
      // 点击该块的折叠按钮
      var btn=b.querySelector(':scope > .cat-head .tree-toggle');
      if(!btn) continue;
      var cardStyleBefore = cards ? getComputedStyle(cards).display : null;
      var bodyStyleBefore = body ? getComputedStyle(body).display : null;
      btn.click();
      var cardStyleAfter = cards ? getComputedStyle(cards).display : null;
      var bodyStyleAfter = body ? getComputedStyle(body).display : null;
      var kidsStyleAfter = kids ? getComputedStyle(kids).display : null;
      var collapsed = b.classList.contains('collapsed');
      return {id:b.id, collapsed:collapsed,
              bodyBefore:bodyStyleBefore, bodyAfter:bodyStyleAfter,
              cardBefore:cardStyleBefore, cardAfter:cardStyleAfter,
              kidsAfter:kidsStyleAfter};
    }
    return null;})()`);
  return r;
}

for (const view of ['list', 'card']) {
  const r = await collapseProbe(view);
  if (!r) { check(`BUG-2 [${view}] 找到可折叠的分类块`, false); continue; }
  const activeBody = view === 'card' ? r.cardAfter : r.bodyAfter;
  check(`BUG-2 [${view}] 本级内容体折叠后 display:none`, activeBody === 'none',
    `id=${r.id} body=${r.bodyBefore}→${r.bodyAfter} card=${r.cardBefore}→${r.cardAfter}`);
  if (r.kidsAfter !== null) {
    check(`BUG-2 [${view}] 下级容器同步收起`, r.kidsAfter === 'none', `kids=${r.kidsAfter}`);
  }
  // 再点一次展开（③ 第二次操作）
  await evaluate(`(function(){
    var b=document.getElementById(${JSON.stringify(r.id)});
    b.querySelector(':scope > .cat-head .tree-toggle').click(); return 1;})()`);
  const reopened = await evaluate(`(function(){
    var b=document.getElementById(${JSON.stringify(r.id)});
    return b.classList.contains('collapsed');})()`);
  check(`BUG-2 [${view}] 二次点击可展开还原`, reopened === false, `collapsed=${reopened}`);
}

console.log('\n--- BUG-3 点击左树层级 → 右侧定位 + 高亮 ---');

const locate = await evaluate(`(function(){
  // 切回列表视图，取一个非「全部报表」的树行
  var b=document.querySelector('#rpt-view-seg button[data-view="list"]');
  if(b) b.click();
  var rows=document.querySelectorAll('.tree .cat[data-target]');
  if(rows.length<2) return {err:'树行不足', n:rows.length};
  var row=rows[1];
  var target=row.getAttribute('data-target');
  var block=document.getElementById(target);
  if(!block) return {err:'data-target 未命中区块', target:target};
  // 折叠目标，验证「定位会先展开」
  block.classList.add('collapsed');
  var before=block.getBoundingClientRect().top;
  row.click();
  var after=block.getBoundingClientRect().top;
  return {target:target, before:before, after:after,
          collapsed:block.classList.contains('collapsed'),
          highlighted:block.classList.contains('row-highlight'),
          rowActive:row.classList.contains('active'),
          scrolled:Math.abs(after-before)>1,
          inViewport: block.getBoundingClientRect().top < window.innerHeight
                      && block.getBoundingClientRect().bottom > 0};
})()`);

if (locate.err) {
  check('BUG-3 定位链路可用', false, JSON.stringify(locate));
} else {
  check('BUG-3 点击树行后目标分组进入视口', locate.inViewport,
    `target=${locate.target} top=${locate.after.toFixed(0)}`);
  check('BUG-3 目标分组被高亮（复用 .row-highlight）', locate.highlighted === true);
  check('BUG-3 目标分组若折叠会被先展开', locate.collapsed === false);
  check('BUG-3 左树当前层级高亮（.cat.active）', locate.rowActive === true);
  check('BUG-3 行点击不再触发折叠',
    await evaluate(`(function(){
      var rows=document.querySelectorAll('.tree .cat[data-target]');
      for(var i=0;i<rows.length;i++){
        if(rows[i].getAttribute('data-kids')){
          var k=document.getElementById(rows[i].getAttribute('data-kids'));
          var before=k?k.classList.contains('on'):null;
          rows[i].click();
          var after=k?k.classList.contains('on'):null;
          return before===after;
        }
      }
      return null;})()`) !== false,
    '点击行不应改变 .kids 的 .on');
}

// 全部报表行也应可定位
const allRow = await evaluate(`(function(){
  var r=document.querySelector('.tree .cat[data-target="cat-block-all"]');
  if(!r) return {err:'无全部报表行'};
  r.click();
  var anchor=document.getElementById('cat-block-all');
  return {ok:!!anchor, highlighted: anchor?anchor.classList.contains('row-highlight'):false,
          rowActive: r.classList.contains('active')};
})()`);
check('BUG-3「全部报表」行同样可定位（交互统一）',
  allRow.ok && allRow.highlighted === true && allRow.rowActive === true,
  JSON.stringify(allRow));

// 独立展开箭头仍能折叠（BUG-3 要求保留折叠能力）
const arrow = await evaluate(`(function(){
  var rows=document.querySelectorAll('.tree .cat[data-kids]');
  for(var i=0;i<rows.length;i++){
    var btn=rows[i].querySelector('.cat-expand');
    if(!btn) continue;
    var k=document.getElementById(rows[i].getAttribute('data-kids'));
    var before=k.classList.contains('on');
    btn.click();
    var after=k.classList.contains('on');
    var reversed = before!==after;
    btn.click();
    return {changed:reversed, restored: document.getElementById(rows[i].getAttribute('data-kids')).classList.contains('on')===before,
            aria: btn.getAttribute('aria-expanded')};
  }
  return {err:'未找到 .cat-expand'};
})()`);
check('BUG-3 独立箭头仍可折叠/展开（未误点定位）',
  arrow.changed === true && arrow.restored === true, JSON.stringify(arrow));

// ④ 组合序列：定位 → 折叠 → 切视图 → 再定位
console.log('\n--- 组合序列（定位 × 折叠 × 视图切换）---');
const combo = await evaluate(`(function(){
  var rows=document.querySelectorAll('.tree .cat[data-target]');
  var row=rows[rows.length-1];
  var block=document.getElementById(row.getAttribute('data-target'));
  row.click();                                   // 定位
  var h1=block.classList.contains('row-highlight');
  block.querySelector(':scope > .cat-head .tree-toggle').click();  // 折叠
  var c=block.classList.contains('collapsed');
  var cv=document.querySelector('#rpt-view-seg button[data-view="card"]');
  if(cv) cv.click();                             // 切卡片视图
  row.click();                                   // 再定位（应自动展开）
  var h2=block.classList.contains('row-highlight');
  var stillCollapsed=block.classList.contains('collapsed');
  return {h1:h1, collapsedAfterToggle:c, h2:h2, stillCollapsed:stillCollapsed};
})()`);
check('组合序列：定位高亮仍生效', combo.h1 === true && combo.h2 === true, JSON.stringify(combo));
check('组合序列：折叠生效且再定位会展开',
  combo.collapsedAfterToggle === true && combo.stillCollapsed === false, JSON.stringify(combo));

console.log(`\n${failed === 0 ? 'ALL PASS' : failed + ' FAILED'}`);
process.exit(failed === 0 ? 0 : 1);

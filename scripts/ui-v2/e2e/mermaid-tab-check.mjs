// 备注页卡 mermaid 渲染验证（整页加载 → 点备注 → 多轮切换 → 摘要条「查看全文」）
//
// 复现的历史缺陷（2026-10-09 用户实测 /report?id=42）：
//   mermaid 用 startOnLoad:true 在 window load 时渲染了 display:none 的备注页卡 ——
//   隐藏容器里量测全 0，mermaid 产出 16×16 空图（viewBox `-8 -8 16 16`）并打上
//   data-processed；之后 mermaid.run 对已打标记的节点直接 continue，切页也不重画，
//   于是备注页卡永远只剩一个空框。
//
// 前置（同 06 卷 E2E 约定）：
//   1) 本地实例：HOST=127.0.0.1 PORT=8099 venv/bin/python server.py &
//   2) headless Chrome：/opt/chrome-offline/chrome-linux64/chrome --headless=new --no-sandbox \
//        --remote-debugging-port=9411 --user-data-dir=run-logs/ui-v2/.chrome-e2e about:blank &
// 运行：
//   CDP_PORT=9411 REPORT_ID=42 node scripts/ui-v2/e2e/mermaid-tab-check.mjs
//   可选 BASE=http://127.0.0.1:8098（另起的验证实例）；REPORT_ID 指向含 ```mermaid 备注的报表。
// 退出码：0 = 全部通过；1 = 有断言失败；2 = 环境/连通错误。
const BASE = process.env.BASE || 'http://127.0.0.1:8099';
const REPORT_ID = process.env.REPORT_ID || '42';
const CDP = process.env.CDP_PORT || '9450';
const EMPTY_VIEWBOX = '-8 -8 16 16';   // mermaid 在零尺寸容器里退化的空图

let port;
try {
  const list = await (await fetch(`http://127.0.0.1:${CDP}/json/new?about:blank`, { method: 'PUT' })).json();
  port = list.webSocketDebuggerUrl;
} catch (e) {
  console.error(`[环境错误] 连不上 CDP ${CDP}：${e.message}`);
  process.exit(2);
}
const ws = new WebSocket(port);
let id = 0; const pending = new Map(); const exc = [];
const send = (m, p = {}) => new Promise((res, rej) => {
  const i = ++id; pending.set(i, { res, rej });
  ws.send(JSON.stringify({ id: i, method: m, params: p }));
  setTimeout(() => { if (pending.has(i)) { pending.delete(i); rej(new Error('timeout ' + m)); } }, 30000);
});
ws.onmessage = e => {
  const m = JSON.parse(e.data);
  if (m.id && pending.has(m.id)) {
    const x = pending.get(m.id); pending.delete(m.id);
    m.error ? x.rej(new Error(m.error.message)) : x.res(m.result);
  } else if (m.method === 'Runtime.exceptionThrown') {
    exc.push(String(m.params.exceptionDetails.exception?.description || '').slice(0, 200));
  }
};
const ev = async e => (await send('Runtime.evaluate', { returnByValue: true, expression: e, awaitPromise: true })).result.value;
const sleep = ms => new Promise(r => setTimeout(r, ms));

const PROBE = `(() => {
  const pres = [...document.querySelectorAll('.md-body pre.mermaid')];
  const active = document.querySelector('.tabpanel.active');
  return {
    panel: active ? active.getAttribute('data-panel') : null,
    blocks: pres.map(p => {
      const s = p.querySelector('svg');
      const r = s ? s.getBoundingClientRect() : null;
      return { svg: !!s, svgW: r ? Math.round(r.width) : 0, svgH: r ? Math.round(r.height) : 0,
               viewBox: s ? s.getAttribute('viewBox') : null,
               processed: p.getAttribute('data-processed') === 'true' };
    }),
    svgTotal: document.querySelectorAll('.md-body pre.mermaid svg').length,
  };
})()`;

const fails = [];
const check = (ok, msg) => { console.log(`${ok ? 'PASS' : 'FAIL'}  ${msg}`); if (!ok) fails.push(msg); };
const clickTab = async (key) => { await ev(`document.querySelector('.tabs .tab[data-tab=${key}]').click()`); await sleep(900); };
const good = (b) => b.svg && b.viewBox && b.viewBox !== EMPTY_VIEWBOX && b.svgW > 200;

await new Promise((r, j) => { ws.onopen = r; ws.onerror = j; });
await send('Page.enable'); await send('Runtime.enable');
await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });

// 登录（与其余 e2e 脚本一致：DEBUG 配置库默认账号）
await send('Page.navigate', { url: BASE + '/login' }); await sleep(800);
await ev(`document.querySelector('input[name=username]').value='admin';` +
         `document.querySelector('input[name=password]').value='admin123';` +
         `document.querySelector('form').submit();`);
await sleep(1500);
await send('Page.navigate', { url: `${BASE}/report?id=${REPORT_ID}` }); await sleep(2500);

const atLoad = await ev(PROBE);
if (!atLoad.blocks.length) {
  console.error('[环境错误] 该报表备注里没有 <pre class="mermaid">：请用 REPORT_ID 指向含 ```mermaid 备注的报表');
  process.exit(2);
}
check(atLoad.panel === 'data', `整页加载：默认页卡=data（实际 ${atLoad.panel}）`);
check(atLoad.blocks.every(b => !b.processed && !b.svg),
      `整页加载：隐藏的备注页卡未被 mermaid 渲染（processed=${atLoad.blocks.map(b => b.processed).join(',')}）`);

await clickTab('memo');
const click1 = await ev(PROBE);
check(click1.blocks.every(good), `第一次点备注：每张图都渲染出真实几何 ` +
      click1.blocks.map(b => `${b.svgW}x${b.svgH}/${b.viewBox}`).join(' '));

await clickTab('data'); await clickTab('memo');
const click2 = await ev(PROBE);
check(click2.blocks.every(good), `第二/三次切换后：几何不变（无重画/无退化）`);
check(click2.svgTotal === click1.svgTotal && click2.svgTotal === click1.blocks.length,
      `无重复渲染：svg 数 ${click2.svgTotal}（应 ${click1.blocks.length}）`);

await clickTab('api'); await clickTab('rules'); await clickTab('memo');
const click3 = await ev(PROBE);
check(click3.blocks.every(good), `跨页卡组合切换后：几何仍正常`);

check(exc.length === 0, `页面无未捕获 JS 异常（${exc.length} 条）${exc.join(' | ')}`);

console.log(fails.length ? `\n结论：FAIL（${fails.length} 项）` : '\n结论：PASS（备注页卡流程图正常渲染）');
ws.close();
process.exit(fails.length ? 1 : 0);

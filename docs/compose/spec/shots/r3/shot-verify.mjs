// shot-verify.mjs —— 截图与渲染一致性验证（唯一可信截图管线）
// 用法: node shot-verify.mjs '<JSON specs>'
// 每项: {n:名称, u:url, o:输出png, w:宽, h:高, y:滚动位置?, sw:期望侧栏宽?}
// 流程: 导航 → 等字体/图片/双 rAF → 滚动 → 注入角标+关动画 → DOM 探针 → 截图 → 像素回验
// 单视口截图（禁止滚动拼接）；像素回验 FAIL 即非零退出——不一致的图不得用于任何判断。
const specs = JSON.parse(process.argv[2]);
const CDP = 'http://127.0.0.1:9333';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let failed = 0;

async function openSession(target) {
  const ws = new WebSocket(target.webSocketDebuggerUrl);
  let id = 0; const pending = new Map();
  ws.onmessage = (ev) => {
    const m = JSON.parse(ev.data);
    if (m.id && pending.has(m.id)) { const p = pending.get(m.id); pending.delete(m.id); m.error ? p.rej(new Error(m.error.message)) : p.res(m.result); }
  };
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
  return {
    send: (method, params = {}) => new Promise((res, rej) => {
      const i = ++id; pending.set(i, { res, rej });
      ws.send(JSON.stringify({ id: i, method, params }));
      setTimeout(() => { if (pending.has(i)) { pending.delete(i); rej(new Error('timeout ' + method)); } }, 30000);
    }),
    close: () => { try { ws.close(); } catch (e) {} },
  };
}

for (const sp of specs) {
  try {
    const t = await (await fetch(`${CDP}/json/new?${encodeURIComponent('about:blank')}`, { method: 'PUT' })).json();
    const s = await openSession(t);
    await s.send('Page.enable'); await s.send('Runtime.enable');
    await s.send('Emulation.setDeviceMetricsOverride', { width: sp.w, height: sp.h, deviceScaleFactor: 1, mobile: false });
    await s.send('Page.navigate', { url: sp.u });
    await sleep(1500);
    // 等字体/图片/双 rAF（渲染稳定判据）
    await s.send('Runtime.evaluate', {
      awaitPromise: true,
      expression: `(async function(){ if (document.fonts && document.fonts.ready) await document.fonts.ready;
        var imgs = Array.prototype.slice.call(document.images || []);
        await Promise.all(imgs.map(function(i){ return i.complete ? 0 : new Promise(function(r){ i.onload = i.onerror = r; }); }));
        await new Promise(function(r){ requestAnimationFrame(function(){ requestAnimationFrame(r); }); });
        return 'ok'; })()`,
    });
    if (sp.y) { await s.send('Runtime.evaluate', { expression: `window.scrollTo(0, ${sp.y});` }); await sleep(400); }
    // 关动画 + 注入角标（对齐基准），返回 DOM 探针
    const probeRes = await s.send('Runtime.evaluate', {
      returnByValue: true,
      expression: `(function(){
        var st = document.createElement('style');
        st.textContent = '*,*::before,*::after{animation:none!important;transition:none!important}';
        document.head.appendChild(st);
        function mk(color, pos){ var d = document.createElement('div');
          d.style.cssText = 'position:fixed;'+pos+';width:24px;height:24px;background:'+color+';z-index:2147483647;pointer-events:none';
          document.body.appendChild(d); return d.getBoundingClientRect(); }
        var m1 = mk('#ff0000', 'top:0;left:0');
        var m2 = mk('#00ff00', 'bottom:0;left:0');
        function parse(c){ var m = String(c).match(/(\\d+)[, ]+(\\d+)[, ]+(\\d+)/); return m ? [+m[1], +m[2], +m[3]] : null; }
        function pt(name, el, dx, dy, viaStyle){
          if (!el) return null;
          var r = el.getBoundingClientRect();
          if (r.width < 2 || r.height < 2) return null;  // 隐藏形态跳过
          return { n: name, x: r.left + dx, y: r.top + dy, rgb: viaStyle ? parse(getComputedStyle(el).backgroundColor) : viaStyle };
        }
        var out = [];
        out.push({ n: 'marker-tl', x: m1.left + 12, y: m1.top + 12, rgb: [255, 0, 0] });
        out.push({ n: 'marker-bl', x: m2.left + 12, y: m2.top + 12, rgb: [0, 255, 0] });
        var sb = document.querySelector('.sidebar');
        if (sb) { var r = sb.getBoundingClientRect();
          out.push({ n: 'sidebar-bg', x: r.left + 3, y: r.top + 120, rgb: parse(getComputedStyle(sb).backgroundColor) });
          out.push({ n: 'sidebar-w', w: Math.round(r.width) }); }
        out.push({ n: 'page-bg', x: window.innerWidth - 6, y: window.innerHeight - 6, rgb: parse(getComputedStyle(document.body).backgroundColor) });
        var extra = [
          pt('cfg-th', document.querySelector('th.cfg-group'), 3, 3, true),
          pt('pool-chip', document.querySelector('.pool-chip'), 4, 4, true),
          pt('sec-ico', document.querySelector('#sec-reports .section-title .ico'), 2, 13, true),
          pt('rpt-card', document.querySelector('.rpt-card'), 6, 30, true)
        ];
        extra.forEach(function(e){ if (e && e.rgb) out.push(e); });
        return JSON.stringify({ probes: out.filter(function(p){ return p && p.rgb; }),
          vw: window.innerWidth, vh: window.innerHeight, dpr: window.devicePixelRatio,
          title: document.title, bodyOver: document.documentElement.scrollWidth - document.documentElement.clientWidth });
      })()`,
    });
    const probe = JSON.parse(probeRes.result.value);
    const expVw = probe.vw === sp.w && probe.vh === sp.h;
    // 截图（单视口，不拼接）
    const shot = await s.send('Page.captureScreenshot', { format: 'png' });
    const fs = await import('node:fs');
    fs.writeFileSync(sp.o, Buffer.from(shot.data, 'base64'));
    const bytes = fs.statSync(sp.o).size;
    // 像素回验：把截图 dataURL 画进 canvas，按 DOM 坐标取像素比对
    const verifyRes = await s.send('Runtime.evaluate', {
      awaitPromise: true, returnByValue: true,
      expression: `(new Promise(function(res){
        var img = new Image();
        img.onload = function(){ try {
          var c = document.createElement('canvas'); c.width = img.naturalWidth; c.height = img.naturalHeight;
          var g = c.getContext('2d'); g.drawImage(img, 0, 0);
          var out = ${JSON.stringify(probe.probes)}.map(function(p){
            if (p.w !== undefined) return { n: p.n, w: p.w };
            var d = g.getImageData(Math.round(p.x), Math.round(p.y), 1, 1).data;
            return { n: p.n, exp: p.rgb, got: [d[0], d[1], d[2]] };
          });
          res(JSON.stringify({ px: out, iw: img.naturalWidth, ih: img.naturalHeight }));
        } catch (e) { res('ERR ' + e.message); } };
        img.onerror = function(){ res('ERR img load'); };
        img.src = 'data:image/png;base64,${shot.data}';
      }))`,
    });
    let ok = expVw && bytes > 10000;
    const lines = [];
    if (!expVw) lines.push(`  FAIL viewport 实际 ${probe.vw}x${probe.vh} ≠ 期望 ${sp.w}x${sp.h}`);
    if (bytes <= 10000) lines.push(`  FAIL 文件过小 ${bytes}B`);
    const vr = JSON.parse(verifyRes.result.value);
    if (vr.iw !== sp.w || vr.ih !== sp.h) { ok = false; lines.push(`  FAIL 图像尺寸 ${vr.iw}x${vr.ih} ≠ ${sp.w}x${sp.h}`); }
    for (const p of vr.px) {
      if (p.w !== undefined) {
        if (sp.sw && p.w !== sp.sw) { ok = false; lines.push(`  FAIL ${p.n} 实际 ${p.w} ≠ 期望 ${sp.sw}`); }
        else lines.push(`  ok   ${p.n}=${p.w}`);
        continue;
      }
      const diff = Math.max(Math.abs(p.exp[0] - p.got[0]), Math.abs(p.exp[1] - p.got[1]), Math.abs(p.exp[2] - p.got[2]));
      if (diff > 12) { ok = false; lines.push(`  FAIL ${p.n} 期望 rgb(${p.exp}) 实得 rgb(${p.got}) diff=${diff}`); }
      else lines.push(`  ok   ${p.n} rgb(${p.got})`);
    }
    if (!ok) failed++;
    console.log(`${ok ? 'PASS' : 'FAIL'} ${sp.n}  ${sp.o}  ${bytes}B  title="${probe.title}"  bodyOver=${probe.bodyOver}`);
    lines.forEach((l) => console.log(l));
    s.close();
  } catch (e) {
    failed++;
    console.log(`FAIL ${sp.n}  异常: ${e.message}`);
  }
}
console.log(failed === 0 ? 'ALL PASS（截图与渲染一致）' : `FAILED=${failed}（存在不一致，以上图不得用于判断）`);
process.exit(failed === 0 ? 0 : 1);

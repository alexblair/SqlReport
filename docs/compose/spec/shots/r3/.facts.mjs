// 事实取证: 侧栏各组间距/spacer高度/账号区吸底/表格溢出
const [url, w, h] = process.argv.slice(2);
const t = await (await fetch('http://127.0.0.1:9333/json/new?'+encodeURIComponent('about:blank'),{method:'PUT'})).json();
const ws = new WebSocket(t.webSocketDebuggerUrl);
let id=0; const p=new Map();
const send=(m,q={})=>new Promise((res,rej)=>{const i=++id;p.set(i,{res,rej});ws.send(JSON.stringify({id:i,method:m,params:q}));setTimeout(()=>{if(p.has(i)){p.delete(i);rej(new Error('timeout '+m));}},30000);});
ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.id&&p.has(m.id)){const q=p.get(m.id);p.delete(m.id);m.error?q.rej(new Error(m.error.message)):q.res(m.result);}};
await new Promise((r,j)=>{ws.onopen=r;ws.onerror=j;});
await send('Page.enable');await send('Runtime.enable');
await send('Emulation.setDeviceMetricsOverride',{width:+w,height:+h,deviceScaleFactor:1,mobile:false});
await send('Page.navigate',{url});
await new Promise(r=>setTimeout(r,1200));
await send('Runtime.evaluate',{awaitPromise:true,expression:`(async function(){if(document.fonts&&document.fonts.ready)await document.fonts.ready;var im=Array.from(document.images||[]);await Promise.all(im.map(function(i){return i.complete?0:new Promise(function(r){i.onload=i.onerror=r;});}));await new Promise(function(r){requestAnimationFrame(function(){requestAnimationFrame(r);});});return 'ok';})()`});
const expr=`JSON.stringify((function(){
  var sb=document.querySelector('.sidebar');
  if(!sb) return {err:'no sidebar'};
  var spacers=Array.from(sb.querySelectorAll('.spacer')).map(function(s){return Math.round(s.getBoundingClientRect().height);});
  // 每个 nav-group 顶部到上一个元素底部的空白
  var groups=Array.from(sb.querySelectorAll('.nav-group')).map(function(g){return {t:g.textContent.trim(), top:Math.round(g.getBoundingClientRect().top)};});
  var items=Array.from(sb.querySelectorAll('.nav-item')).map(function(g){return {t:g.textContent.trim().slice(0,6), top:Math.round(g.getBoundingClientRect().top), bot:Math.round(g.getBoundingClientRect().bottom)};});
  var acc=sb.querySelector('.account');
  var accR=acc?acc.getBoundingClientRect():null;
  var gaps=(function(){var g=[];var sbEls=sb.querySelectorAll('.nav-group,.nav-item');var prev=null;Array.from(sb.querySelectorAll('.nav-group')).forEach(function(gr,ix){if(ix>0){var pv=sb.querySelectorAll('.nav-item');} });var kids=Array.from(sb.children);for(var i=0;i<kids.length;i++){if(kids[i].classList.contains('nav-group')&&i>0){var p=kids[i-1];g.push({after:p.className.split(' ').slice(-1)[0],gap:Math.round(kids[i].getBoundingClientRect().top-p.getBoundingClientRect().bottom)});}}return g;})();
  var tws=Array.from(document.querySelectorAll('.table-wrap')).map(function(t){return t.scrollWidth-t.clientWidth;});
  var ops=document.querySelector('.ops-cell');
  return {spacers:spacers, groupGaps:gaps, groups:groups, items:items,
    accTop:accR?Math.round(accR.top):null, accBot:accR?Math.round(accR.bottom):null,
    vh:window.innerHeight, sbH:Math.round(sb.getBoundingClientRect().height),
    tablesOver:tws, opsRight:ops?Math.round(ops.getBoundingClientRect().right):null,
    vw:window.innerWidth};
})())`;
const r=await send('Runtime.evaluate',{expression:expr,returnByValue:true});
console.log(r.result.value);
process.exit(0);

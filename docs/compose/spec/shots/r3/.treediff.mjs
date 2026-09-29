// 左树文本取证：提取 .tree/.cat/.cnt/.ops/标题 的几何与计算样式
const [url, label] = process.argv.slice(2);
const t = await (await fetch('http://127.0.0.1:9333/json/new?'+encodeURIComponent('about:blank'),{method:'PUT'})).json();
const ws = new WebSocket(t.webSocketDebuggerUrl);
let id=0; const p=new Map();
const send=(m,q={})=>new Promise((res,rej)=>{const i=++id;p.set(i,{res,rej});ws.send(JSON.stringify({id:i,method:m,params:q}));setTimeout(()=>{if(p.has(i)){p.delete(i);rej(new Error('timeout'));}},30000);});
ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.id&&p.has(m.id)){const q=p.get(m.id);p.delete(m.id);m.error?q.rej(new Error(m.error.message)):q.res(m.result);}};
await new Promise((r,j)=>{ws.onopen=r;ws.onerror=j;});
await send('Page.enable');await send('Runtime.enable');
await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1600,deviceScaleFactor:1,mobile:false});
await send('Page.navigate',{url});
await new Promise(r=>setTimeout(r,1500));
await send('Runtime.evaluate',{awaitPromise:true,expression:`(async function(){if(document.fonts&&document.fonts.ready)await document.fonts.ready;await new Promise(function(r){requestAnimationFrame(function(){requestAnimationFrame(r);});});return 1;})()`});
const expr = `JSON.stringify((function(){
  function g(sel){var e=document.querySelector(sel);if(!e)return null;var b=e.getBoundingClientRect();var c=getComputedStyle(e);
    return {sel:sel,x:Math.round(b.x),y:Math.round(b.y),w:Math.round(b.width),h:Math.round(b.height),
      fs:c.fontSize,fw:c.fontWeight,lh:c.lineHeight,pad:c.padding,margin:c.margin,gap:c.gap,
      color:c.color,bg:c.backgroundColor,br:c.borderRadius,bd:c.border,disp:c.display,ai:c.alignItems};}
  var out={};
  ['aside.card .tree','.tree','.tree .cat','.tree .cat .cnt','.tree .cat .ops',
   'aside.card .section-title','.section-title','#sec-categories .section-title',
   '.tree .cat svg','.tree .cat .ico'].forEach(function(s){var v=g(s);if(v)out[s]=v;});
  // 首行子元素布局
  var row=document.querySelector('.tree .cat');
  if(row){out.firstRowKids=Array.from(row.children).map(function(k){var b=k.getBoundingClientRect();var c=getComputedStyle(k);
    return {tag:k.tagName,cls:String(k.className).slice(0,30),txt:(k.textContent||'').trim().slice(0,14),
      x:Math.round(b.x),w:Math.round(b.width),h:Math.round(b.height),disp:c.display,fs:c.fontSize,color:c.color};});}
  // 标题行文本与子元素
  var st=document.querySelector('#sec-categories .section-title')||document.querySelector('aside.card .section-title')||document.querySelector('.section-title');
  if(st){out.titleText=(st.textContent||'').replace(/\\s+/g,' ').trim().slice(0,40);
    out.titleKids=Array.from(st.children).map(function(k){var b=k.getBoundingClientRect();
      return {tag:k.tagName,cls:String(k.className).slice(0,30),txt:(k.textContent||'').trim().slice(0,16),x:Math.round(b.x),w:Math.round(b.width),h:Math.round(b.height)};});}
  out.treeRowCount=document.querySelectorAll('.tree .cat').length;
  return JSON.stringify(out);
})())`;
const r=await send('Runtime.evaluate',{expression:expr,returnByValue:true});
console.log('===== '+label+' =====');
console.log(JSON.stringify(JSON.parse(r.result.value),null,1));
process.exit(0);

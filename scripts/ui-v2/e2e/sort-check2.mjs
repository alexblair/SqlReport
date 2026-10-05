const BASE='http://127.0.0.1:8099', port=process.env.CDP_PORT||9402;
const list=await (await fetch(`http://127.0.0.1:${port}/json/new?about:blank`,{method:'PUT'})).json();
const ws=new WebSocket(list.webSocketDebuggerUrl); let id=0; const pending=new Map(); const logs=[];
const send=(m,p={})=>new Promise((res,rej)=>{const i=++id;pending.set(i,{res,rej});ws.send(JSON.stringify({id:i,method:m,params:p}));setTimeout(()=>{if(pending.has(i)){pending.delete(i);rej(new Error('t '+m))}},60000)});
ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.id&&pending.has(m.id)){const x=pending.get(m.id);pending.delete(m.id);m.error?x.rej(new Error(m.error.message)):x.res(m.result)}else if(m.method==='Log.entryAdded')logs.push(m.params.entry)};
const ev=async e=>(await send('Runtime.evaluate',{returnByValue:true,expression:e})).result.value;
await new Promise((r,j)=>{ws.onopen=r;ws.onerror=j});
await send('Page.enable');await send('Runtime.enable');await send('Log.enable');
await send('Emulation.setDeviceMetricsOverride',{width:1440,height:900,deviceScaleFactor:1,mobile:false});
await send('Page.navigate',{url:BASE+'/login'});await new Promise(r=>setTimeout(r,700));
await ev(`document.querySelector('input[name=username]').value='admin';document.querySelector('input[name=password]').value='admin123';document.querySelector('form').submit();`);
await new Promise(r=>setTimeout(r,1500));

for (const [label,url] of [['订单概览(缓存)',BASE+'/report?id=1&page_size=20'],['全量导出(20万行)',BASE+'/report?id=5&page_size=20']]) {
  await send('Page.navigate',{url}); await new Promise(r=>setTimeout(r,1500));
  const t0=Date.now();
  await ev(`openPanel('sortSettingsPanel')`); await new Promise(r=>setTimeout(r,300));
  const cols=await ev(`[...document.querySelectorAll('#newSortCol option')].map(o=>o.value).filter(Boolean)`);
  await ev(`(()=>{const c=${JSON.stringify(cols)};const pick=c.find(x=>x!=='id')||c[0];
    const s=document.getElementById('newSortCol');s.value=pick;document.getElementById('newSortDir').value='desc';
    document.querySelector('button[onclick="addSortItem()"]').click();})()`);
  await new Promise(r=>setTimeout(r,250));
  const picked=await ev(`[...document.querySelectorAll('#sortList .sort-item')].map(it=>it.querySelector('input[name=sort_col]').value+':'+it.querySelector('input[name=sort_dir]').value).join(',')`);
  const tApply=Date.now();
  await ev(`document.querySelector('button[onclick="applySortSettings()"]').click()`);
  // 等 URL 变化 + 数据表刷新
  let applied=false, waited=0;
  while (waited<25000){ await new Promise(r=>setTimeout(r,500)); waited+=500;
    const u=await ev('location.search'); if(u.includes('sort=')){ applied=true; const rows=await ev(`document.querySelectorAll('.table-wrap table tbody tr').length`); if(rows>1) break; } }
  const dt=Date.now()-tApply;
  const order=await ev(`(()=>{const t=document.querySelector('.table-wrap table');if(!t)return '无表';
    return [...t.querySelectorAll('tbody tr')].filter(r=>!r.classList.contains('qf-row')).slice(0,4).map(r=>[...r.children].map(td=>td.textContent.trim()).slice(0,3).join('|')).join('  //  ')})()`);
  console.log(`【${label}】面板选项=${cols.join(',')}  配置=${picked}`);
  console.log(`   应用后 URL=${await ev('location.search')}`);
  console.log(`   耗时≈${dt}ms  前几行: ${order}`);
  console.log(`   排序条: ${await ev(`(()=>{const b=document.querySelector('.sort-bar');return b?b.textContent.replace(/\\s+/g,' ').trim().slice(0,70):'无'})()`)}`);
}
console.log('控制台错误:', logs.filter(l=>l.level==='error').map(l=>l.text.slice(0,120)).slice(0,4));
ws.close();process.exit(0);

import fs from 'node:fs';
const png = process.argv[2];
const b64 = fs.readFileSync(png).toString('base64');
const t = await (await fetch('http://127.0.0.1:9333/json/new?'+encodeURIComponent('about:blank'),{method:'PUT'})).json();
const ws = new WebSocket(t.webSocketDebuggerUrl);
let id=0; const p=new Map();
const send=(m,q={})=>new Promise((res,rej)=>{const i=++id;p.set(i,{res,rej});ws.send(JSON.stringify({id:i,method:m,params:q}));setTimeout(()=>{if(p.has(i)){p.delete(i);rej(new Error('timeout'));}},30000);});
ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.id&&p.has(m.id)){const q=p.get(m.id);p.delete(m.id);m.error?q.rej(new Error(m.error.message)):q.res(m.result);}};
await new Promise((r,j)=>{ws.onopen=r;ws.onerror=j;});
await send('Page.enable');await send('Runtime.enable');
const expr = `new Promise(function(res){
  var img=new Image();
  img.onload=function(){
    var c=document.createElement('canvas');c.width=img.naturalWidth;c.height=img.naturalHeight;
    var g=c.getContext('2d');g.drawImage(img,0,0);
    var d1=g.getImageData(1340,190,80,26).data, dark=0;
    for(var i=0;i<d1.length;i+=4){ if(d1[i]<130&&d1[i+1]<130&&d1[i+2]<130) dark++; }
    var rows=[];
    for(var y=300;y<560;y++){
      var d=g.getImageData(560,y,840,1).data, run=0, maxrun=0;
      for(var x=0;x<840;x++){ var R=d[x*4],G=d[x*4+1],B=d[x*4+2];
        if(Math.abs(R-G)<=1&&Math.abs(G-B)<=1&&R>=232&&R<=247){ run++; if(run>maxrun)maxrun=run; } else run=0; }
      if(maxrun>=500) rows.push(y);
    }
    var edge=g.getImageData(1420,180,19,40).data, nonbg=0;
    for(var j=0;j<edge.length;j+=4){ if(!(Math.abs(edge[j]-243)<6&&Math.abs(edge[j+1]-244)<6&&Math.abs(edge[j+2]-248)<6)) nonbg++; }
    res(JSON.stringify({size:[img.naturalWidth,img.naturalHeight],opsHeaderDarkPx:dark,scrollbarRows:rows.slice(0,10),rightEdgeNonBg:nonbg}));
  };
  img.onerror=function(){res('ERR img');};
  img.src='data:image/png;base64,${b64}';
})`;
const r = await send('Runtime.evaluate',{expression:expr,awaitPromise:true,returnByValue:true});
console.log(r.result.value);
process.exit(0);

// HamLab AD9850 sweep. The Pico returns both measurement runs as [Hz,A0 dBm,A1 dBm].
let sweepData=null,lastSweepSignature='',hoverIndex=-1,dutComplete=false;
function sweepConfig(mode){let hz=id=>Math.round(Number(el(id).value)*1e6);
 const cfg={mode,start_hz:hz('scanStart'),stop_hz:hz('scanStop'),step_hz:hz('scanStep'),
 dwell_ms:Number(el('scanDwell').value),samples:Number(el('scanSamples').value)};
 if(!Number.isInteger(cfg.start_hz)||!Number.isInteger(cfg.stop_hz)||!Number.isInteger(cfg.step_hz)||
 cfg.start_hz<1||cfg.stop_hz>40000000||cfg.stop_hz<cfg.start_hz||cfg.step_hz<1||
 Math.floor((cfg.stop_hz-cfg.start_hz)/cfg.step_hz)+1>256||
 !Number.isInteger(cfg.dwell_ms)||cfg.dwell_ms<0||cfg.dwell_ms>1000||
 !Number.isInteger(cfg.samples)||cfg.samples<1||cfg.samples>8)throw Error('Raster: 1–40 MHz, maximal 256 Punkte; Wartezeit 0–1000 ms, Messungen 1–8');
 return cfg}
async function startSweep(mode){try{let cfg=sweepConfig(mode);
 const r=await fetch('/api/v1/sweep/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(cfg)});
 if(!r.ok)throw Error(await r.text());lastSweepSignature='';sweepData=null;hoverIndex=-1;dutComplete=false;
 el('scanStatus').textContent=(mode==='baseline'?'Baseline':'Filter')+' läuft …';drawSweep();
 }catch(e){el('scanStatus').textContent=String(e)}}
el('baselineStart').onclick=()=>startSweep('baseline');el('dutStart').onclick=()=>startSweep('dut');
el('scanStopButton').onclick=async()=>{try{await fetch('/api/v1/sweep/stop',{method:'POST'});el('scanStatus').textContent='Abbruch angefordert'}catch(e){el('scanStatus').textContent=String(e)}};
async function pollSweep(){try{const r=await fetch('/api/v1/sweep/status',{cache:'no-store'});if(!r.ok)return;
 const s=await r.json();dutComplete=!!s.dut_ready;el('baselineStart').disabled=s.running;el('dutStart').disabled=s.running||!s.baseline_ready;
 el('scanStopButton').disabled=!s.running;
 if(s.running)el('scanStatus').textContent=(s.mode==='baseline'?'Baseline':'Filter')+' läuft: '+s.points+' / '+s.target+' Punkte';
 else if(s.error)el('scanStatus').textContent='Sweep beendet, Fehler '+s.error+(s.error===-34?' (Pegel über +10 dBm)':'');
 else el('scanStatus').textContent=(s.baseline_ready?'Baseline bereit':'Noch keine Baseline')+(s.dut_ready?' · Filter bereit':'');
 const signature=[s.running,s.baseline_ready,s.dut_ready,s.points,s.error].join(':');
 if((s.baseline_ready||s.points>0)&&signature!==lastSweepSignature){let rr=await fetch('/api/v1/sweep/results',{cache:'no-store'});
 if(rr.ok){sweepData=await rr.json();drawSweep()}lastSweepSignature=signature}
 }catch(e){el('scanStatus').textContent=String(e)}}
function traces(){if(!sweepData||!sweepData.baseline.length)return[];
 let b=sweepData.baseline,d=sweepData.dut;
 if(d.length){let bm=new Map(b.map(p=>[p[0],p]));return [{label:'Filter A0/A1, normiert',color:'#f6ce72',values:d.filter(p=>bm.has(p[0])).map(p=>[p[0]/1e6,(p[1]-p[2])-(bm.get(p[0])[1]-bm.get(p[0])[2])])}];}
 return[{label:'A0 ohne Filter',color:'#60b9f2',values:b.map(p=>[p[0]/1e6,p[1]])},
 {label:'A1 ohne Filter',color:'#94dd91',values:b.map(p=>[p[0]/1e6,p[2]])}];}
// Use the peak of the normalized DUT trace as the 0 dB reference.
// Find the nearest -3 dB crossings on each side using linear interpolation.
function cutoff3db(values){
 if(values.length<3)return null;
 let peak=0;for(let i=1;i<values.length;i++)if(values[i][1]>values[peak][1])peak=i;
 const level=values[peak][1]-3;
 function crossing(from,to,step){for(let i=from;i!==to;i+=step){let a=values[i],b=values[i+step];
  if((a[1]-level)*(b[1]-level)<=0&&a[1]!==b[1])
   return a[0]+(level-a[1])*(b[0]-a[0])/(b[1]-a[1]);}return null;}
 return {level,peak:values[peak],low:crossing(peak,0,-1),high:crossing(peak,values.length-1,1)};
}
function drawSweep(){const canvas=el('sweepGraph'),ctx=canvas.getContext('2d'),w=canvas.width,h=canvas.height;
 ctx.fillStyle='#101a28';ctx.fillRect(0,0,w,h);const all=traces();
 ctx.font='14px system-ui';if(!all.length){ctx.fillStyle='#9aafc6';ctx.fillText('Baseline starten, um den Frequenzgang zu sehen',30,45);return}
 const cut=dutComplete&&sweepData.dut.length?cutoff3db(all[0].values):null;
 el('cutoffReadout').textContent=cut?('−3 dB bezogen auf Maximum '+cut.peak[1].toFixed(2)+' dB bei '+cut.peak[0].toFixed(4)+' MHz · '+(cut.low===null?'untere Grenze außerhalb des Sweeps':'f₁ '+cut.low.toFixed(4)+' MHz')+' · '+(cut.high===null?'obere Grenze außerhalb des Sweeps':'f₂ '+cut.high.toFixed(4)+' MHz')+(cut.low!==null&&cut.high!==null?' · Bandbreite '+(cut.high-cut.low).toFixed(4)+' MHz':'')):'−3-dB-Grenzen nach vollständiger Filtermessung';
 const vals=all.flatMap(t=>t.values),xmin=Math.min(...vals.map(p=>p[0])),xmax=Math.max(...vals.map(p=>p[0]));
 let ymin=Math.min(0,...vals.map(p=>p[1]),...(cut?[cut.level]:[])),ymax=Math.max(0,...vals.map(p=>p[1]));
 if(ymax-ymin<1){ymin-=0.5;ymax+=0.5}const margin=(ymax-ymin)*.08;ymin-=margin;ymax+=margin;
 const left=72,right=w-20,top=24,bottom=h-55;
 const xp=x=>left+(x-xmin)/(xmax-xmin||1)*(right-left),yp=y=>bottom-(y-ymin)/(ymax-ymin)*(bottom-top);
 ctx.strokeStyle='#405064';ctx.fillStyle='#abc1d6';ctx.lineWidth=1;
 for(let i=0;i<=5;i++){let y=top+i*(bottom-top)/5,v=ymax-i*(ymax-ymin)/5;
 ctx.beginPath();ctx.moveTo(left,y);ctx.lineTo(right,y);ctx.stroke();ctx.fillText(v.toFixed(1),10,y+5)}
 for(let i=0;i<=5;i++){let x=left+i*(right-left)/5,v=xmin+i*(xmax-xmin)/5;
 ctx.beginPath();ctx.moveTo(x,top);ctx.lineTo(x,bottom);ctx.stroke();ctx.fillText(v.toFixed(2),x-20,bottom+24)}
 ctx.fillText('MHz',right-35,bottom+46);ctx.fillText('dB / dBm',8,17);
 all.forEach((t,j)=>{ctx.strokeStyle=t.color;ctx.lineWidth=2;ctx.beginPath();t.values.forEach((p,i)=>i?ctx.lineTo(xp(p[0]),yp(p[1])):ctx.moveTo(xp(p[0]),yp(p[1])));ctx.stroke();
 ctx.fillStyle=t.color;ctx.fillRect(left+j*230,top+6,14,3);ctx.fillText(t.label,left+20+j*230,top+11)});
 if(cut){ctx.save();ctx.strokeStyle='#ff8290';ctx.fillStyle='#ff9ba7';ctx.setLineDash([6,5]);ctx.lineWidth=1;
 ctx.beginPath();ctx.moveTo(left,yp(cut.level));ctx.lineTo(right,yp(cut.level));ctx.stroke();ctx.setLineDash([]);
 for(const [label,f] of [['f₁',cut.low],['f₂',cut.high]])if(f!==null){let x=xp(f),y=yp(cut.level);
 ctx.beginPath();ctx.arc(x,y,5,0,2*Math.PI);ctx.fill();ctx.fillText(label+' '+f.toFixed(3),Math.min(x+7,right-105),y-9)}ctx.restore()}
 if(hoverIndex>=0&&all[0].values[hoverIndex]){let p=all[0].values[hoverIndex];ctx.strokeStyle='#fff';ctx.beginPath();ctx.moveTo(xp(p[0]),top);ctx.lineTo(xp(p[0]),bottom);ctx.stroke();
 el('cursorReadout').textContent=p[0].toFixed(4)+' MHz · '+all.map(t=>t.label+': '+(t.values[hoverIndex]?t.values[hoverIndex][1].toFixed(3):'—')+' dB').join(' · ')}
}
el('sweepGraph').addEventListener('pointermove',e=>{let t=traces()[0];if(!t)return;
 let rect=e.currentTarget.getBoundingClientRect(),x=(e.clientX-rect.left)/rect.width*860;
 hoverIndex=Math.max(0,Math.min(t.values.length-1,Math.round((x-72)/(860-92)*(t.values.length-1))));drawSweep()});
el('sweepGraph').addEventListener('pointerleave',()=>{hoverIndex=-1;drawSweep()});
el('scanCsv').onclick=()=>{if(!sweepData){el('scanStatus').textContent='Noch keine Messwerte vorhanden';return}
 let b=sweepData.baseline,d=new Map(sweepData.dut.map(p=>[p[0],p]));
 let lines=['frequency_hz,baseline_a0_dbm,baseline_a1_dbm,dut_a0_dbm,dut_a1_dbm,transmission_db'];
 b.forEach(p=>{let q=d.get(p[0]);lines.push([p[0],p[1],p[2],q?q[1]:'',q?q[2]:'',q?((q[1]-q[2])-(p[1]-p[2])).toFixed(3):''].join(','))});
 let url=URL.createObjectURL(new Blob([lines.join('\n')+'\n'],{type:'text/csv'})),a=document.createElement('a');
 a.href=url;a.download='hamlab_ad9850_sweep.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)};
drawSweep();pollSweep();setInterval(pollSweep,1000);

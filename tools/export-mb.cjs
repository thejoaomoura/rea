// After-Effects-style motion blur by temporal supersampling (like Remotion's CameraMotionBlur):
// every output frame = average of SAMPLES sub-frames spread across the shutter (SHUTTER degrees, 180 = AE default).
// Parallel: WORKERS separate browsers (own compositor each) render interleaved frames. Resume-safe: frames whose sub-frames all exist are skipped.
// usage: [START=f] [END=f] [SAMPLES=4] [SHUTTER=180] [WORKERS=4] NODE_PATH=$(npm root -g) node tools/export-mb.cjs URL OUT_DIR [FPS]
// then: tools/encode-mb.sh OUT_DIR audio.mp3 out.mp4 FPS SAMPLES
const {chromium}=require('playwright');const fs=require('fs');
(async()=>{const [url,out,fps='30']=process.argv.slice(2);fs.mkdirSync(out,{recursive:true});
const K=+(process.env.SAMPLES||4),SH=+(process.env.SHUTTER||180)/360,F=+fps,W=+(process.env.WORKERS||4);
const name=i=>`${out}/s${String(i).padStart(6,'0')}.jpg`;
const browsers=[];const pages=[];for(let w=0;w<W;w++){const b=await chromium.launch();browsers.push(b);const p=await b.newPage({viewport:{width:1080,height:1920}});p.on('pageerror',e=>console.log('pageerror:',e.message));
 await p.goto(url);await p.waitForFunction('window.LYRIC&&window.LYRIC.ready',null,{timeout:90000});pages.push(p)}
const D=await pages[0].evaluate(()=>window.LYRIC.DURATION);const N=Math.round(D*F);const s0=+(process.env.START||0),end=Math.min(N,+(process.env.END||1e9));
let done=0;const t0=Date.now();
await Promise.all(pages.map(async(p,w)=>{for(let n=s0+w;n<end;n+=W){if([...Array(K).keys()].every(j=>fs.existsSync(name(n*K+j))))continue;
 for(let j=0;j<K;j++){const t=Math.max(0,n/F+((j+.5)/K-.5)*SH/F);await p.evaluate(t=>window.LYRIC.seek(t),t);await p.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));
  const tmp=name(n*K+j)+'.part';await p.screenshot({path:tmp,type:'jpeg',quality:92});fs.renameSync(tmp,name(n*K+j))}
 if(++done%60===0)console.log(`${done} frames, ${((Date.now()-t0)/done/1000).toFixed(2)} s/frame`)}}));
await Promise.all(browsers.map(b=>b.close()));console.log('done',end-s0,'frames x',K,'samples in',((Date.now()-t0)/60000).toFixed(1),'min')})();

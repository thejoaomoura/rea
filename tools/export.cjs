// Frame-accurate export: seeks window.LYRIC per frame and writes JPGs.
// usage: [START=n] [END=n] NODE_PATH=$(npm root -g) node tools/export.cjs URL OUT_DIR [FPS]
// Resumable: background jobs die at 30 min / on container restart -> rerun with START=<last frame-2>.
const {chromium}=require('playwright');const fs=require('fs');
(async()=>{const [url,out,fps='30']=process.argv.slice(2);fs.mkdirSync(out,{recursive:true});
const b=await chromium.launch();const p=await b.newPage({viewport:{width:1080,height:1920}});
p.on('pageerror',e=>console.log('pageerror:',e.message));
await p.goto(url);await p.waitForFunction('window.LYRIC&&window.LYRIC.ready',null,{timeout:60000});
const D=await p.evaluate(()=>window.LYRIC.DURATION);const N=Math.round(D*+fps);
for(let i=+(process.env.START||0);i<Math.min(N,+(process.env.END||1e9));i++){await p.evaluate(t=>window.LYRIC.seek(t),i/+fps);await p.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));
 await p.screenshot({path:`${out}/f${String(i).padStart(5,'0')}.jpg`,type:'jpeg',quality:93});if(i%150===0)console.log(i,'/',N);}
await b.close();console.log('done',N)})();

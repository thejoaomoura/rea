// usage: NODE_PATH=$(npm root -g) node tools/snap.cjs URL OUT_DIR t1 t2 ...  (prefer tools/contact.sh)
const {chromium}=require('playwright');
(async()=>{const [url,out,...ts]=process.argv.slice(2);
const b=await chromium.launch();const p=await b.newPage({viewport:{width:1080,height:1920}});
p.on('console',m=>{if(m.type()==='error')console.log('console:',m.text())});p.on('pageerror',e=>console.log('pageerror:',e.message));
await p.goto(url);await p.waitForFunction('window.LYRIC&&window.LYRIC.ready',null,{timeout:60000});
for(const t of ts){await p.evaluate(t=>window.LYRIC.seek(+t),t);await p.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));
 await p.screenshot({path:`${out}/s_${String(t)}.png`});}
await b.close()})();

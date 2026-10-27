#!/usr/bin/env node
// Dedicated guests only. Optional private SOAP credentials enable authoritative team checks.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const {execFileSync}=require('node:child_process');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const base=process.env.BROWSER_URL||'http://localhost:8096';
const results=[];
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true,args:['--enable-unsafe-webgpu',...(process.platform==='darwin'?['--use-angle=metal']:[])]});
 const peers=[];
 fs.mkdirSync('artifacts/coop',{recursive:true});
 try {
  for(let i=0;i<2;i++){
   const context=await browser.newContext({viewport:{width:1920,height:1080},deviceScaleFactor:1});
   const page=await context.newPage();
   page.on('console',m=>{if(m.text().includes('Arena lobby:')||m.text().includes('Arena client recovery:'))console.log('Peer',i,m.text());});
   await page.goto(base);
   const iframe=await page.waitForSelector('iframe#game');let frame=await iframe.contentFrame();
   await frame.waitForFunction(()=>wenilla?.state?.session?.state==='charselect',{}, {timeout:180000});
   const lua=code=>frame.evaluate(code=>wenilla.lua(code),code);
   const until=async(code)=>{const end=Date.now()+120000;while(Date.now()<end){try{if((await lua(code))[0])return;}catch(e){if(!/no VM|Lua bridge timed out/.test(e.message))throw e;}await page.waitForTimeout(500);}throw Error('Peer '+i+' timed out: '+code);};
   const click=async(expr)=>{const [x,y,w,h]=await lua(`local x,y=${expr}:GetCenter();return x,y,GetScreenWidth(),GetScreenHeight()`);const r=await frame.locator('canvas').boundingBox();await page.mouse.click(r.x+x/w*r.width,r.y+(1-y/h)*r.height);};
   const api=async(url,method='GET',data)=>{const r=await context.request.fetch(base+'/api/'+url,{method,data});return {status:r.status(),data:await r.json()};};
   await until('return ArenaLaunchButton ~= nil');
   await frame.waitForFunction(()=>document.querySelector('#wenilla-boot')?.classList.contains('gone'));
   const peer={context,page,frame,lua,until,click,api};
   peers.push(peer);
   console.log('Ready peer',i+1);
  }
  assert.notEqual((await peers[0].api('session','POST',{})).data.account,(await peers[1].api('session','POST',{})).data.account);
  const sizes=(process.env.COOP_SIZES||'2,2,3,3').split(',').map(Number);
  for(const [round,size] of sizes.entries()){
   assert.ok([2,3].includes(size));
   const [a,b]=peers;
   for(const [i,p] of peers.entries()){
    await p.click('ArenaModeButtons.bots');
    if(round===0)await p.click(`ArenaHeroButtons[${i===0?1:2}]`);else await p.click('ArenaSavedButton');
    await p.click(`ArenaMatchSizeButtons[${size}]`);await p.click('ArenaFriendButton');
   }
   await a.click('ArenaCreateTeamCode');
   await a.until('return string.len(ArenaTeamCode:GetText())==8');
   const [code]=await a.lua('return ArenaTeamCode:GetText()');
   await b.lua(`ArenaTeamCode:SetText(${JSON.stringify(code)})`);
   await a.page.screenshot({path:`artifacts/coop/lobby-${size}.png`,scale:'css'});
   await a.click('ArenaLaunchButton');
   await a.until('return ArenaQueueWaiting==1 and ArenaQueueNeeded==2');
   assert.equal((await a.api('queue')).data.mode,'coop');
   assert.equal((await b.api('queue')).data.state,'idle');
   await a.page.waitForTimeout(10000);
   await a.page.screenshot({path:`artifacts/coop/waiting-${size}.png`,scale:'css'});
   await b.click('ArenaLaunchButton');
   for(const p of peers)await p.until('return ArenaWorldCover and not ArenaWorldCover:IsShown() and select(2,IsInInstance())=="arena"');
   const games=await Promise.all(peers.map(p=>p.api('queue')));
   assert.equal(games[0].data.match,games[1].data.match);assert.equal(games[0].data.mode,'coop');
   const session=(await a.api('session','POST',{})).data;
   const denied=await b.api('leave','POST',{name:session.characters[0].name,logout:true});assert.equal(denied.status,403);
   // Allow worldport acknowledgement and NPC setup before reading authoritative state.
   await a.page.waitForTimeout(2500);
   let match=null;
   if(process.env.ARENA_SOAP_PASS){
    const raw=execFileSync('python3',['-c','import sys;sys.path.insert(0,"controller");import arena_ctl;print(arena_ctl.soap("botarena json"))'],{encoding:'utf8',maxBuffer:16*1024*1024});
    match=JSON.parse(raw).matches.find(m=>m.id===games[0].data.match);
    assert.equal(match.humans.length,2);assert.ok(match.humans.every(h=>h.team==='A'&&h.joined));
    assert.equal(match.bots.filter(b=>b.team==='A').length,size-2);
    assert.equal(match.bots.filter(b=>b.team==='H').length,size);
    if(size===3)assert.equal(match.bots.find(b=>b.team==='A').class,'mage','Human Holy Paladin supplies healing; allied filler should deal damage');
    const previous=results.filter(r=>r.size===size).at(-1);if(previous)assert.notEqual(match.compH,previous.opponent);
   }
   const observe=round===sizes.length-1?Number(process.env.TEST_COMBAT_SECONDS||0):0;
   assert.ok(Number.isFinite(observe)&&observe>=0&&observe<=120);
   let tookDamage=false,walking=false,walked=0;
   for(let second=0;second<observe;second++){
    if(!walking && walked===0 && (match?.elapsed||0)+second>=62){
     await a.page.bringToFront();await a.frame.locator('canvas').focus();await a.page.keyboard.down('w');
     walking=true;
    }
    if(walking){
     walked++;
     if(walked===9){await a.page.keyboard.up('w');await b.page.bringToFront();await b.frame.locator('canvas').focus();await b.page.keyboard.down('w');}
     if(walked===18){await b.page.keyboard.up('w');walking=false;}
    }
    await a.page.waitForTimeout(1000);
    for(const p of peers){const [hp,max]=await p.lua('return UnitHealth("player"),UnitHealthMax("player")');if(hp<max)tookDamage=true;}
   }
   for(const p of peers)await p.page.keyboard.up('w');
   if(observe>=90)assert.ok(tookDamage,'Bots must damage a human player after both teammates move out through the gates');
   results.push({size,match:games[0].data.match,opponent:match?.compH,observedSeconds:observe,tookDamage});
   await a.page.screenshot({path:`artifacts/coop/arena-${size}-${round}.png`,scale:'css'});
   console.log('PASS two teammates vs bots',size+'v'+size,match?.compH||'(SOAP verification not configured)');
   for(const p of peers)await p.lua('ArenaReturnButton:Click()');
   for(const p of peers){await p.frame.waitForFunction(()=>wenilla.state.session.state==='charselect',{}, {timeout:90000});await p.until('return ArenaLaunchButton ~= nil');}
  }
  console.log('PASS separate guest ownership, team waiting, configured matches and return');
 } finally {
  for(const p of peers)await p.api('recover','POST',{}).catch(()=>{});
  fs.writeFileSync('artifacts/coop/results.json',JSON.stringify(results,null,2));
  await browser.close();
 }
})().catch(e=>{console.error(e);process.exitCode=1;});

#!/usr/bin/env node
// Exercise the Lua lobby through actual canvas clicks, then enter and leave a spectator arena.
const assert=require('node:assert/strict');
const path=require('node:path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true,args:['--enable-unsafe-webgpu',...(process.platform==='darwin'?['--use-angle=metal']:[])]});
 const page=await browser.newPage({viewport:{width:Number(process.env.TEST_WIDTH)||1440,height:Number(process.env.TEST_HEIGHT)||1000},deviceScaleFactor:Number(process.env.TEST_DPR)||1});
 page.on('console',m=>{if(m.text().includes('Arena lobby:'))console.log(m.text());});
 try{
  await page.goto(process.env.BROWSER_URL||'http://127.0.0.1:8090');
  assert.equal(await page.locator('button,input,select').count(),0,'The host page must not contain lobby controls');
  await page.waitForTimeout(1000);const frame=page.frames().find(f=>f.url().includes('/game/'));
  await frame.waitForFunction(()=>window.wenilla?.state?.session?.state==='charselect',{}, {timeout:180000});
  async function lua(code){return frame.evaluate(code=>wenilla.lua(code),code);}
  async function until(code,timeout=90000){const start=Date.now();while(Date.now()-start<timeout){try{if((await lua(code))[0])return;}catch{}await page.waitForTimeout(500);}console.log('Display diagnostics',await frame.evaluate(()=>({session:wenilla.state?.session,canvas:[document.querySelector('canvas')?.width,document.querySelector('canvas')?.height],dpr:devicePixelRatio})),await lua('return ArenaWorldMessage,GetCVar("gxResolution")'));throw Error('Timed out: '+code);}
  await until('return ArenaLaunchButton ~= nil');
  await frame.waitForFunction(()=>!document.querySelector('#wenilla-boot') || document.querySelector('#wenilla-boot').classList.contains('gone'));
  async function click(expr){
   const [x,y,w,h]=await lua(`local x,y=${expr}:GetCenter();return x,y,GetScreenWidth(),GetScreenHeight()`);
   const r=await frame.locator('canvas').boundingBox();await page.mouse.click(r.x+x/w*r.width,r.y+(1-y/h)*r.height);
  }
  console.log('Loaded full-screen lobby');
  async function hover(expr){
   const [x,y,w,h]=await lua(`local x,y=${expr}:GetCenter();return x,y,GetScreenWidth(),GetScreenHeight()`);
   const r=await frame.locator('canvas').boundingBox();await page.mouse.move(r.x+x/w*r.width,r.y+(1-y/h)*r.height);
  }
  await click('ArenaHeroButtons[10]');
  await until('return ArenaSelectedBuild == 30');
  await click('ArenaTalentButton');
  await until('return ArenaTalentModal:IsShown() and #ArenaTalentTrees == 3 and #ArenaTalentNodes > 60');
  await hover('ArenaTalentNodes[1]');
  await until('return ArenaInspectTooltip:IsShown() and ArenaInspectTooltip:NumLines() >= 3');
  await page.screenshot({scale:"css",path:path.resolve(__dirname,"../artifacts/lobby/native-talent-tooltip.png")});
  await hover('ArenaGlyphButtons[1]');
  await until('return ArenaInspectTooltip:IsOwned(ArenaGlyphButtons[1]) and ArenaInspectTooltip:NumLines() >= 3');
  await page.screenshot({scale:"css",path:path.resolve(__dirname,"../artifacts/lobby/native-glyph-tooltip.png")});
  await lua("ArenaTalentModal:Hide()");
  await click('ArenaGearButton');
  await until("return #ArenaGearSlots >= 16");
  await click("ArenaGearButton");
  await hover('ArenaGearSlots[1]');
  await until('return ArenaInspectTooltip:IsOwned(ArenaGearSlots[1]) and ArenaInspectTooltip:NumLines() >= 8');
  await page.screenshot({scale:"css",path:path.resolve(__dirname,"../artifacts/lobby/native-item-tooltip.png")});
  const [before]=await lua("return GetCharacterCreateFacing()");
  const canvas=await frame.locator("canvas").boundingBox();
  await page.mouse.move(canvas.x+canvas.width*.5,canvas.y+canvas.height*.5);
  await page.mouse.down();await page.mouse.move(canvas.x+canvas.width*.6,canvas.y+canvas.height*.5,{steps:12});await page.mouse.up();
  await page.waitForTimeout(500);
  assert.notEqual((await lua("return GetCharacterCreateFacing()"))[0],before,"Dragging the hero rotates it");
  const [preview]=await lua('return ArenaHeroPreview');assert.equal(JSON.parse(preview).length,19);
  await page.waitForTimeout(10000);
  await page.screenshot({scale:"css",path:path.resolve(__dirname,'../artifacts/lobby/ingame-lobby.png')});
  console.log('Graphical inspection and mouse rotation passed');
  await click('ArenaModeButtons.watch');
  await until('return ArenaSpectatorSettings:IsShown() and not ArenaHeroModel:IsShown()');
  await page.screenshot({scale:"css",path:path.resolve(__dirname,'../artifacts/lobby/spectator-settings.png')});
  await click('ArenaWatchButton');
  await frame.waitForFunction(()=>wenilla?.state?.session?.state==='inworld',{}, {timeout:120000});
  await until('return ArenaWorldCover and not ArenaWorldCover:IsShown()',120000);
  assert.deepEqual(await lua('return UnitLevel("player"),select(2,UnitClass("player")),select(2,IsInInstance())'),[80,'DRUID','arena']);
  assert.deepEqual(await lua('return not not ArenaLobbyViewReady,not not UIParent:IsShown()'),[true,false]);
  await page.screenshot({scale:"css",path:path.resolve(__dirname,'../artifacts/lobby/ingame-spectating.png')});
  await lua('ArenaReturnButton:Click()');
  await frame.waitForFunction(()=>wenilla?.state?.session?.state==='charselect',{}, {timeout:90000});
  await until('return ArenaLaunchButton ~= nil');
  assert.equal((await lua('return #ArenaLobbyData.characters'))[0],1);
  console.log('Spectator entry and return passed');
  for (const mode of ['bots','players']) {
   console.log('Testing '+mode);
   await click('ArenaSavedButton');
   await click('ArenaModeButtons.'+mode);
   await click('ArenaLaunchButton');
   await frame.waitForFunction(()=>wenilla?.state?.session?.state==='inworld',{}, {timeout:120000});
   if(mode==='bots') {
    await until('return ArenaWorldCover and not ArenaWorldCover:IsShown()',120000);
    assert.deepEqual(await lua('return select(2,IsInInstance()),not not UIParent:IsShown()'),['arena',true]);
   } else {
    await until("return ArenaQueueWaiting == 1 and ArenaQueueNeeded == 4");
    await page.waitForTimeout(7000);
    await page.screenshot({scale:"css",path:path.resolve(__dirname,"../artifacts/lobby/matchmaking-selection.png")});
   }
   await lua('ArenaReturnButton:Click()');
   await frame.waitForFunction(()=>wenilla?.state?.session?.state==='charselect',{}, {timeout:90000});
   await until('return ArenaLaunchButton ~= nil');
  }
  await click('ArenaHeroButtons[1]');await click('ArenaModeButtons.bots');await click('ArenaLaunchButton');
  await frame.waitForFunction(()=>wenilla?.state?.session?.state==='inworld',{}, {timeout:120000});
  await until('return ArenaWorldCover and not ArenaWorldCover:IsShown()',120000);
  assert.equal((await lua('return select(2,UnitClass("player"))'))[0],'WARRIOR','Second roster entry must log into the chosen hero');
  await lua('ArenaReturnButton:Click()');
  await frame.waitForFunction(()=>wenilla?.state?.session?.state==='charselect',{}, {timeout:90000});
  await until('return ArenaLaunchButton ~= nil');
  assert.equal((await lua('return #ArenaLobbyData.characters'))[0],2);
  console.log('PASS game-first Lua lobby, canvas hero selection, gear/talents, S8 preview, spectating, bot participation, human queue cancellation and return without reloading');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});

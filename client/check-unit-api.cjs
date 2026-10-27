#!/usr/bin/env node
// Dedicated guest: exercise arena unit APIs and addons against a live isolated server.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const {chromium} = require('playwright');
(async () => {
 const browser = await chromium.launch({channel:'chrome',headless:true,args:['--enable-unsafe-webgpu',...(process.platform==='darwin'?['--use-angle=metal']:[])]});
 const page = await browser.newPage({viewport:{width:1920,height:1080}});
 let frame;
 const lua = code => frame.evaluate(code => wenilla.lua(code), code);
 async function until(code, timeout=120000) {
  const start=Date.now();
  while(Date.now()-start<timeout) {
   try { if((await lua(code))[0]) return; } catch {}
   await page.waitForTimeout(500);
  }
  console.log('Diagnostics',await lua('return UnitGUID and UnitGUID("player"), GetNumArenaOpponents and GetNumArenaOpponents(), ArenaPvPStatus and ArenaPvPStatus.Gladius, ArenaAddonErrors and table.concat(ArenaAddonErrors,"\\n")'));
  throw Error('Timed out: '+code);
 }
 try {
  await page.goto(process.env.BROWSER_URL || 'http://localhost:8096');
  frame=await (await page.waitForSelector('#game')).contentFrame();
  await frame.waitForFunction(()=>window.wenilla?.state?.session?.state==='charselect',{}, {timeout:180000});
  await until('return ArenaLaunchButton ~= nil');
  await lua('ArenaHeroButtons[2]:Click(); ArenaModeButtons.bots:Click(); ArenaMapButtons.na:Click(); ArenaLaunchButton:Click()');
  await until('return ArenaPvPDB and ArenaPvPDB.configured and ArenaWorldCover and not ArenaWorldCover:IsShown() and select(2,IsInInstance()) == "arena"');
  await until('return UnitGUID and UnitGUID("arena1") and UnitExists("arena1")');
  console.log('Opponent state',await lua('return GetNumArenaOpponents(),UnitGUID("arena1"),UnitName("arena1"),select(2,UnitClass("arena1")),UnitHealth("arena1"),UnitHealthMax("arena1"),UnitGUID("arena2"),UnitName("arena2"),select(2,UnitClass("arena2"))'));
  console.log('Addon state',await lua('return ArenaPvPStatus.Gladius,ArenaPvPStatus.SoundAlerter,table.concat(ArenaAddonErrors,"\\n")'));
  assert.equal((await lua('return GetNumArenaOpponents()'))[0],2);
  assert.deepEqual(await lua('return IsAddOnLoaded("Gladius") and true,IsAddOnLoaded("SoundAlerter") and true'),[true,true]);
  assert.equal((await lua('return table.concat(ArenaAddonErrors,"\\n")'))[0],'');
  await until('return Gladius and Gladius.buttons.arena1 and Gladius.buttons.arena1:IsShown() and Gladius.buttons.arena1:GetAlpha() > 0');
  await lua('ArenaUnitProbe={}; local f=CreateFrame("Frame"); for _,e in ipairs({"UNIT_HEALTH","UNIT_SPELLCAST_START","UNIT_SPELLCAST_CHANNEL_START","UNIT_AURA","UNIT_TARGET"}) do f:RegisterEvent(e) end; f:SetScript("OnEvent",function(_,e,u) if u and string.match(u,"^arena%d$") then ArenaUnitProbe[e]=true; if e=="UNIT_SPELLCAST_START" then ArenaUnitProbe.cast=UnitCastingInfo(u) end end end)');
  await lua('Gladius.buttons.arena1.secure:Click("LeftButton")');
  await until('return UnitGUID("target") == UnitGUID("arena1")',15000);
  await until('return ArenaUnitProbe.UNIT_HEALTH and (ArenaUnitProbe.UNIT_SPELLCAST_START or ArenaUnitProbe.UNIT_SPELLCAST_CHANNEL_START)',90000);
  console.log('Live events',await lua('return ArenaUnitProbe.UNIT_HEALTH,ArenaUnitProbe.UNIT_AURA,ArenaUnitProbe.UNIT_TARGET,ArenaUnitProbe.cast'));
  assert.equal((await lua('return table.concat(ArenaAddonErrors,"\\n")'))[0],'');
  fs.mkdirSync('artifacts/unit-api',{recursive:true});
  await page.screenshot({path:'artifacts/unit-api/verified-ui.png'});
  await lua('ArenaReturnButton:Click()');
  await frame.waitForFunction(()=>wenilla.state?.session?.state==='charselect',{}, {timeout:90000});
  // Character select runs the glue environment, where the arena unit APIs may be absent.
  assert.deepEqual(await lua('return not GetNumArenaOpponents or GetNumArenaOpponents() == 0, not UnitGUID or UnitGUID("arena1") == nil'),[true,true]);
  console.log('PASS: real opponents, Gladius targeting, health/cast events and roster reset');
 } finally {
  if(frame) {try {await lua('if ArenaReturnButton then ArenaReturnButton:Click() end');} catch {}}
  await browser.close();
 }
})().catch(error=>{console.error(error);process.exitCode=1;});

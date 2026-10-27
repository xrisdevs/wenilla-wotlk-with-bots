#!/usr/bin/env node
// Dedicated browser guest; never changes an existing player's addon preferences.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const {chromium} = require('playwright');
(async () => {
 const browser = await chromium.launch({channel:'chrome',headless:true,args:['--enable-unsafe-webgpu',...(process.platform==='darwin'?['--use-angle=metal']:[])]});
 const page = await browser.newPage({viewport:{width:1920,height:1080}});
 let frame;
 const lua = code => frame.evaluate(code => wenilla.lua(code), code);
 async function until(code, timeout=150000) {
  const start=Date.now();
  while(Date.now()-start<timeout) {
   try { if((await lua(code))[0]) return; } catch {}
   await page.waitForTimeout(500);
  }
  console.log('Failure diagnostics',await lua('local q=LibStub("AceAddon-3.0"):GetAddon("Quartz3"); return UnitName("player"),select(2,UnitClass("player")),q:GetModule("Player"):IsEnabled(),q:GetModule("Player").Bar:IsShown(),UnitCastingInfo("player"),table.concat(ArenaAddonErrors,"\\n")'));
  throw Error('Timed out: '+code);
 }
 try {
  await page.goto(process.env.BROWSER_URL || 'http://localhost:8096');
  frame=await (await page.waitForSelector('#game')).contentFrame();
  await frame.waitForFunction(()=>window.wenilla?.state?.session?.state==='charselect',{}, {timeout:180000});
  await until('return ArenaLaunchButton ~= nil');
  await lua('ArenaHeroButtons[2]:Click(); ArenaModeButtons.bots:Click(); ArenaMapButtons.na:Click(); ArenaLaunchButton:Click()');
  await until('return ArenaPvPDB and ArenaPvPDB.configured and ArenaWorldCover and not ArenaWorldCover:IsShown() and select(2,IsInInstance()) == "arena"');
  assert.deepEqual(await lua('return IsAddOnLoaded("InterruptBar") and true,IsAddOnLoaded("LoseControl") and true,IsAddOnLoaded("OmniCC") and true,IsAddOnLoaded("Quartz") and true'),[true,true,true,true]);
  assert.deepEqual(await lua('return InterruptBarDB.hidden,InterruptBarDB.lock,InterruptBarDB.scale,LoseControlDB.frames.player.size,OmniCC:GetFontSize()'),[true,true,1.1,52,20]);
  // Exercise actual addon timer/render paths without pretending this is a real interrupt.
  assert.deepEqual(await lua('SlashCmdList.InterruptBar("test"); ArenaAddonCheck=CreateFrame("Cooldown",nil,UIParent); ArenaAddonCheck:SetWidth(44); ArenaAddonCheck:SetHeight(44); ArenaAddonCheck:SetPoint("CENTER",UIParent,"CENTER",0,100); ArenaAddonCheck:SetCooldown(GetTime(),60); local icon=ArenaInterruptBar[GetSpellInfo(57994)]; return icon:IsShown() and true,icon.cd.noCooldownCount,ArenaAddonCheck.omnicc'),[true,true,true]);
  await until('local timer=OmniCC.Timer:Get(ArenaAddonCheck); return timer and timer.text:GetText() and string.find(timer.text:GetText(),"%d")',15000);
  await page.waitForTimeout(12000);
  await lua('local bar=LibStub("AceAddon-3.0"):GetAddon("Quartz3"):GetModule("Player").Bar; bar:HookScript("OnShow",function() if UnitCastingInfo("player") then ArenaCastSeen=true end end); CastSpellByName("Holy Light","player")');
  await until('return ArenaCastSeen',20000);
  fs.mkdirSync('artifacts/pvp-addons',{recursive:true});
  await page.screenshot({path:'artifacts/pvp-addons/verified-ui.png'});
  const [errors]=await lua('return table.concat(ArenaAddonErrors,"\\n")');
  assert.equal(errors,'','Enabled addons must not raise Lua errors');
  console.log('PASS: configured addons, interrupt timers, cooldown text and live player cast bar');
  // Preferences must survive leaving and re-entering with the same guest/hero.
  await lua('InterruptBarDB.scale=1.2; ArenaReturnButton:Click()');
  await frame.waitForFunction(()=>wenilla.state?.session?.state==='charselect',{}, {timeout:90000});
  await until('return ArenaLaunchButton ~= nil');
  await lua('ArenaSavedButton:Click(); ArenaModeButtons.bots:Click(); ArenaLaunchButton:Click()');
  await until('return ArenaPvPDB and ArenaPvPDB.configured and ArenaInterruptBarRefresh and ArenaWorldCover and not ArenaWorldCover:IsShown()');
  assert.equal((await lua('return InterruptBarDB.scale'))[0],1.2,'Saved user settings must survive another match');
  await lua('ArenaReturnButton:Click()');
  console.log('PASS: saved addon preferences survive another arena');
 } finally {
  if(frame) {try {await lua('if ArenaReturnButton then ArenaReturnButton:Click() end');} catch {}}
  await browser.close();
 }
})().catch(error=>{console.error(error);process.exitCode=1;});

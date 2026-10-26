#!/usr/bin/env node
// Capture native level-80 tooltips from ten dedicated, provisioned characters.
// Never joins a real queue or match: Playwright intercepts only this guest's play/queue requests.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'../..');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const catalog=JSON.parse(fs.readFileSync(path.join(__dirname,'builds.json')));
const slots={0:16,1:17,2:18,3:1,4:3,5:5,6:6,7:7,8:8,9:9,10:10,11:15,12:4,13:11,14:12,15:13,16:14,17:2};
if(process.env.GEAR_ONLY)for(const b of catalog){
 const f=path.join(root,`artifacts/lobby/tooltips-${b.id}.json`);
 if(fs.existsSync(f)){const previous=JSON.parse(fs.readFileSync(f)).gear;
  const signature=gear=>JSON.stringify(gear.map(g=>[g.slot,g.item,g.enchant]));
  if(signature(previous)===signature(b.gear))b.gear=previous;
 }
}
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true,args:['--enable-unsafe-webgpu','--use-angle=metal']});
 try{
 const page=await browser.newPage({viewport:{width:1440,height:1000}});
 page.on('console',m=>{if(m.text().includes('Arena lobby:'))console.log(m.text());});
 await page.route('**/api/play',r=>r.fulfill({json:{state:'queued',waiting:1,needed:4}}));
 await page.route('**/api/queue',r=>r.request().method()==='GET'?r.fulfill({json:{state:'queued',waiting:1,needed:4}}):r.continue());
 await page.goto('http://127.0.0.1:8090');await page.waitForTimeout(1000);
 const frame=page.frames().find(f=>f.url().includes('/game/'));
 const lua=code=>frame.evaluate(code=>wenilla.lua(code),code);
 async function until(code,timeout=120000){const start=Date.now();while(Date.now()-start<timeout){try{if((await lua(code))[0])return;}catch{}await page.waitForTimeout(300);}throw Error('Timeout: '+code);}
 const read=`local out={};for i=1,GameTooltip:NumLines()do local l=_G['GameTooltipTextLeft'..i];local r=_G['GameTooltipTextRight'..i];local lr,lg,lb=l:GetTextColor();local rr,rg,rb=r:GetTextColor();local row={l:GetText() or '',lr,lg,lb,r:IsShown() and (r:GetText() or '') or '',rr,rg,rb};for _,v in ipairs(row)do table.insert(out,v)end end;return unpack(out)`;
 async function capture(call){
  await lua('GameTooltip:SetOwner(ArenaWorldControls,"ANCHOR_NONE");GameTooltip:ClearLines();'+call+';GameTooltip:Show()');await page.waitForTimeout(100);
  await lua(call);const flat=await lua(read);const lines=[];for(let i=0;i<flat.length;i+=8)lines.push(flat.slice(i,i+8));
  assert(lines.length>=(call.includes('InventoryItem')?2:3),'Incomplete native tooltip: '+call+': '+JSON.stringify(lines));return lines;
 }
 for(let index=Number(process.env.START_INDEX)||0;index<catalog.length;index++){
  const b=catalog[index];await until('return ArenaLaunchButton~=nil and ArenaLobby:IsShown()');
  await lua(`ArenaHeroButtons[${index+1}]:Click();ArenaModeButtons.players:Click();ArenaLaunchButton:Click()`);
  await until('return ArenaQueueWaiting==1 and UnitLevel("player")==80');
  await page.waitForTimeout(2200);
  assert.equal((await lua('return select(2,UnitClass("player"))'))[0],b.className.replaceAll(' ','').toUpperCase());
  for(const gear of b.gear){gear.tooltip=await capture(`GameTooltip:SetInventoryItem("player",${slots[gear.slot]})`);gear.inventorySlot=slots[gear.slot];}
  if(!process.env.GEAR_ONLY)for(let ti=1;ti<=3;ti++){
   const [count]=await lua(`return GetNumTalents(${ti})`);
   for(let ni=1;ni<=count;ni++){
    const [name,icon,row,col,rank]=await lua(`return GetTalentInfo(${ti},${ni})`);
    const node=b.talentTrees[ti-1].nodes.find(n=>n.row===row-1&&n.column===col-1);
    assert(node && node.name===name,`Talent mismatch ${b.name} ${name}`);assert.equal(node.rank,rank);
    node.tooltip=await capture(`GameTooltip:SetTalent(${ti},${ni})`);node.treeIndex=ti;node.talentIndex=ni;
   }
  }
  if(!process.env.GEAR_ONLY)for(let gi=1;gi<=6;gi++){
   const lines=await capture(`GameTooltip:SetGlyph(${gi})`);
   const glyph=b.glyphs.find(g=>lines.some(l=>l[0].includes(g.name)));
   assert(glyph,`Glyph mismatch ${JSON.stringify(lines)}`);glyph.tooltip=lines;glyph.socket=gi;
  }
  fs.writeFileSync(path.join(root,`artifacts/lobby/tooltips-${b.id}.json`),JSON.stringify(b,null,2)+'\n');
  b.tooltipLevel=80;b.tooltipSource='native-client';
  console.log('Captured native tooltips:',b.name,b.gear.length,b.talentTrees.reduce((a,t)=>a+t.nodes.length,0),b.glyphs.length);
  await lua('GameTooltip:Hide();ArenaReturnButton:Click()');
  await frame.waitForFunction(()=>wenilla.state?.session?.state==='charselect',{},{timeout:90000});
 }
 fs.writeFileSync(path.join(__dirname,'builds.json'),JSON.stringify(catalog,null,2)+'\n');
 console.log('Saved complete native tooltip catalog');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});

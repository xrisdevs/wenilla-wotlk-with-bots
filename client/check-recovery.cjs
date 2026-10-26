#!/usr/bin/env node
// Exercise the real host recovery code with a small stand-in for the game VM.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 const page=await browser.newPage();let loads=0,cleanups=0,available=true;
 await page.route('http://arena.test/**',async route=>{
  const url=new URL(route.request().url());
  if(url.pathname==='/')return route.fulfill({contentType:'text/html',body:fs.readFileSync(path.join(__dirname,'lobby/index.html'),'utf8')});
  if(url.pathname==='/lobby/recovery.js')return route.fulfill({contentType:'text/javascript',body:fs.readFileSync(path.join(__dirname,'lobby/recovery.js'),'utf8')});
  if(url.pathname==='/healthz')return route.fulfill({status:available?200:503,body:'{}'});
  if(url.pathname==='/api/recover'){cleanups++;return route.fulfill({body:'{}'});}
  if(url.pathname==='/game/'){
   loads++;return route.fulfill({contentType:'text/html',body:`<script>parent.arenaRecovery.attach(window);setInterval(()=>parent.arenaRecovery.frame({session:{state:'charselect',connected:true}}),100);parent.arenaRecovery.ready();</script><p>Custom lobby</p>`});
  }
  return route.abort();
 });
 try{
  await page.goto('http://arena.test/');await page.waitForFunction(()=>!document.querySelector('#arena-recovery'));
  const game=page.frames().find(f=>f.url().includes('/game/'));
  available=false;
  await game.evaluate(()=>setTimeout(()=>{throw new WebAssembly.RuntimeError('unreachable');},0));
  await page.waitForFunction(()=>document.querySelector('#arena-recovery')?.textContent.includes('Waiting for the server'));
  assert.equal(loads,1);assert.equal(cleanups,0);assert.equal(await page.locator('iframe').count(),0);
  available=true;
  await page.waitForFunction(()=>document.querySelector('#game') && !document.querySelector('#arena-recovery'),null,{timeout:15000});
  assert.equal(loads,2);assert.equal(cleanups,1);
  assert.equal(new URL(page.frames().find(f=>f.url().includes('/game/')).url()).search,'');
  console.log('PASS fatal WASM error replaces the iframe, waits for server health, cleans up once and returns to a fresh lobby');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});

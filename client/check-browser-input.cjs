#!/usr/bin/env node
// Live regression check: needs a running gateway/server and a dedicated spectator account.
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const credentials = { user: process.env.WOW_USER, pass: process.env.WOW_PASS, char: process.env.WOW_CHAR };
assert(credentials.user && credentials.pass, 'Set WOW_USER and WOW_PASS for a dedicated test account');
const output = path.resolve(__dirname, '../artifacts/browser/input');
fs.mkdirSync(output, { recursive: true });

(async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true, args: ['--enable-unsafe-webgpu', ...(process.platform === 'darwin' ? ['--use-angle=metal'] : [])] });
  try {
    for (const dpr of (process.env.TEST_DPRS || '1,2').split(',').map(Number)) {
      const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: dpr });
      try {
        const page = await context.newPage();
        await page.addInitScript(env => { window.__wenilla_env = { ...env, nosound: '1' }; }, credentials);
        await page.goto(process.env.BROWSER_URL || 'http://127.0.0.1:8090');
        await page.waitForFunction(() => window.wenilla?.state?.session?.state === 'inworld', {}, { timeout: 120000 });
        // InWorld precedes completion of map loading; wait for the game's input gate too.
        let ready = false;
        for (let attempt = 0; attempt < 120; attempt++) {
          await page.mouse.move(720 + attempt % 2, 450);
          await page.waitForTimeout(1000);
          const cursor = await page.evaluate(() => wenilla.lua('return GetCursorPosition()'));
          if (cursor[0] > 0 && cursor[1] > 0) { ready = true; break; }
        }
        assert(ready, 'The game never accepted pointer input');
        await page.evaluate(() => wenilla.lua('BotArenaPanel:Hide()'));
        for (const [width, height, expectedOpen] of [[1440, 900, true], [1000, 700, false]]) {
          await page.setViewportSize({ width, height });
          await page.waitForTimeout(1000);
          const canvas = await page.locator('#benilla').boundingBox();
          const dimensions = await page.evaluate(() => ({ width: document.querySelector('canvas').width, height: document.querySelector('canvas').height }));
          assert.deepEqual(dimensions, { width: 1920, height: 1080 });
          assert(Math.abs(canvas.width / canvas.height - 16 / 9) < 0.001);
          assert(Math.abs(canvas.width - Math.min(width, height * 16 / 9)) < 1);
          // Actual mouse input at the spectator launcher's screen position, not a Lua Click().
          await page.mouse.click(canvas.x + 49 / (768 * 16 / 9) * canvas.width, canvas.y + 16 / 768 * canvas.height);
          await page.waitForTimeout(500);
          const [shown] = await page.evaluate(() => wenilla.lua('return BotArenaPanel:IsShown()'));
          assert.equal(Boolean(shown), expectedOpen, `Panel click at DPR ${dpr}, ${width}x${height}`);
          await page.screenshot({ path: path.join(output, `dpr-${dpr}-${width}.png`) });
        }
        console.log(`PASS: DPR ${dpr}: 1080p buffer, fitted image, real panel clicks before/after resize`);
      } finally { await context.close(); }
    }
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });

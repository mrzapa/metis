const { chromium } = require('C:\\Users\\samwe\\AppData\\Roaming\\npm\\node_modules\\playwright');

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.setViewportSize({ width: 1440, height: 900 });

  // Settings page
  await page.goto('http://localhost:3123/settings', { waitUntil: 'networkidle', timeout: 20000 });
  await page.waitForTimeout(2000);
  await page.screenshot({ path: 'C:/Users/samwe/Documents/metis/apps/metis-web/public/phase4-settings.png', fullPage: false });
  console.log('settings done');

  // Diagnostics page
  await page.goto('http://localhost:3123/diagnostics', { waitUntil: 'networkidle', timeout: 20000 });
  await page.waitForTimeout(2000);
  await page.screenshot({ path: 'C:/Users/samwe/Documents/metis/apps/metis-web/public/phase4-diagnostics.png', fullPage: false });
  console.log('diagnostics done');

  // Chat page
  await page.goto('http://localhost:3123/chat', { waitUntil: 'networkidle', timeout: 20000 });
  await page.waitForTimeout(2000);
  await page.screenshot({ path: 'C:/Users/samwe/Documents/metis/apps/metis-web/public/phase4-chat.png', fullPage: false });
  console.log('chat done');

  // Landing page
  await page.goto('http://localhost:3123', { waitUntil: 'networkidle', timeout: 20000 });
  await page.waitForTimeout(2000);
  await page.screenshot({ path: 'C:/Users/samwe/Documents/metis/apps/metis-web/public/phase4-landing.png', fullPage: false });
  console.log('landing done');

  await browser.close();
  console.log('All screenshots saved');
})();

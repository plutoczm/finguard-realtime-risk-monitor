const { chromium } = require('playwright');

async function inspect(url, viewport, screenshotPath) {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport });
  const errors = [];
  page.on('console', msg => {
    if (msg.type() === 'error') errors.push(msg.text());
  });
  page.on('pageerror', err => errors.push(err.message));
  await page.goto(url, { waitUntil: 'networkidle', timeout: 60000 });
  await page.waitForTimeout(8000);
  const result = await page.evaluate(() => {
    const canvases = Array.from(document.querySelectorAll('canvas'));
    const chartCount = document.querySelectorAll('.chart').length;
    const kpiCount = document.querySelectorAll('.kpi').length;
    const panels = document.querySelectorAll('.holo-panel, .holo-card').length;
    const samples = canvases.map((canvas, index) => {
      const width = canvas.width;
      const height = canvas.height;
      let dataUrlLength = 0;
      try {
        dataUrlLength = canvas.toDataURL('image/png').length;
      } catch (err) {
        dataUrlLength = -1;
      }
      return { index, width, height, dataUrlLength };
    });
    return { chartCount, kpiCount, panels, canvasCount: canvases.length, samples };
  });
  await page.screenshot({ path: screenshotPath, fullPage: true });
  await browser.close();
  return { viewport, screenshotPath, errors, result };
}

(async () => {
  const url = process.argv[2] || 'http://127.0.0.1:8090';
  const desktop = await inspect(url, { width: 1600, height: 1000 }, 'dashboard/verify-desktop.png');
  const mobile = await inspect(url, { width: 390, height: 900 }, 'dashboard/verify-mobile.png');
  const payload = { desktop, mobile };
  console.log(JSON.stringify(payload, null, 2));
  const failed =
    desktop.errors.length ||
    mobile.errors.length ||
    desktop.result.canvasCount < 6 ||
    mobile.result.canvasCount < 2 ||
    desktop.result.kpiCount < 6 ||
    desktop.result.panels < 8 ||
    desktop.result.samples.filter(sample => sample.dataUrlLength > 5000).length < 5;
  process.exit(failed ? 1 : 0);
})().catch(err => {
  console.error(err);
  process.exit(1);
});

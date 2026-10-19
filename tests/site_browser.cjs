const { test, before, after } = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const root = path.resolve(__dirname, '../site');
let browser, server, base;

before(async () => {
  server = http.createServer((req, res) => {
    const file = path.resolve(root, '.' + new URL(req.url, 'http://localhost').pathname.replace(/\/$/, '/index.html'));
    if (!file.startsWith(root + path.sep) || !fs.existsSync(file)) { res.writeHead(404).end(); return; }
    res.setHeader('Content-Type', ({ '.html': 'text/html', '.css': 'text/css', '.js': 'text/javascript' })[path.extname(file)] || 'application/octet-stream');
    fs.createReadStream(file).pipe(res);
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  base = `http://127.0.0.1:${server.address().port}`;
  browser = await chromium.launch(process.env.BROWSER_CHANNEL ? { channel: process.env.BROWSER_CHANNEL } : {});
});
after(async () => { await browser?.close(); await new Promise(resolve => server?.close(resolve)); });

async function open(viewport = { width: 1440, height: 1000 }) {
  const page = await browser.newPage({ viewport });
  await page.goto(base, { waitUntil: 'networkidle' });
  await page.waitForSelector('#board tbody tr');
  return page;
}

test('phone layout keeps content within the viewport', async () => {
  const page = await open({ width: 390, height: 844 });
  try {
    for (const id of ['rankings', 'anatomy', 'fighters', 'divisions', 'checks']) {
      await page.locator('#' + id).scrollIntoViewIfNeeded();
      await page.waitForTimeout(350);
      const size = await page.evaluate(() => [innerWidth, document.documentElement.scrollWidth]);
      assert.ok(size[1] <= size[0] + 1, `${id}: viewport ${size[0]}, content ${size[1]}`);
    }
  } finally { await page.close(); }
});

test('resizing and dark mode keep charts within their panels', async () => {
  const page = await open();
  try {
    await page.locator('#anatomy').scrollIntoViewIfNeeded();
    await page.waitForSelector('#anat-chart.js-plotly-plot');
    await page.setViewportSize({ width: 390, height: 844 });
    await page.emulateMedia({ colorScheme: 'dark', reducedMotion: 'reduce' });
    await page.waitForTimeout(700);
    const size = await page.evaluate(() => [innerWidth, document.documentElement.scrollWidth]);
    assert.ok(size[1] <= size[0] + 1, `resized viewport ${size[0]}, content ${size[1]}`);
    const colors = await page.evaluate(() => ({
      panel: getComputedStyle(document.documentElement).getPropertyValue('--bg').trim(),
      chart: document.getElementById('anat-chart').layout.paper_bgcolor,
    }));
    assert.equal(colors.chart, colors.panel);
    if (process.env.SITE_SCREENSHOTS) await page.screenshot({ path: path.join(process.env.SITE_SCREENSHOTS, 'after-dark-mobile.png') });
  } finally { await page.close(); }
});

test('phone filters start compact and expand on request', async () => {
  const page = await open({ width: 390, height: 844 });
  try {
    assert.equal(await page.locator('.filter-panel').getAttribute('open'), null);
    await page.locator('.filter-panel summary').click();
    await page.locator('#c-gender [data-v="F"]').click();
    assert.equal(await page.locator('#c-gender [data-v="F"]').getAttribute('aria-pressed'), 'true');
    await page.setViewportSize({ width: 1440, height: 1000 });
    assert.equal(await page.locator('#c-gender').isVisible(), true);
  } finally { await page.close(); }
});

test('search preserves a fighter’s position within a weight class', async () => {
  const page = await open();
  try {
    await page.locator('#c-view [data-v="prime"]').click();
    await page.locator('#c-div').selectOption('Lightweight');
    const row = page.locator('#board tbody tr').nth(2);
    const name = await row.locator('.namebtn').textContent();
    const rank = await row.locator('td').first().textContent();
    await page.locator('#c-search').fill(name);
    assert.equal(await page.locator('#board tbody tr').count(), 1);
    assert.equal(await page.locator('#board tbody tr td').first().textContent(), rank);
  } finally { await page.close(); }
});

test('weight-class toggles work with a keyboard and expose their state', async () => {
  const page = await open();
  try {
    const toggle = page.locator('#dv-chips button').first();
    assert.ok(await toggle.count(), 'weight classes must be keyboard-operable buttons');
    await toggle.scrollIntoViewIfNeeded();
    const old = await toggle.getAttribute('aria-pressed');
    await toggle.focus();
    await page.keyboard.press('Space');
    assert.notEqual(await toggle.getAttribute('aria-pressed'), old);
  } finally { await page.close(); }
});

test('all analysis sections render, filters and comparisons remain usable', async () => {
  const page = await open();
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  try {
    await page.locator('#c-gender [data-v="F"]').click();
    assert.ok(await page.locator('#board tbody tr').count());
    await page.locator('#c-search').fill('no-such-fighter');
    assert.match(await page.locator('#board').textContent(), /No ranked fighters/);
    await page.locator('#c-search').fill('');
    await page.locator('#c-gender [data-v="M"]').click();
    for (const id of ['anatomy', 'fighters', 'careers', 'movers', 'streaks', 'divisions', 'lineage', 'dominance', 'policy', 'checks', 'benchmark']) {
      await page.locator('#' + id).scrollIntoViewIfNeeded();
      await page.waitForSelector(`#${id} .js-plotly-plot`);
      assert.ok(await page.locator(`#${id} .js-plotly-plot`).count(), `${id} chart did not render`);
    }
    await page.locator('#fighters').scrollIntoViewIfNeeded();
    await page.locator('#sel-add').fill('Anderson Silva');
    await page.locator('#sel-add').dispatchEvent('change');
    await page.waitForFunction(() => document.getElementById('sel-chips').textContent.includes('Anderson Silva'));
    assert.match(await page.locator('#sel-chips').textContent(), /Anderson Silva/);
    assert.deepEqual(errors, []);
    assert.equal(await page.locator('#fail').isVisible(), false);
    if (process.env.SITE_SCREENSHOTS) {
      await page.evaluate(() => scrollTo(0, 0));
      await page.screenshot({ path: path.join(process.env.SITE_SCREENSHOTS, 'after-desktop.png') });
      await page.setViewportSize({ width: 390, height: 844 });
      await page.waitForTimeout(500);
      await page.screenshot({ path: path.join(process.env.SITE_SCREENSHOTS, 'after-mobile.png') });
    }
  } finally { await page.close(); }
});

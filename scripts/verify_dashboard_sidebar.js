#!/usr/bin/env node
/**
 * BigQMT dashboard sidebar navigation verification (read-only).
 *
 * Run with the Playwright skill runner so module resolution is correct:
 *   $env:SKILL_DIR = "C:\Users\developer\.codex\skills\playwright-skill"
 *   node "$env:SKILL_DIR/run.js" scripts/verify_dashboard_sidebar.js
 *
 * Optional environment:
 *   BIGQMT_DASHBOARD_PORTS="17890,17891"   ports to check (default both)
 *   PW_HEADLESS="false"                    show the browser window
 *   PW_ARTIFACT_DIR=<dir>                  screenshot output directory
 *
 * This script only reads local dashboards over HTTP. It is not part of the
 * trading path and never touches Coordinator, Redis or QMT.
 */
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');

const ROUTES = [
  ['overview', '运行总览'],
  ['strategies', '策略账户'],
  ['account', '账户与持仓'],
  ['orders', '委托与成交'],
  ['market', '行情健康度'],
  ['audit', '审计与日志'],
];

// h2 elements carry a muted suffix span (e.g. '· 只读 / 不生成委托'), so match by
// prefix. '策略池登记' only renders when the profile has registry entries.
const STRATEGY_EXTRA_HEADINGS = ['v1.1.15 收盘影子信号'];
const STRATEGY_REGISTRY_HEADING = '策略池登记';

function ports() {
  const raw = process.env.BIGQMT_DASHBOARD_PORTS || '17890,17891';
  return raw.split(',').map((s) => parseInt(s.trim(), 10)).filter(Number.isFinite);
}

function artifactDir() {
  if (process.env.PW_ARTIFACT_DIR) return process.env.PW_ARTIFACT_DIR;
  return path.resolve(__dirname, '..', 'runtime_data', 'artifacts', 'dashboard_sidebar');
}

async function snapshot(page) {
  return page.evaluate(() => {
    const on = document.querySelector('aside .nav.on');
    const h1 = document.querySelector('main .title h1');
    return {
      path: location.pathname,
      mainTitle: h1 ? h1.textContent.trim() : null,
      navOn: on ? on.textContent.trim() : null,
      docTitle: document.title,
    };
  });
}

async function headingList(page) {
  return page.evaluate(() =>
    Array.from(document.querySelectorAll('main h2')).map((n) => n.textContent.trim())
  );
}

function pathOk(route, actual) {
  // The dashboard pushes '/<prefix>/<route>' (prefix = profile); '/' means overview.
  const segment = (actual || '').split('/').filter(Boolean).pop() || 'overview';
  return segment === route;
}

async function checkPort(browser, port, outDir) {
  const base = 'http://127.0.0.1:' + port + '/';
  const page = await browser.newPage();
  const failures = [];
  const routes = [];
  try {
    await page.goto(base, { waitUntil: 'domcontentloaded' });
    await page.waitForSelector('#app');

    for (const [route, title] of ROUTES) {
      await page.click("aside .nav[data-route='" + route + "']");
      await page.waitForFunction(
        (expected) => {
          const h1 = document.querySelector('main .title h1');
          return !!h1 && h1.textContent.trim() === expected;
        },
        title,
        { timeout: 8000 }
      );
      const snap = await snapshot(page);
      const entry = { route, expected_title: title, ...snap };
      const problems = [];
      if (!pathOk(route, snap.path)) problems.push('path=' + snap.path);
      if (snap.mainTitle !== title) problems.push('mainTitle=' + snap.mainTitle);
      if (snap.navOn !== title) problems.push('navOn=' + snap.navOn);
      if (!snap.docTitle.includes(title)) problems.push('docTitle=' + snap.docTitle);
      entry.ok = problems.length === 0;
      if (problems.length) {
        entry.problems = problems;
        failures.push({ port, route, problems });
      }
      routes.push(entry);
    }

    // Regression guard: leaving a deep route and returning to 运行总览 must
    // reset heading, sidebar highlight and document title.
    await page.click("aside .nav[data-route='audit']");
    await page.waitForFunction(
      () => {
        const h1 = document.querySelector('main .title h1');
        return !!h1 && h1.textContent.trim() === '审计与日志';
      },
      null,
      { timeout: 8000 }
    );
    await page.click("aside .nav[data-route='overview']");
    await page.waitForFunction(
      () => {
        const h1 = document.querySelector('main .title h1');
        return !!h1 && h1.textContent.trim() === '运行总览';
      },
      null,
      { timeout: 8000 }
    );
    const back = await snapshot(page);
    const backProblems = [];
    if (!pathOk('overview', back.path)) backProblems.push('path=' + back.path);
    if (back.mainTitle !== '运行总览') backProblems.push('mainTitle=' + back.mainTitle);
    if (back.navOn !== '运行总览') backProblems.push('navOn=' + back.navOn);
    if (!back.docTitle.includes('运行总览')) backProblems.push('docTitle=' + back.docTitle);
    if (backProblems.length) failures.push({ port, route: 'overview-regression', problems: backProblems });

    // 策略账户 must stay a complete page (not overwritten by the strategy tab).
    await page.click("aside .nav[data-route='strategies']");
    await page.waitForFunction(
      () => {
        const h1 = document.querySelector('main .title h1');
        return !!h1 && h1.textContent.trim() === '策略账户';
      },
      null,
      { timeout: 8000 }
    );
    const headings = await headingList(page);
    const has = (needle) => headings.some((h) => h.indexOf(needle) === 0);
    const missing = STRATEGY_EXTRA_HEADINGS.filter((h) => !has(h));
    const status = await page.evaluate(() => window.__bigqmtStatus || {});
    const registryCount = (status.strategy_registry || []).length;
    if (registryCount > 0 && !has(STRATEGY_REGISTRY_HEADING)) missing.push(STRATEGY_REGISTRY_HEADING);
    if (missing.length) failures.push({ port, route: 'strategies-content', problems: missing.map((m) => 'missing heading: ' + m) });

    if (outDir) {
      fs.mkdirSync(outDir, { recursive: true });
      await page.screenshot({ path: path.join(outDir, 'strategies_' + port + '.png'), fullPage: true });
      await page.click("aside .nav[data-route='overview']");
      await page.waitForTimeout(300);
      await page.screenshot({ path: path.join(outDir, 'overview_' + port + '.png'), fullPage: true });
    }

    return { port, ok: failures.length === 0, routes, overview_back: back, strategies_headings: headings, strategy_registry_count: registryCount, failures };
  } finally {
    await page.close();
  }
}

(async () => {
  const outDir = artifactDir();
  const browser = await chromium.launch({ headless: process.env.PW_HEADLESS !== 'false' });
  const report = { checked_at: new Date().toISOString(), artifacts: outDir, dashboards: [], failures: [] };
  try {
    for (const port of ports()) {
      const result = await checkPort(browser, port, outDir);
      report.dashboards.push(result);
      report.failures.push(...result.failures);
    }
  } finally {
    await browser.close();
  }
  report.ok = report.failures.length === 0;
  console.log(JSON.stringify(report, null, 2));
  process.exitCode = report.ok ? 0 : 1;
})();

/* eslint-disable @typescript-eslint/no-require-imports */

const fs = require('fs');
const os = require('os');
const path = require('path');

function findPlaywrightModule() {
  const localAppData = process.env.LOCALAPPDATA;
  if (!localAppData) {
    throw new Error('LOCALAPPDATA is not set');
  }

  const npxRoot = path.join(localAppData, 'npm-cache', '_npx');
  const candidates = fs
    .readdirSync(npxRoot, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => {
      const fullName = path.join(npxRoot, entry.name);
      return {
        fullName,
        modulePath: path.join(fullName, 'node_modules', 'playwright'),
        mtimeMs: fs.statSync(fullName).mtimeMs,
      };
    })
    .filter((entry) => fs.existsSync(path.join(entry.modulePath, 'index.js')))
    .sort((left, right) => right.mtimeMs - left.mtimeMs);

  if (candidates.length === 0) {
    throw new Error('No cached Playwright package was found under npm-cache/_npx');
  }

  return require(candidates[0].modulePath);
}

function findBrowserExecutable() {
  const candidates = [
    'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
    'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
    'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
  ];

  const executablePath = candidates.find((candidate) => fs.existsSync(candidate));
  if (!executablePath) {
    throw new Error('No supported browser executable was found');
  }
  return executablePath;
}

function safeJson(text) {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

function clip(value, maxLength = 2400) {
  if (typeof value !== 'string') {
    return value;
  }
  return value.length > maxLength
    ? `${value.slice(0, maxLength)}\n...[truncated]`
    : value;
}

function excerptAround(text, needle, radius = 500) {
  if (!text || !needle) {
    return clip(text, radius * 2);
  }
  const index = text.indexOf(needle);
  if (index === -1) {
    return clip(text, radius * 2);
  }
  const start = Math.max(0, index - radius);
  const end = Math.min(text.length, index + needle.length + radius);
  return text.slice(start, end).trim();
}

async function main() {
  const playwright = findPlaywrightModule();
  const executablePath = findBrowserExecutable();
  const artifactDir = path.join(os.tmpdir(), 'metis-nyx-smoke');
  fs.mkdirSync(artifactDir, { recursive: true });

  const frontendUrl = 'http://127.0.0.1:3001/chat';
  const apiBase = 'http://127.0.0.1:8001';
  const prompt = 'Design a frosted glass panel with a glowing card.';

  const consoleLogs = [];
  const pageErrors = [];
  const requestLog = [];
  const responseLog = [];

  const result = {
    frontendUrl,
    apiBase,
    prompt,
    executablePath,
    actionAppeared: false,
    queryResponse: null,
    actionResponse: null,
    ui: {
      actionTitle: null,
      components: [],
      resultHeadline: null,
      resultMeta: null,
      outputExcerpt: null,
      bodyExcerpt: null,
    },
    screenshots: {},
    requestSummary: {
      frontend3001: [],
      api8001: [],
      wrongPorts: [],
    },
    consoleLogs: [],
    pageErrors: [],
    scriptError: null,
  };

  let browser;
  let context;

  try {
    browser = await playwright.chromium.launch({
      executablePath,
      headless: true,
      args: ['--disable-dev-shm-usage'],
    });
    context = await browser.newContext({ viewport: { width: 1600, height: 1200 } });
    const page = await context.newPage();

    page.on('console', (message) => {
      consoleLogs.push({ type: message.type(), text: message.text() });
    });

    page.on('pageerror', (error) => {
      pageErrors.push(String(error && (error.stack || error.message || error)));
    });

    page.on('request', (request) => {
      const url = request.url();
      if (!url.includes('127.0.0.1:3001') && !url.includes('127.0.0.1:8001') && !url.includes('127.0.0.1:3000') && !url.includes('127.0.0.1:8000')) {
        return;
      }
      requestLog.push({
        method: request.method(),
        url,
        postData: clip(request.postData() || '', 1200),
      });
    });

    page.on('response', async (response) => {
      const url = response.url();
      if (!url.includes('127.0.0.1:8001') && !url.includes('127.0.0.1:8000')) {
        return;
      }

      let body = null;
      if (url.includes('/v1/query/direct') || url.includes('/actions')) {
        try {
          body = clip(await response.text());
        } catch {
          body = null;
        }
      }

      responseLog.push({
        status: response.status(),
        url,
        body,
      });
    });

    await page.goto(frontendUrl, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await page.getByLabel('Message input').waitFor({ state: 'visible', timeout: 60000 });

    const initialShot = path.join(artifactDir, 'nyx-chat-initial.png');
    await page.screenshot({ path: initialShot, fullPage: true });
    result.screenshots.initial = initialShot;

    const messageInput = page.getByLabel('Message input');
    const sendButton = page.getByRole('button', { name: 'Send message' });

    const queryResponsePromise = page.waitForResponse(
      (response) =>
        response.url().includes(`${apiBase}/v1/query/direct`) &&
        response.request().method() === 'POST',
      { timeout: 240000 },
    );

    await messageInput.fill(prompt);
    await sendButton.click();

    const queryResponse = await queryResponsePromise;
    const queryBodyText = await queryResponse.text();
    const queryBody = safeJson(queryBodyText);

    result.queryResponse = {
      status: queryResponse.status(),
      body: queryBody || clip(queryBodyText),
    };

    const nyxAction = Array.isArray(queryBody?.actions)
      ? queryBody.actions.find((action) => action && action.action_type === 'nyx_install')
      : null;

    if (!nyxAction) {
      const bodyText = await page.locator('body').innerText();
      result.ui.bodyExcerpt = excerptAround(bodyText, queryBody?.answer_text || prompt);
      throw new Error('Direct query completed without a Nyx install action in the API response');
    }

    const approveButton = page.getByRole('button', { name: 'Approve' });
    await approveButton.waitFor({ state: 'visible', timeout: 30000 });
    result.actionAppeared = true;

    result.ui.actionTitle = nyxAction.label || 'Approve Nyx install proposal';
    result.ui.components = Array.isArray(nyxAction.proposal?.component_names) && nyxAction.proposal.component_names.length > 0
      ? nyxAction.proposal.component_names
      : Array.isArray(nyxAction.payload?.component_names)
        ? nyxAction.payload.component_names
        : [];

    const actionCardShot = path.join(artifactDir, 'nyx-chat-action-card.png');
    await page.screenshot({ path: actionCardShot, fullPage: true });
    result.screenshots.actionCard = actionCardShot;

    const actionResponsePromise = page.waitForResponse(
      (response) =>
        response.url().includes(`${apiBase}/v1/runs/`) &&
        response.url().includes('/actions') &&
        response.request().method() === 'POST',
      { timeout: 240000 },
    );

    await approveButton.click();

    const actionResponse = await actionResponsePromise;
    const actionBodyText = await actionResponse.text();
    const actionBody = safeJson(actionBodyText);

    result.actionResponse = {
      status: actionResponse.status(),
      body: actionBody || clip(actionBodyText),
    };

    const resultHeadlineLocator = page.getByText(/Installer completed|Installer failed|Proposal declined/).first();
    await resultHeadlineLocator.waitFor({ state: 'visible', timeout: 60000 });
    result.ui.resultHeadline = (await resultHeadlineLocator.textContent())?.trim() || null;

    const bodyText = await page.locator('body').innerText();
    result.ui.bodyExcerpt = excerptAround(bodyText, result.ui.resultHeadline);
    const metaMatch = bodyText.match(/\b\d+ components?(?:\s+•\s+exit\s+-?\d+)?/i);
    result.ui.resultMeta = metaMatch ? metaMatch[0] : null;
    result.ui.outputExcerpt = clip((await page.locator('pre').first().textContent().catch(() => null)) || null);

    const finalShot = path.join(artifactDir, 'nyx-chat-after-approval.png');
    await page.screenshot({ path: finalShot, fullPage: true });
    result.screenshots.final = finalShot;
  } catch (error) {
    result.scriptError = String(error && (error.stack || error.message || error));
  } finally {
    result.requestSummary.frontend3001 = requestLog
      .filter((entry) => entry.url.includes('127.0.0.1:3001'))
      .map((entry) => ({ method: entry.method, url: entry.url }));
    result.requestSummary.api8001 = requestLog
      .filter((entry) => entry.url.includes('127.0.0.1:8001'))
      .map((entry) => ({ method: entry.method, url: entry.url, postData: entry.postData }));
    result.requestSummary.wrongPorts = requestLog
      .filter((entry) => entry.url.includes('127.0.0.1:3000') || entry.url.includes('127.0.0.1:8000'))
      .map((entry) => ({ method: entry.method, url: entry.url }));
    result.consoleLogs = consoleLogs;
    result.pageErrors = pageErrors;
    result.responseLog = responseLog;

    if (context) {
      await context.close().catch(() => {});
    }
    if (browser) {
      await browser.close().catch(() => {});
    }
  }

  console.log(`SMOKE_RESULT ${JSON.stringify(result)}`);
}

main().catch((error) => {
  console.error(`SMOKE_FATAL ${error && (error.stack || error.message || error)}`);
  process.exitCode = 1;
});
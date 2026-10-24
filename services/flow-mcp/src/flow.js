// Drives the Flow web UI in the dedicated Chrome: generate images, upload local files as
// named assets, and reference those assets inside prompts. Selectors avoid translated text
// where possible (CSS classes, material icon names, radio values, model names) so it works
// with any UI language.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright-core';
import { CDP_PORT, FLOW_URL, ensureChrome } from './chrome.js';

export const MODELS = {
  'pro': 'Nano Banana Pro',
  '2': 'Nano Banana 2.1',
  'lite': 'Nano Banana 2 Lite',
};
export const ASPECTS = ['16:9', '4:3', '1:1', '3:4', '9:16'];

// In prompts, @{name} becomes a reference chip to the project asset called `name`.
// Any other "@" (e.g. "@Image 1") is left as plain text.
export const MENTION = /@\{([^}]+)\}/g;

// Everything lives next to the code, so the folder can be moved as a whole.
// In containers, point FLOW_STATE_FILE/FLOW_CONFIG_FILE at a persisted volume:
// the projectId must survive rebuilds and restarts.
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const STATE_FILE = process.env.FLOW_STATE_FILE || path.join(ROOT, 'state.json');
const CONFIG_FILE = process.env.FLOW_CONFIG_FILE || path.join(ROOT, 'config.json');

const readJson = (file) => { try { return JSON.parse(fs.readFileSync(file, 'utf8')); } catch { return {}; } };
const readState = () => readJson(STATE_FILE);

// Output folder: FLOW_OUTPUT_DIR, else "outputDir" in config.json (written at install), else output/.
export const DEFAULT_OUT = process.env.FLOW_OUTPUT_DIR || readJson(CONFIG_FILE).outputDir || path.join(ROOT, 'output');

const SELECT_ALL = process.platform === 'darwin' ? 'Meta+A' : 'Control+A';
export function writeState(patch) {
  fs.writeFileSync(STATE_FILE, JSON.stringify({ ...readState(), ...patch }, null, 2));
}
export function getProjectId() {
  return process.env.FLOW_PROJECT_ID || readState().projectId;
}

async function connect() {
  await ensureChrome();
  const browser = await chromium.connectOverCDP(`http://127.0.0.1:${CDP_PORT}`);
  const context = browser.contexts()[0];
  return { browser, context };
}

async function flowPage(context) {
  return context.pages().find((p) => p.url().startsWith(FLOW_URL)) || context.newPage();
}

async function assertSignedIn(page) {
  if (/accounts\.google\.com/.test(page.url())) {
    throw new Error('Not signed in to Google in the Flow Chrome. Run `node src/cli.js chrome`, sign in, and retry.');
  }
}

// Creates a new Flow project from the home page and remembers it.
export async function newProject() {
  const { browser, context } = await connect();
  try {
    const page = await flowPage(context);
    await page.goto(FLOW_URL, { waitUntil: 'domcontentloaded' });
    await assertSignedIn(page);
    const btn = page.getByRole('button', { name: /^(Nuevo proyecto|New project|Nouveau projet|Nuovo progetto|Neues Projekt|Novo projeto)$/i });
    await btn.click({ timeout: 20000 });
    await page.waitForURL(/\/project\/[0-9a-f-]{36}/, { timeout: 30000 });
    const projectId = page.url().match(/\/project\/([0-9a-f-]{36})/)[1];
    writeState({ projectId });
    return projectId;
  } finally {
    await browser.close().catch(() => {});
  }
}

// Runs fn(page, context, projectId) inside the current project, creating one if needed.
async function inProject(fn) {
  if (!getProjectId()) await newProject();
  const projectId = getProjectId();
  const { browser, context } = await connect();
  try {
    const page = await flowPage(context);
    const url = `${FLOW_URL}project/${projectId}`;
    if (!page.url().startsWith(url)) await page.goto(url, { waitUntil: 'domcontentloaded' });
    await assertSignedIn(page);
    await page.locator('div.ProseMirror').waitFor({ state: 'visible', timeout: 30000 });
    await closePicker(page);
    return await fn(page, context, projectId);
  } finally {
    await browser.close().catch(() => {});
  }
}

// ---------- assets (uploaded files and generated images in the project) ----------

function tiles(page) {
  return page.evaluate(() => [...document.querySelectorAll('flow-grid-tile-container')].map((t) => ({
    name: t.querySelector('span.footer-title')?.innerText.trim() || '',
    mediaId: t.querySelector('img[data-media-id]')?.dataset.mediaId || '',
  })).filter((t) => t.mediaId));
}

export async function listAssets() {
  return inProject(async (page) => tiles(page));
}

const picker = (page) => page.locator('button.asset-item').first();

// Buttons and menu items are identified by their Material icon name, which is not translated.
const icon = (page, name) => page.locator('mat-icon', { hasText: new RegExp(`^\\s*${name}\\s*$`) });

// The upload button is the readiness signal: in an empty project the picker opens with no
// button.asset-item at all, so waiting for an asset would time out.
const uploadButton = (page) => page.locator('.sidebar-footer button').filter({ has: icon(page, 'upload') });

async function openPicker(page) {
  if (await uploadButton(page).isVisible().catch(() => false)) return;
  await page.locator('div.add-menu-container button').click();
  await uploadButton(page).waitFor({ state: 'visible', timeout: 10000 });
}

// Closes the asset picker and any stray menu: an open overlay leaves an invisible backdrop
// that swallows every click on the page.
async function closePicker(page) {
  const open = async () => (await picker(page).isVisible().catch(() => false))
    || (await page.locator('.cdk-overlay-backdrop-showing, .cdk-overlay-container [role=menu]').count()) > 0;
  for (let i = 0; i < 5 && (await open()); i++) {
    await page.keyboard.press('Escape');
    await page.waitForTimeout(500);
  }
  await closeAddPopover(page);
}

// ---------- new agent UI: the "+" popover (popover="manual": Escape does NOT close it) ----------

async function openAddPopover(page) {
  const popButtons = page.locator('.cdk-overlay-popover button:visible');
  if (await popButtons.count()) return;
  await page.locator('button.add-menu-trigger:visible').first().click({ timeout: 10000 });
  await popButtons.first().waitFor({ state: 'visible', timeout: 10000 });
}

async function closeAddPopover(page) {
  for (let i = 0; i < 3 && (await page.locator('.cdk-overlay-popover').count()); i++) {
    await page.locator('button.add-menu-trigger:visible').first().click({ timeout: 5000 }).catch(() => {});
    await page.waitForTimeout(700);
  }
}

async function popoverText(page) {
  return page.evaluate(() => document.querySelector('.cdk-overlay-popover')?.innerText || '');
}

async function renameTile(page, mediaId, name) {
  const tile = page.locator('flow-grid-tile-container').filter({ has: page.locator(`img[data-media-id="${mediaId}"]`) });
  await closePicker(page);
  await tile.click({ button: 'right' });
  await page.getByRole('menuitem').filter({ has: icon(page, 'edit') }).click(); // rename
  const input = page.locator('input.editable-text-input.editing');
  await input.waitFor({ state: 'visible', timeout: 5000 });
  await input.press(SELECT_ALL);
  // Typed key by key: a programmatic fill() changes the field but Flow never saves it.
  await input.pressSequentially(name, { delay: 30 });
  await input.press('Enter');
  await page.waitForTimeout(2500);
  const shown = (await tile.locator('span.footer-title').innerText()).trim();
  if (shown !== name) throw new Error(`Rename did not apply (tile shows "${shown}")`);
}

// Clicks whatever opens the local file chooser: the legacy sidebar button or the new
// agent UI's "Subir archivo..." inside the "+" popover.
async function clickUpload(page) {
  const legacy = uploadButton(page);
  if (await legacy.isVisible().catch(() => false)) return legacy.click();
  await openAddPopover(page);
  const popUpload = page.locator('.cdk-overlay-popover button:visible').filter({ has: page.locator('mat-icon', { hasText: /^upload$/ }) }).first();
  await popUpload.waitFor({ state: 'visible', timeout: 10000 });
  return popUpload.click();
}

// Uploads a local file into the current project and names it, so prompts can use @{name}.
// If an asset with that name already exists it is reused unless replace=true.
export async function uploadFile({ filePath, name, replace = false }) {
  filePath = path.resolve(filePath);
  if (!fs.existsSync(filePath)) throw new Error(`File not found: ${filePath}`);
  name = (name || path.parse(filePath).name).trim();
  return inProject(async (page) => {
    if (await isNewUi(page)) {
      // New agent UI: assets are named after their file (no inline rename), so upload a
      // copy carrying the requested name. The copy goes to /tmp: /app/uploads (chat
      // attachments) is mounted READ-ONLY in this container. The "+" popover lists
      // existing assets by name.
      const fileBase = name.replace(/[^\w.-]+/g, '-');
      const named = path.join(os.tmpdir(), `${fileBase}${path.extname(filePath)}`);
      fs.copyFileSync(filePath, named);
      await openAddPopover(page);
      if (!replace && (await popoverText(page)).toLowerCase().includes(fileBase.toLowerCase())) {
        await closeAddPopover(page);
        return { name, mediaId: '', reused: true };
      }
      const [chooser] = await Promise.all([
        page.waitForEvent('filechooser', { timeout: 15000 }),
        clickUpload(page),
      ]);
      await chooser.setFiles(named);
      // A one-time usage-rights consent can block the upload: accept it and keep polling.
      let uploaded = false;
      for (let i = 0; i < 40 && !uploaded; i++) {
        await page.waitForTimeout(2000);
        const accept = page.locator('button:visible').filter({ hasText: /^(Acepto|I accept|Entendido)$/i }).first();
        if (await accept.isVisible().catch(() => false)) {
          await accept.click().catch(() => {});
          continue;
        }
        uploaded = (await popoverText(page)).toLowerCase().includes(fileBase.toLowerCase());
      }
      await closeAddPopover(page);
      if (!uploaded) throw new Error(`Upload of ${path.basename(named)} did not finish within 80s`);
      return { name, mediaId: '', reused: false };
    }

    const existing = (await tiles(page)).find((t) => t.name === name);
    if (existing && !replace) return { name, mediaId: existing.mediaId, reused: true };

    const before = new Set((await tiles(page)).map((t) => t.mediaId));
    const [chooser] = await Promise.all([
      page.waitForEvent('filechooser', { timeout: 15000 }),
      clickUpload(page),
    ]);
    await chooser.setFiles(filePath);

    let mediaId;
    for (let i = 0; i < 60 && !mediaId; i++) {
      await page.waitForTimeout(1000);
      mediaId = (await tiles(page)).find((t) => !before.has(t.mediaId))?.mediaId;
    }
    if (!mediaId) throw new Error(`Upload of ${path.basename(filePath)} did not finish within 60s`);
    await closePicker(page);
    try {
      await renameTile(page, mediaId, name);
    } catch {
      // The new agent UI may not expose the inline rename; the upload itself succeeded.
    }
    return { name, mediaId, reused: false };
  });
}

// ---------- prompt editing ----------

// New agent UI: the visible editor; the old hidden prompt box may coexist in the DOM.
const promptEditor = (page) => page.locator('div.ProseMirror:visible').first();

// Empties the prompt box. New agent UI: its own "Borrar petición" (close) button.
// Old UI: referenced images stay attached as ingredients, so use Flow's "clear request"
// button when it is shown.
async function clearPrompt(page) {
  await closePicker(page);
  const editor = promptEditor(page);
  await editor.click().catch(() => {});
  const newClear = page.locator('button[aria-label="Borrar petición"]:visible');
  if (await newClear.count()) {
    await newClear.first().click().catch(() => {});
    await page.waitForTimeout(800);
  }
  const clear = page.locator('div.top-right-actions button.clear-button');
  if (await clear.isVisible().catch(() => false)) {
    await clear.click();
    await page.waitForTimeout(800);
  }
  // New agent UI: ingredient thumbnails live in their own bar; remove them explicitly.
  const ingredientBar = page.locator('flow-ingredient-bar:visible');
  if (await ingredientBar.count()) {
    await ingredientBar.locator('button').first().click().catch(() => {});
    await page.waitForTimeout(600);
  }
  await page.keyboard.press(SELECT_ALL);
  await page.keyboard.press('Backspace');
}

async function typeText(page, text) {
  const lines = text.split('\n');
  for (const [i, line] of lines.entries()) {
    if (i) await page.keyboard.press('Shift+Enter'); // Enter alone would submit
    if (line) await page.keyboard.insertText(line); // insertText never triggers the @ picker
  }
}

async function insertMention(page, name) {
  if (await isNewUi(page)) {
    // New agent UI: the "+" popover searches assets; clicking one attaches it as an
    // ingredient to the prompt (the popover closes itself afterwards). Search with the
    // sanitized file name used at upload time.
    const fileBase = name.replace(/[^\w.-]+/g, '-');
    await openAddPopover(page);
    const search = page.locator('.cdk-overlay-popover input:visible').first();
    await search.fill(fileBase);
    await page.waitForTimeout(1500);
    const pattern = new RegExp(fileBase.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'i');
    const item = page.locator('.cdk-overlay-popover button:visible').filter({ hasText: pattern }).first();
    await item.waitFor({ state: 'visible', timeout: 10000 }).catch(() => {
      throw new Error(`No asset named "${name}" in the Flow project. Upload it first (flow_upload_file).`);
    });
    await item.click({ timeout: 10000 });
    await page.waitForTimeout(1500);
    return;
  }
  const chips = page.locator('div.ProseMirror:visible span.mention-chip');
  const before = await chips.count();
  await page.keyboard.type('@'); // a typed "@" opens the asset picker with its search focused
  await picker(page).waitFor({ state: 'visible', timeout: 10000 });
  await page.keyboard.type(name, { delay: 20 });
  const option = page.locator('button.asset-item').filter({
    has: page.locator('.asset-title', { hasText: new RegExp(`^\\s*${name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s*$`) }),
  }).first();
  await option.waitFor({ state: 'visible', timeout: 10000 }).catch(() => {
    throw new Error(`No asset named "${name}" in the Flow project. Upload it first (flow_upload_file).`);
  });
  await option.click();
  await page.waitForFunction(([n]) => document.querySelectorAll('div.ProseMirror span.mention-chip').length > n, [before], { timeout: 5000 });
}

async function writePrompt(page, prompt) {
  await clearPrompt(page);
  let last = 0;
  for (const m of prompt.matchAll(MENTION)) {
    await typeText(page, prompt.slice(last, m.index));
    await insertMention(page, m[1].trim());
    last = m.index + m[0].length;
  }
  await typeText(page, prompt.slice(last));
}

// ---------- generation ----------

// New agent UI (Flow's "Configuración del agente" panel) sets session defaults: aspect,
// count, model and the pre-generation confirmation. Radios are identified by their
// visible text ("16:9", "x2"); the panel is saved with Guardar.
async function configureNew(page, { aspect, count, model }) {
  const tune = page.locator('button[aria-label="Ajustes"]:visible').filter({ has: page.locator('mat-icon', { hasText: /^tune/ }) });
  await tune.first().click({ timeout: 10000 });
  await page.waitForTimeout(1500);

  // Never require the confirmation step: automated submissions can't answer it.
  await page.locator('[role=radio]:visible', { hasText: /^Nunca\b|^Never\b/i }).first().click({ timeout: 5000 }).catch(() => {});
  await page.locator('[role=radio]:visible', { hasText: aspect }).first().click({ timeout: 8000 });
  await page.locator('[role=radio]:visible', { hasText: new RegExp(`^x${count}$`) }).first().click({ timeout: 8000 });

  const modelBtn = page.locator('button:visible').filter({ hasText: 'Nano Banana' }).first();
  if (await modelBtn.count()) {
    const current = modelName(await modelBtn.innerText().catch(() => ''));
    if (current !== model) {
      await modelBtn.click({ timeout: 8000 });
      await page.locator('.cdk-overlay-container [role=menuitem]:visible, .cdk-overlay-container [role=option]:visible, .cdk-overlay-container button:visible', { hasText: model }).first().click({ timeout: 10000 }).catch(() => {});
      await page.waitForTimeout(1000);
    }
  }

  await page.getByRole('button', { name: /^(Guardar|Save)$/i }).first().click({ timeout: 8000 }).catch(() => {});
  await page.waitForTimeout(1500);
}

// The new agent UI announces itself with its own submit control.
const isNewUi = (page) => page.locator('button[aria-label="Iniciar generación"]:visible').count();

async function configure(page, opts) {
  if (await isNewUi(page)) return configureNew(page, opts);
  return configureLegacy(page, opts);
}

async function configureLegacy(page, { aspect, count, model }) {
  // Plain generation, not Flow's chat agent.
  const agent = page.locator('flow-agent-mode-toggle-chip button');
  if (await agent.count() && (await agent.getAttribute('aria-pressed')) === 'true') await agent.click();

  // The trigger sometimes ignores the first click after the panel was closed: retry.
  const panel = page.locator('flow-prompt-box-settings');
  for (let i = 0; i < 4 && !(await panel.isVisible()); i++) {
    await page.locator('button.settings-trigger-button').click();
    await panel.waitFor({ state: 'visible', timeout: 2500 }).catch(() => {});
  }
  if (!(await panel.isVisible())) throw new Error('Could not open Flow\'s settings panel');

  await panel.getByRole('radiogroup').first().getByRole('radio').first().click(); // image (not video)
  await panel.getByRole('radio', { name: aspect, exact: true }).click();
  await panel.getByRole('radio', { name: `x${count}`, exact: true }).click();

  const modelBtn = panel.getByRole('button').filter({ hasText: 'Nano Banana' });
  if (modelName(await modelBtn.innerText()) !== model) {
    await modelBtn.click();
    await page.getByRole('menuitem').filter({ hasText: new RegExp(`${model}\\s*$`) }).click();
  }
  for (let i = 0; i < 4 && (await panel.isVisible()); i++) {
    await page.keyboard.press('Escape');
    await panel.waitFor({ state: 'hidden', timeout: 1500 }).catch(() => {});
  }
  if (await panel.isVisible()) throw new Error('Could not close Flow\'s settings panel');

  const summary = await page.locator('button.settings-trigger-button').innerText();
  if (modelName(summary) !== model || !summary.includes(`x${count}`)) {
    throw new Error(`Flow settings did not apply (shows "${summary}")`);
  }
}

// "🍌 Nano Banana 2 Lite\ncrop_square\nx1" -> "Nano Banana 2 Lite"
function modelName(text) {
  return (text.match(/Nano Banana[^\n]*/) || [''])[0].trim();
}

// Error tiles from earlier attempts stay in the project grid, so a failure only counts if
// the number of error tiles grows after this submit.
function failedTiles(page) {
  return page.evaluate(() => [...document.querySelectorAll('flow-image-tile, flow-tile-container')]
    .map((e) => e.innerText).filter((s) => /error|fail|unusual|no se ha podido|falló|política|policy|inusual/i.test(s)));
}

function mediaIds(page) {
  return page.evaluate(() =>
    [...document.querySelectorAll('flow-image-tile img[data-media-id], img[data-media-id]')].map((i) => i.dataset.mediaId));
}

// New agent UI: policy rejections render as "Error" cards in the session; count them so a
// failure only registers when a NEW one appears (old errors stay in the transcript).
const policyErrorHits = (page) => page.evaluate(() =>
  (document.body.innerText.match(/infringir nuestras políticas|might violate our policies/gi) || []).length);

function slug(text) {
  return text.replace(MENTION, '$1').toLowerCase().normalize('NFKD').replace(/[^\w\s-]/g, '').trim().replace(/\s+/g, '-').slice(0, 40) || 'image';
}

export async function generateImages({ prompt, aspect = '1:1', count = 1, model = 'Nano Banana 2.1', outDir = DEFAULT_OUT, timeoutMs = 240000 }) {
  if (!prompt?.trim()) throw new Error('prompt is required');
  if (!ASPECTS.includes(aspect)) throw new Error(`aspect must be one of ${ASPECTS.join(', ')}`);
  if (![1, 2, 3, 4].includes(count)) throw new Error('count must be 1-4');
  model = MODELS[String(model).toLowerCase()] || model;
  if (!Object.values(MODELS).includes(model)) throw new Error(`model must be one of ${Object.values(MODELS).join(', ')}`);

  return inProject(async (page, context, projectId) => {
    await configure(page, { aspect, count, model });
    const before = new Set(await mediaIds(page));
    const failedBefore = (await failedTiles(page)).length;
    const policyBefore = await policyErrorHits(page);
    await writePrompt(page, prompt);
    const newSubmit = page.locator('button[aria-label="Iniciar generación"]:visible');
    let submit;
    if (await newSubmit.count()) {
      submit = newSubmit.first();
    } else {
      submit = page.locator('flow-generate-icon-button button[type=submit]');
      await page.waitForFunction((el) => !el.disabled, await submit.elementHandle(), { timeout: 10000 });
    }
    await submit.click();

    const started = Date.now();
    let fresh = [];
    while (Date.now() - started < timeoutMs) {
      await page.waitForTimeout(2000);
      fresh = (await mediaIds(page)).filter((id) => !before.has(id));
      if (fresh.length >= count) break;
      if ((await policyErrorHits(page)) > policyBefore) throw new Error('Flow rejected the prompt (policy classifier). Retry, or rephrase the prompt.');
      const failed = await failedTiles(page);
      if (failed.length > failedBefore) throw new Error(`Flow reported a failed generation: ${failed[0].replace(/\s+/g, ' ').slice(0, 200)}`);
    }
    if (!fresh.length) throw new Error(`No image appeared within ${Math.round(timeoutMs / 1000)}s`);

    fs.mkdirSync(outDir, { recursive: true });
    const stamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
    const files = [];
    for (const [i, id] of fresh.slice(0, count).entries()) {
      const src = await page.locator(`img[data-media-id="${id}"]`).getAttribute('src');
      const res = await context.request.get(src);
      if (!res.ok()) throw new Error(`Download failed (${res.status()}) for media ${id}`);
      const ext = (res.headers()['content-type'] || '').includes('png') ? 'png' : 'jpg';
      const file = path.join(outDir, `${stamp}-${slug(prompt)}-${i + 1}.${ext}`);
      fs.writeFileSync(file, await res.body());
      files.push(file);
    }
    return { files, projectId, model, aspect, seconds: Math.round((Date.now() - started) / 1000) };
  });
}

// Captures real ObsyGPT screenshots for the docs site (docs/docs/assets/screenshots).
// Env: DOCS_BASE_URL (default http://localhost:3001), DOCS_USER, DOCS_EMAIL,
// DOCS_PASSWORD (required). Never run against production.
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const outDir = join(root, "docs", "docs", "assets", "screenshots");
const BASE = process.env.DOCS_BASE_URL ?? "http://localhost:3001";
const USER = process.env.DOCS_USER ?? "docs";
const EMAIL = process.env.DOCS_EMAIL ?? "docs@obsygpt.local";
const PASSWORD = process.env.DOCS_PASSWORD;
if (!PASSWORD) {
  console.error("DOCS_PASSWORD is required");
  process.exit(1);
}
mkdirSync(outDir, { recursive: true });

const views = [
  ["chat", "/", ".composer"],
  ["tasks", "/tasks", null],
  ["projects", "/projects", null],
  ["trace", "/trace", null],
  ["memory", "/memory", null],
  ["skills", "/skills", null],
  ["tools", "/tools", null],
  ["connectors", "/connectors", null],
  ["history", "/history", null]
];

async function main() {
  // Ensure the docs account exists (first account on a fresh DB becomes admin).
  try {
    const res = await fetch(`${BASE}/api/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: USER, email: EMAIL, password: PASSWORD, confirm_password: PASSWORD })
    });
    console.log("register:", res.status);
  } catch (err) {
    console.log("register skipped:", err.message);
  }

  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

  async function shoot(name) {
    await page.waitForTimeout(900);
    await page.screenshot({ path: join(outDir, `${name}.png`), fullPage: false });
    console.log("captured", name);
  }

  // 1) Auth screen
  await page.goto(BASE, { waitUntil: "domcontentloaded" });
  await page.waitForSelector(".auth-form", { timeout: 30000 });
  await shoot("login");

  // 2) Log in
  await page.fill('input[aria-label="Usuario"]', USER);
  await page.fill('input[aria-label="Contraseña"]', PASSWORD);
  await page.click(".auth-form > button");
  await page.waitForSelector(".left-rail", { timeout: 30000 });

  // 3) Main views
  for (const [name, path, selector] of views) {
    await page.goto(`${BASE}${path}`, { waitUntil: "domcontentloaded" });
    try {
      await page.waitForSelector(selector ?? ".left-rail", { timeout: 15000 });
    } catch { /* keep going */ }
    await shoot(name);
  }

  // 4) Settings tabs (state-driven: navigate to /settings then click chips)
  await page.goto(`${BASE}/settings`, { waitUntil: "domcontentloaded" });
  await page.waitForSelector(".settings-chips", { timeout: 15000 });
  await page.waitForTimeout(1200);
  await shoot("settings-preferencias");

  const chips = [
    ["Modelo", "settings-modelo"],
    ["Preferencias", "settings-preferencias"],
    ["Seguridad", "settings-seguridad"],
    ["Sistema", "settings-sistema"],
    ["Agentes", "settings-agentes"],
    ["Triggers", "settings-triggers"],
    ["Datos", "settings-datos"]
  ];
  for (const [label, name] of chips) {
    const chip = page.locator(".settings-chips .chip", { hasText: label }).first();
    try {
      await chip.click({ timeout: 5000 });
    } catch {
      continue;
    }
    await page.waitForTimeout(1000);
    await shoot(name);
  }

  // 5) Admin: monitoring
  try {
    await page.goto(`${BASE}/monitoring`, { waitUntil: "domcontentloaded" });
    await page.waitForSelector(".left-rail", { timeout: 15000 });
    await shoot("monitoring");
  } catch {
    console.log("monitoring skipped (admin only)");
  }

  // 6) Diagnostics
  try {
    await page.goto(`${BASE}/diagnostics`, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(1200);
    await shoot("diagnostics");
  } catch {
    console.log("diagnostics skipped");
  }

  await browser.close();
  console.log("done ->", outDir);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});

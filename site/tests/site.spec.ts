import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { parse } from "yaml";

const PAGES = ["/", "/fonctionnalites/", "/comparatif/", "/nouveautes/", "/installer/", "/demo/", "/contact/", "/contact/merci/", "/mentions-legales/", "/donnees-personnelles/"];
const changelog = parse(readFileSync(new URL("../../data/changelog.yml", import.meta.url), "utf8"), { version: "1.1" }) as {
  next?: { text: string; tech?: string }[];
  versions: { version: string; entries: { text: string; tech?: string }[] }[];
};
const current = changelog.versions[0]!;

test("« Essayer la démo » en haut à droite, vers la page de la démo", async ({ page }) => {
  await page.goto("/");
  const demo = page.getByTestId("demo");
  await expect(demo).toBeVisible();
  await expect(demo).toHaveAttribute("href", "/demo/");
  const box = (await demo.boundingBox())!;
  expect(box.x + box.width).toBeGreaterThan(page.viewportSize()!.width * 0.6);
  await page.goto("/demo/");
  await expect(page.getByRole("link", { name: "Ouvrir la démo" })).toHaveAttribute("href", /^https:\/\/demo\./);
});

test("version et nouveautés lues dans data/changelog.yml, sans la partie next ni les notes techniques", async ({ page }) => {
  await page.goto("/nouveautes/");
  await expect(page.getByTestId("version")).toHaveText(`Version ${current.version}`);
  await expect(page.getByRole("heading", { level: 2 }).first()).toContainText(current.version);
  const main = page.locator("main");
  const techs = changelog.versions.flatMap((v) => v.entries.map((e) => e.tech?.trim().slice(0, 40)).filter(Boolean));
  const text = await main.innerText();
  for (const tech of techs.slice(0, 20)) expect(text).not.toContain(tech!);
  for (const pending of (changelog.next ?? []).slice(0, 10)) expect(text).not.toContain(pending.text.trim().slice(0, 60));
  const json = await (await page.request.get("/version.json")).json();
  expect(json.version).toBe(current.version);
});

test("une page par version et un flux RSS", async ({ page }) => {
  await page.goto(`/nouveautes/${current.version}/`);
  await expect(page.getByRole("heading", { level: 1 })).toContainText(current.version);
  const rss = await (await page.request.get("/nouveautes/rss.xml")).text();
  expect(rss).toContain(`<title>${current.version} · `);
});

test("formulaire de contact : champs, piège invisible, consentement, envoi vers /api/contact", async ({ page }) => {
  await page.goto("/contact/");
  await expect(page.getByRole("textbox", { name: "Nom" })).toBeVisible();
  await expect(page.getByRole("textbox", { name: "E-mail" })).toBeVisible();
  await expect(page.getByRole("checkbox")).toBeVisible();
  await expect(page.locator('input[name="website"]')).not.toBeInViewport();
  await expect(page.locator("form#formulaire")).toHaveAttribute("action", "/api/contact");
  expect(Number(await page.locator("#started_at").inputValue())).toBeGreaterThan(0);
  await page.goto("/contact/?erreur=trop");
  await expect(page.getByRole("alert")).toContainText("Trop de messages");
});

test("fonctionnalités : un module par section avec ses écrans, liens vers la version d'arrivée", async ({ page }) => {
  await page.goto("/fonctionnalites/");
  await expect(page.getByRole("heading", { level: 2, name: /Comptabilité/ })).toBeVisible();
  await expect(page.locator("#agri .shot img").first()).toHaveAttribute("alt", /Résultat fiscal/);
  const since = page.locator(".feature-since").first();
  await since.click();
  await expect(page).toHaveURL(/\/nouveautes\/\d{4}\.\d{2}\.\d+\/$/);
});

test("fonctionnalités : le filtre par structure masque ce qui ne la concerne pas et se garde dans l'adresse", async ({ page }) => {
  await page.goto("/fonctionnalites/");
  await expect(page.locator("#baux")).toBeVisible();
  await page.getByRole("button", { name: "une exploitation agricole" }).click();
  await expect(page.getByRole("button", { name: "une exploitation agricole" })).toHaveAttribute("aria-pressed", "true");
  await expect(page).toHaveURL(/\?pour=agri/);
  await expect(page.locator("#baux")).toBeHidden();
  await expect(page.locator("#agri")).toBeVisible();
  await expect(page.locator("#adhesions")).toBeHidden();
  await expect(page.locator("#rapprochement")).toBeVisible();
  await page.goto("/fonctionnalites/?pour=sci");
  await expect(page.locator("#agri")).toBeHidden();
  await expect(page.locator("#baux")).toBeVisible();
});

test("comparatif : chaque case renvoie à sa source", async ({ page }) => {
  await page.goto("/comparatif/");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Lyvre et les autres logiciels");
  const cell = page.locator("td.mark a").first();
  await expect(cell).toHaveAttribute("href", /^https:\/\//);
  await expect(cell).toHaveAttribute("title", /.+/);
});

test("aucun défilement horizontal", async ({ page }) => {
  for (const path of PAGES) {
    await page.goto(path);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow, path).toBeLessThanOrEqual(0);
  }
});

for (const path of PAGES) {
  test(`accessibilité ${path}`, async ({ page }) => {
    await page.goto(path);
    const { violations } = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
    expect(violations.map((v) => `${v.id} : ${v.nodes.map((n) => n.target.join(" ")).slice(0, 3).join(", ")}`)).toEqual([]);
  });
}

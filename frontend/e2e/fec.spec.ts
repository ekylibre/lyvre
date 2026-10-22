// FEC (phase A.3) : SIREN renseigné, clôture provisoire d'un exercice ancien, contrôles et
// téléchargement du fichier des écritures comptables.
import { expect, test } from "@playwright/test";
import { login } from "./helpers";

test("FEC : SIREN, clôture provisoire, contrôles et téléchargement", async ({ page }) => {
  const old = String(new Date().getFullYear() - 6);
  await login(page, "SCI E2E", "/configuration/organization");
  await page.getByLabel("SIREN").fill("732 829 320");
  await page.getByRole("button", { name: "Enregistrer" }).click();
  await expect(page.getByText("Identité de la structure enregistrée.")).toBeVisible();

  await page.goto("/fiscal-years/");
  const row = page.getByRole("row", { name: new RegExp(`^${old}`) });
  await expect(row.getByText("après clôture")).toBeVisible();
  await row.getByRole("button", { name: "Clôturer" }).click();
  await page.getByRole("dialog", { name: `Clôturer l'exercice ${old} ?` }).getByRole("button", { name: "Clôturer l'exercice" }).click();
  await expect(row.getByText("Clôture provisoire")).toBeVisible();

  await row.getByRole("button", { name: "FEC" }).click();
  const dialog = page.getByRole("dialog", { name: `Fichier des écritures comptables — ${old}` });
  await expect(dialog.getByText(/Format relu : 18 champs/)).toBeVisible();
  const link = dialog.getByRole("link", { name: `Télécharger 732829320FEC${old}1231.txt` });
  const href = await link.getAttribute("href");
  expect(href).toMatch(/^\/fiscal-years\/\d+\/fec$/);
  const resp = await page.request.get(href!);
  expect(resp.headers()["content-disposition"]).toContain(`732829320FEC${old}1231.txt`);
  const lines = (await resp.text()).split("\r\n").filter(Boolean);
  expect(lines[0].split("\t")).toHaveLength(18);
  expect(lines.slice(1).map((line) => line.split("\t")[2])).toEqual(["BQ000001", "BQ000001"]);
  expect(lines[1].split("\t")[11]).toBe("250,00");
});

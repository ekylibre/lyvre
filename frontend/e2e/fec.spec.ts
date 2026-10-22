// FEC (phases A.3, A.4) : SIREN renseigné, assistant de clôture d'un exercice ancien (étapes,
// clôture provisoire, réouverture, nouvelle clôture), contrôles et téléchargement du FEC.
import { expect, test } from "@playwright/test";
import { login } from "./helpers";

test("FEC : SIREN, assistant de clôture, réouverture, contrôles et téléchargement", async ({ page }) => {
  const old = String(new Date().getFullYear() - 6);
  await login(page, "SCI E2E", "/configuration/organization");
  await page.getByLabel("SIREN").fill("732 829 320");
  await page.getByRole("button", { name: "Enregistrer" }).click();
  await expect(page.getByText("Identité de la structure enregistrée.")).toBeVisible();

  await page.goto("/fiscal-years/");
  const row = page.getByRole("row", { name: new RegExp(`^${old}`) });
  await expect(row.getByText("après clôture")).toBeVisible();
  await row.getByRole("link", { name: "Clôturer…" }).click();

  // Assistant : chaque étape faite ou ignorée avec un motif, puis clôture provisoire.
  await expect(page.getByText("Aucune anomalie détectée.")).toBeVisible();
  await page.getByRole("button", { name: "Marquer comme fait" }).click();
  for (const [title, reason] of [["Écritures d'inventaire", "Aucune charge à rattacher"], ["Fonds dédiés", "Sans objet"]]) {
    await expect(page.getByRole("heading", { name: title })).toBeVisible();
    await page.getByRole("button", { name: "Ignorer…" }).click();
    await page.getByLabel("Motif").fill(reason);
    await page.getByRole("button", { name: "Ignorer l'étape" }).click();
  }
  await expect(page.getByText("Excédent")).toBeVisible();
  await page.getByRole("button", { name: "Marquer comme fait" }).click();
  await expect(page.getByText(/Essai à blanc avec une numérotation provisoire/)).toBeVisible();
  await page.getByRole("button", { name: "Marquer comme fait" }).click();
  await page.getByRole("button", { name: "Clôture provisoire" }).click();
  await page.getByRole("dialog", { name: `Clôture provisoire de l'exercice ${old} ?` }).getByRole("button", { name: "Clôturer" }).click();
  await expect(page.getByText(/Écritures verrouillées et numérotées/)).toBeVisible();

  // Réouverture (motif obligatoire) puis nouvelle clôture : même numérotation.
  await page.getByRole("button", { name: "Rouvrir…" }).click();
  const reopen = page.getByRole("dialog", { name: `Rouvrir l'exercice ${old}` });
  await reopen.getByLabel("Motif").fill("Facture oubliée");
  await reopen.getByRole("button", { name: "Rouvrir l'exercice" }).click();
  await expect(page.getByText("Réouverture")).toBeVisible();
  await page.getByRole("button", { name: "Clôture provisoire" }).click();
  await page.getByRole("dialog", { name: `Clôture provisoire de l'exercice ${old} ?` }).getByRole("button", { name: "Clôturer" }).click();
  await expect(page.getByText(/Écritures verrouillées et numérotées/)).toBeVisible();

  await page.getByRole("link", { name: "Retour aux exercices" }).click();
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

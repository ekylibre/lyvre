// Lot F6 : reprise d'historique (tableur en brouillard, puis FEC d'un exercice ancien).
import { expect, test } from "@playwright/test";
import { login } from "./helpers";

const year = new Date().getFullYear();

test("tableur : écritures importées en brouillard", async ({ page }) => {
  await login(page, "SCI E2E", "/imports/reprise");
  await page.getByText("Tableur (CSV, XLSX)").click();
  const csv = `Date;Pièce;Compte;Libellé;Débit;Crédit\n02/02/${year};T-1;606300;Ampoules;12,40;\n02/02/${year};T-1;512000;Ampoules;;12,40\n`;
  await page.locator("input[type=file]").setInputFiles({ name: "ecritures.csv", mimeType: "text/csv", buffer: Buffer.from(csv) });
  await expect(page.getByText("2 ligne(s), 1 écriture(s)")).toBeVisible();
  await page.getByRole("button", { name: "Importer en brouillard" }).click();
  await expect(page.getByText("1 écriture(s) importée(s) en brouillard.")).toBeVisible();
});

test("FEC : historique d'un exercice ancien", async ({ page }) => {
  const old = year - 10;
  const fields = "JournalCode\tJournalLib\tEcritureNum\tEcritureDate\tCompteNum\tCompteLib\tCompAuxNum\tCompAuxLib\tPieceRef\tPieceDate\tEcritureLib\tDebit\tCredit\tEcritureLet\tDateLet\tValidDate\tMontantdevise\tIdevise";
  const row = (num: string, account: string, debit: string, credit: string) =>
    `BQ\tBanque\t${num}\t${old}0310\t${account}\tCompte\t\t\tR${num}\t${old}0310\tLoyer\t${debit}\t${credit}\t\t\t${old}1231\t\t`;
  const fec = [fields, row("1", "512000", "800,00", "0,00"), row("1", "706000", "0,00", "800,00")].join("\r\n") + "\r\n";
  await login(page, "SCI E2E", "/imports/reprise");
  await page.locator("input[type=file]").setInputFiles({ name: `732829320FEC${old}1231.txt`, mimeType: "text/plain", buffer: Buffer.from(fec, "latin1") });
  await expect(page.getByText("1 (2 lignes)")).toBeVisible();
  await page.getByLabel("Début de l'exercice").fill(`${old}-01-01`);
  await page.getByRole("button", { name: /^Importer/ }).click();
  await expect(page.getByText(new RegExp(`1 écriture\\(s\\) importée\\(s\\) dans l'exercice ${old}`))).toBeVisible();
});

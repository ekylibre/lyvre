// Captures d'écran du README (doc/images/) sur la base jetable des tests de bout en bout : données
// fictives créées par l'API dans « SCI Ventes E2E », aucun service externe appelé.
// Serveur neuf requis (les données s'ajoutent à chaque passage) :
//   .venv/bin/python scripts/e2e_server.py &
//   cd frontend && node --input-type=module - ../doc/images < ../scripts/readme_screenshots.mjs
// (lu sur l'entrée standard depuis frontend/ pour y résoudre @playwright/test)
import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";

const BASE = "http://127.0.0.1:5099";
const OUT = process.argv[2];
mkdirSync(OUT, { recursive: true });
const today = new Date();
const iso = (d) => d.toISOString().slice(0, 10);

const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1, locale: "fr-FR" });
const page = await context.newPage();

async function login(instance) {
  await page.goto(`${BASE}/login`);
  await page.getByLabel("Email").fill("e2e@example.org");
  await page.getByLabel("Mot de passe").fill("e2e-mot-de-passe");
  await page.getByRole("button", { name: "Se connecter" }).click();
  await page.waitForURL(/select-instance/);
  await page.getByLabel(instance).check();
  await page.getByRole("button", { name: "Continuer" }).click();
  await page.waitForURL((u) => !u.pathname.includes("select-instance"));
}

let csrf = "";
async function call(method, path, body) {
  if (!csrf) csrf = (await (await page.request.get(`${BASE}/api/v1/session`)).json()).csrf_token;
  const resp = await page.request.fetch(`${BASE}/api/v1${path}`, { method, data: body, headers: { "X-CSRFToken": csrf } });
  const json = await resp.json().catch(() => ({}));
  if (!resp.ok()) throw new Error(`${method} ${path} → ${resp.status()} ${JSON.stringify(json)}`);
  return json;
}

async function shot(path, name, { wait, dark = false, full = false } = {}) {
  await page.emulateMedia({ colorScheme: dark ? "dark" : "light" });
  await page.goto(`${BASE}${path}`);
  await page.waitForLoadState("networkidle");
  if (wait) await page.getByText(wait).first().waitFor();
  await page.waitForTimeout(600); // animations des graphiques
  await page.screenshot({ path: `${OUT}/${name}.png`, fullPage: full });
  console.log("capture", name);
}

// ---------------------------------------------------------------- données (SCI Ventes E2E)
await login("SCI Ventes E2E");
await call("PUT", "/billing-settings", { legal_form: "SCI", share_capital: "274890", iban: "FR76 3000 6000 0112 3456 7890 189",
  rcs: "RCS Paris 123 456 782" });
const client = (await call("GET", "/sales/form-options")).clients.find((c) => c.label === "Client Ventes E2E").value;
const invoices = [
  [["Gestion locative — octobre", "1", "450"], ["Frais de dossier", "1", "120"]],
  [["Audit énergétique", "2", "380"]],
  [["Mise à disposition de la salle", "3", "150"], ["Ménage", "3", "40"]],
  [["Conseil en gestion", "1", "1200"]],
];
const ids = [];
for (const rows of invoices) {
  const item = (await call("POST", "/sales", { entity_id: client, issue_date: iso(today),
    lines: rows.map(([label, quantity, unit_price]) => ({ label, quantity, unit_price, vat_rate: "0", account_code: "706" })) })).item;
  await call("POST", `/sales/${item.id}/issue`);
  ids.push(item.id);
}
// Encaissement de la dernière par le crédit bancaire de 1 200 €, une autre par chèque.
const options = await call("GET", `/sales/${ids[3]}/payment-options`);
await call("POST", "/sales/match", { bank_transaction_id: options.candidates[0].id, allocations: [{ sale_id: ids[3], amount_cents: 120000 }] });
await call("POST", `/sales/${ids[1]}/payments`, { amount: "300", paid_on: iso(today), bank_account_id: options.accounts[0].value, method: "check" });
const quote = (await call("POST", "/sales", { kind: "quote", entity_id: client, issue_date: iso(today),
  lines: [{ label: "Rénovation de la cage d'escalier", quantity: "1", unit_price: "6800", vat_rate: "0" }] })).item;
await call("POST", `/sales/${quote.id}/issue`);
await call("POST", `/sales/${quote.id}/quote-status`, { status: "accepted" });
// Draft pour montrer un brouillon dans la liste.
await call("POST", "/sales", { entity_id: client, issue_date: iso(today), lines: [{ label: "Location du parking", unit_price: "90", vat_rate: "0" }] });
// Bail au 1er du mois, avis préparé et émis, abonnements.
const first = new Date(today.getFullYear(), today.getMonth(), 1, 12);
const lease = (await call("POST", "/leases", { entity_id: client, unit_label: "Appartement 2B", address_line1: "10 rue des Lilas",
  postal_code: "75011", city: "Paris", start_date: iso(first), rent: "850", charges: "60", deposit: "1700", due_day: 1 })).item;
const due = (await call("GET", "/sales/due")).items;
await call("POST", "/sales/issue-batch", { ids: due.map((s) => s.id) });
const leaseInvoice = (await call("GET", `/leases/${lease.id}`)).item.invoices[0];
await call("POST", `/sales/${leaseInvoice.id}/payments`, { amount: "910", bank_account_id: options.accounts[0].value, method: "transfer" });
await call("POST", `/sales/${leaseInvoice.id}/rent-receipt`);
await call("POST", `/leases/${lease.id}/deposit`, { paid_on: iso(today), bank_account_id: options.accounts[0].value });
const supplier = (await call("GET", "/subscriptions")).meta.suppliers.find((s) => s.label === "Orange E2E").value;
const start = new Date(today.getFullYear(), today.getMonth() - 4, 1, 12);
for (const [label, category, amount, frequency, renewal] of [
  ["Box internet et téléphonie", "internet", "45", "monthly", null],
  ["Assurance propriétaire non occupant", "insurance", "620", "yearly", 40],
  ["Logiciel de gestion", "software", "29", "monthly", null],
]) {
  await call("POST", "/subscriptions", { label, entity_id: supplier, category, amount, frequency, due_day: 5, start_date: iso(start),
    ...(renewal ? { renewal_date: iso(new Date(today.getTime() + renewal * 86400000)), notice_days: 30 } : {}) });
}

// ---------------------------------------------------------------- captures
await call("POST", "/integrations/qonto/dismiss");
await shot("/", "tableau-de-bord", { wait: "Encours clients" });
await shot("/", "tableau-de-bord-sombre", { wait: "Encours clients", dark: true });
await shot("/sales/", "ventes", { wait: "Restant dû" });
await shot(`/sales/${ids[3]}`, "facture", { wait: "Encaissements" });
await shot(`/leases/${lease.id}`, "bail", { wait: "Quittances et reçus" });
await shot("/subscriptions/", "abonnements", { wait: "Coût mensuel" });
await shot("/configuration/integrations/", "integrations", { wait: "Qonto" });

await browser.close();

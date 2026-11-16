// Fonctions réservées aux associations (lot G1) : Structure, formulaire et fiche du tiers, tableau de
// bord, rendus pour une association puis pour une SCI.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { Route, Routes } from "react-router";
import { renderWithProviders, TEST_SESSION } from "../../test/render";
import type { Session } from "../../api/session";
import DashboardPage from "../dashboard/DashboardPage";
import { EntityForm } from "../entities/EntityForm";
import EntityDetailPage from "../entities/EntityDetailPage";
import type { Entity } from "../entities/types";
import OrganizationPage from "./OrganizationPage";

const json = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
const session = (chart: "asso" | "sci" | "societe"): Session => ({ ...TEST_SESSION, role: "admin",
  permissions: { write: true, instance_admin: true }, instance: { ...TEST_SESSION.instance!, chart } });

const ENTITY: Entity = {
  id: 3, name: "Martin", entity_type: "AUTRE", email: null, account_code: null, is_member: true, is_benevole: true,
  notes: null, default_product_id: null, default_product: null, vat_number: null, siret: null, iban: null,
  siren: null, naf_code: null, naf_nomenclature: null,
  address_line1: null, address_line2: null, postal_code: null, city: null, country: null, person_kind: null,
  last_helloasso_membership: null, last_pos_membership: null, transactions: 0,
};
const META = { types: [{ value: "AUTRE", label: "Autre" }], products: [],
  integrations: Object.fromEntries(["helloasso", "odoo", "smtp"].map((k) => [k, { enabled: true, available: true }])) };
const ORGANIZATION = {
  name: "Structure", siren: null, rna: null, address_line1: null, address_line2: null, postal_code: null, city: null,
  country: null, purpose: null, signatory_name: null, signatory_title: null, legal_form: null, rcs_city: null,
  vat_number: null, share_capital: "", naf_code: null, naf_nomenclature: null, rcs_mention: "",
  fec_ready: false, has_associates: false, associate_interest_rate: "0", jei_since: null, vat_due_day: "",
};

let sci = false;
beforeEach(() => {
  vi.spyOn(globalThis, "fetch").mockImplementation(((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/v1/organization") return json({ item: ORGANIZATION });
    if (url === "/api/v1/tiers/3") return json({
      item: ENTITY, meta: META, supplier: { account_code: null, balance_cents: null }, purchases: [], pos_orders: [],
      customer_invoices: [], lettering: [],
      work_times: sci ? null : [], helloasso: sci ? null : { orders: [], items: [], payments: [] } });
    if (url.startsWith("/api/v1/dashboard")) return json({
      stats: { total_sales_cents: 0, new_members: sci ? null : 4, resultat_courant_cents: 0, total_payouts_cents: 0 },
      monthly: [],
      meta: { fiscal_years: [{ value: "1", label: "2026" }], fiscal_year: { id: 1, label: "2026" }, previous: null } });
    return json({ items: [] });
  }) as typeof fetch);
});
afterEach(() => { vi.restoreAllMocks(); sci = false; });

describe("association", () => {
  it("Structure : RNA et signataire des reçus, sans bloc Associés", async () => {
    renderWithProviders(<OrganizationPage />, { session: session("asso") });
    expect(await screen.findByText("Signataire des reçus fiscaux")).toBeInTheDocument();
    expect(screen.getByLabelText("Numéro RNA")).toBeInTheDocument();
    expect(screen.queryByText("Associés (sociétés)")).not.toBeInTheDocument();
  });

  it("tiers : cases d'adhésion et mention des reçus", () => {
    renderWithProviders(<EntityForm entity={null} meta={undefined} onDone={() => undefined} />, { session: session("asso") });
    expect(screen.getByLabelText("Adhérent de l'association")).toBeInTheDocument();
    expect(screen.getByText("Exigées pour émettre un reçu fiscal à ce donateur.")).toBeInTheDocument();
  });

  it("fiche du tiers : badges et tuiles d'adhésion", async () => {
    renderWithProviders(<Routes><Route path="/entities/:entity_id" element={<EntityDetailPage />} /></Routes>,
      { session: session("asso"), route: "/entities/3" });
    expect(await screen.findByText("Adhésion HelloAsso")).toBeInTheDocument();
    expect(screen.getByText("Bénévole")).toBeInTheDocument();
  });

  it("tableau de bord : tuile Adhésions", async () => {
    renderWithProviders(<DashboardPage />, { session: session("asso") });
    expect(await screen.findByText("Adhésions")).toBeInTheDocument();
  });
});

describe("SCI", () => {
  beforeEach(() => { sci = true; });

  it("Structure : bloc Associés, sans RNA ni signataire", async () => {
    renderWithProviders(<OrganizationPage />, { session: session("sci") });
    expect(await screen.findByText("Associés (sociétés)")).toBeInTheDocument();
    expect(screen.queryByLabelText("Jeune entreprise innovante depuis")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Numéro RNA")).not.toBeInTheDocument();
    expect(screen.queryByText("Signataire des reçus fiscaux")).not.toBeInTheDocument();
    expect(screen.queryByText(/reçus fiscaux/)).not.toBeInTheDocument();
  });

  it("tiers : nature et adresse, sans adhésion ni mention des reçus", () => {
    renderWithProviders(<EntityForm entity={null} meta={undefined} onDone={() => undefined} />, { session: session("sci") });
    expect(screen.queryByLabelText("Adhérent de l'association")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Bénévole")).not.toBeInTheDocument();
    expect(screen.queryByText(/reçu fiscal/)).not.toBeInTheDocument();
    expect(screen.queryByText(/HelloAsso/)).not.toBeInTheDocument();
    expect(screen.getByText("Particulier")).toBeInTheDocument();
    expect(screen.getByLabelText("Adresse")).toBeInTheDocument();
  });

  it("fiche du tiers : ni badges ni tuiles d'adhésion, même pour un ancien adhérent", async () => {
    renderWithProviders(<Routes><Route path="/entities/:entity_id" element={<EntityDetailPage />} /></Routes>,
      { session: session("sci"), route: "/entities/3" });
    expect(await screen.findByText(/Solde fournisseur/)).toBeInTheDocument();
    expect(screen.queryByText("Adhésion HelloAsso")).not.toBeInTheDocument();
    expect(screen.queryByText("Adhérent")).not.toBeInTheDocument();
    expect(screen.queryByText("Bénévole")).not.toBeInTheDocument();
  });

  it("tableau de bord : pas de tuile Adhésions", async () => {
    renderWithProviders(<DashboardPage />, { session: session("sci") });
    expect(await screen.findByText("Résultat courant")).toBeInTheDocument();
    expect(screen.queryByText("Adhésions")).not.toBeInTheDocument();
  });
});

describe("société", () => {
  beforeEach(() => { sci = true; });

  it("Structure : bloc Société avec le statut JEI, sans RNA", async () => {
    renderWithProviders(<OrganizationPage />, { session: session("societe") });
    expect(await screen.findByText("Société")).toBeInTheDocument();
    expect(screen.getByLabelText("Jeune entreprise innovante depuis")).toBeInTheDocument();
    expect(screen.queryByLabelText("Numéro RNA")).not.toBeInTheDocument();
  });
});

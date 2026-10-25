// Revue de la comparaison avec Sirene (lot G5) : progression et arrêt, champs vides cochés, différents
// non cochés, tiers sans proposition, application de la sélection et champs laissés tels quels.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router";
import { renderWithProviders, TEST_SESSION } from "../../test/render";
import SireneReviewPage from "./SireneReviewPage";

const DONE = {
  job: { id: 5, status: "done", message: "Synchronisation terminée.", progress_done: 3, progress_total: 3 },
  result: { total: 3, compared: 3, cancelled: false, items: [
    { entity_id: 1, name: "INSEE Poitiers", state: "changes", state_label: "À revoir", warnings: [], changes: [
      { field: "city", label: "Ville", current: "Montrouge", proposed: "Poitiers", computed: false, kind: "different" },
      { field: "naf_code", label: "Activité (NAF)", current: null, proposed: "8411Z", computed: false, kind: "empty" },
    ] },
    { entity_id: 2, name: "Ancienne SARL", state: "ceased", state_label: "Cessé ou fermé", warnings: [], changes: [] },
    { entity_id: 3, name: "À jour", state: "up_to_date", state_label: "À jour", warnings: [], changes: [] },
  ] },
  applied: false,
};

let review: unknown;
let posted: { url: string; body: unknown }[];
beforeEach(() => {
  posted = [];
  review = DONE;
  vi.spyOn(globalThis, "fetch").mockImplementation(((input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = String(input);
    if (init.method === "POST") {
      posted.push({ url, body: JSON.parse(String(init.body ?? "{}")) });
      const body = url.endsWith("/apply")
        ? { applied: 1, skipped: [{ entity_id: 1, field: "city", reason: "Modifié depuis la revue : valeur conservée." }], notices: [] }
        : { notices: [] };
      return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
    }
    return Promise.resolve(new Response(JSON.stringify(review), { status: 200 }));
  }) as typeof fetch);
});
afterEach(() => vi.restoreAllMocks());

const render = () => renderWithProviders(
  <Routes><Route path="/entities/sirene-review/:job_id" element={<SireneReviewPage />} /></Routes>,
  { session: TEST_SESSION, route: "/entities/sirene-review/5" });

describe("revue Sirene", () => {
  it("en cours : progression et arrêt", async () => {
    review = { job: { id: 5, status: "running", message: "1 tiers sur 3 comparés à Sirene…", progress_done: 1, progress_total: 3 },
      result: null, applied: false };
    render();
    expect(await screen.findByText("1 tiers sur 3 comparés à Sirene…")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Arrêter" }));
    await waitFor(() => expect(posted[0].url).toBe("/api/v1/entities/sirene-refresh/5/cancel"));
  });

  it("coche les champs vides, applique la sélection, montre ce qui est laissé", async () => {
    render();
    expect(await screen.findByRole("checkbox", { name: "INSEE Poitiers : Activité (NAF)" })).toBeChecked();
    const city = screen.getByRole("checkbox", { name: "INSEE Poitiers : Ville" });
    expect(city).not.toBeChecked();
    expect(screen.getByText("84.11Z")).toBeInTheDocument();
    expect(screen.getByText("Cessé ou fermé")).toBeInTheDocument();
    expect(screen.queryByRole("checkbox", { name: /Ancienne SARL/ })).not.toBeInTheDocument();
    await userEvent.click(city);
    await userEvent.click(screen.getByRole("button", { name: "Appliquer la sélection (2)" }));
    await waitFor(() => expect(posted[0]).toEqual({ url: "/api/v1/entities/sirene-refresh/5/apply",
      body: { changes: { 1: ["naf_code", "city"] } } }));
    expect(await screen.findByText(/Modifié depuis la revue/)).toBeInTheDocument();
  });

  it("déjà appliquée : lecture seule", async () => {
    review = { ...DONE, applied: true, result: { ...DONE.result, applied_at: "2026-10-25T22:00:00" } };
    render();
    expect(await screen.findByText(/Sélection appliquée le/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Appliquer la sélection/ })).not.toBeInTheDocument();
  });
});

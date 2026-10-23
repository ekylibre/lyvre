import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { notifications } from "@mantine/notifications";
import { renderWithProviders, TEST_SESSION } from "../../test/render";
import { fromMovement, readyForPreview, toPayload, type MovementValues } from "./register";
import RegisterPage from "./RegisterPage";
import type { Movement } from "./types";

const DONATION: MovementValues = {
  movement_date: "2020-01-15", kind: "donation", nominal: "", price: "", description: "",
  lines: [
    { associate_id: "1", nature: "full", direction: "out", parts: "300" },
    { associate_id: "1", nature: "usufruct", direction: "in", parts: "300" },
    { associate_id: "2", nature: "bare", direction: "in", parts: "300" },
  ],
};

describe("lignes du registre", () => {
  it("signe les parts selon le sens, ou le sens imposé par le type", () => {
    expect(toPayload(DONATION).lines.map((l) => l.parts)).toEqual([-300, 300, 300]);
    const reduction = toPayload({ ...DONATION, kind: "reduction", nominal: "10" });
    expect(reduction.lines.map((l) => l.parts)).toEqual([-300, -300, -300]);
    expect(reduction.nominal).toBe("10");
    expect(toPayload({ ...DONATION, nominal: "10" }).nominal).toBe(""); // pas de nominal pour une donation
    expect(readyForPreview(DONATION)).toBe(true);
    expect(readyForPreview({ ...DONATION, kind: "subscription" })).toBe(false); // nominal manquant
  });

  it("relit un mouvement enregistré", () => {
    const movement: Movement = { id: 5, movement_date: "2019-07-29", kind: "subscription", kind_label: "Souscription",
      nominal_cents: 1000, price_cents: null, description: null, attachment: null,
      lines: [{ associate_id: 1, associate: "A", nature: "full", nature_label: "Pleine propriété", parts: 1000 }] };
    expect(fromMovement(movement)).toMatchObject({ nominal: "10,00",
      lines: [{ associate_id: "1", nature: "full", direction: "in", parts: "1000" }] });
  });
});

type Call = { method: string; url: string; body: any }; // eslint-disable-line @typescript-eslint/no-explicit-any
let calls: Call[];
const json = (status: number, body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status }));
const ADMIN = { ...TEST_SESSION, role: "admin" as const, permissions: { write: true, instance_admin: true } };
const META = {
  at: "2026-10-23", capital: { parts: 0, nominal_cents: null, capital_cents: null, ledger_cents: 0, warnings: [] },
  situation: [], natures: [], associates: [{ value: "1", label: "Pascal" }],
  kinds: [{ value: "subscription", label: "Souscription" }, { value: "transfer", label: "Cession" }],
};

beforeEach(() => {
  calls = [];
  vi.spyOn(notifications, "show").mockReturnValue("id");
  vi.spyOn(globalThis, "fetch").mockImplementation(((input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = String(input);
    const method = init.method ?? "GET";
    const body = init.body ? JSON.parse(init.body as string) : undefined;
    calls.push({ method, url, body });
    if (url.startsWith("/api/v1/share-movements") && method === "GET") return json(200, { items: [], meta: META });
    if (url === "/api/v1/share-movements/preview") {
      return json(200, { total_parts: 1000, rows: [{ associate_id: 1, name: "Pascal",
        parts: { full: 1000, usufruct: 0, bare: 0 }, percent: { full: 100, usufruct: 0, bare: 0 } }] });
    }
    if (url === "/api/v1/share-movements" && method === "POST") return json(201, { item: {}, notices: [] });
    return json(404, { error: { code: "not_found", message: "?" } });
  }) as typeof fetch);
});

afterEach(() => vi.restoreAllMocks());

describe("registre des parts", () => {
  it("souscription : aperçu de la situation puis inscription", async () => {
    const user = userEvent.setup();
    renderWithProviders(<RegisterPage />, { route: "/share-movements/new", session: ADMIN });
    await user.type(await screen.findByLabelText(/Valeur nominale/), "10");
    await user.click(screen.getByRole("combobox", { name: "Associé (ligne 1)" }));
    await user.click(await screen.findByRole("option", { name: "Pascal" }));
    await user.type(screen.getByLabelText("Parts (ligne 1)"), "1000");
    expect(screen.getByText("reçoit")).toBeTruthy(); // sens imposé par la souscription
    expect(await screen.findByText(/Situation après le mouvement/)).toBeTruthy();
    expect(screen.getByText("1 000 (100 %)")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Inscrire au registre" }));
    await waitFor(() => expect(calls.find((c) => c.url === "/api/v1/share-movements" && c.method === "POST")?.body)
      .toMatchObject({ kind: "subscription", nominal: "10", lines: [{ associate_id: 1, nature: "full", parts: 1000 }] }));
  });

  it("trésorier : lecture seule", async () => {
    renderWithProviders(<RegisterPage />, { route: "/share-movements/" });
    expect(await screen.findByText(/Aucun mouvement/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Nouveau mouvement" })).toBeNull();
  });
});

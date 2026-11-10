// Lot AG9b.a : tiroir de l'assistant, réponse diffusée (SSE) et outils consultés.
import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, screen } from "@testing-library/react";
import { renderWithProviders, TEST_SESSION } from "../../test/render";
import { ActionCard, AssistantPanel, AssistantText, type AssistantStatus } from "./AssistantDrawer";

const STATUS: AssistantStatus = { applies: true, enabled: true, available: true, message: null, model: "claude-haiku-5-5",
  model_label: "Claude Haiku 5.5", can_propose: true, quota_left: 1999000, server_key: false };
const json = (body: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(body), { status }));
const sse = (events: unknown[]) => Promise.resolve(new Response(events.map((e) => `event: x\ndata: ${JSON.stringify(e)}\n\n`).join(""),
  { status: 200, headers: { "Content-Type": "text/event-stream" } }));

afterEach(() => vi.restoreAllMocks());

describe("Assistant", () => {
  it("envoie la question et affiche la réponse au fil de l'eau", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(((url: string, init?: RequestInit) => {
      const u = String(url);
      if (u.endsWith("/messages")) return sse([{ type: "tool", name: "get_agenda" }, { type: "text", text: "Acompte de TVA le **05/11**." },
        { type: "error", message: "Quota bientôt atteint." }, { type: "done" }]);
      if (u.endsWith("/assistant/conversations") && init?.method === "POST") return json({ item: { id: 3, title: "x", updated_at: "" } }, 201);
      return json({ items: [] });
    }) as typeof globalThis.fetch);
    renderWithProviders(<AssistantPanel status={STATUS} />, { route: "/agenda/", session: { ...TEST_SESSION, role: "admin" as const } });
    fireEvent.change(screen.getByLabelText("Question"), { target: { value: "Que dois-je payer ?" } });
    fireEvent.click(screen.getByRole("button", { name: "Envoyer" }));
    expect(await screen.findByText("Que dois-je payer ?")).toBeInTheDocument();
    expect(await screen.findByText("05/11")).toBeInTheDocument();
    expect(screen.getByText("Échéancier")).toBeInTheDocument();
    expect(screen.getByText("Quota bientôt atteint.")).toBeInTheDocument();
    const call = fetchMock.mock.calls.find(([u]) => String(u).endsWith("/conversations/3/messages"));
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({ text: "Que dois-je payer ?", explain: false, page: { route: "/agenda/" } });
  });

  it("question « Expliquer » envoyée aussitôt, avec un effort élevé, et carte de brouillon", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(((url: string, init?: RequestInit) => {
      const u = String(url);
      if (u.endsWith("/messages")) return sse([{ type: "action", action: { id: 9, kind: "entry", status: "open", summary: "Écriture",
        payload: { lines: [{ account: "60111", account_label: "Engrais", debit_cents: 120050, credit_cents: 0 },
          { account: "401", account_label: "Fournisseurs", debit_cents: 0, credit_cents: 120050 }] } } },
        { type: "text", text: "Voici le brouillon." }, { type: "done" }]);
      if (u.endsWith("/assistant/conversations") && init?.method === "POST") return json({ item: { id: 4, title: "x", updated_at: "" } }, 201);
      return json({ items: [] });
    }) as typeof globalThis.fetch);
    renderWithProviders(<AssistantPanel status={STATUS} initial={{ question: "Explique ce contrôle", explain: true }} />,
      { route: "/fiscal-years/1/closing", session: { ...TEST_SESSION, role: "admin" as const } });
    expect(await screen.findByText("Voici le brouillon.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ouvrir le brouillon" })).toBeInTheDocument();
    expect(screen.getByText("60111 Engrais")).toBeInTheDocument();
    const call = fetchMock.mock.calls.find(([u]) => String(u).endsWith("/conversations/4/messages"));
    expect(JSON.parse(String(call?.[1]?.body)).explain).toBe(true);
  });

  it("carte d'échéance : confirmation explicite", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(((url: string) => json(String(url).includes("/agenda/states")
      ? { item: { id: 5 } } : { item: {} })) as typeof globalThis.fetch);
    renderWithProviders(<ActionCard action={{ id: 7, kind: "deadline", status: "open",
      payload: { deadline_id: "FIS-03#0", occurs_on: "2026-05-19", period: "2025", status: "done", title: "Liasse BA" } }} />);
    fireEvent.click(screen.getByRole("button", { name: "Confirmer" }));
    expect(await screen.findByText("fait")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([u]) => String(u).endsWith("/api/v1/assistant/proposals/7"))).toBe(true);
  });

  it("assistant indisponible et rendu des listes", () => {
    renderWithProviders(<><AssistantPanel status={{ ...STATUS, available: false, message: "Intégration Assistant Claude non configurée." }} />
      <AssistantText text={"Deux échéances [FIS-03] :\n\n- TVA [vat.rsa.threshold_cents]\n- MSA"} /></>);
    expect(screen.getByText(/non configurée/)).toBeInTheDocument();
    expect(screen.getByText("MSA").closest("li")).not.toBeNull();
    expect(screen.getByText("FIS-03").closest("a")).toHaveAttribute("href", "/agenda/");
    expect(screen.getByText("vat.rsa.threshold_cents")).toBeInTheDocument();
  });

  it("rend un tableau Markdown en tableau", () => {
    renderWithProviders(<AssistantText text={"Détail\n| Date | Échéance |\n|---|---|\n| 15/10/2026 | Taxe foncière [FIS-06] |"} />);
    expect(screen.getByRole("columnheader", { name: "Échéance" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "15/10/2026" })).toBeInTheDocument();
    expect(screen.queryByText(/\|---/)).not.toBeInTheDocument();
    expect(screen.getByText("Détail")).toBeInTheDocument();
  });
});

// Lot AG9b.d : usage du mois de l'assistant.
import { afterEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "../../test/render";
import { AssistantUsage } from "./AssistantUsage";

afterEach(() => vi.restoreAllMocks());

describe("Usage de l'assistant", () => {
  it("tokens, quota et coût estimé par modèle", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((() => Promise.resolve(new Response(JSON.stringify({ item: {
      month: "2026-11", used_tokens: 12000, quota_tokens: 2000000, left_tokens: 1988000, cost_usd: 0.0021,
      models: [{ model: "claude-haiku-5-5", responses: 4, input_tokens: 10000, output_tokens: 2000, cache_read_tokens: 30000, cost_usd: 0.0021 }] } }),
    { status: 200 }))) as typeof globalThis.fetch);
    renderWithProviders(<AssistantUsage />);
    expect(await screen.findByText("claude-haiku-5-5")).toBeInTheDocument();
    expect(screen.getByText(/quota mensuel/)).toBeInTheDocument();
  });
});

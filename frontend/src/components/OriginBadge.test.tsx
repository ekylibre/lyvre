// Lot AK3 : badge d'origine des saisies par clé d'API et lien de la ligne « À traiter ».
import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "../test/render";
import { agentSignalHref } from "../features/dashboard/AttentionCard";
import { OriginBadge } from "./OriginBadge";

describe("saisies par clé d'API", () => {
  it("montre le nom de la clé, rien pour une saisie dans Lyvre", () => {
    renderWithProviders(<OriginBadge origin={{ label: "Aiffel — terrain", external_ref: null, pending: true, checked_at: null }} />);
    expect(screen.getByText("Aiffel — terrain")).toBeInTheDocument();
    const { container } = renderWithProviders(<div data-testid="vide"><OriginBadge origin={null} /></div>);
    expect(container.querySelector("[data-testid=vide]")?.textContent).toBe("");
  });

  it("mène à la liste la plus utile", () => {
    expect(agentSignalHref({ purchases: 2, entities: 1, entries: 0, total: 3 })).toBe("/purchases/?from_key=1");
    expect(agentSignalHref({ purchases: 0, entities: 1, entries: 1, total: 2 })).toBe("/entries/?state=draft");
    expect(agentSignalHref({ purchases: 0, entities: 1, entries: 0, total: 1 })).toBe("/entities/");
  });
});

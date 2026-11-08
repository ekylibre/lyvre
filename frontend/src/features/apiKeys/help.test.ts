import { expect, it } from "vitest";
import { callOutcome } from "./JournalDrawer";
import { toolsByDomain } from "./ApiHelpPage";

it("classe les outils par domaine, les outils toujours disponibles en tête", () => {
  const tool = (name: string, domain: string) => ({ name, title: name, domain, domain_label: "", access: "read" as const, description: "" });
  const groups = toolsByDomain({
    domains: [{ key: "accounting", label: "Comptabilité", description: "", writable: true },
      { key: "purchases", label: "Achats", description: "", writable: true }],
    tools: [tool("list_purchases", "purchases"), tool("get_context", "*"), tool("get_balances", "accounting")],
  });
  expect(groups.map((g) => [g.label, g.tools.map((t) => t.name)])).toEqual([
    ["Toujours disponibles", ["get_context"]], ["Comptabilité", ["get_balances"]], ["Achats", ["list_purchases"]]]);
});

it("donne le résultat lisible d'un appel", () => {
  expect(callOutcome({ status: 200 }).label).toBe("Accepté");
  expect(callOutcome({ status: 403 }).label).toBe("Refusé");
  expect(callOutcome({ status: 429 }).label).toBe("Limite atteinte");
  expect(callOutcome({ status: 422 }).label).toBe("Erreur");
});

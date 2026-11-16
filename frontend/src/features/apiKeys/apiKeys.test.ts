import { describe, expect, it } from "vitest";
import { canWrite, isoInDays, mcpConfig, toggleDomain } from "./apiKeys";

describe("grille des domaines", () => {
  it("cocher l'écriture coche la lecture, décocher la lecture décoche l'écriture", () => {
    let grid = toggleDomain({ read: [], write: [] }, "purchases", "write", true);
    expect(grid).toEqual({ read: ["purchases"], write: ["purchases"] });
    grid = toggleDomain(grid, "purchases", "read", false);
    expect(grid).toEqual({ read: [], write: [] });
    grid = toggleDomain(toggleDomain(grid, "bank", "read", true), "bank", "write", false);
    expect(grid).toEqual({ read: ["bank"], write: [] });
  });

  it("refuse l'écriture à un expert-comptable et aux domaines en lecture seule", () => {
    const purchases = { key: "purchases", label: "Achats", description: "", writable: true };
    expect(canWrite(purchases, "treasurer")).toBe(true);
    expect(canWrite(purchases, "accountant")).toBe(false);
    expect(canWrite({ ...purchases, writable: false }, "admin")).toBe(false);
  });
});

it("donne la date d'expiration et la configuration MCP", () => {
  expect(isoInDays(365, new Date("2026-11-08T12:00:00Z"))).toBe("2027-11-08");
  const config = JSON.parse(mcpConfig("https://app.lyvre.org/mcp", "lyv_x"));
  expect(config.mcpServers.lyvre).toEqual({ type: "http", url: "https://app.lyvre.org/mcp", headers: { Authorization: "Bearer lyv_x" } });
});

import { describe, expect, it } from "vitest";
import { checkSummary, localDateTime } from "./types";

describe("intégrations", () => {
  it("affiche les horodatages du serveur (UTC) à l'heure locale", () => {
    expect(localDateTime(null)).toBe("—");
    expect(localDateTime("2026-10-20T19:52:00")).toMatch(/^20\/10\/2026 \d{2}:52$/);
    expect(checkSummary({ ok: true, message: "", checked_at: "2026-10-20T19:52:00", duration_ms: 1250 })).toMatch(/ · 1,3 s$/);
  });
});

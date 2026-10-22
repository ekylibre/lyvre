import { describe, expect, it } from "vitest";
import { labelFromSlug, megabytes, slugFromFilename } from "./types";

describe("instances", () => {
  it("déduit le slug du nom d'une sauvegarde", () => {
    expect(slugFromFilename("asso-dupont-20261022-120000.zip")).toBe("asso-dupont");
    expect(slugFromFilename("pre-restore-sci-20261022-120000.zip")).toBe("sci");
    expect(slugFromFilename("Ma-Base.db")).toBe("ma-base");
    expect(labelFromSlug("asso-dupont")).toBe("Asso Dupont");
    expect(megabytes(3 * 1024 * 1024 + 200_000)).toBe("3,2 Mo");
  });
});

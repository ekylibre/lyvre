import { afterEach, describe, expect, it, vi } from "vitest";
import { isChunkLoadError, loadWithReload } from "./chunkReload";

const chunkError = () => new TypeError(
  "Failed to fetch dynamically imported module: https://lyvre.seconde-nature.net/static/dist/assets/SelectInstancePage-DAM9WnIy.js");

describe("loadWithReload", () => {
  afterEach(() => { sessionStorage.clear(); vi.useRealTimers(); });

  it("returns the module when it loads", async () => {
    const reload = vi.fn();
    await expect(loadWithReload(async () => ({ default: 1 }), reload)).resolves.toEqual({ default: 1 });
    expect(reload).not.toHaveBeenCalled();
  });

  it("reloads the page once when a chunk is missing, then shows the error", async () => {
    const reload = vi.fn();
    void loadWithReload(() => Promise.reject(chunkError()), reload);
    await vi.waitFor(() => expect(reload).toHaveBeenCalledTimes(1));
    // Juste après le rechargement, le fichier manque encore : pas de boucle, l'erreur remonte.
    await expect(loadWithReload(() => Promise.reject(chunkError()), reload)).rejects.toThrow(/dynamically imported/);
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it("reloads again once the guard delay has passed", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    const reload = vi.fn();
    void loadWithReload(() => Promise.reject(chunkError()), reload);
    await vi.waitFor(() => expect(reload).toHaveBeenCalledTimes(1));
    vi.setSystemTime(Date.now() + 11_000);
    void loadWithReload(() => Promise.reject(chunkError()), reload);
    await vi.waitFor(() => expect(reload).toHaveBeenCalledTimes(2));
  });

  it("does not reload on other errors", async () => {
    const reload = vi.fn();
    await expect(loadWithReload(() => Promise.reject(new Error("boom")), reload)).rejects.toThrow("boom");
    expect(reload).not.toHaveBeenCalled();
  });
});

describe("isChunkLoadError", () => {
  it("recognises Chrome, Firefox and Safari messages", () => {
    expect(isChunkLoadError(chunkError())).toBe(true);
    expect(isChunkLoadError(new TypeError("error loading dynamically imported module: x.js"))).toBe(true);
    expect(isChunkLoadError(new TypeError("Importing a module script failed."))).toBe(true);
    expect(isChunkLoadError(new Error("Network error"))).toBe(false);
  });
});

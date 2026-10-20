import "@testing-library/jest-dom/vitest";

// Node ≥ 25 expose un localStorage natif (inutilisable sans --localstorage-file)
// qui masque celui de jsdom : le remplacer par un stockage en mémoire.
if (typeof globalThis.localStorage?.clear !== "function") {
  const data = new Map<string, string>();
  const storage: Storage = {
    get length() { return data.size; },
    clear: () => data.clear(),
    getItem: (k) => (data.has(k) ? data.get(k)! : null),
    key: (i) => Array.from(data.keys())[i] ?? null,
    removeItem: (k) => { data.delete(k); },
    setItem: (k, v) => { data.set(k, String(v)); },
  };
  Object.defineProperty(globalThis, "localStorage", { value: storage, configurable: true });
}

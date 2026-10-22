import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// Sans `globals`, Testing Library ne démonte pas les rendus entre deux tests.
afterEach(() => cleanup());

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

// jsdom n'implémente pas le défilement.
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}

// Mantine : jsdom n'implémente ni matchMedia ni ResizeObserver. Une requête absente
// (colonne de mantine-datatable sans `visibleMediaQuery`) doit être vraie.
if (!window.matchMedia) {
  window.matchMedia = (query: string) => ({
    matches: !query || query === "undefined", media: query, onchange: null,
    addListener: () => {}, removeListener: () => {},
    addEventListener: () => {}, removeEventListener: () => {}, dispatchEvent: () => false,
  }) as MediaQueryList;
}
if (!("ResizeObserver" in window)) {
  (window as unknown as { ResizeObserver: unknown }).ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}
window.HTMLElement.prototype.scrollTo = window.HTMLElement.prototype.scrollTo ?? (() => {});
// Textarea autosize de Mantine écoute le chargement des polices (absent de jsdom).
if (!("fonts" in document)) {
  Object.defineProperty(document, "fonts", {
    value: { addEventListener: () => {}, removeEventListener: () => {}, ready: Promise.resolve() },
    configurable: true,
  });
}

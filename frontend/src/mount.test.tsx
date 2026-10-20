import { afterEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import type { Root } from "react-dom/client";
import { mountIslands } from "./mount";

function Hello({ name }: { name: string }) {
  return <p>Bonjour {name}</p>;
}

const registry = { hello: async () => ({ default: Hello }) };
let roots: Root[] = [];

afterEach(() => {
  act(() => roots.forEach((r) => r.unmount()));
  roots = [];
  document.body.innerHTML = "";
});

describe("mountIslands", () => {
  it("monte un îlot avec les props JSON de data-props", async () => {
    document.body.innerHTML = `<div data-island="hello" data-props='{"name": "Léa"}'></div>`;
    await act(async () => {
      roots = await mountIslands(document, registry);
    });
    expect(document.body.textContent).toContain("Bonjour Léa");
  });

  it("ne monte pas deux fois le même élément", async () => {
    document.body.innerHTML = `<div data-island="hello" data-props='{"name": "A"}'></div>`;
    await act(async () => {
      roots = await mountIslands(document, registry);
    });
    let again: Root[] = [];
    await act(async () => {
      again = await mountIslands(document, registry);
    });
    expect(again).toHaveLength(0);
  });

  it("ignore un îlot inconnu ou des props invalides", async () => {
    const error = vi.spyOn(console, "error").mockImplementation(() => {});
    document.body.innerHTML = `
      <div data-island="absent"></div>
      <div data-island="hello" data-props="{pas du json"></div>`;
    await act(async () => {
      roots = await mountIslands(document, registry);
    });
    expect(roots).toHaveLength(0);
    expect(error).toHaveBeenCalledTimes(2);
    error.mockRestore();
  });
});

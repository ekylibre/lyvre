import { StrictMode } from "react";
import { createRoot, type Root } from "react-dom/client";
import type { IslandLoader, IslandProps } from "./islands/registry";

const MOUNTED = "islandMounted";

/**
 * Monte les éléments [data-island] présents sous `root`.
 * Retourne les racines React créées (utile pour les tests).
 */
export async function mountIslands(
  root: ParentNode,
  registry: Record<string, IslandLoader>,
): Promise<Root[]> {
  const elements = Array.from(root.querySelectorAll<HTMLElement>("[data-island]"));
  const roots: Root[] = [];
  for (const el of elements) {
    if (el.dataset[MOUNTED]) continue;
    const name = el.dataset.island ?? "";
    const load = registry[name];
    if (!load) {
      console.error(`[islands] îlot inconnu : « ${name} »`);
      continue;
    }
    let props: IslandProps = {};
    try {
      props = JSON.parse(el.dataset.props || "{}") as IslandProps;
    } catch (err) {
      console.error(`[islands] props invalides pour « ${name} »`, err);
      continue;
    }
    el.dataset[MOUNTED] = "1";
    const { default: Component } = await load();
    const reactRoot = createRoot(el);
    reactRoot.render(
      <StrictMode>
        <Component {...props} />
      </StrictMode>,
    );
    roots.push(reactRoot);
  }
  return roots;
}

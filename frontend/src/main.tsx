import { islands } from "./islands/registry";
import { mountIslands } from "./mount";

void mountIslands(document, islands);

// Contenu remplacé par HTMX (navigation dans #page-content) : monter les
// nouveaux îlots éventuels.
document.addEventListener("htmx:afterSettle", () => {
  void mountIslands(document, islands);
});

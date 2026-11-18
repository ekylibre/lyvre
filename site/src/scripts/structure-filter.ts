// Filtre de la page Fonctionnalités : ne garde que les fonctionnalités d'un type de structure (celles sans
// structure servent à toutes), masque les sous-parties et modules vides, et garde le choix dans l'adresse
// (?pour=agri) pour qu'il se partage. La barre est affichée d'emblée (pas de décalage à son apparition) ; sans
// JavaScript, ses boutons restent sans effet et tout s'affiche.
const LABELS: Record<string, string> = {
  asso: "une association", sci: "une SCI", agri: "une exploitation agricole", societe: "une société",
};

export function setupStructureFilter(): void {
  const bar = document.querySelector<HTMLElement>("[data-structure-filter]");
  if (!bar) return;
  const buttons = [...bar.querySelectorAll<HTMLButtonElement>("button[data-structure]")];
  const status = bar.querySelector<HTMLElement>("[data-structure-status]");
  const modules = [...document.querySelectorAll<HTMLElement>("[data-module]")];

  function apply(structure: string, announce: boolean): void {
    for (const b of buttons) b.setAttribute("aria-pressed", String(b.dataset.structure === structure));
    let shown = 0;
    for (const module of modules) {
      for (const item of module.querySelectorAll<HTMLElement>("[data-structures]")) {
        const list = (item.dataset.structures ?? "").split(" ").filter(Boolean);
        item.hidden = !!structure && list.length > 0 && !list.includes(structure);
        if (!item.hidden) shown += 1;
      }
      for (const group of module.querySelectorAll<HTMLElement>("[data-group]")) {
        group.hidden = !group.querySelector("[data-structures]:not([hidden])");
      }
      module.hidden = !module.querySelector("[data-structures]:not([hidden])");
      const link = document.querySelector<HTMLElement>(`[data-module-link="${module.dataset.module}"]`);
      if (link) link.hidden = module.hidden;
    }
    if (status && announce) {
      status.textContent = structure
        ? `${shown} fonctionnalités pour ${LABELS[structure]}, ${modules.filter((m) => !m.hidden).length} modules.`
        : `Toutes les fonctionnalités : ${shown}.`;
    }
    const url = new URL(window.location.href);
    if (structure) url.searchParams.set("pour", structure);
    else url.searchParams.delete("pour");
    history.replaceState(null, "", url);
  }

  for (const b of buttons) b.addEventListener("click", () => apply(b.dataset.structure ?? "", true));
  const initial = new URL(window.location.href).searchParams.get("pour") ?? "";
  apply(initial in LABELS ? initial : "", false);

  // Index : module en cours de lecture.
  const links = new Map(modules.map((m) => [m.id, document.querySelector<HTMLAnchorElement>(`.modules-index a[href="#${m.id}"]`)]));
  const observer = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue;
      for (const [id, a] of links) a?.setAttribute("aria-current", String(id === entry.target.id));
    }
  }, { rootMargin: "-30% 0px -60% 0px" });
  for (const m of modules) observer.observe(m);
}

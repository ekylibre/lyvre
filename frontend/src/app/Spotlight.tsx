// Palette de commandes (Ctrl+K, FM9/FM13) : aller à un écran ; la recherche de tiers,
// factures et écritures est branchée en phase C (GET /api/v1/search).
import { useMemo } from "react";
import { Spotlight, type SpotlightActionData } from "@mantine/spotlight";
import { IconSearch } from "@tabler/icons-react";
import { useCurrentSession } from "../api/session";
import { useGoTo } from "./navigation";

export function AppSpotlight() {
  const session = useCurrentSession();
  const goTo = useGoTo();
  const actions = useMemo<SpotlightActionData[]>(() => {
    const links: SpotlightActionData[] = [];
    for (const menu of session.nav) {
      if (menu.url) links.push({ id: menu.url, label: menu.label, onClick: () => goTo(menu.url!) });
      for (const item of menu.items ?? []) {
        if ("url" in item) {
          links.push({ id: item.url, label: item.label, description: menu.label, onClick: () => goTo(item.url) });
        }
      }
    }
    for (const link of session.admin_links) {
      links.push({ id: link.url, label: link.label, description: "Administration", onClick: () => goTo(link.url) });
    }
    links.push({ id: "select-instance", label: "Changer d'instance", onClick: () => goTo("/select-instance") });
    return links;
  }, [session, goTo]);
  return (
    <Spotlight actions={actions} shortcut={["mod + K"]} nothingFound="Aucun résultat" highlightQuery
      limit={12} searchProps={{ leftSection: <IconSearch size={18} />, placeholder: "Aller à…" }} />
  );
}

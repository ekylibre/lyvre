// Onglets entre pages sœurs (lot NV2, claudedocs/design_navigation.md § 3) : chaque onglet est une page avec son
// adresse (favoris et liens de l'assistant conservés) ; changer d'onglet change l'adresse sans recharger.
import { Tabs } from "@mantine/core";
import { useLocation } from "react-router";
import { useGoTo } from "../app/navigation";

export interface PageTab { label: string; url: string }

export const ENTRY_TABS: PageTab[] = [{ label: "Écritures", url: "/entries/" }, { label: "Lettrage", url: "/lettering/" }];
export const LEASE_TABS: PageTab[] = [{ label: "Baux et quittances", url: "/leases/" },
  { label: "Indices de loyer", url: "/rent-indices/" }];

const clean = (url: string) => url.replace(/\/$/, "");

export function PageTabs({ tabs }: { tabs: PageTab[] }) {
  const { pathname } = useLocation();
  const goTo = useGoTo();
  const current = tabs.find((t) => clean(pathname) === clean(t.url))?.url ?? tabs[0].url;
  return (
    <Tabs value={current} onChange={(url) => url && url !== current && goTo(url)} mb="md">
      <Tabs.List>
        {tabs.map((t) => <Tabs.Tab key={t.url} value={t.url}>{t.label}</Tabs.Tab>)}
      </Tabs.List>
    </Tabs>
  );
}

// Palette de commandes (Ctrl+K, FM9/FM13) : aller à un écran, et chercher un tiers, une
// facture d'achat ou une écriture (GET /api/v1/search, 2 caractères au moins).
import { useMemo, useState } from "react";
import { Group, Loader, Text } from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { Spotlight, spotlight } from "@mantine/spotlight";
import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { api } from "../api/client";
import { navLinks, useCurrentSession } from "../api/session";
import { useGoTo } from "./navigation";

interface SearchGroup { label: string; items: { label: string; description: string | null; url: string }[] }
interface NavAction { id: string; label: string; description?: string; url: string }

const fold = (s: string) => s.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase();

export function AppSpotlight() {
  const session = useCurrentSession();
  const goTo = useGoTo();
  const [query, setQuery] = useState("");
  const [debounced] = useDebouncedValue(query.trim(), 250);

  const navActions = useMemo<NavAction[]>(() => {
    const links: NavAction[] = [];
    for (const link of navLinks(session.nav)) {
      links.push({ id: link.url, label: link.label, description: link.trail.join(" › ") || undefined, url: link.url });
    }
    for (const link of session.admin_links) links.push({ id: link.url, label: link.label, description: "Administration", url: link.url });
    links.push({ id: "select-instance", label: "Changer d'instance", url: "/select-instance" });
    return links;
  }, [session]);

  const { data: results, isFetching } = useQuery({
    queryKey: ["search", debounced], enabled: debounced.length >= 2, staleTime: 10_000,
    queryFn: () => api.get<{ groups: SearchGroup[] }>(`/api/v1/search?q=${encodeURIComponent(debounced)}`),
  });

  const screens = navActions.filter((a) => !query || fold(`${a.label} ${a.description ?? ""}`).includes(fold(query))).slice(0, 8);
  const groups = debounced.length >= 2 ? results?.groups ?? [] : [];
  const open = (url: string) => { spotlight.close(); goTo(url); };

  return (
    <Spotlight.Root query={query} onQueryChange={setQuery} shortcut={["mod + K"]} scrollable maxHeight={480}>
      <Spotlight.Search placeholder="Aller à un écran, chercher un tiers, une facture, une écriture…"
        leftSection={<Search size={18} />} rightSection={isFetching ? <Loader size="xs" /> : null} />
      <Spotlight.ActionsList>
        {screens.length > 0 && (
          <Spotlight.ActionsGroup label="Écrans">
            {screens.map((a) => (
              <Spotlight.Action key={a.id} onClick={() => open(a.url)}>
                <Group gap="xs"><Text>{a.label}</Text>{a.description && <Text size="sm" c="dimmed">{a.description}</Text>}</Group>
              </Spotlight.Action>
            ))}
          </Spotlight.ActionsGroup>
        )}
        {groups.map((g) => (
          <Spotlight.ActionsGroup key={g.label} label={g.label}>
            {g.items.map((item) => (
              <Spotlight.Action key={item.url} onClick={() => open(item.url)}>
                <Group gap="xs" wrap="nowrap"><Text>{item.label}</Text>
                  {item.description && <Text size="sm" c="dimmed" truncate>{item.description}</Text>}</Group>
              </Spotlight.Action>
            ))}
          </Spotlight.ActionsGroup>
        ))}
        {screens.length === 0 && groups.length === 0 && (
          <Spotlight.Empty>{debounced.length >= 2 && !isFetching ? "Aucun résultat." : "Tapez au moins deux lettres pour chercher."}</Spotlight.Empty>
        )}
      </Spotlight.ActionsList>
    </Spotlight.Root>
  );
}

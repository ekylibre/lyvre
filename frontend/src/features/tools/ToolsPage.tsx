// Outils › Calculettes (lot AG12, AGD29) : outils filtrés par type de structure (par défaut celui de l'instance),
// groupés par catégorie ; badge « préremplie » quand l'instance fournit des valeurs.
import { Badge, Card, Group, SegmentedControl, SimpleGrid, Stack, Text, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { FilterBar, useUrlParams } from "../../components/FilterBar";
import { PageHeader } from "../../components/PageHeader";
import { AppLink } from "../../app/navigation";
import { TOOL_CATEGORY_ICONS } from "../../app/navIcons";
import { IconTile } from "../../components/IconTile";
import { TOOLS_KEY, type CalcSpec } from "./types";

interface ListData {
  items: CalcSpec[];
  meta: { chart: string | null; instance_chart: string | null; charts: { value: string; label: string }[];
    categories: { value: string; label: string }[] };
}

export default function ToolsPage() {
  const [params, setParams] = useUrlParams({ chart: "" });
  const { data } = useQuery({ queryKey: [...TOOLS_KEY, params.chart],
    queryFn: () => api.get<ListData>(`/api/v1/calculators${params.chart ? `?chart=${params.chart}` : ""}`) });
  const chart = params.chart || data?.meta.chart || "all";
  return (
    <>
      <PageHeader title="Calculettes"
        description="Calculs courts, avec leur méthode et leurs sources. Rien n'est enregistré dans la comptabilité ; une calculette peut être préremplie avec les chiffres de la structure." />
      <FilterBar>
        <SegmentedControl size="xs" value={chart} onChange={(v) => setParams({ chart: v })}
          data={[...(data?.meta.charts ?? []), { value: "all", label: "Tous" }]} />
      </FilterBar>
      {data && data.items.length === 0 && <Text c="dimmed">Aucune calculette pour ce type de structure pour l'instant.</Text>}
      <Stack>
        {data?.meta.categories.map((cat) => {
          const items = data.items.filter((i) => i.category === cat.value);
          if (!items.length) return null;
          return (
            <div key={cat.value}>
              <Group gap="sm" mb="xs" wrap="nowrap">
                <IconTile {...TOOL_CATEGORY_ICONS[cat.value]} size={36} />
                <Title order={3}>{cat.label}</Title>
              </Group>
              <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }}>
                {items.map((i) => (
                  <Card key={i.code} withBorder component={AppLink} href={`/outils/${i.code}`}>
                    <Group justify="space-between" mb={4}><Text fw={600}>{i.title}</Text>
                      {i.prefillable && <Badge variant="light" color="lichen">préremplie</Badge>}</Group>
                    <Text size="sm" c="dimmed">{i.summary}</Text>
                  </Card>
                ))}
              </SimpleGrid>
            </div>
          );
        })}
      </Stack>
    </>
  );
}

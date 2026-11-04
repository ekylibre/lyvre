// Résumé du lundi en tête du tableau de bord d'une exploitation (lot AG9a.d) : en retard, cette semaine, à
// préparer, à vérifier ; le détail est dans Compta › Échéancier.
import { Anchor, Badge, Group, Paper, SimpleGrid, Stack, Text, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { AppLink } from "../../app/navigation";
import { MoneyText } from "../../components/Money";
import { formatDate } from "../../lib/format";
import { AGENDA_KEY, type SummaryLine, type WeeklySummary } from "./types";

const TILES: { key: keyof WeeklySummary["counts"]; label: string; color: string }[] = [
  { key: "late", label: "En retard", color: "brique" },
  { key: "this_week", label: "Cette semaine", color: "paille" },
  { key: "to_prepare", label: "À préparer", color: "ardoise" },
  { key: "to_check", label: "À vérifier", color: "lichen" },
];

function Line({ row }: { row: SummaryLine }) {
  return (
    <Group gap="xs" wrap="nowrap">
      <Text size="sm" c="dimmed" w={48}>{formatDate(row.date).slice(0, 5)}</Text>
      <Anchor component={AppLink} href={row.link} size="sm">{row.label}</Anchor>
      <Text size="sm" c="dimmed">{row.organism}</Text>
      {row.amount_cents !== null && <MoneyText cents={row.amount_cents} size="sm" />}
    </Group>
  );
}

export function AgendaWeekCard() {
  const { data } = useQuery({
    queryKey: [...AGENDA_KEY, "summary"],
    queryFn: () => api.get<{ item: WeeklySummary }>("/api/v1/agenda/summary"),
  });
  const summary = data?.item;
  if (!summary) return null;
  const urgent = [...summary.late, ...summary.this_week].slice(0, 6);
  return (
    <Paper withBorder p="md">
      <Group justify="space-between" mb="sm">
        <Title order={4}>Échéancier — semaine du {formatDate(summary.monday)}</Title>
        <Anchor component={AppLink} href="/agenda/" size="sm">Tout l'échéancier</Anchor>
      </Group>
      {summary.empty ? <Text size="sm" c="dimmed">Rien à signaler cette semaine.</Text> : (
        <Stack gap="sm">
          <SimpleGrid cols={{ base: 2, sm: 4 }}>
            {TILES.map((t) => (
              <Group key={t.key} gap="xs">
                <Badge size="lg" variant={summary.counts[t.key] ? "filled" : "light"} color={t.color}>{summary.counts[t.key]}</Badge>
                <Text size="sm">{t.label}</Text>
              </Group>))}
          </SimpleGrid>
          {urgent.length > 0 && <Stack gap={4}>{urgent.map((row) => <Line key={row.key} row={row} />)}</Stack>}
          {summary.to_check.slice(0, 3).map((d) => (
            <Text key={d.id} size="sm"><b>{d.title}</b>{d.link && <> — <Anchor component={AppLink} href={d.link} size="sm">
              {d.link_label ?? "Ouvrir"}</Anchor></>}</Text>))}
        </Stack>)}
    </Paper>
  );
}

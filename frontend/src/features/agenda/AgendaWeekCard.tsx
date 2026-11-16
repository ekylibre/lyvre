// Échéancier de la semaine en tête du tableau de bord d'une exploitation (lot AG9a.d, harmonisé au lot DB1) : compteurs
// en retard / cette semaine / à préparer / à vérifier, puis les échéances proches (date, libellé, organisme, montant)
// et les points à vérifier ; le détail est dans Compta › Échéancier.
import { Anchor, Group, Paper, SimpleGrid, Stack, Text, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { AppLink } from "../../app/navigation";
import { IconTile } from "../../components/IconTile";
import { MoneyText } from "../../components/Money";
import { formatDate } from "../../lib/format";
import { SignalRow } from "../dashboard/AttentionCard";
import { AGENDA_KEY, type SummaryLine, type WeeklySummary } from "./types";

const COUNTS: { key: keyof WeeklySummary["counts"]; label: string; tone: string }[] = [
  { key: "late", label: "En retard", tone: "brique" },
  { key: "this_week", label: "Cette semaine", tone: "paille" },
  { key: "to_prepare", label: "À préparer", tone: "ardoise" },
  { key: "to_check", label: "À vérifier", tone: "lichen" },
];

function Due({ row, late }: { row: SummaryLine; late: boolean }) {
  return (
    <div className="lv-due">
      <Text size="sm" className="lv-num" c={late ? "var(--lv-brique-ink)" : "dimmed"}>{formatDate(row.date).slice(0, 5)}</Text>
      <div><Anchor component={AppLink} href={row.link} size="sm">{row.label}</Anchor>
        {row.organism && <Text size="xs" c="dimmed">{row.organism}</Text>}</div>
      {row.amount_cents !== null ? <MoneyText cents={row.amount_cents} size="sm" /> : <span />}
    </div>
  );
}

export function AgendaWeekCard() {
  const { data } = useQuery({
    queryKey: [...AGENDA_KEY, "summary"],
    queryFn: () => api.get<{ item: WeeklySummary }>("/api/v1/agenda/summary"),
  });
  const summary = data?.item;
  if (!summary) return null;
  const late = new Set(summary.late.map((r) => r.key));
  const urgent = [...summary.late, ...summary.this_week].slice(0, 6);
  return (
    <Paper p="md" h="100%">
      <Group justify="space-between" mb="sm" wrap="nowrap">
        <Group gap="xs" wrap="nowrap"><IconTile icon="calendar-clock" size={28} />
          <div><Title order={2} size="h3">Échéancier</Title>
            <Text size="xs" c="dimmed">Semaine du {formatDate(summary.monday)}</Text></div></Group>
        <Anchor component={AppLink} href="/agenda/" size="sm">Tout l'échéancier</Anchor>
      </Group>
      <SimpleGrid cols={{ base: 2, sm: 4 }} spacing="xs" mb="sm">
        {COUNTS.map((c) => (
          <div key={c.key} className="lv-count" data-tone={c.tone} data-on={summary.counts[c.key] ? "" : undefined}>
            <Text className="lv-num" fz={22} lh="26px" fw={500}>{summary.counts[c.key]}</Text>
            <Text size="xs" c="dimmed">{c.label}</Text>
          </div>))}
      </SimpleGrid>
      {summary.empty ? <Text size="sm" c="dimmed">Aucune échéance cette semaine.</Text> : (
        <Stack gap="sm">
          {urgent.length > 0 && <div>{urgent.map((row) => <Due key={row.key} row={row} late={late.has(row.key)} />)}</div>}
          {summary.to_check.slice(0, 3).map((d) => (
            <SignalRow key={d.id} signal={{ key: d.id, tone: "lichen", icon: <IconTile icon="shield-check" size={28} />, title: d.title,
              action: d.link ? <Anchor component={AppLink} href={d.link} size="sm">{d.link_label ?? "Ouvrir"}</Anchor> : null }} />))}
        </Stack>)}
    </Paper>
  );
}

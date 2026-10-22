// Indicateurs › Visibilité & Impact : indicateurs phares, sections par dimension (valeur,
// évolution, tendance), fraîcheur des sources ; synchronisation GA4 / Facebook, export XLSX.
import { Badge, Button, Card, Group, Paper, SimpleGrid, Text, Title, Tooltip } from "@mantine/core";
import { Sparkline } from "@mantine/charts";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { useCan } from "../../api/session";
import { useUrlParams } from "../../components/FilterBar";
import { PageHeader } from "../../components/PageHeader";
import { Can } from "../../components/Can";
import { StatusBadge } from "../../components/StatusBadge";
import { formatDate } from "../../lib/format";
import { AppLink } from "../../app/navigation";
import { PeriodFilter } from "./PeriodFilter";
import { IMPACT_KEY, PERIOD_DEFAULTS, delta, periodQuery, type ImpactView, type Kpi } from "./types";

const PENDING: Record<string, string> = { manual: "En attente de saisie", snapshot: "Source non synchronisée" };

function KpiCard({ kpi }: { kpi: Kpi }) {
  const d = delta(kpi);
  const points = kpi.trend.filter((p) => p !== null).length;
  return (
    <Card padding="sm" style={{ opacity: kpi.available ? 1 : 0.55 }}>
      <Group justify="space-between" align="flex-start" wrap="nowrap">
        <Text size="sm" c="dimmed">{kpi.label}</Text>
        {points >= 2 && <Sparkline w={90} h={24} data={kpi.trend} curveType="linear" color="lichen" fillOpacity={0.15} strokeWidth={1.5}
          aria-label={`Tendance : ${kpi.label}`} />}
      </Group>
      <Group justify="space-between" align="flex-end" mt={4}>
        <Text fw={600} size="lg" className="lv-num">{kpi.formatted}</Text>
        {d ? <Badge variant="light" color={d.good ? "lichen" : "brique"} tt="none">{d.text}</Badge> : <Text size="sm" c="dimmed">—</Text>}
      </Group>
      {!kpi.available && <Text size="xs" c="dimmed" mt={4}>{PENDING[kpi.origin] ?? "Indisponible"}</Text>}
      {kpi.source_label && <Text size="xs" c="dimmed" mt={4}>Source : {kpi.source_label}</Text>}
    </Card>
  );
}

export function useImpact() {
  const [params, setParams] = useUrlParams(PERIOD_DEFAULTS);
  const query = periodQuery(params);
  const result = useQuery({ queryKey: [...IMPACT_KEY, query], placeholderData: (prev) => prev,
    queryFn: () => api.get<ImpactView>(`/api/v1/impact${query}`) });
  /** Changer de granularité garde les autres valeurs (préremplies par la période courante). */
  const change = (patch: Partial<typeof PERIOD_DEFAULTS>) => setParams({ ...result.data?.current, ...params, ...patch });
  return { ...result, query, change };
}

export default function ImpactPage() {
  const can = useCan();
  const { data, query, change } = useImpact();
  const opts = { invalidate: [IMPACT_KEY] };
  const syncMonth = useAction(() => api.post<{ notices: Notice[] }>("/api/v1/impact/sync", { scope: "month", month: data?.current.month }), opts);
  const syncYear = useAction(() => api.post<{ notices: Notice[] }>("/api/v1/impact/sync", { scope: "year", year: data?.current.year }), opts);
  const ga4 = data?.meta.ga4.available ?? false;
  const facebook = data?.meta.facebook.available ?? false;
  return (
    <>
      <PageHeader title="Visibilité & Impact" description={data?.period.label}
        actions={<>
          <Can><Button variant="default" component={AppLink} href="/impact/manual">Saisie manuelle</Button></Can>
          {can.instanceAdmin && <Button variant="default" component={AppLink} href="/impact/factors">Facteurs d'impact</Button>}
          <Button variant="default" component={AppLink} href={`/impact/report${query}`}>Rapport imprimable</Button>
          {data && <Button variant="default" component="a" href={data.meta.export_url}>Exporter (XLSX)</Button>}
        </>} />
      <PeriodFilter view={data} onChange={change} />
      <Can><Group gap="xs" mb="md">
        <Tooltip label="GA4 et Facebook indisponibles" disabled={ga4 || facebook}>
          <Button size="compact-md" variant="default" disabled={!ga4 && !facebook} loading={syncMonth.isPending}
            onClick={() => syncMonth.mutate()}>Synchroniser le mois</Button>
        </Tooltip>
        <Tooltip label="GA4 indisponible" disabled={ga4}>
          <Button size="compact-md" disabled={!ga4} loading={syncYear.isPending}
            onClick={() => syncYear.mutate()}>Synchroniser l'année {data?.current.year} (GA4)</Button>
        </Tooltip>
      </Group></Can>
      <Group gap="md" mb="md">
        {data?.sources.map((s) => (
          <Group key={s.source} gap={6}>
            <StatusBadge tone={s.status === "ok" ? "ok" : "neutral"}>{s.label}</StatusBadge>
            <Text size="xs" c="dimmed">{s.status === "ok" ? `mise à jour ${formatDate(s.fresh_at)}` : "en attente"}</Text>
          </Group>
        ))}
      </Group>
      <SimpleGrid cols={{ base: 2, md: 4 }} mb="lg">
        {data?.highlights.map((h) => (
          <Paper key={h.key} p="md" ta="center" style={{ opacity: h.available ? 1 : 0.55 }}>
            <Text size="xl" aria-hidden>{h.icon}</Text>
            <Text fw={700} size="xl" className="lv-num">{h.formatted}</Text>
            <Text size="sm" c="dimmed">{h.label}</Text>
          </Paper>
        ))}
      </SimpleGrid>
      {data?.sections.map((s) => (
        <div key={s.key}>
          <Title order={3} mt="lg" mb="xs">{s.label}</Title>
          {s.kpis.length
            ? <SimpleGrid cols={{ base: 1, md: 2, xl: 3 }}>{s.kpis.map((k) => <KpiCard key={k.key} kpi={k} />)}</SimpleGrid>
            : <Text size="sm" c="dimmed">Aucun indicateur.</Text>}
        </div>
      ))}
    </>
  );
}

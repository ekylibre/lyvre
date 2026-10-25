// Tableau de bord : alerte de trésorerie négative prévue, indicateurs de l'exercice, suivi du budget
// (s'il y en a un), résultat, ventes et
// solde bancaire mensuels, dernières écritures. Graphiques Mantine Charts (FM6), couleurs de la charte.
import type { ReactNode } from "react";
import { Alert, Anchor, Center, Group, Loader, Paper, Select, SimpleGrid, Stack, Table, Text, Title } from "@mantine/core";
import { AreaChart, BarChart, CompositeChart } from "@mantine/charts";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useBookkeeping, useCan, useIntegration } from "../../api/session";
import { useUrlParams } from "../../components/FilterBar";
import { MoneyText } from "../../components/Money";
import { PageHeader } from "../../components/PageHeader";
import { EUROS_Y_AXIS, formatDate, formatEuros } from "../../lib/format";
import { AppLink } from "../../app/navigation";
import type { ReportMeta } from "../reports/ReportFrame";
import { RateBar, useTracking } from "../budget/BudgetTrackingPage";
import { NegativeAlert, useForecast } from "../cash-forecast/CashForecastPage";
import { IntegrationProposals } from "../integrations/IntegrationProposals";

interface Month { month: string; produits: number; charges: number; net: number; ventes: number; pos: number; factures: number; solde: number }
interface Dashboard {
  stats: { total_sales_cents: number; new_members: number | null; resultat_courant_cents: number; total_payouts_cents: number } | null;
  /** Module Ventes : CA facturé HT de l'exercice, encours clients, factures échues. */
  sales?: { revenue_cents: number; receivable_cents: number; overdue_count: number; overdue_cents: number; has_sales: boolean };
  /** Écritures en brouillard des exercices ouverts ; `old` : plus de 3 mois (lot F1). */
  drafts?: { drafts: number; old: number };
  monthly: Month[];
  recent_entries: { id: number; url: string; reference: string | null; date: string; description: string; total_cents: number }[];
  meta: ReportMeta;
}

const euros = (value: number) => formatEuros(Math.round(value * 100));

function StatTile({ label, children, meta }: { label: string; children: ReactNode; meta?: string }) {
  return (
    <Paper p="md">
      <Text size="sm" c="dimmed">{label}</Text>
      <Text className="lv-num" fz={28} lh="34px" fw={500}>{children}</Text>
      {meta && <Text size="sm" c="dimmed">{meta}</Text>}
    </Paper>
  );
}

function ChartCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Paper p="md">
      <Title order={2} size="h3" mb="sm">{title}</Title>
      {children}
    </Paper>
  );
}

function BudgetCard({ fyId }: { fyId: number }) {
  const { data } = useTracking(String(fyId));
  if (!data || data.rows.every((r) => r.unbudgeted)) return null;
  const parts = [{ kind: "expense", title: "Charges" }, { kind: "income", title: "Produits" }] as const;
  return (
    <Paper p="md">
      <Group justify="space-between" mb="xs">
        <Title order={2} size="h3">Budget au {formatDate(data.as_of)}</Title>
        <Anchor component={AppLink} href={`/budget/tracking?fiscal_year_id=${fyId}`} size="sm">Suivi détaillé</Anchor>
      </Group>
      <SimpleGrid cols={{ base: 1, sm: 2 }}>
        {parts.map((p) => {
          const s = data.summary[p.kind];
          const gap = s.actual_cents - s.planned_to_date_cents;
          const rate = s.planned_to_date_cents ? Math.round((s.actual_cents / s.planned_to_date_cents) * 1000) / 10 : null;
          return (
            <Stack key={p.kind} gap={4}>
              <Text size="sm" c="dimmed">{p.title} réalisées / prévues à date</Text>
              <Text className="lv-num" fw={500}><MoneyText cents={s.actual_cents} /> / <MoneyText cents={s.planned_to_date_cents} /></Text>
              <RateBar row={{ kind: p.kind, rate, gap_cents: gap }} />
            </Stack>
          );
        })}
      </SimpleGrid>
    </Paper>
  );
}

function ForecastAlert() {
  const { data } = useForecast();
  return data ? <NegativeAlert forecast={data} /> : null;
}

export default function DashboardPage() {
  const [params, setParams] = useUrlParams({ fy_id: "" });
  const can = useCan();
  const bookkeeping = useBookkeeping();
  const { data, isPending } = useQuery({
    queryKey: ["dashboard", params.fy_id], placeholderData: (prev) => prev,
    queryFn: () => api.get<Dashboard>(`/api/v1/dashboard${params.fy_id ? `?fy_id=${params.fy_id}` : ""}`),
  });
  const fy = data?.meta.fiscal_year;
  const stats = data?.stats;
  // Tuiles et séries qui ne viennent que d'une intégration : masquées si elle est désactivée.
  const odoo = useIntegration("odoo");
  const stancer = useIntegration("stancer");
  return (
    <>
      <PageHeader title="Tableau de bord" description={fy ? `Exercice ${fy.label}` : undefined}
        actions={<Select aria-label="Exercice" data={data?.meta.fiscal_years ?? []} value={params.fy_id || (fy ? String(fy.id) : null)}
          w={180} allowDeselect={false} onChange={(v) => setParams({ fy_id: v ?? "" })} />} />
      <IntegrationProposals />
      {isPending ? <Center h={300}><Loader /></Center> : !stats ? (
        <Alert color="paille">Aucun exercice : <Anchor component={AppLink} href="/fiscal-years/new">créer un exercice</Anchor> pour commencer.</Alert>
      ) : (
        <Stack gap="lg">
          <ForecastAlert />
          {!!data.drafts?.old && can.write && bookkeeping === "double" && (
            <Alert color="paille" variant="light">{data.drafts.old} écriture(s) en brouillard depuis plus de 3 mois :{" "}
              <Anchor component={AppLink} href="/entries/?state=draft">validez-les</Anchor> une fois vérifiées.</Alert>
          )}
          <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }}>
            {odoo && <StatTile label="Ventes de l'exercice" meta="Caisse et factures Odoo"><MoneyText cents={stats.total_sales_cents} /></StatTile>}
            {stats.new_members !== null && <StatTile label="Adhésions" meta="Adhérents de l'exercice">{stats.new_members}</StatTile>}
            <StatTile label="Résultat courant" meta="Exploitation et financier">
              <MoneyText cents={stats.resultat_courant_cents} c={stats.resultat_courant_cents >= 0 ? "var(--lv-lichen)" : "var(--lv-brique)"} />
            </StatTile>
            {stancer && <StatTile label="Versements Stancer" meta="Reçus sur l'exercice"><MoneyText cents={stats.total_payouts_cents} /></StatTile>}
          </SimpleGrid>
          {data.sales?.has_sales && (
            <SimpleGrid cols={{ base: 1, sm: 3 }}>
              <StatTile label="Facturé" meta="Factures émises de l'exercice, HT, avoirs déduits"><MoneyText cents={data.sales.revenue_cents} /></StatTile>
              <StatTile label="Encours clients" meta="Restant dû des factures émises">
                <Anchor component={AppLink} href="/sales/" underline="never" c="inherit"><MoneyText cents={data.sales.receivable_cents} /></Anchor></StatTile>
              <StatTile label="Factures échues" meta={`${data.sales.overdue_count} facture(s) à relancer`}>
                <Anchor component={AppLink} href="/sales/?overdue=1" underline="never" c="inherit">
                  <MoneyText cents={data.sales.overdue_cents} c={data.sales.overdue_cents ? "var(--lv-brique)" : undefined} /></Anchor></StatTile>
            </SimpleGrid>
          )}
          {fy && <BudgetCard fyId={fy.id} />}
          <ChartCard title="Résultat mensuel">
            <CompositeChart h={300} data={data.monthly} yAxisProps={EUROS_Y_AXIS} dataKey="month" valueFormatter={euros} withLegend
              series={[
                { name: "produits", label: "Produits", color: "lichen.7", type: "bar" },
                { name: "charges", label: "Charges", color: "ardoise.5", type: "bar" },
                { name: "net", label: "Net", color: "paille.6", type: "line" },
              ]} />
          </ChartCard>
          <SimpleGrid cols={{ base: 1, lg: 2 }}>
            <ChartCard title="Ventes mensuelles">
              <BarChart h={260} data={data.monthly} yAxisProps={EUROS_Y_AXIS} dataKey="month" valueFormatter={euros} withLegend
                series={[
                  { name: "ventes", label: "Ventes (70x)", color: "lichen.7" },
                  ...(odoo ? [{ name: "pos", label: "Caisse", color: "ardoise.5" },
                    { name: "factures", label: "Factures Odoo", color: "paille.6" }] : []),
                ]} />
            </ChartCard>
            <ChartCard title="Solde bancaire (fin de mois)">
              <AreaChart h={260} data={data.monthly} yAxisProps={EUROS_Y_AXIS} dataKey="month" valueFormatter={euros} curveType="monotone"
                series={[{ name: "solde", label: "Solde", color: "lichen.7" }]} />
            </ChartCard>
          </SimpleGrid>
          <Paper p={0}>
            <Group justify="space-between" p="md" pb="xs"><Title order={2} size="h3">Dernières écritures</Title>
              <Anchor component={AppLink} href="/entries/">Toutes les écritures</Anchor></Group>
            <Table verticalSpacing="xs">
              <Table.Tbody>
                {data.recent_entries.map((e) => (
                  <Table.Tr key={e.id}>
                    <Table.Td className="lv-num" w={110}>{formatDate(e.date)}</Table.Td>
                    <Table.Td w={140}><Anchor component={AppLink} href={e.url} className="lv-num">{e.reference ?? `#${e.id}`}</Anchor></Table.Td>
                    <Table.Td><Text size="sm" lineClamp={1}>{e.description}</Text></Table.Td>
                    <Table.Td ta="right"><MoneyText cents={e.total_cents} /></Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Paper>
        </Stack>
      )}
    </>
  );
}

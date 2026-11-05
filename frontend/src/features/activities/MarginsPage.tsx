// Rapports › Marges par activité (lot AG8.d, claudedocs/design_analytique_agricole.md § 7, AGD25) : production nette
// des achats d'animaux, charges opérationnelles (spécifiques végétaux et animaux du RICA), marge brute par unité,
// structure directe et résultat, par activité × campagne et par atelier ; part non affectée.
import { Fragment } from "react";
import { Alert, Anchor, Badge, Button, Center, Group, Loader, Paper, Select, Table, Text } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { ApiError, api } from "../../api/client";
import { AppLink } from "../../app/navigation";
import { FilterBar, useUrlParams } from "../../components/FilterBar";
import { MoneyText } from "../../components/Money";
import { PageHeader } from "../../components/PageHeader";
import type { FiscalYear } from "../fiscal-years/FiscalYearsPage";

type Summary = { classes: Record<string, number>; production_cents: number; operational_cents: number; gross_margin_cents: number;
  structure_cents: number; result_cents: number; auxiliary_cents?: number; result_after_cents?: number };
export interface MarginRow extends Summary {
  activity_id: number; activity: string; nature: string; workshop_id: number; workshop: string; campaign_year: number;
  unit_label: string; measure: string | null; gross_margin_per_unit_cents: number | null;
}
interface WorkshopRow { workshop_id: number; workshop: string; measure: string | null; unit_label: string | null;
  production_cents: number; operational_cents: number; gross_margin_cents: number; gross_margin_per_unit_cents: number | null;
  structure_cents: number; result_cents: number; auxiliary_cents?: number; result_after_cents?: number }
export interface Reconciliation { accounting_result_cents: number; activities_cents: number; unallocated_cents: number;
  excluded_cents: number; stock_lines_cents: number; computed_stock_cents: number; method_gap_cents: number; note: string }
export interface MarginsView {
  fiscal_year: { id: number; label: string; status: string }; campaign: number | null; campaigns: number[];
  productions: MarginRow[]; workshops: WorkshopRow[]; unallocated: Summary; deferred_cents: number; warnings: string[];
  classes: { key: string; label: string; side: string }[];
  reconciliation?: Reconciliation | null; frozen?: boolean; frozen_at?: string | null;
}

const money = (v: number | null) => (v === null ? "—" : <MoneyText cents={v} />);
const fr = (m: string | null) => (m ? m.replace(".", ",") : "");

export default function MarginsPage() {
  const { data: years } = useQuery({ queryKey: ["fiscal-years"], queryFn: () => api.get<{ items: FiscalYear[] }>("/api/v1/fiscal-years") });
  const [params, setParams] = useUrlParams({ fiscal_year: "", campaign: "" });
  const fyId = Number(params.fiscal_year) || years?.items.find((y) => y.status === "open")?.id || years?.items[0]?.id;
  const query = params.campaign ? `?campaign=${params.campaign}` : "";
  const { data, error } = useQuery({ queryKey: ["analytic", "margins", fyId, params.campaign], enabled: !!fyId,
    queryFn: () => api.get<{ item: MarginsView }>(`/api/v1/fiscal-years/${fyId}/activity-margins${query}`) });
  if (error) return <Alert color="paille">{error instanceof ApiError ? error.message : "Indisponible."}</Alert>;
  if (!years || !data) return <Center h={300}><Loader /></Center>;
  const v = data.item;
  const cells = (s: Summary | WorkshopRow, perUnit: number | null, strong = false) => (
    <>
      <Table.Td ta="right">{money(s.production_cents)}</Table.Td>
      <Table.Td ta="right">{money(s.operational_cents)}</Table.Td>
      <Table.Td ta="right"><Text span fw={strong ? 700 : 600}>{money(s.gross_margin_cents)}</Text></Table.Td>
      <Table.Td ta="right">{money(perUnit)}</Table.Td>
      <Table.Td ta="right">{money(s.structure_cents)}</Table.Td>
      <Table.Td ta="right">{s.auxiliary_cents ? <MoneyText cents={s.auxiliary_cents} plus /> : "—"}</Table.Td>
      <Table.Td ta="right"><Text span fw={strong ? 700 : 500}>{money(s.result_after_cents ?? s.result_cents)}</Text></Table.Td>
    </>);
  return (
    <>
      <PageHeader title="Marges par activité" description="Production nette des achats d'animaux, charges opérationnelles (RICA), marge brute par hectare ou par tête, charges de structure directes, par activité et par atelier."
        actions={<Group gap="xs">
          <Button variant="default" component="a" href={`/fiscal-years/${fyId}/activity-margins.xlsx${query}`}>XLSX</Button>
          <Button variant="default" component="a" href={`/fiscal-years/${fyId}/activity-margins.pdf${query}`} target="_blank">PDF</Button></Group>} />
      <FilterBar>
        <Select aria-label="Exercice" w={180} allowDeselect={false} value={fyId ? String(fyId) : null}
          data={years.items.map((y) => ({ value: String(y.id), label: `Exercice ${y.label}` }))} onChange={(x) => setParams({ fiscal_year: x ?? "", campaign: "" })} />
        <Select aria-label="Campagne" w={180} clearable placeholder="Toutes les campagnes" value={params.campaign || null}
          data={v.campaigns.map((c) => ({ value: String(c), label: `Campagne ${c}` }))} onChange={(x) => setParams({ campaign: x ?? "" })} />
      </FilterBar>
      {v.warnings.map((w) => <Alert key={w} color="paille" mb="xs">{w}</Alert>)}
      {v.frozen && <Badge color="gray" mb="xs">Figé à la clôture{v.frozen_at ? ` (${new Date(v.frozen_at).toLocaleDateString("fr-FR")})` : ""}</Badge>}
      {v.productions.length === 0 ? <Text c="dimmed">Aucune ligne affectée à une activité : <Anchor component={AppLink} href="/analytic/">ventilation analytique</Anchor>.</Text> : (
        <Table>
          <Table.Thead><Table.Tr><Table.Th>Atelier / activité</Table.Th><Table.Th>Campagne</Table.Th><Table.Th ta="right">Mesure</Table.Th>
            <Table.Th ta="right">Production</Table.Th><Table.Th ta="right">Charges opérationnelles</Table.Th><Table.Th ta="right">Marge brute</Table.Th>
            <Table.Th ta="right">MB / unité</Table.Th><Table.Th ta="right">Structure directe</Table.Th><Table.Th ta="right">Auxiliaires</Table.Th><Table.Th ta="right">Résultat</Table.Th></Table.Tr></Table.Thead>
          <Table.Tbody>
            {v.workshops.map((w) => (
              <Fragment key={w.workshop_id}>
                <Table.Tr bg="var(--mantine-color-gray-0)"><Table.Td fw={700}>{w.workshop}</Table.Td><Table.Td />
                  <Table.Td ta="right">{w.measure ? `${fr(w.measure)} ${w.unit_label}` : ""}</Table.Td>{cells(w, w.gross_margin_per_unit_cents, true)}</Table.Tr>
                {v.productions.filter((p) => p.workshop_id === w.workshop_id).map((p) => (
                  <Table.Tr key={`${p.activity_id}-${p.campaign_year}`}>
                    <Table.Td pl="lg">{p.activity}{p.nature !== "main" && <Text span size="xs" c="dimmed"> · {p.nature === "auxiliary" ? "auxiliaire" : "autonome"}</Text>}</Table.Td>
                    <Table.Td>{p.campaign_year}</Table.Td>
                    <Table.Td ta="right">{p.measure ? `${fr(p.measure)} ${p.unit_label}` : "—"}</Table.Td>
                    {cells(p, p.gross_margin_per_unit_cents)}
                  </Table.Tr>))}
              </Fragment>))}
            <Table.Tr><Table.Td fw={600}>Non affecté</Table.Td><Table.Td /><Table.Td />{cells(v.unallocated, null)}</Table.Tr>
          </Table.Tbody>
        </Table>)}
      {v.reconciliation && (
        <Paper withBorder p="sm" mt="md" maw={620}>
          <Text fw={600} size="sm" mb={4}>Rapprochement avec le résultat comptable</Text>
          <Table>
            <Table.Tbody>
              {([["Résultat des activités (après auxiliaires)", v.reconciliation.activities_cents], ["Non affecté", v.reconciliation.unallocated_cents],
                ["Hors analytique (exceptionnel, impôt, écritures de clôture)", v.reconciliation.excluded_cents],
                ["Écart de méthode (stocks et amortissements recalculés)", v.reconciliation.method_gap_cents]] as [string, number][]).map(([label, cents]) => (
                <Table.Tr key={label}><Table.Td><Text size="sm">{label}</Text></Table.Td><Table.Td ta="right"><MoneyText cents={cents} /></Table.Td></Table.Tr>))}
              <Table.Tr><Table.Td fw={700}>Résultat comptable</Table.Td><Table.Td ta="right"><MoneyText cents={v.reconciliation.accounting_result_cents} fw={700} /></Table.Td></Table.Tr>
            </Table.Tbody>
          </Table>
          <Text size="xs" c="dimmed">{v.reconciliation.note}</Text>
        </Paper>)}
      <Text size="xs" c="dimmed" mt="sm">Variations de stock : lignes d'inventaire rattachées à l'activité ; amortissements : fiches d'immobilisation rattachées.
        Charges opérationnelles : charges spécifiques végétaux et animaux du RICA (engrais, semences, phytos, eau d'irrigation, aliments, vétérinaire, reproduction, locations d'animaux, travaux).</Text>
    </>
  );
}

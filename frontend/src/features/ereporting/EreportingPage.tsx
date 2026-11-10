// TVA › E-reporting B2C (lot AG10.e) : ventes directes sans facture (catégories « vente directe », journal de
// caisse) agrégées par jour, catégorie (TLB1 biens, TPS1 services) et taux ; export JSON au format de l'API
// SUPER PDP (`b2c_transactions`) et tableur ; jours non exportés signalés. Lyvre ne transmet pas.
import { useState } from "react";
import { Alert, Button, Checkbox, Group, Paper, SimpleGrid, Stack, Table, Text, TextInput, Title } from "@mantine/core";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError, postBlob, query } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { Can } from "../../components/Can";
import { MoneyText } from "../../components/Money";
import { PageHeader } from "../../components/PageHeader";
import { StatusBadge } from "../../components/StatusBadge";
import { formatDate, formatDateTime } from "../../lib/format";

const KEY = ["ereporting"] as const;

interface Day {
  date: string; category: "TLB1" | "TPS1"; category_label: string; base_cents: number; tax_cents: number; exported: boolean;
  subtotals: { rate_bp: number; base_cents: number; tax_cents: number }[];
}

export interface EreportingData {
  start: string; end: string; last_entry_date?: string | null; days: Day[]; base_cents: number; tax_cents: number; pending_days: string[]; warnings: string[];
  categories: { id: number; label: string; account: string; direct_sale: boolean }[];
  exports: { id: number; start: string; end: string; transactions: number; base_cents: number; tax_cents: number; exported_at: string }[];
}

const rate = (bp: number) => `${(bp / 100).toLocaleString("fr-FR")} %`;

/** Catégories de recette comptées comme ventes directes à des particuliers. */
export function DirectSaleCategories({ categories }: { categories: EreportingData["categories"] }) {
  const [ids, setIds] = useState<string[]>(categories.filter((c) => c.direct_sale).map((c) => String(c.id)));
  const save = useAction(() => api.put<{ notices: Notice[] }>("/api/v1/ereporting/categories", { ids: ids.map(Number) }),
    { invalidate: [KEY] });
  return (
    <Paper p="md">
      <Title order={3} mb={4}>Catégories de vente directe</Title>
      {categories.length === 0 ? (
        <Text size="sm" c="dimmed">Pas de catégorie de recette (elles servent à la comptabilité simplifiée) : en partie double,
          les ventes directes sont celles du journal de caisse (CA), comptes 70 ; les ventes facturées partent comme factures
          (note B2C).</Text>) : (<>
      <Text size="sm" c="dimmed" mb="xs">Recettes encaissées sans facture auprès de particuliers. Les ventes du journal de caisse
        (comptes 70) sont toujours comptées ; les ventes facturées partent comme factures (note B2C).</Text>
      <Checkbox.Group value={ids} onChange={setIds}>
        <SimpleGrid cols={{ base: 1, md: 3 }} spacing={4}>{categories.map((c) =>
          <Checkbox key={c.id} value={String(c.id)} label={`${c.label} (${c.account})`} />)}</SimpleGrid>
      </Checkbox.Group>
      <Can><Button mt="sm" size="compact-sm" loading={save.isPending} onClick={() => save.mutate()}>Enregistrer</Button></Can>
      </>)}
    </Paper>
  );
}

/** Dernier mois terminé : l'export se fait mois par mois, une fois le mois clos. */
export function lastMonth(today = new Date()): { start: string; end: string } {
  const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  return { start: iso(new Date(today.getFullYear(), today.getMonth() - 1, 1)), end: iso(new Date(today.getFullYear(), today.getMonth(), 0)) };
}

export default function EreportingPage() {
  const client = useQueryClient();
  const params = new URLSearchParams(window.location.search);
  const [period, setPeriod] = useState({ start: params.get("start") ?? lastMonth().start, end: params.get("end") ?? lastMonth().end });
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const { data } = useQuery({ queryKey: [...KEY, period.start, period.end],
    queryFn: () => api.get<EreportingData>(`/api/v1/ereporting${query(period)}`) });
  const exportJson = async () => {
    setBusy(true); setError(null);
    try {
      const blob = await postBlob("/api/v1/ereporting/export", period);
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = `ereporting-b2c-${period.start}-${period.end}.json`;
      link.click();
      URL.revokeObjectURL(link.href);
      void client.invalidateQueries({ queryKey: KEY });
    } catch (e) { setError(e); } finally { setBusy(false); }
  };
  return (
    <>
      <PageHeader title="E-reporting des ventes directes"
        description="Ventes à des particuliers sans facture, par jour, catégorie et taux, à transmettre par votre plateforme agréée (format de l'API SUPER PDP). La plateforme fixe le calendrier selon votre régime de TVA." />
      <Stack>
        <Group align="flex-end">
          <TextInput type="date" label="Du" value={period.start} onChange={(e) => setPeriod({ ...period, start: e.currentTarget.value })} />
          <TextInput type="date" label="Au" value={period.end} onChange={(e) => setPeriod({ ...period, end: e.currentTarget.value })} />
          <Can><Button loading={busy} disabled={!data?.days.length} onClick={() => void exportJson()}>Exporter (JSON)</Button></Can>
          <Button variant="default" component="a" href={`/api/v1/ereporting/csv${query(period)}`}>Tableur</Button>
        </Group>
        {error != null && <Alert color="brique">{error instanceof ApiError ? error.message : "Échec."}</Alert>}
        {data && <>
          {data.warnings.map((w) => <Alert key={w} color="paille">{w}</Alert>)}
          {data.last_entry_date && data.last_entry_date < period.start && (
            <Alert color="ardoise">Aucune écriture sur la période : la dernière écriture date du {formatDate(data.last_entry_date)}.</Alert>)}
          {data.pending_days.length > 0 && <Alert color="ardoise">{data.pending_days.length} jour(s) non exporté(s) sur la période.</Alert>}
          <SimpleGrid cols={{ base: 2, md: 3 }}>
            <Paper p="sm"><Text size="sm" c="dimmed">Base HT</Text><MoneyText cents={data.base_cents} fw={700} /></Paper>
            <Paper p="sm"><Text size="sm" c="dimmed">TVA</Text><MoneyText cents={data.tax_cents} fw={700} /></Paper>
            <Paper p="sm"><Text size="sm" c="dimmed">Transactions</Text><Text fw={700}>{data.days.length}</Text></Paper>
          </SimpleGrid>
          <Paper p={0}>
            <Table>
              <Table.Thead><Table.Tr><Table.Th>Date</Table.Th><Table.Th>Catégorie</Table.Th><Table.Th>Taux</Table.Th>
                <Table.Th ta="right">Base HT</Table.Th><Table.Th ta="right">TVA</Table.Th><Table.Th>Export</Table.Th></Table.Tr></Table.Thead>
              <Table.Tbody>
                {data.days.length === 0 && <Table.Tr><Table.Td colSpan={6}><Text size="sm" c="dimmed">Aucune vente directe sur la période.</Text></Table.Td></Table.Tr>}
                {data.days.map((d) => (
                  <Table.Tr key={d.date + d.category}>
                    <Table.Td className="lv-num">{formatDate(d.date)}</Table.Td>
                    <Table.Td>{d.category} <Text span size="xs" c="dimmed">{d.category_label}</Text></Table.Td>
                    <Table.Td className="lv-num">{d.subtotals.map((s) => rate(s.rate_bp)).join(", ")}</Table.Td>
                    <Table.Td ta="right"><MoneyText cents={d.base_cents} size="sm" /></Table.Td>
                    <Table.Td ta="right"><MoneyText cents={d.tax_cents} size="sm" /></Table.Td>
                    <Table.Td><StatusBadge tone={d.exported ? "ok" : "todo"}>{d.exported ? "exporté" : "à exporter"}</StatusBadge></Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Paper>
          <DirectSaleCategories key={data.categories.map((c) => `${c.id}${c.direct_sale}`).join()} categories={data.categories} />
          {data.exports.length > 0 && <Paper p="md">
            <Title order={3} mb="xs">Exports</Title>
            {data.exports.map((e) => <Text key={e.id} size="sm">{formatDateTime(e.exported_at)} — {formatDate(e.start)} au {formatDate(e.end)} :{" "}
              {e.transactions} transaction(s), <MoneyText cents={e.base_cents} size="sm" /> HT</Text>)}
          </Paper>}
        </>}
      </Stack>
    </>
  );
}

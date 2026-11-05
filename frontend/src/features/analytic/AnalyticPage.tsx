// Compta › Ventilation analytique (lot AG8.b, claudedocs/design_analytique_agricole.md § 5, AGD25) : lignes de charges
// et de produits non affectées, groupées par compte ; affectation à une activité ou à une clé de répartition, sans
// toucher les écritures ; règles de compte (suggérées depuis les libellés) ; taux de couverture.
import { useState } from "react";
import { Alert, Badge, Button, Center, Checkbox, Group, Loader, NumberInput, Paper, Select, SimpleGrid, Switch, Table, Text, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { ApiError, api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { useCan } from "../../api/session";
import { FilterBar, useUrlParams } from "../../components/FilterBar";
import { MoneyText } from "../../components/Money";
import { PageHeader } from "../../components/PageHeader";
import type { FiscalYear } from "../fiscal-years/FiscalYearsPage";

type Target = { kind: "activity" | "key"; id: number; label: string; share_bp?: number; campaign_year?: number | null };
type TargetOption = { value: string; label: string; group: string };
interface Line { id: number; date: string; reference: string | null; label: string; account: string; amount_cents: number;
  origin: string | null; origin_label: string | null; targets: Target[]; share_bp: number }
export interface UnallocatedView {
  fiscal_year: { id: number; label: string };
  coverage: Record<"charges" | "products", { total_cents: number; allocated_cents: number; ratio_bp: number | null }>;
  groups: { account: string; label: string; count: number; amount_cents: number; partial: number }[];
  lines: Line[];
  suggestions: { account_prefix: string; account_label: string; target: Target }[];
}

const pct = (bp: number | null) => (bp === null ? "—" : `${(bp / 100).toLocaleString("fr-FR", { maximumFractionDigits: 1 })} %`);
const toTarget = (value: string) => { const [kind, id] = value.split(":"); return kind === "key" ? { key_id: Number(id) } : { activity_id: Number(id) }; };

export default function AnalyticPage() {
  const can = useCan();
  const { data: years } = useQuery({ queryKey: ["fiscal-years"], queryFn: () => api.get<{ items: FiscalYear[] }>("/api/v1/fiscal-years") });
  const [params, setParams] = useUrlParams({ fiscal_year: "", account: "" });
  const fyId = Number(params.fiscal_year) || years?.items.find((y) => y.status === "open")?.id || years?.items[0]?.id;
  const [showAll, setShowAll] = useState(false);
  const url = `/api/v1/fiscal-years/${fyId}/analytic`;
  const { data, error } = useQuery({ queryKey: ["analytic", fyId, params.account, showAll], enabled: !!fyId,
    queryFn: () => api.get<{ item: UnallocatedView; meta: { targets: TargetOption[] } }>(
      `${url}/unallocated?${new URLSearchParams({ ...(params.account ? { account: params.account } : {}), ...(showAll ? { all: "1" } : {}) })}`) });
  const [selected, setSelected] = useState<number[]>([]);
  const [targets, setTargets] = useState<{ value: string | null; share: number }[]>([{ value: null, share: 100 }]);
  const [campaign, setCampaign] = useState<number | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const opts = { invalidate: [["analytic"]] };
  const allocate = useAction((b: object) => api.post<{ notices: Notice[] }>(`${url}/allocations`, b), opts);
  const clear = useAction((ids: number[]) => api.post<{ notices: Notice[] }>(`${url}/allocations/clear`, { line_ids: ids }), opts);
  const rule = useAction((b: object) => api.post<{ notices: Notice[] }>("/api/v1/analytic-rules", b), opts);
  if (error) return <Alert color="paille">{error instanceof ApiError ? error.message : "Indisponible."}</Alert>;
  if (!years || !data) return <Center h={300}><Loader /></Center>;
  const v = data.item;
  const run = (x: Promise<unknown>, after?: () => void) => { setMessage(null); x.then(after, (e) => setMessage(e instanceof ApiError ? e.message : "Action impossible.")); };
  const valid = targets.every((t) => t.value) && targets.reduce((s, t) => s + t.share, 0) <= 100;
  const body = () => ({ targets: targets.map((t) => ({ ...toTarget(t.value!), share_bp: Math.round(t.share * 100) })), ...(campaign ? { campaign_year: campaign } : {}) });
  return (
    <>
      <PageHeader title="Ventilation analytique" description="Affectation des charges et des produits aux activités, directement ou par une clé de répartition (surface, effectif, pourcentages), sans modifier les écritures." />
      <FilterBar>
        <Select aria-label="Exercice" w={180} allowDeselect={false} value={fyId ? String(fyId) : null}
          data={years.items.map((y) => ({ value: String(y.id), label: `Exercice ${y.label}` }))} onChange={(x) => setParams({ fiscal_year: x ?? "", account: "" })} />
        <Switch label="Voir aussi les lignes affectées" checked={showAll} onChange={(e) => setShowAll(e.currentTarget.checked)} />
      </FilterBar>
      <SimpleGrid cols={{ base: 1, sm: 2 }} mb="md">
        {(["charges", "products"] as const).map((side) => (
          <Paper key={side} withBorder p="sm"><Text size="xs" c="dimmed">{side === "charges" ? "Charges affectées" : "Produits affectés"}</Text>
            <Text fw={600}>{pct(v.coverage[side].ratio_bp)} <Text span size="sm" c="dimmed">(<MoneyText cents={v.coverage[side].allocated_cents} /> sur <MoneyText cents={v.coverage[side].total_cents} />)</Text></Text></Paper>))}
      </SimpleGrid>
      {v.suggestions.length > 0 && (
        <Paper withBorder p="sm" mb="md">
          <Text fw={600} size="sm" mb={4}>Règles de compte suggérées</Text>
          {v.suggestions.map((s) => (
            <Group key={s.account_prefix} gap="xs"><Text size="sm">{s.account_prefix} {s.account_label} → {s.target.label}</Text>
              {can.write && <Button size="compact-xs" variant="light" onClick={() => run(rule.mutateAsync({ account_prefix: s.account_prefix, activity_id: s.target.id }))}>Créer la règle</Button>}</Group>))}
        </Paper>)}
      {message && <Alert color="brique" mb="sm">{message}</Alert>}
      <SimpleGrid cols={{ base: 1, md: 2 }}>
        <Paper withBorder p="sm">
          <Title order={5} mb="xs">{showAll ? "Comptes" : "Comptes à ventiler"}</Title>
          {v.groups.length === 0 ? <Text size="sm" c="dimmed">Tout est affecté.</Text> : (
            <Table highlightOnHover>
              <Table.Tbody>
                {v.groups.map((g) => (
                  <Table.Tr key={g.account} style={{ cursor: "pointer" }} bg={params.account === g.account ? "var(--mantine-color-gray-1)" : undefined}
                    onClick={() => { setSelected([]); setParams({ account: g.account }); }}>
                    <Table.Td><Text size="sm">{g.account} {g.label}</Text>{g.partial > 0 && <Badge size="xs" color="paille">{g.partial} partielle(s)</Badge>}</Table.Td>
                    <Table.Td><Text size="xs" c="dimmed">{g.count} ligne(s)</Text></Table.Td>
                    <Table.Td ta="right"><MoneyText cents={g.amount_cents} /></Table.Td>
                  </Table.Tr>))}
              </Table.Tbody>
            </Table>)}
        </Paper>
        <Paper withBorder p="sm">
          <Title order={5} mb="xs">{params.account ? `Lignes du compte ${params.account}` : "Choisissez un compte"}</Title>
          {v.lines.length > 0 && (
            <>
              <Table>
                <Table.Thead><Table.Tr><Table.Th><Checkbox aria-label="Tout sélectionner" checked={selected.length === v.lines.length}
                  onChange={(e) => setSelected(e.currentTarget.checked ? v.lines.map((l) => l.id) : [])} /></Table.Th>
                  <Table.Th>Date</Table.Th><Table.Th>Libellé</Table.Th><Table.Th ta="right">Montant</Table.Th><Table.Th>Affectation</Table.Th></Table.Tr></Table.Thead>
                <Table.Tbody>
                  {v.lines.map((l) => (
                    <Table.Tr key={l.id}>
                      <Table.Td><Checkbox aria-label={`Ligne ${l.id}`} checked={selected.includes(l.id)}
                        onChange={(e) => setSelected(e.currentTarget.checked ? [...selected, l.id] : selected.filter((i) => i !== l.id))} /></Table.Td>
                      <Table.Td><Text size="xs">{new Date(l.date).toLocaleDateString("fr-FR")}</Text></Table.Td>
                      <Table.Td><Text size="xs">{l.label}</Text></Table.Td>
                      <Table.Td ta="right"><MoneyText cents={l.amount_cents} /></Table.Td>
                      <Table.Td><Text size="xs">{l.targets.map((t) => `${t.label}${(t.share_bp ?? 10000) < 10000 ? ` ${pct(t.share_bp ?? 0)}` : ""}`).join(" + ") || "—"}</Text>
                        {l.origin_label && <Text size="xs" c="dimmed">{l.origin_label}</Text>}</Table.Td>
                    </Table.Tr>))}
                </Table.Tbody>
              </Table>
              {can.write && (
                <>
                  {targets.map((t, i) => (
                    <Group key={i} gap="xs" mt="xs" align="end">
                      <Select label={i === 0 ? "Activité ou clé" : undefined} w={280} searchable data={data.meta.targets.reduce<{ group: string; items: { value: string; label: string }[] }[]>((acc, o) => {
                        const item = { value: o.value, label: o.label };
                        const g = acc.find((x) => x.group === o.group); if (g) g.items.push(item); else acc.push({ group: o.group, items: [item] }); return acc; }, [])}
                        value={t.value} onChange={(x) => setTargets(targets.map((u, j) => (j === i ? { ...u, value: x } : u)))} />
                      <NumberInput label={i === 0 ? "Part (%)" : undefined} w={90} min={1} max={100} value={t.share}
                        onChange={(x) => setTargets(targets.map((u, j) => (j === i ? { ...u, share: Number(x) || 0 } : u)))} />
                      {targets.length > 1 && <Button size="compact-xs" variant="subtle" onClick={() => setTargets(targets.filter((_u, j) => j !== i))}>Retirer</Button>}
                    </Group>))}
                  <Group gap="xs" mt="xs">
                    <Button size="compact-sm" variant="subtle" onClick={() => setTargets([...targets, { value: null, share: 0 }])}>+ Cible</Button>
                    <NumberInput aria-label="Campagne" placeholder="campagne (déduite)" w={170} min={2000} max={2100} value={campaign ?? ""} onChange={(x) => setCampaign(typeof x === "number" ? x : null)} />
                    <Button disabled={!selected.length || !valid} loading={allocate.isPending}
                      onClick={() => run(allocate.mutateAsync({ line_ids: selected, ...body() }), () => setSelected([]))}>Affecter {selected.length || ""} ligne(s)</Button>
                    <Button variant="default" disabled={!selected.length} onClick={() => run(clear.mutateAsync(selected), () => setSelected([]))}>Retirer la ventilation</Button>
                    {params.account && targets.length === 1 && targets[0].value && (
                      <Button variant="subtle" onClick={() => run(rule.mutateAsync({ account_prefix: params.account, ...toTarget(targets[0].value!) }))}>Règle pour tout le compte {params.account}</Button>)}
                  </Group>
                </>)}
            </>)}
        </Paper>
      </SimpleGrid>
    </>
  );
}

// Compta › Inventaire de clôture (lot AG4.a, claudedocs/design_inventaire_agricole.md §§ 3, 4 et 9.4) : lignes de
// stock d'un exercice par groupe (approvisionnements, animaux, végétaux en terre, en-cours et produits), méthodes
// (coût réel, standard, prix de détail moins décote, forfaitaire), décotes par catégorie, stocks initiaux à recompter,
// feuilles de comptage, reprise de l'exercice précédent, import d'un tableur, barèmes. Masqué au micro-BA.
import { useState } from "react";
import {
  Alert, Anchor, Badge, Button, Center, FileButton, Group, Loader, NumberInput, Paper, SegmentedControl, Select,
  SimpleGrid, Stack, Table, Text, TextInput, Textarea, Title,
} from "@mantine/core";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, api } from "../../api/client";
import { showNotices, useAction, type Notice } from "../../api/resources";
import { useCan } from "../../api/session";
import { upload } from "../../api/upload";
import { ConfirmButton } from "../../components/ConfirmButton";
import { FilterBar, useUrlParams } from "../../components/FilterBar";
import { FormDrawer, FormModal } from "../../components/FormModal";
import { MoneyInput, MoneyText } from "../../components/Money";
import { PageHeader } from "../../components/PageHeader";
import { formatDate } from "../../lib/format";
import type { FiscalYear } from "../fiscal-years/FiscalYearsPage";
import { LotsPanel, type StockLotItem } from "./LotsPanel";
import { CropAdvancesPanel, type CropAdvanceItem } from "./CropAdvancesPanel";
import { StockEntryBar, type StockEntryStatus } from "./StockEntryBar";
import { ActivitySelect, useAnalyticTargets } from "../../components/AnalyticSelect";

export const STOCK_KEY = ["stock"];
type Option = { value: string; label: string };
export interface StockLineItem {
  id: number; category: string; account: { id: number; code: string; label: string }; variation_account: { id: number; code: string };
  label: string; production: string | null; activity_id?: number | null; activity?: string | null; quantity: string; unit: string; method: string; standard_id: number | null;
  standard: { id: number; label: string; value_cents: number; unit: string; year: number } | null;
  market_price_cents: number | null; price_source: string | null; price_reference: string | null; flat_rate: string | null;
  unit_value_cents: number | null; value_cents: number | null; depreciation_cents: number | null;
  depreciation_reason: string | null; notes: string | null; warnings: string[]; purchase_account: string | null;
  lot_id: number | null; heads: number | null; gap_reason: string | null; crop_advance_id: number | null; cow_category?: string | null;
  fiscal: { fiscal_method: string; fiscal_value_cents: number | null; gap_cents: number | null; warnings: string[]; allowed: string[];
    fiscal_reason: string | null; manual_cents: number | null;
    frozen?: { reference_year?: string; reference_unit_cents?: number; blocked_quantity?: string; surplus_quantity?: string; error?: string } };
}
interface Category { key: string; label: string; group: string; methods: string[]; retail: boolean; accounts: { prefix: string; variation: string }[] }
interface Standard { id: number; key: string; label: string; unit: string; value_cents: number; year: number; source: string | null }
export interface StockView {
  item: {
    fiscal_year: { id: number; label: string; end_date: string; status: string }; editable: boolean; items: StockLineItem[];
    totals: Record<string, { value_cents: number; depreciation_cents: number; lines: number }>; total_cents: number;
    discounts: Record<string, number>; counted_on: string | null; flat_allowed: boolean; has_previous: boolean;
    opening: { code: string; label: string; balance_cents: number; counted: boolean }[]; purchases: Record<string, number | null>;
    lots: StockLotItem[]; crop_advances: CropAdvanceItem[];
    fiscal: { accounting_cents: number; fiscal_cents: number; gap_cents: number; missing: number; flat: boolean; frozen: boolean; frozen_since: string | null };
  };
  meta: {
    categories: Category[]; groups: Option[]; methods: Option[]; units: Option[]; flat_rates: Option[]; standards: Standard[];
    price_references: { source: string; week: string; items: { key: string; label: string; unit: string; min: number; max: number }[] };
  };
  files: { id: number; name: string; mime: string; size: number; note: string | null; created_at: string }[];
  entry: StockEntryStatus;
}

const FISCAL: Record<string, string> = { none: "Valeur comptable", flat: "Méthode forfaitaire (art. 74 b)",
  frozen: "Stock bloqué (art. 72 B bis)", manual: "Valeur fiscale saisie" };
const errorOf = (e: unknown) => (e instanceof ApiError ? e.message : "Enregistrement impossible.");

type Draft = Record<string, string | number | null>;

function LineForm({ view, line, onDone }: { view: StockView; line: StockLineItem | null; onDone: () => void }) {
  const fyId = view.item.fiscal_year.id;
  const [d, setD] = useState<Draft>((): Draft => line ? {
    account_code: line.account.code, variation_account_code: line.variation_account.code, label: line.label,
    production: line.production, activity_id: line.activity_id ?? null, quantity: line.quantity, unit: line.unit, method: line.method,
    standard_id: line.standard_id, market_price_cents: line.market_price_cents, price_source: line.price_source,
    price_reference: line.price_reference, flat_rate: line.flat_rate, unit_value_cents: line.unit_value_cents,
    depreciation_cents: line.depreciation_cents, depreciation_reason: line.depreciation_reason, notes: line.notes,
    lot_id: line.lot_id, heads: line.heads, gap_reason: line.gap_reason, cow_category: line.cow_category ?? null,
    fiscal_method: line.fiscal.fiscal_method, fiscal_value_cents: line.fiscal.manual_cents, fiscal_reason: line.fiscal.fiscal_reason,
  } : { account_code: "", label: "", quantity: "0", unit: "unit", method: "actual" });
  const [error, setError] = useState<string | null>(null);
  const targets = useAnalyticTargets();
  const opts = { invalidate: [STOCK_KEY] };
  const save = useAction((body: Draft) => (line ? api.put<{ notices: Notice[] }>(`/api/v1/fiscal-years/${fyId}/stock/lines/${line.id}`, body)
    : api.post<{ notices: Notice[] }>(`/api/v1/fiscal-years/${fyId}/stock/lines`, body)), opts);
  const set = (patch: Draft) => setD((x) => ({ ...x, ...patch }));
  const code = String(d.account_code ?? "");
  const cat = view.meta.categories
    .filter((c) => c.accounts.some((a) => code.startsWith(a.prefix)))
    .sort((a, b) => Math.max(...b.accounts.filter((x) => code.startsWith(x.prefix)).map((x) => x.prefix.length))
      - Math.max(...a.accounts.filter((x) => code.startsWith(x.prefix)).map((x) => x.prefix.length)))[0];
  const methods = view.meta.methods.filter((m) => !cat || cat.methods.includes(m.value));
  const method = String(d.method ?? "actual");
  const clean = (x: Draft) => Object.fromEntries(Object.entries(x).filter(([k, v]) => !(k === "variation_account_code" && !v)));
  return (
    <form onSubmit={(e) => { e.preventDefault(); setError(null); save.mutateAsync(clean(d)).then(onDone, (er) => setError(errorOf(er))); }}>
      <Stack gap="sm">
        <Group grow>
          <TextInput label="Compte de stock" required value={code} onChange={(e) => set({ account_code: e.currentTarget.value })}
            description={cat ? cat.label : "31, 32, 33, 35 ou 37"} />
          <TextInput label="Compte de variation" placeholder="proposé" value={String(d.variation_account_code ?? "")}
            onChange={(e) => set({ variation_account_code: e.currentTarget.value })} />
        </Group>
        {cat?.group === "animals" && view.item.lots.length > 0 && (
          <Group grow>
            <Select label="Lot d'animaux" clearable data={view.item.lots.filter((l) => l.account.code === code || !code)
              .map((l) => ({ value: String(l.id), label: `${l.label} (théorique ${l.summary?.theoretical ?? 0})` }))}
              value={d.lot_id ? String(d.lot_id) : null} onChange={(v) => set({ lot_id: v ? Number(v) : null })} />
            {d.lot_id ? <NumberInput label="Effectif compté (têtes)" min={0} value={(d.heads as number | null) ?? ""}
              onChange={(v) => set({ heads: typeof v === "number" ? v : null })} /> : null}
          </Group>)}
        {cat?.group === "animals" && (
          <Select label="Vaches (provision 73 A)" clearable placeholder="autres animaux" w={260}
            data={[{ value: "dairy", label: "Vaches laitières" }, { value: "suckler", label: "Vaches allaitantes" }]}
            value={d.cow_category ? String(d.cow_category) : null} onChange={(v) => set({ cow_category: v })} />)}
        {d.lot_id ? <TextInput label="Motif d'un écart avec l'effectif théorique" value={String(d.gap_reason ?? "")}
          onChange={(e) => set({ gap_reason: e.currentTarget.value })} /> : null}
        <TextInput label="Libellé" required value={String(d.label ?? "")} onChange={(e) => set({ label: e.currentTarget.value })} />
        <TextInput label="Production" value={String(d.production ?? "")} onChange={(e) => set({ production: e.currentTarget.value })} />
        <ActivitySelect label="Activité" description="Variation de stock reprise dans la marge de l'activité." targets={targets}
          value={typeof d.activity_id === "number" ? d.activity_id : null} onChange={(v) => set({ activity_id: v })} />
        <Group grow>
          <TextInput label="Quantité" value={String(d.quantity ?? "")} onChange={(e) => set({ quantity: e.currentTarget.value.replace(",", ".") })} />
          <Select label="Unité" data={view.meta.units} value={String(d.unit ?? "unit")} allowDeselect={false} onChange={(v) => set({ unit: v })} />
          <Select label="Méthode" data={methods} value={method} allowDeselect={false} onChange={(v) => set({ method: v })} />
        </Group>
        {method === "actual" && <MoneyInput label="Valeur unitaire (coût réel)" value={(d.unit_value_cents as number | null) ?? null}
          onChange={(v) => set({ unit_value_cents: v })} />}
        {method === "standard" && (
          <Select label="Barème" data={view.meta.standards.map((s) => ({ value: String(s.id), label: `${s.label} (${s.year})` }))}
            value={d.standard_id ? String(d.standard_id) : null} onChange={(v) => set({ standard_id: v ? Number(v) : null })} />)}
        {(method === "retail" || method === "flat") && (
          <>
            <Group grow>
              <MoneyInput label="Cours du jour à la clôture (par unité)" value={(d.market_price_cents as number | null) ?? null}
                onChange={(v) => set({ market_price_cents: v })} />
              <TextInput label="Source du cours" value={String(d.price_source ?? "")} onChange={(e) => set({ price_source: e.currentTarget.value })} />
            </Group>
            <Select label="Ordre de grandeur à contrôler" clearable
              description={`${view.meta.price_references.source}`}
              data={view.meta.price_references.items.map((r) => ({ value: r.key, label: `${r.label} — ${r.min} à ${r.max} ${r.unit}` }))}
              value={(d.price_reference as string | null) ?? null} onChange={(v) => set({ price_reference: v })} />
            {method === "flat" && <Select label="Décote forfaitaire" data={view.meta.flat_rates} value={String(d.flat_rate ?? "general")}
              allowDeselect={false} onChange={(v) => set({ flat_rate: v })} />}
          </>)}
        <Group grow>
          <MoneyInput label="Dépréciation" value={(d.depreciation_cents as number | null) ?? null} onChange={(v) => set({ depreciation_cents: v })} />
          <TextInput label="Motif de la dépréciation" value={String(d.depreciation_reason ?? "")} onChange={(e) => set({ depreciation_reason: e.currentTarget.value })} />
        </Group>
        {line && line.fiscal.allowed.length > 2 && (
          <>
            <Select label="Valeur fiscale" allowDeselect={false} value={String(d.fiscal_method ?? "none")} onChange={(v) => set({ fiscal_method: v })}
              data={line.fiscal.allowed.map((m) => ({ value: m, label: FISCAL[m] ?? m }))}
              description={d.fiscal_method === "frozen" ? "Règle de l'excédent et des sorties à valider (Q-S5)." : undefined} />
            {d.fiscal_method === "manual" && (
              <Group grow>
                <MoneyInput label="Valeur fiscale saisie" value={(d.fiscal_value_cents as number | null) ?? null} onChange={(v) => set({ fiscal_value_cents: v })} />
                <TextInput label="Motif" value={String(d.fiscal_reason ?? "")} onChange={(e) => set({ fiscal_reason: e.currentTarget.value })} />
              </Group>)}
          </>)}
        <Textarea label="Notes" autosize minRows={2} value={String(d.notes ?? "")} onChange={(e) => set({ notes: e.currentTarget.value })} />
        {error && <Alert color="brique">{error}</Alert>}
        <Group><Button type="submit" loading={save.isPending}>{line ? "Enregistrer" : "Ajouter la ligne"}</Button></Group>
      </Stack>
    </form>
  );
}

function Discounts({ view }: { view: StockView }) {
  const fyId = view.item.fiscal_year.id;
  const [values, setValues] = useState<Record<string, number | null>>(() =>
    Object.fromEntries(Object.entries(view.item.discounts).map(([k, bp]) => [k, bp / 100])));
  const save = useAction((body: object) => api.put<{ notices: Notice[] }>(`/api/v1/fiscal-years/${fyId}/stock/settings`, body), { invalidate: [STOCK_KEY] });
  const retail = view.meta.categories.filter((c) => c.retail && c.methods.includes("retail"));
  return (
    <Paper withBorder p="sm">
      <Text fw={600} size="sm" mb={4}>Décotes du prix de détail, par catégorie</Text>
      <Text size="xs" c="dimmed" mb="xs">Marge et frais de commercialisation déduits du cours du jour (PCG 618-13, 3°). Sans valeur par défaut.</Text>
      <SimpleGrid cols={{ base: 1, sm: 3 }}>
        {retail.map((c) => (
          <NumberInput key={c.key} label={c.label} suffix=" %" min={0} max={99.99} decimalScale={2} decimalSeparator=","
            disabled={!view.item.editable} value={values[c.key] ?? ""}
            onChange={(v) => setValues({ ...values, [c.key]: typeof v === "number" ? v : null })} />))}
      </SimpleGrid>
      {view.item.editable && <Group mt="xs"><Button size="xs" variant="light" loading={save.isPending}
        onClick={() => save.mutate({ discounts: Object.fromEntries(Object.entries(values).map(([k, v]) => [k, v === null ? null : Math.round(v * 100)])) })}>
        Enregistrer les décotes</Button></Group>}
    </Paper>
  );
}

function Files({ view }: { view: StockView }) {
  const fyId = view.item.fiscal_year.id;
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const remove = useAction((id: number) => api.delete<{ notices: Notice[] }>(`/api/v1/fiscal-years/${fyId}/stock/files/${id}`), { invalidate: [STOCK_KEY] });
  const send = async (file: File | null) => {
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    setError(null);
    try {
      const body = await upload<{ notices: Notice[] }>(`/api/v1/fiscal-years/${fyId}/stock/files`, form);
      showNotices(body.notices);
      void queryClient.invalidateQueries({ queryKey: STOCK_KEY });
    } catch (e) { setError(errorOf(e)); }
  };
  return (
    <Paper withBorder p="sm">
      <Group justify="space-between" mb={4}>
        <Text fw={600} size="sm">Feuilles de comptage</Text>
        {view.item.editable && <FileButton onChange={(f) => void send(f)} accept="application/pdf,image/jpeg,image/png">
          {(props) => <Button size="xs" variant="light" {...props}>Joindre</Button>}</FileButton>}
      </Group>
      {view.files.length === 0 ? <Text size="sm" c="dimmed">Aucune pièce.</Text> : view.files.map((f) => (
        <Group key={f.id} gap="xs">
          <Anchor size="sm" href={`/api/v1/fiscal-years/${fyId}/stock/files/${f.id}`} target="_blank">{f.name}</Anchor>
          {view.item.editable && <Button size="compact-xs" variant="subtle" color="brique" onClick={() => remove.mutate(f.id)}>Retirer</Button>}
        </Group>))}
      {error && <Alert color="brique" mt="xs">{error}</Alert>}
    </Paper>
  );
}

function Standards({ view }: { view: StockView }) {
  const [d, setD] = useState<{ label: string; unit: string; value: number | null; year: number; source: string }>(
    { label: "", unit: "head", value: null, year: new Date().getFullYear(), source: "" });
  const [error, setError] = useState<string | null>(null);
  const create = useAction((body: object) => api.post<{ notices: Notice[] }>("/api/v1/stock-standards", body), { invalidate: [STOCK_KEY] });
  const remove = useAction((id: number) => api.delete<{ notices: Notice[] }>(`/api/v1/stock-standards/${id}`), { invalidate: [STOCK_KEY] });
  return (
    <Stack>
      <Text size="sm" c="dimmed">Coûts standards de l'exploitation (PCG 618-13, 1°) : barèmes des chambres ou des instituts,
        adaptés aux conditions propres de l'exploitation.</Text>
      <Table>
        <Table.Tbody>{view.meta.standards.map((s) => (
          <Table.Tr key={s.id}><Table.Td>{s.label}</Table.Td><Table.Td>{s.year}</Table.Td>
            <Table.Td ta="right"><MoneyText cents={s.value_cents} /> / {view.meta.units.find((u) => u.value === s.unit)?.label}</Table.Td>
            <Table.Td>{s.source}</Table.Td>
            <Table.Td><Button size="compact-xs" variant="subtle" color="brique" onClick={() => remove.mutate(s.id)}>Supprimer</Button></Table.Td></Table.Tr>))}
        </Table.Tbody>
      </Table>
      <Group align="end" gap="xs">
        <TextInput label="Libellé" w={200} value={d.label} onChange={(e) => setD({ ...d, label: e.currentTarget.value })} />
        <Select label="Unité" w={110} data={view.meta.units} value={d.unit} allowDeselect={false} onChange={(v) => setD({ ...d, unit: v ?? "unit" })} />
        <MoneyInput label="Valeur" w={120} value={d.value} onChange={(v) => setD({ ...d, value: v })} />
        <NumberInput label="Année" w={90} value={d.year} onChange={(v) => setD({ ...d, year: Number(v) })} />
        <TextInput label="Source" w={180} value={d.source} onChange={(e) => setD({ ...d, source: e.currentTarget.value })} />
        <Button disabled={!d.label || !d.value} loading={create.isPending} onClick={() => {
          setError(null);
          create.mutateAsync({ label: d.label, unit: d.unit, value_cents: d.value, year: d.year, source: d.source })
            .then(() => setD({ ...d, label: "", value: null }), (e) => setError(errorOf(e)));
        }}>Ajouter</Button>
      </Group>
      {error && <Alert color="brique">{error}</Alert>}
    </Stack>
  );
}

export default function InventoryPage() {
  const can = useCan();
  const queryClient = useQueryClient();
  const { data: years } = useQuery({ queryKey: ["fiscal-years"], queryFn: () => api.get<{ items: FiscalYear[] }>("/api/v1/fiscal-years") });
  const [params, setParams] = useUrlParams({ fiscal_year: "", group: "supplies" });
  const fyId = Number(params.fiscal_year) || years?.items.find((y) => y.status === "open")?.id || years?.items[0]?.id;
  const { data: view, error } = useQuery({ queryKey: [...STOCK_KEY, fyId], enabled: !!fyId,
    queryFn: () => api.get<StockView>(`/api/v1/fiscal-years/${fyId}/stock`) });
  const [editing, setEditing] = useState<StockLineItem | "new" | null>(null);
  const [standards, setStandards] = useState(false);
  const [importError, setImportError] = useState<string | null>(null);
  const opts = { invalidate: [STOCK_KEY] };
  const copy = useAction(() => api.post<{ notices: Notice[] }>(`/api/v1/fiscal-years/${fyId}/stock/copy-previous`), opts);
  const remove = useAction((id: number) => api.delete<{ notices: Notice[] }>(`/api/v1/fiscal-years/${fyId}/stock/lines/${id}`), opts);
  if (error) return <Alert color="paille">{errorOf(error)}</Alert>;
  if (!years || !view) return <Center h={300}><Loader /></Center>;
  const v = view.item;
  const writable = can.write && v.editable;
  const cats = view.meta.categories.filter((c) => c.group === params.group).map((c) => c.key);
  const lines = v.items.filter((i) => cats.includes(i.category));
  const catLabel = (key: string) => view.meta.categories.find((c) => c.key === key)?.label ?? key;
  const unitLabel = (u: string) => view.meta.units.find((x) => x.value === u)?.label ?? u;
  const methodLabel = (m: string) => view.meta.methods.find((x) => x.value === m)?.label ?? m;
  const groupTotal = (g: string) => view.meta.categories.filter((c) => c.group === g)
    .reduce((s, c) => s + (v.totals[c.key]?.value_cents ?? 0), 0);
  const importFile = async (file: File | null) => {
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    setImportError(null);
    try {
      const body = await upload<{ notices: Notice[] }>(`/api/v1/fiscal-years/${fyId}/stock/import`, form);
      showNotices(body.notices);
      void queryClient.invalidateQueries({ queryKey: STOCK_KEY });
    } catch (e) { setImportError(errorOf(e)); }
  };
  const missing = v.opening.filter((o) => !o.counted);
  const fiscalShown = v.fiscal.flat || v.fiscal.frozen;
  return (
    <>
      <PageHeader title="Inventaire de clôture"
        description={`Stocks au ${formatDate(v.fiscal_year.end_date)} : quantités comptées, méthode de valorisation par ligne. L'écriture de stock se passe à la clôture.`}
        actions={<Group gap="xs">
          {can.write && <Button variant="default" onClick={() => setStandards(true)}>Barèmes</Button>}
          {writable && v.items.length === 0 && v.has_previous && <Button variant="default" loading={copy.isPending}
            onClick={() => copy.mutate(undefined)}>Reprendre l'exercice précédent</Button>}
          {writable && <FileButton onChange={(f) => void importFile(f)} accept=".csv,.xlsx,text/csv">
            {(props) => <Button variant="default" {...props}>Importer</Button>}</FileButton>}
          {writable && <Button onClick={() => setEditing("new")}>Ajouter une ligne</Button>}
        </Group>} />
      <FilterBar>
        <Select aria-label="Exercice" w={180} allowDeselect={false} value={fyId ? String(fyId) : null}
          data={years.items.map((y) => ({ value: String(y.id), label: `Exercice ${y.label}` }))}
          onChange={(x) => setParams({ fiscal_year: x ?? "" })} />
        {!v.editable && <Badge color="gray">Exercice clôturé : inventaire figé</Badge>}
      </FilterBar>
      {importError && <Alert color="brique" mb="sm">{importError}</Alert>}
      {fyId && <StockEntryBar fyId={fyId} status={view.entry} editable={v.editable} invalidate={[STOCK_KEY, ["closing", fyId]]} />}
      {missing.length > 0 && (
        <Alert color="paille" mb="sm" title="Stocks initiaux sans ligne d'inventaire">
          {missing.map((o) => <Text key={o.code} size="sm">{o.code} {o.label} : <MoneyText cents={o.balance_cents} /> à l'ouverture</Text>)}
          <Text size="xs" mt={4}>Sans ligne, l'écriture de stock annulera ce stock initial (stock final nul).</Text>
        </Alert>)}
      <SimpleGrid cols={{ base: 2, sm: 5 }} mb="md">
        {view.meta.groups.map((g) => (
          <Paper key={g.value} withBorder p="sm"><Text size="xs" c="dimmed">{g.label}</Text><MoneyText cents={groupTotal(g.value)} /></Paper>))}
        <Paper withBorder p="sm"><Text size="xs" c="dimmed">Total</Text><Title order={4}><MoneyText cents={v.total_cents} /></Title>
          {(v.fiscal.flat || v.fiscal.frozen) && <Text size="xs" c="dimmed">fiscal <MoneyText cents={v.fiscal.fiscal_cents} /> · écart <MoneyText cents={v.fiscal.gap_cents} plus /></Text>}</Paper>
      </SimpleGrid>
      <SegmentedControl mb="sm" value={params.group} onChange={(g) => setParams({ group: g })} data={view.meta.groups} />
      {params.group === "crops" && fyId && <CropAdvancesPanel fyId={fyId} advances={v.crop_advances} editable={writable} invalidate={[STOCK_KEY]} />}
      {params.group === "animals" && fyId && <LotsPanel fyId={fyId} lots={v.lots} editable={writable} invalidate={[STOCK_KEY]} />}
      <Table highlightOnHover mb="lg">
        <Table.Thead><Table.Tr><Table.Th>Ligne</Table.Th><Table.Th>Comptes</Table.Th><Table.Th ta="right">Quantité</Table.Th>
          <Table.Th>Méthode</Table.Th><Table.Th ta="right">Valeur unitaire</Table.Th><Table.Th ta="right">Valeur</Table.Th>
          {fiscalShown && <Table.Th ta="right">Valeur fiscale</Table.Th>}<Table.Th /></Table.Tr></Table.Thead>
        <Table.Tbody>
          {lines.length === 0 && <Table.Tr><Table.Td colSpan={7}><Text size="sm" c="dimmed">Aucune ligne dans ce groupe.</Text></Table.Td></Table.Tr>}
          {lines.map((l) => (
            <Table.Tr key={l.id} style={{ cursor: writable ? "pointer" : undefined }} onClick={() => writable && !l.crop_advance_id && setEditing(l)}>
              <Table.Td><Text size="sm">{l.label}</Text><Text size="xs" c="dimmed">{catLabel(l.category)}{l.production ? ` · ${l.production}` : ""}</Text>
                {l.warnings.map((w) => <Text key={w} size="xs" c="var(--lv-paille-ink)">{w}</Text>)}
                {l.depreciation_cents ? <Text size="xs" c="dimmed">dépréciation <MoneyText cents={l.depreciation_cents} /> ({l.depreciation_reason})</Text> : null}</Table.Td>
              <Table.Td className="lv-num">{l.account.code} / {l.variation_account.code}</Table.Td>
              <Table.Td ta="right" className="lv-num">{Number(l.quantity).toLocaleString("fr-FR")} {unitLabel(l.unit)}</Table.Td>
              <Table.Td><Text size="sm">{methodLabel(l.method)}</Text>
                {l.method === "actual" && l.purchase_account && v.purchases[l.purchase_account] != null && (
                  <Text size="xs" c="dimmed">achats {l.purchase_account} de l'exercice : <MoneyText cents={v.purchases[l.purchase_account] ?? 0} /></Text>)}</Table.Td>
              <Table.Td ta="right">{l.unit_value_cents !== null ? <MoneyText cents={l.unit_value_cents} /> : "—"}</Table.Td>
              <Table.Td ta="right">{l.value_cents !== null ? <MoneyText cents={l.value_cents} /> : "—"}</Table.Td>
              {fiscalShown && <Table.Td ta="right">{l.fiscal.fiscal_value_cents !== null ? <MoneyText cents={l.fiscal.fiscal_value_cents} /> : "—"}
                <Text size="xs" c="dimmed">{FISCAL[l.fiscal.fiscal_method]}{l.fiscal.gap_cents ? <> · <MoneyText cents={l.fiscal.gap_cents} plus /></> : null}</Text>
                {l.fiscal.warnings.map((w) => <Text key={w} size="xs" c="var(--lv-paille-ink)">{w}</Text>)}</Table.Td>}
              <Table.Td onClick={(e) => e.stopPropagation()}>{writable && (
                <ConfirmButton title={`Supprimer la ligne « ${l.label} » ?`} message="La ligne est retirée de l'inventaire."
                  confirmLabel="Supprimer" onConfirm={() => remove.mutate(l.id)}>Supprimer</ConfirmButton>)}</Table.Td>
            </Table.Tr>))}
        </Table.Tbody>
      </Table>
      <SimpleGrid cols={{ base: 1, md: 2 }}>
        <Discounts key={`${fyId}-${JSON.stringify(v.discounts)}`} view={view} />
        <Files view={view} />
      </SimpleGrid>
      <FormDrawer opened={editing !== null} onClose={() => setEditing(null)} title={editing === "new" ? "Nouvelle ligne de stock" : "Ligne de stock"}>
        {editing !== null && <LineForm view={view} line={editing === "new" ? null : editing} onDone={() => setEditing(null)} />}
      </FormDrawer>
      <FormModal opened={standards} onClose={() => setStandards(false)} title="Barèmes de coût standard" size="xl">
        {standards && <Standards view={view} />}
      </FormModal>
    </>
  );
}

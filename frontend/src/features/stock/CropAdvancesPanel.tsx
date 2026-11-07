// Inventaire de clôture › Végétaux en terre (lot AG4.c, claudedocs/design_inventaire_agricole.md § 5) : avances aux
// cultures. Fiche par culture en terre (production, surface, implantation, cycle) ; coût standard du barème de
// l'exploitation (variantes F, M1, M2 du guide CEGARA, cumul au mois de clôture) ou coût réel de l'art. 72 A (charges
// de l'exercice cochées avec une quote-part). La fiche alimente sa ligne d'inventaire 31151 / 31141.
import { useState } from "react";
import {
  Alert, Button, Checkbox, Drawer, Group, Loader, NumberInput, Paper, SegmentedControl, Select, Stack, Table, Text, TextInput,
} from "@mantine/core";
import { DateInput } from "@mantine/dates";
import { useQuery } from "@tanstack/react-query";
import { ApiError, api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { FormModal } from "../../components/FormModal";
import { MoneyInput, MoneyText } from "../../components/Money";
import { formatDate } from "../../lib/format";

type Option = { value: string; label: string };
type StandardRow = { component: string; month: number; amount_cents: number };
export interface CropStandardItem { id: number; production: string; year: number; source: string | null; labour_assumption: string | null;
  entry_mode?: "monthly" | "cumulative"; start_month?: number | null; rows: StandardRow[]; cumulative_rows?: StandardRow[] }
export interface CropAdvanceItem {
  id: number; production: string; surface_ha: string; planted_on: string; campaign: number | null; cycle: "short" | "long";
  account_code: string; plots: string | null; method: string; method_label: string; crop_standard_id: number | null;
  notes: string | null; value_cents: number | null; warnings: string[]; line_id: number | null;
  detail: { components: Record<string, number>; costs: Record<string, number>; months: number; labour_assumption?: string };
  costs: { id: number; rubric: string; rubric_label: string; label: string; journal_line_id: number | null; base_cents: number; share_bp: number; amount_cents: number }[];
  proposals?: { journal_line_id: number; date: string; account: string; label: string; amount_cents: number; rubric: string;
    rubric_label: string; selected: boolean; cost_id: number | null; share_used_bp: number; share_free_bp: number }[];
}
interface CropMeta { methods: Option[]; rubrics: Option[]; real_rubrics?: Record<string, string[]>; components: Option[]; standards: CropStandardItem[] }

const MONTHS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."];
const errorOf = (e: unknown) => (e instanceof ApiError ? e.message : "Enregistrement impossible.");

function AdvanceDrawer({ id, editable, invalidate, onClose }: { id: number | null; editable: boolean; invalidate: unknown[][]; onClose: () => void }) {
  const { data } = useQuery({ queryKey: ["crop-advance", id], enabled: id !== null,
    queryFn: () => api.get<{ item: CropAdvanceItem; meta: CropMeta }>(`/api/v1/crop-advances/${id}`) });
  const [shares, setShares] = useState<Record<number, number>>({});
  const [manual, setManual] = useState<{ rubric: string | null; label: string; amount: number | null }>({ rubric: null, label: "", amount: null });
  const [error, setError] = useState<string | null>(null);
  const opts = { invalidate: [...invalidate, ["crop-advance"]] };
  const save = useAction((body: object) => api.put<{ notices: Notice[] }>(`/api/v1/crop-advances/${id}`, body), opts);
  const addCost = useAction((body: object) => api.post<{ notices: Notice[] }>(`/api/v1/crop-advances/${id}/costs`, body), opts);
  const removeCost = useAction((cid: number) => api.delete<{ notices: Notice[] }>(`/api/v1/crop-advances/${id}/costs/${cid}`), opts);
  const remove = useAction(() => api.delete<{ notices: Notice[] }>(`/api/v1/crop-advances/${id}`), opts);
  const run = (p: Promise<unknown>, after?: () => void) => { setError(null); p.then(after, (e) => setError(errorOf(e))); };
  const a = data?.item;
  const meta = data?.meta;
  const usesCosts = a ? a.method !== "standard_f" : false;
  const supplyOnly = a ? a.method === "standard_m1" || a.method === "standard_m2" : false;
  // Rubriques prises au coût réel selon la méthode (lot CG2.a) : table servie par l'API.
  const realRubrics = a ? meta?.real_rubrics?.[a.method] ?? null : null;
  return (
    <Drawer opened={id !== null} onClose={onClose} position="right" size="xl" title={a ? `Avance aux cultures — ${a.production}` : ""}>
      {!a || !meta ? <Loader /> : (
        <Stack>
          <Text size="sm">{a.surface_ha} ha · implantée le {formatDate(a.planted_on)} · {a.account_code} · {a.detail.months} mois jusqu'à la clôture</Text>
          <Text fw={600}>Valeur : {a.value_cents !== null ? <MoneyText cents={a.value_cents} /> : "—"}</Text>
          {a.warnings.map((w) => <Alert key={w} color="paille">{w}</Alert>)}
          <Group grow>
            <Select label="Méthode" data={meta.methods} value={a.method} allowDeselect={false} disabled={!editable}
              onChange={(v) => run(save.mutateAsync({ method: v }))} />
            {a.method !== "actual" && <Select label="Barème" clearable disabled={!editable} value={a.crop_standard_id ? String(a.crop_standard_id) : null}
              data={meta.standards.map((s) => ({ value: String(s.id), label: `${s.production} (${s.year})` }))}
              onChange={(v) => run(save.mutateAsync({ crop_standard_id: v ? Number(v) : null }))} />}
          </Group>
          {Object.keys(a.detail.components).length > 0 && (
            <Text size="sm">Barème × surface : {Object.entries(a.detail.components).map(([c, cents]) => (
              <span key={c}>{meta.components.find((x) => x.value === c)?.label} <MoneyText cents={cents} /> · </span>))}
              {a.detail.labour_assumption && <Text span size="xs" c="dimmed">main-d'œuvre : {a.detail.labour_assumption}</Text>}</Text>)}
          {usesCosts && (
            <>
              <Text fw={600} size="sm">{supplyOnly ? "Charges prises au coût réel" : "Charges de l'art. 72 A"}</Text>
              <Table>
                <Table.Tbody>
                  {(a.proposals ?? []).filter((p) => !supplyOnly || !realRubrics || realRubrics.includes(p.rubric)).map((p) => {
                    const cost = a.costs.find((c) => c.journal_line_id === p.journal_line_id);
                    return (
                      <Table.Tr key={p.journal_line_id}>
                        <Table.Td><Checkbox aria-label={`Rattacher ${p.label}`} checked={p.selected} disabled={!editable || (!p.selected && p.share_free_bp === 0)}
                          onChange={(e) => run(e.currentTarget.checked
                            ? addCost.mutateAsync({ journal_line_id: p.journal_line_id, share_bp: Math.round((shares[p.journal_line_id] ?? Math.min(100, p.share_free_bp / 100)) * 100) })
                            : removeCost.mutateAsync(p.cost_id!))} /></Table.Td>
                        <Table.Td>{formatDate(p.date)}</Table.Td>
                        <Table.Td>{p.label}<Text size="xs" c="dimmed">{p.account} · {p.rubric_label}</Text></Table.Td>
                        <Table.Td ta="right"><MoneyText cents={p.amount_cents} /></Table.Td>
                        <Table.Td w={110}>{p.selected ? `${(cost?.share_bp ?? 0) / 100} %` : (
                          <NumberInput aria-label={`Quote-part ${p.label}`} size="xs" suffix=" %" min={0.01} max={p.share_free_bp / 100} decimalScale={2}
                            decimalSeparator="," value={shares[p.journal_line_id] ?? Math.min(100, p.share_free_bp / 100)} disabled={!editable}
                            onChange={(v) => setShares({ ...shares, [p.journal_line_id]: Number(v) || 0 })} />)}</Table.Td>
                        <Table.Td ta="right">{cost && <MoneyText cents={cost.amount_cents} />}</Table.Td>
                      </Table.Tr>);
                  })}
                  {a.costs.filter((c) => c.journal_line_id === null).map((c) => (
                    <Table.Tr key={c.id}><Table.Td /><Table.Td>saisie</Table.Td><Table.Td>{c.label}<Text size="xs" c="dimmed">{c.rubric_label}</Text></Table.Td>
                      <Table.Td /><Table.Td /><Table.Td ta="right"><MoneyText cents={c.amount_cents} />
                        {editable && <Button size="compact-xs" variant="subtle" color="brique" onClick={() => run(removeCost.mutateAsync(c.id))}>Retirer</Button>}</Table.Td></Table.Tr>))}
                </Table.Tbody>
              </Table>
              <Text size="xs" c="dimmed">Liste fermée de l'art. 72 A : semences, engrais, traitements, main-d'œuvre des façons culturales,
                frais de matériel. Fermage, assurance et frais généraux en sont exclus.</Text>
              {editable && (
                <Group align="end" gap="xs">
                  <Select label="Rubrique" w={240} data={supplyOnly && realRubrics ? meta.rubrics.filter((r) => realRubrics.includes(r.value)) : meta.rubrics} value={manual.rubric} onChange={(v) => setManual({ ...manual, rubric: v })} />
                  <TextInput label="Libellé" w={180} value={manual.label} onChange={(e) => setManual({ ...manual, label: e.currentTarget.value })} />
                  <MoneyInput label="Montant" w={120} value={manual.amount} onChange={(v) => setManual({ ...manual, amount: v })} />
                  <Button variant="light" disabled={!manual.rubric || !manual.label || !manual.amount}
                    onClick={() => run(addCost.mutateAsync({ rubric: manual.rubric, label: manual.label, amount_cents: manual.amount }),
                      () => setManual({ rubric: null, label: "", amount: null }))}>Ajouter une charge saisie</Button>
                </Group>)}
            </>)}
          {error && <Alert color="brique">{error}</Alert>}
          {editable && <Group><Button variant="subtle" color="brique" onClick={() => run(remove.mutateAsync(undefined), onClose)}>Supprimer la fiche</Button></Group>}
        </Stack>)}
    </Drawer>
  );
}

function StandardsEditor({ standards, invalidate }: { standards: CropStandardItem[]; invalidate: unknown[][] }) {
  const [selected, setSelected] = useState<number | null>(standards[0]?.id ?? null);
  const [head, setHead] = useState({ production: "", year: new Date().getFullYear(), source: "", labour: "100 % main-d'œuvre salariée" });
  const [grid, setGrid] = useState<Record<string, number | null>>({});
  const [error, setError] = useState<string | null>(null);
  const opts = { invalidate: [...invalidate, ["crop-advance"]] };
  const create = useAction((body: object) => api.post<{ item: CropStandardItem; notices: Notice[] }>("/api/v1/crop-standards", body), opts);
  const update = useAction((v: { id: number; body: object }) => api.put<{ notices: Notice[] }>(`/api/v1/crop-standards/${v.id}`, v.body), opts);
  const current = standards.find((s) => s.id === selected);
  // Lot CG2.b : un barème saisi en cumul s'affiche et se modifie en cumul ; Lyvre garde le montant du mois.
  const cumulative = current?.entry_mode === "cumulative";
  const source = cumulative ? current?.cumulative_rows ?? [] : current?.rows ?? [];
  const months = cumulative && current?.start_month
    ? Array.from({ length: 12 }, (_, i) => ((current.start_month as number) - 1 + i) % 12 + 1)
    : Array.from({ length: 12 }, (_, i) => i + 1);
  const cell = (component: string, month: number) => {
    const key = `${component}-${month}`;
    if (key in grid) return grid[key];
    return source.find((r) => r.component === component && r.month === month)?.amount_cents ?? null;
  };
  const rows = () => ["supplies", "machinery", "labour"].flatMap((c) => Array.from({ length: 12 }, (_, i) => i + 1)
    .map((m) => ({ component: c, month: m, amount_cents: cell(c, m) ?? 0 })));
  const run = (p: Promise<unknown>, after?: () => void) => { setError(null); p.then(after, (e) => setError(errorOf(e))); };
  return (
    <Stack>
      <Text size="sm" c="dimmed">Coût par ha et par mois d'opérations, en trois composantes (méthode du guide CEGARA). Lyvre ne fournit
        aucune valeur : saisissez le barème de l'exploitation, ou importez-le (CSV : Production ; Année ; Composante ; Mois ; Montant ;
        Mode « mensuel » ou « cumul » ; Début du cycle).</Text>
      <Group align="end">
        <Select label="Barème" w={260} data={standards.map((s) => ({ value: String(s.id), label: `${s.production} (${s.year})` }))}
          value={selected ? String(selected) : null} onChange={(v) => { setSelected(v ? Number(v) : null); setGrid({}); }} />
        <TextInput label="Nouvelle production" w={180} value={head.production} onChange={(e) => setHead({ ...head, production: e.currentTarget.value })} />
        <NumberInput label="Année" w={90} value={head.year} onChange={(v) => setHead({ ...head, year: Number(v) })} />
        <TextInput label="Source" w={180} value={head.source} onChange={(e) => setHead({ ...head, source: e.currentTarget.value })} />
        <Button variant="light" disabled={!head.production} onClick={() => run(create.mutateAsync({ production: head.production, year: head.year,
          source: head.source, labour_assumption: head.labour }), () => setHead({ ...head, production: "" }))}>Créer</Button>
      </Group>
      {current && (
        <>
          <Group align="end">
            <SegmentedControl aria-label="Mode de saisie" value={current.entry_mode ?? "monthly"}
              data={[{ value: "monthly", label: "Montants par mois" }, { value: "cumulative", label: "Cumul au mois de clôture" }]}
              onChange={(v) => run(update.mutateAsync({ id: current.id, body: { entry_mode: v, start_month: current.start_month ?? 9 } }), () => setGrid({}))} />
            {cumulative && (
              <Select label="Premier mois du cycle" w={170} data={MONTHS.map((m, i) => ({ value: String(i + 1), label: m }))}
                value={String(current.start_month ?? 9)}
                onChange={(v) => v && run(update.mutateAsync({ id: current.id, body: { start_month: Number(v) } }), () => setGrid({}))} />)}
          </Group>
          <Text size="xs" c="dimmed">{cumulative
            ? "Saisissez le cumul depuis le début du cycle, comme dans les barèmes publiés ; une case vide garde le cumul précédent."
            : "Saisissez le coût du seul mois. Les barèmes publiés donnent souvent le cumul au mois de clôture : choisissez alors « Cumul »."}</Text>
          <Table>
            <Table.Thead><Table.Tr><Table.Th>{cumulative ? "€ / ha cumulés" : "€ / ha du mois"}</Table.Th>{months.map((m) => <Table.Th key={m}>{MONTHS[m - 1]}</Table.Th>)}</Table.Tr></Table.Thead>
            <Table.Tbody>
              {[["supplies", "Approvisionnements"], ["machinery", "Mécanisation"], ["labour", "Main-d'œuvre"]].map(([c, label]) => (
                <Table.Tr key={c}><Table.Td>{label}</Table.Td>
                  {months.map((m) => (
                    <Table.Td key={m}><MoneyInput aria-label={`${label} ${MONTHS[m - 1]}`} size="xs" w={78} value={cell(c, m)}
                      onChange={(v) => setGrid({ ...grid, [`${c}-${m}`]: v })} /></Table.Td>))}
                </Table.Tr>))}
            </Table.Tbody>
          </Table>
          <Group><Button disabled={Object.keys(grid).length === 0} loading={update.isPending}
            onClick={() => run(update.mutateAsync({ id: current.id, body: { rows: rows() } }), () => setGrid({}))}>Enregistrer le barème</Button></Group>
        </>)}
      {error && <Alert color="brique">{error}</Alert>}
    </Stack>
  );
}

export function CropAdvancesPanel({ fyId, advances, editable, invalidate }: { fyId: number; advances: CropAdvanceItem[]; editable: boolean; invalidate: unknown[][] }) {
  const [open, setOpen] = useState<number | null>(null);
  const [draft, setDraft] = useState<{ production: string; surface: string; planted: string | null; cycle: string; method: string } | null>(null);
  const [standards, setStandards] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { data: meta } = useQuery({ queryKey: ["crop-advance", "standards"], queryFn: () => api.get<{ items: CropStandardItem[] }>("/api/v1/crop-standards") });
  const create = useAction((body: object) => api.post<{ item: CropAdvanceItem; notices: Notice[] }>(`/api/v1/fiscal-years/${fyId}/crop-advances`, body), { invalidate });
  return (
    <Paper withBorder p="sm" mb="lg">
      <Group justify="space-between" mb={4}>
        <Text fw={600} size="sm">Avances aux cultures</Text>
        <Group gap="xs">
          <Button size="xs" variant="default" onClick={() => setStandards(true)}>Barèmes par ha</Button>
          {editable && !draft && <Button size="xs" variant="light" onClick={() => setDraft({ production: "", surface: "", planted: null, cycle: "short", method: "actual" })}>Nouvelle culture en terre</Button>}
        </Group>
      </Group>
      <Text size="xs" c="dimmed" mb="xs">Produits végétaux en terre à la clôture : coût standard ou coût réel (art. 72 A) ; le prix de détail est interdit.</Text>
      {advances.length === 0 ? <Text size="sm" c="dimmed">Aucune culture en terre.</Text> : (
        <Table highlightOnHover>
          <Table.Tbody>
            {advances.map((a) => (
              <Table.Tr key={a.id} style={{ cursor: "pointer" }} onClick={() => setOpen(a.id)}>
                <Table.Td>{a.production}<Text size="xs" c="dimmed">{a.method_label}</Text>
                  {a.warnings.map((w) => <Text key={w} size="xs" c="var(--lv-paille-ink)">{w}</Text>)}</Table.Td>
                <Table.Td>{a.surface_ha} ha</Table.Td><Table.Td>{formatDate(a.planted_on)}</Table.Td>
                <Table.Td className="lv-num">{a.account_code}</Table.Td>
                <Table.Td ta="right">{a.value_cents !== null ? <MoneyText cents={a.value_cents} /> : "—"}</Table.Td>
              </Table.Tr>))}
          </Table.Tbody>
        </Table>)}
      {draft && (
        <Group align="end" gap="xs" mt="xs">
          <TextInput label="Production" required w={160} value={draft.production} onChange={(e) => setDraft({ ...draft, production: e.currentTarget.value })} />
          <TextInput label="Surface (ha)" w={100} value={draft.surface} onChange={(e) => setDraft({ ...draft, surface: e.currentTarget.value })} />
          <DateInput label="Implantée le" w={130} valueFormat="DD/MM/YYYY" value={draft.planted} onChange={(v) => setDraft({ ...draft, planted: v })} />
          <Select label="Cycle" w={130} value={draft.cycle} allowDeselect={false} onChange={(v) => setDraft({ ...draft, cycle: v ?? "short" })}
            data={[{ value: "short", label: "Court (31151)" }, { value: "long", label: "Long (31141)" }]} />
          <Button disabled={!draft.production || !draft.surface || !draft.planted} loading={create.isPending} onClick={() => {
            setError(null);
            create.mutateAsync({ production: draft.production, surface_ha: draft.surface.replace(",", "."), planted_on: draft.planted,
              cycle: draft.cycle, method: draft.method }).then((r) => { setDraft(null); setOpen(r.item.id); }, (e) => setError(errorOf(e)));
          }}>Créer</Button>
          <Button variant="default" onClick={() => setDraft(null)}>Annuler</Button>
        </Group>)}
      {error && <Alert color="brique" mt="xs">{error}</Alert>}
      <AdvanceDrawer id={open} editable={editable} invalidate={invalidate} onClose={() => setOpen(null)} />
      <FormModal opened={standards} onClose={() => setStandards(false)} title="Barèmes de coût standard des avances aux cultures" size="100%">
        {standards && <StandardsEditor standards={meta?.items ?? []} invalidate={invalidate} />}
      </FormModal>
    </Paper>
  );
}

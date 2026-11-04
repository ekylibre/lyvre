// Administration › Paramètres réglementaires (lot AG1.a, claudedocs/design_compta_agricole.md § 4.4) : seuils, taux
// et dates datés et sourcés (data/regulatory/*.json), avec leur fiabilité ; l'administrateur de la plateforme ajoute
// une surcharge datée (date limite PAC de l'année, appels MSA…), commune à toutes les instances.
import { useState } from "react";
import { Anchor, Badge, Button, Group, SegmentedControl, Select, SimpleGrid, Stack, Table, Text, TextInput, Textarea } from "@mantine/core";
import { DateInput } from "@mantine/dates";
import { useForm } from "@mantine/form";
import { api } from "../../api/client";
import { useAction, useList, type Notice } from "../../api/resources";
import { useCurrentSession } from "../../api/session";
import { applyApiError, FormBody } from "../../components/ApiForm";
import { confirmAction } from "../../components/ConfirmButton";
import { DataGrid, type GridColumn } from "../../components/DataGrid";
import { FormModal } from "../../components/FormModal";
import { PageHeader } from "../../components/PageHeader";
import { formatDate } from "../../lib/format";
import { RELIABILITY_COLORS } from "../organization/FiscalProfile";

export interface Param {
  key: string; value: unknown; valid_from: string; valid_to: string | null; source: string; source_label: string;
  verified_on: string | null; reliability: string; reliability_label: string; note: string; origin: "file" | "override";
  id: number | null;
}
interface Row { key: string; domain: string; current: Param | null; history: Param[] }
type Meta = { reliabilities: { value: string; label: string }[]; on: string };

const KEY = ["regulatory-values"];
const DOMAINS: Record<string, string> = { ba: "Bénéfices agricoles", vat: "TVA", option: "Options fiscales", msa: "MSA", pac: "PAC" };

/** Valeur lisible : montant en euros, taux en %, sinon JSON. */
export function formatParam(key: string, value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number" && key.endsWith("_cents")) return `${(value / 100).toLocaleString("fr-FR")} €`;
  if (typeof value === "number" && key.endsWith("_bp")) return `${(value / 100).toLocaleString("fr-FR")} %`;
  if (typeof value === "string" && key.endsWith("_date")) return formatDate(value);
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}

/** Saisie : euros et % convertis en centimes et points de base ; JSON pour un objet. */
function parseInput(key: string, text: string): unknown {
  const trimmed = text.trim();
  const number = Number(trimmed.replace(/\s/g, "").replace(",", "."));
  if (key.endsWith("_cents")) return Number.isFinite(number) ? Math.round(number * 100) : trimmed;
  if (key.endsWith("_bp")) return Number.isFinite(number) ? Math.round(number * 100) : trimmed;
  if (key.endsWith("_years") || key.endsWith("_days")) return Number.isFinite(number) ? Math.round(number) : trimmed;
  if (trimmed.startsWith("{") || trimmed.startsWith("[")) {
    try { return JSON.parse(trimmed); } catch { return trimmed; }
  }
  return trimmed;
}

const iso = (value: unknown) => (value ? String(value).slice(0, 10) : null);

function OverrideForm({ row, meta, onDone }: { row: Row; meta: Meta | undefined; onDone: () => void }) {
  const [error, setError] = useState<string | null>(null);
  const unit = row.key.endsWith("_cents") ? " (€)" : row.key.endsWith("_bp") ? " (%)" : "";
  const form = useForm({ initialValues: {
    value: "", valid_from: null as string | null, valid_to: null as string | null, reliability: "V",
    source: "", source_label: row.current?.source_label ?? "", note: "",
  } });
  const save = useAction((values: typeof form.values) => api.post<{ notices: Notice[] }>(
    `/api/v1/regulatory-values/${encodeURIComponent(row.key)}`,
    { ...values, value: parseInput(row.key, values.value), valid_from: iso(values.valid_from), valid_to: iso(values.valid_to) },
  ), { invalidate: [KEY], silent: true });
  return (
    <form onSubmit={form.onSubmit((values) => save.mutate(values, {
      onSuccess: onDone, onError: (e) => setError(applyApiError(form, e)),
    }))}>
      <FormBody error={error} submitLabel="Enregistrer la valeur" onCancel={onDone} loading={save.isPending}>
        <Text size="sm">Valeur actuelle : <b>{formatParam(row.key, row.current?.value)}</b>
          {row.current && ` (${row.current.reliability_label.toLowerCase()})`}</Text>
        <TextInput label={`Nouvelle valeur${unit}`} required data-autofocus classNames={{ input: "lv-num" }} {...form.getInputProps("value")} />
        <SimpleGrid cols={2}>
          <DateInput label="Valable du" required valueFormat="DD/MM/YYYY" {...form.getInputProps("valid_from")} />
          <DateInput label="au" clearable valueFormat="DD/MM/YYYY" description="Vide : sans fin." {...form.getInputProps("valid_to")} />
        </SimpleGrid>
        <Select label="Fiabilité" data={meta?.reliabilities ?? []} allowDeselect={false} {...form.getInputProps("reliability")} />
        <TextInput label="Source officielle" required placeholder="https://…" {...form.getInputProps("source")} />
        <TextInput label="Référence" placeholder="CGI art. 69, arrêté du…" {...form.getInputProps("source_label")} />
        <Textarea label="Note" autosize minRows={2} {...form.getInputProps("note")} />
        <Text size="xs" c="dimmed">La valeur s'applique à toutes les instances pour les dates couvertes.</Text>
      </FormBody>
    </form>
  );
}

function History({ row, onDelete }: { row: Row; onDelete: (p: Param) => void }) {
  return (
    <Table fz="sm" withRowBorders={false}>
      <Table.Tbody>{row.history.map((p, i) => (
        <Table.Tr key={`${p.origin}-${p.id ?? i}`}>
          <Table.Td className="lv-num">{formatDate(p.valid_from)} → {p.valid_to ? formatDate(p.valid_to) : "…"}</Table.Td>
          <Table.Td className="lv-num">{formatParam(row.key, p.value)}</Table.Td>
          <Table.Td><Badge size="xs" color={RELIABILITY_COLORS[p.reliability] ?? "gray"}>{p.reliability}</Badge></Table.Td>
          <Table.Td>{p.origin === "override" ? "Surcharge" : "Référence"}</Table.Td>
          <Table.Td>{p.source ? <Anchor href={p.source} target="_blank" rel="noreferrer" size="sm">{p.source_label || "source"}</Anchor> : "—"}</Table.Td>
          <Table.Td>{p.origin === "override" && (
            <Button size="compact-xs" variant="subtle" color="brique" onClick={() => onDelete(p)}>Supprimer</Button>)}</Table.Td>
        </Table.Tr>))}
      </Table.Tbody>
    </Table>
  );
}

export default function RegulatoryValuesPage() {
  const isAdmin = !!useCurrentSession().user?.is_admin;
  const [domain, setDomain] = useState("ba");
  const { data, isFetching } = useList<Row, Meta>(KEY, `/api/v1/regulatory-values?prefix=${domain}.`);
  const [editing, setEditing] = useState<Row | null>(null);
  const [viewing, setViewing] = useState<string | null>(null);
  const viewed = data?.items.find((r) => r.key === viewing) ?? null;
  const remove = useAction((p: Param) => api.delete<{ notices: Notice[] }>(`/api/v1/regulatory-values/overrides/${p.id}`),
    { invalidate: [KEY] });
  const columns: GridColumn<Row>[] = [
    { accessor: "key", title: "Paramètre", hideable: false,
      render: (r) => <Stack gap={0}><Text size="sm" ff="monospace">{r.key}</Text>
        {r.current?.note && <Text size="xs" c="dimmed">{r.current.note}</Text>}</Stack> },
    { accessor: "value", title: "Valeur en vigueur", textAlign: "right",
      render: (r) => <span className="lv-num">{r.current ? formatParam(r.key, r.current.value) : "aucune"}</span> },
    { accessor: "reliability", title: "Fiabilité",
      render: (r) => r.current && <Badge color={RELIABILITY_COLORS[r.current.reliability] ?? "gray"}>{r.current.reliability_label}</Badge> },
    { accessor: "source", title: "Source",
      render: (r) => r.current?.source ? <Anchor href={r.current.source} target="_blank" rel="noreferrer" size="sm">
        {r.current.source_label || "source"}</Anchor> : "—" },
    { accessor: "verified_on", title: "Vérifiée le",
      render: (r) => <span className="lv-num">{formatDate(r.current?.verified_on ?? null)}</span> },
    { accessor: "actions", title: "", hideable: false, textAlign: "right",
      render: (r) => isAdmin && <Button size="compact-sm" variant="subtle"
        onClick={(e) => { e.stopPropagation(); setEditing(r); }}>Nouvelle valeur</Button> },
  ];
  return (
    <>
      <PageHeader title="Paramètres réglementaires"
        description={`Seuils, taux et dates datés et sourcés, en vigueur au ${formatDate(data?.meta?.on ?? null)}. Rouge : à valider par l'expert-comptable.`} />
      <Group mb="md">
        <SegmentedControl value={domain} onChange={setDomain}
          data={Object.entries(DOMAINS).map(([value, label]) => ({ value, label }))} />
      </Group>
      <DataGrid id="regulatory-values" idAccessor="key" records={data?.items} columns={columns} fetching={isFetching}
        onRowClick={(r) => setViewing(r.key)} />
      <FormModal opened={!!viewed && !editing} onClose={() => setViewing(null)} title={viewed ? `Historique : ${viewed.key}` : ""} size="xl">
        {viewed && <Stack>
          <History row={viewed} onDelete={(p) => confirmAction({
            title: "Supprimer cette surcharge ?", message: "La valeur de référence du fichier s'appliquera de nouveau.",
            confirmLabel: "Supprimer", onConfirm: () => remove.mutate(p) })} />
          {isAdmin && <Group><Button onClick={() => setEditing(viewed)}>Nouvelle valeur</Button></Group>}
        </Stack>}
      </FormModal>
      <FormModal opened={!!editing} onClose={() => setEditing(null)} title={editing ? editing.key : ""}>
        {editing && <OverrideForm row={editing} meta={data?.meta} onDone={() => setEditing(null)} />}
      </FormModal>
    </>
  );
}

// Validation des écritures (lot F1) : « Valider jusqu'au… », contrepassation, historique d'une écriture,
// lots de validation d'un exercice (dernier lot annulable par l'administrateur, motif obligatoire).
import { useState } from "react";
import { Alert, Button, Group, List, Paper, Stack, Table, Text, TextInput, Title } from "@mantine/core";
import { DateInput } from "@mantine/dates";
import { useForm } from "@mantine/form";
import { useQuery } from "@tanstack/react-query";
import { api, ApiError } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { useCan } from "../../api/session";
import { applyApiError, FormBody } from "../../components/ApiForm";
import { MoneyText } from "../../components/Money";
import { StatusBadge } from "../../components/StatusBadge";
import { formatDate } from "../../lib/format";

export const VALIDATION_KEY = ["validation"];
const today = () => new Date().toISOString().slice(0, 10);

/** Écritures refusées par la validation (déséquilibrées, hors exercice…), renvoyées par l'API. */
function refusals(error: unknown): string[] {
  return error instanceof ApiError && Array.isArray(error.details?.problems) ? (error.details.problems as string[]) : [];
}

export function ValidationRefusals({ error }: { error: unknown }) {
  const items = refusals(error);
  return items.length ? <List size="sm" c="var(--lv-brique)">{items.slice(0, 10).map((p) => <List.Item key={p}>{p}</List.Item>)}</List> : null;
}

export function ValidateUntilForm({ fiscalYearId, defaultDate, invalidate, onDone }: {
  fiscalYearId: number; defaultDate?: string; invalidate: unknown[][]; onDone: () => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const form = useForm({ initialValues: { until: defaultDate ?? today() } });
  const save = useAction((values: typeof form.values) => api.post<{ notices: Notice[] }>("/api/v1/entries/validation",
    { fiscal_year_id: fiscalYearId, until: values.until }), { invalidate: [...invalidate, VALIDATION_KEY], silent: true });
  return (
    <form onSubmit={form.onSubmit((values) => save.mutate(values, { onSuccess: onDone, onError: (e) => setError(applyApiError(form, e)) }))}>
      <FormBody error={error} submitLabel="Valider" onCancel={onDone} loading={save.isPending}>
        <Text size="sm">Les écritures en brouillard datées jusqu'à cette date reçoivent leur numéro définitif : elles ne
          se modifieront plus (une erreur se corrige ensuite par contrepassation).</Text>
        <DateInput label="Valider jusqu'au" required valueFormat="DD/MM/YYYY" data-autofocus {...form.getInputProps("until")} />
        <ValidationRefusals error={save.error} />
      </FormBody>
    </form>
  );
}

export function ReverseForm({ entryId, reference, invalidate, onDone }: {
  entryId: number; reference: string; invalidate: unknown[][]; onDone: (reversalId?: number) => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const form = useForm({ initialValues: { date: today(), reason: "" },
    validate: { reason: (v) => (v.trim() ? null : "Motif obligatoire.") } });
  const save = useAction((values: typeof form.values) =>
    api.post<{ item: { id: number }; notices: Notice[] }>(`/api/v1/entries/${entryId}/reverse`, values),
    { invalidate, silent: true });
  return (
    <form onSubmit={form.onSubmit((values) => save.mutate(values, {
      onSuccess: (r) => onDone(r.item.id), onError: (e) => setError(applyApiError(form, e)) }))}>
      <FormBody error={error} submitLabel="Contrepasser" onCancel={() => onDone()} loading={save.isPending}>
        <Text size="sm">Une écriture inverse de {reference} est passée au même journal ; un rapprochement bancaire
          est défait, la transaction redevient à rapprocher.</Text>
        <DateInput label="Date de la contrepassation" required valueFormat="DD/MM/YYYY" {...form.getInputProps("date")} />
        <TextInput label="Motif" required placeholder="Doublon, erreur de compte…" data-autofocus {...form.getInputProps("reason")} />
      </FormBody>
    </form>
  );
}

// ------------------------------------------------------------------ historique

interface SnapshotLine { account: string; label: string; debit_cents: number; credit_cents: number }
interface Snapshot { entry_date: string | null; description: string; journal: string | null; validation_number: number | null; lines: SnapshotLine[] }
interface HistoryEvent { id: number; action: string; at: string; user: string | null; origin: string | null; snapshot: Snapshot | null }

const ACTIONS: Record<string, string> = {
  create: "Création", update: "Modification", delete: "Suppression", validate: "Validation",
  unvalidate: "Dévalidation", reverse: "Contrepassation",
};

const lineKey = (l: SnapshotLine) => `${l.account}|${l.label}|${l.debit_cents}|${l.credit_cents}`;

/** Différences entre deux états : champs de l'en-tête et lignes ajoutées / retirées. */
export function diff(before: Snapshot | null, after: Snapshot | null): { changes: string[]; added: SnapshotLine[]; removed: SnapshotLine[] } {
  if (!before || !after) return { changes: [], added: [], removed: [] };
  const changes: string[] = [];
  if (before.entry_date !== after.entry_date) changes.push(`Date : ${formatDate(before.entry_date ?? "")} → ${formatDate(after.entry_date ?? "")}`);
  if (before.journal !== after.journal) changes.push(`Journal : ${before.journal} → ${after.journal}`);
  if (before.description !== after.description) changes.push(`Description : « ${before.description} » → « ${after.description} »`);
  const pending = before.lines.map(lineKey);
  const added: SnapshotLine[] = [];
  for (const line of after.lines) {
    const i = pending.indexOf(lineKey(line));
    if (i >= 0) pending.splice(i, 1);
    else added.push(line);
  }
  const removed = before.lines.filter((l) => pending.includes(lineKey(l)));
  return { changes, added, removed };
}

function LineText({ line }: { line: SnapshotLine }) {
  return <><span className="lv-num">{line.account}</span> {line.label} · {line.debit_cents
    ? <>débit <MoneyText cents={line.debit_cents} size="sm" /></> : <>crédit <MoneyText cents={line.credit_cents} size="sm" /></>}</>;
}

export function EntryHistory({ entryId }: { entryId: number }) {
  const { data } = useQuery({ queryKey: [...VALIDATION_KEY, "history", entryId],
    queryFn: () => api.get<{ items: HistoryEvent[] }>(`/api/v1/entries/${entryId}/history`) });
  const items = data?.items ?? [];
  return (
    <Paper p="md" mt="md">
      <Title order={3} size="h4" mb="xs">Historique</Title>
      {!items.length && <Text size="sm" c="dimmed">Aucun événement enregistré (écriture antérieure à l'historique).</Text>}
      <Stack gap="xs">
        {items.map((event, i) => {
          const previous = items.slice(0, i).reverse().find((e) => e.snapshot)?.snapshot ?? null;
          const { changes, added, removed } = event.action === "update" ? diff(previous, event.snapshot) : { changes: [], added: [], removed: [] };
          return (
            <div key={event.id}>
              <Text size="sm"><b>{ACTIONS[event.action] ?? event.action}</b>
                {event.action === "validate" && event.snapshot?.validation_number ? ` n° ${event.snapshot.validation_number}` : ""}
                <Text span c="dimmed"> · {new Date(event.at + "Z").toLocaleString("fr-FR")} · {event.user ?? (event.origin === "job" ? "tâche automatique" : "—")}</Text></Text>
              {changes.map((c) => <Text key={c} size="sm" ml="md">{c}</Text>)}
              {removed.map((l, j) => <Text key={`r${j}`} size="sm" ml="md" c="var(--lv-brique)">− <LineText line={l} /></Text>)}
              {added.map((l, j) => <Text key={`a${j}`} size="sm" ml="md" c="var(--lv-lichen-strong)">+ <LineText line={l} /></Text>)}
            </div>
          );
        })}
      </Stack>
    </Paper>
  );
}

// ------------------------------------------------------------------ lots de validation d'un exercice

interface Batch { id: number; kind: string; until_date: string | null; entries: number; at: string; undone_at: string | null; undo_reason: string | null; undoable: boolean }

const KINDS: Record<string, string> = {
  manual: "Sélection", until: "Jusqu'à une date", closing: "Clôture provisoire", auto: "Pièces émises",
  lock: "Verrouillage", import: "Import", migration: "Reprise",
};

export function ValidationBatchesPanel({ fiscalYearId, open }: { fiscalYearId: number; open: boolean }) {
  const can = useCan();
  const key = [...VALIDATION_KEY, "batches", fiscalYearId];
  const { data } = useQuery({ queryKey: key,
    queryFn: () => api.get<{ items: Batch[]; drafts: { drafts: number; old: number } }>(`/api/v1/fiscal-years/${fiscalYearId}/validation-batches`) });
  const [validating, setValidating] = useState(false);
  const [reason, setReason] = useState("");
  const undo = useAction(() => api.post<{ notices: Notice[] }>(`/api/v1/fiscal-years/${fiscalYearId}/validation-batches/last/undo`, { reason }),
    { invalidate: [VALIDATION_KEY, ["entries"]] });
  const last = data?.items.find((b) => b.undoable);
  return (
    <Stack>
      <Group justify="space-between">
        <Text size="sm">{data?.drafts.drafts ?? 0} écriture(s) en brouillard{data?.drafts.old ? `, dont ${data.drafts.old} de plus de 3 mois` : ""}.</Text>
        {open && can.write && !validating && <Button size="compact-sm" onClick={() => setValidating(true)}>Valider jusqu'au…</Button>}
      </Group>
      {validating && <Paper withBorder p="sm"><ValidateUntilForm fiscalYearId={fiscalYearId} invalidate={[["entries"]]} onDone={() => setValidating(false)} /></Paper>}
      <Table>
        <Table.Thead><Table.Tr><Table.Th>Lot</Table.Th><Table.Th>Le</Table.Th><Table.Th ta="right">Écritures</Table.Th><Table.Th /></Table.Tr></Table.Thead>
        <Table.Tbody>
          {(data?.items ?? []).map((b) => (
            <Table.Tr key={b.id}>
              <Table.Td>{KINDS[b.kind] ?? b.kind}{b.until_date ? ` (au ${formatDate(b.until_date)})` : ""}</Table.Td>
              <Table.Td className="lv-num">{formatDate(b.at.slice(0, 10))}</Table.Td>
              <Table.Td ta="right">{b.entries}</Table.Td>
              <Table.Td>{b.undone_at ? <StatusBadge tone="neutral">{`annulé : ${b.undo_reason ?? ""}`}</StatusBadge> : b.undoable ? <StatusBadge tone="info">dernier lot</StatusBadge> : null}</Table.Td>
            </Table.Tr>
          ))}
          {!data?.items.length && <Table.Tr><Table.Td colSpan={4}><Text size="sm" c="dimmed">Aucune écriture validée.</Text></Table.Td></Table.Tr>}
        </Table.Tbody>
      </Table>
      {last && can.instanceAdmin && (
        <Alert color="paille" variant="light" title="Annuler le dernier lot">
          <Text size="sm" mb="xs">Ses {last.entries} écriture(s) repassent en brouillard et perdent leur numéro (les lots précédents ne s'annulent pas).</Text>
          <Group align="flex-end">
            <TextInput label="Motif" value={reason} onChange={(e) => setReason(e.currentTarget.value)} style={{ flex: 1 }} />
            <Button color="brique" variant="default" disabled={!reason.trim()} loading={undo.isPending}
              onClick={() => undo.mutate(undefined, { onSuccess: () => setReason("") })}>Annuler le lot</Button>
          </Group>
        </Alert>
      )}
    </Stack>
  );
}

// Verrouillage des périodes (lot F2) : « Verrouiller jusqu'au… » (les brouillards de la période sont
// validés dans le même geste, aperçu avant) et « Déverrouiller… » (administrateur, motif obligatoire).
import { useState } from "react";
import { Alert, Text, TextInput } from "@mantine/core";
import { DateInput } from "@mantine/dates";
import { useForm } from "@mantine/form";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { applyApiError, FormBody } from "../../components/ApiForm";
import { formatDate } from "../../lib/format";
import { ValidationRefusals, VALIDATION_KEY } from "../entries/validation";

interface Year { id: number; label: string; start_date: string; end_date: string; locked_until?: string | null }
interface Preview { drafts: number; problems: string[] }

const KEYS = [["fiscal-years"], ["entries"], VALIDATION_KEY];

function defaultUntil(fy: Year): string {
  // Fin du mois précédent, dans l'exercice.
  const now = new Date();
  const end = new Date(Date.UTC(now.getFullYear(), now.getMonth(), 0)).toISOString().slice(0, 10);
  return end < fy.start_date ? fy.start_date : end > fy.end_date ? fy.end_date : end;
}

export function LockForm({ fy, onDone }: { fy: Year; onDone: () => void }) {
  const [error, setError] = useState<string | null>(null);
  const form = useForm({ initialValues: { until: defaultUntil(fy) } });
  const until = form.values.until;
  const { data } = useQuery({ queryKey: ["fiscal-years", fy.id, "lock-preview", until], enabled: !!until,
    queryFn: () => api.get<{ preview: Preview }>(`/api/v1/fiscal-years/${fy.id}/period-lock?until=${until}`) });
  const save = useAction((values: typeof form.values) => api.post<{ notices: Notice[] }>(`/api/v1/fiscal-years/${fy.id}/period-lock`, values),
    { invalidate: KEYS, silent: true });
  const preview = data?.preview;
  return (
    <form onSubmit={form.onSubmit((values) => save.mutate(values, { onSuccess: onDone, onError: (e) => setError(applyApiError(form, e)) }))}>
      <FormBody error={error} submitLabel="Verrouiller" onCancel={onDone} loading={save.isPending}>
        <Text size="sm">Plus aucune écriture ne pourra être saisie, modifiée ou supprimée jusqu'à cette date. Les pièces
          reçues ensuite (Qonto, relevés, règlements) seront passées à la première date ouverte.</Text>
        <DateInput label="Verrouiller jusqu'au" required valueFormat="DD/MM/YYYY" minDate={fy.locked_until ?? undefined}
          {...form.getInputProps("until")} />
        {preview && (preview.problems.length
          ? <Alert color="brique" role="alert">{preview.problems.length} écriture(s) à corriger avant de verrouiller :
              {preview.problems.slice(0, 5).map((p) => <Text key={p} size="sm">{p}</Text>)}</Alert>
          : <Text size="sm" c="dimmed">{preview.drafts
              ? `${preview.drafts} écriture(s) en brouillard seront validées (numéro définitif).`
              : "Aucune écriture en brouillard dans la période."}</Text>)}
        <ValidationRefusals error={save.error} />
      </FormBody>
    </form>
  );
}

export function UnlockForm({ fy, onDone }: { fy: Year; onDone: () => void }) {
  const [error, setError] = useState<string | null>(null);
  const form = useForm({ initialValues: { until: "" as string | null, reason: "" },
    validate: { reason: (v) => (v.trim() ? null : "Motif obligatoire.") } });
  const save = useAction((values: typeof form.values) => api.post<{ notices: Notice[] }>(`/api/v1/fiscal-years/${fy.id}/period-lock/rewind`,
    { until: values.until || null, reason: values.reason }), { invalidate: KEYS, silent: true });
  return (
    <form onSubmit={form.onSubmit((values) => save.mutate(values, { onSuccess: onDone, onError: (e) => setError(applyApiError(form, e)) }))}>
      <FormBody error={error} submitLabel="Déverrouiller" onCancel={onDone} loading={save.isPending}>
        <Text size="sm">Verrouillé jusqu'au {formatDate(fy.locked_until ?? "")}. Les écritures validées le restent ;
          celles de la période rouverte redeviennent saisissables (contrepassation pour les validées).</Text>
        <DateInput label="Nouvelle date de verrouillage" description="Vide : plus aucun verrou" clearable valueFormat="DD/MM/YYYY"
          maxDate={fy.locked_until ?? undefined} {...form.getInputProps("until")} />
        <TextInput label="Motif" required data-autofocus {...form.getInputProps("reason")} />
      </FormBody>
    </form>
  );
}

// Compta › Exercices : liste, création, assujettissement à la TVA ; la clôture passe par l'assistant (ClosingPage).
import { useState } from "react";
import { Button, Checkbox, Group, Text, TextInput } from "@mantine/core";
import { DateInput } from "@mantine/dates";
import { useForm } from "@mantine/form";
import { api } from "../../api/client";
import { useAction, useList, type Notice } from "../../api/resources";
import { applyApiError, FormBody } from "../../components/ApiForm";
import { confirmAction } from "../../components/ConfirmButton";
import { VatMenu, type VatPatch } from "./VatMenu";
import { DataGrid, type GridColumn } from "../../components/DataGrid";
import { FormModal } from "../../components/FormModal";
import { PageHeader } from "../../components/PageHeader";
import { Can } from "../../components/Can";
import { SESSION_KEY, useBookkeeping, useCan, useCurrentSession } from "../../api/session";
import { StatusBadge } from "../../components/StatusBadge";
import { formatDate } from "../../lib/format";
import { useRouteModal } from "../../app/useRouteModal";
import { AppLink } from "../../app/navigation";
import { FecPanel } from "./FecPanel";
import { ValidationBatchesPanel } from "../entries/validation";
import { LockForm, UnlockForm } from "./PeriodLock";

export interface FiscalYear {
  id: number; label: string; start_date: string; end_date: string; closed: boolean; vat_liable: boolean; vat_on_receipts?: boolean;
  /** Lot T3 : déclaration de TVA préparée dans Lyvre (`monthly` : CA3 mensuelle). */
  vat_period?: "monthly" | "quarterly" | "annual" | null;
  status: "open" | "provisional" | "closed"; status_label: string;
  /** Lot F2 : date de verrouillage, première date où l'on peut écrire. */
  locked_until?: string | null; first_open_date?: string | null;
}

const STATUS_TONES = { open: "ok", provisional: "todo", closed: "neutral" } as const;

export const FISCAL_YEARS_KEY = ["fiscal-years"];

/** Exercice suivant le dernier connu (dates ISO, libellé = année de début). */
export function nextFiscalYear(years: FiscalYear[] | undefined) {
  const last = [...(years ?? [])].sort((a, b) => b.end_date.localeCompare(a.end_date))[0];
  if (!last) {
    const year = new Date().getFullYear();
    return { label: String(year), start_date: `${year}-01-01`, end_date: `${year}-12-31` };
  }
  const start = new Date(`${last.end_date}T12:00:00Z`);
  start.setUTCDate(start.getUTCDate() + 1);
  const end = new Date(start);
  end.setUTCFullYear(end.getUTCFullYear() + 1);
  end.setUTCDate(end.getUTCDate() - 1);
  const iso = (d: Date) => d.toISOString().slice(0, 10);
  return { label: String(start.getUTCFullYear()), start_date: iso(start), end_date: iso(end) };
}

function FiscalYearForm({ years, onDone }: { years: FiscalYear[] | undefined; onDone: () => void }) {
  const [error, setError] = useState<string | null>(null);
  const form = useForm({ initialValues: { ...nextFiscalYear(years), vat_liable: false } });
  const create = useAction((values: typeof form.values) =>
    api.post<{ notices: Notice[] }>("/api/v1/fiscal-years", values), { invalidate: [FISCAL_YEARS_KEY], silent: true });
  return (
    <form onSubmit={form.onSubmit((values) => create.mutate(values, {
      onSuccess: onDone, onError: (e) => setError(applyApiError(form, e)),
    }))}>
      <FormBody error={error} submitLabel="Créer l'exercice" onCancel={onDone} loading={create.isPending}>
        <TextInput label="Libellé" required data-autofocus {...form.getInputProps("label")} />
        <Group grow>
          <DateInput label="Début" required valueFormat="DD/MM/YYYY" {...form.getInputProps("start_date")} />
          <DateInput label="Fin" required valueFormat="DD/MM/YYYY" {...form.getInputProps("end_date")} />
        </Group>
        <Checkbox label="Soumis à la TVA" description="La TVA des achats va en 44566 ; sinon elle est incluse dans la charge."
          {...form.getInputProps("vat_liable", { type: "checkbox" })} />
      </FormBody>
    </form>
  );
}

export default function FiscalYearsPage() {
  const modal = useRouteModal("/fiscal-years/");
  const [fecFor, setFecFor] = useState<FiscalYear | null>(null);
  const [batchesFor, setBatchesFor] = useState<FiscalYear | null>(null);
  const [lockFor, setLockFor] = useState<FiscalYear | null>(null);
  const [unlockFor, setUnlockFor] = useState<FiscalYear | null>(null);
  const { data, isFetching } = useList<FiscalYear>(FISCAL_YEARS_KEY, "/api/v1/fiscal-years");
  const setVat = useAction(({ fy, patch }: { fy: FiscalYear; patch: VatPatch }) =>
    api.patch<{ notices: Notice[] }>(`/api/v1/fiscal-years/${fy.id}`, patch),
    { invalidate: [FISCAL_YEARS_KEY, SESSION_KEY] });  // le rythme change le menu « Déclarations de TVA »
  const simple = useBookkeeping() === "simple";
  const agri = useCurrentSession().instance?.chart === "agri";
  const can = useCan();
  const lock = useAction((fy: FiscalYear) => api.post<{ notices: Notice[] }>(`/api/v1/fiscal-years/${fy.id}/lock`,
    { locked: fy.status === "open" }), { invalidate: [FISCAL_YEARS_KEY] });

  // Comptabilité simplifiée : ni FEC ni assistant de clôture, un verrouillage simple.
  const closingColumns: GridColumn<FiscalYear>[] = simple ? [
    { accessor: "closing", title: "Verrouillage", hideable: false,
      render: (fy) => (fy.status === "open" ? can.write : can.instanceAdmin) ? (
        <Button variant={fy.status === "open" ? "default" : "subtle"} size="compact-sm" loading={lock.isPending && lock.variables?.id === fy.id}
          onClick={() => confirmAction({
            title: fy.status === "open" ? `Verrouiller l'exercice ${fy.label} ?` : `Déverrouiller l'exercice ${fy.label} ?`,
            confirmLabel: fy.status === "open" ? "Verrouiller" : "Déverrouiller", danger: fy.status !== "open",
            message: fy.status === "open" ? "Les opérations de l'exercice ne pourront plus être saisies ni modifiées."
              : "Les opérations redeviennent modifiables.",
            onConfirm: () => lock.mutate(fy),
          })}>{fy.status === "open" ? "Verrouiller" : "Déverrouiller"}</Button>) : null },
  ] : [
    { accessor: "locked_until", title: "Verrouillage", hideable: false,
      render: (fy) => (
        <Group gap={6} wrap="nowrap">
          {fy.locked_until ? <Text size="sm" className="lv-num">{`jusqu'au ${formatDate(fy.locked_until)}`}</Text> : <Text size="sm" c="dimmed">—</Text>}
          {fy.status === "open" && can.write && fy.first_open_date &&
            <Button variant="subtle" size="compact-sm" onClick={() => setLockFor(fy)}>Verrouiller…</Button>}
          {fy.status === "open" && can.instanceAdmin && fy.locked_until &&
            <Button variant="subtle" size="compact-sm" onClick={() => setUnlockFor(fy)}>Déverrouiller…</Button>}
        </Group>) },
    { accessor: "validation", title: "Validation", hideable: false,
      render: (fy) => <Button variant="subtle" size="compact-sm" onClick={() => setBatchesFor(fy)}>Lots</Button> },
    // Hors colonne « actions » : l'expert-comptable (lecture seule) exporte aussi le FEC.
    { accessor: "fec", title: "FEC", hideable: false,
      render: (fy) => fy.status === "open" ? <Text size="sm" c="dimmed">après clôture</Text>
        : <Button variant="subtle" size="compact-sm" onClick={() => setFecFor(fy)}>FEC</Button> },
    { accessor: "closing", title: "Clôture", hideable: false,
      render: (fy) => <Button variant={fy.status === "open" ? "default" : "subtle"} size="compact-sm" component={AppLink}
        href={`/fiscal-years/${fy.id}/closing`}>{fy.status === "open" ? "Clôturer…" : "Assistant"}</Button> },
  ];

  const columns: GridColumn<FiscalYear>[] = [
    { accessor: "label", title: "Libellé", hideable: false },
    { accessor: "start_date", title: "Début", render: (fy) => <span className="lv-num">{formatDate(fy.start_date)}</span> },
    { accessor: "end_date", title: "Fin", render: (fy) => <span className="lv-num">{formatDate(fy.end_date)}</span> },
    { accessor: "status", title: "Statut",
      render: (fy) => <StatusBadge tone={STATUS_TONES[fy.status] ?? "neutral"}>{fy.status_label}</StatusBadge> },
    { accessor: "vat_liable", title: "TVA",
      render: (fy) => <Group gap={6} wrap="nowrap">
        <StatusBadge tone={fy.vat_liable ? "info" : "neutral"}>{fy.vat_liable ? "Soumis" : "Non soumis"}</StatusBadge>
        {fy.vat_liable && <Text size="xs" c="dimmed">{fy.vat_on_receipts === false ? "services : sur les débits" : "services : à l'encaissement"}
          {fy.vat_period === "monthly" && " · CA3 mensuelle"}{fy.vat_period === "quarterly" && " · CA3 trimestrielle"}{fy.vat_period === "annual" && " · CA12A annuelle"}</Text>}
      </Group> },
    ...closingColumns,
    { accessor: "actions", title: "", hideable: false, textAlign: "right",
      render: (fy) => fy.closed ? null : (
        <VatMenu fy={fy} agri={agri} simple={simple} loading={setVat.isPending && setVat.variables?.fy.id === fy.id}
          onChange={(patch) => setVat.mutate({ fy, patch })} />
      ) },
  ];

  return (
    <>
      <PageHeader title="Exercices" description="Un exercice ouvert reçoit les écritures ; une fois clôturé, il est figé."
        actions={<Can><Button onClick={modal.openNew}>Créer un exercice</Button></Can>} />
      <DataGrid id="fiscal-years" records={data?.items} columns={columns} fetching={isFetching}
        emptyText="Aucun exercice : créez le premier pour commencer à saisir." />
      <FormModal opened={modal.mode === "new"} onClose={modal.close} title="Créer un exercice">
        <FiscalYearForm years={data?.items} onDone={modal.close} />
      </FormModal>
      <FormModal opened={!!lockFor} onClose={() => setLockFor(null)} title={`Verrouiller l'exercice ${lockFor?.label ?? ""}`}>
        {lockFor && <LockForm fy={lockFor} onDone={() => setLockFor(null)} />}
      </FormModal>
      <FormModal opened={!!unlockFor} onClose={() => setUnlockFor(null)} title={`Déverrouiller l'exercice ${unlockFor?.label ?? ""}`}>
        {unlockFor && <UnlockForm fy={unlockFor} onDone={() => setUnlockFor(null)} />}
      </FormModal>
      <FormModal opened={!!batchesFor} onClose={() => setBatchesFor(null)} title={`Validation des écritures — ${batchesFor?.label ?? ""}`} size="lg">
        {batchesFor && <ValidationBatchesPanel fiscalYearId={batchesFor.id} open={batchesFor.status === "open"} />}
      </FormModal>
      <FormModal opened={!!fecFor} onClose={() => setFecFor(null)} title={`Fichier des écritures comptables — ${fecFor?.label ?? ""}`} size="lg">
        {fecFor && <FecPanel fiscalYearId={fecFor.id} />}
      </FormModal>
    </>
  );
}

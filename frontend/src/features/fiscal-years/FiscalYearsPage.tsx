// Compta › Exercices : liste, création, assujettissement à la TVA, clôture.
import { useState } from "react";
import { Button, Checkbox, Group, TextInput } from "@mantine/core";
import { DateInput } from "@mantine/dates";
import { useForm } from "@mantine/form";
import { api } from "../../api/client";
import { useAction, useList, type Notice } from "../../api/resources";
import { applyApiError, FormBody } from "../../components/ApiForm";
import { confirmAction } from "../../components/ConfirmButton";
import { DataGrid, type GridColumn } from "../../components/DataGrid";
import { FormModal } from "../../components/FormModal";
import { PageHeader } from "../../components/PageHeader";
import { Can } from "../../components/Can";
import { StatusBadge } from "../../components/StatusBadge";
import { formatDate } from "../../lib/format";
import { useRouteModal } from "../../app/useRouteModal";

export interface FiscalYear {
  id: number; label: string; start_date: string; end_date: string; closed: boolean; vat_liable: boolean;
}

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
  const { data, isFetching } = useList<FiscalYear>(FISCAL_YEARS_KEY, "/api/v1/fiscal-years");
  const close = useAction((fy: FiscalYear) => api.post<{ notices: Notice[] }>(`/api/v1/fiscal-years/${fy.id}/close`),
    { invalidate: [FISCAL_YEARS_KEY] });
  const setVat = useAction((fy: FiscalYear) =>
    api.patch<{ notices: Notice[] }>(`/api/v1/fiscal-years/${fy.id}`, { vat_liable: !fy.vat_liable }),
    { invalidate: [FISCAL_YEARS_KEY] });

  const columns: GridColumn<FiscalYear>[] = [
    { accessor: "label", title: "Libellé", hideable: false },
    { accessor: "start_date", title: "Début", render: (fy) => <span className="lv-num">{formatDate(fy.start_date)}</span> },
    { accessor: "end_date", title: "Fin", render: (fy) => <span className="lv-num">{formatDate(fy.end_date)}</span> },
    { accessor: "closed", title: "Statut",
      render: (fy) => <StatusBadge tone={fy.closed ? "neutral" : "ok"}>{fy.closed ? "Clôturé" : "Ouvert"}</StatusBadge> },
    { accessor: "vat_liable", title: "TVA",
      render: (fy) => <StatusBadge tone={fy.vat_liable ? "info" : "neutral"}>{fy.vat_liable ? "Soumis" : "Non soumis"}</StatusBadge> },
    { accessor: "actions", title: "", hideable: false, textAlign: "right",
      render: (fy) => fy.closed ? null : (
        <Group gap="xs" justify="flex-end" wrap="nowrap">
          <Button variant="subtle" size="compact-sm" loading={setVat.isPending && setVat.variables?.id === fy.id}
            title="S'applique aux factures comptabilisées à partir de maintenant"
            onClick={() => setVat.mutate(fy)}>
            {fy.vat_liable ? "Déclarer non soumis" : "Déclarer soumis"}
          </Button>
          <Button variant="default" size="compact-sm" color="brique"
            onClick={() => confirmAction({
              title: `Clôturer l'exercice ${fy.label} ?`,
              message: "Ses écritures ne pourront plus être modifiées ni supprimées. Cette action est irréversible.",
              confirmLabel: "Clôturer l'exercice",
              onConfirm: () => close.mutate(fy),
            })}>
            Clôturer
          </Button>
        </Group>
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
    </>
  );
}

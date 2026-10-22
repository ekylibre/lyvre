// Tiers › Temps de travaux : liste filtrée (bénévole, tâche, mois) avec totaux, saisie.
import { useState } from "react";
import { Anchor, Button, Group, NumberInput, Select, Text, Textarea } from "@mantine/core";
import { DateInput } from "@mantine/dates";
import { useForm } from "@mantine/form";
import { api } from "../../api/client";
import { useAction, useList, type Notice } from "../../api/resources";
import { applyApiError, FormBody } from "../../components/ApiForm";
import { confirmAction } from "../../components/ConfirmButton";
import { DataGrid, type GridColumn } from "../../components/DataGrid";
import { FilterBar, useUrlParams } from "../../components/FilterBar";
import { FormModal } from "../../components/FormModal";
import { MoneyText } from "../../components/Money";
import { MonthSelect, type MonthOption } from "../../components/MonthSelect";
import { PageHeader } from "../../components/PageHeader";
import { formatDate } from "../../lib/format";
import { AppLink } from "../../app/navigation";
import { useRouteModal } from "../../app/useRouteModal";

export interface WorkTime {
  id: number; entity_id: number; entity_name: string; task_type_id: number; task_type: string;
  work_date: string; hours: number; valuation_cents: number; notes: string | null;
}
interface Meta {
  benevoles: { value: string; label: string }[];
  task_types: { value: string; label: string; active: boolean }[];
  months: MonthOption[]; total_hours: number; total_valuation_cents: number;
}

export const WORK_TIMES_KEY = ["work-times"];
export const formatHours = (h: number) => `${h.toLocaleString("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} h`;

function WorkTimeForm({ workTime, meta, onDone }: { workTime: WorkTime | null; meta: Meta | undefined; onDone: () => void }) {
  const [error, setError] = useState<string | null>(null);
  const form = useForm({
    initialValues: {
      entity_id: workTime ? String(workTime.entity_id) : "", task_type_id: workTime ? String(workTime.task_type_id) : "",
      work_date: workTime?.work_date ?? new Date().toISOString().slice(0, 10),
      hours: workTime?.hours ?? ("" as number | ""), notes: workTime?.notes ?? "",
    },
  });
  const save = useAction((values: typeof form.values) => {
    const body = { ...values, hours: values.hours === "" ? null : values.hours };
    return workTime ? api.patch<{ notices: Notice[] }>(`/api/v1/work-times/${workTime.id}`, body)
      : api.post<{ notices: Notice[] }>("/api/v1/work-times", body);
  }, { invalidate: [WORK_TIMES_KEY], silent: true });
  // Types actifs seulement, plus celui du temps modifié s'il a été désactivé.
  const taskTypes = (meta?.task_types ?? []).filter((t) => t.active || t.value === form.values.task_type_id);
  return (
    <form onSubmit={form.onSubmit((values) => save.mutate(values, {
      onSuccess: onDone, onError: (e) => setError(applyApiError(form, e)),
    }))}>
      <FormBody error={error} submitLabel={workTime ? "Enregistrer" : "Enregistrer le temps"} onCancel={onDone}
        loading={save.isPending}>
        <Select label="Bénévole" required searchable data={meta?.benevoles ?? []} data-autofocus
          nothingFoundMessage="Aucun bénévole : cochez « Bénévole » sur la fiche du tiers."
          {...form.getInputProps("entity_id")} />
        <Select label="Type de tâche" required data={taskTypes} {...form.getInputProps("task_type_id")} />
        <Group grow align="flex-start">
          <DateInput label="Date" required valueFormat="DD/MM/YYYY" {...form.getInputProps("work_date")} />
          <NumberInput label="Heures" required decimalSeparator="," decimalScale={2} min={0} max={24} step={0.5}
            {...form.getInputProps("hours")} />
        </Group>
        <Textarea label="Notes" autosize minRows={2} {...form.getInputProps("notes")} />
      </FormBody>
    </form>
  );
}

export default function WorkTimesPage() {
  const modal = useRouteModal("/work-times/", "work_time_id");
  const [params, setParams] = useUrlParams({ entity_id: "", task_type_id: "", month: "", sort: "desc" });
  const query = new URLSearchParams(Object.entries(params).filter(([, v]) => v)).toString();
  const { data, isFetching } = useList<WorkTime, Meta>(WORK_TIMES_KEY, `/api/v1/work-times${query ? `?${query}` : ""}`);
  const meta = data?.meta;
  const editing = modal.mode === "edit" ? data?.items.find((w) => w.id === modal.id) ?? null : null;
  const remove = useAction((w: WorkTime) => api.delete<{ notices: Notice[] }>(`/api/v1/work-times/${w.id}`),
    { invalidate: [WORK_TIMES_KEY] });

  const columns: GridColumn<WorkTime>[] = [
    { accessor: "work_date", title: "Date", sortable: true, hideable: false,
      render: (w) => <span className="lv-num">{formatDate(w.work_date)}</span> },
    { accessor: "entity_name", title: "Bénévole",
      render: (w) => <Anchor component={AppLink} href={`/entities/${w.entity_id}`}>{w.entity_name}</Anchor> },
    { accessor: "task_type", title: "Tâche" },
    { accessor: "hours", title: "Heures", textAlign: "right", render: (w) => <span className="lv-num">{formatHours(w.hours)}</span> },
    { accessor: "valuation_cents", title: "Valorisation", textAlign: "right", render: (w) => <MoneyText cents={w.valuation_cents} /> },
    { accessor: "notes", title: "Notes", render: (w) => <Text size="sm" c="dimmed" lineClamp={1}>{w.notes ?? ""}</Text> },
    { accessor: "actions", title: "", hideable: false, textAlign: "right",
      render: (w) => (
        <Group gap={4} justify="flex-end" wrap="nowrap">
          <Button variant="subtle" size="compact-sm" onClick={() => modal.openEdit(w.id)}>Modifier</Button>
          <Button variant="subtle" size="compact-sm" color="brique"
            onClick={() => confirmAction({ title: "Supprimer ce temps ?", confirmLabel: "Supprimer",
              message: `${w.entity_name}, ${formatDate(w.work_date)}, ${formatHours(w.hours)}.`,
              onConfirm: () => remove.mutate(w) })}>Supprimer</Button>
        </Group>
      ) },
  ];

  return (
    <>
      <PageHeader title="Temps de travaux" description="Heures données par les bénévoles, valorisées au taux de chaque type de tâche."
        actions={<>
          <Button variant="default" component={AppLink} href="/work-times/task-types">Types de tâches</Button>
          <Button variant="default" component={AppLink} href="/work-times/import">Importer</Button>
          <Button onClick={modal.openNew}>Saisir un temps</Button>
        </>} />
      <FilterBar>
        <Select label="Bénévole" placeholder="Tous" clearable searchable data={meta?.benevoles ?? []} w={220}
          value={params.entity_id || null} onChange={(v) => setParams({ entity_id: v ?? "" })} />
        <Select label="Type de tâche" placeholder="Tous" clearable data={meta?.task_types ?? []} w={200}
          value={params.task_type_id || null} onChange={(v) => setParams({ task_type_id: v ?? "" })} />
        <MonthSelect value={params.month} onChange={(month) => setParams({ month })} options={meta?.months} />
      </FilterBar>
      <DataGrid id="work-times" records={data?.items} columns={columns} fetching={isFetching} perPage={100}
        sort={{ column: "work_date", direction: params.sort === "asc" ? "asc" : "desc" }}
        onSortChange={(s) => setParams({ sort: s.direction })}
        toolbar={meta && <Text size="sm">{data?.items.length} temps · <b className="lv-num">{formatHours(meta.total_hours)}</b> ·{" "}
          <MoneyText cents={meta.total_valuation_cents} fw={600} /></Text>}
        emptyText="Aucun temps saisi pour ces critères." />
      <FormModal opened={modal.mode === "new" || (modal.mode === "edit" && !!editing)} onClose={modal.close}
        title={editing ? "Modifier le temps" : "Saisir un temps"}>
        <WorkTimeForm key={editing?.id ?? "new"} workTime={editing} meta={meta} onDone={modal.close} />
      </FormModal>
    </>
  );
}

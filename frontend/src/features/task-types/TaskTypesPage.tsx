// Tiers › Temps de travaux › Types de tâches : nom, taux horaire, activation.
import { useState } from "react";
import { Anchor, Button, Group, Switch, TextInput } from "@mantine/core";
import { useForm } from "@mantine/form";
import { api } from "../../api/client";
import { useAction, useList, type Notice } from "../../api/resources";
import { applyApiError, FormBody } from "../../components/ApiForm";
import { confirmAction } from "../../components/ConfirmButton";
import { DataGrid, type GridColumn } from "../../components/DataGrid";
import { FormModal } from "../../components/FormModal";
import { MoneyInput, MoneyText } from "../../components/Money";
import { PageHeader } from "../../components/PageHeader";
import { StatusBadge } from "../../components/StatusBadge";
import { useRouteModal } from "../../app/useRouteModal";

export interface TaskType { id: number; name: string; hourly_rate_cents: number; is_active: boolean; work_times: number }

const KEY = ["task-types"];

function TaskTypeForm({ taskType, onDone }: { taskType: TaskType | null; onDone: () => void }) {
  const [error, setError] = useState<string | null>(null);
  const form = useForm({
    initialValues: {
      name: taskType?.name ?? "", hourly_rate_cents: taskType?.hourly_rate_cents ?? 0,
      is_active: taskType?.is_active ?? true,
    },
  });
  const save = useAction((values: typeof form.values) => taskType
    ? api.patch<{ notices: Notice[] }>(`/api/v1/task-types/${taskType.id}`, values)
    : api.post<{ notices: Notice[] }>("/api/v1/task-types", values), { invalidate: [KEY], silent: true });
  return (
    <form onSubmit={form.onSubmit((values) => save.mutate(values, {
      onSuccess: onDone, onError: (e) => setError(applyApiError(form, e)),
    }))}>
      <FormBody error={error} submitLabel={taskType ? "Enregistrer" : "Créer le type"} onCancel={onDone}
        loading={save.isPending}>
        <TextInput label="Nom" required data-autofocus {...form.getInputProps("name")} />
        <MoneyInput label="Taux horaire" description="Valorisation d'une heure de bénévolat." w={220}
          value={form.values.hourly_rate_cents} error={form.errors.hourly_rate_cents}
          onChange={(v) => form.setFieldValue("hourly_rate_cents", v ?? 0)} />
        <Switch label="Proposé à la saisie" {...form.getInputProps("is_active", { type: "checkbox" })} />
      </FormBody>
    </form>
  );
}

export default function TaskTypesPage() {
  const modal = useRouteModal("/work-times/task-types", "task_type_id");
  const { data, isFetching } = useList<TaskType>(KEY, "/api/v1/task-types");
  const editing = modal.mode === "edit" ? data?.items.find((t) => t.id === modal.id) ?? null : null;
  const remove = useAction((t: TaskType) => api.delete<{ notices: Notice[] }>(`/api/v1/task-types/${t.id}`),
    { invalidate: [KEY] });

  const columns: GridColumn<TaskType>[] = [
    { accessor: "name", title: "Nom", sortable: true, hideable: false },
    { accessor: "hourly_rate_cents", title: "Taux horaire", sortable: true, textAlign: "right",
      render: (t) => <><MoneyText cents={t.hourly_rate_cents} /> / h</> },
    { accessor: "is_active", title: "Statut",
      render: (t) => <StatusBadge tone={t.is_active ? "ok" : "neutral"}>{t.is_active ? "Actif" : "Inactif"}</StatusBadge> },
    { accessor: "work_times", title: "Temps saisis", sortable: true, textAlign: "right",
      render: (t) => <span className="lv-num">{t.work_times}</span> },
    { accessor: "actions", title: "", hideable: false, textAlign: "right",
      render: (t) => (
        <Group gap={4} justify="flex-end" wrap="nowrap">
          <Button variant="subtle" size="compact-sm" onClick={() => modal.openEdit(t.id)}>Modifier</Button>
          {t.work_times === 0 && (
            <Button variant="subtle" size="compact-sm" color="brique"
              onClick={() => confirmAction({ title: `Supprimer le type « ${t.name} » ?`, confirmLabel: "Supprimer",
                onConfirm: () => remove.mutate(t) })}>Supprimer</Button>
          )}
        </Group>
      ) },
  ];

  return (
    <>
      <PageHeader title="Types de tâches"
        description={<>Les tâches proposées à la saisie des <Anchor href="/work-times/">temps de travaux</Anchor> et leur valorisation.</>}
        actions={<Button onClick={modal.openNew}>Créer un type</Button>} />
      <DataGrid id="task-types" records={data?.items} columns={columns} fetching={isFetching}
        defaultSort={{ column: "name", direction: "asc" }} emptyText="Aucun type de tâche." />
      <FormModal opened={modal.mode === "new" || (modal.mode === "edit" && !!editing)} onClose={modal.close}
        title={editing ? `Modifier « ${editing.name} »` : "Créer un type de tâche"}>
        <TaskTypeForm key={editing?.id ?? "new"} taskType={editing} onDone={modal.close} />
      </FormModal>
    </>
  );
}

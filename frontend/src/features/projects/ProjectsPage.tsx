// Compta › Projets : projets / activités (axe analytique unique), charges et produits affectés
// (tous exercices ou un exercice), création, modification, archivage.
import { useState } from "react";
import { Button, Group, Select, Switch, Text, Textarea, TextInput } from "@mantine/core";
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
import { PageHeader } from "../../components/PageHeader";
import { Can } from "../../components/Can";
import { StatusBadge } from "../../components/StatusBadge";
import { formatDate } from "../../lib/format";
import { useRouteModal } from "../../app/useRouteModal";
import { AppLink } from "../../app/navigation";
import { FISCAL_YEARS_KEY, type FiscalYear } from "../fiscal-years/FiscalYearsPage";

export interface Project {
  id: number; name: string; description: string; start_date: string | null; end_date: string | null;
  manager: string; archived: boolean; expense_cents: number; income_cents: number; result_cents: number; lines: number;
}

export const PROJECTS_KEY = ["projects"];

function ProjectForm({ project, onDone }: { project: Project | null; onDone: () => void }) {
  const [error, setError] = useState<string | null>(null);
  const form = useForm({
    initialValues: {
      name: project?.name ?? "", description: project?.description ?? "", manager: project?.manager ?? "",
      start_date: project?.start_date ?? null as string | null, end_date: project?.end_date ?? null as string | null,
      archived: project?.archived ?? false,
    },
  });
  const save = useAction((values: typeof form.values) => project
    ? api.put<{ notices: Notice[] }>(`/api/v1/projects/${project.id}`, values)
    : api.post<{ notices: Notice[] }>("/api/v1/projects", values), { invalidate: [PROJECTS_KEY], silent: true });
  return (
    <form onSubmit={form.onSubmit((values) => save.mutate(values, {
      onSuccess: onDone, onError: (e) => setError(applyApiError(form, e)),
    }))}>
      <FormBody error={error} submitLabel={project ? "Enregistrer" : "Créer le projet"} onCancel={onDone} loading={save.isPending}>
        <TextInput label="Nom" required data-autofocus {...form.getInputProps("name")} />
        <Textarea label="Description" autosize minRows={2} {...form.getInputProps("description")} />
        <Group grow>
          <DateInput label="Début" clearable valueFormat="DD/MM/YYYY" {...form.getInputProps("start_date")} />
          <DateInput label="Fin" clearable valueFormat="DD/MM/YYYY" {...form.getInputProps("end_date")} />
        </Group>
        <TextInput label="Responsable" {...form.getInputProps("manager")} />
        {project && <Switch label="Archivé (n'est plus proposé à la saisie)" {...form.getInputProps("archived", { type: "checkbox" })} />}
      </FormBody>
    </form>
  );
}

export default function ProjectsPage() {
  const modal = useRouteModal("/projects/", "project_id");
  const [params, setParams] = useUrlParams({ fiscal_year_id: "" });
  const years = useList<FiscalYear>(FISCAL_YEARS_KEY, "/api/v1/fiscal-years");
  const url = `/api/v1/projects${params.fiscal_year_id ? `?fiscal_year_id=${params.fiscal_year_id}` : ""}`;
  const { data, isFetching } = useList<Project>(PROJECTS_KEY, url);
  const editing = modal.mode === "edit" ? data?.items.find((p) => p.id === modal.id) ?? null : null;
  const remove = useAction((p: Project) => api.delete<{ notices: Notice[] }>(`/api/v1/projects/${p.id}`),
    { invalidate: [PROJECTS_KEY] });

  const columns: GridColumn<Project>[] = [
    { accessor: "name", title: "Projet", sortable: true, hideable: false,
      render: (p) => <Group gap="xs">{p.name}{p.archived && <StatusBadge tone="neutral">Archivé</StatusBadge>}</Group> },
    { accessor: "start_date", title: "Période", sortable: true,
      render: (p) => <span className="lv-num">{p.start_date || p.end_date ? `${formatDate(p.start_date) || "…"} → ${formatDate(p.end_date) || "…"}` : "—"}</span> },
    { accessor: "manager", title: "Responsable", render: (p) => p.manager || <Text c="dimmed">—</Text> },
    { accessor: "expense_cents", title: "Charges", sortable: true, textAlign: "right", render: (p) => <MoneyText cents={p.expense_cents} /> },
    { accessor: "income_cents", title: "Produits", sortable: true, textAlign: "right", render: (p) => <MoneyText cents={p.income_cents} /> },
    { accessor: "result_cents", title: "Résultat", sortable: true, textAlign: "right",
      render: (p) => <MoneyText cents={p.result_cents} anomaly={p.result_cents < 0} /> },
    { accessor: "actions", title: "", hideable: false, textAlign: "right",
      render: (p) => (
        <Group gap={4} justify="flex-end" wrap="nowrap">
          <Button variant="subtle" size="compact-sm" component={AppLink} href={`/projects/${p.id}/statement`}>Compte de résultat</Button>
          <Button variant="subtle" size="compact-sm" onClick={() => modal.openEdit(p.id)}>Modifier</Button>
          {p.lines === 0 && (
            <Button variant="subtle" size="compact-sm" color="brique" onClick={() => confirmAction({
              title: `Supprimer le projet « ${p.name} » ?`, confirmLabel: "Supprimer", onConfirm: () => remove.mutate(p),
            })}>Supprimer</Button>
          )}
        </Group>
      ) },
  ];

  return (
    <>
      <PageHeader title="Projets" description="Projets et activités : affectez-leur des lignes d'écriture, de facture d'achat ou des règles."
        actions={<Can><Button onClick={modal.openNew}>Créer un projet</Button></Can>} />
      <FilterBar>
        <Select aria-label="Exercice" placeholder="Tous les exercices" clearable w={220}
          data={(years.data?.items ?? []).map((fy) => ({ value: String(fy.id), label: `Exercice ${fy.label}` }))}
          value={params.fiscal_year_id || null} onChange={(v) => setParams({ fiscal_year_id: v ?? "" })} />
      </FilterBar>
      <DataGrid id="projects" records={data?.items} columns={columns} fetching={isFetching}
        defaultSort={{ column: "name", direction: "asc" }}
        emptyText="Aucun projet. Créez vos projets ou activités pour suivre leurs charges et produits." />
      <FormModal opened={modal.mode === "new" || (modal.mode === "edit" && !!editing)} onClose={modal.close}
        title={editing ? `Modifier « ${editing.name} »` : "Créer un projet"}>
        <ProjectForm key={editing?.id ?? "new"} project={editing} onDone={modal.close} />
      </FormModal>
    </>
  );
}

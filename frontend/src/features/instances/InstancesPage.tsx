// Administration › Instances : bases comptables (une par structure) ; création, modification.
import { useState } from "react";
import { Anchor, Button, Code, SegmentedControl, Select, Stack, Switch, Text, TextInput } from "@mantine/core";
import { useForm } from "@mantine/form";
import { api } from "../../api/client";
import { useAction, useList, type Notice } from "../../api/resources";
import { applyApiError, FormBody } from "../../components/ApiForm";
import { DataGrid, type GridColumn } from "../../components/DataGrid";
import { FormModal } from "../../components/FormModal";
import { PageHeader } from "../../components/PageHeader";
import { StatusBadge } from "../../components/StatusBadge";
import { AppLink } from "../../app/navigation";
import { useRouteModal } from "../../app/useRouteModal";
import { INSTANCES_KEY, type Instance } from "./types";

interface Meta { charts: { value: string; label: string }[]; default_chart: string }

function CreateForm({ meta, onDone }: { meta: Meta | undefined; onDone: () => void }) {
  const [error, setError] = useState<string | null>(null);
  const form = useForm({ initialValues: { slug: "", label: "", provisioning_mode: "auto", chart: meta?.default_chart ?? "asso", database_url: "" } });
  const save = useAction((values: typeof form.values) => api.post<{ notices: Notice[] }>("/api/v1/instances", values),
    { invalidate: [INSTANCES_KEY], silent: true });
  const auto = form.values.provisioning_mode === "auto";
  return (
    <form onSubmit={form.onSubmit((values) => save.mutate(values, { onSuccess: onDone, onError: (e) => setError(applyApiError(form, e)) }))}>
      <FormBody error={error} submitLabel="Créer l'instance" onCancel={onDone} loading={save.isPending}>
        <TextInput label="Slug" required data-autofocus description="Lettres minuscules, chiffres et tirets ; sert de nom au fichier SQLite."
          classNames={{ input: "lv-num" }} {...form.getInputProps("slug")} />
        <TextInput label="Libellé" required {...form.getInputProps("label")} />
        <Stack gap={4}>
          <Text size="sm" fw={500}>Création de la base</Text>
          <SegmentedControl data={[{ value: "auto", label: "Automatique" }, { value: "manual", label: "Base existante" }]}
            {...form.getInputProps("provisioning_mode")} />
          <Text size="xs" c="dimmed">{auto
            ? "Crée instance/tenants/<slug>.db, applique le schéma, charge le plan comptable choisi et les journaux."
            : "URL d'une base déjà initialisée (PostgreSQL, ou SQLite relative au dossier instance/)."}</Text>
        </Stack>
        {auto
          ? <Select label="Plan comptable" data={meta?.charts ?? []} allowDeselect={false} description="Pilote aussi les menus affichés."
            {...form.getInputProps("chart")} />
          : <TextInput label="URL de base de données" required placeholder="postgresql://utilisateur:motdepasse@hôte/base"
            classNames={{ input: "lv-num" }} autoComplete="off" {...form.getInputProps("database_url")} />}
      </FormBody>
    </form>
  );
}

function EditForm({ instance, onDone }: { instance: Instance; onDone: () => void }) {
  const [error, setError] = useState<string | null>(null);
  const form = useForm({ initialValues: { label: instance.label, is_active: instance.is_active } });
  const save = useAction((values: typeof form.values) => api.patch<{ notices: Notice[] }>(`/api/v1/instances/${instance.id}`, values),
    { invalidate: [INSTANCES_KEY], silent: true });
  return (
    <form onSubmit={form.onSubmit((values) => save.mutate(values, { onSuccess: onDone, onError: (e) => setError(applyApiError(form, e)) }))}>
      <FormBody error={error} submitLabel="Enregistrer" onCancel={onDone} loading={save.isPending}>
        <Text size="sm">Slug <Code>{instance.slug}</Code> · {instance.chart_label}</Text>
        <Text size="sm" c="dimmed">Base <Code>{instance.database}</Code> (non modifiable après création)</Text>
        <TextInput label="Libellé" required data-autofocus {...form.getInputProps("label")} />
        <Switch label="Instance active" description="Une instance désactivée n'est plus proposée à la connexion."
          {...form.getInputProps("is_active", { type: "checkbox" })} />
      </FormBody>
    </form>
  );
}

export default function InstancesPage() {
  const modal = useRouteModal("/instances/", "instance_id");
  const { data, isFetching } = useList<Instance, Meta>(INSTANCES_KEY, "/api/v1/instances");
  const editing = modal.mode === "edit" ? data?.items.find((i) => i.id === modal.id) ?? null : null;
  const columns: GridColumn<Instance>[] = [
    { accessor: "slug", title: "Slug", sortable: true, hideable: false,
      render: (i) => <Anchor component={AppLink} href={`/instances/${i.id}`} className="lv-num" size="sm">{i.slug}</Anchor> },
    { accessor: "label", title: "Libellé", sortable: true },
    { accessor: "chart_label", title: "Plan comptable" },
    { accessor: "database", title: "Base de données", render: (i) => <Text size="sm" c="dimmed" className="lv-num">{i.database}</Text> },
    { accessor: "is_active", title: "Statut", render: (i) => <StatusBadge tone={i.is_active ? "ok" : "neutral"}>{i.is_active ? "Active" : "Désactivée"}</StatusBadge> },
    { accessor: "actions", title: "", hideable: false, textAlign: "right",
      render: (i) => <Button variant="subtle" size="compact-sm" onClick={() => modal.openEdit(i.id)}>Modifier</Button> },
  ];
  return (
    <>
      <PageHeader title="Instances" description="Une base comptable par structure ; chaque instance a ses données, ses intégrations et ses sauvegardes."
        actions={<>
          <Button variant="default" component={AppLink} href="/instances/import">Importer un fichier</Button>
          <Button onClick={modal.openNew}>Nouvelle instance</Button>
        </>} />
      <DataGrid id="instances" records={data?.items} columns={columns} fetching={isFetching}
        defaultSort={{ column: "label", direction: "asc" }} emptyText="Aucune instance." />
      <FormModal opened={modal.mode === "new"} onClose={modal.close} title="Nouvelle instance">
        <CreateForm meta={data?.meta} onDone={modal.close} />
      </FormModal>
      <FormModal opened={!!editing} onClose={modal.close} title={editing ? `Modifier ${editing.label}` : ""}>
        {editing && <EditForm key={editing.id} instance={editing} onDone={modal.close} />}
      </FormModal>
    </>
  );
}

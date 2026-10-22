// Compta › Journaux : liste et création (fenêtre portée par /journals/new).
import { useState } from "react";
import { Button, Text, TextInput } from "@mantine/core";
import { useForm } from "@mantine/form";
import { api } from "../../api/client";
import { useAction, useList, type Notice } from "../../api/resources";
import { applyApiError, FormBody } from "../../components/ApiForm";
import { DataGrid, type GridColumn } from "../../components/DataGrid";
import { FormModal } from "../../components/FormModal";
import { PageHeader } from "../../components/PageHeader";
import { useRouteModal } from "../../app/useRouteModal";

export interface Journal { id: number; code: string; label: string }

const KEY = ["journals"];

const COLUMNS: GridColumn<Journal>[] = [
  { accessor: "code", title: "Code", sortable: true, hideable: false, width: 120,
    render: (j) => <Text className="lv-num" fw={600}>{j.code}</Text> },
  { accessor: "label", title: "Libellé", sortable: true },
];

function JournalForm({ onDone }: { onDone: () => void }) {
  const [error, setError] = useState<string | null>(null);
  const form = useForm({ initialValues: { code: "", label: "" } });
  const create = useAction((values: { code: string; label: string }) =>
    api.post<{ notices: Notice[] }>("/api/v1/journals", values), { invalidate: [KEY], silent: true });
  return (
    <form onSubmit={form.onSubmit((values) => create.mutate(values, {
      onSuccess: onDone, onError: (e) => setError(applyApiError(form, e)),
    }))}>
      <FormBody error={error} submitLabel="Créer le journal" onCancel={onDone} loading={create.isPending}>
        <TextInput label="Code" description="10 caractères au plus, en capitales (AC, VT, BQ…)." required
          data-autofocus classNames={{ input: "lv-num" }} {...form.getInputProps("code")} />
        <TextInput label="Libellé" required {...form.getInputProps("label")} />
      </FormBody>
    </form>
  );
}

export default function JournalsPage() {
  const modal = useRouteModal("/journals/");
  const { data, isFetching } = useList<Journal>(KEY, "/api/v1/journals");
  return (
    <>
      <PageHeader title="Journaux" description="Les journaux classent les écritures : achats, ventes, banque, opérations diverses."
        actions={<Button onClick={modal.openNew}>Créer un journal</Button>} />
      <DataGrid id="journals" records={data?.items} columns={COLUMNS} fetching={isFetching}
        defaultSort={{ column: "code", direction: "asc" }} emptyText="Aucun journal." />
      <FormModal opened={modal.mode === "new"} onClose={modal.close} title="Créer un journal">
        <JournalForm onDone={modal.close} />
      </FormModal>
    </>
  );
}

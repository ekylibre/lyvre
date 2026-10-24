// Compta › Plan comptable : recherche, création, modification (libellé et type).
import { useMemo, useState } from "react";
import { Checkbox, Button, Select, Text, TextInput } from "@mantine/core";
import { useForm } from "@mantine/form";
import { api } from "../../api/client";
import { useAction, useList, type Notice } from "../../api/resources";
import { applyApiError, FormBody } from "../../components/ApiForm";
import { DataGrid, type GridColumn } from "../../components/DataGrid";
import { FilterBar, SearchInput, useUrlParams } from "../../components/FilterBar";
import { FormModal } from "../../components/FormModal";
import { PageHeader } from "../../components/PageHeader";
import { Can } from "../../components/Can";
import { useRouteModal } from "../../app/useRouteModal";

export interface ChartAccount {
  id: number; code: string; label: string; account_type: string; is_header: boolean; parent_code: string | null;
  /** Lot F3 : compte de tiers lettrable. */
  lettrable?: boolean;
}
interface Meta { types: { value: string; label: string }[] }

const KEY = ["chart-of-accounts"];

/** Recherche sans accents sur le code (début) ou le libellé (mots). */
export function matchAccount(account: ChartAccount, query: string): boolean {
  const norm = (s: string) => s.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase();
  const q = norm(query.trim());
  if (!q) return true;
  return account.code.startsWith(q) || q.split(/\s+/).every((word) => norm(account.label).includes(word));
}

function AccountForm({ account, types, onDone }: {
  account: ChartAccount | null; types: Meta["types"]; onDone: () => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const form = useForm({
    initialValues: {
      code: account?.code ?? "", label: account?.label ?? "",
      account_type: account?.account_type ?? "OTHER", parent_code: "", lettrable: account?.lettrable ?? false,
    },
  });
  const save = useAction((values: typeof form.values) => account
    ? api.patch<{ notices: Notice[] }>(`/api/v1/chart-of-accounts/${account.id}`, values)
    : api.post<{ notices: Notice[] }>("/api/v1/chart-of-accounts", values),
  { invalidate: [KEY], silent: true });
  return (
    <form onSubmit={form.onSubmit((values) => save.mutate(values, {
      onSuccess: onDone, onError: (e) => setError(applyApiError(form, e)),
    }))}>
      <FormBody error={error} submitLabel={account ? "Enregistrer" : "Créer le compte"} onCancel={onDone}
        loading={save.isPending}>
        <TextInput label="Code" required readOnly={!!account} classNames={{ input: "lv-num" }}
          description={account ? "Le code d'un compte ne change pas." : undefined}
          data-autofocus={!account || undefined} {...form.getInputProps("code")} />
        <TextInput label="Libellé" required data-autofocus={account ? true : undefined} {...form.getInputProps("label")} />
        <Select label="Type" data={types} allowDeselect={false} {...form.getInputProps("account_type")} />
        {account && !account.is_header && (
          <Checkbox label="Lettrable" description="Compte de tiers dont les lignes se lettrent (Compta › Lettrage)."
            {...form.getInputProps("lettrable", { type: "checkbox" })} />
        )}
        {!account && (
          <TextInput label="Compte parent" description="Code du compte de regroupement, facultatif."
            classNames={{ input: "lv-num" }} {...form.getInputProps("parent_code")} />
        )}
      </FormBody>
    </form>
  );
}

export default function AccountsPage() {
  const modal = useRouteModal("/accounts/", "account_id");
  const [params, setParams] = useUrlParams({ q: "" });
  const { data, isFetching } = useList<ChartAccount, Meta>(KEY, "/api/v1/chart-of-accounts");
  const types = data?.meta?.types ?? [];
  const typeLabel = useMemo(() => Object.fromEntries(types.map((t) => [t.value, t.label])), [types]);
  const records = useMemo(() => data?.items.filter((a) => matchAccount(a, params.q)), [data, params.q]);
  const editing = modal.mode === "edit" ? data?.items.find((a) => a.id === modal.id) ?? null : null;

  const columns: GridColumn<ChartAccount>[] = [
    { accessor: "code", title: "Code", sortable: true, hideable: false, width: 140,
      render: (a) => <Text className="lv-num" fw={a.is_header ? 600 : 400}>{a.code}</Text> },
    { accessor: "label", title: "Libellé", sortable: true,
      render: (a) => <Text fw={a.is_header ? 600 : 400}>{a.label}</Text> },
    { accessor: "account_type", title: "Type", sortable: true,
      render: (a) => <Text size="sm" c="dimmed">{typeLabel[a.account_type] ?? a.account_type}</Text> },
    { accessor: "actions", title: "", hideable: false, textAlign: "right",
      render: (a) => <Button variant="subtle" size="compact-sm" onClick={() => modal.openEdit(a.id)}>Modifier</Button> },
  ];

  return (
    <>
      <PageHeader title="Plan comptable" description="Les comptes utilisables dans les écritures, les produits et les règles."
        actions={<Can><Button onClick={modal.openNew}>Créer un compte</Button></Can>} />
      <FilterBar>
        <SearchInput value={params.q} onChange={(q) => setParams({ q })} placeholder="Code ou libellé…" />
      </FilterBar>
      <DataGrid id="accounts" records={records} columns={columns} fetching={isFetching} perPage={100}
        defaultSort={{ column: "code", direction: "asc" }} emptyText="Aucun compte ne correspond." />
      <FormModal opened={modal.mode === "new" || (modal.mode === "edit" && !!editing)} onClose={modal.close}
        title={editing ? `Modifier le compte ${editing.code}` : "Créer un compte"}>
        <AccountForm key={editing?.id ?? "new"} account={editing} types={types} onDone={modal.close} />
      </FormModal>
    </>
  );
}

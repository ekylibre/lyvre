// Compta › Catalogue : produits et services (comptes d'achat / de vente, TVA par défaut).
import { useState } from "react";
import { Button, Group, SegmentedControl, Select, Stack, Switch, Text, TextInput } from "@mantine/core";
import { useForm } from "@mantine/form";
import { api } from "../../api/client";
import { useAction, useList, type Notice } from "../../api/resources";
import { applyApiError, FormBody } from "../../components/ApiForm";
import { confirmAction } from "../../components/ConfirmButton";
import { DataGrid, type GridColumn } from "../../components/DataGrid";
import { FilterBar, useUrlParams } from "../../components/FilterBar";
import { FormModal } from "../../components/FormModal";
import { PageHeader } from "../../components/PageHeader";
import { StatusBadge } from "../../components/StatusBadge";
import { useRouteModal } from "../../app/useRouteModal";

interface AccountRef { id: number; code: string; label: string }
export interface Product {
  id: number; name: string; reference: string | null; kind: "purchase" | "sale" | "both"; active: boolean;
  purchase_account: AccountRef | null; sale_account: AccountRef | null;
  vat_rate_bp: number | null; vat_rate: string; usages: number;
}
interface Meta {
  kinds: { value: string; label: string }[];
  purchase_accounts: { code: string; label: string }[];
  sale_accounts: { code: string; label: string }[];
}

const KEY = ["products"];

const accountOptions = (accounts: Meta["purchase_accounts"] = []) =>
  accounts.map((a) => ({ value: a.code, label: `${a.code} — ${a.label}` }));

function AccountCell({ account }: { account: AccountRef | null }) {
  if (!account) return <Text c="dimmed">—</Text>;
  return <Text size="sm"><span className="lv-num">{account.code}</span> <Text span c="dimmed" size="sm">{account.label}</Text></Text>;
}

function ProductForm({ product, meta, onDone }: { product: Product | null; meta: Meta | undefined; onDone: () => void }) {
  const [error, setError] = useState<string | null>(null);
  const form = useForm({
    initialValues: {
      name: product?.name ?? "", reference: product?.reference ?? "", kind: product?.kind ?? "purchase",
      purchase_account_code: product?.purchase_account?.code ?? "",
      sale_account_code: product?.sale_account?.code ?? "", vat_rate: product?.vat_rate ?? "",
    },
  });
  const save = useAction((values: typeof form.values) => product
    ? api.patch<{ notices: Notice[] }>(`/api/v1/products/${product.id}`, values)
    : api.post<{ notices: Notice[] }>("/api/v1/products", values), { invalidate: [KEY], silent: true });
  const kind = form.values.kind;
  return (
    <form onSubmit={form.onSubmit((values) => save.mutate(values, {
      onSuccess: onDone, onError: (e) => setError(applyApiError(form, e)),
    }))}>
      <FormBody error={error} submitLabel={product ? "Enregistrer" : "Créer le produit"} onCancel={onDone}
        loading={save.isPending}>
        <TextInput label="Libellé" required data-autofocus {...form.getInputProps("name")} />
        <TextInput label="Référence" description="Facultative." {...form.getInputProps("reference")} />
        <Stack gap={4}>
          <Text size="sm" fw={600}>Sens</Text>
          <SegmentedControl data={meta?.kinds ?? []} {...form.getInputProps("kind")} />
        </Stack>
        {kind !== "sale" && (
          <Select label="Compte d'achat" required searchable data={accountOptions(meta?.purchase_accounts)}
            nothingFoundMessage="Aucun compte 6…" {...form.getInputProps("purchase_account_code")} />
        )}
        {kind !== "purchase" && (
          <Select label="Compte de vente" required searchable data={accountOptions(meta?.sale_accounts)}
            nothingFoundMessage="Aucun compte 7…" {...form.getInputProps("sale_account_code")} />
        )}
        <TextInput label="Taux de TVA (%)" description="20, 10, 5,5… ; vide si aucun taux par défaut." w={200}
          inputMode="decimal" {...form.getInputProps("vat_rate")} />
      </FormBody>
    </form>
  );
}

export default function ProductsPage() {
  const modal = useRouteModal("/products/", "product_id");
  const [params, setParams] = useUrlParams({ archived: "" });
  const archived = params.archived === "1";
  const url = `/api/v1/products${archived ? "?archived=1" : ""}`;
  const { data, isFetching } = useList<Product, Meta>(KEY, url);
  const kinds = Object.fromEntries((data?.meta?.kinds ?? []).map((k) => [k.value, k.label]));
  const editing = modal.mode === "edit" ? data?.items.find((p) => p.id === modal.id) ?? null : null;
  const archive = useAction((p: Product) => api.patch<{ notices: Notice[] }>(`/api/v1/products/${p.id}`, { active: !p.active }),
    { invalidate: [KEY] });
  const remove = useAction((p: Product) => api.delete<{ notices: Notice[] }>(`/api/v1/products/${p.id}`),
    { invalidate: [KEY] });

  const columns: GridColumn<Product>[] = [
    { accessor: "name", title: "Libellé", sortable: true, hideable: false,
      render: (p) => <Group gap="xs">{p.name}{!p.active && <StatusBadge tone="neutral">Archivé</StatusBadge>}</Group> },
    { accessor: "reference", title: "Référence", render: (p) => <span className="lv-num">{p.reference ?? "—"}</span> },
    { accessor: "kind", title: "Sens", sortable: true, render: (p) => kinds[p.kind] ?? p.kind },
    { accessor: "purchase_account", title: "Compte d'achat", render: (p) => <AccountCell account={p.purchase_account} /> },
    { accessor: "sale_account", title: "Compte de vente", render: (p) => <AccountCell account={p.sale_account} /> },
    { accessor: "vat_rate_bp", title: "TVA", textAlign: "right", sortable: true,
      render: (p) => <span className="lv-num">{p.vat_rate ? `${p.vat_rate} %` : "—"}</span> },
    { accessor: "usages", title: "Utilisations", textAlign: "right", sortable: true,
      render: (p) => <span className="lv-num">{p.usages}</span> },
    { accessor: "actions", title: "", hideable: false, textAlign: "right",
      render: (p) => (
        <Group gap={4} justify="flex-end" wrap="nowrap">
          <Button variant="subtle" size="compact-sm" onClick={() => modal.openEdit(p.id)}>Modifier</Button>
          <Button variant="subtle" size="compact-sm" onClick={() => archive.mutate(p)}>
            {p.active ? "Archiver" : "Réactiver"}
          </Button>
          {p.usages === 0 && (
            <Button variant="subtle" size="compact-sm" color="brique"
              onClick={() => confirmAction({ title: `Supprimer « ${p.name} » ?`, confirmLabel: "Supprimer",
                onConfirm: () => remove.mutate(p) })}>
              Supprimer
            </Button>
          )}
        </Group>
      ) },
  ];

  return (
    <>
      <PageHeader title="Catalogue" description="Produits et services : comptes et taux de TVA proposés sur les lignes de facture."
        actions={<Button onClick={modal.openNew}>Créer un produit</Button>} />
      <FilterBar>
        <Switch label="Afficher les archivés" checked={archived}
          onChange={(e) => setParams({ archived: e.currentTarget.checked ? "1" : "" })} />
      </FilterBar>
      <DataGrid id="products" records={data?.items} columns={columns} fetching={isFetching}
        defaultSort={{ column: "name", direction: "asc" }}
        emptyText="Aucun produit. « Achats divers » est créé à la première facture d'achat ; créez vos produits pour orienter chaque dépense vers le bon compte." />
      <FormModal opened={modal.mode === "new" || (modal.mode === "edit" && !!editing)} onClose={modal.close}
        title={editing ? `Modifier « ${editing.name} »` : "Créer un produit"} size="lg">
        <ProductForm key={editing?.id ?? "new"} product={editing} meta={data?.meta} onDone={modal.close} />
      </FormModal>
    </>
  );
}

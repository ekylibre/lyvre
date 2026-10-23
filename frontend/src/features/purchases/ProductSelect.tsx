// Produit d'une ligne d'achat : recherche dans le catalogue, ou création sur place (« + Créer
// « Electricité » ») avec le compte et le taux déjà saisis sur la ligne.
import { useState } from "react";
import { Select, TextInput } from "@mantine/core";
import { useForm } from "@mantine/form";
import { api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { applyApiError, FormBody } from "../../components/ApiForm";
import { FormModal } from "../../components/FormModal";
import { PURCHASES_KEY, type Option, type ProductOption } from "./types";

export const CREATE_PRODUCT = "__create__";

/** Options du champ : catalogue, puis la création (avec le texte cherché s'il n'est pas déjà un produit). */
export function productChoices(products: ProductOption[], search: string): Option[] {
  const wanted = search.trim();
  const exists = products.some((p) => p.label.toLowerCase() === wanted.toLowerCase());
  const create = { value: CREATE_PRODUCT, label: wanted && !exists ? `+ Créer « ${wanted} »` : "+ Créer un produit…" };
  return [...products.map(({ value, label }) => ({ value, label })), ...(exists ? [] : [create])];
}

interface Created { item: { id: number; name: string; purchase_account: { code: string } | null; vat_rate: string }; notices: Notice[] }

function CreateProductForm({ name, account, rate, accounts, onCreated, onCancel }: {
  name: string; account: string; rate: string; accounts: Option[];
  onCreated: (product: ProductOption) => void; onCancel: () => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const form = useForm({ initialValues: { name, kind: "purchase", purchase_account_code: account, vat_rate: rate } });
  const create = useAction((values: typeof form.values) => api.post<Created>("/api/v1/products", values),
    { invalidate: [PURCHASES_KEY, ["products"]], silent: true });
  return (
    <form onSubmit={form.onSubmit((values) => create.mutate(values, {
      onSuccess: ({ item }) => onCreated({ value: String(item.id), label: item.name,
        account: item.purchase_account?.code ?? "", rate: item.vat_rate }),
      onError: (e) => setError(applyApiError(form, e)),
    }))}>
      <FormBody error={error} submitLabel="Créer le produit" onCancel={onCancel} loading={create.isPending}>
        <TextInput label="Libellé" required data-autofocus {...form.getInputProps("name")} />
        <Select label="Compte d'achat" required searchable data={accounts} nothingFoundMessage="Aucun compte 6…"
          {...form.getInputProps("purchase_account_code")} />
        <TextInput label="Taux de TVA (%)" description="20, 10, 5,5… ; vide si aucun taux par défaut." w={200}
          inputMode="decimal" {...form.getInputProps("vat_rate")} />
      </FormBody>
    </form>
  );
}

export function ProductSelect({ label, value, products, accounts, account, rate, onChange }: {
  label: string; value: string; products: ProductOption[]; accounts: Option[];
  /** Compte et taux de la ligne, proposés pour un nouveau produit. */
  account: string; rate: string;
  /** Produit choisi ; `created` : produit qui vient d'être créé (pas encore dans la liste rechargée). */
  onChange: (productId: string, created?: ProductOption) => void;
}) {
  const [search, setSearch] = useState("");
  const [creating, setCreating] = useState<string | null>(null);
  const selected = products.find((p) => p.value === value)?.label ?? "";
  // Recherche égale au produit choisi : rien de cherché, création générique.
  const typed = search === selected ? "" : search;
  const cancel = () => { setCreating(null); setSearch(selected); };
  return (
    <>
      <Select aria-label={label} data={productChoices(products, typed)} value={value || null} clearable searchable
        placeholder="—" w={180} searchValue={search} onSearchChange={setSearch} nothingFoundMessage="Aucun produit"
        onChange={(v) => {
          if (v === CREATE_PRODUCT) { setCreating(typed); return; }
          onChange(v ?? "");
        }} />
      <FormModal opened={creating !== null} onClose={cancel} title="Nouveau produit d'achat">
        {creating !== null && (
          <CreateProductForm name={creating} account={account} rate={rate} accounts={accounts} onCancel={cancel}
            onCreated={(product) => { setCreating(null); setSearch(product.label); onChange(product.value, product); }} />
        )}
      </FormModal>
    </>
  );
}

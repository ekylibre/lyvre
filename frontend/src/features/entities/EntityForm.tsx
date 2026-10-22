// Création / modification d'un tiers (identité, fournisseur, adhésion).
import { useState } from "react";
import { Checkbox, Divider, Group, Select, Text, TextInput, Textarea } from "@mantine/core";
import { useForm } from "@mantine/form";
import { api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { applyApiError, FormBody } from "../../components/ApiForm";
import { TIERS_KEY, type EntitiesMeta, type Entity } from "./types";

export function EntityForm({ entity, meta, onDone }: {
  entity: Entity | null; meta: EntitiesMeta | undefined; onDone: () => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const form = useForm({
    initialValues: {
      name: entity?.name ?? "", entity_type: entity?.entity_type ?? "AUTRE", email: entity?.email ?? "",
      account_code: entity?.account_code ?? "", is_member: entity?.is_member ?? false,
      is_benevole: entity?.is_benevole ?? false, notes: entity?.notes ?? "",
      default_product_id: entity?.default_product_id ? String(entity.default_product_id) : "",
      vat_number: entity?.vat_number ?? "", siret: entity?.siret ?? "", iban: entity?.iban ?? "",
    },
  });
  const save = useAction((values: typeof form.values) => entity
    ? api.patch<{ notices: Notice[] }>(`/api/v1/tiers/${entity.id}`, values)
    : api.post<{ notices: Notice[] }>("/api/v1/tiers", values),
  { invalidate: [TIERS_KEY, ["members"]], silent: true });
  return (
    <form onSubmit={form.onSubmit((values) => save.mutate(values, {
      onSuccess: onDone, onError: (e) => setError(applyApiError(form, e)),
    }))}>
      <FormBody error={error} submitLabel={entity ? "Enregistrer" : "Créer le tiers"} onCancel={onDone}
        loading={save.isPending}>
        <TextInput label="Nom" required data-autofocus {...form.getInputProps("name")} />
        <Group grow align="flex-start">
          <Select label="Type" data={meta?.types ?? []} allowDeselect={false} {...form.getInputProps("entity_type")} />
          <TextInput label="Compte" description="Compte du plan associé, facultatif." placeholder="401000"
            classNames={{ input: "lv-num" }} {...form.getInputProps("account_code")} />
        </Group>
        <TextInput label="Email" type="email" placeholder="prenom.nom@exemple.fr"
          description="Sert au rattachement automatique des commandes HelloAsso." {...form.getInputProps("email")} />
        <Group>
          <Checkbox label="Adhérent de l'association" {...form.getInputProps("is_member", { type: "checkbox" })} />
          <Checkbox label="Bénévole" {...form.getInputProps("is_benevole", { type: "checkbox" })} />
        </Group>
        <Divider label="Fournisseur" labelPosition="left" />
        <Select label="Produit par défaut" placeholder="Achats divers" clearable data={meta?.products ?? []}
          description="Proposé sur les lignes de ses factures d'achat (compte de charge, TVA)."
          {...form.getInputProps("default_product_id")} />
        <Group grow align="flex-start">
          <TextInput label="N° de TVA" classNames={{ input: "lv-num" }} {...form.getInputProps("vat_number")} />
          <TextInput label="SIRET" inputMode="numeric" classNames={{ input: "lv-num" }} {...form.getInputProps("siret")} />
        </Group>
        <TextInput label="IBAN" classNames={{ input: "lv-num" }} {...form.getInputProps("iban")} />
        <Text size="sm" c="dimmed" mt={-8}>Servent à reconnaître le fournisseur sur les factures Qonto et saisies.</Text>
        <Textarea label="Notes" autosize minRows={2} {...form.getInputProps("notes")} />
      </FormBody>
    </form>
  );
}

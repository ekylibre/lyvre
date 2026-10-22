// Création / modification d'un tiers (identité, adresse et nature pour les reçus fiscaux,
// fournisseur, adhésion).
import { useState } from "react";
import { Checkbox, Divider, Group, SegmentedControl, Select, Stack, Text, TextInput, Textarea } from "@mantine/core";
import { useForm } from "@mantine/form";
import { api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { applyApiError, FormBody } from "../../components/ApiForm";
import { TIERS_KEY, type EntitiesMeta, type Entity } from "./types";

export function EntityForm({ entity, meta, onDone }: {
  entity: Entity | null; meta: EntitiesMeta | undefined; onDone: () => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const initial = {
    name: entity?.name ?? "", entity_type: entity?.entity_type ?? "AUTRE", email: entity?.email ?? "",
    account_code: entity?.account_code ?? "", is_member: entity?.is_member ?? false,
    is_benevole: entity?.is_benevole ?? false, notes: entity?.notes ?? "",
    default_product_id: entity?.default_product_id ? String(entity.default_product_id) : "",
    vat_number: entity?.vat_number ?? "", siret: entity?.siret ?? "", iban: entity?.iban ?? "",
    address_line1: entity?.address_line1 ?? "", address_line2: entity?.address_line2 ?? "",
    postal_code: entity?.postal_code ?? "", city: entity?.city ?? "", country: entity?.country ?? "",
    person_kind: entity?.person_kind ?? "",
  };
  const form = useForm({ initialValues: initial });
  const save = useAction((values: typeof initial) => {
    const body = { ...values, person_kind: values.person_kind || null };
    return entity ? api.patch<{ notices: Notice[] }>(`/api/v1/tiers/${entity.id}`, body)
      : api.post<{ notices: Notice[] }>("/api/v1/tiers", body);
  },
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
        <Divider label="Adresse et nature" labelPosition="left" />
        <Stack gap={4}>
          <Text size="sm" fw={500}>Nature</Text>
          <SegmentedControl data={[{ value: "", label: "Non précisée" }, { value: "individual", label: "Particulier" },
            { value: "company", label: "Entreprise ou organisme" }]} {...form.getInputProps("person_kind")} />
        </Stack>
        <TextInput label="Adresse" {...form.getInputProps("address_line1")} />
        <TextInput label="Complément d'adresse" {...form.getInputProps("address_line2")} />
        <Group grow align="flex-start">
          <TextInput label="Code postal" classNames={{ input: "lv-num" }} {...form.getInputProps("postal_code")} />
          <TextInput label="Ville" {...form.getInputProps("city")} />
          <TextInput label="Pays" placeholder="France" {...form.getInputProps("country")} />
        </Group>
        <Text size="sm" c="dimmed" mt={-8}>Exigées pour émettre un reçu fiscal à ce donateur.</Text>
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

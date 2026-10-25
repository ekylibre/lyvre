// Création / modification d'un tiers (identité, adresse et nature, fournisseur ; adhésion et
// mentions des reçus fiscaux pour une association seulement). Recherche Sirene en tête (lot G4) :
// la proposition remplit le formulaire, sans enregistrer.
import { useState } from "react";
import { Alert, Anchor, Button, Checkbox, Collapse, Divider, Group, SegmentedControl, Select, Stack, Text, TextInput, Textarea } from "@mantine/core";
import { useForm } from "@mantine/form";
import { api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { useIsAssociation } from "../../api/session";
import { applyApiError, FormBody } from "../../components/ApiForm";
import { SireneProposalModal } from "../../components/sirene/SireneProposalModal";
import { SireneSearch } from "../../components/sirene/SireneSearch";
import { isValidSiren, sireneMessage, useSireneAvailable, useSireneProposal, type SireneCandidate } from "../../components/sirene/useSirene";
import { AppLink } from "../../app/navigation";
import { formatNaf } from "../../lib/format";
import { TIERS_KEY, type EntitiesMeta, type Entity } from "./types";

/** Champs que Sirene peut compléter sur un tiers, dans l'ordre du formulaire. */
const SIRENE_FIELDS: Record<string, string> = {
  name: "Nom", person_kind: "Nature", address_line1: "Adresse", address_line2: "Complément d'adresse",
  postal_code: "Code postal", city: "Ville", country: "Pays", vat_number: "N° de TVA", siret: "SIRET", siren: "SIREN",
  naf_code: "Activité (NAF)",
};
const digits = (value: string) => value.replace(/[\s.]/g, "");

export function EntityForm({ entity, meta, onDone }: {
  entity: Entity | null; meta: EntitiesMeta | undefined; onDone: () => void;
}) {
  const association = useIsAssociation();
  const [error, setError] = useState<string | null>(null);
  const initial = {
    name: entity?.name ?? "", entity_type: entity?.entity_type ?? "AUTRE", email: entity?.email ?? "",
    account_code: entity?.account_code ?? "", is_member: entity?.is_member ?? false,
    is_benevole: entity?.is_benevole ?? false, notes: entity?.notes ?? "",
    default_product_id: entity?.default_product_id ? String(entity.default_product_id) : "",
    vat_number: entity?.vat_number ?? "", siret: entity?.siret ?? "", siren: entity?.siren ?? "", iban: entity?.iban ?? "",
    address_line1: entity?.address_line1 ?? "", address_line2: entity?.address_line2 ?? "",
    postal_code: entity?.postal_code ?? "", city: entity?.city ?? "", country: entity?.country ?? "",
    person_kind: entity?.person_kind ?? "", naf_code: entity?.naf_code ?? "", naf_nomenclature: entity?.naf_nomenclature ?? "",
  };
  const form = useForm({ initialValues: initial });
  const sireneAvailable = useSireneAvailable();
  const sirene = useSireneProposal();
  const [searchOpen, setSearchOpen] = useState(!entity);
  const [proposalOpen, setProposalOpen] = useState(false);
  const propose = (params: { siren?: string; siret?: string }) =>
    sirene.mutate({ ...params, for: "entity" }, { onSuccess: () => setProposalOpen(true) });
  const pick = (c: SireneCandidate) => propose(c.siret ? { siret: c.siret } : { siren: c.siren });
  const known = sirene.data?.existing_entity;
  const duplicate = known && known.id !== entity?.id ? known : null;
  const ownNumber = digits(form.values.siret).length === 14 ? { siret: digits(form.values.siret) }
    : isValidSiren(form.values.siren) ? { siren: digits(form.values.siren) } : null;
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
        {sireneAvailable && (
          <Stack gap="xs">
            <Group justify="space-between">
              <Anchor component="button" type="button" size="sm" onClick={() => setSearchOpen((o) => !o)}>
                {searchOpen ? "Masquer la recherche Sirene" : "Rechercher dans Sirene"}</Anchor>
              {ownNumber && (
                <Button size="compact-sm" variant="light" loading={sirene.isPending} onClick={() => propose(ownNumber)}>
                  Compléter depuis Sirene</Button>
              )}
            </Group>
            <Collapse expanded={searchOpen}>
              <SireneSearch onPick={pick} initialQuery={form.values.name} initialPostalCode={form.values.postal_code} />
            </Collapse>
            {sirene.isError && <Alert color="brique" role="alert">{sireneMessage(sirene.error)}</Alert>}
            {duplicate && (
              <Alert color="paille">Ce SIREN est déjà celui du tiers{" "}
                <Anchor component={AppLink} href={`/entities/${duplicate.id}`}>{duplicate.name}</Anchor> : vérifiez qu'il ne s'agit pas d'un doublon.</Alert>
            )}
          </Stack>
        )}
        <TextInput label="Nom" required data-autofocus {...form.getInputProps("name")} />
        <Group grow align="flex-start">
          <Select label="Type" data={meta?.types ?? []} allowDeselect={false} {...form.getInputProps("entity_type")} />
          <TextInput label="Compte" description="Compte du plan associé, facultatif." placeholder="401000"
            classNames={{ input: "lv-num" }} {...form.getInputProps("account_code")} />
        </Group>
        <TextInput label="Email" type="email" placeholder="prenom.nom@exemple.fr"
          description={association ? "Sert au rattachement automatique des commandes HelloAsso." : undefined}
          {...form.getInputProps("email")} />
        {association && (
          <Group>
            <Checkbox label="Adhérent de l'association" {...form.getInputProps("is_member", { type: "checkbox" })} />
            <Checkbox label="Bénévole" {...form.getInputProps("is_benevole", { type: "checkbox" })} />
          </Group>
        )}
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
        {association && <Text size="sm" c="dimmed" mt={-8}>Exigées pour émettre un reçu fiscal à ce donateur.</Text>}
        <Divider label="Fournisseur" labelPosition="left" />
        <Select label="Produit par défaut" placeholder="Achats divers" clearable data={meta?.products ?? []}
          description="Proposé sur les lignes de ses factures d'achat (compte de charge, TVA)."
          {...form.getInputProps("default_product_id")} />
        <Group grow align="flex-start">
          <TextInput label="N° de TVA" classNames={{ input: "lv-num" }} {...form.getInputProps("vat_number")} />
          <TextInput label="SIRET" inputMode="numeric" classNames={{ input: "lv-num" }} {...form.getInputProps("siret")} />
          <TextInput label="SIREN" inputMode="numeric" classNames={{ input: "lv-num" }}
            description={form.values.siret ? "Début du SIRET" : "Sans établissement connu"} {...form.getInputProps("siren")} />
        </Group>
        <Group grow align="flex-start">
          <TextInput label="IBAN" classNames={{ input: "lv-num" }} {...form.getInputProps("iban")} />
          <TextInput label="Activité (code NAF)" placeholder="68.20B" classNames={{ input: "lv-num" }}
            description={form.values.naf_code && sirene.data?.labels.naf && digits(form.values.naf_code) === sirene.data.proposal.naf_code
              ? sirene.data.labels.naf : undefined}
            {...form.getInputProps("naf_code")} value={formatNaf(digits(form.values.naf_code))}
            onChange={(e) => form.setFieldValue("naf_code", digits(e.currentTarget.value).toUpperCase())} />
        </Group>
        <Text size="sm" c="dimmed" mt={-8}>Servent à reconnaître le fournisseur sur les factures Qonto et saisies.</Text>
        <Textarea label="Notes" autosize minRows={2} {...form.getInputProps("notes")} />
      </FormBody>
      <SireneProposalModal opened={proposalOpen} onClose={() => setProposalOpen(false)} result={sirene.data ?? null}
        current={form.values} fields={SIRENE_FIELDS} onApply={(values) => form.setValues(values)}
        note="Pensez à enregistrer le tiers." />
    </form>
  );
}

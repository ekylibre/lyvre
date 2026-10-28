// Configuration › Structure : identité de la structure (raison sociale, SIREN, mentions légales, adresse, objet ; RNA et
// signataire des reçus pour une association, associés pour une société), utilisée par le FEC, les reçus fiscaux et les états ; onglet Facturation (mentions et
// réglages des factures de vente). Modifiable par l'administrateur de l'instance, lisible par tous.
import { useEffect, useState } from "react";
import { Alert, Button, Center, Checkbox, Fieldset, Group, Loader, SimpleGrid, Stack, Tabs, Text, TextInput, Textarea } from "@mantine/core";
import { DateInput } from "@mantine/dates";
import { useForm } from "@mantine/form";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { SESSION_KEY, useCan, useCurrentSession, useIsAssociation } from "../../api/session";
import { applyApiError } from "../../components/ApiForm";
import { useUrlParams } from "../../components/FilterBar";
import { PageHeader } from "../../components/PageHeader";
import { formatNaf } from "../../lib/format";
import { SireneProposalModal } from "../../components/sirene/SireneProposalModal";
import { isValidSiren, sireneMessage, useSireneAvailable, useSireneProposal } from "../../components/sirene/useSirene";
import { BillingSettings } from "../sales/BillingSettings";
import { BILLING_KEY } from "../sales/types";

export interface Organization {
  name: string; siren: string | null; rna: string | null; address_line1: string | null; address_line2: string | null;
  postal_code: string | null; city: string | null; country: string; purpose: string | null;
  signatory_name: string | null; signatory_title: string | null;
  /** Mentions légales (factures, baux) : seule source depuis le lot G2. */
  legal_form: string | null; rcs_city: string | null; vat_number: string | null; share_capital: string;
  /** Activité : code NAF sans point (« 6820B »), rempli depuis Sirene. */
  naf_code: string | null; naf_nomenclature: string | null;
  /** « 840 968 499 RCS Saintes », telle qu'imprimée sur les factures et les baux. */
  rcs_mention: string;
  fec_ready: boolean;
  /** Module « Associés » : option de l'instance et taux d'intérêt des comptes courants par défaut. */
  has_associates: boolean; associate_interest_rate: string;
  /** Jeune entreprise innovante depuis cette date (sociétés), AAAA-MM-JJ. */
  jei_since: string | null;
  /** Lot T3 : jour d'échéance de la CA3 (15 à 24), vide : 24. */
  vat_due_day: string;
}
export const ORGANIZATION_KEY = ["organization"];
const FIELDS = ["name", "siren", "rna", "address_line1", "address_line2", "postal_code", "city", "country", "purpose",
  "signatory_name", "signatory_title", "legal_form", "rcs_city", "vat_number", "share_capital", "naf_code", "naf_nomenclature"] as const;
/** Champs que Sirene peut compléter, dans l'ordre du formulaire (le RNA : associations). */
const SIRENE_FIELDS: Record<string, string> = {
  name: "Raison sociale", rna: "Numéro RNA", legal_form: "Forme juridique", vat_number: "N° de TVA intracommunautaire",
  naf_code: "Activité (NAF)", address_line1: "Adresse", address_line2: "Complément", postal_code: "Code postal",
  city: "Ville", country: "Pays",
};
type Values = Record<(typeof FIELDS)[number] | "associate_interest_rate", string>
  & { has_associates: boolean; jei_since: string | null; vat_due_day: string };

export default function OrganizationPage() {
  const can = useCan();
  const association = useIsAssociation();
  const company = useCurrentSession().instance?.chart === "societe";
  const client = useQueryClient();
  const [params, setParams] = useUrlParams({ tab: "identity" });
  const { data } = useQuery({ queryKey: ORGANIZATION_KEY,
    queryFn: () => api.get<{ item: Organization }>("/api/v1/organization") });
  const [error, setError] = useState<string | null>(null);
  const form = useForm<Values>({ initialValues: { ...Object.fromEntries(FIELDS.map((f) => [f, ""])),
    has_associates: false, associate_interest_rate: "", jei_since: null, vat_due_day: "" } as Values });
  useEffect(() => {
    if (data) form.setValues({ ...Object.fromEntries(FIELDS.map((f) => [f, data.item[f] ?? ""])),
      has_associates: data.item.has_associates, associate_interest_rate: data.item.associate_interest_rate,
      jei_since: data.item.jei_since, vat_due_day: data.item.vat_due_day ?? "" } as Values);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data]);
  const sireneAvailable = useSireneAvailable();
  const sirene = useSireneProposal();
  const [proposalOpen, setProposalOpen] = useState(false);
  const save = useAction((values: Values) => api.put<{ item: Organization; notices: Notice[] }>("/api/v1/organization", values),
    { silent: true });
  if (!data) return <Center h={300}><Loader /></Center>;
  const readOnly = !can.instanceAdmin;
  const field = (name: (typeof FIELDS)[number], label: string, props: Record<string, unknown> = {}) => (
    <TextInput label={label} readOnly={readOnly} {...props} {...form.getInputProps(name)} />
  );
  return (
    <>
      <PageHeader title="Structure" description={association
        ? "Identité de la structure : FEC, reçus fiscaux, factures de vente et états."
        : "Identité de la structure : FEC, factures de vente, baux et états."} />
      <Tabs value={params.tab} onChange={(tab) => setParams({ tab: tab === "identity" ? "" : tab ?? "" })} mb="md">
        <Tabs.List>
          <Tabs.Tab value="identity">Identité</Tabs.Tab>
          <Tabs.Tab value="billing">Facturation</Tabs.Tab>
        </Tabs.List>
      </Tabs>
      {params.tab === "billing" ? <BillingSettings organization={data.item} onEditLegal={() => setParams({ tab: "" })} /> : <>
      {!data.item.fec_ready && <Alert color="paille" mb="md">Renseignez le SIREN : il nomme le fichier des écritures comptables (FEC).</Alert>}
      <form onSubmit={form.onSubmit((values) => {
        setError(null);
        save.mutate(values, {
          onSuccess: (body) => {
            client.setQueryData(ORGANIZATION_KEY, { item: body.item });
            void client.invalidateQueries({ queryKey: SESSION_KEY }); // menu « Associés »
            void client.invalidateQueries({ queryKey: BILLING_KEY }); // mentions obligatoires des factures
          },
          onError: (e) => setError(applyApiError(form, e)),
        });
      })}>
        <Stack maw={760}>
          {error && <Alert color="brique" role="alert">{error}</Alert>}
          <Fieldset legend="Identité">
            <Stack>
              {field("name", "Raison sociale", { required: true })}
              <SimpleGrid cols={{ base: 1, sm: 2 }}>
                <Stack gap={4}>
                  {field("siren", "SIREN", { description: "9 chiffres", classNames: { input: "lv-num" } })}
                  {sireneAvailable && !readOnly && (
                    <Group gap="xs">
                      <Button size="compact-sm" variant="light" loading={sirene.isPending} disabled={!isValidSiren(form.values.siren)}
                        onClick={() => sirene.mutate({ siren: form.values.siren.replace(/[\s.]/g, "") }, { onSuccess: () => setProposalOpen(true) })}>
                        Compléter depuis Sirene</Button>
                      {sirene.isError && <Text size="sm" c="var(--lv-brique)" role="alert">{sireneMessage(sirene.error)}</Text>}
                    </Group>
                  )}
                </Stack>
                {association && field("rna", "Numéro RNA", { description: "W suivi de 9 chiffres", classNames: { input: "lv-num" } })}
              </SimpleGrid>
              <Textarea label="Objet" autosize minRows={2} readOnly={readOnly} {...form.getInputProps("purpose")} />
            </Stack>
          </Fieldset>
          <Fieldset legend="Mentions légales">
            <Stack>
              <Text size="sm" c="dimmed">Imprimées sur les factures et les baux.</Text>
              <SimpleGrid cols={{ base: 1, sm: 2 }}>
                {field("legal_form", "Forme juridique", { placeholder: "Société civile immobilière, association…" })}
                {field("share_capital", "Capital social (€)", { inputMode: "decimal", classNames: { input: "lv-num" } })}
                {field("rcs_city", "Greffe du RCS", { placeholder: "Saintes", description: "Sociétés immatriculées" })}
                {field("vat_number", "N° de TVA intracommunautaire", { placeholder: "FR…", classNames: { input: "lv-num" } })}
                <TextInput label="Échéance de la déclaration de TVA" inputMode="numeric" readOnly={readOnly} placeholder="24"
                  description="Jour du mois suivant fixé par votre SIE (15 à 24) ; vide : le 24."
                  classNames={{ input: "lv-num" }} {...form.getInputProps("vat_due_day")} />
              </SimpleGrid>
              {form.values.naf_code && (
                <TextInput label="Activité (code NAF)" readOnly classNames={{ input: "lv-num" }}
                  value={formatNaf(form.values.naf_code)} description={form.values.naf_nomenclature || undefined} />
              )}
            </Stack>
          </Fieldset>
          <Fieldset legend="Adresse du siège">
            <Stack>
              {field("address_line1", "Adresse")}
              {field("address_line2", "Complément")}
              <SimpleGrid cols={{ base: 1, sm: 3 }}>
                {field("postal_code", "Code postal")}
                {field("city", "Ville")}
                {field("country", "Pays")}
              </SimpleGrid>
            </Stack>
          </Fieldset>
          {association ? (
            <Fieldset legend="Signataire des reçus fiscaux">
              <SimpleGrid cols={{ base: 1, sm: 2 }}>
                {field("signatory_name", "Nom")}
                {field("signatory_title", "Qualité", { placeholder: "Président, trésorier…" })}
              </SimpleGrid>
            </Fieldset>
          ) : (
          <Fieldset legend={company ? "Société" : "Associés (sociétés)"}>
            <Stack>
              <Checkbox label="Société avec associés" disabled={readOnly}
                description="Active le menu Associés : parts sociales, comptes courants d'associés."
                {...form.getInputProps("has_associates", { type: "checkbox" })} />
              {form.values.has_associates && (
                <TextInput label="Taux d'intérêt des comptes courants (%)" w={300} readOnly={readOnly} inputMode="decimal"
                  description="Par défaut pour tous les associés ; 0 : pas d'intérêts." {...form.getInputProps("associate_interest_rate")} />
              )}
              {company && (
                <DateInput label="Jeune entreprise innovante depuis" w={300} clearable valueFormat="DD/MM/YYYY"
                  readOnly={readOnly} description="Vide : pas de statut JEI. Repris par la liasse et les crédits d'impôt."
                  {...form.getInputProps("jei_since")} />
              )}
            </Stack>
          </Fieldset>
          )}
          {!readOnly && <Group><Button type="submit" loading={save.isPending}>Enregistrer</Button></Group>}
        </Stack>
      </form>
      <SireneProposalModal opened={proposalOpen} onClose={() => setProposalOpen(false)} result={sirene.data ?? null}
        current={form.values} onApply={(values) => form.setValues(values as Partial<Values>)}
        fields={association ? SIRENE_FIELDS : Object.fromEntries(Object.entries(SIRENE_FIELDS).filter(([k]) => k !== "rna"))}
        note="Le greffe du RCS et le capital ne figurent pas dans Sirene : ils restent à saisir. Pensez à enregistrer." />
      </>}
    </>
  );
}

// Configuration › Structure : identité de la structure (raison sociale, SIREN, RNA, adresse, objet,
// signataire), utilisée par le FEC, les reçus fiscaux et les états ; onglet Facturation (mentions et
// réglages des factures de vente). Modifiable par l'administrateur de l'instance, lisible par tous.
import { useEffect, useState } from "react";
import { Alert, Button, Center, Checkbox, Fieldset, Group, Loader, SimpleGrid, Stack, Tabs, TextInput, Textarea } from "@mantine/core";
import { useForm } from "@mantine/form";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { SESSION_KEY, useCan } from "../../api/session";
import { applyApiError } from "../../components/ApiForm";
import { useUrlParams } from "../../components/FilterBar";
import { PageHeader } from "../../components/PageHeader";
import { BillingSettings } from "../sales/BillingSettings";

export interface Organization {
  name: string; siren: string | null; rna: string | null; address_line1: string | null; address_line2: string | null;
  postal_code: string | null; city: string | null; country: string; purpose: string | null;
  signatory_name: string | null; signatory_title: string | null; fec_ready: boolean;
  /** Module « Associés » : option de l'instance et taux d'intérêt des comptes courants par défaut. */
  has_associates: boolean; associate_interest_rate: string;
}
export const ORGANIZATION_KEY = ["organization"];
const FIELDS = ["name", "siren", "rna", "address_line1", "address_line2", "postal_code", "city", "country", "purpose",
  "signatory_name", "signatory_title"] as const;
type Values = Record<(typeof FIELDS)[number] | "associate_interest_rate", string> & { has_associates: boolean };

export default function OrganizationPage() {
  const can = useCan();
  const client = useQueryClient();
  const [params, setParams] = useUrlParams({ tab: "identity" });
  const { data } = useQuery({ queryKey: ORGANIZATION_KEY,
    queryFn: () => api.get<{ item: Organization }>("/api/v1/organization") });
  const [error, setError] = useState<string | null>(null);
  const form = useForm<Values>({ initialValues: { ...Object.fromEntries(FIELDS.map((f) => [f, ""])),
    has_associates: false, associate_interest_rate: "" } as Values });
  useEffect(() => {
    if (data) form.setValues({ ...Object.fromEntries(FIELDS.map((f) => [f, data.item[f] ?? ""])),
      has_associates: data.item.has_associates, associate_interest_rate: data.item.associate_interest_rate } as Values);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data]);
  const save = useAction((values: Values) => api.put<{ item: Organization; notices: Notice[] }>("/api/v1/organization", values),
    { silent: true });
  if (!data) return <Center h={300}><Loader /></Center>;
  const readOnly = !can.instanceAdmin;
  const field = (name: (typeof FIELDS)[number], label: string, props: Record<string, unknown> = {}) => (
    <TextInput label={label} readOnly={readOnly} {...props} {...form.getInputProps(name)} />
  );
  return (
    <>
      <PageHeader title="Structure" description="Identité de la structure : FEC, reçus fiscaux, factures de vente et états." />
      <Tabs value={params.tab} onChange={(tab) => setParams({ tab: tab === "identity" ? "" : tab ?? "" })} mb="md">
        <Tabs.List>
          <Tabs.Tab value="identity">Identité</Tabs.Tab>
          <Tabs.Tab value="billing">Facturation</Tabs.Tab>
        </Tabs.List>
      </Tabs>
      {params.tab === "billing" ? <BillingSettings /> : <>
      {!data.item.fec_ready && <Alert color="paille" mb="md">Renseignez le SIREN : il nomme le fichier des écritures comptables (FEC).</Alert>}
      <form onSubmit={form.onSubmit((values) => {
        setError(null);
        save.mutate(values, {
          onSuccess: (body) => {
            client.setQueryData(ORGANIZATION_KEY, { item: body.item });
            void client.invalidateQueries({ queryKey: SESSION_KEY }); // menu « Associés »
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
                {field("siren", "SIREN", { description: "9 chiffres", classNames: { input: "lv-num" } })}
                {field("rna", "Numéro RNA", { description: "Associations : W suivi de 9 chiffres", classNames: { input: "lv-num" } })}
              </SimpleGrid>
              <Textarea label="Objet" autosize minRows={2} readOnly={readOnly} {...form.getInputProps("purpose")} />
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
          <Fieldset legend="Signataire des reçus fiscaux">
            <SimpleGrid cols={{ base: 1, sm: 2 }}>
              {field("signatory_name", "Nom")}
              {field("signatory_title", "Qualité", { placeholder: "Président, trésorier…" })}
            </SimpleGrid>
          </Fieldset>
          <Fieldset legend="Associés (sociétés)">
            <Stack>
              <Checkbox label="Société avec associés" disabled={readOnly}
                description="Active le menu Associés : parts sociales, comptes courants d'associés. Pour une SCI ou une entreprise, pas pour une association."
                {...form.getInputProps("has_associates", { type: "checkbox" })} />
              {form.values.has_associates && (
                <TextInput label="Taux d'intérêt des comptes courants (%)" w={300} readOnly={readOnly} inputMode="decimal"
                  description="Par défaut pour tous les associés ; 0 : pas d'intérêts." {...form.getInputProps("associate_interest_rate")} />
              )}
            </Stack>
          </Fieldset>
          {!readOnly && <Group><Button type="submit" loading={save.isPending}>Enregistrer</Button></Group>}
        </Stack>
      </form>
      </>}
    </>
  );
}

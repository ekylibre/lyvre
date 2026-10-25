// Configuration › Structure › Facturation : coordonnées bancaires, conditions de paiement, pénalités,
// logo, message d'envoi des factures. Les mentions légales (forme, capital, RCS, TVA) sont celles de
// l'onglet Identité, rappelées ici en lecture.
import { useEffect, useState } from "react";
import { Alert, Anchor, Button, Center, Checkbox, Fieldset, FileButton, Group, List, Loader, SimpleGrid, Stack, Text, TextInput, Textarea } from "@mantine/core";
import { useForm } from "@mantine/form";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { useCan } from "../../api/session";
import { upload } from "../../api/upload";
import { applyApiError } from "../../components/ApiForm";
import { BILLING_KEY } from "./types";

/** Mentions légales de la Structure (lecture). */
export interface LegalMentions {
  legal_form: string | null; share_capital: string; rcs_mention: string; vat_number: string | null;
}

interface Billing {
  iban: string; bic: string;
  payment_terms_days: number; late_penalty_text: string; recovery_fee: boolean; discount_text: string; footer: string;
  send_subject: string; send_body: string; reminder_subject: string; reminder_body: string; has_logo: boolean;
  defaults: { send_subject: string; send_body: string; reminder_subject: string; reminder_body: string; late_penalty_text: string };
  readiness: { key: string; label: string; ok: boolean }[];
}
type Values = Omit<Billing, "has_logo" | "defaults" | "readiness" | "payment_terms_days"> & { payment_terms_days: string };
const TEXT = ["iban", "bic", "late_penalty_text", "discount_text", "footer",
  "send_subject", "send_body", "reminder_subject", "reminder_body"] as const;

export function BillingSettings({ organization, onEditLegal }: { organization: LegalMentions; onEditLegal: () => void }) {
  const can = useCan();
  const client = useQueryClient();
  const { data } = useQuery({ queryKey: BILLING_KEY, queryFn: () => api.get<{ item: Billing }>("/api/v1/billing-settings") });
  const [error, setError] = useState<string | null>(null);
  const form = useForm<Values>({ initialValues: { ...Object.fromEntries(TEXT.map((k) => [k, ""])), payment_terms_days: "30", recovery_fee: true } as Values });
  useEffect(() => {
    if (data) form.setValues({ ...Object.fromEntries(TEXT.map((k) => [k, data.item[k] ?? ""])),
      payment_terms_days: String(data.item.payment_terms_days), recovery_fee: data.item.recovery_fee } as Values);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data]);
  const save = useAction((values: Values) => api.put<{ item: Billing; notices: Notice[] }>("/api/v1/billing-settings", values), { silent: true });
  const removeLogo = useAction(() => api.delete<{ item: Billing; notices: Notice[] }>("/api/v1/billing-settings/logo"));
  const [uploading, setUploading] = useState(false);
  if (!data) return <Center h={200}><Loader /></Center>;
  const d = data.item;
  const readOnly = !can.instanceAdmin;
  const setItem = (item: Billing) => client.setQueryData(BILLING_KEY, { item });
  const sendLogo = async (file: File | null) => {
    if (!file) return;
    const body = new FormData();
    body.append("logo", file);
    setUploading(true);
    try { setItem((await upload<{ item: Billing }>("/api/v1/billing-settings/logo", body)).item); } finally { setUploading(false); }
  };
  const missing = d.readiness.filter((r) => !r.ok);
  return (
    <form onSubmit={form.onSubmit((values) => { setError(null); save.mutate(values, { onSuccess: (r) => setItem(r.item), onError: (e) => setError(applyApiError(form, e)) }); })}>
      <Stack maw={760}>
        {error && <Alert color="brique" role="alert">{error}</Alert>}
        {missing.length > 0 && <Alert color="paille" title="Mentions obligatoires manquantes (aucune facture ne s'émet sans elles) :">
          <List size="sm">{missing.map((r) => <List.Item key={r.key}>{r.label}</List.Item>)}</List></Alert>}
        <Fieldset legend="Mentions légales">
          <Stack gap="xs">
            <SimpleGrid cols={{ base: 1, sm: 2 }}>
              <TextInput label="Forme juridique" readOnly value={organization.legal_form ?? ""} placeholder="—" />
              <TextInput label="Capital social (€)" readOnly value={organization.share_capital} placeholder="—" classNames={{ input: "lv-num" }} />
              <TextInput label="Immatriculation" readOnly value={organization.rcs_mention} placeholder="—" />
              <TextInput label="N° de TVA intracommunautaire" readOnly value={organization.vat_number ?? ""} placeholder="—" classNames={{ input: "lv-num" }} />
            </SimpleGrid>
            <Text size="sm" c="dimmed">Saisies dans l'onglet Identité, communes aux factures et aux baux.{" "}
              <Anchor component="button" type="button" size="sm" onClick={onEditLegal}>Modifier dans Structure</Anchor></Text>
          </Stack>
        </Fieldset>
        <Fieldset legend="Paiement">
          <Stack>
            <SimpleGrid cols={{ base: 1, sm: 3 }}>
              <TextInput label="IBAN" readOnly={readOnly} classNames={{ input: "lv-num" }} {...form.getInputProps("iban")} />
              <TextInput label="BIC" readOnly={readOnly} classNames={{ input: "lv-num" }} {...form.getInputProps("bic")} />
              <TextInput label="Délai de paiement (jours)" inputMode="numeric" readOnly={readOnly} {...form.getInputProps("payment_terms_days")} />
            </SimpleGrid>
            <Textarea label="Pénalités de retard" autosize minRows={2} readOnly={readOnly} placeholder={d.defaults.late_penalty_text} {...form.getInputProps("late_penalty_text")} />
            <Checkbox label="Indemnité forfaitaire de 40 € pour frais de recouvrement (clients professionnels)" disabled={readOnly}
              {...form.getInputProps("recovery_fee", { type: "checkbox" })} />
            <TextInput label="Escompte" placeholder="Pas d'escompte pour paiement anticipé." readOnly={readOnly} {...form.getInputProps("discount_text")} />
          </Stack>
        </Fieldset>
        <Fieldset legend="Présentation">
          <Stack>
            <Group>
              <Text size="sm">Logo : {d.has_logo ? "enregistré" : "aucun"}</Text>
              {!readOnly && <FileButton onChange={(f) => void sendLogo(f)} accept="image/png,image/jpeg">
                {(props) => <Button size="compact-sm" variant="default" loading={uploading} {...props}>{d.has_logo ? "Remplacer" : "Ajouter"} (PNG, JPEG)</Button>}
              </FileButton>}
              {!readOnly && d.has_logo && <Button size="compact-sm" variant="subtle" color="brique" loading={removeLogo.isPending}
                onClick={() => removeLogo.mutate(undefined, { onSuccess: (r) => setItem(r.item) })}>Retirer</Button>}
            </Group>
            <Textarea label="Pied de page des factures" autosize minRows={2} readOnly={readOnly} {...form.getInputProps("footer")} />
          </Stack>
        </Fieldset>
        <Fieldset legend="Message d'envoi par email">
          <Stack>
            <TextInput label="Objet" placeholder={d.defaults.send_subject} readOnly={readOnly} {...form.getInputProps("send_subject")} />
            <Textarea label="Message" autosize minRows={5} placeholder={d.defaults.send_body} readOnly={readOnly} {...form.getInputProps("send_body")} />
            <Text size="xs" c="dimmed">Champs : {"{type}"}, {"{numero}"}, {"{date}"}, {"{montant}"}, {"{echeance}"}, {"{client}"}, {"{organisation}"}. Vide : message par défaut.</Text>
          </Stack>
        </Fieldset>
        <Fieldset legend="Message de relance">
          <Stack>
            <TextInput label="Objet" placeholder={d.defaults.reminder_subject} readOnly={readOnly} {...form.getInputProps("reminder_subject")} />
            <Textarea label="Message" autosize minRows={5} placeholder={d.defaults.reminder_body} readOnly={readOnly} {...form.getInputProps("reminder_body")} />
            <Text size="xs" c="dimmed">Champs supplémentaires : {"{date_echeance}"}, {"{restant}"} (restant dû).</Text>
          </Stack>
        </Fieldset>
        {!readOnly && <Group><Button type="submit" loading={save.isPending}>Enregistrer</Button></Group>}
      </Stack>
    </form>
  );
}

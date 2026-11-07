// Configuration › Structure › Fiscalité (lot AG1.a, claudedocs/design_compta_agricole.md § 3 et § 8) : forme
// juridique codée, régimes datés (IR / IS, bénéfices agricoles, TVA), options fiscales datées avec la date limite
// de renonciation calculée. Lecture pour tous, modification par l'administrateur de l'instance.
import { useEffect, useState } from "react";
import { Alert, Badge, Button, Checkbox, Fieldset, Group, Loader, Center, Select, SimpleGrid, Stack, Table, Text, TextInput } from "@mantine/core";
import { DateInput } from "@mantine/dates";
import { useForm } from "@mantine/form";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { useCan } from "../../api/session";
import { applyApiError, FormBody } from "../../components/ApiForm";
import { confirmAction } from "../../components/ConfirmButton";
import { FormModal } from "../../components/FormModal";
import { formatDate } from "../../lib/format";
import { BaRegimePanel } from "./BaRegimePanel";

type Option = { value: string; label: string };
export interface TaxPeriod {
  id: number; kind: string; kind_label: string; value: string; value_label: string;
  start_date: string; end_date: string | null; origin: string; origin_label: string; note: string | null;
}
export interface TaxOption {
  id: number; code: string; label: string; start_date: string; duration_years: number | null; tacit_renewal: boolean;
  renounced_on: string | null; current_period: { first_year: number; last_year: number } | null;
  renounce_by: { date: string | null; reliability: string; note: string } | null; note: string | null;
}
export interface TaxProfilePayload {
  legal_form_code: string | null; created_on: string | null; periods: TaxPeriod[]; options: TaxOption[];
  current: Record<string, string | null>; warnings: string[];
}
interface TaxMeta {
  legal_forms: Option[]; origins: Option[]; options: (Option & { description?: string | null })[];
  kinds: (Option & { values: Option[] })[];
}
type Response = { item: TaxProfilePayload; meta: TaxMeta; notices?: Notice[] };

export const TAX_PROFILE_KEY = ["tax-profile"];
/** Couleur de la pastille de fiabilité d'un paramètre réglementaire (V, R, A, I). */
export const RELIABILITY_COLORS: Record<string, string> = { V: "lichen", R: "ardoise", A: "paille", I: "brique" };

const iso = (value: unknown) => (value ? String(value).slice(0, 10) : null);

function PeriodForm({ meta, period, onDone }: { meta: TaxMeta; period: TaxPeriod | null; onDone: () => void }) {
  const [error, setError] = useState<string | null>(null);
  const form = useForm({ initialValues: {
    kind: period?.kind ?? "income_tax", value: period?.value ?? "", origin: period?.origin ?? "law",
    start_date: period?.start_date ?? null as string | null, end_date: period?.end_date ?? null as string | null,
    note: period?.note ?? "",
  } });
  const client = useQueryClient();
  const save = useAction((values: typeof form.values) => {
    const body = { ...values, start_date: iso(values.start_date), end_date: iso(values.end_date) };
    return period ? api.patch<Response>(`/api/v1/tax-profiles/${period.id}`, body)
      : api.post<Response>("/api/v1/tax-profiles", body);
  }, { silent: true });
  const kind = meta.kinds.find((k) => k.value === form.values.kind);
  return (
    <form onSubmit={form.onSubmit((values) => save.mutate(values, {
      onSuccess: (body) => { client.setQueryData(TAX_PROFILE_KEY, body); onDone(); },
      onError: (e) => setError(applyApiError(form, e)),
    }))}>
      <FormBody error={error} submitLabel={period ? "Enregistrer" : "Ajouter la période"} onCancel={onDone} loading={save.isPending}>
        <Select label="Régime" data={meta.kinds} allowDeselect={false} disabled={!!period}
          {...form.getInputProps("kind")} onChange={(v) => { form.setFieldValue("kind", v ?? "income_tax"); form.setFieldValue("value", ""); }} />
        <Select label="Valeur" required data={kind?.values ?? []} allowDeselect={false} {...form.getInputProps("value")} />
        <Select label="Origine" data={meta.origins} allowDeselect={false} {...form.getInputProps("origin")} />
        <SimpleGrid cols={2}>
          <DateInput label="Début" required valueFormat="DD/MM/YYYY" {...form.getInputProps("start_date")}
            description="En général le 1er jour d'un exercice." />
          <DateInput label="Fin" clearable valueFormat="DD/MM/YYYY" {...form.getInputProps("end_date")}
            description="Vide : en cours." />
        </SimpleGrid>
        {!period && <Text size="sm" c="dimmed">Une période en cours du même régime se termine la veille du début.</Text>}
        <TextInput label="Note" {...form.getInputProps("note")} />
      </FormBody>
    </form>
  );
}

function OptionForm({ meta, option, onDone }: { meta: TaxMeta; option: TaxOption | null; onDone: () => void }) {
  const [error, setError] = useState<string | null>(null);
  const form = useForm({ initialValues: {
    code: option?.code ?? "", start_date: option?.start_date ?? null as string | null,
    duration_years: option?.duration_years != null ? String(option.duration_years) : "",
    tacit_renewal: option?.tacit_renewal ?? true, renounced_on: option?.renounced_on ?? null as string | null,
    note: option?.note ?? "",
  } });
  const client = useQueryClient();
  const save = useAction((values: typeof form.values) => {
    const body: Record<string, unknown> = { ...values, start_date: iso(values.start_date), renounced_on: iso(values.renounced_on) };
    if (!option && !values.duration_years) delete body.duration_years; // durée par défaut des paramètres réglementaires
    return option ? api.patch<Response>(`/api/v1/tax-options/${option.id}`, body) : api.post<Response>("/api/v1/tax-options", body);
  }, { silent: true });
  return (
    <form onSubmit={form.onSubmit((values) => save.mutate(values, {
      onSuccess: (body) => { client.setQueryData(TAX_PROFILE_KEY, body); onDone(); },
      onError: (e) => setError(applyApiError(form, e)),
    }))}>
      <FormBody error={error} submitLabel={option ? "Enregistrer" : "Ajouter l'option"} onCancel={onDone} loading={save.isPending}>
        <Select label="Option" required data={meta.options.map(({ value, label }) => ({ value, label }))} disabled={!!option}
          description={meta.options.find((o) => o.value === form.values.code)?.description ?? undefined} {...form.getInputProps("code")} />
        <DateInput label="Prise d'effet" required valueFormat="DD/MM/YYYY" {...form.getInputProps("start_date")} />
        <SimpleGrid cols={2}>
          <TextInput label="Durée (années)" inputMode="numeric" classNames={{ input: "lv-num" }}
            description={option ? "Vide : sans terme." : "Vide : durée légale."} {...form.getInputProps("duration_years")} />
          <Checkbox mt="xl" label="Reconduction tacite" {...form.getInputProps("tacit_renewal", { type: "checkbox" })} />
        </SimpleGrid>
        {option && <DateInput label="Renoncée le" clearable valueFormat="DD/MM/YYYY" {...form.getInputProps("renounced_on")} />}
        <TextInput label="Note" {...form.getInputProps("note")} />
      </FormBody>
    </form>
  );
}

export function FiscalProfile({ siren, farm = false }: { siren: string | null; farm?: boolean }) {
  const can = useCan();
  const readOnly = !can.instanceAdmin;
  const client = useQueryClient();
  const { data } = useQuery({ queryKey: TAX_PROFILE_KEY, queryFn: () => api.get<Response>("/api/v1/tax-profile") });
  const [error, setError] = useState<string | null>(null);
  const [periodModal, setPeriodModal] = useState<TaxPeriod | "new" | null>(null);
  const [optionModal, setOptionModal] = useState<TaxOption | "new" | null>(null);
  const form = useForm({ initialValues: { legal_form_code: "", created_on: null as string | null } });
  useEffect(() => {
    if (data) form.setValues({ legal_form_code: data.item.legal_form_code ?? "", created_on: data.item.created_on });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data]);
  const saveIdentity = useAction((values: typeof form.values) => api.put<Response>("/api/v1/tax-profile",
    { legal_form_code: values.legal_form_code, created_on: iso(values.created_on) }), { silent: true });
  const removePeriod = useAction((p: TaxPeriod) => api.delete<Response>(`/api/v1/tax-profiles/${p.id}`), { invalidate: [TAX_PROFILE_KEY] });
  const removeOption = useAction((o: TaxOption) => api.delete<Response>(`/api/v1/tax-options/${o.id}`), { invalidate: [TAX_PROFILE_KEY] });
  if (!data) return <Center h={200}><Loader /></Center>;
  const { item, meta } = data;
  return (
    <Stack maw={900}>
      {item.warnings.map((w) => <Alert key={w} color="paille">{w}</Alert>)}
      <form onSubmit={form.onSubmit((values) => {
        setError(null);
        saveIdentity.mutate(values, {
          onSuccess: (body) => client.setQueryData(TAX_PROFILE_KEY, body),
          onError: (e) => setError(applyApiError(form, e)),
        });
      })}>
        <Fieldset legend="Forme juridique">
          <Stack>
            {error && <Alert color="brique" role="alert">{error}</Alert>}
            <SimpleGrid cols={{ base: 1, sm: 2 }}>
              <Select label="Forme" data={meta.legal_forms} clearable readOnly={readOnly}
                description={siren ? "Proposée par « Compléter depuis Sirene » (onglet Identité)." : undefined}
                {...form.getInputProps("legal_form_code")} />
              <DateInput label="Date de création" clearable valueFormat="DD/MM/YYYY" readOnly={readOnly}
                description="Société créée depuis 1997 : micro-BA impossible (sauf EARL unipersonnelle)."
                {...form.getInputProps("created_on")} />
            </SimpleGrid>
            {!readOnly && <Group><Button type="submit" loading={saveIdentity.isPending}>Enregistrer</Button></Group>}
          </Stack>
        </Fieldset>
      </form>

      <Fieldset legend="Régimes">
        <Stack>
          <Text size="sm" c="dimmed">Une ligne par période : un changement de régime (passage au réel, option IS) ouvre une nouvelle période.</Text>
          {item.periods.length === 0 ? <Text size="sm">Aucun régime renseigné.</Text> : (
            <Table striped>
              <Table.Thead><Table.Tr>
                <Table.Th>Régime</Table.Th><Table.Th>Valeur</Table.Th><Table.Th>Origine</Table.Th>
                <Table.Th>Début</Table.Th><Table.Th>Fin</Table.Th><Table.Th />
              </Table.Tr></Table.Thead>
              <Table.Tbody>{item.periods.map((p) => (
                <Table.Tr key={p.id}>
                  <Table.Td>{p.kind_label}</Table.Td>
                  <Table.Td>{p.value_label}{p.note && <Text size="xs" c="dimmed">{p.note}</Text>}</Table.Td>
                  <Table.Td>{p.origin_label}</Table.Td>
                  <Table.Td className="lv-num">{formatDate(p.start_date)}</Table.Td>
                  <Table.Td className="lv-num">{p.end_date ? formatDate(p.end_date) : "en cours"}</Table.Td>
                  <Table.Td>{!readOnly && (
                    <Group gap={4} justify="flex-end" wrap="nowrap">
                      <Button variant="subtle" size="compact-sm" onClick={() => setPeriodModal(p)}>Modifier</Button>
                      <Button variant="subtle" size="compact-sm" color="brique" onClick={() => confirmAction({
                        title: "Supprimer cette période ?", message: `${p.kind_label} : ${p.value_label}.`,
                        confirmLabel: "Supprimer", onConfirm: () => removePeriod.mutate(p) })}>Supprimer</Button>
                    </Group>)}
                  </Table.Td>
                </Table.Tr>))}
              </Table.Tbody>
            </Table>)}
          {!readOnly && <Group><Button variant="light" onClick={() => setPeriodModal("new")}>Ajouter une période</Button></Group>}
        </Stack>
      </Fieldset>

      <Fieldset legend="Options fiscales">
        <Stack>
          <Text size="sm" c="dimmed">La date limite de renonciation est calculée pour la période en cours de l'option ;
            la pastille indique la fiabilité de la règle (rouge : à valider).</Text>
          {item.options.length === 0 ? <Text size="sm">Aucune option.</Text> : (
            <Table striped>
              <Table.Thead><Table.Tr>
                <Table.Th>Option</Table.Th><Table.Th>Effet</Table.Th><Table.Th>Période en cours</Table.Th>
                <Table.Th>Renoncer avant le</Table.Th><Table.Th />
              </Table.Tr></Table.Thead>
              <Table.Tbody>{item.options.map((o) => (
                <Table.Tr key={o.id}>
                  <Table.Td>{o.label}{o.note && <Text size="xs" c="dimmed">{o.note}</Text>}</Table.Td>
                  <Table.Td className="lv-num">{formatDate(o.start_date)}</Table.Td>
                  <Table.Td className="lv-num">{o.renounced_on ? `renoncée le ${formatDate(o.renounced_on)}`
                    : o.current_period ? `${o.current_period.first_year}–${o.current_period.last_year}${o.tacit_renewal ? " (tacite)" : ""}` : "sans terme"}</Table.Td>
                  <Table.Td>{o.renounce_by && (
                    <Group gap={6} wrap="nowrap">
                      <Text size="sm" className="lv-num">{o.renounce_by.date ? formatDate(o.renounce_by.date) : "—"}</Text>
                      <Badge size="xs" color={RELIABILITY_COLORS[o.renounce_by.reliability] ?? "gray"} title={o.renounce_by.note}>
                        {o.renounce_by.reliability}</Badge>
                    </Group>)}
                  </Table.Td>
                  <Table.Td>{!readOnly && (
                    <Group gap={4} justify="flex-end" wrap="nowrap">
                      <Button variant="subtle" size="compact-sm" onClick={() => setOptionModal(o)}>Modifier</Button>
                      <Button variant="subtle" size="compact-sm" color="brique" onClick={() => confirmAction({
                        title: "Supprimer cette option ?", message: o.label, confirmLabel: "Supprimer",
                        onConfirm: () => removeOption.mutate(o) })}>Supprimer</Button>
                    </Group>)}
                  </Table.Td>
                </Table.Tr>))}
              </Table.Tbody>
            </Table>)}
          {!readOnly && <Group><Button variant="light" onClick={() => setOptionModal("new")}>Ajouter une option</Button></Group>}
        </Stack>
      </Fieldset>

      {farm && <BaRegimePanel editable={can.write} />}

      <FormModal opened={periodModal !== null} onClose={() => setPeriodModal(null)}
        title={periodModal === "new" ? "Nouvelle période de régime" : "Modifier la période"}>
        {periodModal !== null && <PeriodForm meta={meta} period={periodModal === "new" ? null : periodModal}
          onDone={() => setPeriodModal(null)} />}
      </FormModal>
      <FormModal opened={optionModal !== null} onClose={() => setOptionModal(null)}
        title={optionModal === "new" ? "Nouvelle option fiscale" : "Modifier l'option"}>
        {optionModal !== null && <OptionForm meta={meta} option={optionModal === "new" ? null : optionModal}
          onDone={() => setOptionModal(null)} />}
      </FormModal>
    </Stack>
  );
}

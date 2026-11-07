// Fiche d'immobilisation (lot F5) : compte, dates, valeur, méthode (linéaire, dégressif, non
// amortissable), durée, reprise d'un cumul déjà amorti, projet ; composant d'un bien (`parentId`).
import { useState } from "react";
import { Alert, Anchor, Checkbox, Select, SimpleGrid, Table, Text, TextInput, Textarea } from "@mantine/core";
import { useForm } from "@mantine/form";
import { api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { applyApiError, FormBody } from "../../components/ApiForm";
import { MoneyInput } from "../../components/Money";
import { useProjectOptions } from "../projects/LineProjectModal";
import { ASSETS_KEY, isLivingAccount, type AssetItem, type AssetsMeta } from "./types";
import { ActivitySelect, useAnalyticTargets } from "../../components/AnalyticSelect";

export function AssetForm({ asset, meta, parentId, onDone }: {
  asset: AssetItem | null; meta: AssetsMeta; parentId?: number; onDone: (item?: AssetItem) => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const projects = useProjectOptions().data?.items ?? [];
  const targets = useAnalyticTargets();
  const form = useForm({ initialValues: {
    label: asset?.label ?? "", account_id: asset ? String(asset.account.id) : "",
    acquired_on: asset?.acquired_on ?? new Date().toISOString().slice(0, 10), in_service_date: asset?.in_service_date ?? "",
    acquisition_cents: asset?.acquisition_cents ?? (null as number | null), residual_cents: asset?.residual_cents ?? 0,
    method: asset?.method ?? "linear", duration_months: asset?.duration_months ? String(asset.duration_months) : "60",
    fiscal_coefficient: asset?.fiscal_coefficient ?? "", prior_depreciation_cents: asset?.prior_depreciation_cents ?? 0,
    prior_as_of: asset?.prior_as_of ?? "", project_id: asset?.project_id ? String(asset.project_id) : "",
    notes: asset?.notes ?? "", activity_id: asset?.activity_id ?? (null as number | null), waiting: asset ? asset.status === "waiting" : false,
    living_kind: asset?.living?.kind ?? "", species: asset?.living?.species ?? "", age_class: asset?.living?.age_class ?? "",
    units: asset?.living?.units != null ? String(asset.living.units) : "", origin: asset?.living?.origin ?? "",
    full_first_year: asset ? !!asset.full_first_year : true,
  } });
  const accountLabel = meta.accounts.find((o) => o.value === form.values.account_id)?.label;
  const living = isLivingAccount(accountLabel);
  // Lot CG5.d : plantation (2346, 246) ou nature « plantation » : repères BOFiP et annuité entière.
  const plantation = living && (form.values.living_kind === "plantation" || /^(2346|246)/.test(accountLabel ?? ""));
  const save = useAction((v: typeof form.values) => {
    const body = { ...v, account_id: Number(v.account_id) || null, duration_months: Number(v.duration_months) || null,
      project_id: v.project_id ? Number(v.project_id) : null, parent_id: parentId ?? asset?.parent_id ?? null,
      in_service_date: v.in_service_date || null, prior_as_of: v.prior_as_of || null, fiscal_coefficient: v.fiscal_coefficient || null,
      living_kind: v.living_kind || null, origin: v.origin || null, units: v.units === "" ? null : Number(v.units),
      ...(plantation || asset ? { full_first_year: v.full_first_year } : {}) };
    return asset ? api.patch<{ item: AssetItem; notices: Notice[] }>(`/api/v1/assets/${asset.id}`, body)
      : api.post<{ item: AssetItem; notices: Notice[] }>("/api/v1/assets", body);
  }, { invalidate: [ASSETS_KEY], silent: true });
  const method = form.values.method;
  const money = (name: "acquisition_cents" | "residual_cents" | "prior_depreciation_cents") => ({
    value: form.values[name], onChange: (cents: number | null) => form.setFieldValue(name, cents ?? 0), error: form.errors[name] });
  return (
    <form onSubmit={form.onSubmit((v) => save.mutate(v, { onSuccess: (r) => onDone(r.item), onError: (e) => setError(applyApiError(form, e)) }))}>
      <FormBody error={error} submitLabel={asset ? "Enregistrer" : "Créer l'immobilisation"} onCancel={() => onDone()} loading={save.isPending}>
        <SimpleGrid cols={{ base: 1, sm: 2 }}>
          <TextInput label="Libellé" required data-autofocus {...form.getInputProps("label")} />
          <Select label="Compte" required searchable data={meta.accounts} {...form.getInputProps("account_id")}
            description="2x ; 23x : immobilisation en cours" />
        </SimpleGrid>
        <SimpleGrid cols={{ base: 2, sm: 4 }}>
          <TextInput label="Acquisition" type="date" required {...form.getInputProps("acquired_on")} />
          <TextInput label="Mise en service" type="date" {...form.getInputProps("in_service_date")} disabled={form.values.waiting} />
          <MoneyInput label="Valeur d'origine" required {...money("acquisition_cents")} />
          <MoneyInput label="Valeur résiduelle" {...money("residual_cents")} />
        </SimpleGrid>
        {living && (
          <SimpleGrid cols={{ base: 2, sm: 5 }}>
            <Select label="Nature" data={meta.living_kinds ?? []} placeholder="selon le compte" clearable {...form.getInputProps("living_kind")} />
            <TextInput label="Espèce" {...form.getInputProps("species")} />
            <TextInput label="Catégorie d'âge" {...form.getInputProps("age_class")} />
            <TextInput label="Effectif (têtes, plants)" inputMode="numeric" {...form.getInputProps("units")} />
            <Select label="Origine" data={meta.living_origins ?? []} clearable {...form.getInputProps("origin")} />
          </SimpleGrid>)}
        {!asset && <Checkbox label="Immobilisation en cours (travaux, pas encore utilisée)" {...form.getInputProps("waiting", { type: "checkbox" })} />}
        {plantation && <PlantationHints refs={meta.plantation_references} />}
        {(plantation || asset?.full_first_year) && (
          <Checkbox label="Annuité entière dès l'exercice de mise en service (première récolte)"
            description="BOFiP : l'amortissement part de l'exercice de la première récolte" {...form.getInputProps("full_first_year", { type: "checkbox" })} />)}
        <SimpleGrid cols={{ base: 2, sm: 3 }}>
          <Select label="Méthode" data={meta.methods} allowDeselect={false} {...form.getInputProps("method")} />
          {method !== "none" && <TextInput label="Durée (mois)" inputMode="numeric" required {...form.getInputProps("duration_months")}
            description={Number(form.values.duration_months) ? `Taux ${(1200 / Number(form.values.duration_months)).toFixed(2).replace(".", ",")} %` : undefined} />}
          {method === "regressive" && <TextInput label="Coefficient fiscal" placeholder="selon la durée" {...form.getInputProps("fiscal_coefficient")} />}
        </SimpleGrid>
        <SimpleGrid cols={{ base: 1, sm: 3 }}>
          <MoneyInput label="Déjà amorti (reprise)" {...money("prior_depreciation_cents")} />
          <TextInput label="Au" type="date" {...form.getInputProps("prior_as_of")} />
          <Select label="Projet" clearable searchable data={projects} {...form.getInputProps("project_id")} />
        </SimpleGrid>
        <ActivitySelect label="Activité" description="Dotations et résultat de cession dans la marge de l'activité." targets={targets}
          value={form.values.activity_id} onChange={(v) => form.setFieldValue("activity_id", v)} />
        <Textarea label="Notes" autosize minRows={2} {...form.getInputProps("notes")} />
      </FormBody>
    </form>
  );
}


function PlantationHints({ refs }: { refs?: AssetsMeta["plantation_references"] }) {
  if (!refs) return null;
  const { orchards } = refs;
  const cell = (row: unknown, i: number) => (Array.isArray(row) ? row[i] ?? "—" : "—");
  return (
    <Alert color="paille" title="Repères de durée (BOFiP)">
      <Text size="sm">Vigne : {refs.vine_years} ans à partir de la première déclaration de récolte ({refs.vine_source}).
        Vergers : durée de production à partir de la première récolte, à choisir avec les repères ci-dessous.</Text>
      <Table fz="xs" mt={4}>
        <Table.Thead><Table.Tr><Table.Th>Espèce</Table.Th>
          {Object.values(orchards.conducts).map((c) => <Table.Th key={c}>{c} : 1re récolte / début de décroissance (ans)</Table.Th>)}</Table.Tr></Table.Thead>
        <Table.Tbody>{orchards.species.map((s) => (
          <Table.Tr key={s.key}><Table.Td>{s.label}</Table.Td>
            {Object.keys(orchards.conducts).map((k) => <Table.Td key={k}>{s[k] ? `${cell(s[k], 1)} / ${cell(s[k], 2)}` : "—"}</Table.Td>)}</Table.Tr>))}
        </Table.Tbody>
      </Table>
      <Text size="xs" c="dimmed">Source : <Anchor href={orchards.source} target="_blank" size="xs">{orchards.source_label}</Anchor>. {orchards.note}</Text>
    </Alert>
  );
}

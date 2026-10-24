// Ventes › Baux › Nouveau bail (lot L1) : assistant en trois étapes. 1. Bail (parties, type, dates,
// dépôt, révision) — enregistré en brouillon ; 2. Biens loués (une ligne par élément : lettre,
// désignation, nature, surfaces, références cadastrales) ; 3. Loyer et facturation (prix annuel par
// ligne, échéance) — « Valider » crée la facture récurrente. Le même assistant modifie un bail validé.
import { useState } from "react";
import { useParams, useSearchParams } from "react-router";
import {
  ActionIcon, Alert, Button, Center, Checkbox, Group, Loader, Paper, SegmentedControl, Select, SimpleGrid, Stack, Stepper,
  Table, Text, TextInput, Textarea,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, Trash2 } from "lucide-react";
import { api } from "../../api/client";
import { useAction, useList, type Notice } from "../../api/resources";
import { applyApiError, FormBody } from "../../components/ApiForm";
import { FormModal } from "../../components/FormModal";
import { MoneyText } from "../../components/Money";
import { PageHeader } from "../../components/PageHeader";
import { AppLink, useGoTo } from "../../app/navigation";
import type { Option } from "../purchases/types";
import { LEASES_KEY, RECURRENCES_KEY, SALES_KEY, type Lease, type LeaseItem } from "./types";

export interface LeasesMeta {
  tenants: Option[]; accounts: Option[]; bank_accounts: Option[]; qonto: boolean; kinds: Option[]; natures: Option[];
  units: Option[]; indexes: Option[]; frequencies: Option[];
}
type LeaseResponse = { item: Lease; notices?: Notice[] };
type ItemResponse = { item: LeaseItem; lease: Lease; notices?: Notice[] };

const euros = (cents: number) => (cents / 100).toFixed(2).replace(".", ",");
const PER_YEAR: Record<string, number> = { monthly: 12, quarterly: 4, yearly: 1 };

/** Hectares à l'are près, comme le serveur (4 940 m² → 0,49 ha). */
export function hectares(areaM2: number) {
  return Math.round(areaM2 / 100) / 100;
}

/** Montant annuel d'une ligne (centimes) : m² × prix, hectares × prix, ou forfait. */
export function annualOf(unit: string, areaM2: number, priceCents: number) {
  if (unit === "m2") return areaM2 * priceCents;
  if (unit === "ha") return Math.round(hectares(areaM2) * priceCents);
  return priceCents;
}

function toCents(value: string) {
  const n = Number(value.replace(/\s/g, "").replace(",", "."));
  return Number.isFinite(n) && n >= 0 ? Math.round(n * 100) : 0;
}

function quantity(item: Pick<LeaseItem, "area_m2">, unit: string) {
  if (unit === "m2") return `${item.area_m2.toLocaleString("fr-FR")} m²`;
  if (unit === "ha") return `${hectares(item.area_m2).toLocaleString("fr-FR", { minimumFractionDigits: 2 })} ha`;
  return "—";
}

// ------------------------------------------------------------------ étape 1 : bail

function TermsStep({ lease, meta, onSaved }: { lease: Lease | null; meta: LeasesMeta; onSaved: (lease: Lease) => void }) {
  const goTo = useGoTo();
  const [error, setError] = useState<string | null>(null);
  const form = useForm({ initialValues: {
    entity_id: lease ? String(lease.tenant.id) : "", kind: lease?.kind ?? "", unit_label: lease?.unit_label ?? "",
    premises_label: lease?.premises_label ?? "", address_line1: lease?.address_line1 ?? "", address_line2: lease?.address_line2 ?? "",
    postal_code: lease?.postal_code ?? "", city: lease?.city ?? "",
    start_date: lease?.start_date ?? new Date().toISOString().slice(0, 10), end_date: lease?.end_date ?? "",
    deposit: lease ? euros(lease.deposit_cents) : "", index_code: lease?.index_code ?? "",
    index_reference_period: lease?.index_reference_period ?? "", index_reference_value: lease?.index_reference_value ?? "",
    revision_months: lease?.revision_months || "12", revise_deposit: lease?.revise_deposit ?? false,
    signed_on_place: lease?.signed_on_place ?? "", notes: lease?.notes ?? "",
  } });
  const save = useAction((values: typeof form.values) => {
    const body = { ...values, end_date: values.end_date || null };
    return lease ? api.patch<LeaseResponse>(`/api/v1/leases/${lease.id}`, body)
      : api.post<LeaseResponse>("/api/v1/leases", { ...body, draft: true });
  }, { invalidate: [LEASES_KEY], silent: true });
  return (
    <form onSubmit={form.onSubmit((values) => save.mutate(values, {
      onSuccess: (r) => onSaved(r.item), onError: (e) => setError(applyApiError(form, e)) }))}>
      <Stack>
        {error && <Alert color="brique" role="alert">{error}</Alert>}
        <SimpleGrid cols={{ base: 1, sm: 2 }}>
          <Select label="Locataire (preneur)" required searchable data={meta.tenants} {...form.getInputProps("entity_id")}
            description="Tiers : adresse et e-mail sur sa fiche." />
          <Select label="Type de bail" required data={meta.kinds} {...form.getInputProps("kind")} />
          <TextInput label="Désignation" required placeholder="La Vauzelle, appartement 2B…" {...form.getInputProps("unit_label")}
            description="Reprise sur les avis d'échéance." />
          <TextInput label="Lieu-dit des biens" placeholder="La Vauzelle" {...form.getInputProps("premises_label")} />
        </SimpleGrid>
        <TextInput label="Adresse des biens" {...form.getInputProps("address_line1")} />
        <SimpleGrid cols={{ base: 1, sm: 3 }}>
          <TextInput label="Complément" {...form.getInputProps("address_line2")} />
          <TextInput label="Code postal" {...form.getInputProps("postal_code")} />
          <TextInput label="Ville" {...form.getInputProps("city")} />
        </SimpleGrid>
        <SimpleGrid cols={{ base: 1, sm: 3 }}>
          <TextInput label="Date d'effet" type="date" required {...form.getInputProps("start_date")} />
          <TextInput label="Fin" type="date" {...form.getInputProps("end_date")} />
          <TextInput label="Dépôt de garantie (€)" inputMode="decimal" {...form.getInputProps("deposit")} />
        </SimpleGrid>
        <Paper withBorder p="sm">
          <Stack gap="sm">
            <Text fw={600} size="sm">Révision du loyer</Text>
            <SimpleGrid cols={{ base: 1, sm: 2 }}>
              <Select label="Indice" clearable placeholder="Pas de révision" data={meta.indexes} {...form.getInputProps("index_code")} />
              {form.values.index_code && (
                <div>
                  <Text size="sm" fw={500} mb={4}>Périodicité</Text>
                  <SegmentedControl data={[{ value: "12", label: "Annuelle" }, { value: "36", label: "Triennale" }]}
                    {...form.getInputProps("revision_months")} />
                </div>
              )}
            </SimpleGrid>
            {form.values.index_code && (
              <SimpleGrid cols={{ base: 1, sm: 3 }}>
                <TextInput label="Indice de référence : période" placeholder="2025-Q2" {...form.getInputProps("index_reference_period")} />
                <TextInput label="Valeur" inputMode="decimal" placeholder="135,30" {...form.getInputProps("index_reference_value")} />
                <Checkbox mt="lg" label="Réviser aussi le dépôt de garantie" {...form.getInputProps("revise_deposit", { type: "checkbox" })} />
              </SimpleGrid>
            )}
          </Stack>
        </Paper>
        <TextInput label="Lieu de signature" placeholder="Ville de la structure" w={{ base: "100%", sm: 320 }} {...form.getInputProps("signed_on_place")} />
        <Textarea label="Notes" autosize minRows={2} {...form.getInputProps("notes")} />
        <Group justify="flex-end">
          <Button variant="default" onClick={() => goTo(lease ? `/leases/${lease.id}` : "/leases/")}>Annuler</Button>
          <Button type="submit" loading={save.isPending}>Suivant</Button>
        </Group>
      </Stack>
    </form>
  );
}

// ------------------------------------------------------------------ étape 2 : biens loués

function ItemForm({ lease, item, meta, onDone }: { lease: Lease; item: LeaseItem | null; meta: LeasesMeta; onDone: (r?: ItemResponse) => void }) {
  const [error, setError] = useState<string | null>(null);
  const form = useForm({ initialValues: {
    letter: item?.letter ?? "", label: item?.label ?? "", nature: item?.nature ?? "building",
    area_m2: item ? String(item.area_m2) : "", built_m2: item ? String(item.built_m2) : "",
    cadastral_refs: item?.cadastral_refs.join(", ") ?? "", partial: item?.partial ?? false,
  } });
  const save = useAction(({ letter, ...values }: typeof form.values) => {
    const body = { ...values, ...(letter || item ? { letter } : {}) };
    return item ? api.patch<ItemResponse>(`/api/v1/leases/${lease.id}/items/${item.id}`, body)
      : api.post<ItemResponse>(`/api/v1/leases/${lease.id}/items`, body);
  }, { silent: true });
  return (
    <form onSubmit={form.onSubmit((values) => save.mutate(values, { onSuccess: onDone, onError: (e) => setError(applyApiError(form, e)) }))}>
      <FormBody error={error} submitLabel={item ? "Enregistrer" : "Ajouter"} onCancel={() => onDone()} loading={save.isPending}>
        <SimpleGrid cols={{ base: 1, sm: 4 }}>
          <TextInput label="Lettre" placeholder="Auto" maxLength={3} {...form.getInputProps("letter")} />
          <TextInput label="Désignation" required data-autofocus placeholder="Potager, bureau…" style={{ gridColumn: "span 3" }}
            {...form.getInputProps("label")} />
        </SimpleGrid>
        <SegmentedControl data={meta.natures} {...form.getInputProps("nature")} />
        <SimpleGrid cols={{ base: 1, sm: 2 }}>
          <TextInput label="Surface louée (m²)" inputMode="numeric" disabled={form.values.nature === "flat"} {...form.getInputProps("area_m2")} />
          <TextInput label="Dont surface bâtie (m²)" inputMode="numeric" {...form.getInputProps("built_m2")} />
        </SimpleGrid>
        <TextInput label="Références cadastrales" placeholder="AH 248, AH 250" {...form.getInputProps("cadastral_refs")}
          description="Séparées par des virgules." />
        <Checkbox label="Partie seulement du bâtiment ou de la parcelle" {...form.getInputProps("partial", { type: "checkbox" })} />
      </FormBody>
    </form>
  );
}

function ItemsStep({ lease, meta, onChange, onBack, onNext }: {
  lease: Lease; meta: LeasesMeta; onChange: (lease: Lease) => void; onBack: () => void; onNext: () => void;
}) {
  const [editing, setEditing] = useState<LeaseItem | "new" | null>(null);
  const remove = useAction((itemId: number) => api.delete<{ lease: Lease; notices?: Notice[] }>(`/api/v1/leases/${lease.id}/items/${itemId}`));
  const items = lease.items ?? [];
  const natureLabel = Object.fromEntries(meta.natures.map((n) => [n.value, n.label]));
  return (
    <Stack>
      <Text size="sm" c="dimmed">Une ligne par élément loué (parcelle, bâtiment, zone) : elle porte une lettre, reprise dans le
        tableau du bail et sur les avis d'échéance.</Text>
      {items.length > 0 && (
        <Table>
          <Table.Thead><Table.Tr>
            <Table.Th>Lettre</Table.Th><Table.Th>Désignation</Table.Th><Table.Th>Nature</Table.Th>
            <Table.Th ta="right">Surface</Table.Th><Table.Th ta="right">Dont bâti</Table.Th><Table.Th>Cadastre</Table.Th><Table.Th />
          </Table.Tr></Table.Thead>
          <Table.Tbody>{items.map((i) => (
            <Table.Tr key={i.id}>
              <Table.Td fw={600}>{i.letter}</Table.Td>
              <Table.Td>{i.label}{i.partial && <Text span size="xs" c="dimmed"> (partie)</Text>}</Table.Td>
              <Table.Td>{natureLabel[i.nature]}</Table.Td>
              <Table.Td ta="right" className="lv-num">{i.area_m2 ? `${i.area_m2.toLocaleString("fr-FR")} m²` : "—"}</Table.Td>
              <Table.Td ta="right" className="lv-num">{i.built_m2 ? `${i.built_m2.toLocaleString("fr-FR")} m²` : "—"}</Table.Td>
              <Table.Td>{i.cadastral_refs.join(", ")}</Table.Td>
              <Table.Td><Group gap={4} justify="flex-end" wrap="nowrap">
                <ActionIcon variant="subtle" aria-label={`Modifier ${i.label}`} onClick={() => setEditing(i)}><Pencil size={16} /></ActionIcon>
                <ActionIcon variant="subtle" color="brique" aria-label={`Retirer ${i.label}`}
                  onClick={() => remove.mutate(i.id, { onSuccess: (r) => onChange(r.lease) })}><Trash2 size={16} /></ActionIcon>
              </Group></Table.Td>
            </Table.Tr>))}</Table.Tbody>
        </Table>
      )}
      <Group><Button variant="default" onClick={() => setEditing("new")}>Ajouter un bien</Button></Group>
      <Group justify="flex-end">
        <Button variant="default" onClick={onBack}>Précédent</Button>
        <Button disabled={!items.length} onClick={onNext}>Suivant</Button>
      </Group>
      <FormModal opened={editing !== null} onClose={() => setEditing(null)} title={editing === "new" ? "Ajouter un bien" : "Modifier le bien"} size="lg">
        {editing !== null && <ItemForm lease={lease} meta={meta} item={editing === "new" ? null : editing}
          onDone={(r) => { if (r) onChange(r.lease); setEditing(null); }} />}
      </FormModal>
    </Stack>
  );
}

// ------------------------------------------------------------------ étape 3 : loyer et facturation

function RentStep({ lease, meta, onBack, onDone }: { lease: Lease; meta: LeasesMeta; onBack: () => void; onDone: (lease: Lease) => void }) {
  const items = lease.items ?? [];
  const [prices, setPrices] = useState<Record<number, { unit: string; price: string }>>(() =>
    Object.fromEntries(items.map((i) => [i.id, { unit: i.billing_unit, price: i.unit_price_cents ? euros(i.unit_price_cents) : "" }])));
  const [error, setError] = useState<string | null>(null);
  const form = useForm({ initialValues: {
    frequency: lease.status === "active" ? lease.frequency : "monthly", due_day: String(lease.due_day), in_advance: lease.in_advance,
    vat_rate: lease.vat_rate || "0", charges: lease.charges_cents ? euros(lease.charges_cents) : "",
    rent_account_code: lease.rent_account_code, charges_account_code: lease.charges_account_code, qonto_emit: lease.qonto_emit,
  } });
  const annual = (i: LeaseItem) => annualOf(prices[i.id]?.unit ?? i.billing_unit, i.area_m2, toCents(prices[i.id]?.price ?? ""));
  const total = items.reduce((sum, i) => sum + annual(i), 0);
  const perPeriod = Math.round(total / PER_YEAR[form.values.frequency]);
  const save = useAction(async (values: typeof form.values) => {
    for (const i of items) {
      const p = prices[i.id];
      if (p && (p.unit !== i.billing_unit || toCents(p.price) !== i.unit_price_cents)) {
        await api.patch<ItemResponse>(`/api/v1/leases/${lease.id}/items/${i.id}`, { billing_unit: p.unit, unit_price: p.price || "0" });
      }
    }
    return api.post<LeaseResponse>(`/api/v1/leases/${lease.id}/activate`, values);
  }, { invalidate: [LEASES_KEY, RECURRENCES_KEY, SALES_KEY], silent: true });
  const frequencyLabel = meta.frequencies.find((f) => f.value === form.values.frequency)?.label.toLowerCase() ?? "";
  return (
    <form onSubmit={form.onSubmit((values) => save.mutate(values, { onSuccess: (r) => onDone(r.item), onError: (e) => setError(applyApiError(form, e)) }))}>
      <Stack>
        {error && <Alert color="brique" role="alert">{error}</Alert>}
        <Table>
          <Table.Thead><Table.Tr>
            <Table.Th>Lettre</Table.Th><Table.Th>Désignation</Table.Th><Table.Th ta="right">Quantité</Table.Th>
            <Table.Th>Unité</Table.Th><Table.Th>Prix annuel HT (€)</Table.Th><Table.Th ta="right">Montant annuel</Table.Th>
          </Table.Tr></Table.Thead>
          <Table.Tbody>{items.map((i) => {
            const p = prices[i.id] ?? { unit: i.billing_unit, price: "" };
            return (
              <Table.Tr key={i.id}>
                <Table.Td fw={600}>{i.letter}</Table.Td>
                <Table.Td>{i.label}</Table.Td>
                <Table.Td ta="right" className="lv-num">{quantity(i, p.unit)}</Table.Td>
                <Table.Td><Select aria-label={`Unité ${i.label}`} w={150} data={meta.units} value={p.unit} allowDeselect={false}
                  onChange={(unit) => setPrices({ ...prices, [i.id]: { ...p, unit: unit ?? p.unit } })} /></Table.Td>
                <Table.Td><TextInput aria-label={`Prix ${i.label}`} w={120} inputMode="decimal" value={p.price}
                  onChange={(e) => setPrices({ ...prices, [i.id]: { ...p, price: e.currentTarget.value } })} /></Table.Td>
                <Table.Td ta="right"><MoneyText cents={annual(i)} size="sm" /></Table.Td>
              </Table.Tr>);
          })}</Table.Tbody>
          <Table.Tfoot><Table.Tr>
            <Table.Th colSpan={5}>Loyer annuel HT hors charges</Table.Th>
            <Table.Th ta="right"><MoneyText cents={total} fw={700} /></Table.Th>
          </Table.Tr></Table.Tfoot>
        </Table>
        <Text size="sm">Échéance {frequencyLabel} : <MoneyText cents={perPeriod} fw={600} size="sm" /> hors charges.</Text>
        <SimpleGrid cols={{ base: 2, sm: 4 }}>
          <Select label="Périodicité" data={meta.frequencies} allowDeselect={false} {...form.getInputProps("frequency")} />
          <TextInput label="Jour d'échéance" inputMode="numeric" {...form.getInputProps("due_day")} />
          <TextInput label="Provisions sur charges (€)" inputMode="decimal" {...form.getInputProps("charges")} />
          <TextInput label="TVA (%)" inputMode="decimal" {...form.getInputProps("vat_rate")} />
        </SimpleGrid>
        <SimpleGrid cols={{ base: 1, sm: 2 }}>
          <Select label="Compte des loyers" searchable data={meta.accounts} {...form.getInputProps("rent_account_code")}
            description="Défaut 706 (à valider avec l'expert-comptable)" />
          <Select label="Compte des charges" searchable data={meta.accounts} {...form.getInputProps("charges_account_code")} description="Défaut 708" />
        </SimpleGrid>
        <Group>
          <Checkbox label="Terme à échoir" {...form.getInputProps("in_advance", { type: "checkbox" })} />
          {meta.qonto && <Checkbox label="Émettre avec Qonto" {...form.getInputProps("qonto_emit", { type: "checkbox" })} />}
        </Group>
        <Group justify="flex-end">
          <Button variant="default" onClick={onBack}>Précédent</Button>
          <Button type="submit" loading={save.isPending}>{lease.status === "draft" ? "Valider le bail" : "Enregistrer"}</Button>
        </Group>
      </Stack>
    </form>
  );
}

// ------------------------------------------------------------------ page

export default function LeaseWizardPage() {
  const leaseId = Number(useParams().lease_id) || null;
  const goTo = useGoTo();
  const client = useQueryClient();
  const meta = useList<Lease, LeasesMeta>(LEASES_KEY, "/api/v1/leases").data?.meta;
  const loaded = useQuery({ queryKey: [...LEASES_KEY, leaseId], enabled: leaseId !== null,
    queryFn: () => api.get<{ item: Lease }>(`/api/v1/leases/${leaseId}`) });
  const [lease, setLease] = useState<Lease | null>(null);
  const [params, setParams] = useSearchParams();
  const step = Number(params.get("step") ?? 0) || 0;
  const setStep = (s: number) => setParams({ step: String(s) }, { replace: true });
  const current = lease ?? loaded.data?.item ?? null;
  if (!meta || (leaseId !== null && !current)) return <Center h={300}><Loader /></Center>;
  const update = (item: Lease) => {
    setLease(item);
    client.setQueryData([...LEASES_KEY, item.id], { item });
  };
  return (
    <>
      <PageHeader title={current ? `Bail ${current.unit_label}` : "Nouveau bail"}
        description={current?.status === "active" ? "Bail validé : les modifications s'appliquent aux prochains avis d'échéance."
          : "Brouillon enregistré à chaque étape : il se reprend depuis la liste des baux."}
        actions={<Button variant="default" component={AppLink} href="/leases/">Baux</Button>} />
      <Paper p="md" maw={1000}>
        <Stepper active={step} onStepClick={(s) => current && setStep(s)} allowNextStepsSelect={false}>
          <Stepper.Step label="Bail" description="Parties, dates, révision">
            <TermsStep lease={current} meta={meta} onSaved={(item) => {
              update(item);
              if (leaseId) setStep(1);
              else goTo(`/leases/${item.id}/edit?step=1`, { replace: true });
            }} />
          </Stepper.Step>
          <Stepper.Step label="Biens loués" description="Une ligne par élément">
            {current && <ItemsStep lease={current} meta={meta} onChange={update} onBack={() => setStep(0)} onNext={() => setStep(2)} />}
          </Stepper.Step>
          <Stepper.Step label="Loyer" description="Prix annuels et facturation">
            {current && <RentStep key={current.items?.map((i) => i.id).join("-")} lease={current} meta={meta}
              onBack={() => setStep(1)} onDone={(item) => { update(item); goTo(`/leases/${item.id}`); }} />}
          </Stepper.Step>
        </Stepper>
      </Paper>
    </>
  );
}

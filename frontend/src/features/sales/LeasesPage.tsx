// Ventes › Baux et quittances : baux simples (locataire, lot, loyer, charges, échéance, dépôt de
// garantie) ; chaque bail prépare ses avis d'échéance dans « À émettre ».
import { useState } from "react";
import { Anchor, Button, Checkbox, Group, Select, SimpleGrid, TextInput, Textarea } from "@mantine/core";
import { useForm } from "@mantine/form";
import { api } from "../../api/client";
import { useAction, useList, type Notice } from "../../api/resources";
import { applyApiError, FormBody } from "../../components/ApiForm";
import { Can } from "../../components/Can";
import { DataGrid, type GridColumn } from "../../components/DataGrid";
import { FormModal } from "../../components/FormModal";
import { MoneyText } from "../../components/Money";
import { PageHeader } from "../../components/PageHeader";
import { StatusBadge } from "../../components/StatusBadge";
import { formatDate } from "../../lib/format";
import { AppLink, useGoTo } from "../../app/navigation";
import type { Option } from "../purchases/types";
import { LEASES_KEY, RECURRENCES_KEY, SALES_KEY, type Lease } from "./types";

export interface LeasesMeta { tenants: Option[]; accounts: Option[]; bank_accounts: Option[]; qonto: boolean }
const euros = (cents: number) => (cents / 100).toFixed(2).replace(".", ",");

export function LeaseForm({ lease, meta, onDone }: { lease: Lease | null; meta: LeasesMeta; onDone: (item?: Lease) => void }) {
  const [error, setError] = useState<string | null>(null);
  const form = useForm({ initialValues: {
    entity_id: lease ? String(lease.tenant.id) : "", unit_label: lease?.unit_label ?? "", address_line1: lease?.address_line1 ?? "",
    address_line2: lease?.address_line2 ?? "", postal_code: lease?.postal_code ?? "", city: lease?.city ?? "",
    start_date: lease?.start_date ?? new Date().toISOString().slice(0, 10), end_date: lease?.end_date ?? "",
    rent: lease ? euros(lease.rent_cents) : "", charges: lease ? euros(lease.charges_cents) : "", deposit: lease ? euros(lease.deposit_cents) : "",
    due_day: String(lease?.due_day ?? 1), rent_account_code: lease?.rent_account_code ?? "", charges_account_code: lease?.charges_account_code ?? "",
    in_advance: lease?.in_advance ?? true, qonto_emit: lease?.qonto_emit ?? false, active: lease?.active ?? true, notes: lease?.notes ?? "",
  } });
  const save = useAction((values: typeof form.values) => lease
    ? api.patch<{ item: Lease; notices: Notice[] }>(`/api/v1/leases/${lease.id}`, { ...values, end_date: values.end_date || null })
    : api.post<{ item: Lease; notices: Notice[] }>("/api/v1/leases", { ...values, end_date: values.end_date || null }),
  { invalidate: [LEASES_KEY, RECURRENCES_KEY, SALES_KEY], silent: true });
  return (
    <form onSubmit={form.onSubmit((values) => save.mutate(values, { onSuccess: (r) => onDone(r.item), onError: (e) => setError(applyApiError(form, e)) }))}>
      <FormBody error={error} submitLabel={lease ? "Enregistrer" : "Créer le bail"} onCancel={() => onDone()} loading={save.isPending}>
        <SimpleGrid cols={{ base: 1, sm: 2 }}>
          <Select label="Locataire" required searchable data={meta.tenants} {...form.getInputProps("entity_id")}
            description="Tiers (adresse et email sur sa fiche)." />
          <TextInput label="Lot" required placeholder="Appartement 2B, garage n° 4…" {...form.getInputProps("unit_label")} />
        </SimpleGrid>
        <TextInput label="Adresse du lot" {...form.getInputProps("address_line1")} />
        <SimpleGrid cols={{ base: 1, sm: 3 }}>
          <TextInput label="Complément" {...form.getInputProps("address_line2")} />
          <TextInput label="Code postal" {...form.getInputProps("postal_code")} />
          <TextInput label="Ville" {...form.getInputProps("city")} />
        </SimpleGrid>
        <SimpleGrid cols={{ base: 2, sm: 4 }}>
          <TextInput label="Loyer hors charges (€)" required inputMode="decimal" {...form.getInputProps("rent")} />
          <TextInput label="Provisions sur charges (€)" inputMode="decimal" {...form.getInputProps("charges")} />
          <TextInput label="Dépôt de garantie (€)" inputMode="decimal" {...form.getInputProps("deposit")} />
          <TextInput label="Jour d'échéance" inputMode="numeric" {...form.getInputProps("due_day")} />
        </SimpleGrid>
        <SimpleGrid cols={{ base: 2, sm: 4 }}>
          <TextInput label="Date d'effet" type="date" required {...form.getInputProps("start_date")} />
          <TextInput label="Fin" type="date" {...form.getInputProps("end_date")} />
          <Select label="Compte des loyers" searchable data={meta.accounts} {...form.getInputProps("rent_account_code")}
            description="Défaut 706 (à valider avec l'expert-comptable)" />
          <Select label="Compte des charges" searchable data={meta.accounts} {...form.getInputProps("charges_account_code")} description="Défaut 708" />
        </SimpleGrid>
        <Group>
          <Checkbox label="Terme à échoir" {...form.getInputProps("in_advance", { type: "checkbox" })} />
          {meta.qonto && <Checkbox label="Émettre avec Qonto" {...form.getInputProps("qonto_emit", { type: "checkbox" })} />}
          {lease && <Checkbox label="Bail en cours" {...form.getInputProps("active", { type: "checkbox" })} />}
        </Group>
        <Textarea label="Notes" autosize minRows={2} {...form.getInputProps("notes")} />
      </FormBody>
    </form>
  );
}

export default function LeasesPage() {
  const { data, isFetching } = useList<Lease, LeasesMeta>(LEASES_KEY, "/api/v1/leases");
  const [creating, setCreating] = useState(false);
  const goTo = useGoTo();
  const columns: GridColumn<Lease>[] = [
    { accessor: "unit_label", title: "Lot", hideable: false, render: (l) => <Anchor component={AppLink} href={`/leases/${l.id}`} size="sm">{l.unit_label}</Anchor> },
    { accessor: "tenant", title: "Locataire", render: (l) => l.tenant.name },
    { accessor: "rent_cents", title: "Loyer", textAlign: "right", render: (l) => <MoneyText cents={l.rent_cents} size="sm" /> },
    { accessor: "charges_cents", title: "Charges", textAlign: "right", render: (l) => <MoneyText cents={l.charges_cents} size="sm" /> },
    { accessor: "next_date", title: "Prochaine échéance", render: (l) => <span className="lv-num">{formatDate(l.next_date)}</span> },
    { accessor: "deposit_cents", title: "Dépôt", render: (l) => l.deposit_cents
      ? <StatusBadge tone={l.deposit_entry ? "ok" : "todo"}>{l.deposit_entry ? "encaissé" : "à encaisser"}</StatusBadge> : null },
    { accessor: "active", title: "État", render: (l) => <StatusBadge tone={l.active ? "ok" : "neutral"}>{l.active ? "En cours" : "Terminé"}</StatusBadge> },
  ];
  return (
    <>
      <PageHeader title="Baux et quittances" description="Les avis d'échéance de loyer sont préparés dans « À émettre » ; la quittance est disponible quand le loyer de la période est payé."
        actions={<><Button variant="default" component={AppLink} href="/sales/due">À émettre</Button>
          <Can><Button onClick={() => setCreating(true)}>Nouveau bail</Button></Can></>} />
      <DataGrid id="leases" records={data?.items} columns={columns} fetching={isFetching} emptyText="Aucun bail." />
      <FormModal opened={creating} onClose={() => setCreating(false)} title="Nouveau bail" size="xl">
        {creating && data?.meta && <LeaseForm lease={null} meta={data.meta} onDone={(item) => { setCreating(false); if (item) goTo(`/leases/${item.id}`); }} />}
      </FormModal>
    </>
  );
}

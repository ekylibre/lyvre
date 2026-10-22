// Banque › Contreparties à valider : débits sans tiers regroupés par contrepartie ; créer le
// fournisseur, rattacher à un tiers existant ou ignorer (vaut pour toutes ses transactions).
import { useState } from "react";
import { useParams } from "react-router";
import { Button, Group, Select, Text, TextInput, type ComboboxData } from "@mantine/core";
import { api } from "../../api/client";
import { useAction, useList, type Notice } from "../../api/resources";
import { DataGrid, type GridColumn } from "../../components/DataGrid";
import { MoneyText } from "../../components/Money";
import { PageHeader } from "../../components/PageHeader";
import { formatDate } from "../../lib/format";
import { AppLink } from "../../app/navigation";
import { BANK_ACCOUNTS_KEY, type BankAccount, type Option } from "./types";

interface Proposal { key: string; label: string; count: number; total_cents: number; first_date: string; last_date: string }

/** Créer le fournisseur, rattacher à un tiers existant ou ignorer la contrepartie. */
export function Decide({ p, entities, decide }: { p: Pick<Proposal, "key" | "label">; entities: ComboboxData; decide: (body: Record<string, unknown>) => void }) {
  const [name, setName] = useState(p.label);
  const [entityId, setEntityId] = useState<string | null>(null);
  return (
    <Group gap="xs" wrap="nowrap">
      <TextInput aria-label={`Nom du fournisseur pour ${p.label}`} value={name} onChange={(e) => setName(e.currentTarget.value)} w={200} />
      <Button size="compact-md" onClick={() => decide({ action: "create", key: p.key, label: p.label, name })}>Créer le fournisseur</Button>
      <Select aria-label={`Tiers existant pour ${p.label}`} placeholder="Tiers existant" searchable data={entities} value={entityId} onChange={setEntityId} w={200} />
      <Button size="compact-md" variant="default" disabled={!entityId}
        onClick={() => decide({ action: "link", key: p.key, label: p.label, entity_id: entityId })}>Rattacher</Button>
      <Button size="compact-md" variant="subtle" onClick={() => decide({ action: "ignore", key: p.key, label: p.label })}>Ignorer</Button>
    </Group>
  );
}

export default function CounterpartiesPage() {
  const baId = Number(useParams().ba_id);
  const key = [...BANK_ACCOUNTS_KEY, baId, "counterparties"];
  const { data, isFetching } = useList<Proposal, { bank_account: BankAccount; entities: Option[] }>(key,
    `/api/v1/bank-accounts/${baId}/counterparties`);
  const decide = useAction((body: Record<string, unknown>) => api.post<{ notices: Notice[] }>("/api/v1/counterparties", body),
    { invalidate: [key, [...BANK_ACCOUNTS_KEY, baId]] });
  const columns: GridColumn<Proposal>[] = [
    { accessor: "label", title: "Contrepartie", hideable: false, render: (p) => <Text fw={600} size="sm">{p.label}</Text> },
    { accessor: "count", title: "Transactions", textAlign: "right", sortable: true, render: (p) => <span className="lv-num">{p.count}</span> },
    { accessor: "total_cents", title: "Total", textAlign: "right", sortable: true, render: (p) => <MoneyText cents={p.total_cents} /> },
    { accessor: "first_date", title: "Période", render: (p) => <Text size="sm" className="lv-num">{formatDate(p.first_date)}{p.last_date !== p.first_date && ` → ${formatDate(p.last_date)}`}</Text> },
    { accessor: "actions", title: "Décision", hideable: false,
      render: (p) => <Decide p={p} entities={data?.meta?.entities ?? []} decide={(body) => decide.mutate(body)} /> },
  ];
  return (
    <>
      <PageHeader title="Contreparties à valider"
        description="Débits sans tiers, regroupés par contrepartie. Le choix s'applique à toutes ses transactions sans tiers ; frais bancaires et rémunérations ne sont pas proposés."
        actions={<Button variant="default" component={AppLink} href={`/bank-accounts/${baId}/transactions`}>
          Retour à {data?.meta?.bank_account.label ?? "au compte"}</Button>} />
      <DataGrid id="counterparties" records={data?.items} columns={columns} fetching={isFetching} idAccessor="key"
        emptyText="Aucune contrepartie à valider." />
    </>
  );
}

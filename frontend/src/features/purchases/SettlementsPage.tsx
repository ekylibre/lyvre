// Achats › Règlements à remplacer : paiements de factures comptabilisées déjà rapprochés d'une
// écriture de règle (charge comptée deux fois) → règlement fournisseur à la place.
import { useEffect, useState } from "react";
import { Anchor, Button, Code, Group, Text, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { DataGrid, type GridColumn } from "../../components/DataGrid";
import { MoneyText } from "../../components/Money";
import { PageHeader } from "../../components/PageHeader";
import { formatDate } from "../../lib/format";
import { AppLink } from "../../app/navigation";
import { PURCHASES_KEY } from "./types";

interface Replacement {
  transaction: { id: number; date: string; label: string; amount_cents: number };
  entry: { reference: string; url: string; charge_accounts: string[] };
  purchases: { id: number; label: string; url: string }[];
}

const COLUMNS: GridColumn<Replacement>[] = [
  { accessor: "date", title: "Date", hideable: false, render: (r) => <span className="lv-num">{formatDate(r.transaction.date)}</span> },
  { accessor: "label", title: "Transaction", render: (r) => <Text size="sm">{r.transaction.label}</Text> },
  { accessor: "amount", title: "Montant", textAlign: "right", render: (r) => <MoneyText cents={r.transaction.amount_cents} /> },
  { accessor: "entry", title: "Écriture", render: (r) => (
    <Group gap={6}><Anchor component={AppLink} href={r.entry.url} size="sm">{r.entry.reference}</Anchor>
      {r.entry.charge_accounts.map((c) => <Code key={c}>{c}</Code>)}</Group>
  ) },
  { accessor: "purchases", title: "Facture(s)", render: (r) => (
    <Group gap={6}>{r.purchases.map((p) => <Anchor key={p.id} component={AppLink} href={p.url} size="sm">{p.label}</Anchor>)}</Group>
  ) },
];

const rowId = (r: Replacement) => ({ ...r, id: r.transaction.id });

export default function SettlementsPage() {
  const key = [...PURCHASES_KEY, "settlements"];
  const { data, isFetching } = useQuery({ queryKey: key,
    queryFn: () => api.get<{ replaceable: Replacement[]; manual: Replacement[] }>("/api/v1/purchases/settlements") });
  const replaceable = (data?.replaceable ?? []).map(rowId);
  const [selected, setSelected] = useState<typeof replaceable>([]);
  // Tout est coché par défaut, comme l'ancien écran.
  useEffect(() => setSelected((data?.replaceable ?? []).map(rowId)), [data]);
  const replace = useAction((ids: number[]) => api.post<{ notices: Notice[] }>("/api/v1/purchases/settlements/replace", { transaction_ids: ids }),
    { invalidate: [PURCHASES_KEY] });
  return (
    <>
      <PageHeader title="Règlements à remplacer" description="Paiements de factures d'achat comptabilisées, mais déjà rapprochés d'une autre écriture."
        actions={<Button variant="default" component={AppLink} href="/purchases/">Factures d'achat</Button>} />
      {replaceable.length > 0 && (
        <Text size="sm" mb="sm">Ces transactions ont été passées en charge par une <b>règle de catégorisation</b> avant l'arrivée de leur
          facture : la charge figure donc aussi dans l'écriture d'achat. Le remplacement supprime l'écriture de règle et passe à la
          place un règlement fournisseur (401 / banque), rapproché.</Text>
      )}
      <DataGrid id="purchase-settlements" records={replaceable} columns={COLUMNS} fetching={isFetching}
        selection={{ selected, onChange: setSelected, actions: (rows) => (
          <Button size="compact-md" loading={replace.isPending} disabled={!rows.length}
            onClick={() => replace.mutate(rows.map((r) => r.id))}>Remplacer la sélection ({rows.length})</Button>
        ) }}
        emptyText="Aucune écriture de règle à remplacer." />
      {(data?.manual.length ?? 0) > 0 && (
        <>
          <Title order={3} mt="lg" mb={4}>Rapprochements manuels à vérifier</Title>
          <Text size="sm" c="dimmed" mb="sm">Ces paiements sont rapprochés d'une écriture saisie à la main : elle n'est pas remplacée
            automatiquement. Vérifiez qu'elle ne double pas la charge de la facture.</Text>
          <DataGrid id="purchase-settlements-manual" records={data?.manual.map(rowId)} columns={COLUMNS} />
        </>
      )}
    </>
  );
}

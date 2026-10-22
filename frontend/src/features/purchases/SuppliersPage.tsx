// Achats › Fournisseurs à valider : factures Qonto au fournisseur non reconnu, regroupées par nom ;
// créer le fournisseur, rattacher à un tiers existant ou ignorer (vaut aussi pour ses transactions).
import { Button, Text } from "@mantine/core";
import { api } from "../../api/client";
import { useAction, useList, type Notice } from "../../api/resources";
import { DataGrid, type GridColumn } from "../../components/DataGrid";
import { MoneyText } from "../../components/Money";
import { PageHeader } from "../../components/PageHeader";
import { formatDate } from "../../lib/format";
import { AppLink } from "../../app/navigation";
import { Decide } from "../bank-accounts/CounterpartiesPage";
import { PURCHASES_KEY, type Option } from "./types";

interface Proposal {
  key: string; label: string; count: number; total_cents: number; first_date: string | null; last_date: string | null;
  vat_number: string | null; iban: string | null; suggestions: Option[];
}

export default function SuppliersPage() {
  const key = [...PURCHASES_KEY, "suppliers"];
  const { data, isFetching } = useList<Proposal, { entities: Option[] }>(key, "/api/v1/purchases/suppliers");
  const decide = useAction((body: Record<string, unknown>) => api.post<{ notices: Notice[] }>("/api/v1/purchases/suppliers", body),
    { invalidate: [PURCHASES_KEY] });
  const entities = data?.meta?.entities ?? [];
  const columns: GridColumn<Proposal>[] = [
    { accessor: "label", title: "Contrepartie", hideable: false, render: (p) => (
      <><Text fw={600} size="sm">{p.label}</Text>
        {(p.vat_number || p.iban) && <Text size="xs" c="dimmed" className="lv-num">{[p.vat_number, p.iban].filter(Boolean).join(" ")}</Text>}</>
    ) },
    { accessor: "count", title: "Factures", textAlign: "right", sortable: true, render: (p) => <span className="lv-num">{p.count}</span> },
    { accessor: "total_cents", title: "Total", textAlign: "right", sortable: true, render: (p) => <MoneyText cents={p.total_cents} /> },
    { accessor: "first_date", title: "Période", render: (p) => p.first_date && (
      <Text size="sm" className="lv-num">{formatDate(p.first_date)}{p.last_date !== p.first_date && ` → ${formatDate(p.last_date)}`}</Text>
    ) },
    { accessor: "actions", title: "Décision", hideable: false, render: (p) => (
      <Decide p={p} decide={(body) => decide.mutate(body)}
        entities={p.suggestions.length ? [{ group: "Noms ou IBAN proches", items: p.suggestions }, { group: "Tous les tiers", items: entities }] : entities} />
    ) },
  ];
  return (
    <>
      <PageHeader title="Fournisseurs des factures à valider"
        description="Factures d'achat Qonto dont le fournisseur n'est pas reconnu, regroupées par nom. Le choix s'applique à ses factures et à ses transactions sans tiers de même nom ; les factures devenues complètes sont aussitôt comptabilisées et réglées. Le n° de TVA et l'IBAN de Qonto sont enregistrés sur la fiche."
        actions={<Button variant="default" component={AppLink} href="/purchases/">Factures d'achat</Button>} />
      <DataGrid id="purchase-suppliers" records={data?.items} columns={columns} fetching={isFetching} idAccessor="key"
        emptyText="Aucun fournisseur de facture à valider." />
    </>
  );
}

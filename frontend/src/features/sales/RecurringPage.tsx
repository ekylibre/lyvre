// Ventes › Factures récurrentes : échéanciers (abonnements clients, loyers des baux), prochaine
// échéance, montant ; création, modification, arrêt.
import { Anchor, Badge, Button, Group, Text } from "@mantine/core";
import { useList } from "../../api/resources";
import { Can } from "../../components/Can";
import { DataGrid, type GridColumn } from "../../components/DataGrid";
import { MoneyText } from "../../components/Money";
import { PageHeader } from "../../components/PageHeader";
import { StatusBadge } from "../../components/StatusBadge";
import { formatDate } from "../../lib/format";
import { AppLink } from "../../app/navigation";
import { RECURRENCES_KEY, type Recurrence } from "./types";

export default function RecurringPage() {
  const { data, isFetching } = useList<Recurrence>(RECURRENCES_KEY, "/api/v1/recurrences");
  const columns: GridColumn<Recurrence>[] = [
    { accessor: "label", title: "Libellé", hideable: false, render: (r) => (
      <Group gap={6} wrap="nowrap">
        <Anchor component={AppLink} href={r.lease ? `/leases/${r.lease.id}` : `/sales/recurring/${r.id}`} size="sm">{r.label}</Anchor>
        {r.lease && <Badge size="xs" variant="light">bail</Badge>}
      </Group>
    ) },
    { accessor: "client", title: "Client", render: (r) => r.client.name },
    { accessor: "frequency_label", title: "Périodicité", render: (r) => <Text size="sm">{r.frequency_label}, le {r.due_day}{r.in_advance ? " (à échoir)" : " (échu)"}</Text> },
    { accessor: "total_cents", title: "Montant", textAlign: "right", render: (r) => <MoneyText cents={r.total_cents} size="sm" /> },
    { accessor: "next_date", title: "Prochaine échéance", render: (r) => <span className="lv-num">{formatDate(r.next_date)}</span> },
    { accessor: "end_date", title: "Fin", render: (r) => <span className="lv-num">{formatDate(r.end_date)}</span> },
    { accessor: "active", title: "État", render: (r) => <StatusBadge tone={r.active ? "ok" : "neutral"}>{r.active ? "Active" : "Arrêtée"}</StatusBadge> },
  ];
  return (
    <>
      <PageHeader title="Factures récurrentes"
        description="Chaque échéance arrivée est préparée en brouillon dans « À émettre ». Les loyers se gèrent depuis leur bail."
        actions={<>
          <Button variant="default" component={AppLink} href="/sales/due">À émettre</Button>
          <Can><Button component={AppLink} href="/sales/recurring/new">Nouvelle facture récurrente</Button></Can>
        </>} />
      <DataGrid id="recurrences" records={data?.items} columns={columns} fetching={isFetching} emptyText="Aucune facture récurrente." />
    </>
  );
}

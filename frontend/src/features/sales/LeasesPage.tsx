// Ventes › Baux et quittances : baux (locataire, biens loués, loyer annuel, échéance, dépôt de
// garantie) ; « Nouveau bail » ouvre l'assistant ; un brouillon se reprend depuis la liste. Chaque bail
// validé prépare ses avis d'échéance dans « À émettre ».
import { Anchor, Button } from "@mantine/core";
import { useList } from "../../api/resources";
import { Can } from "../../components/Can";
import { DataGrid, type GridColumn } from "../../components/DataGrid";
import { MoneyText } from "../../components/Money";
import { PageHeader } from "../../components/PageHeader";
import { StatusBadge } from "../../components/StatusBadge";
import { formatDate } from "../../lib/format";
import { AppLink } from "../../app/navigation";
import type { LeasesMeta } from "./LeaseWizardPage";
import { LEASES_KEY, type Lease } from "./types";

export default function LeasesPage() {
  const { data, isFetching } = useList<Lease, LeasesMeta>(LEASES_KEY, "/api/v1/leases");
  const columns: GridColumn<Lease>[] = [
    { accessor: "unit_label", title: "Bail", hideable: false, render: (l) => (
      <Anchor component={AppLink} href={l.status === "draft" ? `/leases/${l.id}/edit` : `/leases/${l.id}`} size="sm">{l.unit_label}</Anchor>) },
    { accessor: "tenant", title: "Locataire", render: (l) => l.tenant.name },
    { accessor: "kind_label", title: "Type", render: (l) => l.kind_label },
    { accessor: "annual_cents", title: "Loyer annuel", textAlign: "right", render: (l) => <MoneyText cents={l.annual_cents} size="sm" /> },
    { accessor: "rent_cents", title: "Échéance", textAlign: "right", render: (l) => <MoneyText cents={l.rent_cents} size="sm" /> },
    { accessor: "charges_cents", title: "Charges", textAlign: "right", render: (l) => <MoneyText cents={l.charges_cents} size="sm" /> },
    { accessor: "next_date", title: "Prochaine échéance", render: (l) => <span className="lv-num">{formatDate(l.next_date)}</span> },
    { accessor: "deposit_cents", title: "Dépôt", render: (l) => l.deposit_cents
      ? <StatusBadge tone={l.deposit_entry ? "ok" : "todo"}>{l.deposit_entry ? "encaissé" : "à encaisser"}</StatusBadge> : null },
    { accessor: "active", title: "État", render: (l) => l.status === "draft" ? <StatusBadge tone="todo">Brouillon</StatusBadge>
      : <StatusBadge tone={l.active ? "ok" : "neutral"}>{l.active ? "En cours" : "Terminé"}</StatusBadge> },
  ];
  return (
    <>
      <PageHeader title="Baux et quittances" description="Les avis d'échéance de loyer sont préparés dans « À émettre » ; la quittance est disponible quand le loyer de la période est payé."
        actions={<><Button variant="default" component={AppLink} href="/sales/due">À émettre</Button>
          <Can><Button component={AppLink} href="/leases/new">Nouveau bail</Button></Can></>} />
      <DataGrid id="leases" records={data?.items} columns={columns} fetching={isFetching} emptyText="Aucun bail." />
    </>
  );
}

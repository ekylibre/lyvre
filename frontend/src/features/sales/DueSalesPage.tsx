// Ventes › À émettre : à l'ouverture, les échéances arrivées des factures récurrentes et des baux
// sont préparées en brouillon (une seule fois par période) ; on les vérifie puis on les émet, avec
// ou sans envoi par email, en lot.
import { useState } from "react";
import { Alert, Anchor, Button, Group, Text } from "@mantine/core";
import { api } from "../../api/client";
import { useAction, useList, type Notice } from "../../api/resources";
import { DataGrid, type GridColumn } from "../../components/DataGrid";
import { MoneyText } from "../../components/Money";
import { PageHeader } from "../../components/PageHeader";
import { formatDate } from "../../lib/format";
import { AppLink } from "../../app/navigation";
import { SALES_KEY, type SaleRow } from "./types";

export default function DueSalesPage() {
  const { data, isFetching } = useList<SaleRow, { prepared: number }>([...SALES_KEY, "due"], "/api/v1/sales/due");
  const [selected, setSelected] = useState<SaleRow[]>([]);
  const issue = useAction((body: { ids: number[]; send: boolean }) => api.post<{ notices: Notice[] }>("/api/v1/sales/issue-batch", body),
    { invalidate: [SALES_KEY] });
  const columns: GridColumn<SaleRow>[] = [
    { accessor: "client", title: "Client", hideable: false, render: (s) => <Anchor component={AppLink} href={`/sales/${s.id}`} size="sm">{s.client.name}</Anchor> },
    { accessor: "issue_date", title: "Date", render: (s) => <span className="lv-num">{formatDate(s.issue_date)}</span> },
    { accessor: "due_date", title: "Échéance", render: (s) => <span className="lv-num">{formatDate(s.due_date)}</span> },
    { accessor: "total_cents", title: "Montant", textAlign: "right", render: (s) => <MoneyText cents={s.total_cents} size="sm" /> },
  ];
  const run = (send: boolean) => issue.mutate({ ids: selected.map((s) => s.id), send }, { onSuccess: () => setSelected([]) });
  return (
    <>
      <PageHeader title="Factures à émettre"
        description="Échéances des factures récurrentes et des loyers, préparées en brouillon : vérifiez-les, puis émettez-les (et envoyez-les)."
        actions={<Button variant="default" component={AppLink} href="/sales/recurring">Factures récurrentes</Button>} />
      {!!data?.meta?.prepared && <Alert color="lichen" mb="sm">{data.meta.prepared} échéance(s) préparée(s) à l'instant.</Alert>}
      <DataGrid id="sales-due" records={data?.items} columns={columns} fetching={isFetching}
        emptyText="Aucune échéance à émettre."
        selection={{
          selected, onChange: setSelected,
          actions: () => <Group gap="xs">
            <Button size="compact-sm" loading={issue.isPending} onClick={() => run(false)}>Émettre ({selected.length})</Button>
            <Button size="compact-sm" variant="default" loading={issue.isPending} onClick={() => run(true)}>Émettre et envoyer</Button>
          </Group>,
        }} />
      <Text size="xs" c="dimmed" mt="xs">Un brouillon se modifie depuis sa fiche avant l'émission ; une échéance n'est jamais préparée deux fois.</Text>
    </>
  );
}

// Adhérents › Relance des adhésions échues (email), avec choix des destinataires.
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router";
import { Alert, Anchor, Button, Text } from "@mantine/core";
import { api } from "../../api/client";
import { useAction, useList, type Notice } from "../../api/resources";
import { useIntegration } from "../../api/session";
import { confirmAction } from "../../components/ConfirmButton";
import { DataGrid, type GridColumn } from "../../components/DataGrid";
import { IntegrationNotice } from "../../components/IntegrationNotice";
import { PageHeader } from "../../components/PageHeader";
import { Can } from "../../components/Can";
import { useIntegrationGuard } from "../../components/IntegrationRequired";
import { formatDate } from "../../lib/format";
import { AppLink } from "../../app/navigation";
import { filterQuery, MEMBERS_KEY, type Integrations, type Member } from "./types";

type Meta = Integrations & { helloasso_url: string };

const COLUMNS: GridColumn<Member>[] = [
  { accessor: "name", title: "Nom", hideable: false },
  { accessor: "email", title: "Email" },
  { accessor: "birthday", title: "Échéance", render: (m) => <span className="lv-num">{formatDate(m.birthday)}</span> },
];

export default function RemindersPage() {
  const [search] = useSearchParams();
  const filters = { q: search.get("q") ?? "", date_from: search.get("date_from") ?? "", date_to: search.get("date_to") ?? "" };
  const { data, isFetching } = useList<Member, Meta>([...MEMBERS_KEY, "reminders"],
    `/api/v1/members/reminders${filterQuery(filters)}`);
  const [selected, setSelected] = useState<Member[]>([]);
  // Tous cochés au départ, comme l'ancien écran.
  useEffect(() => { if (data) setSelected(data.items); }, [data]);
  const send = useAction(() => api.post<{ notices: Notice[] }>("/api/v1/members/reminders",
    { ...filters, ids: selected.map((m) => m.id) }), { invalidate: [MEMBERS_KEY] });
  const smtp = data?.meta?.integrations.smtp;
  const helloasso = useIntegration("helloasso");
  const smtpGuard = useIntegrationGuard("smtp", "L'envoi des relances par email");

  return (
    <>
      <PageHeader title="Relancer les adhésions échues"
        description="Adhérents dont l'adhésion est échue et dont l'email est connu."
        actions={<>
          <Can><Button variant="default" component={AppLink} href="/entities/members/reminder-template">Modifier le message</Button></Can>
          <Can><Button disabled={!selected.length || (smtpGuard.enabled && !smtp?.available)} loading={send.isPending}
            onClick={smtpGuard.guard(() => confirmAction({
              title: `Envoyer ${selected.length} email(s) de relance ?`, danger: false, confirmLabel: "Envoyer",
              message: "Chaque adhérent coché reçoit le message de relance.", onConfirm: () => send.mutate(undefined),
            }))}>Envoyer la relance</Button></Can>
        </>} />
      <IntegrationNotice name="smtp" state={smtp} consequence="envoi des relances impossible" />
      {data?.meta?.helloasso_url ? (
        <Text size="sm" c="dimmed" mb="sm">Lien de renouvellement : <Anchor href={data.meta.helloasso_url} target="_blank" rel="noreferrer">{data.meta.helloasso_url}</Anchor></Text>
      ) : helloasso && <Alert color="paille" variant="light" mb="sm">Aucun lien HelloAsso : renseignez l'organisation dans l'intégration HelloAsso.</Alert>}
      <DataGrid id="reminders" records={data?.items} columns={COLUMNS} fetching={isFetching}
        selection={{ selected, onChange: setSelected }} emptyText="Aucun adhérent à relancer." />
    </>
  );
}

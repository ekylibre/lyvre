// Tiers › Adhérents : statut d'adhésion, filtres, actions groupées, exports, relances.
import { useState } from "react";
import { Anchor, Button, Group, Menu, Text } from "@mantine/core";
import { DateInput } from "@mantine/dates";
import { ChevronDown } from "lucide-react";
import { api } from "../../api/client";
import { useAction, useList, type Notice } from "../../api/resources";
import { useIntegration } from "../../api/session";
import { DataGrid, type GridColumn, type SortState } from "../../components/DataGrid";
import { FilterBar, SearchInput, useUrlParams } from "../../components/FilterBar";
import { IntegrationNotice } from "../../components/IntegrationNotice";
import { PageHeader } from "../../components/PageHeader";
import { Can } from "../../components/Can";
import { StatusBadge } from "../../components/StatusBadge";
import { formatDate } from "../../lib/format";
import { AppLink } from "../../app/navigation";
import { useHelloAssoSync } from "../entities/EntitiesPage";
import {
  EXPIRY, filterQuery, MEMBER_FILTERS, MEMBERS_KEY, type Integrations, type Member,
} from "./types";

type Meta = Integrations & { export_urls: { csv: string; xlsx: string } };

// Tri serveur (nom, échéance, statut), comme l'export.
const SORTABLE: Record<string, string> = { name: "name", birthday: "birthday", color: "status" };

export default function MembersPage() {
  const [params, setParams] = useUrlParams(MEMBER_FILTERS);
  const [selected, setSelected] = useState<Member[]>([]);
  const { data, isFetching } = useList<Member, Meta>(MEMBERS_KEY, `/api/v1/members${filterQuery(params)}`);
  const meta = data?.meta;
  const sync = useHelloAssoSync();
  const helloasso = useIntegration("helloasso");
  const odoo = useIntegration("odoo");
  const benevole = useAction((value: boolean) => api.post<{ notices: Notice[] }>("/api/v1/members/benevole",
    { ids: selected.map((m) => m.id), value }), { invalidate: [MEMBERS_KEY] });
  const odooNotes = useAction(() => api.post<{ notices: Notice[] }>("/api/v1/members/odoo-notes",
    { ...params, ids: selected.map((m) => m.id) }));
  const sortColumn = Object.entries(SORTABLE).find(([, v]) => v === params.sort_by)?.[0] ?? "name";
  const sort: SortState = { column: sortColumn, direction: params.sort === "desc" ? "desc" : "asc" };

  const columns: GridColumn<Member>[] = [
    { accessor: "name", title: "Nom", sortable: true, hideable: false,
      render: (m) => <Anchor component={AppLink} href={`/entities/${m.id}`} fw={600}>{m.name}</Anchor> },
    { accessor: "email", title: "Email", render: (m) => <Text size="sm" c="dimmed">{m.email ?? ""}</Text> },
    { accessor: "is_member", title: "Adhérent",
      render: (m) => m.is_member ? <StatusBadge tone="ok">Adhérent</StatusBadge> : <Text c="dimmed">—</Text> },
    { accessor: "is_benevole", title: "Bénévole",
      render: (m) => m.is_benevole ? <StatusBadge tone="info">Bénévole</StatusBadge> : <Text c="dimmed">—</Text> },
    { accessor: "last_helloasso_membership", title: "Adhésion HelloAsso",
      render: (m) => <span className="lv-num">{formatDate(m.last_helloasso_membership)}</span> },
    { accessor: "last_pos_membership", title: "Adhésion caisse",
      render: (m) => <span className="lv-num">{formatDate(m.last_pos_membership)}</span> },
    { accessor: "birthday", title: "Échéance", sortable: true, render: (m) => <span className="lv-num">{formatDate(m.birthday)}</span> },
    { accessor: "color", title: "Statut", sortable: true,
      render: (m) => <Group gap={6} wrap="nowrap"><StatusBadge tone={EXPIRY[m.color].tone}>{EXPIRY[m.color].label}</StatusBadge>
        <Text size="xs" c="dimmed">{m.status_label}</Text></Group> },
    { accessor: "notes", title: "Notes", render: (m) => <Text size="sm" c="dimmed" lineClamp={1}>{m.notes ?? ""}</Text> },
  ];

  const filtered = params.q || params.date_from || params.date_to;
  return (
    <>
      <PageHeader title="Adhérents" description="Tiers de type adhérent, avec l'échéance de leur dernière adhésion (HelloAsso ou caisse)."
        actions={<>
          <Menu position="bottom-end">
            <Menu.Target><Button variant="default" rightSection={<ChevronDown size={16} />}>Exporter</Button></Menu.Target>
            <Menu.Dropdown>
              <Menu.Item component="a" href={meta?.export_urls.csv}>CSV</Menu.Item>
              <Menu.Item component="a" href={meta?.export_urls.xlsx}>Excel (XLSX)</Menu.Item>
            </Menu.Dropdown>
          </Menu>
          <Can><Button variant="default" component={AppLink}
            href={`/entities/members/reminders${filterQuery({ q: params.q, date_from: params.date_from, date_to: params.date_to })}`}
            disabled={!meta?.integrations.smtp.available}>Relancer les échus</Button></Can>
          {helloasso && <Can><Button loading={sync.isPending} disabled={!meta?.integrations.helloasso.available}
            onClick={() => sync.mutate(undefined)}>Synchroniser HelloAsso</Button></Can>}
        </>} />
      <IntegrationNotice name="helloasso" state={meta?.integrations.helloasso} consequence="synchronisation des adhérents impossible" />
      <IntegrationNotice name="smtp" state={meta?.integrations.smtp} consequence="relance par email impossible" />
      <FilterBar>
        <SearchInput value={params.q} onChange={(q) => setParams({ q })} placeholder="Nom, prénom ou email…" />
        <DateInput label="Adhésion du" clearable valueFormat="DD/MM/YYYY" w={160} value={params.date_from || null}
          onChange={(v) => setParams({ date_from: v ?? "" })} />
        <DateInput label="au" clearable valueFormat="DD/MM/YYYY" w={160} value={params.date_to || null}
          onChange={(v) => setParams({ date_to: v ?? "" })} />
      </FilterBar>
      <DataGrid id="members" records={data?.items} columns={columns} fetching={isFetching} perPage={100}
        sort={sort} onSortChange={(s) => setParams({ sort_by: SORTABLE[s.column] ?? "name", sort: s.direction })}
        selection={{
          selected, onChange: setSelected,
          actions: () => <>
            <Button size="compact-sm" loading={benevole.isPending && benevole.variables}
              onClick={() => benevole.mutate(true, { onSuccess: () => setSelected([]) })}>Marquer bénévole</Button>
            <Button size="compact-sm" variant="default" loading={benevole.isPending && !benevole.variables}
              onClick={() => benevole.mutate(false, { onSuccess: () => setSelected([]) })}>Retirer bénévole</Button>
            {odoo && <Button size="compact-sm" variant="default" loading={odooNotes.isPending}
              disabled={!meta?.integrations.odoo.available}
              title="Écrire la date anniversaire et le statut d'adhésion dans « Notes interne » d'Odoo"
              onClick={() => odooNotes.mutate(undefined)}>Mettre à jour les fiches Odoo</Button>}
          </>,
        }}
        emptyText={filtered ? "Aucun adhérent ne correspond aux critères."
          : "Aucun adhérent. La synchronisation HelloAsso en crée un pour chaque adhésion."} />
    </>
  );
}

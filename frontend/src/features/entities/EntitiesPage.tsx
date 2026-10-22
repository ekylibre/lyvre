// Tiers › Entités : liste (hors adhérents), recherche, création, modification, suppression.
import { Anchor, Button, Group, Text } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useAction, useList, type Notice } from "../../api/resources";
import { confirmAction } from "../../components/ConfirmButton";
import { DataGrid, type GridColumn } from "../../components/DataGrid";
import { FilterBar, SearchInput, useUrlParams } from "../../components/FilterBar";
import { FormDrawer } from "../../components/FormModal";
import { IntegrationNotice } from "../../components/IntegrationNotice";
import { PageHeader } from "../../components/PageHeader";
import { Can } from "../../components/Can";
import { StatusBadge } from "../../components/StatusBadge";
import { formatDate } from "../../lib/format";
import { AppLink } from "../../app/navigation";
import { useRouteModal } from "../../app/useRouteModal";
import { EntityForm } from "./EntityForm";
import { TIERS_KEY, type EntitiesMeta, type Entity } from "./types";

export function useHelloAssoSync() {
  return useAction(() => api.post<{ notices: Notice[] }>("/api/v1/helloasso/sync"),
    { invalidate: [TIERS_KEY, ["members"]] });
}

export default function EntitiesPage() {
  const modal = useRouteModal("/entities/", "entity_id");
  const [params, setParams] = useUrlParams({ q: "" });
  const { data, isFetching } = useList<Entity, EntitiesMeta>(TIERS_KEY,
    `/api/v1/tiers${params.q ? `?q=${encodeURIComponent(params.q)}` : ""}`);
  const meta = data?.meta;
  const types = Object.fromEntries((meta?.types ?? []).map((t) => [t.value, t.label]));
  const listed = modal.mode === "edit" ? data?.items.find((e) => e.id === modal.id) : undefined;
  // Tiers hors de la liste affichée (adhérent, filtre) : lu sur sa fiche.
  const { data: detail } = useQuery({
    queryKey: [...TIERS_KEY, modal.id], enabled: modal.mode === "edit" && !!data && !listed,
    queryFn: () => api.get<{ item: Entity }>(`/api/v1/tiers/${modal.id}`),
  });
  const editing = modal.mode === "edit" ? listed ?? detail?.item ?? null : null;
  const sync = useHelloAssoSync();
  const remove = useAction((e: Entity) => api.delete<{ notices: Notice[] }>(`/api/v1/tiers/${e.id}`),
    { invalidate: [TIERS_KEY] });

  const columns: GridColumn<Entity>[] = [
    { accessor: "name", title: "Nom", sortable: true, hideable: false,
      render: (e) => <Anchor component={AppLink} href={`/entities/${e.id}`} fw={600}>{e.name}</Anchor> },
    { accessor: "entity_type", title: "Type", sortable: true, render: (e) => types[e.entity_type] ?? e.entity_type },
    { accessor: "email", title: "Email", render: (e) => <Text size="sm" c="dimmed">{e.email ?? ""}</Text> },
    { accessor: "is_member", title: "Adhérent",
      render: (e) => e.is_member ? <StatusBadge tone="ok">Adhérent</StatusBadge> : <Text c="dimmed">—</Text> },
    { accessor: "last_helloasso_membership", title: "Adhésion HelloAsso", sortable: true,
      render: (e) => <span className="lv-num">{formatDate(e.last_helloasso_membership)}</span> },
    { accessor: "last_pos_membership", title: "Adhésion caisse", sortable: true,
      render: (e) => <span className="lv-num">{formatDate(e.last_pos_membership)}</span> },
    { accessor: "account_code", title: "Compte", render: (e) => <span className="lv-num">{e.account_code ?? "—"}</span> },
    { accessor: "transactions", title: "Transactions", sortable: true, textAlign: "right",
      render: (e) => <span className="lv-num">{e.transactions}</span> },
    { accessor: "notes", title: "Notes", render: (e) => <Text size="sm" c="dimmed" lineClamp={1}>{e.notes ?? ""}</Text> },
    { accessor: "actions", title: "", hideable: false, textAlign: "right",
      render: (e) => (
        <Group gap={4} justify="flex-end" wrap="nowrap">
          <Button variant="subtle" size="compact-sm" onClick={() => modal.openEdit(e.id)}>Modifier</Button>
          <Button variant="subtle" size="compact-sm" color="brique"
            onClick={() => confirmAction({ title: `Supprimer ${e.name} ?`, confirmLabel: "Supprimer",
              message: e.transactions ? `${e.transactions} transaction(s) y sont liées : la suppression sera refusée.` : undefined,
              onConfirm: () => remove.mutate(e) })}>Supprimer</Button>
        </Group>
      ) },
  ];

  return (
    <>
      <PageHeader title="Entités" description="Fournisseurs, clients, organismes et autres tiers. Les adhérents ont leur propre écran."
        actions={<>
          <Button variant="default" component={AppLink} href="/entities/members">Voir les adhérents</Button>
          <Can><Button variant="default" loading={sync.isPending} disabled={!meta?.integrations.helloasso.available}
            onClick={() => sync.mutate(undefined)}>Synchroniser HelloAsso</Button></Can>
          <Can><Button onClick={modal.openNew}>Créer un tiers</Button></Can>
        </>} />
      <IntegrationNotice name="helloasso" state={meta?.integrations.helloasso}
        consequence="synchronisation des adhérents impossible" />
      <FilterBar>
        <SearchInput value={params.q} onChange={(q) => setParams({ q })} placeholder="Nom ou email…" />
      </FilterBar>
      <DataGrid id="entities" records={data?.items} columns={columns} fetching={isFetching} perPage={100}
        defaultSort={{ column: "name", direction: "asc" }}
        emptyText={params.q ? `Aucun tiers ne correspond à « ${params.q} ».` : "Aucun tiers : créez le premier."} />
      <FormDrawer opened={modal.mode === "new" || (modal.mode === "edit" && !!editing)} onClose={modal.close}
        title={editing ? `Modifier ${editing.name}` : "Créer un tiers"}>
        <EntityForm key={editing?.id ?? "new"} entity={editing} meta={meta} onDone={modal.close} />
      </FormDrawer>
    </>
  );
}

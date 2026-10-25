// Tiers › Entités : liste (hors adhérents), recherche, création, modification, suppression ; mise à jour
// groupée depuis Sirene (lot G5 : comparaison en arrière-plan, puis revue).
import { useState } from "react";
import { Anchor, Button, Group, Text } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useAction, useList, type Notice } from "../../api/resources";
import { useIntegration, useIsAssociation } from "../../api/session";
import { confirmAction } from "../../components/ConfirmButton";
import { DataGrid, type GridColumn } from "../../components/DataGrid";
import { FilterBar, SearchInput, useUrlParams } from "../../components/FilterBar";
import { FormDrawer } from "../../components/FormModal";
import { IntegrationNotice } from "../../components/IntegrationNotice";
import { PageHeader } from "../../components/PageHeader";
import { Can } from "../../components/Can";
import { StatusBadge } from "../../components/StatusBadge";
import { formatDate } from "../../lib/format";
import { AppLink, useGoTo } from "../../app/navigation";
import { useSireneAvailable } from "../../components/sirene/useSirene";
import { useRouteModal } from "../../app/useRouteModal";
import { EntityForm } from "./EntityForm";
import { TIERS_KEY, type EntitiesMeta, type Entity } from "./types";

export function useHelloAssoSync() {
  return useAction(() => api.post<{ notices: Notice[] }>("/api/v1/helloasso/sync"),
    { invalidate: [TIERS_KEY, ["members"], ["brevo"]] });  // passage Brevo enchaîné (lot B3)
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
  const association = useIsAssociation();
  const helloasso = useIntegration("helloasso") && association;
  const sireneAvailable = useSireneAvailable();
  const goTo = useGoTo();
  const [selected, setSelected] = useState<Entity[]>([]);
  const withNumber = (data?.items ?? []).filter((e) => e.siren || e.siret);
  const refresh = useAction((ids: number[] | null) =>
    api.post<{ job: { id: number }; count: number; notices?: Notice[] }>("/api/v1/entities/sirene-refresh", ids ? { entity_ids: ids } : {}));
  const startRefresh = (ids: number[] | null) =>
    refresh.mutate(ids, { onSuccess: (r) => { setSelected([]); goTo(`/entities/sirene-review/${r.job.id}`); } });
  const remove = useAction((e: Entity) => api.delete<{ notices: Notice[] }>(`/api/v1/tiers/${e.id}`),
    { invalidate: [TIERS_KEY] });

  const columns: GridColumn<Entity>[] = [
    { accessor: "name", title: "Nom", sortable: true, hideable: false,
      render: (e) => <Anchor component={AppLink} href={`/entities/${e.id}`} fw={600}>{e.name}</Anchor> },
    { accessor: "entity_type", title: "Type", sortable: true, render: (e) => types[e.entity_type] ?? e.entity_type },
    { accessor: "email", title: "Email", render: (e) => <Text size="sm" c="dimmed">{e.email ?? ""}</Text> },
    ...(association ? [
      { accessor: "is_member", title: "Adhérent",
        render: (e) => e.is_member ? <StatusBadge tone="ok">Adhérent</StatusBadge> : <Text c="dimmed">—</Text> },
      { accessor: "last_helloasso_membership", title: "Adhésion HelloAsso", sortable: true,
        render: (e) => <span className="lv-num">{formatDate(e.last_helloasso_membership)}</span> },
      { accessor: "last_pos_membership", title: "Adhésion caisse", sortable: true,
        render: (e) => <span className="lv-num">{formatDate(e.last_pos_membership)}</span> },
    ] satisfies GridColumn<Entity>[] : []),
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
      <PageHeader title="Entités" description={association
        ? "Fournisseurs, clients, organismes et autres tiers. Les adhérents ont leur propre écran."
        : "Fournisseurs, clients, locataires, organismes et autres tiers."}
        actions={<>
          {association && <Button variant="default" component={AppLink} href="/entities/members">Voir les adhérents</Button>}
          {helloasso && <Can><Button variant="default" loading={sync.isPending} disabled={!meta?.integrations.helloasso.available}
            onClick={() => sync.mutate(undefined)}>Synchroniser HelloAsso</Button></Can>}
          <Can><Button onClick={modal.openNew}>Créer un tiers</Button></Can>
        </>} />
      {association && <IntegrationNotice name="helloasso" state={meta?.integrations.helloasso}
        consequence="synchronisation des adhérents impossible" />}
      <FilterBar>
        <SearchInput value={params.q} onChange={(q) => setParams({ q })} placeholder="Nom ou email…" />
      </FilterBar>
      <DataGrid id="entities" records={data?.items} columns={columns} fetching={isFetching} perPage={100}
        defaultSort={{ column: "name", direction: "asc" }}
        selection={sireneAvailable ? {
          selected, onChange: setSelected,
          actions: (rows) => {
            const ids = rows.filter((e) => e.siren || e.siret).map((e) => e.id);
            return <Button size="compact-sm" variant="light" loading={refresh.isPending} disabled={!ids.length}
              onClick={() => startRefresh(ids)}>Mettre à jour depuis Sirene ({ids.length})</Button>;
          },
        } : undefined}
        toolbar={sireneAvailable && withNumber.length > 0 ? (
          <Group gap="xs">
            <Text size="sm" c="dimmed">{data?.items.length ?? 0} élément(s)</Text>
            <Can><Button size="compact-sm" variant="light" loading={refresh.isPending} onClick={() => startRefresh(null)}>
              Mettre à jour depuis Sirene ({withNumber.length} avec un SIREN)</Button></Can>
          </Group>
        ) : undefined}
        emptyText={params.q ? `Aucun tiers ne correspond à « ${params.q} ».` : "Aucun tiers : créez le premier."} />
      <FormDrawer opened={modal.mode === "new" || (modal.mode === "edit" && !!editing)} onClose={modal.close}
        title={editing ? `Modifier ${editing.name}` : "Créer un tiers"}>
        <EntityForm key={editing?.id ?? "new"} entity={editing} meta={meta} onDone={modal.close} />
      </FormDrawer>
    </>
  );
}

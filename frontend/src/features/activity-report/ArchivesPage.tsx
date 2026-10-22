// Rapport d'activité › Versions archivées : PDF figés et consultables ; archivage et suppression (admin).
import { useState } from "react";
import { Alert, Anchor, Button, Group, Paper, Text, TextInput } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { useCurrentSession } from "../../api/session";
import { confirmAction } from "../../components/ConfirmButton";
import { DataGrid, type GridColumn } from "../../components/DataGrid";
import { FilterBar, useUrlParams } from "../../components/FilterBar";
import { PageHeader } from "../../components/PageHeader";
import { StatusBadge } from "../../components/StatusBadge";
import { formatDateTime } from "../../lib/format";
import { AppLink } from "../../app/navigation";
import { FiscalYearSelect, REPORT_KEY, useReportContext, withFy } from "./shared";

interface Archive { id: number; version: number; label: string | null; prorata: boolean; created_at: string | null; url: string }

export default function ArchivesPage() {
  const session = useCurrentSession();
  const admin = session.user?.is_admin;
  const { setParams, context } = useReportContext();
  const [params] = useUrlParams({ fy_id: "" });
  const key = [...REPORT_KEY, "archives", params.fy_id];
  const { data, isFetching } = useQuery({ queryKey: key, enabled: !context.error,
    queryFn: () => api.get<{ fiscal_year: { id: number; label: string }; items: Archive[] }>(
      `/api/v1/activity-report/archives${params.fy_id ? `?fy_id=${params.fy_id}` : ""}`) });
  const [label, setLabel] = useState("");
  const create = useAction(() => api.post<{ notices: Notice[] }>("/api/v1/activity-report/archives",
    { fy_id: data?.fiscal_year.id, label, prorata: context.data?.prorata ?? false }), { invalidate: [key] });
  const remove = useAction((id: number) => api.delete<{ notices: Notice[] }>(`/api/v1/activity-report/archives/${id}`), { invalidate: [key] });
  const columns: GridColumn<Archive>[] = [
    { accessor: "version", title: "Version", hideable: false, render: (a) => <Text fw={700} size="sm">v{a.version}</Text> },
    { accessor: "label", title: "Libellé", render: (a) => a.label ?? "—" },
    { accessor: "prorata", title: "Éco", render: (a) => <StatusBadge tone="neutral">{a.prorata ? "pro-rata" : "indivisible"}</StatusBadge> },
    { accessor: "created_at", title: "Créée le", render: (a) => <span className="lv-num">{formatDateTime(a.created_at)}</span> },
    { accessor: "actions", title: "", hideable: false, textAlign: "right", render: (a) => (
      <Group gap="xs" justify="flex-end" wrap="nowrap">
        <Anchor href={a.url} target="_blank" rel="noopener" size="sm">Consulter</Anchor>
        {admin && <Button size="compact-sm" variant="subtle" color="red" onClick={() => confirmAction({
          title: `Supprimer la version v${a.version} ?`, confirmLabel: "Supprimer", onConfirm: () => remove.mutate(a.id) })}>Supprimer</Button>}
      </Group>
    ) },
  ];
  if (context.error) return <Alert color="ardoise" mt="md">{(context.error as Error).message}</Alert>;
  return (
    <>
      <PageHeader title="Versions archivées"
        description={data ? `Exercice ${data.fiscal_year.label} — PDF figés, consultables.` : undefined}
        actions={<Button variant="default" component={AppLink} href={withFy("/rapport-activite/", data?.fiscal_year.id)}>Aperçu</Button>} />
      <FilterBar><FiscalYearSelect context={context.data} onChange={(fy_id) => setParams({ fy_id })} /></FilterBar>
      {admin && (
        <Paper p="md" mb="md" maw={720}>
          <form onSubmit={(e) => { e.preventDefault(); create.mutate(undefined, { onSuccess: () => setLabel("") }); }}>
            <Group align="flex-end">
              <TextInput label="Archiver l'état actuel du rapport (PDF figé)" placeholder="Libellé (ex. « Validé en AG du 12/06 »)"
                value={label} maxLength={200} onChange={(e) => setLabel(e.currentTarget.value)} style={{ flex: 1 }} />
              <Button type="submit" loading={create.isPending}>Archiver maintenant</Button>
            </Group>
            <Text size="xs" c="dimmed" mt={4}>Mode éco de la version : {context.data?.prorata ? "pro-rata" : "indivisible"} (réglé sur l'aperçu).</Text>
          </form>
        </Paper>
      )}
      <DataGrid id="report-archives" records={data?.items} columns={columns} fetching={isFetching}
        emptyText="Aucune version archivée pour cet exercice." />
    </>
  );
}

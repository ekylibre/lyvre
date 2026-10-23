// Administration › Instance : informations, sauvegardes .zip (création, téléchargement,
// suppression) et restauration depuis un fichier (/instances/<id>/restore ouvre la fenêtre).
import { useLocation, useNavigate, useParams } from "react-router";
import { Alert, Anchor, Badge, Button, Center, Code, Group, Loader, Paper, SimpleGrid, Text, Title } from "@mantine/core";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { confirmAction } from "../../components/ConfirmButton";
import { DataGrid, type GridColumn } from "../../components/DataGrid";
import { FormModal } from "../../components/FormModal";
import { PageHeader } from "../../components/PageHeader";
import { StatusBadge } from "../../components/StatusBadge";
import { formatDateTime } from "../../lib/format";
import { AppLink } from "../../app/navigation";
import { RestoreForm } from "./RestoreForm";
import { INSTANCES_KEY, megabytes, type Backup, type Instance } from "./types";

type Detail = { item: Instance; backups: Backup[] };

function Info({ label, children }: { label: string; children: React.ReactNode }) {
  return <Paper p="md"><Text size="sm" c="dimmed">{label}</Text><Text component="div">{children}</Text></Paper>;
}

export default function InstanceDetailPage() {
  const id = Number(useParams().instance_id);
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const client = useQueryClient();
  const key = [...INSTANCES_KEY, id];
  const { data, error, isFetching } = useQuery({ queryKey: key, retry: false, queryFn: () => api.get<Detail>(`/api/v1/instances/${id}`) });
  const refresh = (body: Detail) => client.setQueryData(key, body);
  const create = useAction(() => api.post<Detail & { notices: Notice[] }>(`/api/v1/instances/${id}/backups`));
  const remove = useAction((filename: string) => api.delete<Detail & { notices: Notice[] }>(
    `/api/v1/instances/${id}/backups/${encodeURIComponent(filename)}`));
  const restoring = pathname.replace(/\/$/, "").endsWith("/restore");
  const switchMode = useAction((bookkeeping: "double" | "simple") =>
    api.patch<{ item: Instance; notices: Notice[] }>(`/api/v1/instances/${id}`, { label: data?.item.label, bookkeeping }),
    { invalidate: [key, ["session"]] });

  if (error) return <Alert color="brique" mt="md">{(error as Error).message}</Alert>;
  if (!data) return <Center h={300}><Loader /></Center>;
  const inst = data.item;
  const columns: GridColumn<Backup>[] = [
    { accessor: "filename", title: "Fichier", hideable: false, render: (b) => (
      <Group gap={6} wrap="nowrap"><Text size="sm" className="lv-num">{b.filename}</Text>
        {b.database_only && <Badge size="xs" variant="outline" color="gray" title="Ancienne sauvegarde : base seule, sans les pièces jointes">base seule</Badge>}</Group>
    ) },
    { accessor: "is_pre_restore", title: "Type", render: (b) => <StatusBadge tone={b.is_pre_restore ? "todo" : "neutral"}>{b.is_pre_restore ? "Pré-restauration" : "Manuelle"}</StatusBadge> },
    { accessor: "created_at", title: "Date", render: (b) => <span className="lv-num">{formatDateTime(b.created_at)}</span> },
    { accessor: "size_bytes", title: "Taille", textAlign: "right", render: (b) => <span className="lv-num">{megabytes(b.size_bytes)}</span> },
    { accessor: "actions", title: "", hideable: false, textAlign: "right", render: (b) => (
      <Group gap={6} justify="flex-end" wrap="nowrap">
        <Anchor href={b.download_url} size="sm">Télécharger</Anchor>
        <Button size="compact-sm" variant="subtle" color="red" onClick={() => confirmAction({
          title: `Supprimer définitivement ${b.filename} ?`, confirmLabel: "Supprimer",
          onConfirm: () => remove.mutate(b.filename, { onSuccess: refresh }) })}>Supprimer</Button>
      </Group>
    ) },
  ];
  return (
    <>
      <PageHeader title={inst.label} description={<>slug <Code>{inst.slug}</Code></>}
        actions={<>
          <Button variant="default" component={AppLink} href={`/instances/${inst.id}/edit`}>Modifier</Button>
          <Button variant="default" component={AppLink} href="/instances/">Instances</Button>
        </>} />
      <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }} mb="lg">
        <Info label="Base de données"><Text size="sm" className="lv-num" style={{ wordBreak: "break-all" }}>{inst.database}</Text></Info>
        <Info label="Plan comptable">{inst.chart_label}</Info>
        {inst.chart === "asso" && (
          <Info label="Tenue de la comptabilité">
            <Group gap="xs" justify="space-between">
              <Text>{inst.bookkeeping === "simple" ? "Simplifiée (recettes et dépenses)" : "Partie double"}</Text>
              <Button size="compact-sm" variant="default" loading={switchMode.isPending} onClick={() => confirmAction(
                inst.bookkeeping === "simple" ? {
                  title: "Passer en partie double ?", confirmLabel: "Passer en partie double", danger: false,
                  message: "Les opérations déjà saisies sont des écritures en partie double : rien n'est ressaisi. Écritures, "
                    + "plan comptable, états complets, assistant de clôture et FEC deviennent disponibles ; la première clôture "
                    + "reprend les soldes cumulés et les résultats antérieurs en report à nouveau.",
                  onConfirm: () => switchMode.mutate("double"),
                } : {
                  title: "Revenir en comptabilité simplifiée ?", confirmLabel: "Revenir au simple",
                  message: "Refusé si des écritures ne se lisent pas en recettes et dépenses (tiers, immobilisations, capitaux…).",
                  onConfirm: () => switchMode.mutate("simple"),
                })}>{inst.bookkeeping === "simple" ? "Passer en partie double" : "Revenir au simple"}</Button>
            </Group>
          </Info>
        )}
        <Info label="Statut"><StatusBadge tone={inst.is_active ? "ok" : "neutral"}>{inst.is_active ? "Active" : "Désactivée"}</StatusBadge></Info>
        <Info label="Créée le"><span className="lv-num">{formatDateTime(inst.created_at)}</span></Info>
      </SimpleGrid>
      <Group justify="space-between" mb="xs">
        <Title order={3}>Sauvegardes</Title>
        {inst.sqlite && <Group gap="xs">
          <Button loading={create.isPending} onClick={() => create.mutate(undefined, { onSuccess: refresh })}>Créer une sauvegarde</Button>
          <Button variant="default" color="brique" component={AppLink} href={`/instances/${inst.id}/restore`}>Restaurer un fichier…</Button>
        </Group>}
      </Group>
      {inst.sqlite ? (
        <DataGrid id="instance-backups" records={data.backups} columns={columns} fetching={isFetching} idAccessor="filename"
          emptyText="Aucune sauvegarde." />
      ) : (
        <Alert color="ardoise" variant="light">Les sauvegardes ne sont disponibles que pour les instances SQLite. Pour cette instance,
          utilisez les outils de la base (pg_dump / pg_restore) côté serveur.</Alert>
      )}
      <FormModal opened={restoring && inst.sqlite} onClose={() => navigate(`/instances/${inst.id}`)} title={`Restaurer ${inst.label}`} size="lg">
        <RestoreForm instance={inst} onCancel={() => navigate(`/instances/${inst.id}`)}
          onDone={() => { void client.invalidateQueries({ queryKey: INSTANCES_KEY }); navigate(`/instances/${inst.id}`); }} />
      </FormModal>
    </>
  );
}

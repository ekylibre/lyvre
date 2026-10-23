// Associés › Registre des parts : capital à une date (parts, valeur nominale, capital, contrôle
// avec le compte 101), situation par associé et nature, mouvements datés. Saisie par
// l'administrateur de l'instance ; lecture pour tous.
import { Alert, Button, Center, Group, Loader, Paper, SimpleGrid, Stack, Text, TextInput } from "@mantine/core";
import { api } from "../../api/client";
import { useAction, useList, type Notice } from "../../api/resources";
import { useCan } from "../../api/session";
import { AppLink } from "../../app/navigation";
import { useRouteModal } from "../../app/useRouteModal";
import { confirmAction } from "../../components/ConfirmButton";
import { DataGrid, type GridColumn } from "../../components/DataGrid";
import { FilterBar, useUrlParams } from "../../components/FilterBar";
import { FormModal } from "../../components/FormModal";
import { MoneyText } from "../../components/Money";
import { PageHeader } from "../../components/PageHeader";
import { formatDate } from "../../lib/format";
import { MovementForm } from "./MovementForm";
import { ASSOCIATES_KEY, NATURES, REGISTER_KEY, type Associate, type Movement, type RegisterMeta } from "./types";

const fr = (n: number) => n.toLocaleString("fr-FR");
const percent = (n: number) => `${n.toLocaleString("fr-FR", { maximumFractionDigits: 2 })} %`;

export function MovementLines({ movement }: { movement: Movement }) {
  return (
    <Stack gap={0}>
      {movement.lines.map((l, i) => (
        <Text key={i} size="sm">
          <AppLink href={`/associates/${l.associate_id}`}>{l.associate}</AppLink>{" "}
          {l.parts > 0 ? "reçoit" : "cède"} <span className="lv-num">{fr(Math.abs(l.parts))}</span> part(s) en {l.nature_label.toLowerCase()}
        </Text>
      ))}
    </Stack>
  );
}

function Figure({ label, children }: { label: string; children: React.ReactNode }) {
  return <div><Text size="xs" c="dimmed">{label}</Text><Text fw={600} className="lv-num">{children}</Text></div>;
}

export default function RegisterPage() {
  const can = useCan();
  const modal = useRouteModal("/share-movements/", "movement_id");
  const [params, setParams] = useUrlParams({ at: "" });
  const url = `/api/v1/share-movements${params.at ? `?at=${params.at}` : ""}`;
  const { data, isFetching } = useList<Movement, RegisterMeta>(REGISTER_KEY, url);
  const meta = data?.meta;
  const capital = meta?.capital;
  const editing = modal.mode === "edit" ? data?.items.find((m) => m.id === modal.id) ?? null : null;
  const remove = useAction((m: Movement) => api.delete<{ notices: Notice[] }>(`/api/v1/share-movements/${m.id}`),
    { invalidate: [ASSOCIATES_KEY] });

  const situation: GridColumn<Associate>[] = [
    { accessor: "name", title: "Associé", hideable: false, render: (a) => <AppLink href={`/associates/${a.id}`}>{a.name}</AppLink> },
    ...NATURES.map((n): GridColumn<Associate> => ({ accessor: n.value, title: n.label, textAlign: "right",
      render: (a) => a.parts[n.value] ? <span className="lv-num">{fr(a.parts[n.value])} · {percent(a.percent[n.value])}</span> : "—" })),
  ];
  const columns: GridColumn<Movement>[] = [
    { accessor: "movement_date", title: "Date", sortable: true, render: (m) => formatDate(m.movement_date) },
    { accessor: "kind_label", title: "Mouvement" },
    { accessor: "lines", title: "Détail", render: (m) => <MovementLines movement={m} /> },
    { accessor: "nominal_cents", title: "Nominal", textAlign: "right",
      render: (m) => m.nominal_cents !== null ? <MoneyText cents={m.nominal_cents} size="sm" /> : "" },
    { accessor: "attachment", title: "Pièce", render: (m) => m.attachment
      ? <a href={m.attachment.url} target="_blank" rel="noreferrer">{m.attachment.name}</a> : "" },
    { accessor: "actions", title: "", hideable: false, textAlign: "right", render: (m) => can.instanceAdmin && (
      <Group gap={4} justify="flex-end" wrap="nowrap">
        <Button variant="subtle" size="compact-sm" onClick={() => modal.openEdit(m.id)}>Modifier</Button>
        <Button variant="subtle" size="compact-sm" color="brique" onClick={() => confirmAction({
          title: `Supprimer ce mouvement du ${formatDate(m.movement_date)} ?`, confirmLabel: "Supprimer",
          message: "Refusé si un mouvement postérieur s'appuie dessus.", onConfirm: () => remove.mutate(m) })}>Supprimer</Button>
      </Group>
    ) },
  ];

  return (
    <>
      <PageHeader title="Registre des parts" description="Mouvements de parts datés ; la situation du capital se recalcule à toute date."
        actions={can.instanceAdmin && <Button onClick={modal.openNew}>Nouveau mouvement</Button>} />
      <FilterBar>
        <TextInput type="date" label="Situation au" value={params.at} onChange={(e) => setParams({ at: e.currentTarget.value })} />
      </FilterBar>
      {capital && meta && (
        <Paper p="md" withBorder mb="md">
          <SimpleGrid cols={{ base: 2, sm: 4 }}>
            <Figure label={`Parts au ${formatDate(meta.at)}`}>{fr(capital.parts)}</Figure>
            <Figure label="Valeur nominale">{capital.nominal_cents !== null ? <MoneyText cents={capital.nominal_cents} /> : "—"}</Figure>
            <Figure label="Capital du registre">{capital.capital_cents !== null ? <MoneyText cents={capital.capital_cents} /> : "—"}</Figure>
            <Figure label="Comptes 101 (capital)"><MoneyText cents={capital.ledger_cents} /></Figure>
          </SimpleGrid>
          {capital.warnings.map((w) => <Alert key={w} color="paille" mt="sm">{w}</Alert>)}
        </Paper>
      )}
      <Text fw={600} mb="xs">Situation par associé</Text>
      <DataGrid id="register-situation" records={meta?.situation.filter((a) => !a.is_out)} columns={situation}
        fetching={isFetching} emptyText="Aucune part à cette date." />
      <Text fw={600} mt="lg" mb="xs">Mouvements</Text>
      <DataGrid id="register-movements" records={data?.items} columns={columns} fetching={isFetching}
        defaultSort={{ column: "movement_date", direction: "desc" }}
        emptyText="Aucun mouvement. Commencez par la reprise de la situation ou la souscription du capital." />
      <FormModal opened={can.instanceAdmin && (modal.mode === "new" || (modal.mode === "edit" && !!editing))}
        onClose={modal.close} title={editing ? "Modifier le mouvement" : "Nouveau mouvement"} size="xl">
        {meta ? <MovementForm key={editing?.id ?? "new"} movement={editing} meta={meta} onDone={modal.close} />
          : <Center h={120}><Loader /></Center>}
      </FormModal>
    </>
  );
}

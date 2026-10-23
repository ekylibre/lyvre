// Fiche d'un associé : tiers, compte courant et son solde, taux d'intérêt, parts détenues par
// nature. Modification et suppression par l'administrateur (suppression refusée dès qu'il a un
// historique : registre, écritures, règlements).
import { useState } from "react";
import { useParams } from "react-router";
import { Button, Center, Group, Loader, Paper, SimpleGrid, Stack, Table, Text } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { useCan } from "../../api/session";
import { AppLink, useGoTo } from "../../app/navigation";
import { confirmAction } from "../../components/ConfirmButton";
import { FormModal } from "../../components/FormModal";
import { PageHeader } from "../../components/PageHeader";
import { AssociateForm } from "./AssociateForm";
import { BalanceCell } from "./AssociatesPage";
import { MovementLines } from "./RegisterPage";
import { ASSOCIATES_KEY, NATURES, REGISTER_KEY, type Associate, type AssociatesMeta, type Movement } from "./types";
import { formatDate } from "../../lib/format";

interface Detail { item: Associate; meta: { can_delete: boolean; account_locked: boolean } }

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <div><Text size="xs" c="dimmed">{label}</Text><div>{children}</div></div>;
}

export default function AssociateDetailPage() {
  const id = Number(useParams().associate_id);
  const can = useCan();
  const goTo = useGoTo();
  const [editing, setEditing] = useState(false);
  const { data } = useQuery({ queryKey: [...ASSOCIATES_KEY, "detail", id],
    queryFn: () => api.get<Detail>(`/api/v1/associates/${id}`) });
  const list = useQuery({ queryKey: [...ASSOCIATES_KEY, "/api/v1/associates"], enabled: editing,
    queryFn: () => api.get<{ meta: AssociatesMeta }>("/api/v1/associates") });
  const movements = useQuery({ queryKey: [...REGISTER_KEY, "associate", id],
    queryFn: () => api.get<{ items: Movement[] }>(`/api/v1/share-movements?associate_id=${id}`) });
  const remove = useAction(() => api.delete<{ notices: Notice[] }>(`/api/v1/associates/${id}`),
    { invalidate: [ASSOCIATES_KEY] });
  if (!data) return <Center h={300}><Loader /></Center>;
  const a = data.item;
  const total = NATURES.reduce((sum, n) => sum + a.parts[n.value], 0);
  return (
    <>
      <PageHeader title={a.name} description={`Associé — compte courant ${a.account_code}`}
        actions={can.instanceAdmin && (
          <Group gap="xs">
            <Button variant="default" onClick={() => setEditing(true)}>Modifier</Button>
            {data.meta.can_delete && (
              <Button variant="subtle" color="brique" onClick={() => confirmAction({
                title: `Retirer ${a.name} des associés ?`, confirmLabel: "Retirer",
                message: "Le tiers et son compte 455 sont conservés.",
                onConfirm: () => remove.mutate(undefined, { onSuccess: () => goTo("/associates/") }) })}>
                Retirer
              </Button>
            )}
          </Group>
        )} />
      <Stack maw={900}>
        <Paper p="md" withBorder>
          <SimpleGrid cols={{ base: 1, sm: 4 }}>
            <Field label="Tiers"><AppLink href={`/entities/${a.entity_id}`}>{a.name}</AppLink></Field>
            <Field label="Compte courant"><span className="lv-num">{a.account_code}</span>
              <Text size="xs" c="dimmed">{a.account_label}</Text></Field>
            <Field label="Solde"><div style={{ display: "inline-block" }}><BalanceCell cents={a.balance_cents} /></div></Field>
            <Field label="Taux d'intérêt">{a.interest_rate ? `${a.interest_rate} %` : "Taux de la structure"}</Field>
          </SimpleGrid>
          {a.notes && <Text size="sm" mt="sm" style={{ whiteSpace: "pre-wrap" }}>{a.notes}</Text>}
        </Paper>
        <Paper p="md" withBorder>
          <Text fw={600} mb="xs">Parts détenues</Text>
          {total === 0 ? <Text size="sm" c="dimmed">Aucune part à ce jour.</Text> : (
            <Table>
              <Table.Thead><Table.Tr><Table.Th>Nature</Table.Th><Table.Th ta="right">Parts</Table.Th>
                <Table.Th ta="right">% du capital</Table.Th></Table.Tr></Table.Thead>
              <Table.Tbody>
                {NATURES.filter((n) => a.parts[n.value]).map((n) => (
                  <Table.Tr key={n.value}><Table.Td>{n.label}</Table.Td>
                    <Table.Td ta="right" className="lv-num">{a.parts[n.value].toLocaleString("fr-FR")}</Table.Td>
                    <Table.Td ta="right" className="lv-num">
                      {a.percent[n.value].toLocaleString("fr-FR", { maximumFractionDigits: 2 })} %</Table.Td></Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          )}
        </Paper>
        <Paper p="md" withBorder>
          <Text fw={600} mb="xs">Mouvements de parts</Text>
          {!movements.data?.items.length ? <Text size="sm" c="dimmed">Aucun mouvement au registre.</Text> : (
            <Table>
              <Table.Tbody>
                {movements.data.items.map((m) => (
                  <Table.Tr key={m.id}>
                    <Table.Td w={110}>{formatDate(m.movement_date)}</Table.Td>
                    <Table.Td w={170}>{m.kind_label}</Table.Td>
                    <Table.Td><MovementLines movement={m} /></Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          )}
        </Paper>
      </Stack>
      <FormModal opened={editing} onClose={() => setEditing(false)} title={`Modifier ${a.name}`}>
        {editing && <AssociateForm associate={a} meta={list.data?.meta} accountLocked={data.meta.account_locked}
          onDone={() => setEditing(false)} />}
      </FormModal>
    </>
  );
}

// Fiche d'une écriture : lignes, totaux, origine ; modification et suppression ; projet des
// lignes (affectation, ventilation), y compris sur une écriture rapprochée.
import { useState } from "react";
import { useParams } from "react-router";
import { Alert, Button, Center, Group, Loader, Paper, Table, Text } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { useCan } from "../../api/session";
import { api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { confirmAction } from "../../components/ConfirmButton";
import { MoneyText } from "../../components/Money";
import { PageHeader } from "../../components/PageHeader";
import { Can } from "../../components/Can";
import { StatusBadge } from "../../components/StatusBadge";
import { formatDate } from "../../lib/format";
import { AppLink, useGoTo } from "../../app/navigation";
import { LineProjectModal, type ProjectLine } from "../projects/LineProjectModal";
import { ENTRIES_KEY } from "./EntriesPage";

interface EntryDetail {
  id: number; reference: string | null; fiscal_year: string; journal: string; entry_date: string;
  description: string; source: string; source_ref: string | null; is_balanced: boolean;
  total_debit_cents: number; total_credit_cents: number; reconciled: boolean; editable: boolean; managed?: boolean;
  lines: (ProjectLine & { account_label: string; project: string | null })[];
}

export default function EntryDetailPage() {
  const id = Number(useParams().entry_id);
  const goTo = useGoTo();
  const can = useCan();
  const [projectLine, setProjectLine] = useState<ProjectLine | null>(null);
  const { data, isPending } = useQuery({ queryKey: [...ENTRIES_KEY, id], queryFn: () => api.get<EntryDetail>(`/api/v1/entries/${id}`) });
  // Seule la liste est rechargée : la fiche supprimée n'existe plus (pas de 404 affiché).
  const remove = useAction(() => api.delete<{ notices: Notice[] }>(`/api/v1/entries/${id}`),
    { invalidate: [[...ENTRIES_KEY, "list"], ["dashboard"]] });
  if (isPending || !data) return <Center h={300}><Loader /></Center>;
  const projectsEditable = can.write && data.editable;
  const withProjects = projectsEditable || data.lines.some((l) => l.project);
  return (
    <>
      <PageHeader title={<Group gap="sm">{data.reference ?? `Écriture #${data.id}`}
        {data.reconciled && <StatusBadge tone="ok">Rapprochée</StatusBadge>}</Group>}
        description={`${data.journal} · ${formatDate(data.entry_date)} · exercice ${data.fiscal_year}`}
        actions={<>
          <Button variant="default" component={AppLink} href="/entries/">Retour à la liste</Button>
          <Can>{data.editable && <>
            <Button variant="default" color="brique"
              onClick={() => confirmAction({ title: `Supprimer l'écriture ${data.reference ?? ""} ?`, confirmLabel: "Supprimer",
                message: data.reconciled ? "Le rapprochement bancaire sera défait." : undefined,
                onConfirm: () => remove.mutate(undefined, { onSuccess: () => goTo("/entries/") }) })}>Supprimer</Button>
            <Button component={AppLink} href={`/entries/${data.id}/edit`} disabled={data.reconciled}
              title={data.reconciled ? "Annulez le rapprochement avant de modifier l'écriture." : undefined}>Modifier</Button>
          </>}</Can>
        </>} />
      {data.description && <Text mb="sm">{data.description}</Text>}
      {data.source !== "MANUAL" && data.source_ref && <Text size="sm" c="dimmed" mb="sm">Origine : {data.source} · {data.source_ref}</Text>}
      {!data.editable && <Alert color="ardoise" variant="light" mb="sm">{data.managed
        ? "Écriture gérée par l'assistant de clôture : elle se modifie depuis l'assistant de l'exercice."
        : "Exercice clôturé : l'écriture ne peut plus être modifiée."}</Alert>}
      {!data.is_balanced && <Alert color="brique" role="alert" mb="sm">Cette écriture n'est pas équilibrée.</Alert>}
      <Paper p={0} style={{ overflowX: "auto" }}>
        <Table verticalSpacing="xs">
          <Table.Thead bg="var(--lv-sauge)"><Table.Tr><Table.Th>Compte</Table.Th><Table.Th>Libellé</Table.Th>
            {withProjects && <Table.Th>Projet</Table.Th>}
            <Table.Th ta="right">Débit</Table.Th><Table.Th ta="right">Crédit</Table.Th></Table.Tr></Table.Thead>
          <Table.Tbody>
            {data.lines.map((l) => (
              <Table.Tr key={l.id}>
                <Table.Td><span className="lv-num">{l.account_code}</span> <Text span size="sm" c="dimmed">{l.account_label}</Text></Table.Td>
                <Table.Td>{l.label}</Table.Td>
                {withProjects && <Table.Td>
                  {projectsEditable
                    ? <Button variant="subtle" size="compact-sm" onClick={() => setProjectLine(l)}>{l.project ?? "Affecter…"}</Button>
                    : l.project ?? <Text span c="dimmed">—</Text>}
                </Table.Td>}
                <Table.Td ta="right">{l.debit_cents ? <MoneyText cents={l.debit_cents} /> : null}</Table.Td>
                <Table.Td ta="right">{l.credit_cents ? <MoneyText cents={l.credit_cents} /> : null}</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
          <Table.Tfoot><Table.Tr><Table.Th colSpan={withProjects ? 3 : 2}>Total</Table.Th>
            <Table.Th ta="right"><MoneyText cents={data.total_debit_cents} /></Table.Th>
            <Table.Th ta="right"><MoneyText cents={data.total_credit_cents} /></Table.Th></Table.Tr></Table.Tfoot>
        </Table>
      </Paper>
      <LineProjectModal entryId={data.id} line={projectLine} invalidate={[[...ENTRIES_KEY, id]]} onClose={() => setProjectLine(null)} />
    </>
  );
}

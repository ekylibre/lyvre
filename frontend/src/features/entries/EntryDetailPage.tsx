// Fiche d'une écriture : lignes, totaux, origine ; modification et suppression (brouillard) ;
// validation, contrepassation et historique (lot F1) ; projet des lignes (affectation, ventilation
// avant validation), y compris sur une écriture rapprochée.
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
import { FormModal } from "../../components/FormModal";
import { LineProjectModal, type ProjectLine } from "../projects/LineProjectModal";
import { ENTRIES_KEY } from "./EntriesPage";
import { EntryHistory, ReverseForm, VALIDATION_KEY } from "./validation";

interface EntryLink { id: number; reference: string | null }

interface EntryDetail {
  id: number; reference: string | null; fiscal_year: string; journal: string; entry_date: string;
  description: string; source: string; source_ref: string | null; is_balanced: boolean;
  total_debit_cents: number; total_credit_cents: number; reconciled: boolean; editable: boolean; managed?: boolean;
  validated: boolean; validation_number: number | null; validated_at: string | null; fiscal_year_id: number;
  fiscal_year_closed: boolean; locked_until: string | null; reversal: EntryLink | null; reverses: EntryLink | null; reversible: boolean;
  lines: (ProjectLine & { account_label: string; project: string | null })[];
}

export default function EntryDetailPage() {
  const id = Number(useParams().entry_id);
  const goTo = useGoTo();
  const can = useCan();
  const [projectLine, setProjectLine] = useState<ProjectLine | null>(null);
  const [reversing, setReversing] = useState(false);
  const validate = useAction(() => api.post<{ notices: Notice[] }>("/api/v1/entries/validation", { ids: [id] }),
    { invalidate: [ENTRIES_KEY, VALIDATION_KEY] });
  const { data, isPending } = useQuery({ queryKey: [...ENTRIES_KEY, id], queryFn: () => api.get<EntryDetail>(`/api/v1/entries/${id}`) });
  // Seule la liste est rechargée : la fiche supprimée n'existe plus (pas de 404 affiché).
  const remove = useAction(() => api.delete<{ notices: Notice[] }>(`/api/v1/entries/${id}`),
    { invalidate: [[...ENTRIES_KEY, "list"], ["dashboard"]] });
  if (isPending || !data) return <Center h={300}><Loader /></Center>;
  // Projet : aussi sur une écriture validée (colonne libre), sans ventilation.
  const projectsEditable = can.write && !data.fiscal_year_closed && !data.managed && (data.editable || data.validated);
  const reference = data.reference ?? `#${data.id}`;
  const withProjects = projectsEditable || data.lines.some((l) => l.project);
  return (
    <>
      <PageHeader title={<Group gap="sm">{data.reference ?? `Écriture #${data.id}`}
        {data.validated ? <StatusBadge tone="ok">{`Validée n° ${data.validation_number}`}</StatusBadge>
          : <StatusBadge tone="todo">Brouillard</StatusBadge>}
        {data.reconciled && <StatusBadge tone="ok">Rapprochée</StatusBadge>}
        {data.reversal && <StatusBadge tone="neutral">Contrepassée</StatusBadge>}</Group>}
        description={`${data.journal} · ${formatDate(data.entry_date)} · exercice ${data.fiscal_year}`}
        actions={<>
          <Button variant="default" component={AppLink} href="/entries/">Retour à la liste</Button>
          <Can>
            {data.validated && data.reversible && <Button variant="default" onClick={() => setReversing(true)}>Contrepasser</Button>}
            {!data.validated && !data.fiscal_year_closed && data.is_balanced &&
              <Button variant="default" loading={validate.isPending} onClick={() => validate.mutate(undefined)}>Valider</Button>}
          </Can>
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
      {data.reverses && <Alert color="ardoise" variant="light" mb="sm">Contrepassation de l'écriture{" "}
        <AppLink href={`/entries/${data.reverses.id}`}>{data.reverses.reference ?? `#${data.reverses.id}`}</AppLink>.</Alert>}
      {data.reversal && <Alert color="ardoise" variant="light" mb="sm">Écriture contrepassée par{" "}
        <AppLink href={`/entries/${data.reversal.id}`}>{data.reversal.reference ?? `#${data.reversal.id}`}</AppLink> : elle ne compte plus.</Alert>}
      {!data.editable && !data.reversal && <Alert color="ardoise" variant="light" mb="sm">{data.managed
        ? "Écriture gérée par l'assistant de clôture : elle se modifie depuis l'assistant de l'exercice."
        : data.fiscal_year_closed ? "Exercice clôturé : l'écriture ne peut plus être modifiée."
          : data.locked_until && !data.validated ? `Période verrouillée jusqu'au ${formatDate(data.locked_until)} : l'écriture ne peut plus être modifiée.`
          : data.validated ? `Écriture validée${data.validated_at ? ` le ${formatDate(data.validated_at.slice(0, 10))}` : ""} : elle ne se modifie plus ; contrepassez-la pour la corriger.`
            : "Écriture d'une pièce émise : elle se corrige depuis la pièce."}</Alert>}
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
      <LineProjectModal entryId={data.id} line={projectLine} invalidate={[[...ENTRIES_KEY, id]]} onClose={() => setProjectLine(null)}
        splittable={!data.validated} />
      <EntryHistory entryId={data.id} />
      <FormModal opened={reversing} onClose={() => setReversing(false)} title={`Contrepasser l'écriture ${reference}`}>
        {reversing && <ReverseForm entryId={data.id} reference={reference} invalidate={[ENTRIES_KEY, VALIDATION_KEY, ["dashboard"]]}
          onDone={(reversalId) => { setReversing(false); if (reversalId) goTo(`/entries/${reversalId}`); }} />}
      </FormModal>
    </>
  );
}

// Lot AG2.c : acomptes de TVA du régime simplifié agricole (3525 bis) d'une période annuelle : référence (CA12A
// précédente ou saisie), dispense, montant proposé (1/5), enregistrement avec modulation motivée, paiement.
import { useState } from "react";
import { Alert, Button, Group, Paper, Stack, Table, Text, TextInput, Title } from "@mantine/core";
import { DateInput } from "@mantine/dates";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { useCan } from "../../api/session";
import { ConfirmButton } from "../../components/ConfirmButton";
import { FormModal } from "../../components/FormModal";
import { MoneyInput, MoneyText } from "../../components/Money";
import { StatusBadge } from "../../components/StatusBadge";
import { formatDate } from "../../lib/format";
import { INSTALLMENT_TONES, VAT_RETURNS_KEY, type InstallmentRow, type InstallmentSchedule } from "./types";

const opts = { invalidate: [VAT_RETURNS_KEY] };

function RecordForm({ schedule, row, onDone }: { schedule: InstallmentSchedule; row: InstallmentRow; onDone: () => void }) {
  const [amount, setAmount] = useState<number | null>(schedule.proposed_cents);
  const [motive, setMotive] = useState("");
  const record = useAction(() => api.post<{ notices: Notice[] }>("/api/v1/vat-returns/installments",
    { period: schedule.period, number: row.number, amount_cents: amount === null ? null : Math.round(amount / 100) * 100,
      motive }), opts);
  const modulated = schedule.proposed_cents !== null && amount !== schedule.proposed_cents;
  return (
    <form onSubmit={(e) => { e.preventDefault(); record.mutate(undefined, { onSuccess: onDone }); }}>
      <Stack>
        <Text size="sm">{schedule.proposed_cents !== null
          ? <>Acompte calculé : <MoneyText cents={schedule.proposed_cents} /> (1/5 de la TVA due l'année précédente,
            arrondi à l'euro supérieur).</>
          : "Pas de référence : fixez l'acompte à au moins 70 % de la TVA réelle du trimestre (CGI art. 1693 bis II)."}</Text>
        <MoneyInput label="Montant de l'acompte" required value={amount} onChange={setAmount}
          description="En euros entiers ; 0 pour un bulletin de suspension." />
        <TextInput label="Motif de la modulation" required={modulated} disabled={!modulated && schedule.proposed_cents !== null}
          description="Réduction ou suspension : si la TVA de l'année dépasse les acomptes de plus de 30 %, intérêt de retard et majoration."
          value={motive} onChange={(e) => setMotive(e.currentTarget.value)} />
        <Text size="xs" c="dimmed">Écriture en brouillard : débit 44581 « acomptes », crédit 44551 « TVA à décaisser ».</Text>
        <Group><Button type="submit" loading={record.isPending}>Enregistrer l'acompte</Button></Group>
      </Stack>
    </form>
  );
}

function PayForm({ id, onDone }: { id: number; onDone: () => void }) {
  const [paidOn, setPaidOn] = useState<string | null>(new Date().toISOString().slice(0, 10));
  const pay = useAction(() => api.post<{ notices: Notice[] }>(`/api/v1/vat-returns/${id}/declare`,
    { declared_on: paidOn }), opts);
  return (
    <form onSubmit={(e) => { e.preventDefault(); pay.mutate(undefined, { onSuccess: onDone }); }}>
      <Stack>
        <Text size="sm">Bulletin 3525 bis déposé et acompte payé sur l'espace professionnel : l'écriture est validée,
          la période reste ouverte.</Text>
        <DateInput label="Payé le" required valueFormat="DD/MM/YYYY" value={paidOn} onChange={setPaidOn} />
        <Group><Button type="submit" loading={pay.isPending}>Marquer payé</Button></Group>
      </Stack>
    </form>
  );
}

function ReferenceForm({ schedule, onDone }: { schedule: InstallmentSchedule; onDone: () => void }) {
  const [due, setDue] = useState<number | null>(schedule.reference.source === "entered" ? schedule.reference.due_cents : null);
  const [assets, setAssets] = useState<number | null>(schedule.reference.source === "entered" ? schedule.reference.assets_cents : null);
  const save = useAction(() => api.put<{ notices: Notice[] }>("/api/v1/vat-returns/installments/reference",
    { period: schedule.period, reference_cents: due, assets_cents: assets }), opts);
  return (
    <form onSubmit={(e) => { e.preventDefault(); save.mutate(undefined, { onSuccess: onDone }); }}>
      <Stack>
        <MoneyInput label="TVA due l'année précédente" description="Ligne 23 de la dernière CA12A. Vide : nouvel assujetti."
          value={due} onChange={setDue} />
        <MoneyInput label="Dont TVA sur immobilisations déduite" description="Ligne 17 : sert à la dispense (moins de 1 000 € avant immobilisations)."
          value={assets} onChange={setAssets} />
        <Group><Button type="submit" loading={save.isPending}>Enregistrer</Button></Group>
      </Stack>
    </form>
  );
}

export function InstallmentsPanel({ period }: { period: string }) {
  const can = useCan();
  const [recording, setRecording] = useState<InstallmentRow | null>(null);
  const [paying, setPaying] = useState<number | null>(null);
  const [editing, setEditing] = useState(false);
  const { data } = useQuery({ queryKey: [...VAT_RETURNS_KEY, "installments", period],
    queryFn: () => api.get<InstallmentSchedule>(`/api/v1/vat-returns/installments?period=${period}`) });
  const unvalidate = useAction((id: number) => api.post<{ notices: Notice[] }>(`/api/v1/vat-returns/${id}/unvalidate`), opts);
  if (!data) return null;
  const ref = data.reference;
  const lastRecorded = data.items.filter((r) => r.return).at(-1);  // seule la dernière déclaration s'annule
  return (
    <Paper withBorder p="md" mt="lg">
      <Group justify="space-between" mb="xs">
        <Title order={4}>Acomptes {data.label} (3525 bis)</Title>
        {can.write && ref.source !== "ca12a" && !data.annual_return && (
          <Button size="xs" variant="light" onClick={() => setEditing(true)}>Référence de l'année précédente</Button>)}
      </Group>
      <Text size="sm" c="dimmed" mb="sm">
        {ref.source === "ca12a" && <>Référence : TVA due sur la CA12A {ref.label}, <MoneyText cents={ref.due_cents ?? 0} /></>}
        {ref.source === "entered" && <>Référence saisie : <MoneyText cents={ref.due_cents ?? 0} /></>}
        {ref.source === "missing" && "Pas de référence."}
        {ref.before_assets_cents !== null && <> ; avant TVA sur immobilisations, <MoneyText cents={ref.before_assets_cents} /></>}
        {data.proposed_cents !== null && <> · acompte calculé <MoneyText cents={data.proposed_cents} /></>}
        {data.estimate && <> · TVA estimée de l'année <MoneyText cents={data.estimate.year_cents} /></>}
      </Text>
      {data.dispensed && <Alert color="lichen" mb="sm">Dispensé d'acomptes : TVA due l'année précédente, avant TVA sur
        immobilisations, sous <MoneyText cents={data.exemption_cents} /> ; tout se paie avec la CA12A.</Alert>}
      {data.warnings.map((w) => <Alert key={w} color={w.startsWith("TVA estimée") ? "brique" : "paille"} mb="sm">{w}</Alert>)}
      <Table>
        <Table.Thead><Table.Tr><Table.Th>Acompte</Table.Th><Table.Th>Trimestre</Table.Th><Table.Th>Échéance</Table.Th>
          <Table.Th>Statut</Table.Th><Table.Th ta="right">Montant</Table.Th><Table.Th /></Table.Tr></Table.Thead>
        <Table.Tbody>
          {data.items.map((row) => (
            <Table.Tr key={row.number}>
              <Table.Td>n° {row.number}</Table.Td>
              <Table.Td className="lv-num">{row.label}</Table.Td>
              <Table.Td className="lv-num">{formatDate(row.deadline)}</Table.Td>
              <Table.Td><StatusBadge tone={row.late ? "gap" : INSTALLMENT_TONES[row.status]}>
                {row.late ? `${row.status_label} — en retard` : row.status_label}</StatusBadge>
                {row.motive && <Text size="xs" c="dimmed">{row.motive}</Text>}</Table.Td>
              <Table.Td ta="right">{row.amount_cents !== null ? <MoneyText cents={row.amount_cents} />
                : data.proposed_cents !== null && row.status === "to_prepare"
                  ? <Text size="sm" c="dimmed">≈ <MoneyText cents={data.proposed_cents} /></Text> : "—"}</Table.Td>
              <Table.Td ta="right">
                {can.write && row.can_validate && <Button size="xs" onClick={() => setRecording(row)}>Enregistrer</Button>}
                {can.write && row.return?.status === "validated" && (
                  <Group gap="xs" justify="flex-end">
                    <Button size="xs" variant="light" onClick={() => setPaying(row.return!.id)}>Payé</Button>
                    {row === lastRecorded && !data.annual_return && (
                      <ConfirmButton size="xs" title={`Annuler l'acompte n° ${row.number} ?`}
                        message="La déclaration d'acompte et son écriture (brouillard) sont supprimées."
                        confirmLabel="Annuler l'acompte" onConfirm={() => unvalidate.mutate(row.return!.id)}>Annuler</ConfirmButton>)}
                  </Group>)}
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
      <FormModal opened={!!recording} onClose={() => setRecording(null)} title={`Acompte n° ${recording?.number ?? ""}`}>
        {recording && <RecordForm schedule={data} row={recording} onDone={() => setRecording(null)} />}
      </FormModal>
      <FormModal opened={paying !== null} onClose={() => setPaying(null)} title="Acompte payé">
        {paying !== null && <PayForm id={paying} onDone={() => setPaying(null)} />}
      </FormModal>
      <FormModal opened={editing} onClose={() => setEditing(false)} title="Référence des acomptes">
        {editing && <ReferenceForm schedule={data} onDone={() => setEditing(false)} />}
      </FormModal>
    </Paper>
  );
}

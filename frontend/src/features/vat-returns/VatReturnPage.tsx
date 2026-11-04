// Compta › Déclarations de TVA › un mois (lot T3) : cases de la CA3 dans l'ordre du formulaire, avec le
// code de chaque case (saisie TeleDEC) ; un montant ouvre les lignes d'écriture qui le composent ;
// contrôles, validation (cases figées, liquidation), annulation de la dernière, dépôt (mois verrouillé).
import { useState } from "react";
import { useParams } from "react-router";
import {
  Alert, Anchor, Badge, Button, Center, Drawer, Group, List, Loader, Paper, Stack, Table, Text, TextInput,
} from "@mantine/core";
import { DateInput } from "@mantine/dates";
import { useQuery } from "@tanstack/react-query";
import { Download, FileText } from "lucide-react";
import { api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { useCan } from "../../api/session";
import { ConfirmButton } from "../../components/ConfirmButton";
import { FormModal } from "../../components/FormModal";
import { MoneyInput, MoneyText } from "../../components/Money";
import { PageHeader } from "../../components/PageHeader";
import { StatusBadge } from "../../components/StatusBadge";
import { AppLink } from "../../app/navigation";
import { formatDate } from "../../lib/format";
import {
  VAT_RETURNS_KEY, formatWholeEuros, monthLabel, type BoxLine, type FormRow, type VatReturnPreview,
} from "./types";

function BoxLines({ period, box, onClose }: { period: string; box: FormRow | null; onClose: () => void }) {
  const { data } = useQuery({ queryKey: [...VAT_RETURNS_KEY, "lines", period, box?.line], enabled: !!box,
    queryFn: () => api.get<{ items: BoxLine[] }>(`/api/v1/vat-returns/lines?period=${period}&box=${box!.line}`) });
  return (
    <Drawer opened={!!box} onClose={onClose} position="right" size="xl"
      title={box ? `Ligne ${box.line} — ${box.label}` : ""}>
      {!data ? <Center h={200}><Loader /></Center> : data.items.length === 0 ? <Text c="dimmed">Aucune ligne.</Text> : (
        <Table>
          <Table.Thead><Table.Tr><Table.Th>Date</Table.Th><Table.Th>Écriture</Table.Th><Table.Th>Compte</Table.Th>
            <Table.Th>Code</Table.Th><Table.Th ta="right">Base HT</Table.Th><Table.Th ta="right">Débit</Table.Th>
            <Table.Th ta="right">Crédit</Table.Th></Table.Tr></Table.Thead>
          <Table.Tbody>
            {data.items.map((l) => (
              <Table.Tr key={l.id}>
                <Table.Td className="lv-num">{formatDate(l.date)}</Table.Td>
                <Table.Td><AppLink href={`/entries/${l.entry_id}`}>{l.reference ?? `n° ${l.entry_id}`}</AppLink>
                  <Text size="xs" c="dimmed">{l.label || l.description}</Text></Table.Td>
                <Table.Td className="lv-num">{l.account}</Table.Td>
                <Table.Td className="lv-num">{l.vat_code}</Table.Td>
                <Table.Td ta="right">{l.vat_base_cents != null && <MoneyText cents={l.vat_base_cents} />}</Table.Td>
                <Table.Td ta="right">{l.debit_cents ? <MoneyText cents={l.debit_cents} /> : ""}</Table.Td>
                <Table.Td ta="right">{l.credit_cents ? <MoneyText cents={l.credit_cents} /> : ""}</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}
    </Drawer>
  );
}

function DeclareForm({ id, onDone }: { id: number; onDone: () => void }) {
  const [declaredOn, setDeclaredOn] = useState<string | null>(new Date().toISOString().slice(0, 10));
  const [reference, setReference] = useState("");
  const declare = useAction(() => api.post<{ notices: Notice[] }>(`/api/v1/vat-returns/${id}/declare`,
    { declared_on: declaredOn, reference }), { invalidate: [VAT_RETURNS_KEY] });
  return (
    <form onSubmit={(e) => { e.preventDefault(); declare.mutate(undefined, { onSuccess: onDone }); }}>
      <Stack>
        <Text size="sm">La liquidation est validée et le mois verrouillé : plus aucune écriture ne pourra y être saisie.
          Une erreur se corrigera par une régularisation sur une déclaration suivante.</Text>
        <DateInput label="Déposée le" required valueFormat="DD/MM/YYYY" value={declaredOn} onChange={setDeclaredOn} />
        <TextInput label="Référence du dépôt" description="Facultatif (numéro d'accusé de réception TeleDEC)."
          value={reference} onChange={(e) => setReference(e.currentTarget.value)} />
        <Group><Button type="submit" loading={declare.isPending}>Marquer déposée</Button></Group>
      </Stack>
    </form>
  );
}

export default function VatReturnPage() {
  const period = useParams().period ?? "";
  const can = useCan();
  const [box, setBox] = useState<FormRow | null>(null);
  const [declaring, setDeclaring] = useState(false);
  const { data } = useQuery({ queryKey: [...VAT_RETURNS_KEY, "preview", period],
    queryFn: () => api.get<VatReturnPreview>(`/api/v1/vat-returns/preview?period=${period}`) });
  const opts = { invalidate: [VAT_RETURNS_KEY] };
  const [refund, setRefund] = useState<number | null>(null);
  const [tca, setTca] = useState<number | null>(null);
  const validate = useAction(() => api.post<{ notices: Notice[] }>("/api/v1/vat-returns",
    { period, ...(refund ? { refund_cents: Math.round(refund / 100) * 100 } : {}),
      ...(tca ? { tca_euros: Math.round(tca / 100) } : {}) }), opts);
  const unvalidate = useAction((id: number) => api.post<{ notices: Notice[] }>(`/api/v1/vat-returns/${id}/unvalidate`), opts);
  if (!data) return <Center h={300}><Loader /></Center>;
  const ret = data.vat_return;
  const blocked = data.checks.some((c) => c.level === "error");
  const status = ret ? <StatusBadge tone={ret.status === "declared" ? "ok" : "info"}>{ret.status_label}</StatusBadge>
    : <StatusBadge tone="todo">Non validée</StatusBadge>;
  return (
    <>
      <PageHeader title={`TVA — ${monthLabel(period)}`}
        description={<Group gap="xs">{status}<Text size="sm" c="dimmed">Formulaire {data.form ?? "3310-CA3-SD"} {data.form_year} · échéance
          {" "}{formatDate(data.deadline)}{ret?.declared_on && ` · déposée le ${formatDate(ret.declared_on)}`}
          {ret?.declared_reference && ` (réf. ${ret.declared_reference})`}</Text></Group>}
        actions={<>
          <Button variant="default" component="a" href={`/vat-returns/${period}.pdf`} target="_blank"
            leftSection={<FileText size={16} />}>PDF</Button>
          <Button variant="default" component="a" href={`/vat-returns/${period}.xlsx`}
            leftSection={<Download size={16} />}>XLSX</Button>
          {can.write && !ret && (
            <ConfirmButton danger={false} variant="filled" disabled={blocked} loading={validate.isPending}
              title={`Valider la déclaration de ${monthLabel(period)} ?`}
              message={`Les écritures en brouillard jusqu'à la fin de la période sont validées, les cases figées et l'écriture de liquidation passée (TVA à décaisser ou crédit à reporter)${refund ? `, avec un remboursement de ${formatWholeEuros(Math.round(refund / 100))} demandé` : ""}.`}
              confirmLabel="Valider" onConfirm={() => validate.mutate(undefined)}>Valider</ConfirmButton>
          )}
          {can.write && ret?.status === "validated" && (
            <>
              <ConfirmButton size="sm" loading={unvalidate.isPending} title="Annuler la validation ?"
                message="Les cases ne sont plus figées et l'écriture de liquidation est retirée (contrepassée si elle a été validée)."
                confirmLabel="Annuler la validation" onConfirm={() => unvalidate.mutate(ret.id)}>Annuler la validation</ConfirmButton>
              <Button onClick={() => setDeclaring(true)}>Marquer déposée</Button>
            </>
          )}
        </>} />
      <AppLink href="/vat-returns/">← Toutes les déclarations</AppLink>
      <Stack mt="md" maw={1000}>
        {data.checks.map((check) => (
          <Alert key={check.message} color={check.level === "error" ? "brique" : "paille"} role={check.level === "error" ? "alert" : undefined}>
            {check.message}{check.count != null && ` (${check.count})`}</Alert>
        ))}
        <Paper p="md">
          <Group justify="space-between">
            <Text fw={700}>{data.due_cents ? <>TVA nette due : <MoneyText cents={data.due_cents} fw={700} /></>
              : data.credit_cents ? <>Crédit de TVA à reporter : <MoneyText cents={data.credit_cents} fw={700} /></>
                : "Déclaration néant"}</Text>
            <Group gap="md">
              {data.credit_carried_cents > 0 && <Text size="sm" c="dimmed">Crédit reporté de la période précédente :
                {" "}<MoneyText cents={data.credit_carried_cents} /></Text>}
              {ret?.liquidation_entry && <Anchor component={AppLink} href={`/entries/${ret.liquidation_entry.id}`} size="sm">
                Liquidation {ret.liquidation_entry.reference}</Anchor>}
            </Group>
          </Group>
                  {!ret && can.write && data.refund?.possible && (
            <MoneyInput mt="sm" w={360} label={data.form_code === "CA12A" ? "Remboursement à demander (cadre VII, ligne 45)"
              : "Remboursement de crédit à demander (formulaire 3519)"}
              description={`De ${formatWholeEuros(data.refund.minimum_cents / 100)} à ${formatWholeEuros(data.refund.maximum_cents / 100)} ; vide : tout le crédit est reporté.`}
              value={refund} onChange={setRefund} />)}
          {ret && ret.refund_cents > 0 && <Text size="sm" mt="xs">Remboursement demandé (3519) : <MoneyText cents={ret.refund_cents} /></Text>}
          {!ret && can.write && data.form_code === "CA12A" && (
            <MoneyInput mt="sm" w={360} label="Ligne 31 — taxe sur le chiffre d'affaires des exploitants agricoles"
              description="Saisie libre, en euros (art. 302 bis MB) ; à comptabiliser à part." value={tca} onChange={setTca} />)}
          {data.form_code === "CA12A" && !!data.installments_cents && <Text size="sm" mt="xs" c="dimmed">Acomptes imputés
            (ligne 25) : <MoneyText cents={data.installments_cents} /></Text>}
        </Paper>
        <Table>
          <Table.Thead><Table.Tr><Table.Th w={60}>Ligne</Table.Th><Table.Th w={70}>Code</Table.Th><Table.Th>Libellé</Table.Th>
            <Table.Th ta="right">Base HT</Table.Th><Table.Th ta="right">Montant</Table.Th></Table.Tr></Table.Thead>
          <Table.Tbody>
            {data.rows.map((row, i) => row.kind === "section" ? (
              <Table.Tr key={`s${i}`} bg="var(--lv-sauge)"><Table.Td colSpan={5}><Text fw={600} size="sm">{row.label}</Text></Table.Td></Table.Tr>
            ) : (
              <Table.Tr key={row.line} fw={row.kind === "total" ? 600 : undefined}>
                <Table.Td className="lv-num">{row.line}</Table.Td>
                <Table.Td className="lv-num"><Text size="sm" c="dimmed">{row.code ?? ""}</Text></Table.Td>
                <Table.Td>{row.label}{row.note && <Text size="xs" c="dimmed">{row.note}</Text>}</Table.Td>
                <Table.Td ta="right" className="lv-num">{row.with_base ? formatWholeEuros(row.base) : ""}</Table.Td>
                <Table.Td ta="right" className="lv-num">
                  {row.kind === "box" && row.amount ? (
                    <Anchor component="button" type="button" className="lv-num" onClick={() => setBox(row)}
                      aria-label={`Lignes de la case ${row.line}`}>{formatWholeEuros(row.amount)}</Anchor>
                  ) : row.amount ? formatWholeEuros(row.amount) : <Text span c="dimmed">0</Text>}
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
        <Text size="xs" c="dimmed">Montants arrondis à l'euro, comme sur le formulaire. Code : identifiant de la case dans
          la saisie en ligne. {Object.keys(data.codes).length > 0 && <>Codes de TVA repris : {Object.keys(data.codes).map((c) =>
            <Badge key={c} size="xs" variant="light" mr={4}>{c}</Badge>)}</>}</Text>
        {!ret && data.lines_count === 0 && <List size="sm"><List.Item>Aucune ligne codée sur la période : la déclaration
          sera néant.</List.Item></List>}
      </Stack>
      <BoxLines period={period} box={box} onClose={() => setBox(null)} />
      <FormModal opened={declaring} onClose={() => setDeclaring(false)} title="Déclaration déposée sur TeleDEC">
        {ret && <DeclareForm id={ret.id} onDone={() => setDeclaring(false)} />}
      </FormModal>
    </>
  );
}

// Compta › Remboursement forfaitaire (lot AG2.e) : demande 3520 d'une année de ventes, calculée depuis les recettes
// (comptes 70) : classes de taux des comptes, type des clients, attestations d'achats, forfait, seuil, dépôt.
import { useState } from "react";
import {
  Alert, Anchor, Button, Center, FileInput, Group, Loader, Paper, Select, SimpleGrid, Stack, Table, Text, TextInput, Title,
} from "@mantine/core";
import { DateInput } from "@mantine/dates";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, FileText } from "lucide-react";
import { ApiError, api } from "../../api/client";
import { showNotices, useAction, type Notice } from "../../api/resources";
import { useCan } from "../../api/session";
import { upload } from "../../api/upload";
import { ConfirmButton } from "../../components/ConfirmButton";
import { FilterBar, useUrlParams } from "../../components/FilterBar";
import { FormModal } from "../../components/FormModal";
import { MoneyInput, MoneyText } from "../../components/Money";
import { PageHeader } from "../../components/PageHeader";
import { StatusBadge } from "../../components/StatusBadge";
import { formatDate } from "../../lib/format";
import { CalculatorLink } from "../tools/CalculatorLink";

export const RFA_KEY = ["rfa"];

type Option = { value: string; label: string };
interface Attestation { id: number; amount_cents: number; received_on: string | null; note: string | null; has_file: boolean; file_name: string | null }
export interface RfaClient {
  entity_id: number | null; name: string; buyer: string | null; buyer_guessed: boolean; eligible: boolean;
  high_cents: number; low_cents: number; excluded_cents: number; unclassified_cents: number; eligible_cents: number;
  attestation: Attestation | null; issues: string[];
}
export interface RfaYear {
  year: number; regime: string | null; clients: RfaClient[];
  accounts: { account_id: number; code: string; label: string; rate: string | null; source: string | null; total_cents: number }[];
  high_base_cents: number; low_base_cents: number; excluded_cents: number; non_eligible_cents: number; unclassified_cents: number;
  high_bp: number | null; low_bp: number | null; amount_cents: number; deadline: string; late: boolean; can_declare: boolean;
  threshold: { threshold_cents: number | null; factor: number; average_cents: number; over: boolean; years: { year: number; receipts_cents: number }[] };
  problems: string[]; warnings: string[]; applicable: { ok: boolean; reason: string | null }; rates: Option[]; buyers: Option[]; years_available: number[];
  claim: { id: number; status: "declared" | "refunded"; status_label: string; amount_cents: number; declared_on: string;
    refunded_on: string | null; entry: { id: number; reference: string } | null } | null;
}

const SOURCES: Record<string, string> = { category: "catégorie", products: "catalogue", proposed: "proposée" };
const opts = { invalidate: [RFA_KEY] };
const pct = (bp: number | null) => (bp == null ? "taux non paramétré" : `${(bp / 100).toLocaleString("fr-FR")} %`);
const salesAt = (bp: number | null) => (bp == null ? "Ventes (taux non paramétré)" : `Ventes au taux de ${pct(bp)}`);

function AttestationForm({ year, client, onDone }: { year: number; client: RfaClient; onDone: () => void }) {
  const queryClient = useQueryClient();
  const [amount, setAmount] = useState<number | null>(client.attestation?.amount_cents ?? client.eligible_cents);
  const [received, setReceived] = useState<string | null>(client.attestation?.received_on ?? null);
  const [note, setNote] = useState(client.attestation?.note ?? "");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const submit = async () => {
    const form = new FormData();
    form.append("payload", JSON.stringify({ amount_cents: amount, received_on: received, note }));
    if (file) form.append("attachment", file);
    setSending(true);
    try {
      const body = await upload<{ notices: Notice[] }>(`/api/v1/rfa/${year}/attestations/${client.entity_id}`, form);
      showNotices(body.notices);
      void queryClient.invalidateQueries({ queryKey: RFA_KEY });
      onDone();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Enregistrement impossible.");
    } finally {
      setSending(false);
    }
  };
  return (
    <form onSubmit={(e) => { e.preventDefault(); void submit(); }}>
      <Stack>
        <Text size="sm">Ventes éligibles de {client.name} dans Lyvre : <MoneyText cents={client.eligible_cents} />.</Text>
        <MoneyInput label="Montant attesté" required value={amount} onChange={setAmount} />
        <DateInput label="Reçue le" clearable valueFormat="DD/MM/YYYY" value={received} onChange={setReceived} />
        <TextInput label="Remarque" value={note} onChange={(e) => setNote(e.currentTarget.value)} />
        <FileInput label="Attestation" placeholder={client.attestation?.file_name ?? "PDF, JPEG ou PNG"} clearable
          value={file} onChange={setFile} accept="application/pdf,image/jpeg,image/png" />
        {error && <Alert color="brique">{error}</Alert>}
        <Group><Button type="submit" loading={sending}>Enregistrer</Button></Group>
      </Stack>
    </form>
  );
}

function DateForm({ label, action, onDone }: { label: string; action: (day: string) => Promise<unknown>; onDone: () => void }) {
  const [day, setDay] = useState<string | null>(new Date().toISOString().slice(0, 10));
  const [busy, setBusy] = useState(false);
  return (
    <form onSubmit={(e) => { e.preventDefault(); if (day) { setBusy(true); action(day).then(onDone).finally(() => setBusy(false)); } }}>
      <Stack>
        <DateInput label={label} required valueFormat="DD/MM/YYYY" value={day} onChange={setDay} />
        <Group><Button type="submit" loading={busy}>Enregistrer</Button></Group>
      </Stack>
    </form>
  );
}

export default function RfaPage() {
  const can = useCan();
  const [params, setParams] = useUrlParams({ year: String(new Date().getFullYear() - 1) });
  const year = Number(params.year);
  const [attesting, setAttesting] = useState<RfaClient | null>(null);
  const [dialog, setDialog] = useState<"declare" | "refunded" | null>(null);
  const [showAnyway, setShowAnyway] = useState(false);
  const { data } = useQuery({ queryKey: [...RFA_KEY, year], queryFn: () => api.get<RfaYear>(`/api/v1/rfa/${year}`) });
  const setRate = useAction((v: { account: number; rate: string | null }) =>
    api.put<{ notices: Notice[] }>(`/api/v1/rfa/accounts/${v.account}/rate`, { rfa_rate: v.rate }), opts);
  const setBuyer = useAction((v: { entity: number; buyer: string | null }) =>
    api.put<{ notices: Notice[] }>(`/api/v1/rfa/buyers/${v.entity}`, { rfa_buyer: v.buyer }), opts);
  const declare = useAction((day: string) => api.post<{ notices: Notice[] }>(`/api/v1/rfa/${year}/declare`, { declared_on: day }), opts);
  const refunded = useAction((day: string) => api.post<{ notices: Notice[] }>(`/api/v1/rfa/${year}/refunded`, { refunded_on: day }), opts);
  const cancel = useAction(() => api.delete<{ notices: Notice[] }>(`/api/v1/rfa/${year}/declare`), opts);
  if (!data) return <Center h={300}><Loader /></Center>;
  const claim = data.claim;
  const locked = !!claim;
  return (
    <>
      <PageHeader title="Remboursement forfaitaire"
        description="Demande 3520 sur les ventes de l'année civile à des clients assujettis : forfait par taux, attestations d'achats à joindre, à déposer avant le 31 décembre de l'année suivante."
        actions={<CalculatorLink code="rfa" label="Simuler" />} />
      <FilterBar>
        <Select aria-label="Année des ventes" w={160} allowDeselect={false} value={String(year)}
          data={data.years_available.map((y) => ({ value: String(y), label: `Ventes ${y}` }))}
          onChange={(v) => setParams({ year: v ?? "" })} />
        <Group gap="xs" ml="auto">
          <Button size="xs" variant="light" component="a" href={`/rfa/${year}.xlsx`} leftSection={<Download size={14} />}>XLSX</Button>
          <Button size="xs" variant="light" component="a" target="_blank" href={`/rfa/${year}.pdf`} leftSection={<FileText size={14} />}>État récapitulatif</Button>
        </Group>
      </FilterBar>
      {!data.applicable.ok && (
        <Alert color="brique" mb="sm">
          <Text size="sm">{data.applicable.reason}</Text>
          {!claim && <Button mt="sm" size="xs" variant="light" onClick={() => setShowAnyway((v) => !v)}>
            {showAnyway ? "Masquer la simulation" : "Afficher la simulation quand même"}</Button>}
        </Alert>)}
      {(data.applicable.ok || showAnyway || !!claim) && (<>
      {data.problems.map((p) => <Alert key={p} color="brique" mb="sm">{p}</Alert>)}
      {data.warnings.map((w) => <Alert key={w} color="paille" mb="sm">{w}</Alert>)}
      <SimpleGrid cols={{ base: 1, sm: 4 }} mb="lg">
        <Paper withBorder p="md"><Text size="xs" c="dimmed">{salesAt(data.high_bp)}</Text><MoneyText cents={data.high_base_cents} /></Paper>
        <Paper withBorder p="md"><Text size="xs" c="dimmed">{salesAt(data.low_bp)}</Text><MoneyText cents={data.low_base_cents} /></Paper>
        <Paper withBorder p="md"><Text size="xs" c="dimmed">Remboursement forfaitaire</Text>
          <Title order={3}><MoneyText cents={claim?.amount_cents ?? data.amount_cents} /></Title></Paper>
        <Paper withBorder p="md"><Text size="xs" c="dimmed">Dépôt</Text>
          {claim ? <StatusBadge tone={claim.status === "refunded" ? "ok" : "info"}>{`${claim.status_label} le ${formatDate(claim.refunded_on ?? claim.declared_on)}`}</StatusBadge>
            : <StatusBadge tone={data.late ? "gap" : "todo"}>{`avant le ${formatDate(data.deadline)}`}</StatusBadge>}
          {claim?.entry && <Text size="xs" c="dimmed">écriture <Anchor href={`/entries/${claim.entry.id}`}>{claim.entry.reference}</Anchor></Text>}</Paper>
      </SimpleGrid>
      {can.write && (
        <Group mb="lg">
          {!claim && <Button disabled={!data.can_declare} onClick={() => setDialog("declare")}>Marquer déposée</Button>}
          {claim?.status === "declared" && <Button variant="light" onClick={() => setDialog("refunded")}>Remboursement reçu</Button>}
          {claim?.status === "declared" && (
            <ConfirmButton title={`Annuler le dépôt de la demande ${year} ?`} message="La demande redevient modifiable ; son écriture de créance est supprimée ou contrepassée."
              confirmLabel="Annuler le dépôt" onConfirm={() => cancel.mutate(undefined)}>Annuler le dépôt</ConfirmButton>)}
          {!claim && !data.can_declare && data.problems.length === 0 && <Text size="sm" c="dimmed">Dépôt possible à partir du 1er janvier {year + 1}.</Text>}
        </Group>)}

      <Title order={4} mb="xs">Classes de taux des comptes de vente</Title>
      <Table mb="lg">
        <Table.Thead><Table.Tr><Table.Th>Compte</Table.Th><Table.Th>Classe</Table.Th><Table.Th ta="right">Ventes {year}</Table.Th></Table.Tr></Table.Thead>
        <Table.Tbody>
          {data.accounts.map((a) => (
            <Table.Tr key={a.account_id}>
              <Table.Td><span className="lv-num">{a.code}</span> {a.label}</Table.Td>
              <Table.Td><Group gap="xs">
                <Select aria-label={`Classe du compte ${a.code}`} w={360} placeholder="À choisir" disabled={!can.write || locked}
                  data={data.rates} value={a.rate} clearable error={!a.rate ? true : undefined}
                  onChange={(v) => setRate.mutate({ account: a.account_id, rate: v })} />
                {a.source && <Text size="xs" c="dimmed">{SOURCES[a.source]}</Text>}</Group></Table.Td>
              <Table.Td ta="right"><MoneyText cents={a.total_cents} /></Table.Td>
            </Table.Tr>))}
        </Table.Tbody>
      </Table>

      <Title order={4} mb="xs">Clients et attestations</Title>
      <Table mb="lg">
        <Table.Thead><Table.Tr><Table.Th>Client</Table.Th><Table.Th>Type</Table.Th><Table.Th ta="right">{pct(data.high_bp)}</Table.Th>
          <Table.Th ta="right">{pct(data.low_bp)}</Table.Th><Table.Th ta="right">Exclues / sans classe</Table.Th><Table.Th>Attestation</Table.Th></Table.Tr></Table.Thead>
        <Table.Tbody>
          {data.clients.map((c) => (
            <Table.Tr key={c.entity_id ?? "none"}>
              <Table.Td>{c.name}{c.issues.map((i) => <Text key={i} size="xs" c="var(--lv-brique)">{i}</Text>)}</Table.Td>
              <Table.Td>{c.entity_id === null ? "—" : (
                <Select aria-label={`Type de ${c.name}`} w={300} data={data.buyers} value={c.buyer} disabled={!can.write || locked}
                  description={c.buyer_guessed ? "déduit de la fiche" : undefined}
                  onChange={(v) => setBuyer.mutate({ entity: c.entity_id!, buyer: v })} />)}</Table.Td>
              <Table.Td ta="right"><MoneyText cents={c.high_cents} /></Table.Td>
              <Table.Td ta="right"><MoneyText cents={c.low_cents} /></Table.Td>
              <Table.Td ta="right"><MoneyText cents={c.excluded_cents + c.unclassified_cents} /></Table.Td>
              <Table.Td>
                {c.attestation && <Text size="sm"><MoneyText cents={c.attestation.amount_cents} />
                  {c.attestation.has_file && <> · <Anchor href={`/api/v1/rfa/attestations/${c.attestation.id}/file`} target="_blank">pièce</Anchor></>}</Text>}
                {can.write && !locked && c.entity_id !== null && c.buyer === "professional" && (
                  <Button size="xs" variant="light" onClick={() => setAttesting(c)}>{c.attestation ? "Modifier" : "Saisir"}</Button>)}
              </Table.Td>
            </Table.Tr>))}
        </Table.Tbody>
      </Table>

      <Text size="sm" c="dimmed">Seuil du forfait : moyenne des recettes {data.threshold.years.map((y) => y.year).join(" et ")}{" "}
        <MoneyText cents={data.threshold.average_cents} /> pour {data.threshold.threshold_cents !== null
          ? <MoneyText cents={data.threshold.threshold_cents * data.threshold.factor} /> : "?"}
        {data.threshold.factor > 1 && ` (${data.threshold.factor} associés de GAEC)`}.</Text>
      </>)}

      <FormModal opened={!!attesting} onClose={() => setAttesting(null)} title={`Attestation d'achats ${year}`}>
        {attesting && <AttestationForm year={year} client={attesting} onDone={() => setAttesting(null)} />}
      </FormModal>
      <FormModal opened={dialog === "declare"} onClose={() => setDialog(null)} title={`Demande ${year} déposée`}>
        {dialog === "declare" && <DateForm label="Déposée le" action={(d) => declare.mutateAsync(d)} onDone={() => setDialog(null)} />}
      </FormModal>
      <FormModal opened={dialog === "refunded"} onClose={() => setDialog(null)} title={`Remboursement ${year} reçu`}>
        {dialog === "refunded" && <DateForm label="Reçu le" action={(d) => refunded.mutateAsync(d)} onDone={() => setDialog(null)} />}
      </FormModal>
    </>
  );
}

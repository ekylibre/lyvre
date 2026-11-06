// Ventes › Autofactures reçues (lot AG10.c) : dépôt d'une facture électronique émise par un client sous
// mandat de facturation (Factur-X, CII, UBL) ; contrôle (vendeur, lignes, TVA, doublon), compte de vente
// proposé par ligne, enregistrement en vente « reçue » ; liste avec le statut à transmettre par la plateforme.
import { useState } from "react";
import { Alert, Anchor, Badge, Button, Group, List, Paper, Select, SimpleGrid, Stack, Table, Text } from "@mantine/core";
import { Dropzone } from "@mantine/dropzone";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { FileUp } from "lucide-react";
import { api, ApiError } from "../../api/client";
import { showNotices, useList, type Notice } from "../../api/resources";
import { upload } from "../../api/upload";
import { Can } from "../../components/Can";
import { DataGrid, type GridColumn } from "../../components/DataGrid";
import { MoneyText } from "../../components/Money";
import { PageHeader } from "../../components/PageHeader";
import { StatusBadge } from "../../components/StatusBadge";
import { formatDate } from "../../lib/format";
import { AppLink, useGoTo } from "../../app/navigation";
import { LIFECYCLE_TONES, SALES_KEY, type SaleDetail, type SaleRow } from "./types";

interface ReceivedLine {
  index: number; label: string; kind: "line" | "allowance" | "charge"; quantity: string; unit: string; unit_price: string;
  net_cents: number; vat_rate_bp: number; account_code: string; account_origin: string | null;
}

interface Party { name: string; siren: string | null; vat_number: string | null; city: string | null }

export interface SelfBilledAnalysis {
  syntax: "cii" | "ubl"; container: "pdf" | "xml"; type_code: string; self_billed: boolean; number: string;
  issue_date: string | null; due_date: string | null; seller: Party; buyer: Party; client: { id: number; name: string } | null;
  lines: ReceivedLine[]; taxes: { rate_bp: number; base_cents: number; tax_cents: number }[];
  untaxed_cents: number; tax_cents: number; total_cents: number | null; payable_cents: number | null;
  notes: { subject: string | null; text: string }[]; problems: string[]; warnings: string[];
}

const rate = (bp: number) => `${(bp / 100).toLocaleString("fr-FR")} %`;

/** Contrôles et lignes d'une autofacture lue, avec le compte de vente choisi par ligne. */
export function SelfBilledReview({ analysis, accounts, options, onAccount }: {
  analysis: SelfBilledAnalysis; accounts: Record<number, string>; options: { value: string; label: string }[];
  onAccount: (index: number, code: string) => void;
}) {
  return (
    <Stack>
      {analysis.problems.length > 0 && <Alert color="brique" title="Autofacture refusée :">
        <List size="sm">{analysis.problems.map((p) => <List.Item key={p}>{p}</List.Item>)}</List></Alert>}
      {analysis.warnings.length > 0 && <Alert color="paille" title="À vérifier :">
        <List size="sm">{analysis.warnings.map((w) => <List.Item key={w}>{w}</List.Item>)}</List></Alert>}
      <SimpleGrid cols={{ base: 2, md: 4 }}>
        <Paper p="sm"><Text size="sm" c="dimmed">Facture</Text>
          <Text fw={700}>{analysis.number}</Text>
          <Text size="xs" c="dimmed">{analysis.self_billed ? "autofacture (389)" : `type ${analysis.type_code}`} · {analysis.syntax.toUpperCase()}
            {analysis.container === "pdf" ? " (Factur-X)" : ""}</Text></Paper>
        <Paper p="sm"><Text size="sm" c="dimmed">Client</Text><Text fw={700}>{analysis.buyer.name}</Text>
          <Text size="xs" c="dimmed">{analysis.client ? "fiche existante" : "fiche créée à l'enregistrement"}
            {analysis.buyer.siren ? ` · SIREN ${analysis.buyer.siren}` : ""}</Text></Paper>
        <Paper p="sm"><Text size="sm" c="dimmed">Date · échéance</Text>
          <Text fw={700} className="lv-num">{formatDate(analysis.issue_date)} · {formatDate(analysis.due_date)}</Text></Paper>
        <Paper p="sm"><Text size="sm" c="dimmed">Total TTC</Text><MoneyText cents={analysis.total_cents ?? 0} fw={700} /></Paper>
      </SimpleGrid>
      <Paper p={0}>
        <Table.ScrollContainer minWidth={700}>
          <Table>
            <Table.Thead><Table.Tr><Table.Th>Désignation</Table.Th><Table.Th ta="right">Quantité</Table.Th><Table.Th ta="right">Prix</Table.Th>
              <Table.Th ta="right">TVA</Table.Th><Table.Th ta="right">HT</Table.Th><Table.Th>Compte de vente</Table.Th></Table.Tr></Table.Thead>
            <Table.Tbody>
              {analysis.lines.map((l) => (
                <Table.Tr key={l.index}>
                  <Table.Td>{l.label}{l.kind !== "line" && <Badge ml={6} size="xs" variant="light">{l.kind === "allowance" ? "remise" : "frais"}</Badge>}</Table.Td>
                  <Table.Td ta="right" className="lv-num">{l.quantity} {l.unit}</Table.Td>
                  <Table.Td ta="right" className="lv-num">{l.unit_price && `${l.unit_price} €`}</Table.Td>
                  <Table.Td ta="right" className="lv-num">{rate(l.vat_rate_bp)}</Table.Td>
                  <Table.Td ta="right"><MoneyText cents={l.net_cents} size="sm" /></Table.Td>
                  <Table.Td miw={240}>
                    <Select size="xs" searchable clearable data={options} value={accounts[l.index] || null} aria-label={`Compte de ${l.label}`}
                      placeholder="à choisir avant l'acceptation" onChange={(v) => onAccount(l.index, v ?? "")} />
                    {l.account_origin && accounts[l.index] === l.account_code &&
                      <Text size="xs" c="dimmed">proposé : {l.account_origin}</Text>}
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
        <Stack gap={2} align="flex-end" p="md">
          <Text size="sm">Total HT <MoneyText cents={analysis.untaxed_cents} size="sm" /></Text>
          {analysis.taxes.map((t) => <Text key={t.rate_bp} size="sm">TVA {rate(t.rate_bp)} sur <MoneyText cents={t.base_cents} size="sm" /> :{" "}
            <MoneyText cents={t.tax_cents} size="sm" /></Text>)}
        </Stack>
      </Paper>
    </Stack>
  );
}

export default function SelfBilledPage() {
  const client = useQueryClient();
  const goTo = useGoTo();
  const { data, isFetching } = useList<SaleRow>([...SALES_KEY, "self-billed"], "/api/v1/sales?self_billed=1");
  const options = useQuery({ queryKey: [...SALES_KEY, "form-options"],
    queryFn: () => api.get<{ sale_accounts: { value: string; label: string }[] }>("/api/v1/sales/form-options") });
  const [file, setFile] = useState<File | null>(null);
  const [analysis, setAnalysis] = useState<SelfBilledAnalysis | null>(null);
  const [accounts, setAccounts] = useState<Record<number, string>>({});
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const analyze = async (chosen: File) => {
    const form = new FormData();
    form.append("file", chosen);
    setBusy(true); setError(null); setAnalysis(null);
    try {
      const result = await upload<SelfBilledAnalysis>("/api/v1/sales/self-billed/analyze", form);
      setAnalysis(result);
      setAccounts(Object.fromEntries(result.lines.map((l) => [l.index, l.account_code])));
    } catch (e) { setError(e); } finally { setBusy(false); }
  };
  const save = async () => {
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    form.append("accounts", JSON.stringify(Object.fromEntries(Object.entries(accounts).filter(([, v]) => v))));
    setBusy(true); setError(null);
    try {
      const body = await upload<{ item: SaleDetail; notices: Notice[] }>("/api/v1/sales/self-billed", form);
      showNotices(body.notices);
      void client.invalidateQueries({ queryKey: SALES_KEY });
      goTo(`/sales/${body.item.id}`);
    } catch (e) { setError(e); } finally { setBusy(false); }
  };
  const columns: GridColumn<SaleRow>[] = [
    { accessor: "number", title: "N°", hideable: false,
      render: (s) => <Anchor component={AppLink} href={`/sales/${s.id}`} size="sm" className="lv-num">{s.number}</Anchor> },
    { accessor: "client", title: "Client", render: (s) => s.client.name },
    { accessor: "issue_date", title: "Date", render: (s) => <span className="lv-num">{formatDate(s.issue_date)}</span> },
    { accessor: "total_cents", title: "Montant", textAlign: "right", render: (s) => <MoneyText cents={s.total_cents} size="sm" /> },
    { accessor: "lifecycle", title: "Statut", render: (s) => s.lifecycle && <Group gap={6}>
      <StatusBadge tone={LIFECYCLE_TONES[s.lifecycle.status]}>{s.lifecycle.label}</StatusBadge>
      {s.lifecycle.code && <Text span size="xs" c="dimmed" className="lv-num">{s.lifecycle.code}</Text>}</Group> },
  ];
  return (
    <>
      <PageHeader title="Autofactures reçues"
        description="Factures émises à votre nom par une coopérative, une laiterie ou un négociant (mandat de facturation) : déposez le fichier, vérifiez, puis acceptez ou contestez. Le statut se transmet par votre plateforme agréée."
        actions={<Button variant="default" component={AppLink} href="/sales/">Ventes</Button>} />
      <Can>
        <Stack mb="lg">
          <Dropzone onDrop={(files) => { if (files[0]) { setFile(files[0]); void analyze(files[0]); } }} multiple={false} loading={busy}>
            <Group justify="center" gap="sm" mih={80}><FileUp size={28} />
              <Text>{file ? file.name : "Déposez l'autofacture : PDF Factur-X, XML CII ou UBL"}</Text></Group>
          </Dropzone>
          {error != null && <Alert color="brique" role="alert">{error instanceof ApiError ? error.message : "Échec."}</Alert>}
          {analysis && <>
            <SelfBilledReview analysis={analysis} accounts={accounts} options={options.data?.sale_accounts ?? []}
              onAccount={(index, code) => setAccounts((current) => ({ ...current, [index]: code }))} />
            <Group><Button disabled={analysis.problems.length > 0} loading={busy} onClick={() => void save()}>Enregistrer l'autofacture</Button>
              <Text size="sm" c="dimmed">Enregistrée « reçue », sans écriture : l'acceptation la comptabilise.</Text></Group>
          </>}
        </Stack>
      </Can>
      <DataGrid id="sales-self-billed" records={data?.items} columns={columns} fetching={isFetching} emptyText="Aucune autofacture reçue." />
    </>
  );
}

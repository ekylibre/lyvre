// Imports › Odoo : dépôt d'un export CSV de lignes de factures, rangé dans un lot ; lots importés.
import { useState } from "react";
import { Alert, Anchor, Group, List, Paper, Progress, Stack, Table, Text, TextInput, Title } from "@mantine/core";
import { Dropzone } from "@mantine/dropzone";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { FileUp } from "lucide-react";
import { api, ApiError } from "../../api/client";
import { showNotices, type Notice } from "../../api/resources";
import { upload } from "../../api/upload";
import { MoneyText } from "../../components/Money";
import { PageHeader } from "../../components/PageHeader";
import { formatDate } from "../../lib/format";
import { AppLink } from "../../app/navigation";
import { ODOO_IMPORTS_KEY } from "./types";
import { writeOnly } from "../../components/ReadOnlyPage";

interface Result {
  batch: string; imported: number; errors: string[]; url: string;
  preview: { invoice_number: string; invoice_date: string | null; partner_name: string; amount_ttc_cents: number; account_code: string }[];
}

function OdooImportPage() {
  const client = useQueryClient();
  const { data } = useQuery({ queryKey: ODOO_IMPORTS_KEY,
    queryFn: () => api.get<{ items: { name: string; lines: number; url: string }[] }>("/api/v1/imports/odoo") });
  const [batch, setBatch] = useState("");
  const [progress, setProgress] = useState<number | null>(null);
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState<string | null>(null);

  const send = async (file: File) => {
    const form = new FormData();
    form.append("batch_name", batch);
    form.append("csv_file", file);
    setError(null); setResult(null); setProgress(0);
    try {
      const body = await upload<{ result: Result; notices: Notice[] }>("/api/v1/imports/odoo", form, setProgress);
      setResult(body.result);
      showNotices(body.notices);
      void client.invalidateQueries({ queryKey: ODOO_IMPORTS_KEY });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "L'import a échoué.");
    } finally {
      setProgress(null);
    }
  };

  return (
    <>
      <PageHeader title="Import de lignes Odoo" description="Export CSV des lignes de factures Odoo, rangé dans un lot." />
      <Stack maw={720}>
        <TextInput label="Nom du lot" description="Facultatif : généré automatiquement si vide (odoo-AAAAMMJJ-HHMMSS)."
          placeholder="odoo-2026-06" maxLength={50} value={batch} onChange={(e) => setBatch(e.currentTarget.value)} />
        <Dropzone onDrop={(files) => files[0] && void send(files[0])} multiple={false} loading={progress !== null}
          accept={{ "text/csv": [".csv"], "application/vnd.ms-excel": [".csv"] }} onReject={() => setError("Fichier refusé : .csv attendu.")}>
          <Group justify="center" mih={120} style={{ pointerEvents: "none" }}>
            <FileUp size={32} />
            <div><Text fw={600}>Déposer le fichier CSV ici ou cliquer pour le choisir</Text>
              <Text size="sm" c="dimmed">Colonnes : name, invoice_date, partner_id/name, product_id/name, price_subtotal, price_total, account_id/code</Text></div>
          </Group>
        </Dropzone>
        {progress !== null && <Progress value={progress} aria-label="Envoi du fichier" />}
        {error && <Alert color="brique" role="alert">{error}</Alert>}
        {result && (
          <Paper p="md">
            <Text fw={600}>Lot {result.batch} : {result.imported} ligne(s) importée(s).</Text>
            {result.errors.length > 0 && <List size="sm" c="var(--lv-brique)" mt={4}>{result.errors.map((e) => <List.Item key={e}>{e}</List.Item>)}</List>}
            {result.preview.length > 0 && (
              <Table mt="sm">
                <Table.Thead><Table.Tr><Table.Th>Facture</Table.Th><Table.Th>Date</Table.Th><Table.Th>Client</Table.Th><Table.Th ta="right">TTC</Table.Th><Table.Th>Compte</Table.Th></Table.Tr></Table.Thead>
                <Table.Tbody>{result.preview.map((r, i) => (
                  <Table.Tr key={i}><Table.Td>{r.invoice_number}</Table.Td><Table.Td className="lv-num">{formatDate(r.invoice_date)}</Table.Td>
                    <Table.Td>{r.partner_name}</Table.Td><Table.Td ta="right"><MoneyText cents={r.amount_ttc_cents} /></Table.Td><Table.Td className="lv-num">{r.account_code}</Table.Td></Table.Tr>
                ))}</Table.Tbody>
              </Table>
            )}
            <Anchor component={AppLink} href={result.url} size="sm" mt="sm" display="inline-block">Voir toutes les lignes du lot</Anchor>
          </Paper>
        )}
        {(data?.items.length ?? 0) > 0 && (
          <>
            <Title order={3} mt="md">Lots importés</Title>
            <Table>
              <Table.Thead><Table.Tr><Table.Th>Lot</Table.Th><Table.Th ta="right">Lignes</Table.Th></Table.Tr></Table.Thead>
              <Table.Tbody>{data!.items.map((b) => (
                <Table.Tr key={b.name}><Table.Td><Anchor component={AppLink} href={b.url} size="sm">{b.name}</Anchor></Table.Td>
                  <Table.Td ta="right" className="lv-num">{b.lines}</Table.Td></Table.Tr>
              ))}</Table.Tbody>
            </Table>
          </>
        )}
      </Stack>
    </>
  );
}

export default writeOnly(OdooImportPage, "Import de lignes Odoo");

// Imports › Relevé OFX : dépôt du fichier pour un compte bancaire ; les doublons sont ignorés,
// les factures d'achat saisies payées par un débit importé sont réglées.
import { useState } from "react";
import { useSearchParams } from "react-router";
import { Alert, Anchor, Group, List, Paper, Progress, Select, Stack, Text } from "@mantine/core";
import { Dropzone } from "@mantine/dropzone";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { FileUp } from "lucide-react";
import { api, ApiError } from "../../api/client";
import { showNotices, type Notice } from "../../api/resources";
import { upload } from "../../api/upload";
import { PageHeader } from "../../components/PageHeader";
import { AppLink } from "../../app/navigation";
import { BANK_ACCOUNTS_KEY, type BankAccount } from "../bank-accounts/types";
import { writeOnly } from "../../components/ReadOnlyPage";

interface Result { imported: number; duplicates: number; errors: string[]; matched: number; settled: number }

function ImportOfxPage() {
  const [search] = useSearchParams();
  const client = useQueryClient();
  const { data } = useQuery({ queryKey: BANK_ACCOUNTS_KEY, queryFn: () => api.get<{ items: BankAccount[] }>("/api/v1/bank-accounts") });
  const accounts = data?.items ?? [];
  const [accountId, setAccountId] = useState<string | null>(search.get("bank_account_id"));
  const chosen = accounts.find((a) => String(a.id) === accountId);
  const [progress, setProgress] = useState<number | null>(null);
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState<string | null>(null);

  const send = async (file: File) => {
    if (!accountId) { setError("Choisissez d'abord le compte bancaire."); return; }
    const form = new FormData();
    form.append("bank_account_id", accountId);
    form.append("ofx_file", file);
    setError(null); setResult(null); setProgress(0);
    try {
      const body = await upload<{ result: Result; notices: Notice[] }>("/api/v1/imports/ofx", form, setProgress);
      setResult(body.result);
      showNotices(body.notices);
      void client.invalidateQueries({ queryKey: BANK_ACCOUNTS_KEY });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "L'import a échoué.");
    } finally {
      setProgress(null);
    }
  };

  return (
    <>
      <PageHeader title="Importer un relevé OFX" description="Les transactions déjà importées sont reconnues et ignorées." />
      <Stack maw={720}>
        <Select label="Compte bancaire" required data={accounts.map((a) => ({ value: String(a.id), label: `${a.label}${a.iban ? ` (${a.iban})` : ""}` }))}
          value={accountId} onChange={setAccountId} placeholder="Choisir un compte" />
        {chosen?.qonto && <Alert color="paille">Ce compte est synchronisé avec Qonto : un import OFX créerait des doublons de source différente.</Alert>}
        <Dropzone onDrop={(files) => files[0] && void send(files[0])} multiple={false} loading={progress !== null}
          disabled={!accountId} accept={{ "application/x-ofx": [".ofx", ".qfx"], "application/octet-stream": [".ofx", ".qfx"] }}
          onReject={() => setError("Fichier refusé : .ofx ou .qfx attendu.")}>
          <Group justify="center" mih={140} style={{ pointerEvents: "none" }}>
            <FileUp size={36} />
            <div><Text fw={600}>Déposer le relevé ici ou cliquer pour le choisir</Text>
              <Text size="sm" c="dimmed">.ofx ou .qfx (OFX 1.x SGML ou 2.x XML)</Text></div>
          </Group>
        </Dropzone>
        {progress !== null && <Progress value={progress} aria-label="Envoi du fichier" />}
        {error && <Alert color="brique" role="alert">{error}</Alert>}
        {result && (
          <Paper p="md">
            <Text fw={600}>{result.imported} transaction(s) importée(s), {result.duplicates} doublon(s) ignoré(s).</Text>
            {result.matched > 0 && <Text size="sm">{result.matched} facture(s) d'achat rattachée(s) à leur paiement, {result.settled} règlement(s) passé(s).</Text>}
            {result.errors.length > 0 && <List size="sm" c="var(--lv-brique)" mt={4}>{result.errors.map((e) => <List.Item key={e}>{e}</List.Item>)}</List>}
            {chosen && <Group mt="sm"><Anchor component={AppLink} href={`/reconciliation/?bank_account_id=${chosen.id}`}>Rapprocher les transactions</Anchor>
              <Anchor component={AppLink} href={`/bank-accounts/${chosen.id}/transactions`}>Voir le compte</Anchor></Group>}
          </Paper>
        )}
      </Stack>
    </>
  );
}

export default writeOnly(ImportOfxPage, "Importer un relevé OFX", { href: "/bank-accounts/", label: "Voir les comptes bancaires." });

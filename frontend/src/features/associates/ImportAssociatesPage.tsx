// Associés › Import : reprise des associés, de leurs parts et des soldes des comptes courants
// depuis un CSV (export Ekylibre ou tableur). Analyse sans rien écrire, puis import tout ou rien.
import { useState } from "react";
import { Alert, Anchor, Button, FileInput, Group, List, Paper, Select, Stack, Table, Text } from "@mantine/core";
import { useQueryClient } from "@tanstack/react-query";
import { ApiError } from "../../api/client";
import { showNotices, type Notice } from "../../api/resources";
import { useCan } from "../../api/session";
import { upload } from "../../api/upload";
import { useGoTo } from "../../app/navigation";
import { MoneyText } from "../../components/Money";
import { PageHeader } from "../../components/PageHeader";
import { StatusBadge } from "../../components/StatusBadge";
import { formatDate } from "../../lib/format";
import type { Option } from "../purchases/types";
import { ASSOCIATES_KEY, NATURES, type Nature } from "./types";

export interface Analysis {
  ok: boolean; errors: string[]; line_errors: number; needs_counterpart: boolean; counterparts: Option[];
  rows: { line: number; name: string; errors: string[] }[];
  associates: { name: string; action: "create" | "reuse"; account_code: string; parts: Record<Nature, number>;
    balance_cents: number; balance_action: "entry" | "ignored" | null; rate: number | null }[];
  movements: { date: string; nominal_cents: number | null; parts: number }[];
}

const COLUMNS = "nom ; compte ; nature ; parts ; date ; nominal ; solde ; taux";

export default function ImportAssociatesPage() {
  const can = useCan();
  const client = useQueryClient();
  const goTo = useGoTo();
  const [file, setFile] = useState<File | null>(null);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [counterpart, setCounterpart] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const send = async <T,>(url: string, extra: Record<string, string> = {}) => {
    const form = new FormData();
    form.append("file", file as File);
    for (const [k, v] of Object.entries(extra)) form.append(k, v);
    return upload<T>(url, form);
  };
  const analyse = async (chosen: File | null) => {
    setFile(chosen); setAnalysis(null); setError(null); setCounterpart(null);
    if (!chosen) return;
    const form = new FormData();
    form.append("file", chosen);
    setBusy(true);
    try {
      setAnalysis(await upload<Analysis>("/api/v1/associates/import/preview", form));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Analyse impossible.");
    } finally {
      setBusy(false);
    }
  };
  const run = async () => {
    setBusy(true); setError(null);
    try {
      const body = await send<{ notices: Notice[] }>("/api/v1/associates/import", counterpart ? { counterpart_code: counterpart } : {});
      showNotices(body.notices);
      void client.invalidateQueries({ queryKey: ASSOCIATES_KEY });
      goTo("/associates/");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Import impossible.");
    } finally {
      setBusy(false);
    }
  };

  if (!can.instanceAdmin) {
    return <><PageHeader title="Importer des associés" /><Alert color="ardoise">Réservé à l'administrateur de l'instance.</Alert></>;
  }
  const rowErrors = analysis?.rows.filter((r) => r.errors.length) ?? [];
  return (
    <>
      <PageHeader title="Importer des associés" description="Associés, parts et soldes d'ouverture des comptes courants, depuis un fichier CSV." />
      <Stack maw={980}>
        <Paper withBorder p="md">
          <Text size="sm">Une ligne par associé et par nature de parts (un associé démembré a plusieurs lignes). Colonnes :{" "}
            <code>{COLUMNS}</code>. Nature : PP, US ou NP ; solde : créditeur positif (la société doit à l'associé) ; séparateur
            « ; » ou « , ». <Anchor href="/api/v1/associates/import/template" size="sm">Télécharger le modèle</Anchor>.</Text>
          <FileInput mt="sm" label="Fichier CSV" placeholder="associes.csv" accept=".csv,text/csv" clearable value={file}
            onChange={(f) => void analyse(f)} disabled={busy} />
        </Paper>
        {error && <Alert color="brique" role="alert">{error}</Alert>}
        {analysis && (
          <>
            {(analysis.errors.length > 0 || rowErrors.length > 0) && (
              <Alert color="brique" title="Rien ne sera importé tant que ces erreurs subsistent">
                <List size="sm">
                  {analysis.errors.map((e) => <List.Item key={e}>{e}</List.Item>)}
                  {rowErrors.map((r) => <List.Item key={r.line}>Ligne {r.line} ({r.name || "sans nom"}) : {r.errors.join(" ; ")}</List.Item>)}
                </List>
              </Alert>
            )}
            <Table>
              <Table.Thead><Table.Tr><Table.Th>Associé</Table.Th><Table.Th>Compte courant</Table.Th>
                {NATURES.map((n) => <Table.Th key={n.value} ta="right">{n.short}</Table.Th>)}
                <Table.Th ta="right">Solde d'ouverture</Table.Th><Table.Th ta="right">Taux</Table.Th></Table.Tr></Table.Thead>
              <Table.Tbody>
                {analysis.associates.map((a) => (
                  <Table.Tr key={a.name}>
                    <Table.Td><Group gap={6}>{a.name}<StatusBadge tone={a.action === "create" ? "info" : "neutral"}>
                      {a.action === "create" ? "nouveau" : "existant"}</StatusBadge></Group></Table.Td>
                    <Table.Td className="lv-num">{a.account_code}</Table.Td>
                    {NATURES.map((n) => <Table.Td key={n.value} ta="right" className="lv-num">{a.parts[n.value] || "—"}</Table.Td>)}
                    <Table.Td ta="right">{a.balance_cents ? <>
                      <MoneyText cents={a.balance_cents} size="sm" />
                      {a.balance_action === "ignored" && <Text size="xs" c="dimmed">ignoré : compte déjà mouvementé</Text>}
                    </> : "—"}</Table.Td>
                    <Table.Td ta="right">{a.rate !== null ? `${a.rate.toLocaleString("fr-FR")} %` : ""}</Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
            <Text size="sm">Registre : {analysis.movements.map((m) => `reprise du ${formatDate(m.date)} (${m.parts.toLocaleString("fr-FR")} parts)`).join(", ")}.</Text>
            {analysis.needs_counterpart && (
              <Select label="Compte de contrepartie des soldes d'ouverture" required searchable w={420} data={analysis.counterparts}
                value={counterpart} onChange={setCounterpart}
                description="Les soldes sont passés au journal AN à la date de reprise, contre ce compte (ex. compte d'attente, report à nouveau)." />
            )}
            <Group>
              <Button loading={busy} disabled={!analysis.ok || (analysis.needs_counterpart && !counterpart)} onClick={() => void run()}>
                Importer</Button>
            </Group>
          </>
        )}
      </Stack>
    </>
  );
}

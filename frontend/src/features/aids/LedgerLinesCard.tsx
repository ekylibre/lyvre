// Aides et subventions › aides comptabilisées sans dossier (essai de l'interface, 09/11/2026) : lignes 74 de l'année
// (hors 741 et 747) qu'aucun versement ne couvre, typiquement une reprise d'historique (FEC). On les rattache à un
// dossier existant ou on crée le dossier ; aucune écriture n'est passée, les versements pointent les lignes.
import { useState } from "react";
import { Alert, Button, Checkbox, Group, Paper, Select, Stack, Table, Text, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { ApiError, api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { AppLink } from "../../app/navigation";
import { MoneyText } from "../../components/Money";
import { formatDate } from "../../lib/format";

export interface LedgerLine {
  id: number; entry_id: number; reference: string | null; date: string; label: string; amount_cents: number;
  account: { id: number; code: string; label: string };
}
interface Scheme { key: string; label: string; accounts: { code: string }[] }

export function LedgerLinesCard({ lines, campaign, aids, canWrite, invalidate }: {
  lines: LedgerLine[]; campaign: number; aids: { id: number; label: string; account: { code: string } }[];
  canWrite: boolean; invalidate: unknown[][];
}) {
  const [selected, setSelected] = useState<number[]>([]);
  const [schemeKey, setSchemeKey] = useState<string | null>(null);
  const [aidId, setAidId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { data: schemes } = useQuery({ queryKey: ["aids", "schemes"], enabled: canWrite && lines.length > 0,
    queryFn: () => api.get<{ items: Scheme[] }>("/api/v1/aids/schemes") });
  // Un versement de début d'année solde souvent la campagne précédente (DPB de janvier) : ses dossiers sont proposés.
  const { data: previous } = useQuery({ queryKey: ["aids", "list", String(campaign - 1)], enabled: canWrite && lines.length > 0,
    queryFn: () => api.get<{ items: { id: number; label: string; campaign: number; account: { code: string } }[] }>(
      `/api/v1/aids?campaign=${campaign - 1}`) });
  const targets = [...aids.map((a) => ({ ...a, campaign })), ...(previous?.items ?? [])];
  const opts = { invalidate };
  const create = useAction((body: object) => api.post<{ notices: Notice[] }>("/api/v1/aids/from-ledger", body), opts);
  const link = useAction((v: { id: string; line_ids: number[] }) =>
    api.post<{ notices: Notice[] }>(`/api/v1/aids/${v.id}/ledger-lines`, { line_ids: v.line_ids }), opts);
  if (lines.length === 0) return null;
  const chosen = lines.filter((l) => selected.includes(l.id));
  const account = chosen[0]?.account.code;
  const oneAccount = chosen.length > 0 && chosen.every((l) => l.account.code === account);
  // Dispositifs dont le compte prolonge celui des écritures (745 → 7451…), sinon tous.
  const matching = (schemes?.items ?? []).filter((s) => account && s.accounts.some((a) => a.code.startsWith(account)));
  const schemeOptions = (matching.length ? matching : schemes?.items ?? []).map((s) => ({ value: s.key, label: s.label }));
  const total = lines.reduce((sum, l) => sum + l.amount_cents, 0);
  const done = () => { setSelected([]); setSchemeKey(null); setAidId(null); };
  const fail = (e: unknown) => setError(e instanceof ApiError ? e.message : "Enregistrement impossible.");
  const toggle = (id: number) => setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
  return (
    <Paper withBorder p="md" mb="lg">
      <Stack gap="sm">
        <Title order={4}>Aides comptabilisées sans dossier — {campaign}</Title>
        <Text size="sm" c="dimmed">
          {lines.length} écriture{lines.length > 1 ? "s" : ""} d'aides datée{lines.length > 1 ? "s" : ""} de {campaign} (comptes 74
          hors 741 et 747) pour <MoneyText cents={total} /> : aucun dossier ne les couvre. Rattachez-les pour suivre le
          reste à percevoir ; aucune écriture n'est passée.</Text>
        <Table>
          <Table.Thead><Table.Tr>{canWrite && <Table.Th />}<Table.Th>Date</Table.Th><Table.Th>Compte</Table.Th>
            <Table.Th>Libellé</Table.Th><Table.Th ta="right">Montant</Table.Th></Table.Tr></Table.Thead>
          <Table.Tbody>
            {lines.map((l) => (
              <Table.Tr key={l.id}>
                {canWrite && <Table.Td><Checkbox aria-label={`Choisir l'écriture du ${formatDate(l.date)}`}
                  checked={selected.includes(l.id)} onChange={() => toggle(l.id)} /></Table.Td>}
                <Table.Td><span className="lv-num">{formatDate(l.date)}</span></Table.Td>
                <Table.Td><span className="lv-num">{l.account.code}</span></Table.Td>
                <Table.Td><AppLink href={`/entries/${l.entry_id}`}>{l.label}</AppLink></Table.Td>
                <Table.Td ta="right"><MoneyText cents={l.amount_cents} /></Table.Td>
              </Table.Tr>))}
          </Table.Tbody>
        </Table>
        {canWrite && chosen.length > 0 && (
          <Stack gap="xs">
            {!oneAccount && <Alert color="paille">Les écritures choisies portent sur plusieurs comptes : un dossier par compte.</Alert>}
            <Group align="end">
              <Select label="Dispositif du nouveau dossier" w={360} searchable data={schemeOptions} value={schemeKey}
                onChange={setSchemeKey} disabled={!oneAccount} />
              <Button disabled={!schemeKey || !oneAccount} loading={create.isPending}
                onClick={() => { setError(null); create.mutateAsync({ scheme: schemeKey, campaign, line_ids: selected }).then(done, fail); }}>
                Créer le dossier</Button>
            </Group>
            {targets.length > 0 && (
              <Group align="end">
                <Select label="Ou rattacher à un dossier" w={360} value={aidId} onChange={setAidId}
                  data={targets.map((a) => ({ value: String(a.id), label: `${a.label} ${a.campaign} (${a.account.code})` }))} />
                <Button variant="light" disabled={!aidId} loading={link.isPending}
                  onClick={() => { setError(null); link.mutateAsync({ id: aidId!, line_ids: selected }).then(done, fail); }}>
                  Rattacher</Button>
              </Group>)}
            {error && <Alert color="brique">{error}</Alert>}
          </Stack>)}
      </Stack>
    </Paper>
  );
}

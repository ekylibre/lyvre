// Relevés de compte (lots RQ1, RQ3) : mois de l'exercice en cours (récupérés ou manquants) et relevés
// stockés, PDF dans un nouvel onglet ; récupération Qonto au clic, ou dépôt d'un PDF pour un compte hors
// Qonto (droit d'écriture). Aucune suppression.
import { useState } from "react";
import { Alert, Anchor, Button, FileInput, Group, Paper, Select, Stack, Table, Text } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../api/client";
import { showNotices, useAction, type Notice } from "../../api/resources";
import { upload } from "../../api/upload";
import { Can } from "../../components/Can";
import { FormModal } from "../../components/FormModal";
import { StatusBadge } from "../../components/StatusBadge";
import { formatDateTime } from "../../lib/format";
import { BANK_ACCOUNTS_KEY } from "./types";

export interface Statement {
  id: number; source: "qonto" | "upload"; file_name: string | null; file_size: number;
  fetched_at: string | null; replaced_at: string | null; url: string;
}
export interface StatementsList {
  items: { period: string; statement: Statement | null }[];
  fiscal_year: { id: number; label: string } | null;
  qonto: { enabled: boolean; available: boolean; message: string | null } | null;
  /** Mois déposables (AAAA-MM), vide pour un compte Qonto. */
  upload_months: string[];
}

/** « 2026-07 » → « juillet 2026 ». */
export function periodLabel(period: string): string {
  const [year, month] = period.split("-").map(Number);
  return new Date(year, month - 1, 1).toLocaleDateString("fr-FR", { month: "long", year: "numeric" });
}

/** Dépôt d'un relevé PDF pour un mois (remplace celui du mois). */
function UploadModal({ bankAccountId, months, opened, onClose }: {
  bankAccountId: number; months: string[]; opened: boolean; onClose: () => void;
}) {
  const client = useQueryClient();
  const [period, setPeriod] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const send = useMutation({
    mutationFn: () => {
      const form = new FormData();
      form.append("period", period ?? "");
      if (file) form.append("file", file);
      return upload<{ notices: Notice[] }>(`/api/v1/bank-accounts/${bankAccountId}/statements`, form);
    },
    onSuccess: (data) => {
      showNotices(data.notices);
      void client.invalidateQueries({ queryKey: [...BANK_ACCOUNTS_KEY, bankAccountId, "statements"] });
      close();
    },
  });
  const close = () => { setPeriod(null); setFile(null); send.reset(); onClose(); };
  return (
    <FormModal opened={opened} onClose={close} title="Déposer un relevé de compte">
      <Stack>
        <Select label="Mois" data={months.map((m) => ({ value: m, label: periodLabel(m) }))} value={period}
          onChange={setPeriod} searchable data-autofocus />
        <FileInput label="Relevé (PDF)" placeholder="PDF de la banque, 10 Mo au plus" accept="application/pdf"
          value={file} onChange={setFile} clearable />
        <Text size="xs" c="dimmed">Un relevé déjà déposé pour ce mois est remplacé.</Text>
        {send.error && <Alert color="brique" role="alert">{send.error.message}</Alert>}
        <Group justify="flex-end">
          <Button variant="default" onClick={close}>Annuler</Button>
          <Button disabled={!period || !file} loading={send.isPending} onClick={() => send.mutate()}>Déposer</Button>
        </Group>
      </Stack>
    </FormModal>
  );
}

export function StatementsCard({ bankAccountId }: { bankAccountId: number }) {
  const [uploading, setUploading] = useState(false);
  const key = [...BANK_ACCOUNTS_KEY, bankAccountId, "statements"];
  const { data } = useQuery({ queryKey: key,
    queryFn: () => api.get<StatementsList>(`/api/v1/bank-accounts/${bankAccountId}/statements`) });
  const fetch = useAction(() => api.post<{ notices: Notice[] }>(`/api/v1/bank-accounts/${bankAccountId}/statements/fetch`),
    { invalidate: [key] });
  if (!data) return null;
  const qonto = data.qonto;
  const canUpload = data.upload_months.length > 0;
  // Qonto coupé et rien à déposer ni à montrer : pas de carte.
  if (!qonto?.enabled && !canUpload && !data.items.some((i) => i.statement)) return null;
  const missing = data.items.filter((i) => !i.statement).length;
  return (
    <Paper p="md" mb="md">
      <Group justify="space-between" align="flex-start" mb="xs">
        <div>
          <Text fw={600}>Relevés de compte</Text>
          <Text size="sm" c="dimmed">
            {data.fiscal_year ? `Exercice ${data.fiscal_year.label}` : "Aucun exercice en cours"}
            {missing > 0 && ` — ${missing} mois sans relevé`}</Text>
        </div>
        {qonto?.enabled && <Can><Button variant="default" loading={fetch.isPending} disabled={!qonto.available}
          title={qonto.available ? "Télécharge depuis Qonto les relevés des mois terminés de l'exercice" : qonto.message ?? undefined}
          onClick={() => fetch.mutate(undefined)}>Récupérer les relevés</Button></Can>}
        {canUpload && <Can><Button variant="default" onClick={() => setUploading(true)}>Déposer un relevé</Button></Can>}
      </Group>
      {data.items.length === 0 ? <Text size="sm" c="dimmed">Aucun mois terminé dans l'exercice.</Text> : (
        <Table>
          <Table.Thead><Table.Tr><Table.Th>Mois</Table.Th><Table.Th>Relevé</Table.Th><Table.Th>Obtenu le</Table.Th>
            <Table.Th ta="right">Taille</Table.Th></Table.Tr></Table.Thead>
          <Table.Tbody>
            {data.items.map(({ period, statement }) => (
              <Table.Tr key={period}>
                <Table.Td>{periodLabel(period)}</Table.Td>
                <Table.Td>{statement
                  ? <Group gap={6}><Anchor href={statement.url} target="_blank" rel="noopener" size="sm">
                      {statement.file_name || `Relevé ${period}`}</Anchor>
                      <StatusBadge tone="info">{statement.source === "qonto" ? "Qonto" : "Déposé"}</StatusBadge>
                      {statement.replaced_at && <StatusBadge tone="neutral">Remplacé</StatusBadge>}</Group>
                  : <StatusBadge tone="todo">Manquant</StatusBadge>}</Table.Td>
                <Table.Td className="lv-num">{statement ? formatDateTime(statement.replaced_at ?? statement.fetched_at) : "—"}</Table.Td>
                <Table.Td ta="right" className="lv-num">{statement ? `${Math.max(1, Math.round(statement.file_size / 1024))} Ko` : ""}</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}
      {canUpload && <UploadModal bankAccountId={bankAccountId} months={data.upload_months} opened={uploading}
        onClose={() => setUploading(false)} />}
    </Paper>
  );
}

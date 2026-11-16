// Compta › Immobilisations, biens vivants (lot AG5.c) : registre des abattages sanitaires — indemnité, valeur nette des
// animaux abattus, reconstitution du cheptel dans les 2 ans (exonération et réintégration calculées en AG6).
import { useState } from "react";
import { Alert, Button, Group, Paper, Table, Text, TextInput } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { ApiError, api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { useCan } from "../../api/session";
import { MoneyInput, MoneyText } from "../../components/Money";
import { formatDate } from "../../lib/format";

interface Reinvestment { id: number; label: string; on: string; indemnity_cents: number; book_value_cents: number; gain_cents: number;
  deadline: string; reinvested_cents: number; reinvested_on: string | null; remaining_cents: number }
interface Exit { id: number; kind: string; reinvestment: Reinvestment | null }

export function ReinvestmentsPanel() {
  const can = useCan();
  const { data } = useQuery({ queryKey: ["assets", "living-exits"], queryFn: () => api.get<{ items: Exit[] }>("/api/v1/living-exits") });
  const [drafts, setDrafts] = useState<Record<number, { amount: number | null; on: string }>>({});
  const [error, setError] = useState<string | null>(null);
  const save = useAction((v: { id: number; body: object }) => api.put<{ notices: Notice[] }>(`/api/v1/living-reinvestments/${v.id}`, v.body),
    { invalidate: [["assets"]] });
  const rows = (data?.items ?? []).map((e) => e.reinvestment).filter((r): r is Reinvestment => !!r);
  if (rows.length === 0) return null;
  return (
    <Paper withBorder p="sm" mt="lg">
      <Text fw={600} size="sm" mb={4}>Abattages sanitaires : reconstitution du cheptel</Text>
      <Text size="xs" c="dimmed" mb="xs">Indemnité exonérée si elle est réinvestie dans la reconstitution du cheptel dans les 2 ans
        (art. 75-0 D, à vérifier) ; la part non réinvestie sera réintégrée (AG6).</Text>
      <Table>
        <Table.Tbody>
          {rows.map((r) => {
            const d = drafts[r.id] ?? { amount: r.reinvested_cents, on: r.reinvested_on ?? "" };
            return (
              <Table.Tr key={r.id}>
                <Table.Td>{r.label}<Text size="xs" c="dimmed">abattage du {formatDate(r.on)} · avant le {formatDate(r.deadline)}</Text></Table.Td>
                <Table.Td><Text size="xs">indemnité <MoneyText cents={r.indemnity_cents} /> · valeur nette <MoneyText cents={r.book_value_cents} /></Text></Table.Td>
                <Table.Td>{can.write ? <MoneyInput aria-label={`Réinvesti ${r.label}`} w={120} value={d.amount}
                  onChange={(v) => setDrafts({ ...drafts, [r.id]: { ...d, amount: v } })} /> : <MoneyText cents={r.reinvested_cents} />}</Table.Td>
                <Table.Td>{can.write ? <TextInput aria-label={`Date ${r.label}`} type="date" w={140} value={d.on}
                  onChange={(e) => setDrafts({ ...drafts, [r.id]: { ...d, on: e.currentTarget.value } })} /> : formatDate(r.reinvested_on ?? "")}</Table.Td>
                <Table.Td>{can.write && <Group gap={4}><Button size="compact-sm" variant="light" onClick={() => {
                  setError(null);
                  save.mutateAsync({ id: r.id, body: { reinvested_cents: d.amount ?? 0, reinvested_on: d.on || null } })
                    .catch((e) => setError(e instanceof ApiError ? e.message : "Enregistrement impossible."));
                }}>Enregistrer</Button></Group>}</Table.Td>
              </Table.Tr>);
          })}
        </Table.Tbody>
      </Table>
      {error && <Alert color="brique" mt="xs">{error}</Alert>}
    </Paper>
  );
}

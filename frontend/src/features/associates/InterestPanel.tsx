// Clôture, étape « Écritures d'inventaire » : intérêts des comptes courants d'associés (module
// « Associés »). Calcul jour par jour sur le solde créditeur, au taux de l'associé ou de la
// structure ; écritures 6615 / 455 au dernier jour de l'exercice, remplacées si on relance.
import { Alert, Anchor, Button, Paper, Stack, Table, Text } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { useCan } from "../../api/session";
import { AppLink } from "../../app/navigation";
import { MoneyText } from "../../components/Money";
import { formatEuros } from "../../lib/format";
import { ASSOCIATES_KEY } from "./types";

interface Preview {
  rows: { associate_id: number; name: string; account_code: string; rate: string; average_balance_cents: number; interest_cents: number }[];
  total_cents: number; entries: { id: number; reference: string; amount_cents: number }[];
}

export function InterestPanel({ fyId, open }: { fyId: number; open: boolean }) {
  const can = useCan();
  const key = [...ASSOCIATES_KEY, "interest", fyId];
  const { data } = useQuery({ queryKey: key, queryFn: () => api.get<Preview>(`/api/v1/fiscal-years/${fyId}/associate-interest`) });
  const post = useAction(() => api.post<{ notices: Notice[] }>(`/api/v1/fiscal-years/${fyId}/associate-interest`),
    { invalidate: [key, ASSOCIATES_KEY, ["closing", fyId]] });
  if (!data) return null;
  return (
    <Paper withBorder p="sm">
      <Stack gap="xs">
        <Text fw={600}>Intérêts des comptes courants d'associés</Text>
        {!data.rows.length ? <Text size="sm" c="dimmed">Aucun associé.</Text> : (
          <Table>
            <Table.Thead><Table.Tr><Table.Th>Associé</Table.Th><Table.Th ta="right">Taux</Table.Th>
              <Table.Th ta="right">Solde créditeur moyen</Table.Th><Table.Th ta="right">Intérêts</Table.Th></Table.Tr></Table.Thead>
            <Table.Tbody>
              {data.rows.map((r) => (
                <Table.Tr key={r.associate_id}>
                  <Table.Td><AppLink href={`/associates/${r.associate_id}`}>{r.name}</AppLink></Table.Td>
                  <Table.Td ta="right" className="lv-num">{r.rate} %</Table.Td>
                  <Table.Td ta="right"><MoneyText cents={r.average_balance_cents} size="sm" /></Table.Td>
                  <Table.Td ta="right"><MoneyText cents={r.interest_cents} size="sm" /></Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        )}
        <Text size="xs" c="dimmed">Intérêts = Σ des soldes créditeurs de fin de journée × taux / 365. Taux de l'associé, sinon taux de la
          structure (Configuration › Structure) ; 0 % : aucun intérêt.</Text>
        {data.entries.length > 0 && (
          <Alert color="lichen" variant="light">
            Passés : {data.entries.map((e, i) => (
              <span key={e.id}>{i > 0 && ", "}<Anchor component={AppLink} href={`/entries/${e.id}`} size="sm">{e.reference}</Anchor></span>
            ))}. Relancer les remplace.
          </Alert>
        )}
        {open && can.instanceAdmin && (
          <Button variant="default" w="fit-content" loading={post.isPending} disabled={data.total_cents === 0 && !data.entries.length}
            onClick={() => post.mutate(undefined)}>
            {data.entries.length ? "Recalculer les intérêts" : "Passer les intérêts"} ({formatEuros(data.total_cents)})
          </Button>
        )}
      </Stack>
    </Paper>
  );
}

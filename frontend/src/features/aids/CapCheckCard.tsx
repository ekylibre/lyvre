// Compta › Aides et subventions (lot AG3.e, claudedocs/design_aides_pac.md § 7) : aides PAC publiées par l'ASP pour le
// SIREN de l'exploitation (Lexicon, jeu cap_beneficiaries), comparées aux versements rattachés et aux comptes de
// subventions de l'année civile. Information seulement : l'année publiée est une année de paiement de l'UE.
import { Alert, Button, Group, Paper, SimpleGrid, Text } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { useCan } from "../../api/session";
import { MoneyText } from "../../components/Money";
import { formatDateTime } from "../../lib/format";
import { AIDS_KEY } from "./AidsPage";

export interface CapCheck {
  year: number; configured: boolean; siren: string | null; years: number[]; fetched_at: string | null;
  found: boolean | null; paid_cents: number; ledger_cents: number; message: string | null;
  published: { feaga_cents: number; feader_cents: number; cofinanced_cents: number; total_cents: number } | null;
  gap_paid_cents?: number; gap_ledger_cents?: number;
}

export function CapCheckCard({ year }: { year: number }) {
  const can = useCan();
  const key = [...AIDS_KEY, "cap", year];
  const { data } = useQuery({ queryKey: key, queryFn: () => api.get<{ item: CapCheck }>(`/api/v1/aids/cap-check?year=${year}`) });
  const refresh = useAction(() => api.post<{ item: CapCheck; notices: Notice[] }>("/api/v1/aids/cap-check", { year }),
    { invalidate: [[...AIDS_KEY, "cap"]] });
  const c = data?.item;
  if (!c || !c.configured) return null;
  return (
    <Paper withBorder p="md" mt="lg">
      <Group justify="space-between" mb="xs">
        <Text fw={600} size="sm">Montants publiés par l'ASP — {year}</Text>
        {can.write && c.siren && <Button size="xs" variant="subtle" loading={refresh.isPending} onClick={() => refresh.mutate(undefined)}>Relire dans Lexicon</Button>}
      </Group>
      {c.message && <Alert color="paille" mb="xs">{c.message}</Alert>}
      {c.published && (
        <SimpleGrid cols={{ base: 1, sm: 3 }}>
          <div><Text size="xs" c="dimmed">Publié (FEAGA + FEADER + cofinancé)</Text><MoneyText cents={c.published.total_cents} />
            <Text size="xs" c="dimmed">FEAGA <MoneyText cents={c.published.feaga_cents} /> · FEADER <MoneyText cents={c.published.feader_cents} />
              {c.published.cofinanced_cents > 0 && <> · cofinancé <MoneyText cents={c.published.cofinanced_cents} /></>}</Text></div>
          <div><Text size="xs" c="dimmed">Versements rattachés en {year}</Text><MoneyText cents={c.paid_cents} />
            <Text size="xs" c="dimmed">écart <MoneyText cents={c.gap_paid_cents ?? 0} plus /></Text></div>
          <div><Text size="xs" c="dimmed">Comptes 74 et 131 en {year}</Text><MoneyText cents={c.ledger_cents} />
            <Text size="xs" c="dimmed">écart <MoneyText cents={c.gap_ledger_cents ?? 0} plus /></Text></div>
        </SimpleGrid>)}
      <Text size="xs" c="dimmed" mt="xs">Source : ASP, via Lexicon (OSFarm), SIREN {c.siren ?? "non renseigné"}
        {c.fetched_at && `, lu le ${formatDateTime(c.fetched_at)}`}. L'année publiée est une année de paiement de l'Union
        européenne, ni un exercice ni une campagne : un écart n'est pas forcément une erreur. Aides régionales et
        nationales non comprises.</Text>
    </Paper>
  );
}

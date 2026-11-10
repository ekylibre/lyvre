// Immobilisations › immobilisations comptabilisées sans fiche (essai de l'interface, 10/11/2026) : après la reprise
// d'un FEC, le grand livre porte des immobilisations que le registre ignore. Par compte : brut du grand livre et du
// registre, écart, amortissements du grand livre ; « Créer la fiche » ouvre une fiche préremplie (valeur d'origine =
// écart, cumul antérieur = amortissements des à-nouveaux), sans écriture : la date et la durée restent à saisir.
import { Badge, Button, Paper, Stack, Table, Text, Title, Tooltip } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { MoneyText } from "../../components/Money";
import { formatDate } from "../../lib/format";
import type { AssetDraft } from "./AssetForm";

export interface LedgerGap {
  account: { id: number; code: string; label: string };
  ledger_cents: number; register_cents: number; gap_cents: number;
  depreciation_cents: number; opening_depreciation_cents: number; prior_as_of: string;
  depreciation_accounts: string[]; shared_with: string[]; no_depreciation: boolean;
}

export function draftFrom(gap: LedgerGap): AssetDraft {
  const shared = gap.shared_with.length > 0;
  return {
    label: gap.account.label, account_id: String(gap.account.id), acquired_on: gap.prior_as_of,
    acquisition_cents: gap.gap_cents, prior_as_of: gap.prior_as_of,
    // Amortissements communs à plusieurs comptes : la répartition revient à l'utilisateur.
    prior_depreciation_cents: shared || gap.register_cents ? 0 : gap.opening_depreciation_cents,
    notes: `Reprise du grand livre (compte ${gap.account.code}) : date d'acquisition, durée et cumul amorti à vérifier.`,
  };
}

export function LedgerGapsCard({ canWrite, onCreate }: { canWrite: boolean; onCreate: (draft: AssetDraft) => void }) {
  const { data } = useQuery({ queryKey: ["assets", "ledger-gaps"],
    queryFn: () => api.get<{ items: LedgerGap[]; fiscal_year: { label: string; end_date: string } | null }>("/api/v1/assets/ledger-gaps") });
  const items = data?.items ?? [];
  if (!items.length || !data?.fiscal_year) return null;
  const total = items.reduce((sum, g) => sum + g.gap_cents, 0);
  return (
    <Paper withBorder p="md" mb="lg">
      <Stack gap="sm">
        <Title order={4}>Immobilisations comptabilisées sans fiche</Title>
        <Text size="sm" c="dimmed">
          Au {formatDate(data.fiscal_year.end_date)} (exercice {data.fiscal_year.label}), le grand livre porte{" "}
          <MoneyText cents={total} /> d'immobilisations brutes que le registre ne couvre pas. Sans fiche, ni plan
          d'amortissement, ni plus-value à la cession. Créer une fiche ne passe aucune écriture.</Text>
        <Table>
          <Table.Thead><Table.Tr><Table.Th>Compte</Table.Th><Table.Th ta="right">Grand livre</Table.Th>
            <Table.Th ta="right">Registre</Table.Th><Table.Th ta="right">Écart</Table.Th>
            <Table.Th ta="right">Amortissements</Table.Th>{canWrite && <Table.Th />}</Table.Tr></Table.Thead>
          <Table.Tbody>
            {items.map((g) => (
              <Table.Tr key={g.account.id}>
                <Table.Td><Text size="sm"><span className="lv-num">{g.account.code}</span> {g.account.label}</Text>
                  {g.no_depreciation && <Tooltip label="Compte amortissable sans aucun amortissement au grand livre : à vérifier" withArrow>
                    <Badge color="paille" variant="light" size="sm">sans amortissement</Badge></Tooltip>}</Table.Td>
                <Table.Td ta="right"><MoneyText cents={g.ledger_cents} /></Table.Td>
                <Table.Td ta="right"><MoneyText cents={g.register_cents} /></Table.Td>
                <Table.Td ta="right"><MoneyText cents={g.gap_cents} fw={600} /></Table.Td>
                <Table.Td ta="right">{g.depreciation_cents ? <MoneyText cents={g.depreciation_cents} /> : "—"}
                  {g.depreciation_accounts.length > 0 && <Text size="xs" c="dimmed">{g.depreciation_accounts.join(", ")}
                    {g.shared_with.length > 0 && ` (commun avec ${g.shared_with.join(", ")})`}</Text>}</Table.Td>
                {canWrite && <Table.Td ta="right"><Button size="xs" variant="light" onClick={() => onCreate(draftFrom(g))}>
                  Créer la fiche</Button></Table.Td>}
              </Table.Tr>))}
          </Table.Tbody>
        </Table>
      </Stack>
    </Paper>
  );
}

// Tableau d'un état (bilan, compte de résultat) : sections, lignes indentées, totaux,
// résultats ; colonnes N et N-1, de largeur fixe et sans retour à la ligne (le libellé se replie) :
// actif et passif tiennent côte à côte dans la largeur de page. Actif : colonnes Brut et Amortissements quand les
// lignes d'immobilisations les portent (`gross`, `depreciation`), la colonne N donnant alors le net.
import { Paper, Table, Text } from "@mantine/core";
import { MoneyText } from "../../components/Money";

export interface StatementLine {
  kind: "section" | "subhead" | "row" | "total" | "result";
  label: string; indent?: number; n?: number | null; p?: number | null;
  /** Lignes d'immobilisations : brut et amortissements (positif), `n` étant le net. */
  gross?: number; depreciation?: number;
  /** Ligne globale des amortissements : reste non rapproché d'une ligne (masquée à zéro). */
  unallocated?: boolean;
}

function Amount({ cents, strong }: { cents: number | null | undefined; strong?: boolean }) {
  if (cents === null || cents === undefined) return null;
  return <MoneyText cents={cents} fw={strong ? 600 : undefined} />;
}

const AMOUNT = { width: 116, whiteSpace: "nowrap" } as const;

export function StatementTable({ title, lines, nLabel, pLabel, showPrevious }: {
  title: string; lines: StatementLine[]; nLabel: string; pLabel: string; showPrevious: boolean;
}) {
  const split = lines.some((l) => l.gross !== undefined);
  const shown = lines.filter((l) => !(l.unallocated && !l.n && !l.p));
  const span = 2 + (showPrevious ? 1 : 0) + (split ? 2 : 0);
  return (
    <Paper p={0} style={{ overflowX: "auto" }}>
      <Table verticalSpacing={6} style={{ minWidth: split ? 560 : 440 }}>
        <Table.Thead bg="var(--lv-sauge)">
          <Table.Tr><Table.Th>{title}</Table.Th>
            {split && <><Table.Th ta="right" style={AMOUNT}>Brut</Table.Th><Table.Th ta="right" style={AMOUNT}>Amort. et dépréc.</Table.Th></>}
            <Table.Th ta="right" style={AMOUNT}>{nLabel}</Table.Th>
            {showPrevious && <Table.Th ta="right" style={AMOUNT}>{pLabel}</Table.Th>}</Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {shown.map((line, i) => {
            if (line.kind === "section") {
              return <Table.Tr key={i} bg="var(--lv-surface-sunken)"><Table.Td colSpan={span}>
                <Text fw={700} size="sm" tt="uppercase" style={{ letterSpacing: "0.06em" }}>{line.label}</Text></Table.Td></Table.Tr>;
            }
            const strong = line.kind === "total" || line.kind === "result";
            const bg = line.kind === "result" ? "var(--lv-sauge)" : undefined;
            return (
              <Table.Tr key={i} bg={bg}>
                <Table.Td pl={8 + (line.indent ?? 0) * 16}>
                  <Text size="sm" fw={strong || line.kind === "subhead" ? 600 : 400} fs={line.label.startsWith("dont ") ? "italic" : undefined}>{line.label}</Text>
                </Table.Td>
                {split && <><Table.Td ta="right" style={AMOUNT}><Amount cents={line.gross} /></Table.Td>
                  <Table.Td ta="right" style={AMOUNT}>{line.depreciation ? <Amount cents={line.depreciation} /> : null}</Table.Td></>}
                <Table.Td ta="right" style={AMOUNT}><Amount cents={line.n} strong={strong} /></Table.Td>
                {showPrevious && <Table.Td ta="right" c="dimmed" style={AMOUNT}><Amount cents={line.p} strong={strong} /></Table.Td>}
              </Table.Tr>
            );
          })}
        </Table.Tbody>
      </Table>
    </Paper>
  );
}

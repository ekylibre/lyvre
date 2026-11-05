// Écriture de stock à la clôture (lot AG4.d, claudedocs/design_inventaire_agricole.md § 8) : annulation du stock
// initial et constatation du stock final, dépréciations, au dernier jour de l'exercice, sans extourne. Passer,
// repasser, annuler tant que l'exercice est ouvert ; export XLSX de l'état d'inventaire.
import { useState } from "react";
import { Alert, Anchor, Badge, Button, Group, Paper, Text } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { ApiError, api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { useCan } from "../../api/session";
import { AppLink } from "../../app/navigation";
import { MoneyText } from "../../components/Money";

export interface StockEntryStatus {
  entry: { id: number; reference: string; validated: boolean } | null; stale: boolean; problems: string[];
  opening_cents: number; final_cents: number; variation_cents: number; depreciation_cents: number; lines: number;
}

export function StockEntryBar({ fyId, status, editable, invalidate, withLink = false }: {
  fyId: number; status: StockEntryStatus; editable: boolean; invalidate: unknown[][]; withLink?: boolean;
}) {
  const can = useCan();
  const [error, setError] = useState<string | null>(null);
  const opts = { invalidate };
  const post = useAction(() => api.post<{ notices: Notice[] }>(`/api/v1/fiscal-years/${fyId}/stock/entry`), opts);
  const cancel = useAction(() => api.delete<{ notices: Notice[] }>(`/api/v1/fiscal-years/${fyId}/stock/entry`), opts);
  const run = (p: Promise<unknown>) => { setError(null); p.catch((e) => setError(e instanceof ApiError ? e.message : "Action impossible.")); };
  const writable = can.write && editable;
  return (
    <Paper withBorder p="sm" mb="md">
      <Group justify="space-between" align="start">
        <div>
          <Group gap="xs">
            <Text fw={600} size="sm">Écriture de stock</Text>
            {status.entry ? <Badge color={status.stale ? "yellow" : "green"} variant="light">{status.stale ? "à repasser" : "passée"}</Badge>
              : <Badge color="gray" variant="light">non passée</Badge>}
            {status.entry && <Anchor component={AppLink} href={`/entries/${status.entry.id}`} size="sm">{status.entry.reference}</Anchor>}
          </Group>
          <Text size="sm">Stock initial <MoneyText cents={status.opening_cents} /> · stock final <MoneyText cents={status.final_cents} /> ·
            variation <MoneyText cents={status.variation_cents} plus />{status.depreciation_cents > 0 && <> · dépréciations <MoneyText cents={status.depreciation_cents} /></>}</Text>
          <Text size="xs" c="dimmed">Au dernier jour de l'exercice : annulation du stock initial, constatation du stock final, sans extourne à l'ouverture.</Text>
        </div>
        <Group gap="xs">
          {withLink && <Button size="xs" variant="default" component={AppLink} href={`/inventory/?fiscal_year=${fyId}`}>Inventaire</Button>}
          <Button size="xs" variant="default" component="a" href={`/fiscal-years/${fyId}/stock.xlsx`}>XLSX</Button>
          {writable && <Button size="xs" loading={post.isPending} disabled={status.problems.length > 0 || (status.lines === 0 && status.opening_cents === 0)}
            onClick={() => run(post.mutateAsync(undefined))}>{status.entry ? "Repasser l'écriture" : "Passer l'écriture"}</Button>}
          {writable && status.entry && !status.entry.validated && <Button size="xs" variant="subtle" color="brique"
            onClick={() => run(cancel.mutateAsync(undefined))}>Annuler</Button>}
        </Group>
      </Group>
      {status.problems.map((p) => <Text key={p} size="xs" c="var(--lv-brique-ink)">{p}</Text>)}
      {error && <Alert color="brique" mt="xs">{error}</Alert>}
    </Paper>
  );
}

/** Clôture › Inventaire : panneau « Stocks » (exploitation agricole au réel). */
export function ClosingStockPanel({ fyId, editable }: { fyId: number; editable: boolean }) {
  const { data } = useQuery({ queryKey: ["stock", fyId], retry: false,
    queryFn: () => api.get<{ entry: StockEntryStatus }>(`/api/v1/fiscal-years/${fyId}/stock`) });
  if (!data) return null;
  return <StockEntryBar fyId={fyId} status={data.entry} editable={editable} invalidate={[["stock"], ["closing", fyId]]} withLink />;
}

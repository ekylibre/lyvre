// Tiers › Règles de catégorisation › « Proposer depuis un mois » : règles déduites des transactions du
// mois réglées par une facture (achat, vente) ou rapprochées d'une écriture saisie ; créer les nouvelles
// et recréer celles dont le tiers ou le compte a changé (app/services/rule_suggestions.py).
import { useEffect, useState } from "react";
import { Alert, Button, Center, Checkbox, Group, Loader, Stack, Table, Text, TextInput } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { StatusBadge, type Tone } from "../../components/StatusBadge";

export interface Suggestion {
  pattern: string; status: "new" | "update" | "identical" | "conflict" | "too_short"; reason: string; creatable: boolean;
  entity: string | null; account_code: string | null; accounts: string[]; count: number; sources: Record<string, number>;
  examples: string[]; rule: { id: number; name: string; account_code: string | null; entity_name: string | null } | null;
  shadowed_by: { id: number; name: string } | null;
}

const STATUS: Record<Suggestion["status"], [string, Tone]> = {
  new: ["À créer", "todo"], update: ["À recréer", "info"], identical: ["Déjà en place", "ok"],
  conflict: ["Ambigu", "gap"], too_short: ["Motif trop court", "neutral"],
};

function previousMonth(): string {
  const d = new Date();
  d.setDate(1);
  d.setMonth(d.getMonth() - 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export function RuleSuggestions({ invalidate, onDone }: { invalidate: unknown[][]; onDone: () => void }) {
  const [period, setPeriod] = useState(previousMonth());
  const valid = /^\d{4}-\d{2}$/.test(period);
  const { data, isFetching } = useQuery({ queryKey: ["rules", "suggestions", period], enabled: valid,
    queryFn: () => api.get<{ items: Suggestion[] }>(`/api/v1/rules/suggestions?period=${period}`) });
  const [chosen, setChosen] = useState<Set<string>>(new Set());
  useEffect(() => {  // par défaut : toutes les règles à créer ou à recréer
    setChosen(new Set((data?.items ?? []).filter((s) => s.creatable).map((s) => s.pattern)));
  }, [data]);
  const save = useAction(() => api.post<{ notices: Notice[] }>("/api/v1/rules/suggestions",
    { period, patterns: [...chosen] }), { invalidate });
  const toggle = (pattern: string) => setChosen((current) => {
    const next = new Set(current);
    if (next.has(pattern)) next.delete(pattern); else next.add(pattern);
    return next;
  });
  const items = data?.items ?? [];
  return (
    <Stack>
      <Text size="sm">Lyvre part des transactions du mois réglées par une facture (achat ou vente) ou rapprochées d'une
        écriture saisie, et propose une règle par libellé : « le libellé contient … » → tiers et compte. Les règles ne
        sont pas appliquées tout de suite : « Appliquer les règles » s'en charge.</Text>
      <TextInput type="month" label="Mois" w={200} value={period} onChange={(e) => setPeriod(e.currentTarget.value)} />
      {!valid ? null : isFetching && !data ? <Center h={120}><Loader /></Center> : items.length === 0 ? (
        <Alert color="paille">Aucune transaction réglée ou catégorisée à la main sur ce mois.</Alert>
      ) : (
        <Table>
          <Table.Thead><Table.Tr><Table.Th w={36} /><Table.Th>Libellé contient</Table.Th><Table.Th>Tiers</Table.Th>
            <Table.Th>Compte</Table.Th><Table.Th>D'après</Table.Th><Table.Th>Statut</Table.Th></Table.Tr></Table.Thead>
          <Table.Tbody>
            {items.map((s) => (
              <Table.Tr key={s.pattern}>
                <Table.Td><Checkbox aria-label={`Retenir ${s.pattern}`} disabled={!s.creatable}
                  checked={chosen.has(s.pattern)} onChange={() => toggle(s.pattern)} /></Table.Td>
                <Table.Td><Text size="sm" className="lv-num">{s.pattern}</Text>
                  <Text size="xs" c="dimmed">{s.examples.join(" · ")}</Text></Table.Td>
                <Table.Td>{s.entity ?? "—"}</Table.Td>
                <Table.Td className="lv-num">{s.account_code ?? s.accounts.join(", ")}</Table.Td>
                <Table.Td><Text size="sm">{Object.entries(s.sources).map(([k, v]) => `${v} ${k}`).join(", ")}</Text></Table.Td>
                <Table.Td>
                  <StatusBadge tone={STATUS[s.status][1]}>{STATUS[s.status][0]}</StatusBadge>
                  {s.status === "update" && s.rule && <Text size="xs" c="dimmed">aujourd'hui : {s.rule.entity_name ?? "—"} · {s.rule.account_code ?? "—"}</Text>}
                  {s.reason && <Text size="xs" c="dimmed">{s.reason}</Text>}
                  {s.shadowed_by && <Text size="xs" c="var(--lv-brique)">Masquée par la règle « {s.shadowed_by.name} », placée avant.</Text>}
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}
      <Group>
        <Button disabled={chosen.size === 0} loading={save.isPending}
          onClick={() => save.mutate(undefined, { onSuccess: onDone })}>
          Créer ou recréer {chosen.size} règle{chosen.size > 1 ? "s" : ""}</Button>
      </Group>
    </Stack>
  );
}

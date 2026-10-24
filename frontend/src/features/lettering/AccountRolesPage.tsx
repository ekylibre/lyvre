// Configuration › Comptes par défaut (lot F3) : comptes que Lyvre choisit seul (écart de lettrage,
// puis dotations, cessions…), défaut du référentiel ou choix de l'administrateur ; seuil d'écart.
import { useState } from "react";
import { Button, Group, Paper, Table, Text } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { useCan, useSession } from "../../api/session";
import { AccountSelect } from "../../components/AccountSelect";
import { MoneyInput } from "../../components/Money";
import { PageHeader } from "../../components/PageHeader";
import type { Account } from "../../lib/types";

interface Role { role: string; label: string; custom: boolean; account: Account | null; default_code: string | null }
interface Response { items: Role[]; lettering_gap_cents: number }
const KEY = ["account-roles"];

export default function AccountRolesPage() {
  const can = useCan();
  const session = useSession().data;
  const { data } = useQuery({ queryKey: KEY, queryFn: () => api.get<Response>("/api/v1/account-roles") });
  const [choices, setChoices] = useState<Record<string, Account | null>>({});
  const [gap, setGap] = useState<number | null>(null);
  const save = useAction(() => api.put<Response & { notices: Notice[] }>("/api/v1/account-roles", {
    roles: Object.fromEntries(Object.entries(choices).map(([role, account]) => [role, account?.id ?? null])),
    ...(gap !== null ? { lettering_gap_cents: gap } : {}),
  }), { invalidate: [KEY, ["lettering"]] });
  const scope = (session as { instance?: { slug?: string } } | undefined)?.instance?.slug ?? "default";
  return (
    <>
      <PageHeader title="Comptes par défaut" description="Comptes utilisés par Lyvre pour les écritures qu'il passe seul. Par défaut, ceux du plan comptable de la structure ; à faire valider par l'expert-comptable." />
      <Paper p={0} mb="md">
        <Table verticalSpacing="sm">
          <Table.Thead bg="var(--lv-sauge)"><Table.Tr><Table.Th>Usage</Table.Th><Table.Th>Compte</Table.Th><Table.Th>Défaut</Table.Th></Table.Tr></Table.Thead>
          <Table.Tbody>
            {(data?.items ?? []).map((r) => (
              <Table.Tr key={r.role}>
                <Table.Td>{r.label}</Table.Td>
                <Table.Td w={380}>{can.instanceAdmin
                  ? <AccountSelect label={r.label} recentsScope={scope} value={r.role in choices ? choices[r.role] : r.account}
                      onChange={(account) => setChoices({ ...choices, [r.role]: account })} />
                  : <Text size="sm" className="lv-num">{r.account ? `${r.account.code} — ${r.account.label}` : "—"}</Text>}</Table.Td>
                <Table.Td><Text size="sm" c="dimmed" className="lv-num">{r.default_code ?? "—"}{r.custom ? " (remplacé)" : ""}</Text></Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Paper>
      <Group align="flex-end">
        <MoneyInput label="Seuil d'écart de lettrage" description="Un reste jusqu'à ce montant se solde en charge ou produit divers."
          value={gap ?? data?.lettering_gap_cents ?? null} onChange={setGap} w={260} readOnly={!can.instanceAdmin} />
        {can.instanceAdmin && <Button loading={save.isPending} onClick={() => save.mutate(undefined, { onSuccess: () => { setChoices({}); setGap(null); } })}>Enregistrer</Button>}
      </Group>
    </>
  );
}

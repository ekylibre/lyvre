// Recherche Sirene (lot G3) : nom, SIREN ou SIRET, code postal facultatif ; lancée par le bouton ou
// Entrée (jamais à la frappe : 30 requêtes par minute pour tout le serveur). Un clic choisit la ligne.
import { useState } from "react";
import { Alert, Badge, Button, Group, Stack, Table, Text, TextInput, UnstyledButton } from "@mantine/core";
import { sireneMessage, useSireneSearch, type SireneCandidate } from "./useSirene";

export function SireneSearch({ onPick, initialQuery = "", initialPostalCode = "" }: {
  onPick: (candidate: SireneCandidate) => void; initialQuery?: string; initialPostalCode?: string;
}) {
  const [q, setQ] = useState(initialQuery);
  const [postal, setPostal] = useState(initialPostalCode);
  const search = useSireneSearch();
  const run = () => { if (q.trim()) search.mutate({ q: q.trim(), postal_code: postal.trim() || undefined }); };
  const onKey = (e: React.KeyboardEvent) => { if (e.key === "Enter") { e.preventDefault(); run(); } };

  return (
    <Stack gap="sm">
      <Group align="flex-end" wrap="nowrap">
        <TextInput label="Nom, SIREN ou SIRET" value={q} onChange={(e) => setQ(e.currentTarget.value)} onKeyDown={onKey} style={{ flex: 1 }} />
        <TextInput label="Code postal" value={postal} onChange={(e) => setPostal(e.currentTarget.value)} onKeyDown={onKey} w={110}
          classNames={{ input: "lv-num" }} />
        <Button onClick={run} loading={search.isPending} disabled={!q.trim()}>Rechercher</Button>
      </Group>
      {search.isError && <Alert color="brique" role="alert">{sireneMessage(search.error)}</Alert>}
      {search.data && (search.data.length === 0 ? <Text c="dimmed" size="sm">Aucune unité active ne correspond.</Text> : (
        <Table highlightOnHover verticalSpacing={4}>
          <Table.Tbody>
            {search.data.map((c) => (
              <Table.Tr key={c.siret ?? c.siren}>
                <Table.Td>
                  <UnstyledButton onClick={() => onPick(c)} w="100%">
                    <Text size="sm" fw={600}>{c.name}</Text>
                    <Text size="xs" c="dimmed">
                      {[c.legal_form, [c.postal_code, c.city].filter(Boolean).join(" "), c.siret ? `SIRET ${c.siret}` : `SIREN ${c.siren}`]
                        .filter(Boolean).join(" · ")}
                    </Text>
                  </UnstyledButton>
                </Table.Td>
                <Table.Td w={90} ta="right">
                  {c.head_office && <Badge size="xs" variant="light">Siège</Badge>}
                  {!c.active && <Badge size="xs" color="brique" variant="light">Fermé</Badge>}
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      ))}
    </Stack>
  );
}

// Proposition Sirene (lot G3) : champs vides à compléter (cochés), champs différents « Actuel → Sirene »
// (non cochés), champs identiques masqués. Remplit le formulaire, sans enregistrer (D3).
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Alert, Badge, Button, Checkbox, Group, Modal, Stack, Table, Text, Title } from "@mantine/core";
import { formatNaf } from "../../lib/format";
import type { SireneProposal } from "./useSirene";

const PERSON_KINDS: Record<string, string> = { individual: "Particulier", company: "Entreprise ou organisme" };

interface Row { key: string; label: string; current: string; proposed: string }

const same = (a: string, b: string) => a.replace(/\s+/g, " ").trim().toLowerCase() === b.replace(/\s+/g, " ").trim().toLowerCase();

export function SireneProposalModal({ opened, onClose, result, current, fields, onApply, note }: {
  opened: boolean; onClose: () => void; result: SireneProposal | null;
  /** Valeurs du formulaire, par champ. */
  current: Record<string, unknown>;
  /** Champs proposables et leurs libellés, dans l'ordre d'affichage. */
  fields: Record<string, string>;
  onApply: (values: Record<string, string>) => void;
  /** Rappel affiché sous la liste (ce que Sirene ne fournit pas). */
  note?: ReactNode;
}) {
  const rows = useMemo(() => {
    if (!result || result.state === "ceased") return { empty: [], changed: [] };
    const all: Row[] = Object.entries(fields).flatMap(([key, label]) => {
      const proposed = result.proposal[key];
      return proposed ? [{ key, label, current: String(current[key] ?? "").trim(), proposed }] : [];
    });
    return { empty: all.filter((r) => !r.current), changed: all.filter((r) => r.current && !same(r.current, r.proposed)) };
  }, [result, current, fields]);
  const [checked, setChecked] = useState<Set<string>>(new Set());
  useEffect(() => setChecked(new Set(rows.empty.map((r) => r.key))), [rows]);

  const display = (key: string, value: string) => {
    if (key === "naf_code") return `${formatNaf(value)}${result?.labels.naf ? ` — ${result.labels.naf}` : ""}`;
    return key === "person_kind" ? (PERSON_KINDS[value] ?? value) : value;
  };
  const toggle = (key: string) => setChecked((prev) => {
    const next = new Set(prev);
    if (next.has(key)) next.delete(key); else next.add(key);
    return next;
  });
  const tag = (key: string) => result?.computed.includes(key) && <Badge size="xs" variant="light" color="ardoise" ml={6}>calculé</Badge>;
  const apply = () => {
    if (!result) return;
    const values = Object.fromEntries([...checked].map((key) => [key, result.proposal[key]]));
    // L'activité va avec sa nomenclature.
    if (values.naf_code && result.proposal.naf_nomenclature) values.naf_nomenclature = result.proposal.naf_nomenclature;
    onApply(values);
    onClose();
  };
  const nothing = rows.empty.length + rows.changed.length === 0;

  return (
    <Modal opened={opened} onClose={onClose} title="Compléter depuis Sirene" size="lg" centered>
      {result && (
        <Stack>
          <Text fw={600}>{result.proposal.name}{result.proposal.siret && <Text span c="dimmed" ml="xs" className="lv-num">SIRET {result.proposal.siret}</Text>}</Text>
          {result.state === "ceased" && (
            <Alert color="brique">Unité légale cessée ou établissement fermé selon Sirene : aucun champ n'est proposé.</Alert>
          )}
          {result.warnings.map((w) => <Alert key={w} color="paille">{w}</Alert>)}
          {result.state !== "ceased" && nothing && <Text c="dimmed">Rien à compléter : la fiche correspond déjà à Sirene.</Text>}
          {rows.empty.length > 0 && (
            <Stack gap="xs">
              <Title order={3} size="h5">À compléter</Title>
              {rows.empty.map((r) => (
                <Checkbox key={r.key} checked={checked.has(r.key)} onChange={() => toggle(r.key)}
                  label={<>{r.label} : <b>{display(r.key, r.proposed)}</b>{tag(r.key)}</>} />
              ))}
            </Stack>
          )}
          {rows.changed.length > 0 && (
            <Stack gap="xs">
              <Title order={3} size="h5">Différent de Sirene</Title>
              <Table verticalSpacing={4}>
                <Table.Thead><Table.Tr><Table.Th w={32} /><Table.Th>Champ</Table.Th><Table.Th>Actuel</Table.Th><Table.Th>Sirene</Table.Th></Table.Tr></Table.Thead>
                <Table.Tbody>
                  {rows.changed.map((r) => (
                    <Table.Tr key={r.key}>
                      <Table.Td><Checkbox aria-label={`Remplacer ${r.label}`} checked={checked.has(r.key)} onChange={() => toggle(r.key)} /></Table.Td>
                      <Table.Td>{r.label}{tag(r.key)}</Table.Td>
                      <Table.Td c="dimmed">{display(r.key, r.current)}</Table.Td>
                      <Table.Td>{display(r.key, r.proposed)}</Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </Stack>
          )}
          {result.computed.length > 0 && !nothing && (
            <Text size="sm" c="dimmed">Le n° de TVA est calculé à partir du SIREN : Sirene ne le fournit pas.</Text>
          )}
          {note && <Text size="sm" c="dimmed">{note}</Text>}
          <Group justify="flex-end">
            <Button variant="default" onClick={onClose}>Annuler</Button>
            {!nothing && result.state !== "ceased" && (
              <Button onClick={apply} disabled={checked.size === 0}>Reporter dans le formulaire</Button>
            )}
          </Group>
        </Stack>
      )}
    </Modal>
  );
}

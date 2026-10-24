// Projet d'une ligne d'écriture : affectation simple ou ventilation sur plusieurs projets (la ligne
// est découpée en lignes de même compte : l'écriture reste équilibrée). Possible sur une écriture
// rapprochée, sauf ventilation de la ligne bancaire elle-même.
import { useState } from "react";
import { ActionIcon, Button, Group, SegmentedControl, Select, Stack, Text } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { FormModal } from "../../components/FormModal";
import { MoneyInput, MoneyText } from "../../components/Money";
import { PROJECTS_KEY } from "./ProjectsPage";

export interface ProjectLine {
  id: number; account_code: string; label: string; debit_cents: number; credit_cents: number;
  project_id: number | null; reconciled: boolean;
}

export function useProjectOptions() {
  return useQuery({ queryKey: [...PROJECTS_KEY, "options"],
    queryFn: () => api.get<{ items: { value: string; label: string }[] }>("/api/v1/projects/options") });
}

export function LineProjectModal({ entryId, line, invalidate, onClose, splittable = true }: {
  entryId: number; line: ProjectLine | null; invalidate: unknown[][]; onClose: () => void;
  /** Faux sur une écriture validée : ses lignes ne changent plus, la ligne s'affecte entière. */
  splittable?: boolean;
}) {
  return (
    <FormModal opened={!!line} onClose={onClose} title={line ? `Projet — ligne ${line.account_code}` : ""}>
      {line && <LineProjectForm key={line.id} entryId={entryId} line={line} invalidate={invalidate} onDone={onClose} splittable={splittable} />}
    </FormModal>
  );
}

function LineProjectForm({ entryId, line, invalidate, onDone, splittable }: {
  entryId: number; line: ProjectLine; invalidate: unknown[][]; onDone: () => void; splittable: boolean;
}) {
  const options = useProjectOptions().data?.items ?? [];
  const amount = line.debit_cents || line.credit_cents;
  const [mode, setMode] = useState<"one" | "split">("one");
  const [projectId, setProjectId] = useState<string | null>(line.project_id ? String(line.project_id) : null);
  const [parts, setParts] = useState<{ project: string | null; amount: number | null }[]>([
    { project: line.project_id ? String(line.project_id) : null, amount: null }, { project: null, amount: null }]);
  const base = `/api/v1/entries/${entryId}/lines/${line.id}`;
  const opts = { invalidate: [...invalidate, PROJECTS_KEY] };
  const assign = useAction(() => api.put<{ notices: Notice[] }>(`${base}/project`, { project_id: projectId ? Number(projectId) : null }), opts);
  const split = useAction(() => api.post<{ notices: Notice[] }>(`${base}/split`, {
    parts: parts.map((p) => ({ project_id: p.project ? Number(p.project) : null, amount_cents: p.amount })),
  }), opts);
  const total = parts.reduce((sum, p) => sum + (p.amount ?? 0), 0);
  const update = (i: number, patch: Partial<(typeof parts)[number]>) => setParts(parts.map((p, j) => (j === i ? { ...p, ...patch } : p)));
  return (
    <Stack>
      <Text size="sm">{line.label || "Ligne"} · <MoneyText cents={amount} /></Text>
      {!splittable && <Text size="xs" c="dimmed">Écriture validée : la ligne s'affecte entière à un projet (pas de ventilation).</Text>}
      {!line.reconciled && splittable && (
        <SegmentedControl value={mode} onChange={(v) => setMode(v as "one" | "split")}
          data={[{ value: "one", label: "Un projet" }, { value: "split", label: "Ventiler" }]} />
      )}
      {mode === "one" ? (
        <>
          <Select label="Projet" data={options} value={projectId} onChange={setProjectId} clearable searchable placeholder="Aucun" data-autofocus />
          <Group justify="flex-end">
            <Button variant="default" onClick={onDone}>Annuler</Button>
            <Button loading={assign.isPending} onClick={() => assign.mutate(undefined, { onSuccess: onDone })}>Enregistrer</Button>
          </Group>
        </>
      ) : (
        <>
          {parts.map((p, i) => (
            <Group key={i} align="flex-end" wrap="nowrap">
              <Select aria-label={`Projet, part ${i + 1}`} label={i === 0 ? "Projet" : undefined} data={options} value={p.project}
                onChange={(v) => update(i, { project: v })} clearable searchable placeholder="Aucun" style={{ flex: 2 }} />
              <MoneyInput aria-label={`Montant, part ${i + 1}`} label={i === 0 ? "Montant" : undefined} value={p.amount}
                onChange={(v) => update(i, { amount: v })} style={{ flex: 1 }} />
              {parts.length > 2 && <ActionIcon variant="subtle" color="brique" mb={6} aria-label={`Retirer la part ${i + 1}`}
                onClick={() => setParts(parts.filter((_p, j) => j !== i))}>×</ActionIcon>}
            </Group>
          ))}
          <Group justify="space-between">
            <Button variant="subtle" size="compact-sm"
              onClick={() => setParts([...parts, { project: null, amount: amount - total > 0 ? amount - total : null }])}>Ajouter une part</Button>
            <Text size="sm" c={total === amount ? undefined : "var(--lv-brique)"}>Réparti : <MoneyText cents={total} /> / <MoneyText cents={amount} /></Text>
          </Group>
          <Group justify="flex-end">
            <Button variant="default" onClick={onDone}>Annuler</Button>
            <Button loading={split.isPending} disabled={total !== amount || parts.some((p) => !p.amount)}
              onClick={() => split.mutate(undefined, { onSuccess: onDone })}>Ventiler la ligne</Button>
          </Group>
        </>
      )}
    </Stack>
  );
}

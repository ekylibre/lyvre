// Champ « Affectation analytique » (lot AG8.c, claudedocs/design_analytique_agricole.md § 5) : une activité (par
// atelier) ou une clé de répartition, valeur « activity:ID » ou « key:ID ». Rien hors instance agricole.
import { Select, type SelectProps } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

export type AnalyticTarget = { value: string; label: string; group: string };

/** Activités et clés de l'instance (liste vide hors agricole). */
export function useAnalyticTargets(enabled = true): AnalyticTarget[] {
  const { data } = useQuery({ queryKey: ["analytic-targets"], enabled, staleTime: 60_000,
    queryFn: () => api.get<{ items: AnalyticTarget[] }>("/api/v1/analytic-targets") });
  const items = Array.isArray(data?.items) ? data.items : [];
  return items.filter((t) => typeof t?.value === "string" && /^(activity|key):\d+$/.test(t.value) && typeof t.label === "string");
}

export function groupTargets(targets: AnalyticTarget[]) {
  return targets.reduce<{ group: string; items: { value: string; label: string }[] }[]>((acc, t) => {
    const item = { value: t.value, label: t.label };
    const group = acc.find((g) => g.group === t.group);
    if (group) group.items.push(item); else acc.push({ group: t.group, items: [item] });
    return acc;
  }, []);
}

export function AnalyticSelect({ targets, value, onChange, ...props }:
  Omit<SelectProps, "data" | "value" | "onChange"> & { targets: AnalyticTarget[]; value: string | null; onChange: (value: string | null) => void }) {
  if (!targets.length) return null;
  return <Select searchable clearable placeholder="—" data={groupTargets(targets)} value={value || null} onChange={onChange} {...props} />;
}

/** Activités seules (fiches d'inventaire et immobilisations : `activity_id`). */
export function ActivitySelect({ targets, value, onChange, ...props }:
  Omit<SelectProps, "data" | "value" | "onChange"> & { targets: AnalyticTarget[]; value: number | null; onChange: (value: number | null) => void }) {
  const activities = targets.filter((t) => t.value.startsWith("activity:"));
  if (!activities.length) return null;
  return <Select searchable clearable placeholder="—" data={groupTargets(activities)} value={value ? `activity:${value}` : null}
    onChange={(x) => onChange(x ? Number(x.split(":")[1]) : null)} {...props} />;
}

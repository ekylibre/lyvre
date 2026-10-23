// Soldes des comptes courants à la fin de chaque exercice, empilés par associé (comme le
// graphique d'Ekylibre). Créditeur positif : la société doit aux associés.
import { BarChart } from "@mantine/charts";
import { Text } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { formatEuros } from "../../lib/format";
import { ASSOCIATES_KEY } from "./types";

const COLORS = ["var(--lv-lichen)", "var(--lv-ardoise)", "var(--lv-paille-ink)", "var(--lv-brique)", "var(--lv-lichen-strong)",
  "var(--lv-night)", "var(--lv-paille)", "var(--lv-brique-ink)"];

interface Data { years: string[]; series: { name: string; values: number[] }[] }

/** Lignes du graphique : une par exercice, une colonne (en euros) par associé. */
export function chartRows(data: Data): Record<string, string | number>[] {
  return data.years.map((year, i) => Object.fromEntries([["exercice", year],
    ...data.series.map((s) => [s.name, s.values[i] / 100])]));
}

export function BalancesChart() {
  const { data } = useQuery({ queryKey: [...ASSOCIATES_KEY, "balances-by-year"],
    queryFn: () => api.get<Data>("/api/v1/associates/balances-by-year") });
  if (!data) return null;
  if (!data.years.length || !data.series.length) return <Text size="sm" c="dimmed">Aucun exercice ou aucun associé.</Text>;
  return (
    <BarChart h={320} data={chartRows(data)} dataKey="exercice" type="stacked" withLegend
      valueFormatter={(v) => formatEuros(Math.round(v * 100))}
      series={data.series.map((s, i) => ({ name: s.name, color: COLORS[i % COLORS.length] }))} />
  );
}

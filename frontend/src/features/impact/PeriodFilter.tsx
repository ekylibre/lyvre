// Période du tableau de bord : mois, trimestre (AAAA-Qn), année ou plage de dates.
import { Select, TextInput } from "@mantine/core";
import { FilterBar } from "../../components/FilterBar";
import type { ImpactView, PeriodParams } from "./types";

const GRANULARITIES = [
  { value: "month", label: "Mois" }, { value: "quarter", label: "Trimestre" },
  { value: "year", label: "Année" }, { value: "custom", label: "Plage" },
];

export function PeriodFilter({ view, onChange }: { view: ImpactView | undefined; onChange: (patch: Partial<PeriodParams>) => void }) {
  const current = view?.current;
  const gran = current?.gran || "month";
  return (
    <FilterBar>
      <Select label="Granularité" data={GRANULARITIES} value={gran} allowDeselect={false} w={140}
        onChange={(value) => onChange({ gran: value ?? "month" })} />
      {gran === "month" && <Select label="Mois" data={view?.meta.months ?? []} value={current?.month || null} w={180} searchable
        allowDeselect={false} onChange={(month) => onChange({ month: month ?? "" })} />}
      {gran === "quarter" && <TextInput label="Trimestre" placeholder="2026-Q2" defaultValue={current?.quarter} w={130}
        key={current?.quarter} onBlur={(e) => onChange({ quarter: e.currentTarget.value.trim() })}
        onKeyDown={(e) => { if (e.key === "Enter") onChange({ quarter: e.currentTarget.value.trim() }); }} />}
      {gran === "year" && <Select label="Année" data={view?.meta.years ?? []} value={current?.year || null} w={120}
        allowDeselect={false} onChange={(year) => onChange({ year: year ?? "" })} />}
      {gran === "custom" && <>
        <TextInput type="date" label="Du" value={current?.start ?? ""} onChange={(e) => onChange({ start: e.currentTarget.value })} />
        <TextInput type="date" label="au" value={current?.end ?? ""} onChange={(e) => onChange({ end: e.currentTarget.value })} />
      </>}
    </FilterBar>
  );
}

import { Select } from "@mantine/core";

export interface MonthOption { value: string; label: string }

/** Mois de l'exercice en cours (`YYYY-MM`), vide = tous les mois. */
export function MonthSelect({ value, onChange, options, label = "Mois" }: {
  value: string; onChange: (value: string) => void; options: MonthOption[] | undefined; label?: string;
}) {
  return (
    <Select label={label} placeholder="Tous les mois" clearable data={options ?? []} value={value || null}
      onChange={(v) => onChange(v ?? "")} w={180} />
  );
}

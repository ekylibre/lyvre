// Choix d'un tiers avec recherche (GET /api/v1/entities?q=, sans accents, nom ou email).
import { useState } from "react";
import { Select, type SelectProps } from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

interface EntityOption { id: number; name: string; type: string; email: string | null }

type EntitySelectProps = Omit<SelectProps, "data" | "value" | "onChange" | "searchValue" | "onSearchChange"> & {
  /** Identifiant du tiers choisi (texte, comme les champs de formulaire), vide si aucun. */
  value: string;
  onChange: (id: string, entity: EntityOption | null) => void;
  /** Libellé du tiers déjà choisi (affiché avant toute recherche). */
  initialLabel?: string | null;
};

export function EntitySelect({ value, onChange, initialLabel, ...props }: EntitySelectProps) {
  const [search, setSearch] = useState("");
  const [debounced] = useDebouncedValue(search, 250);
  const { data } = useQuery({
    queryKey: ["entity-lookup", debounced], staleTime: 30_000,
    queryFn: () => api.get<{ results: EntityOption[] }>(`/api/v1/entities?q=${encodeURIComponent(debounced)}&limit=20`),
  });
  const options = (data?.results ?? []).map((e) => ({ value: String(e.id), label: e.name }));
  if (value && initialLabel && !options.some((o) => o.value === value)) options.unshift({ value, label: initialLabel });
  return (
    <Select searchable clearable filter={({ options: o }) => o} nothingFoundMessage="Aucun tiers" {...props}
      data={options} value={value || null} searchValue={search} onSearchChange={setSearch}
      onChange={(id) => onChange(id ?? "", data?.results.find((e) => String(e.id) === id) ?? null)} />
  );
}

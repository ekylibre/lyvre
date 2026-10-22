// Filtres d'une liste synchronisés avec l'URL (F3 : liens partageables, retour arrière).
import { useEffect, useState, type ReactNode } from "react";
import { useSearchParams } from "react-router";
import { Group, TextInput } from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { IconSearch } from "@tabler/icons-react";

/**
 * Paramètres d'URL d'une liste : valeurs courantes (défauts compris) et mise à jour.
 * Changer un filtre revient à la page 1 ; une valeur vide retire le paramètre.
 */
export function useUrlParams<K extends string>(defaults: Record<K, string>) {
  const [params, setParams] = useSearchParams();
  const values = Object.fromEntries(
    (Object.keys(defaults) as K[]).map((key) => [key, params.get(key) ?? defaults[key]]),
  ) as Record<K, string>;
  const update = (patch: Partial<Record<K, string>>) => {
    setParams((current) => {
      const next = new URLSearchParams(current);
      for (const [key, value] of Object.entries(patch) as [string, string | undefined][]) {
        if (value === undefined || value === "" || value === defaults[key as K]) next.delete(key);
        else next.set(key, value);
      }
      if (!("page" in patch)) next.delete("page");
      return next;
    }, { replace: true });
  };
  return [values, update] as const;
}

/** Recherche texte avec anti-rebond (300 ms) avant mise à jour de l'URL. */
export function SearchInput({ value, onChange, placeholder = "Rechercher…" }: {
  value: string; onChange: (value: string) => void; placeholder?: string;
}) {
  const [text, setText] = useState(value);
  const [debounced] = useDebouncedValue(text, 300);
  useEffect(() => setText(value), [value]);
  useEffect(() => {
    if (debounced !== value) onChange(debounced);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debounced]);
  return (
    <TextInput type="search" aria-label="Rechercher" placeholder={placeholder} value={text}
      leftSection={<IconSearch size={16} />} onChange={(e) => setText(e.currentTarget.value)} w={260} />
  );
}

export function FilterBar({ children }: { children: ReactNode }) {
  return <Group gap="sm" mb="sm" align="flex-end">{children}</Group>;
}

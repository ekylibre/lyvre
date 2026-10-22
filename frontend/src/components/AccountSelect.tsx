// Choix d'un compte (comptes utilisables, hors regroupement) : recherche par début de code
// ou mots du libellé (GET /api/v1/accounts?q=), comptes récents de l'instance quand le champ
// est vide. Clavier : ↓ / Alt+↓ ouvre la liste, ↑↓ parcourt, Entrée ou Tab choisit,
// Échap ferme.
import { forwardRef, useEffect, useRef, useState, type KeyboardEvent } from "react";
import { Combobox, Group, InputBase, Loader, Text, useCombobox } from "@mantine/core";
import { api } from "../api/client";
import { accountLabel, loadRecents, rememberAccount } from "./AccountCombobox";
import type { Account } from "../lib/types";

export { rememberAccount };

const SEARCH_DELAY_MS = 150;
const cache = new Map<string, Account[]>();

interface AccountSelectProps {
  value: Account | null;
  onChange: (account: Account | null) => void;
  recentsScope: string;
  label: string;
  error?: string;
  /** Repères des raccourcis du formulaire parent (data-line, data-field). */
  line?: number;
}

export const AccountSelect = forwardRef<HTMLInputElement, AccountSelectProps>(function AccountSelect(
  { value, onChange, recentsScope, label, error, line }, ref,
) {
  const combobox = useCombobox({ onDropdownClose: () => combobox.resetSelectedOption() });
  const [text, setText] = useState(value ? accountLabel(value) : "");
  const [results, setResults] = useState<Account[]>([]);
  const [loading, setLoading] = useState(false);
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => setText(value ? accountLabel(value) : ""), [value]);

  function search(query: string) {
    window.clearTimeout(timer.current);
    const key = query.trim().toLowerCase();
    if (!key) {
      const recents = loadRecents(recentsScope);
      if (recents.length) return setResults(recents);
    }
    const cached = cache.get(key);
    if (cached) return setResults(cached);
    setLoading(true);
    timer.current = window.setTimeout(async () => {
      try {
        const data = await api.get<{ results: Account[] }>(`/api/v1/accounts?q=${encodeURIComponent(key)}&limit=20`);
        cache.set(key, data.results);
        setResults(data.results);
      } catch {
        setResults([]);
      } finally {
        setLoading(false);
      }
    }, SEARCH_DELAY_MS);
  }

  useEffect(() => { if (results.length) combobox.selectFirstOption(); }, [results]); // eslint-disable-line react-hooks/exhaustive-deps

  function choose(account: Account) {
    rememberAccount(recentsScope, account);
    onChange(account);
    setText(accountLabel(account));
    combobox.closeDropdown();
  }

  function onKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown" && (e.altKey || !combobox.dropdownOpened)) {
      e.preventDefault();
      combobox.openDropdown();
      search(value ? "" : text);
    } else if (e.key === "Tab" && !e.shiftKey && combobox.dropdownOpened && text && results.length) {
      const index = Math.max(combobox.selectedOptionIndex, 0);
      if (results[index]) choose(results[index]);
    } else if (e.key === "Enter" || e.key === "Escape") {
      e.stopPropagation(); // le formulaire parent ne doit pas réagir (ligne, envoi)
    }
  }

  return (
    <Combobox store={combobox} onOptionSubmit={(id) => {
      const account = results.find((a) => String(a.id) === id);
      if (account) choose(account);
    }} withinPortal>
      <Combobox.Target>
        <InputBase ref={ref} aria-label={label} error={error} placeholder="Code ou libellé…"
          classNames={{ input: "lv-num" }} data-line={line} data-field="account" autoComplete="off"
          rightSection={loading ? <Loader size={14} /> : <Combobox.Chevron />} rightSectionPointerEvents="none"
          value={text}
          onChange={(e) => {
            setText(e.currentTarget.value);
            if (value) onChange(null);
            combobox.openDropdown();
            search(e.currentTarget.value);
          }}
          onFocus={() => { if (!value) { combobox.openDropdown(); search(text); } }}
          onBlur={() => { combobox.closeDropdown(); setText(value ? accountLabel(value) : text); }}
          onKeyDown={onKeyDown} />
      </Combobox.Target>
      <Combobox.Dropdown>
        <Combobox.Options mah={280} style={{ overflowY: "auto" }}>
          {results.length === 0
            ? <Combobox.Empty>{loading ? "Recherche…" : "Aucun compte"}</Combobox.Empty>
            : results.map((a) => (
              <Combobox.Option key={a.id} value={String(a.id)}>
                <Group gap="xs" wrap="nowrap"><Text className="lv-num" fw={600} size="sm">{a.code}</Text><Text size="sm">{a.label}</Text></Group>
              </Combobox.Option>
            ))}
        </Combobox.Options>
      </Combobox.Dropdown>
    </Combobox>
  );
});

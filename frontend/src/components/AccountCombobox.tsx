import { forwardRef, useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import { api } from "../lib/api";
import type { Account } from "../lib/types";

const SEARCH_DELAY_MS = 150;
const MAX_RECENTS = 20;

export function accountLabel(account: Account): string {
  return `${account.code} — ${account.label}`;
}

// --- comptes récents (par instance, dans le navigateur) ---------------------

function recentsKey(scope: string) {
  return `compta:recent-accounts:${scope}`;
}

export function loadRecents(scope: string): Account[] {
  try {
    return JSON.parse(localStorage.getItem(recentsKey(scope)) || "[]") as Account[];
  } catch {
    return [];
  }
}

export function rememberAccount(scope: string, account: Account): void {
  const list = [account, ...loadRecents(scope).filter((a) => a.id !== account.id)];
  try {
    localStorage.setItem(recentsKey(scope), JSON.stringify(list.slice(0, MAX_RECENTS)));
  } catch {
    /* stockage indisponible : sans conséquence */
  }
}

// --- composant --------------------------------------------------------------

interface Props {
  value: Account | null;
  onChange: (account: Account | null) => void;
  searchUrl: string;
  recentsScope: string;
  label: string;
  invalid?: boolean;
  describedBy?: string;
  /** Index de ligne (raccourcis clavier du formulaire parent). */
  line?: number;
}

const cache = new Map<string, Account[]>();

/** Champ de saisie d'un compte : motif ARIA « combobox » + liste de suggestions. */
export const AccountCombobox = forwardRef<HTMLInputElement, Props>(function AccountCombobox(
  { value, onChange, searchUrl, recentsScope, label, invalid, describedBy, line },
  ref,
) {
  const listId = useId();
  const [text, setText] = useState(value ? accountLabel(value) : "");
  const [open, setOpen] = useState(false);
  const [results, setResults] = useState<Account[]>([]);
  const [active, setActive] = useState(0);
  const timer = useRef<number>();

  // Valeur modifiée de l'extérieur (réinitialisation, préremplissage).
  useEffect(() => {
    setText(value ? accountLabel(value) : "");
  }, [value]);

  function search(query: string) {
    window.clearTimeout(timer.current);
    if (!query.trim()) {
      const recents = loadRecents(recentsScope);
      if (recents.length) {
        setResults(recents);
        setActive(0);
        return;
      }
    }
    const key = query.trim().toLowerCase();
    const cached = cache.get(key);
    if (cached) {
      setResults(cached);
      setActive(0);
      return;
    }
    timer.current = window.setTimeout(async () => {
      try {
        const data = await api<{ results: Account[] }>(
          "GET", `${searchUrl}?q=${encodeURIComponent(query.trim())}&limit=20`);
        cache.set(key, data.results);
        setResults(data.results);
        setActive(0);
      } catch {
        setResults([]);
      }
    }, SEARCH_DELAY_MS);
  }

  function openList(query = "") {
    setOpen(true);
    search(query);
  }

  function select(account: Account) {
    rememberAccount(recentsScope, account);
    onChange(account);
    setText(accountLabel(account));
    setOpen(false);
  }

  function onKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown" && (e.altKey || !open)) {
      e.preventDefault();
      openList(value ? "" : text);
      return;
    }
    if (!open) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((i) => Math.min(i + 1, results.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter" || (e.key === "Tab" && !e.shiftKey && results.length && text)) {
      if (results[active]) {
        if (e.key === "Enter") e.preventDefault();
        e.stopPropagation();
        select(results[active]);
      }
    } else if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      setOpen(false);
    }
  }

  return (
    <div className="position-relative">
      <input
        ref={ref}
        type="text"
        className={`form-control form-control-sm${invalid ? " is-invalid" : ""}`}
        role="combobox"
        data-line={line}
        data-field="account"
        aria-label={label}
        aria-expanded={open && results.length > 0}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={open && results[active] ? `${listId}-${active}` : undefined}
        aria-invalid={invalid || undefined}
        aria-describedby={describedBy}
        autoComplete="off"
        placeholder="Code ou libellé…"
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          if (value) onChange(null);
          openList(e.target.value);
        }}
        onKeyDown={onKeyDown}
        onBlur={() => window.setTimeout(() => setOpen(false), 120)}
      />
      {open && results.length > 0 && (
        <ul id={listId} role="listbox" className="dropdown-menu show w-100 shadow-sm"
            style={{ maxHeight: "16rem", overflowY: "auto" }}>
          {results.map((a, i) => (
            <li key={a.id} id={`${listId}-${i}`} role="option" aria-selected={i === active}>
              <button
                type="button"
                tabIndex={-1}
                className={`dropdown-item small${i === active ? " active" : ""}`}
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => select(a)}
              >
                <span className="font-monospace">{a.code}</span> — {a.label}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
});

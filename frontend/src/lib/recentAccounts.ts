// Comptes récemment utilisés en saisie, par instance, dans le navigateur.
import type { Account } from "./types";

const MAX_RECENTS = 20;

export function accountLabel(account: Account): string {
  return `${account.code} — ${account.label}`;
}

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

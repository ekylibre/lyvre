// API Sirene (lot G3) : disponibilité, recherche et proposition de champs. Les appels passent par le
// serveur (la clé de l'INSEE n'arrive jamais ici) ; pas de recherche à la frappe.
import { useMutation } from "@tanstack/react-query";
import { ApiError, api } from "../../api/client";
import { useCan, useCurrentSession } from "../../api/session";

export interface SireneCandidate {
  siren: string; siret: string | null; name: string; legal_form: string | null;
  postal_code: string | null; city: string | null; head_office: boolean; active: boolean;
}

export interface SireneProposal {
  proposal: Record<string, string>;
  /** Champs calculés plutôt que lus dans Sirene (n° de TVA). */
  computed: string[];
  state: "active" | "ceased";
  warnings: string[];
  labels: { legal_form: string | null; naf: string | null };
  existing_entity: { id: number; name: string } | null;
}

/** Sirene configuré sur le serveur, et l'utilisateur peut modifier (pas l'expert-comptable). */
export function useSireneAvailable(): boolean {
  const session = useCurrentSession();
  return !!session.services?.sirene && useCan().write;
}

const query = (params: Record<string, string | undefined>) =>
  new URLSearchParams(Object.entries(params).filter((e): e is [string, string] => !!e[1])).toString();

export function useSireneProposal() {
  return useMutation({
    meta: { silent: true },  // message affiché par l'écran (sireneMessage)
    mutationFn: (params: { siren?: string; siret?: string; for?: "entity" }) =>
      api.get<SireneProposal>(`/api/v1/sirene/proposal?${query(params)}`),
  });
}

export function useSireneSearch() {
  return useMutation({
    meta: { silent: true },
    mutationFn: (params: { q: string; postal_code?: string }) =>
      api.get<{ items: SireneCandidate[] }>(`/api/v1/sirene/search?${query(params)}`).then((r) => r.items),
  });
}

/** Message d'erreur à afficher ; quota dépassé : délai d'attente. */
export function sireneMessage(error: unknown): string {
  if (error instanceof ApiError) {
    const wait = Number(error.details.retry_after);
    if (error.code === "sirene_busy" && wait) return `Trop de recherches, réessayez dans ${wait} s.`;
    return error.message;
  }
  return "Sirene ne répond pas : réessayez plus tard.";
}

/** SIREN valide : 9 chiffres et clé de Luhn (La Poste, 356000000, fait exception). */
export function isValidSiren(value: string | null | undefined): boolean {
  const digits = (value ?? "").replace(/[\s.]/g, "");
  if (!/^\d{9}$/.test(digits)) return false;
  if (digits === "356000000") return true;
  let total = 0;
  [...digits].reverse().forEach((ch, i) => {
    let n = Number(ch);
    if (i % 2 === 1) { n *= 2; if (n > 9) n -= 9; }
    total += n;
  });
  return total % 10 === 0;
}

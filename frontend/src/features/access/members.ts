// Membres d'une instance et lignes « utilisateur + rôle » saisies à la création d'une instance
// (claudedocs/design_acces_instances.md §5).

export type Role = "admin" | "treasurer" | "accountant";
export type RoleOption = { value: string; label: string };

export interface Member {
  user_id: number; email: string; full_name: string | null; role: Role;
  role_label: string; global_admin: boolean; is_active: boolean; is_me: boolean;
}
export type MembersMeta = { roles: RoleOption[] };

/** Compte proposé dans la liste (GET /api/v1/users, administrateur global). */
export interface UserOption { id: number; email: string; full_name: string | null; is_admin: boolean; is_active: boolean }

export const ROLE_HELP: Record<string, string> = {
  admin: "Tout, dont les accès, les intégrations et la clôture définitive.",
  treasurer: "Saisie, rapprochement, imports, clôture provisoire.",
  accountant: "Consulte toute la comptabilité et exporte le FEC, sans rien modifier.",
};

export interface MemberRow {
  kind: "existing" | "new";
  user_id: string | null;
  email: string;
  full_name: string;
  password: string;
  role: Role;
}

/** Première ligne : administrateur ; les suivantes : trésorier. */
export function newRow(index: number): MemberRow {
  return { kind: "existing", user_id: null, email: "", full_name: "", password: "", role: index === 0 ? "admin" : "treasurer" };
}

export type MemberPayload =
  | { user_id: number; role: Role }
  | { email: string; full_name?: string; password: string; role: Role };

/** Lignes du formulaire → `members` de l'API, une pour une (les erreurs `members.<i>.<champ>` du
 * serveur retombent sur la bonne ligne). */
export function toMembersPayload(rows: MemberRow[]): MemberPayload[] {
  return rows.map((row): MemberPayload => {
    if (row.kind === "existing") return { user_id: Number(row.user_id), role: row.role };
    const full_name = row.full_name.trim();
    return { email: row.email.trim(), password: row.password, role: row.role, ...(full_name ? { full_name } : {}) };
  });
}

/** Contrôles avant envoi (le serveur refait tout) : chemins d'erreur du formulaire. */
export function memberRowErrors(rows: MemberRow[]): Record<string, string> {
  const errors: Record<string, string> = {};
  rows.forEach((row, i) => {
    if (row.kind === "existing" && !row.user_id) errors[`members.${i}.user_id`] = "Choisissez un utilisateur ou retirez la ligne.";
    if (row.kind === "new" && !row.email.trim()) errors[`members.${i}.email`] = "Email obligatoire.";
    if (row.kind === "new" && row.password.length < 8) errors[`members.${i}.password`] = "8 caractères au moins.";
  });
  return errors;
}

/** Comptes proposables : hors administrateurs globaux (déjà partout). */
export function userChoices(users: UserOption[]): { value: string; label: string }[] {
  return users.filter((u) => !u.is_admin).map((u) => ({
    value: String(u.id),
    label: `${u.full_name ? `${u.full_name} — ${u.email}` : u.email}${u.is_active ? "" : " (désactivé)"}`,
  }));
}

/** Compte existant dont l'email est saisi comme nouveau compte (proposer de le prendre). */
export function knownAccount(users: UserOption[], email: string): UserOption | undefined {
  const wanted = email.trim().toLowerCase();
  return wanted ? users.find((u) => !u.is_admin && u.email.toLowerCase() === wanted) : undefined;
}

export function lacksAdmin(rows: MemberRow[]): boolean {
  return rows.length > 0 && !rows.some((r) => r.role === "admin");
}

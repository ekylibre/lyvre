import { describe, expect, it } from "vitest";
import { knownAccount, lacksAdmin, memberRowErrors, newRow, toMembersPayload, userChoices, type MemberRow } from "./members";

const USERS = [
  { id: 1, email: "boss@asso.fr", full_name: "Boss", is_admin: true, is_active: true },
  { id: 2, email: "marie@asso.fr", full_name: "Marie", is_admin: false, is_active: true },
  { id: 3, email: "dort@asso.fr", full_name: null, is_admin: false, is_active: false },
];

const row = (patch: Partial<MemberRow>): MemberRow => ({ ...newRow(1), ...patch });

describe("lignes de membres", () => {
  it("propose administrateur pour la première ligne, trésorier ensuite", () => {
    expect(newRow(0).role).toBe("admin");
    expect(newRow(2).role).toBe("treasurer");
  });

  it("convertit chaque ligne, une pour une", () => {
    expect(toMembersPayload([
      row({ kind: "existing", user_id: "2", role: "treasurer" }),
      row({ kind: "new", email: " paul@asso.fr ", full_name: " ", password: "motdepasse", role: "admin" }),
      row({ kind: "new", email: "lea@asso.fr", full_name: " Léa ", password: "motdepasse", role: "accountant" }),
    ])).toEqual([
      { user_id: 2, role: "treasurer" },
      { email: "paul@asso.fr", password: "motdepasse", role: "admin" },
      { email: "lea@asso.fr", full_name: "Léa", password: "motdepasse", role: "accountant" },
    ]);
  });

  it("signale les lignes incomplètes", () => {
    expect(memberRowErrors([row({ kind: "existing" }), row({ kind: "new", email: "", password: "court" })])).toEqual({
      "members.0.user_id": "Choisissez un utilisateur ou retirez la ligne.",
      "members.1.email": "Email obligatoire.",
      "members.1.password": "8 caractères au moins.",
    });
    expect(memberRowErrors([row({ kind: "existing", user_id: "2" })])).toEqual({});
  });

  it("liste les comptes hors administrateurs globaux, avec la mention désactivé", () => {
    expect(userChoices(USERS)).toEqual([
      { value: "2", label: "Marie — marie@asso.fr" },
      { value: "3", label: "dort@asso.fr (désactivé)" },
    ]);
    expect(knownAccount(USERS, " MARIE@asso.fr")?.id).toBe(2);
    expect(knownAccount(USERS, "boss@asso.fr")).toBeUndefined();
  });

  it("avertit s'il n'y a aucun administrateur", () => {
    expect(lacksAdmin([])).toBe(false);
    expect(lacksAdmin([row({ role: "treasurer" })])).toBe(true);
    expect(lacksAdmin([row({ role: "treasurer" }), row({ role: "admin" })])).toBe(false);
  });
});

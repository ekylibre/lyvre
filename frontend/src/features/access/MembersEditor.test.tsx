import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useForm } from "@mantine/form";
import { renderWithProviders } from "../../test/render";
import { MembersEditor } from "./MembersEditor";
import type { MemberRow } from "./members";

const USERS = [{ id: 2, email: "marie@asso.fr", full_name: "Marie", is_admin: false, is_active: true }];
const ROLES = [{ value: "admin", label: "Administrateur" }, { value: "treasurer", label: "Trésorier" },
  { value: "accountant", label: "Expert-comptable" }];

function Harness() {
  const form = useForm({ initialValues: { members: [] as MemberRow[] } });
  return <MembersEditor form={form} users={USERS} roles={ROLES} />;
}

describe("MembersEditor", () => {
  it("passe la première ligne en nouveau compte", async () => {
    renderWithProviders(<Harness />);
    await userEvent.click(screen.getByRole("button", { name: "Ajouter un utilisateur" }));
    await userEvent.click(screen.getByText("Nouveau compte"));
    expect(screen.getByRole("textbox", { name: /Email/ })).toBeInTheDocument();
  });

  it("ajoute des lignes, propose le compte existant et avertit sans administrateur", async () => {
    renderWithProviders(<Harness />);
    await userEvent.click(screen.getByRole("button", { name: "Ajouter un utilisateur" }));
    expect(screen.getByRole("combobox", { name: "Utilisateur" })).toBeInTheDocument();
    expect(screen.queryByText(/Aucun administrateur/)).not.toBeInTheDocument();  // 1re ligne : administrateur

    await userEvent.click(screen.getByRole("button", { name: "Ajouter un utilisateur" }));
    await userEvent.click(screen.getAllByText("Nouveau compte")[1]);
    await userEvent.type(screen.getByRole("textbox", { name: /Email/ }), "MARIE@asso.fr");
    await userEvent.click(screen.getByRole("button", { name: "Utiliser ce compte" }));
    expect(screen.queryByRole("textbox", { name: /Email/ })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Retirer la ligne 1" }));
    expect(screen.getByText(/Aucun administrateur/)).toBeInTheDocument();  // reste un trésorier
  });
});

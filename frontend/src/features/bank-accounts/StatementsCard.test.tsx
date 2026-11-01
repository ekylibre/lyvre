// Relevés de compte (lot RQ1) : mois manquants, lien vers le PDF, récupération Qonto au clic.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { notifications } from "@mantine/notifications";
import { renderWithProviders } from "../../test/render";
import { StatementsCard, type StatementsList } from "./StatementsCard";

const uploads = vi.hoisted(() => [] as { url: string; period: FormDataEntryValue | null; file: FormDataEntryValue | null }[]);
vi.mock("../../api/upload", () => ({
  upload: (url: string, form: FormData) => {
    uploads.push({ url, period: form.get("period"), file: form.get("file") });
    return Promise.resolve({ notices: [] });
  },
}));

const LIST: StatementsList = {
  fiscal_year: { id: 1, label: "2026-2027" },
  qonto: { enabled: true, available: true, message: null }, upload_months: [],
  items: [
    { period: "2026-08", statement: null },
    { period: "2026-07", statement: { id: 4, source: "qonto", file_name: "2026-07-statement.pdf", file_size: 41542,
      fetched_at: "2026-11-01T09:00:00", replaced_at: null, url: "/bank-statements/4.pdf" } },
  ],
};

let posts: string[];
let list: StatementsList;
beforeEach(() => {
  posts = [];
  list = LIST;
  uploads.length = 0;
  vi.spyOn(notifications, "show").mockReturnValue("id");
  vi.spyOn(globalThis, "fetch").mockImplementation(((input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = String(input);
    if (init.method === "POST") {
      posts.push(url);
      return Promise.resolve(new Response(JSON.stringify({ result: {}, notices: [] }), { status: 200 }));
    }
    return Promise.resolve(new Response(JSON.stringify(list), { status: 200 }));
  }) as typeof fetch);
});
afterEach(() => vi.restoreAllMocks());

describe("carte Relevés", () => {
  it("liste les mois, ouvre le PDF et récupère les relevés Qonto", async () => {
    renderWithProviders(<StatementsCard bankAccountId={1} />);
    const link = await screen.findByRole("link", { name: "2026-07-statement.pdf" });
    expect(link).toHaveAttribute("href", "/bank-statements/4.pdf");
    expect(screen.getByText("Manquant")).toBeInTheDocument();
    expect(screen.getByText(/1 mois sans relevé/)).toBeInTheDocument();
    expect(screen.getByText("41 Ko")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Récupérer les relevés" }));
    await waitFor(() => expect(posts).toEqual(["/api/v1/bank-accounts/1/statements/fetch"]));
  });

  it("compte hors Qonto : dépose un relevé PDF pour un mois", async () => {
    list = { ...LIST, qonto: null, upload_months: ["2026-10", "2026-09"],
      items: [{ period: "2026-10", statement: null }] };
    const user = userEvent.setup();
    renderWithProviders(<StatementsCard bankAccountId={2} />);
    await user.click(await screen.findByRole("button", { name: "Déposer un relevé" }));
    expect(screen.queryByRole("button", { name: "Récupérer les relevés" })).not.toBeInTheDocument();
    const dialog = await screen.findByRole("dialog", { name: "Déposer un relevé de compte" });
    const send = within(dialog).getByRole("button", { name: "Déposer" });
    expect(send).toBeDisabled();
    await user.click(within(dialog).getByRole("combobox", { name: "Mois" }));
    await user.click(await screen.findByRole("option", { name: "octobre 2026" }));
    const pdf = new File(["%PDF-1.4"], "releve-octobre.pdf", { type: "application/pdf" });
    await user.upload(dialog.querySelector('input[type="file"]') as HTMLInputElement, pdf);
    await user.click(send);
    await waitFor(() => expect(uploads).toHaveLength(1));
    expect(uploads[0].url).toBe("/api/v1/bank-accounts/2/statements");
    expect(uploads[0].period).toBe("2026-10");
    expect((uploads[0].file as File).name).toBe("releve-octobre.pdf");
  });
});

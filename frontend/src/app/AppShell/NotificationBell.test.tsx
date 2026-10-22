import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { notifications } from "@mantine/notifications";
import { renderWithProviders } from "../../test/render";
import { watchJob } from "../../api/jobs";
import { ago, NotificationBell, NOTIFICATIONS_KEY, type AppNotification } from "./NotificationBell";

const note = (id: number, patch: Partial<AppNotification> = {}): AppNotification => ({
  id, kind: "job_done", level: "success", title: `Synchro ${id} terminée`, message: "3 importée(s).", url: "/bank-accounts/",
  job_id: id * 10, created_at: new Date().toISOString().slice(0, 19), read: false, ...patch,
});

let server: AppNotification[];
let posts: unknown[];
let show: ReturnType<typeof vi.spyOn>;
const json = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));

beforeEach(() => {
  posts = [];
  server = [note(2), note(1, { read: true, level: "danger", title: "Synchro 1 : échec", message: "Qonto injoignable" })];
  show = vi.spyOn(notifications, "show").mockReturnValue("id");
  vi.spyOn(globalThis, "fetch").mockImplementation(((input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = String(input);
    if (url.startsWith("/api/v1/notifications?")) return json({ items: server, meta: { unread: server.filter((n) => !n.read).length } });
    if (url === "/api/v1/notifications/read") {
      const body = JSON.parse(String(init.body));
      posts.push(body);
      server = server.map((n) => (!body.ids || body.ids.includes(n.id) ? { ...n, read: true } : n));
      return json({ marked: 1, meta: { unread: server.filter((n) => !n.read).length } });
    }
    return json({});
  }) as typeof fetch);
});

afterEach(() => vi.restoreAllMocks());

describe("cloche des notifications", () => {
  it("affiche les non lues, la liste et marque comme lu", async () => {
    const user = userEvent.setup();
    renderWithProviders(<NotificationBell />);
    const bell = await screen.findByRole("button", { name: "Notifications : 1 non lue(s)" });
    await user.click(bell);
    const list = await screen.findByRole("list", { name: "Notifications" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);
    expect(within(list).getByText("Qonto injoignable")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Tout marquer comme lu" }));
    await waitFor(() => expect(posts).toEqual([{}]));
    expect(await screen.findByRole("button", { name: "Notifications" })).toBeTruthy();
    expect(show).not.toHaveBeenCalled();  // présentes au premier chargement : pas de message
  });

  it("ouvrir une notification la marque lue", async () => {
    const user = userEvent.setup();
    renderWithProviders(<NotificationBell />, { route: "/" });
    await user.click(await screen.findByRole("button", { name: "Notifications : 1 non lue(s)" }));
    await user.click(screen.getByRole("listitem", { name: "Non lue : Synchro 2 terminée" }));
    await waitFor(() => expect(posts).toEqual([{ ids: [2] }]));
  });

  it("annonce une nouvelle notification, sauf si son job est suivi à l'écran", async () => {
    const { client } = renderWithProviders(<NotificationBell />);
    await screen.findByRole("button", { name: "Notifications : 1 non lue(s)" });
    const unwatch = watchJob(40);
    server = [note(4), note(3, { level: "warning", title: "Factures : erreurs" }), ...server];
    await client.invalidateQueries({ queryKey: NOTIFICATIONS_KEY });
    await waitFor(() => expect(show).toHaveBeenCalledTimes(1));
    expect(show.mock.calls[0][0]).toMatchObject({ title: "Factures : erreurs", color: "paille" });
    unwatch();
  });

  it("formate l'ancienneté", () => {
    const now = Date.parse("2026-10-22T20:00:00Z");
    expect(ago("2026-10-22T19:59:40", now)).toBe("à l'instant");
    expect(ago("2026-10-22T19:45:00", now)).toBe("il y a 15 min");
    expect(ago("2026-10-22T17:00:00", now)).toBe("il y a 3 h");
    expect(ago("2026-10-20T10:00:00", now)).toBe("20/10/2026");
  });
});

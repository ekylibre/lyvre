// Assistant Claude (lot AG9b.a, claudedocs/design_assistant_agricole.md § 7, AGD26) : bouton d'en-tête et tiroir
// de conversation. Réponse diffusée au fil de l'eau (SSE) ; l'assistant lit le dossier et ne passe aucune écriture.
import { Fragment, useEffect, useRef, useState } from "react";
import { ActionIcon, Alert, Badge, Box, Button, Drawer, Group, Loader, Paper, ScrollArea, Select, Stack, Text, Textarea, Tooltip } from "@mantine/core";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocation, useNavigate } from "react-router";
import { ApiError, api, postEventStream } from "../../api/client";

export interface AssistantStatus { applies: boolean; enabled: boolean; available: boolean; message: string | null;
  model: string | null; model_label: string | null; can_propose: boolean; quota_left: number | null; server_key: boolean }
interface Conversation { id: number; title: string; updated_at: string }
export interface AssistantAction { id: number; kind: "entry" | "msa_call" | "deadline" | "navigate"; payload: Record<string, unknown>;
  summary?: string | null; status: string }
interface Message { id: number | string; role: "user" | "assistant"; text: string; tools: string[]; actions?: AssistantAction[] }

/** Ouvre le tiroir de l'assistant avec une question (boutons « Expliquer »), envoyée aussitôt avec un effort élevé. */
export function askAssistant(question: string) {
  window.dispatchEvent(new CustomEvent("lyvre:assistant", { detail: { question, explain: true } }));
}

const euro = (cents: unknown) => (typeof cents === "number" ? `${(cents / 100).toLocaleString("fr-FR", { minimumFractionDigits: 2 })} €` : "");

/** Carte d'une proposition : rien ne s'enregistre depuis la carte, sauf l'échéance après confirmation explicite. */
export function ActionCard({ action, onClose }: { action: AssistantAction; onClose?: () => void }) {
  const navigate = useNavigate();
  const [status, setStatus] = useState(action.status);
  const [error, setError] = useState<string | null>(null);
  const p = action.payload;
  const mark = (value: string, ref?: string) => api.patch(`/api/v1/assistant/proposals/${action.id}`, { status: value, ...(ref ? { result_ref: ref } : {}) })
    .then(() => setStatus(value), () => undefined);
  const go = (url: string) => { onClose?.(); navigate(url); };
  const confirmDeadline = () => {
    setError(null);
    api.post<{ item: { id: number } }>("/api/v1/agenda/states", { deadline_id: p.deadline_id, occurs_on: p.occurs_on, period: p.period,
      status: p.status, note: p.note ?? undefined, done_on: new Date().toISOString().slice(0, 10) })
      .then((r) => mark("accepted", String(r.item.id)), (e) => setError(e instanceof ApiError ? e.message : "Action impossible."));
  };
  const lines = Array.isArray(p.lines) ? (p.lines as { account: string; account_label?: string; debit_cents: number; credit_cents: number }[]) : [];
  return (
    <Paper withBorder p="xs" mt={6} bg="var(--mantine-color-gray-0)">
      <Group justify="space-between" mb={4}>
        <Text size="xs" fw={600}>{action.kind === "entry" ? "Brouillon d'écriture" : action.kind === "msa_call" ? "Appel MSA à enregistrer"
          : action.kind === "deadline" ? "Échéance" : "Écran"}</Text>
        {status !== "open" && <Badge size="xs" color={status === "accepted" ? "lichen" : "gray"}>{status === "accepted" ? "fait" : "ignoré"}</Badge>}
      </Group>
      {action.kind === "entry" && (
        <Box component="table" fz="xs" w="100%">
          <tbody>{lines.map((l, i) => <tr key={i}><td>{l.account} {l.account_label}</td><td style={{ textAlign: "right" }}>{l.debit_cents ? euro(l.debit_cents) : ""}</td>
            <td style={{ textAlign: "right" }}>{l.credit_cents ? euro(l.credit_cents) : ""}</td></tr>)}</tbody>
        </Box>)}
      {action.kind === "msa_call" && <Text size="xs">{String(p.person ?? "")} · échéance {String(p.due_on ?? "")} · {euro(p.amount_cents)}</Text>}
      {action.kind === "deadline" && <Text size="xs">{String(p.title ?? "")} ({String(p.occurs_on ?? "")}) : {p.status === "done" ? "marquer faite" : "ignorer"}{p.note ? ` — ${String(p.note)}` : ""}</Text>}
      {error && <Text size="xs" c="brique">{error}</Text>}
      {status === "open" && (
        <Group gap="xs" mt={6}>
          {action.kind === "entry" && <Button size="compact-xs" onClick={() => go(`/entries/new?proposal_id=${action.id}`)}>Ouvrir le brouillon</Button>}
          {action.kind === "msa_call" && <Button size="compact-xs" onClick={() => go(`/msa/?proposal_id=${action.id}`)}>Ouvrir les appels MSA</Button>}
          {action.kind === "deadline" && <Button size="compact-xs" onClick={confirmDeadline}>Confirmer</Button>}
          {action.kind === "navigate" && <Button size="compact-xs" variant="light" onClick={() => { void mark("accepted"); go(String(p.route)); }}>{String(p.label ?? "Voir")}</Button>}
          <Button size="compact-xs" variant="subtle" color="gray" onClick={() => void mark("ignored")}>Ignorer</Button>
        </Group>)}
    </Paper>
  );
}

const TOOL_LABELS: Record<string, string> = {
  get_agenda: "Échéancier", get_context: "Dossier", get_aids: "Aides", get_balances: "Soldes des comptes",
  get_closing_checks: "Contrôles de clôture", get_deadline_fiche: "Fiche d'échéance", get_margins: "Marges",
  get_msa: "MSA", get_parameter: "Paramètre réglementaire", get_tax_result: "Résultat fiscal", get_vat: "TVA",
  search_entries: "Écritures",
};
const CITATION = /(\[[A-Z]{2,4}-\d{2}\]|\[[a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+\]|\*\*[^*]+\*\*)/g;

/** Rendu simple du Markdown de l'assistant : paragraphes, listes, gras. */
export function AssistantText({ text }: { text: string }) {
  const inline = (line: string) => line.split(CITATION).map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) return <b key={i}>{part.slice(2, -2)}</b>;
    if (/^\[[A-Z]{2,4}-\d{2}\]$/.test(part)) {
      return <Badge key={i} size="xs" variant="light" component="a" href="/agenda/" title="Fiche d'échéance" style={{ cursor: "pointer" }}>{part.slice(1, -1)}</Badge>;
    }
    if (/^\[[a-z].*\]$/.test(part)) return <Badge key={i} size="xs" variant="outline" color="gray" title="Paramètre réglementaire daté">{part.slice(1, -1)}</Badge>;
    return <Fragment key={i}>{part}</Fragment>;
  });
  return (
    <Stack gap={4}>
      {text.split(/\n{2,}/).map((para, i) => {
        const lines = para.split("\n");
        if (lines.every((l) => /^\s*[-*] /.test(l))) {
          return <Box key={i} component="ul" m={0} pl="md">{lines.map((l, j) => <li key={j}><Text size="sm" span>{inline(l.replace(/^\s*[-*] /, ""))}</Text></li>)}</Box>;
        }
        return <Text key={i} size="sm">{lines.map((l, j) => <Fragment key={j}>{j > 0 && <br />}{inline(l.replace(/^#+\s*/, ""))}</Fragment>)}</Text>;
      })}
    </Stack>
  );
}

export function AssistantButton() {
  const { data } = useQuery({ queryKey: ["assistant", "status"], staleTime: 60_000,
    queryFn: () => api.get<{ item: AssistantStatus }>("/api/v1/assistant/status") });
  const [open, setOpen] = useState(false);
  const [pending, setPending] = useState<{ question: string; explain: boolean } | null>(null);
  useEffect(() => {
    const listener = (e: Event) => { setPending((e as CustomEvent).detail); setOpen(true); };
    window.addEventListener("lyvre:assistant", listener);
    return () => window.removeEventListener("lyvre:assistant", listener);
  }, []);
  const status = data?.item;
  if (!status?.applies || !status.enabled) return null;
  return (
    <>
      <Tooltip label="Assistant">
        <ActionIcon variant="default" size={44} aria-label="Assistant" onClick={() => setOpen(true)}>
          <Text fw={700} size="sm">IA</Text>
        </ActionIcon>
      </Tooltip>
      <Drawer opened={open} onClose={() => setOpen(false)} position="right" size="lg" title="Assistant">
        {open && <AssistantPanel status={status} initial={pending} onConsumed={() => setPending(null)} onClose={() => setOpen(false)} />}
      </Drawer>
    </>
  );
}

export function AssistantPanel({ status, initial, onConsumed, onClose }: { status: AssistantStatus;
  initial?: { question: string; explain: boolean } | null; onConsumed?: () => void; onClose?: () => void }) {
  const client = useQueryClient();
  const location = useLocation();
  const { data: list } = useQuery({ queryKey: ["assistant", "conversations"], enabled: status.available,
    queryFn: () => api.get<{ items: Conversation[] }>("/api/v1/assistant/conversations") });
  const [conversationId, setConversationId] = useState<number | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const viewport = useRef<HTMLDivElement>(null);

  useEffect(() => { viewport.current?.scrollTo({ top: viewport.current.scrollHeight }); }, [messages]);
  useEffect(() => {
    if (!initial || !status.available) return;
    onConsumed?.();
    setConversationId(null);
    setMessages([]);
    void send(initial.question, initial.explain);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initial]);

  const load = async (id: number | null) => {
    setConversationId(id);
    setError(null);
    if (id === null) { setMessages([]); return; }
    const data = await api.get<{ item: { messages: Message[] } }>(`/api/v1/assistant/conversations/${id}`);
    setMessages(data.item.messages);
  };

  const send = async (question?: string, explain = false) => {
    const text = (question ?? draft).trim();
    if (!text || busy) return;
    setError(null);
    setBusy("Réflexion…");
    try {
      let id = conversationId;
      if (id === null) {
        id = (await api.post<{ item: Conversation }>("/api/v1/assistant/conversations", {})).item.id;
        setConversationId(id);
      }
      setDraft("");
      const answerId = `a${Date.now()}`;
      setMessages((m) => [...m, { id: `q${Date.now()}`, role: "user", text, tools: [] }, { id: answerId, role: "assistant", text: "", tools: [] }]);
      const fyId = Number(new URLSearchParams(location.search).get("fiscal_year")) || undefined;
      await postEventStream(`/api/v1/assistant/conversations/${id}/messages`,
        { text, explain, page: { route: location.pathname, ...(fyId ? { fiscal_year_id: fyId } : {}) } }, (event) => {
          if (event.type === "text") {
            setBusy(null);
            setMessages((m) => m.map((msg) => (msg.id === answerId ? { ...msg, text: msg.text + String(event.text) } : msg)));
          } else if (event.type === "tool") {
            const name = String(event.name);
            setBusy(`Lecture : ${TOOL_LABELS[name] ?? "dossier"}…`);
            setMessages((m) => m.map((msg) => (msg.id === answerId ? { ...msg, tools: [...msg.tools, name] } : msg)));
          } else if (event.type === "action") {
            const action = event.action as AssistantAction;
            setMessages((m) => m.map((msg) => (msg.id === answerId ? { ...msg, actions: [...(msg.actions ?? []), action] } : msg)));
          } else if (event.type === "error") {
            setError(String(event.message));
          }
        });
      client.invalidateQueries({ queryKey: ["assistant"] });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Assistant indisponible.");
    } finally {
      setBusy(null);
    }
  };

  if (!status.available) return <Alert color="paille">{status.message ?? "Assistant indisponible."}</Alert>;
  return (
    <Stack h="calc(100vh - 90px)" gap="xs">
      <Group gap="xs" wrap="nowrap">
        <Select aria-label="Conversation" size="xs" style={{ flex: 1 }} placeholder="Nouvelle conversation" clearable
          data={(list?.items ?? []).map((c) => ({ value: String(c.id), label: c.title }))}
          value={conversationId ? String(conversationId) : null} onChange={(x) => load(x ? Number(x) : null)} />
        <Button size="compact-sm" variant="default" onClick={() => load(null)}>Nouvelle</Button>
      </Group>
      <ScrollArea style={{ flex: 1 }} viewportRef={viewport}>
        <Stack gap="xs" pr="xs">
          {messages.length === 0 && (
            <Text size="sm" c="dimmed">Posez une question sur votre dossier : échéances à venir, montants à payer, situation de l'exercice…
              L'assistant lit vos données dans Lyvre ; il ne passe aucune écriture et ne remplace pas votre expert-comptable.</Text>)}
          {messages.map((m) => (
            <Paper key={m.id} p="xs" withBorder={m.role === "assistant"} bg={m.role === "user" ? "var(--mantine-color-gray-1)" : undefined}
              ml={m.role === "user" ? "xl" : 0}>
              {m.tools.length > 0 && <Group gap={4} mb={4}>{m.tools.map((t, i) => <Badge key={i} size="xs" variant="light" color="gray">{TOOL_LABELS[t] ?? t}</Badge>)}</Group>}
              {m.text ? <AssistantText text={m.text} /> : m.role === "assistant" && busy ? <Group gap={6}><Loader size="xs" /><Text size="xs" c="dimmed">{busy}</Text></Group> : null}
              {(m.actions ?? []).map((a) => <ActionCard key={a.id} action={a} onClose={onClose} />)}
            </Paper>))}
        </Stack>
      </ScrollArea>
      {error && <Alert color="brique" py={6}>{error}</Alert>}
      <Textarea aria-label="Question" placeholder="Votre question…" autosize minRows={2} maxRows={6} value={draft} disabled={!!busy}
        onChange={(e) => setDraft(e.currentTarget.value)}
        onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void send(); } }} />
      <Group justify="space-between">
        <Text size="xs" c="dimmed">{status.model_label}{status.can_propose ? "" : " · lecture seule"}
          {status.quota_left !== null ? ` · reste ${status.quota_left.toLocaleString("fr-FR")} tokens ce mois` : ""}</Text>
        <Button size="compact-sm" onClick={() => void send()} loading={!!busy} disabled={!draft.trim()}>Envoyer</Button>
      </Group>
    </Stack>
  );
}


/** Bouton « Expliquer » posé à côté d'une alerte : visible seulement si l'assistant est actif. */
export function ExplainButton({ question, label = "Expliquer" }: { question: string; label?: string }) {
  const { data } = useQuery({ queryKey: ["assistant", "status"], staleTime: 60_000,
    queryFn: () => api.get<{ item: AssistantStatus }>("/api/v1/assistant/status") });
  if (!data?.item?.available) return null;
  return <Button size="compact-xs" variant="subtle" onClick={() => askAssistant(question)}>{label}</Button>;
}

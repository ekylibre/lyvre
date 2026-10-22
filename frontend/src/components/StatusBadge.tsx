// Badge de statut (charte, StatusBadge) : toujours un mot, couleur en complément.
import { Badge } from "@mantine/core";

export type Tone = "ok" | "todo" | "gap" | "info" | "neutral";

const TONES: Record<Tone, { bg: string; c: string }> = {
  ok: { bg: "var(--lv-sauge)", c: "var(--lv-lichen-strong)" },
  todo: { bg: "var(--lv-paille-tint)", c: "var(--lv-paille-ink)" },
  gap: { bg: "var(--lv-brique-tint)", c: "var(--lv-brique-ink)" },
  info: { bg: "var(--lv-ardoise-tint)", c: "var(--lv-ardoise)" },
  neutral: { bg: "var(--lv-surface-sunken)", c: "var(--lv-ink-muted)" },
};

export function StatusBadge({ tone, children }: { tone: Tone; children: string }) {
  const colors = TONES[tone];
  return (
    <Badge radius="xl" variant="filled" bg={colors.bg} c={colors.c} tt="none" fw={600}
      leftSection={<span aria-hidden style={{ width: 6, height: 6, borderRadius: 99, background: "currentColor", display: "inline-block" }} />}>
      {children}
    </Badge>
  );
}

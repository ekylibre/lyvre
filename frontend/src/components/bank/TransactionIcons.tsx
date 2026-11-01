// Icônes d'une ligne de relevé (lot TX2) : feu, type d'opération, pièce justificative. La couleur ne porte
// jamais seule l'information : libellé en infobulle et en aria-label.
import { Tooltip } from "@mantine/core";
import { FileQuestion, FileX, Paperclip } from "lucide-react";
import type { AttachmentStatus, Light } from "../../lib/types";
import { transactionType } from "../../lib/transactionTypes";

export const LIGHT_LABELS: Record<Light, string> = { green: "À jour", orange: "À traiter", red: "Anomalie" };
export const LIGHT_COLORS: Record<Light, string> = {
  green: "var(--lv-lichen)", orange: "var(--lv-paille)", red: "var(--lv-brique)",
};

export function LightDot({ light, size = 10 }: { light: Light; size?: number }) {
  return <span aria-hidden style={{ display: "inline-block", width: size, height: size, borderRadius: 99,
    background: LIGHT_COLORS[light], flexShrink: 0 }} />;
}

export function TransactionLight({ light, reasons }: { light?: Light; reasons?: string[] }) {
  if (!light) return null;
  const text = `${LIGHT_LABELS[light]}${reasons?.length ? ` : ${reasons.join(", ")}` : ""}`;
  return (
    <Tooltip label={text} withArrow openDelay={150}>
      <span role="img" aria-label={text} style={{ display: "inline-flex", padding: 4 }}><LightDot light={light} /></span>
    </Tooltip>
  );
}

export function TransactionTypeIcon({ rawType, amountCents }: { rawType?: string | null; amountCents: number }) {
  const { label, icon: Icon } = transactionType(rawType, amountCents);
  return (
    <Tooltip label={label} withArrow openDelay={150}>
      <span role="img" aria-label={label} style={{ display: "inline-flex", color: "var(--lv-ink-muted)" }}>
        <Icon size={16} strokeWidth={1.75} aria-hidden /></span>
    </Tooltip>
  );
}

const ATTACHMENTS = {
  ok: { label: "Justificatif présent", icon: Paperclip, color: "var(--lv-lichen)" },
  missing: { label: "Justificatif manquant", icon: FileX, color: "var(--lv-paille-ink)" },
  lost: { label: "Justificatif perdu", icon: FileQuestion, color: "var(--lv-brique)" },
} as const;

export function AttachmentIcon({ status }: { status: AttachmentStatus }) {
  if (!status) return null;
  const { label, icon: Icon, color } = ATTACHMENTS[status];
  return (
    <Tooltip label={label} withArrow openDelay={150}>
      <span role="img" aria-label={label} style={{ display: "inline-flex", color }}><Icon size={17} strokeWidth={2} aria-hidden /></span>
    </Tooltip>
  );
}

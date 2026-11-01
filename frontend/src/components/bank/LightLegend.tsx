// Légende des feux (lot TX2) : trois pastilles « point + libellé + nombre » qui filtrent le tableau d'un clic
// (un second clic retire le filtre). En mode statique (Rapprochement) : libellés seuls, sans clic.
import { Group, Text, UnstyledButton } from "@mantine/core";
import type { Light } from "../../lib/types";
import { LIGHT_COLORS, LIGHT_LABELS, LightDot } from "./TransactionIcons";

const ORDER: Light[] = ["green", "orange", "red"];
const TINTS: Record<Light, string> = {
  green: "var(--lv-sauge)", orange: "var(--lv-paille-tint)", red: "var(--lv-brique-tint)",
};

export function LightLegend({ counts, value, onChange }: {
  counts?: Record<Light, number>; value?: Light | null; onChange?: (light: Light | null) => void;
}) {
  if (!onChange) {
    return (
      <Group gap="md" aria-label="Légende des feux">
        {ORDER.map((light) => (
          <Group key={light} gap={6} wrap="nowrap"><LightDot light={light} /><Text size="sm" c="dimmed">{LIGHT_LABELS[light]}</Text></Group>
        ))}
      </Group>
    );
  }
  return (
    <Group gap="sm" role="group" aria-label="Filtrer par feu">
      {ORDER.map((light) => {
        const active = value === light;
        return (
          <UnstyledButton key={light} aria-pressed={active} onClick={() => onChange(active ? null : light)}
            style={{ display: "flex", alignItems: "center", gap: 10, minHeight: 44, padding: "6px 14px", borderRadius: 10,
              border: `1px solid ${active ? LIGHT_COLORS[light] : "var(--lv-line)"}`,
              background: active ? TINTS[light] : "var(--lv-surface, transparent)" }}>
            <LightDot light={light} size={12} />
            <Text size="sm" fw={active ? 600 : 500}>{LIGHT_LABELS[light]}</Text>
            <Text size="sm" fw={600} className="lv-num" c={active ? undefined : "dimmed"}>{counts?.[light] ?? 0}</Text>
          </UnstyledButton>
        );
      })}
    </Group>
  );
}

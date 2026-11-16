// Origine d'un objet saisi par une clé d'API (lot AK3, claudedocs/design_api_mcp_aiffel.md § 9.2) : nom de la clé
// (« Aiffel — saisie terrain »), en couleur tant que l'objet n'est pas vérifié.
import { Badge, Tooltip } from "@mantine/core";
import { Bot } from "lucide-react";

export interface AgentOrigin { label: string; external_ref: string | null; pending: boolean; checked_at: string | null }

export function OriginBadge({ origin, size = "sm" }: { origin: AgentOrigin | null | undefined; size?: "xs" | "sm" }) {
  if (!origin) return null;
  const hint = `Saisi par la clé « ${origin.label} »${origin.external_ref ? ` (réf. ${origin.external_ref})` : ""}`
    + (origin.pending ? " : à vérifier." : " : vérifié.");
  return (
    <Tooltip label={hint} multiline w={280}>
      <Badge size={size} variant={origin.pending ? "light" : "outline"} color={origin.pending ? "paille" : "gray"} tt="none"
        leftSection={<Bot size={size === "xs" ? 11 : 13} aria-hidden />}>
        {origin.label}
      </Badge>
    </Tooltip>
  );
}

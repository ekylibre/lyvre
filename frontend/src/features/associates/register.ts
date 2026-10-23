// Registre des parts : lignes du formulaire (associé, nature, reçoit / cède, nombre de parts
// positif) ↔ lignes de l'API (parts signées : + reçoit, − cède).
import { CAPITAL_KINDS, type Movement, type MovementKind, type Nature } from "./types";

export interface LineRow { associate_id: string | null; nature: Nature; direction: "in" | "out"; parts: string }

export interface MovementValues {
  movement_date: string; kind: MovementKind; nominal: string; price: string; description: string; lines: LineRow[];
}

export const newLine = (direction: "in" | "out" = "in"): LineRow => ({ associate_id: null, nature: "full", direction, parts: "" });

/** Sens imposé par le type : parts reçues (reprise, souscription) ou cédées (réduction). */
export function forcedDirection(kind: MovementKind): "in" | "out" | null {
  if (kind === "opening" || kind === "subscription") return "in";
  if (kind === "reduction") return "out";
  return null;
}

const centsText = (cents: number | null) => (cents === null ? "" : (cents / 100).toFixed(2).replace(".", ","));

export function emptyMovement(today: string): MovementValues {
  return { movement_date: today, kind: "subscription", nominal: "", price: "", description: "", lines: [newLine()] };
}

export function fromMovement(m: Movement): MovementValues {
  return {
    movement_date: m.movement_date, kind: m.kind, nominal: centsText(m.nominal_cents), price: centsText(m.price_cents),
    description: m.description ?? "",
    lines: m.lines.map((l) => ({ associate_id: String(l.associate_id), nature: l.nature,
      direction: l.parts < 0 ? "out" : "in", parts: String(Math.abs(l.parts)) })),
  };
}

/** Corps de l'API ; le sens imposé par le type l'emporte sur celui de la ligne. */
export function toPayload(values: MovementValues) {
  const forced = forcedDirection(values.kind);
  return {
    movement_date: values.movement_date, kind: values.kind, description: values.description,
    nominal: CAPITAL_KINDS.includes(values.kind) ? values.nominal : "", price: values.price,
    lines: values.lines.map((l) => {
      const parts = Number.parseInt(l.parts, 10) || 0;
      return { associate_id: l.associate_id ? Number(l.associate_id) : null, nature: l.nature,
        parts: (forced ?? l.direction) === "out" ? -Math.abs(parts) : Math.abs(parts) };
    }),
  };
}

/** Lignes complètes : la prévisualisation peut être demandée. */
export function readyForPreview(values: MovementValues): boolean {
  return !!values.movement_date && values.lines.length > 0
    && values.lines.every((l) => l.associate_id && Number.parseInt(l.parts, 10) > 0)
    && (!CAPITAL_KINDS.includes(values.kind) || values.nominal.trim() !== "");
}

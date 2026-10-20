import type { ComponentType } from "react";

/** Props d'un îlot : objet JSON fourni par la vue Flask (macro island()). */
export type IslandProps = Record<string, unknown>;

export type IslandLoader = () => Promise<{ default: ComponentType<any> }>;

/**
 * Îlots disponibles, chargés à la demande (un fichier JS par îlot).
 * Le nom correspond au premier argument de la macro Jinja island(name, props).
 */
export const islands: Record<string, IslandLoader> = {};

// Affiche son contenu seulement si l'utilisateur peut modifier (pas l'expert-comptable, en
// lecture seule) ou, avec `admin`, s'il administre l'instance.
import type { ReactNode } from "react";
import { useCan } from "../api/session";

export function Can({ admin = false, children }: { admin?: boolean; children: ReactNode }) {
  const can = useCan();
  return <>{(admin ? can.instanceAdmin : can.write) ? children : null}</>;
}

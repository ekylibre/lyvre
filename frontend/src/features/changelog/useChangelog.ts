// Nouveautés (lot R2) : version courante et repère « nouveau » tant que l'utilisateur n'a pas ouvert
// la page depuis la dernière version (préférence `changelog_seen`, initialisée par le serveur à la
// première session).
import { useCurrentSession } from "../../api/session";

export function useChangelogUnseen(): boolean {
  const session = useCurrentSession();
  const current = session.app?.version;
  const seen = session.preferences.changelog_seen as string | undefined;
  return !!current && !!seen && seen !== current;
}

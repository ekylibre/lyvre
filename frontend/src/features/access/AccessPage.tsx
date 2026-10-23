// Configuration › Accès (administrateur de l'instance) : qui accède à cette instance, avec quel
// rôle. Administrateur : tout ; trésorier : saisie, rapprochement, clôture provisoire ;
// expert-comptable : lecture de toute la comptabilité et export FEC, sans modification.
import { Alert, Button } from "@mantine/core";
import { useCan, useCurrentSession } from "../../api/session";
import { PageHeader } from "../../components/PageHeader";
import { MembersManager } from "./MembersManager";

export default function AccessPage() {
  const session = useCurrentSession();
  const can = useCan();
  if (!can.instanceAdmin) {
    return <><PageHeader title="Accès" /><Alert color="ardoise">Réservé à l'administrateur de l'instance.</Alert></>;
  }
  return (
    <MembersManager id="access-members" endpoint="/api/v1/access/members" queryKey={["access-members"]}
      actions={(open) => (
        <PageHeader title="Accès" description={`Personnes qui accèdent à ${session.instance?.label ?? "cette instance"}, et leur rôle.`}
          actions={<Button onClick={open}>Donner un accès</Button>} />
      )} />
  );
}

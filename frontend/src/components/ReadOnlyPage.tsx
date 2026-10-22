// Écrans dont la seule fonction est de modifier (saisie, rapprochement, imports) : en lecture
// seule (expert-comptable), un message remplace l'écran ; l'API refuse de toute façon.
import type { ComponentType } from "react";
import { Alert, Anchor } from "@mantine/core";
import { Eye } from "lucide-react";
import { useCan } from "../api/session";
import { AppLink } from "../app/navigation";
import { PageHeader } from "./PageHeader";

export function ReadOnlyNotice({ title, back }: { title: string; back?: { href: string; label: string } }) {
  return (
    <>
      <PageHeader title={title} />
      <Alert color="ardoise" variant="light" icon={<Eye />} title="Accès en lecture seule">
        Cet écran sert à modifier les comptes : votre accès (expert-comptable) permet de consulter, pas de modifier.
        {back && <> <Anchor component={AppLink} href={back.href}>{back.label}</Anchor></>}
      </Alert>
    </>
  );
}

export function writeOnly<P extends object>(Page: ComponentType<P>, title: string, back?: { href: string; label: string }) {
  function WriteOnlyPage(props: P) {
    const can = useCan();
    return can.write ? <Page {...props} /> : <ReadOnlyNotice title={title} back={back} />;
  }
  WriteOnlyPage.displayName = `writeOnly(${Page.displayName ?? Page.name})`;
  return WriteOnlyPage;
}

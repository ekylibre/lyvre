// Rapport d'activité › Photos (admin) : logo de la structure (commun aux exercices), photo de
// couverture et une par section ; légendes. Déposer une image remplace celle de l'emplacement.
import { useState } from "react";
import { Alert, Button, Card, Center, Group, Image, Loader, Paper, SimpleGrid, Text, TextInput, Title } from "@mantine/core";
import { Dropzone } from "@mantine/dropzone";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ImagePlus } from "lucide-react";
import { api, ApiError } from "../../api/client";
import { showNotices, useAction, type Notice } from "../../api/resources";
import { upload } from "../../api/upload";
import { ConfirmButton } from "../../components/ConfirmButton";
import { FilterBar, useUrlParams } from "../../components/FilterBar";
import { PageHeader } from "../../components/PageHeader";
import { AppLink } from "../../app/navigation";
import { FiscalYearSelect, REPORT_KEY, useReportContext, withFy } from "./shared";

interface Slot { slot: string; label: string; photo: { id: number; caption: string; url: string } | null }
interface Photos { fiscal_year: { id: number; label: string }; slots: Slot[]; logo_url: string | null }

const IMAGES = { "image/png": [".png"], "image/jpeg": [".jpg", ".jpeg"], "image/webp": [".webp"], "image/gif": [".gif"] };

function Caption({ slot, onSave }: { slot: Slot; onSave: (caption: string) => void }) {
  const [caption, setCaption] = useState(slot.photo?.caption ?? "");
  return (
    <TextInput aria-label={`Légende : ${slot.label}`} placeholder="Légende" value={caption} maxLength={300}
      onChange={(e) => setCaption(e.currentTarget.value)}
      onBlur={() => { if (caption !== (slot.photo?.caption ?? "")) onSave(caption); }} />
  );
}

export default function PhotosPage() {
  const client = useQueryClient();
  const { setParams, context } = useReportContext();
  const [params] = useUrlParams({ fy_id: "" });
  const key = [...REPORT_KEY, "photos", params.fy_id];
  const { data } = useQuery({ queryKey: key, enabled: !context.error,
    queryFn: () => api.get<Photos>(`/api/v1/activity-report/photos${params.fy_id ? `?fy_id=${params.fy_id}` : ""}`) });
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const caption = useAction(({ id, text }: { id: number; text: string }) =>
    api.patch<{ notices: Notice[] }>(`/api/v1/activity-report/photos/${id}`, { caption: text }), { invalidate: [key] });
  const remove = useAction((id: number) => api.delete<{ notices: Notice[] }>(`/api/v1/activity-report/photos/${id}`), { invalidate: [key] });
  const removeLogo = useAction(() => api.delete<{ notices: Notice[] }>("/api/v1/activity-report/logo"), { invalidate: [key] });

  const send = async (target: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    if (target !== "logo") { form.append("fy_id", String(data!.fiscal_year.id)); form.append("slot", target); }
    setError(null); setBusy(target);
    try {
      const body = await upload<{ notices: Notice[] }>(target === "logo" ? "/api/v1/activity-report/logo" : "/api/v1/activity-report/photos", form);
      showNotices(body.notices);
      void client.invalidateQueries({ queryKey: key });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Le dépôt a échoué.");
    } finally {
      setBusy(null);
    }
  };
  const drop = (target: string, label: string) => (
    <Dropzone onDrop={(files) => files[0] && void send(target, files[0])} multiple={false} loading={busy === target}
      accept={target === "logo" ? { ...IMAGES, "image/svg+xml": [".svg"] } : IMAGES} onReject={() => setError("Fichier refusé : image attendue.")}
      aria-label={label} p="xs">
      <Group justify="center" gap="xs" mih={48} style={{ pointerEvents: "none" }}><ImagePlus size={18} /><Text size="sm">{label}</Text></Group>
    </Dropzone>
  );

  if (context.error) return <Alert color="ardoise" mt="md">{(context.error as Error).message}</Alert>;
  if (!data) return <Center h={300}><Loader /></Center>;
  return (
    <>
      <PageHeader title={`Photos — exercice ${data.fiscal_year.label}`} description="Couverture et illustrations de section."
        actions={<Button variant="default" component={AppLink} href={withFy("/rapport-activite/", data.fiscal_year.id)}>Aperçu</Button>} />
      <FilterBar><FiscalYearSelect context={context.data} onChange={(fy_id) => setParams({ fy_id })} /></FilterBar>
      {error && <Alert color="brique" role="alert" mb="sm">{error}</Alert>}
      <Paper p="md" mb="lg" maw={720}>
        <Title order={4}>Logo de la structure</Title>
        <Text size="sm" c="dimmed" mb="xs">Commun à tous les exercices : couverture et pieds de page.</Text>
        <Group align="center">
          {data.logo_url
            ? <Image src={data.logo_url} alt="Logo de la structure" h={48} w="auto" fit="contain" bg="#fff" p={4} radius="sm" />
            : <Text size="sm" c="dimmed">Aucun logo : le pictogramme par défaut est utilisé.</Text>}
          <div style={{ flex: 1 }}>{drop("logo", data.logo_url ? "Remplacer le logo (PNG, JPG, SVG…)" : "Déposer le logo (PNG, JPG, SVG…)")}</div>
          {data.logo_url && <ConfirmButton size="compact-md" title="Supprimer le logo de la structure ?" confirmLabel="Supprimer"
            onConfirm={() => removeLogo.mutate()}>Supprimer</ConfirmButton>}
        </Group>
      </Paper>
      <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }}>
        {data.slots.map((s) => (
          <Card key={s.slot} padding="sm">
            <Text fw={600} size="sm" mb={6}>{s.label}</Text>
            {s.photo ? (
              <>
                <Card.Section><Image src={s.photo.url} alt={s.photo.caption || s.label} h={160} fit="cover" /></Card.Section>
                <Group mt="xs" gap="xs" wrap="nowrap">
                  <div style={{ flex: 1 }}><Caption key={s.photo.id} slot={s} onSave={(text) => caption.mutate({ id: s.photo!.id, text })} /></div>
                  <ConfirmButton size="compact-sm" title={`Supprimer la photo « ${s.label} » ?`} confirmLabel="Supprimer"
                    onConfirm={() => remove.mutate(s.photo!.id)}>Supprimer</ConfirmButton>
                </Group>
                <div style={{ marginTop: 8 }}>{drop(s.slot, "Remplacer l'image")}</div>
              </>
            ) : drop(s.slot, "Déposer une image (JPG, PNG)")}
          </Card>
        ))}
      </SimpleGrid>
    </>
  );
}

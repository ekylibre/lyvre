// Configuration › Reçus fiscaux (associations) : éligibilité déclarée et responsabilité,
// articles du CGI, comptes de dons, mode d'émission, signature ; liste des mentions requises.
// Modifiable par l'administrateur de l'instance seulement.
import { useEffect, useState } from "react";
import {
  Alert, Anchor, Button, Center, Checkbox, Fieldset, FileButton, Group, Image, List, Loader, Radio, Stack, Switch, Text,
  TagsInput, TextInput, Textarea, ThemeIcon,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, X } from "lucide-react";
import { api, ApiError } from "../../api/client";
import { showNotices, useAction, type Notice } from "../../api/resources";
import { useCan } from "../../api/session";
import { upload } from "../../api/upload";
import { applyApiError } from "../../components/ApiForm";
import { PageHeader } from "../../components/PageHeader";
import { formatDateTime } from "../../lib/format";
import { AppLink } from "../../app/navigation";

interface Option { value: string; label: string }
interface Settings {
  enabled: boolean; eligibility: string | null; eligibility_detail: string; rescrit_ref: string;
  cgi_articles: string[]; donation_prefixes: string[]; donation_accounts: { code: string; label: string }[];
  default_mode: "annual" | "single"; acknowledged_at: string | null;
  readiness: { key: string; label: string; ok: boolean; url: string | null }[];
  options: { eligibility: Option[]; cgi_articles: Option[]; modes: Option[] };
}
const KEY = ["receipts", "settings"];

export default function ReceiptSettingsPage() {
  const can = useCan();
  const client = useQueryClient();
  const { data } = useQuery({ queryKey: KEY, queryFn: () => api.get<{ item: Settings }>("/api/v1/receipts/settings") });
  const [error, setError] = useState<string | null>(null);
  const [signatureVersion, setSignatureVersion] = useState(0);
  const form = useForm({ initialValues: {
    enabled: false, eligibility: "", eligibility_detail: "", rescrit_ref: "", cgi_articles: [] as string[],
    donation_prefixes: [] as string[], default_mode: "annual", acknowledged: false,
  } });
  useEffect(() => {
    if (!data) return;
    const s = data.item;
    form.setValues({ enabled: s.enabled, eligibility: s.eligibility ?? "", eligibility_detail: s.eligibility_detail,
      rescrit_ref: s.rescrit_ref, cgi_articles: s.cgi_articles, donation_prefixes: s.donation_prefixes,
      default_mode: s.default_mode, acknowledged: false });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data]);
  const store = (item: Settings) => client.setQueryData(KEY, { item });
  const save = useAction((values: typeof form.values) => api.put<{ item: Settings; notices: Notice[] }>("/api/v1/receipts/settings",
    { ...values, eligibility: values.eligibility || null }), { silent: true });
  const removeSignature = useAction(() => api.delete<{ item: Settings; notices: Notice[] }>("/api/v1/receipts/settings/signature"));
  if (!data) return <Center h={300}><Loader /></Center>;
  const s = data.item;
  const readOnly = !can.instanceAdmin;
  const hasSignature = s.readiness.find((r) => r.key === "signature")?.ok ?? false;

  const sendSignature = async (file: File | null) => {
    if (!file) return;
    const body = new FormData();
    body.append("signature", file);
    try {
      const result = await upload<{ item: Settings; notices: Notice[] }>("/api/v1/receipts/settings/signature", body);
      showNotices(result.notices);
      store(result.item);
      setSignatureVersion((v) => v + 1);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Le dépôt a échoué.");
    }
  };

  return (
    <>
      <PageHeader title="Reçus fiscaux" description="Reçus des dons (particuliers et entreprises) : paramètres de la structure." />
      <Stack maw={760}>
        <Alert color="paille" title="Responsabilité de la structure">
          Lyvre n'évalue pas si votre structure peut délivrer des reçus fiscaux. Délivrer un reçu sans y être
          habilité expose à une amende (article 1740 A du CGI). En cas de doute, demandez un rescrit à
          l'administration fiscale.
        </Alert>
        <Fieldset legend="Mentions du reçu">
          <List spacing={4} size="sm" center>
            {s.readiness.map((r) => (
              <List.Item key={r.key} icon={<ThemeIcon size={18} radius="xl" color={r.ok ? "lichen" : "brique"}>
                {r.ok ? <Check size={12} /> : <X size={12} />}</ThemeIcon>}>
                {r.label}{!r.ok && r.url && <> · <Anchor component={AppLink} href={r.url} size="sm">compléter</Anchor></>}
              </List.Item>
            ))}
          </List>
        </Fieldset>
        <form onSubmit={form.onSubmit((values) => {
          setError(null);
          save.mutate(values, {
            onSuccess: (body) => { store(body.item); form.setFieldValue("acknowledged", false); },
            onError: (e) => setError(applyApiError(form, e)),
          });
        })}>
          <Stack>
            {error && <Alert color="brique" role="alert">{error}</Alert>}
            <Fieldset legend="Éligibilité" disabled={readOnly}>
              <Stack>
                <Radio.Group {...form.getInputProps("eligibility")}>
                  <Stack gap="xs">{s.options.eligibility.map((o) => <Radio key={o.value} value={o.value} label={o.label} />)}</Stack>
                </Radio.Group>
                {form.values.eligibility === "other" && <Textarea label="Cas prévu par le CGI" autosize minRows={2} {...form.getInputProps("eligibility_detail")} />}
                <TextInput label="Référence du rescrit fiscal" description="Facultatif." {...form.getInputProps("rescrit_ref")} />
                <Checkbox.Group label="Article(s) du CGI mentionnés sur les reçus" {...form.getInputProps("cgi_articles")}>
                  <Stack gap="xs" mt={4}>{s.options.cgi_articles.map((o) => <Checkbox key={o.value} value={o.value} label={o.label} />)}</Stack>
                </Checkbox.Group>
              </Stack>
            </Fieldset>
            <Fieldset legend="Dons et émission" disabled={readOnly}>
              <Stack>
                <TagsInput label="Comptes de dons" description="Préfixes des comptes de produits dont les lignes, avec un tiers, donnent lieu à reçu (7541 : dons manuels)."
                  {...form.getInputProps("donation_prefixes")} />
                {s.donation_accounts.length > 0 && <Text size="xs" c="dimmed">Comptes couverts : {s.donation_accounts.map((a) => `${a.code} ${a.label}`).join(" · ")}</Text>}
                <Radio.Group label="Mode d'émission par défaut" {...form.getInputProps("default_mode")}>
                  <Group mt={4}>{s.options.modes.map((o) => <Radio key={o.value} value={o.value} label={o.label} />)}</Group>
                </Radio.Group>
              </Stack>
            </Fieldset>
            <Fieldset legend="Signature">
              <Group align="flex-end">
                {hasSignature
                  ? <Image src={`/receipts/signature?v=${signatureVersion}`} alt="Signature" h={80} w="auto" fit="contain" bg="white" p={4} />
                  : <Text size="sm" c="dimmed">Aucune signature : déposez une image PNG ou JPEG (500 Ko au plus).</Text>}
                {!readOnly && (
                  <Group>
                    <FileButton onChange={(f) => void sendSignature(f)} accept="image/png,image/jpeg">
                      {(props) => <Button variant="default" {...props}>{hasSignature ? "Remplacer" : "Déposer la signature"}</Button>}
                    </FileButton>
                    {hasSignature && <Button variant="subtle" color="brique" loading={removeSignature.isPending}
                      onClick={() => removeSignature.mutate(undefined, { onSuccess: (body) => store(body.item) })}>Retirer</Button>}
                  </Group>
                )}
              </Group>
            </Fieldset>
            <Fieldset legend="Activation" disabled={readOnly}>
              <Stack>
                <Checkbox label="Je déclare, au nom de la structure, qu'elle remplit les conditions pour délivrer des reçus fiscaux et j'en assume la responsabilité."
                  {...form.getInputProps("acknowledged", { type: "checkbox" })} error={form.errors.acknowledged} />
                {s.acknowledged_at && <Text size="xs" c="dimmed">Déclaration enregistrée le {formatDateTime(s.acknowledged_at)}.</Text>}
                <Switch label="Reçus fiscaux activés" {...form.getInputProps("enabled", { type: "checkbox" })} error={form.errors.enabled} />
              </Stack>
            </Fieldset>
            {!readOnly && <Group><Button type="submit" loading={save.isPending}>Enregistrer</Button></Group>}
          </Stack>
        </form>
      </Stack>
    </>
  );
}

// Achats › Nouvelle facture : dépôt de la pièce → lecture (Factur-X, texte du PDF ou OCR) →
// formulaire prérempli, pièce affichée à côté. Modification de l'en-tête d'une facture saisie
// non comptabilisée (/purchases/<id>/edit), pièce remplaçable tant qu'elle n'est pas dans Qonto.
import { useEffect, useState, type ReactNode } from "react";
import { useParams, useSearchParams } from "react-router";
import {
  Alert, Anchor, Badge, Button, Center, Checkbox, Fieldset, Grid, Group, List, Loader, Progress, Select, SimpleGrid, Stack, Text, TextInput,
} from "@mantine/core";
import { Dropzone } from "@mantine/dropzone";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { FileUp } from "lucide-react";
import { api, ApiError } from "../../api/client";
import { showNotices, type Notice } from "../../api/resources";
import { upload } from "../../api/upload";
import { PageHeader } from "../../components/PageHeader";
import { formatDate, formatEuros } from "../../lib/format";
import { AppLink, useGoTo } from "../../app/navigation";
import { AttachmentPreview } from "./AttachmentPreview";
import { EMPTY_LINE, cents } from "./lines";
import { LinesEditor } from "./LinesEditor";
import { PURCHASES_KEY, type FormOptions, type LineRow, type Option } from "./types";
import { writeOnly } from "../../components/ReadOnlyPage";

type Values = Record<string, string>;
interface Preview { url: string; mime: string }
interface EntryForm { values: Values; checks: string[]; rows: LineRow[]; warnings: string[]; source: "facturx" | "text" | "ocr" | "none" }
interface Duplicate { id: number; label: string; issue_date: string | null; total_cents: number }

const ACCEPT = { "application/pdf": [".pdf"], "image/jpeg": [".jpg", ".jpeg"], "image/png": [".png"] };
const SOURCES: Record<string, string> = {
  facturx: "Facture électronique Factur-X : valeurs reprises de la facture.",
  text: "Valeurs lues dans le texte du PDF.",
  ocr: "Valeurs lues par OCR : vérifiez chaque champ.",
};

function FileDrop({ onFile, loading, title, hint }: { onFile: (file: File) => void; loading: boolean; title: string; hint: string }) {
  return (
    <Dropzone onDrop={(files) => files[0] && onFile(files[0])} multiple={false} loading={loading} accept={ACCEPT} maxSize={10 * 1024 * 1024}>
      <Group justify="center" mih={120} style={{ pointerEvents: "none" }}>
        <FileUp size={32} />
        <div><Text fw={600}>{title}</Text><Text size="sm" c="dimmed">{hint}</Text></div>
      </Group>
    </Dropzone>
  );
}

function PurchaseFormPage() {
  const editId = Number(useParams().purchase_id) || null;
  const [search] = useSearchParams();
  const goTo = useGoTo();
  const client = useQueryClient();
  const options = useQuery({ queryKey: [...PURCHASES_KEY, "form-options"],
    queryFn: () => api.get<FormOptions & { entities: Option[] }>("/api/v1/purchases/form-options") });
  const header = useQuery({ queryKey: [...PURCHASES_KEY, editId, "header"], enabled: editId !== null, retry: false,
    queryFn: () => api.get<{ values: Values; can_replace_attachment: boolean; preview: Preview | null }>(`/api/v1/purchases/${editId}/header`) });

  const [form, setForm] = useState<EntryForm | null>(search.get("manual") ? { values: {}, checks: [], rows: [EMPTY_LINE], warnings: [], source: "none" } : null);
  const [token, setToken] = useState("");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const [errors, setErrors] = useState<string[]>([]);
  const [duplicates, setDuplicates] = useState<Duplicate[]>([]);
  const [confirmDuplicate, setConfirmDuplicate] = useState(false);
  const [sendToQonto, setSendToQonto] = useState(false); // dépôt dans Qonto : choix explicite
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (header.data) {
      setForm({ values: header.data.values, checks: [], rows: [], warnings: [], source: "none" });
      setPreview(header.data.preview);
    }
  }, [header.data]);
  useEffect(() => { if (!editId && !search.get("manual")) { setForm(null); setToken(""); setPreview(null); } }, [editId, search]);

  const send = async (file: File, url: string) => {
    const data = new FormData();
    data.append("invoice_file", file);
    setErrors([]); setProgress(0);
    try {
      const body = await upload<{ token: string; preview: Preview; form?: EntryForm }>(url, data, setProgress);
      setToken(body.token);
      setPreview(body.preview);
      if (body.form) setForm({ ...body.form, rows: body.form.rows.length ? body.form.rows : [EMPTY_LINE] });
    } catch (e) {
      setErrors([e instanceof ApiError ? e.message : "Le dépôt a échoué."]);
    } finally {
      setProgress(null);
    }
  };

  const title = editId ? `Modifier la facture ${header.data?.values.invoice_number ?? ""}` : "Nouvelle facture d'achat";
  const back = editId ? `/purchases/${editId}` : "/purchases/";
  const pageHeader = (description: string) => (
    <PageHeader title={title} description={description} actions={<Button variant="default" component={AppLink} href={back}>Retour</Button>} />
  );

  if (editId && header.error) {
    return <>{pageHeader("")}<Alert color="paille">{(header.error as Error).message}</Alert></>;
  }
  if (editId && !form) return <Center h={300}><Loader /></Center>;
  if (!form) {
    return (
      <>
        {pageHeader("Déposez la facture (PDF, JPEG ou PNG, 10 Mo maximum) : elle est lue et le formulaire prérempli.")}
        <Stack maw={640}>
          <FileDrop onFile={(f) => void send(f, "/api/v1/purchases/read")} loading={progress !== null}
            title="Déposer la facture ici ou cliquer pour la choisir"
            hint="Facture électronique Factur-X, PDF ou scan / photo (lu par OCR, quelques secondes)." />
          {progress !== null && <Progress value={progress} aria-label="Envoi du fichier" />}
          {errors.length > 0 && <Alert color="brique" role="alert">{errors[0]}</Alert>}
          <Anchor component={AppLink} href="/purchases/new?manual=1">Saisir sans fichier</Anchor>
        </Stack>
      </>
    );
  }

  const v = form.values;
  const set = (patch: Values) => setForm({ ...form, values: { ...v, ...patch } });
  const checked = (name: string) => form.checks.includes(name);
  const field = (name: string, label: string, props: Record<string, unknown> = {}): ReactNode => (
    <TextInput label={<>{label}{checked(name) && <Badge ml={6} size="xs" color="paille" variant="light">à vérifier</Badge>}</>}
      value={v[name] ?? ""} onChange={(e) => set({ [name]: e.currentTarget.value })}
      styles={checked(name) ? { input: { borderColor: "var(--lv-paille)", borderWidth: 2 } } : undefined} {...props} />
  );
  const amount = (name: string, label: string, required = false) => field(name, label, {
    inputMode: "decimal", required, classNames: { input: "lv-num" }, styles: { input: { textAlign: "right", ...(checked(name) ? { borderColor: "var(--lv-paille)", borderWidth: 2 } : {}) } },
  });
  const entities = [{ value: "", label: "— à rattacher plus tard —" }, { value: "new", label: "+ Créer un fournisseur…" }, ...(options.data?.entities ?? [])];
  const qontoUpload = !editId && options.data?.qonto.upload;

  const submit = async () => {
    setSaving(true); setErrors([]);
    const body = { ...v, is_credit_note: v.is_credit_note === "1", token, rows: form.rows, confirm_duplicate: confirmDuplicate,
      send_to_qonto: qontoUpload && token ? sendToQonto : false };
    try {
      const result = editId
        ? await api.patch<{ notices: Notice[]; item?: undefined }>(`/api/v1/purchases/${editId}`, body)
        : await api.post<{ notices: Notice[]; item: { url: string } }>("/api/v1/purchases", body);
      showNotices(result.notices);
      void client.invalidateQueries({ queryKey: PURCHASES_KEY });
      goTo(result.item?.url ?? `/purchases/${editId}`);
    } catch (e) {
      if (e instanceof ApiError && e.code === "duplicate") {
        setDuplicates((e.details.duplicates as Duplicate[]) ?? []);
      } else if (e instanceof ApiError && Array.isArray((e.fields as unknown as { form?: string[] }).form)) {
        setErrors((e.fields as unknown as { form: string[] }).form);
      } else {
        setErrors([e instanceof Error ? e.message : "Erreur inattendue."]);
      }
    } finally {
      setSaving(false);
    }
  };

  const canReplace = editId ? header.data?.can_replace_attachment : false;
  return (
    <>
      {pageHeader(editId ? "Facture saisie, non comptabilisée : en-tête et pièce modifiables."
        : token ? "Vérifiez les valeurs lues puis enregistrez la facture." : "Saisie sans fichier.")}
      <form onSubmit={(e) => { e.preventDefault(); void submit(); }}>
      <Grid gap="lg">
        <Grid.Col span={{ base: 12, lg: preview ? 7 : 12 }}>
            <Stack gap="md">
              {errors.length > 0 && <Alert color="brique" role="alert"><List size="sm">{errors.map((e) => <List.Item key={e}>{e}</List.Item>)}</List></Alert>}
              {form.warnings.length > 0 && <Alert color="paille"><List size="sm">{form.warnings.map((w) => <List.Item key={w}>{w}</List.Item>)}</List></Alert>}
              {SOURCES[form.source] && errors.length === 0 && <Alert color="ardoise" variant="light">{SOURCES[form.source]} Les champs <Badge size="xs" color="paille" variant="light">à vérifier</Badge> sont encadrés.</Alert>}
              {form.source === "none" && token && !editId && <Alert color="gray">Rien n'a pu être lu dans le fichier : saisissez la facture.</Alert>}
              {duplicates.length > 0 && (
                <Alert color="brique" title="Doublon possible">
                  <Text size="sm">{duplicates.map((d, i) => <span key={d.id}>{i > 0 && ", "}<Anchor component={AppLink} href={`/purchases/${d.id}`} size="sm">{d.label}</Anchor> du {formatDate(d.issue_date)} ({formatEuros(d.total_cents)})</span>)}.</Text>
                  <Checkbox mt="xs" label="Ce n'est pas un doublon : enregistrer quand même" checked={confirmDuplicate} onChange={(e) => setConfirmDuplicate(e.currentTarget.checked)} />
                </Alert>
              )}
              <Fieldset legend={<>Fournisseur{checked("supplier_name") && <Badge ml={6} size="xs" color="paille" variant="light">à vérifier</Badge>}</>}>
                <SimpleGrid cols={{ base: 1, md: 2 }}>
                  <Select label="Fournisseur" data={entities} searchable value={v.entity_id ?? ""} allowDeselect={false}
                    description={v.supplier_name ? `Lu sur la facture : « ${v.supplier_name} »` : undefined}
                    onChange={(id) => set({ entity_id: id ?? "", ...(id === "new" && !v.new_name ? { new_name: v.supplier_name ?? "" } : {}) })} />
                  {v.entity_id === "new" && field("new_name", "Nom du nouveau fournisseur", { maxLength: 200 })}
                </SimpleGrid>
                <SimpleGrid cols={{ base: 1, md: 3 }} mt="xs">
                  {field("supplier_vat", "N° de TVA", { maxLength: 30, classNames: { input: "lv-num" } })}
                  {field("supplier_siret", "SIRET", { maxLength: 20, inputMode: "numeric", classNames: { input: "lv-num" } })}
                  {field("supplier_iban", "IBAN", { maxLength: 42, classNames: { input: "lv-num" } })}
                </SimpleGrid>
                <Text size="xs" c="dimmed" mt={4}>Ces identifiants complètent la fiche du fournisseur s'ils y manquent.</Text>
              </Fieldset>
              <Fieldset legend="Facture">
                <SimpleGrid cols={{ base: 1, md: 4 }}>
                  {field("invoice_number", "N° de facture", { maxLength: 100 })}
                  {field("issue_date", "Date", { type: "date", required: true })}
                  {field("due_date", "Échéance", { type: "date" })}
                  <Checkbox mt={30} label={<>Avoir{checked("is_credit_note") && <Badge ml={6} size="xs" color="paille" variant="light">à vérifier</Badge>}</>}
                    checked={v.is_credit_note === "1"} onChange={(e) => set({ is_credit_note: e.currentTarget.checked ? "1" : "" })} />
                </SimpleGrid>
                <SimpleGrid cols={{ base: 1, md: 4 }} mt="xs">
                  {amount("untaxed", "HT")}{amount("tax", "TVA")}{amount("total", "TTC", true)}
                </SimpleGrid>
              </Fieldset>
            </Stack>
        </Grid.Col>
        {preview && (
          <Grid.Col span={{ base: 12, lg: 5 }}>
            <div style={{ position: "sticky", top: 16 }}><AttachmentPreview url={preview.url} mime={preview.mime} height="60vh" /></div>
          </Grid.Col>
        )}
      </Grid>
      {/* Lignes sur toute la largeur : le tableau a huit colonnes. */}
      <Stack gap="md" mt="md">
              {editId ? (canReplace && (
          <Fieldset legend={preview ? "Remplacer la pièce" : "Joindre la pièce"}>
            <FileDrop onFile={(f) => void send(f, "/api/v1/purchases/stage")} loading={progress !== null}
              title={token ? "Nouvelle pièce déposée : elle remplacera l'actuelle à l'enregistrement." : "Déposer la pièce ici ou cliquer pour la choisir"}
              hint="PDF, JPEG ou PNG, 10 Mo maximum." />
            {progress !== null && <Progress mt="xs" value={progress} aria-label="Envoi du fichier" />}
          </Fieldset>
        )) : (
          <Fieldset legend="Lignes">
            <LinesEditor rows={form.rows} onChange={(rows) => setForm({ ...form, rows })} products={options.data?.products ?? []} projects={options.data?.projects}
              accounts={options.data?.charge_accounts ?? []} expected={cents(v.total ?? "")} />
            <Text size="xs" c="dimmed" mt={4}>Produit du catalogue : compte et taux préremplis. Une remise obtenue est une ligne négative (609).
              Le total des lignes doit égaler le TTC pour que la facture soit comptabilisée.</Text>
          </Fieldset>
        )}
        {qontoUpload && (
          <Checkbox label="Envoyer à Qonto" checked={!!token && sendToQonto} disabled={!token} onChange={(e) => setSendToQonto(e.currentTarget.checked)}
            description={token ? "Cochez pour déposer la pièce dans Qonto (factures fournisseurs) à l'enregistrement." : "Envoi impossible sans fichier."} />
        )}
        <Group><Button type="submit" loading={saving}>{editId ? "Enregistrer" : "Enregistrer la facture"}</Button></Group>
      </Stack>
      </form>
    </>
  );
}

export default writeOnly(PurchaseFormPage, "Nouvelle facture d'achat", { href: "/purchases/", label: "Voir les factures d'achat." });

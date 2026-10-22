// Aperçu d'une pièce (PDF dans un cadre, image sinon).
export function AttachmentPreview({ url, mime, height = "70vh" }: { url: string; mime: string; height?: string }) {
  const style = { width: "100%", border: "1px solid var(--lv-line)", borderRadius: 8 };
  return mime === "application/pdf"
    ? <iframe src={url} title="Pièce de la facture" style={{ ...style, height }} />
    : <img src={url} alt="Pièce de la facture" style={{ ...style, height: "auto" }} />;
}

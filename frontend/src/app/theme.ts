// Charte Lyvre (design system « Lyvre », FM11) : couleurs, polices, rayons pour Mantine.
// Les tokens de couleur sont des variables CSS (lyvre.css) ; ce fichier règle Mantine.
import "@fontsource/ibm-plex-sans/400.css";
import "@fontsource/ibm-plex-sans/500.css";
import "@fontsource/ibm-plex-sans/600.css";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";
import "@fontsource/bricolage-grotesque/700.css";
import "@fontsource/bricolage-grotesque/800.css";
import { createTheme, type MantineColorsTuple } from "@mantine/core";

// lichen : 7 = #2F6B4F (primaire clair), 4 = #6FB08E (primaire sombre), 8 = lichen-strong.
const lichen: MantineColorsTuple = [
  "#EEF5F1", "#DDE8DF", "#BCD6C5", "#95BFA6", "#6FB08E", "#4F8F6E", "#3C7D5D", "#2F6B4F",
  "#1E4A36", "#123526",
];
// brique : anomalies et actions destructrices seulement (débits pas en rouge).
const brique: MantineColorsTuple = [
  "#FBEDE9", "#F4D9D2", "#EBB4A6", "#E27D66", "#D2654C", "#C2553D", "#B5462F", "#8A2F1C",
  "#6E2416", "#521A10",
];
// ardoise : information, import bancaire.
const ardoise: MantineColorsTuple = [
  "#EEF3F8", "#DCE5EE", "#B8CBDD", "#8FB0D0", "#6E93B5", "#56799C", "#47698A", "#3B5A78",
  "#2C445B", "#1F3041",
];
// paille : accent or (remplissages, pictos), jamais en texte sur paper.
const paille: MantineColorsTuple = [
  "#FBF4E3", "#F6E7C3", "#F0CB7E", "#E6B75A", "#D9A441", "#C38F2F", "#A97A22", "#8A6118",
  "#6B4A0E", "#4D3509",
];

export const theme = createTheme({
  primaryColor: "lichen",
  colors: { lichen, brique, ardoise, paille, red: brique },
  primaryShade: { light: 7, dark: 4 },
  autoContrast: true,
  fontFamily: "'IBM Plex Sans', system-ui, -apple-system, 'Segoe UI', sans-serif",
  fontFamilyMonospace: "'IBM Plex Mono', ui-monospace, 'SF Mono', Menlo, monospace",
  headings: {
    fontFamily: "'Bricolage Grotesque', 'IBM Plex Sans', system-ui, sans-serif",
    fontWeight: "800",
    sizes: {
      h1: { fontSize: "34px", lineHeight: "40px" },
      h2: { fontSize: "24px", lineHeight: "30px", fontWeight: "700" },
      h3: { fontSize: "18px", lineHeight: "24px", fontWeight: "700" },
    },
  },
  fontSizes: { xs: "12px", sm: "13px", md: "15px", lg: "18px", xl: "24px" },
  radius: { xs: "4px", sm: "6px", md: "10px", lg: "14px", xl: "14px" },
  defaultRadius: "md",
  spacing: { xs: "8px", sm: "12px", md: "16px", lg: "24px", xl: "32px" },
  cursorType: "pointer",
  focusRing: "never", // anneau géré par lyvre.css (:focus-visible, token focus)
  components: {
    Paper: { defaultProps: { radius: "lg", withBorder: true } },
    Badge: { defaultProps: { radius: "xl", variant: "light" } },
  },
});

export const APP_NAME = "Lyvre";

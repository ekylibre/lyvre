// Charte graphique (FM11) : seul fichier à modifier quand la charte définitive arrive,
// avec assets/logo.svg. Valeurs provisoires.
import { createTheme, type MantineColorsTuple } from "@mantine/core";

// Vert « association » provisoire (10 nuances, de la plus claire à la plus foncée).
const brand: MantineColorsTuple = [
  "#e9f8ef", "#d6eedf", "#acdcbe", "#7fca9b", "#59ba7d", "#41b06a",
  "#33ab5f", "#24964e", "#198544", "#037337",
];

export const theme = createTheme({
  primaryColor: "brand",
  colors: { brand },
  primaryShade: { light: 7, dark: 5 },
  fontFamily: "Inter, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif",
  defaultRadius: "sm",
  cursorType: "pointer",
});

export const APP_NAME = "Compta Asso";

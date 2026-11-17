import type { ImageMetadata } from "astro";

// Captures de doc/images/ (copiées par scripts/prebuild.mjs), optimisées par astro:assets.
const files = import.meta.glob<{ default: ImageMetadata }>("../assets/captures/*.png", { eager: true });

export const captures = new Map(
  Object.entries(files).map(([path, mod]) => [path.split("/").pop()!, mod.default] as const),
);

export function capture(name: string): ImageMetadata {
  const image = captures.get(name);
  if (!image) throw new Error(`Capture « ${name} » absente de doc/images/ (lancer make captures).`);
  return image;
}

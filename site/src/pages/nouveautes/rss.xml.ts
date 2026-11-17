import rss from "@astrojs/rss";
import type { APIRoute } from "astro";
import { KINDS, plain, versions } from "../../lib/data";

/** Flux des versions publiées : une entrée par version, ses nouveautés en liste. */
export const GET: APIRoute = (context) =>
  rss({
    title: "Nouveautés de Lyvre",
    description: "Les versions de Lyvre, logiciel libre de comptabilité : nouveautés, améliorations, corrections.",
    site: context.site!,
    items: versions.slice(0, 30).map((v) => ({
      title: `${v.version} · ${v.title}`,
      link: `/nouveautes/${v.version}/`,
      pubDate: new Date(`${v.date}T12:00:00Z`),
      content: `<ul>${v.entries
        .map((e) => `<li><strong>${KINDS[e.kind]}</strong> : ${plain(e.text).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" })[c]!)}</li>`)
        .join("")}</ul>`,
    })),
    customData: "<language>fr-FR</language>",
  });

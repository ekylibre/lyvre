import type { APIRoute } from "astro";
import { current } from "../lib/data";

/** Version publiée, lisible par d'autres outils (SP-9). */
export const GET: APIRoute = () =>
  new Response(JSON.stringify({ version: current.version, date: current.date, title: current.title }), {
    headers: { "content-type": "application/json; charset=utf-8" },
  });

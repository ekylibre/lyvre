// Point d'entrée de la SPA (coquille app/templates/spa.html).
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router/dom";
import { Providers, createQueryClient } from "./app/providers";
import { createRouter } from "./app/router";

const router = createRouter();
const queryClient = createQueryClient();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Providers client={queryClient}>
      <RouterProvider router={router} />
    </Providers>
  </StrictMode>,
);

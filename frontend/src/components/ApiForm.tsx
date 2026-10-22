// Formulaires branchés sur l'API : erreurs 422 posées sur les champs (`fields`), message
// général sinon (charte : dire ce qui se passe et quoi faire).
import type { ReactNode } from "react";
import { Alert, Button, Group, Stack } from "@mantine/core";
import type { UseFormReturnType } from "@mantine/form";
import { ApiError } from "../api/client";

/** Champs en erreur → formulaire ; renvoie le message à afficher en tête (ou null). */
export function applyApiError<T>(form: UseFormReturnType<T>, error: unknown): string | null {
  if (error instanceof ApiError) {
    const fields = Object.keys(error.fields ?? {});
    if (fields.length) {
      form.setErrors(error.fields);
      return fields.length > 1 ? error.message : null;
    }
    return error.message;
  }
  return error instanceof Error ? error.message : "Erreur inattendue.";
}

export function FormBody({ error, children, submitLabel, onCancel, loading }: {
  error?: string | null; children: ReactNode; submitLabel: string; onCancel: () => void; loading?: boolean;
}) {
  return (
    <Stack gap="md">
      {error && <Alert color="brique" role="alert">{error}</Alert>}
      {children}
      <Group justify="flex-end" gap="sm" mt="xs">
        <Button variant="default" onClick={onCancel}>Annuler</Button>
        <Button type="submit" loading={loading}>{submitLabel}</Button>
      </Group>
    </Stack>
  );
}

// Action destructive ou irréversible : confirmation explicite avant l'appel (F7).
import type { ReactNode } from "react";
import { Button, Text, type ButtonProps } from "@mantine/core";
import { modals } from "@mantine/modals";

type ConfirmButtonProps = ButtonProps & {
  /** Question posée (« Supprimer le journal VT ? »). */
  title: string;
  /** Conséquences précisées sous la question. */
  message?: ReactNode;
  confirmLabel?: string;
  danger?: boolean;
  onConfirm: () => void;
  children: ReactNode;
};

export function confirmAction({ title, message, confirmLabel = "Confirmer", danger = true, onConfirm }: {
  title: string; message?: ReactNode; confirmLabel?: string; danger?: boolean; onConfirm: () => void;
}) {
  modals.openConfirmModal({
    title,
    children: message ? <Text size="sm">{message}</Text> : null,
    labels: { confirm: confirmLabel, cancel: "Annuler" },
    confirmProps: { color: danger ? "red" : undefined },
    onConfirm,
  });
}

export function ConfirmButton({
  title, message, confirmLabel, danger = true, onConfirm, children, ...buttonProps
}: ConfirmButtonProps) {
  return (
    <Button color={danger ? "red" : undefined} variant="light" {...buttonProps}
      onClick={() => confirmAction({ title, message, confirmLabel, danger, onConfirm })}>
      {children}
    </Button>
  );
}

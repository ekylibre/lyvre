// Création / modification sans quitter la liste (F7) : modale (formulaire court) ou
// panneau latéral (formulaire plus long).
import type { ReactNode } from "react";
import { Drawer, Modal } from "@mantine/core";

interface FormContainerProps {
  opened: boolean;
  onClose: () => void;
  title: ReactNode;
  children: ReactNode;
  size?: string | number;
}

export function FormModal({ opened, onClose, title, children, size = "md" }: FormContainerProps) {
  return (
    <Modal opened={opened} onClose={onClose} title={title} size={size} centered>
      {children}
    </Modal>
  );
}

export function FormDrawer({ opened, onClose, title, children, size = "lg" }: FormContainerProps) {
  return (
    <Drawer opened={opened} onClose={onClose} title={title} size={size} position="right">
      {children}
    </Drawer>
  );
}

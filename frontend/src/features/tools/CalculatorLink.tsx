// Lien vers une calculette depuis un écran existant (lot AG12.b) : « Calculette », instance agricole seulement.
import { Button } from "@mantine/core";
import { Calculator } from "lucide-react";
import { useCurrentSession } from "../../api/session";
import { AppLink } from "../../app/navigation";

export function CalculatorLink({ code, label = "Calculette" }: { code: string; label?: string }) {
  if (useCurrentSession().instance?.chart !== "agri") return null;
  return <Button variant="default" leftSection={<Calculator size={16} />} component={AppLink} href={`/outils/${code}`}>{label}</Button>;
}

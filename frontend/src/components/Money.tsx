// Montants en centimes : saisie (« 1 234,56 ») et affichage (« 1 234,56 € »).
import { NumberInput, Text, type NumberInputProps, type TextProps } from "@mantine/core";
import { formatEuros } from "../lib/format";

type MoneyInputProps = Omit<NumberInputProps, "value" | "onChange"> & {
  /** Centimes ; null = vide. */
  value: number | null;
  onChange: (cents: number | null) => void;
};

export function MoneyInput({ value, onChange, ...props }: MoneyInputProps) {
  return (
    <NumberInput
      decimalSeparator=","
      thousandSeparator=" "
      decimalScale={2}
      fixedDecimalScale
      hideControls
      rightSection="€"
      inputMode="decimal"
      classNames={{ input: "lv-num" }}
      styles={{ input: { textAlign: "right" } }}
      {...props}
      value={value === null ? "" : value / 100}
      onChange={(v) => onChange(v === "" || v === null ? null : Math.round(Number(v) * 100))}
    />
  );
}

/**
 * Montant affiché (charte : chasse fixe, chiffres tabulaires, « − » typographique).
 * Un débit n'est pas en rouge ; `anomaly` (écart, erreur) le met en brique.
 */
export function MoneyText({ cents, plus = false, anomaly = false, ...props }:
  TextProps & { cents: number; plus?: boolean; anomaly?: boolean }) {
  return (
    <Text component="span" className="lv-num" c={anomaly ? "var(--lv-brique)" : undefined}
      style={{ whiteSpace: "nowrap" }} {...props}>
      {formatEuros(cents, { plus })}
    </Text>
  );
}

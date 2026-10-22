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
      {...props}
      value={value === null ? "" : value / 100}
      onChange={(v) => onChange(v === "" || v === null ? null : Math.round(Number(v) * 100))}
    />
  );
}

export function MoneyText({ cents, colored = false, ...props }: TextProps & { cents: number; colored?: boolean }) {
  return (
    <Text component="span" inherit c={colored && cents < 0 ? "red" : undefined}
      style={{ whiteSpace: "nowrap", fontVariantNumeric: "tabular-nums" }} {...props}>
      {formatEuros(cents)}
    </Text>
  );
}

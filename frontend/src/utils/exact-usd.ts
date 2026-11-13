import { normalizeServerDecimalNotation } from '@/pages/policy-form';

const maxExactUsdTextLength = 4096;
const exactUsdPattern = /^[+-]?\d+(?:\.\d+)?$/;

type ParsedUsd = { units: bigint; scale: number };

function parseExactUsd(value: string | null | undefined): ParsedUsd | null {
  if (value == null || value.length > maxExactUsdTextLength) return null;
  const normalized = normalizeServerDecimalNotation(value);
  if (normalized.length > maxExactUsdTextLength || !exactUsdPattern.test(normalized)) return null;
  const negative = normalized.startsWith('-');
  const unsigned = normalized.replace(/^[+-]/, '');
  const [whole = '0', fraction = ''] = unsigned.split('.');
  const units = BigInt(`${whole}${fraction}`);
  return { units: negative ? -units : units, scale: fraction.length };
}

/** Return true/false for a valid exact API USD decimal, or null when it is unavailable/malformed. */
export function isNegativeExactUsd(value: string | null | undefined): boolean | null {
  const parsed = parseExactUsd(value);
  return parsed === null ? null : parsed.units < 0n;
}

/** Return true only when a valid exact API USD decimal is mathematically zero. */
export function isZeroExactUsd(value: string | null | undefined): boolean | null {
  const parsed = parseExactUsd(value);
  return parsed === null ? null : parsed.units === 0n;
}

/** Add API USD decimal strings without converting through floating-point; invalid or absent inputs are withheld. */
export function sumExactUsd(values: readonly (string | null | undefined)[]): string | null {
  if (values.length === 0) return null;
  const parsed = values.map(parseExactUsd);
  if (parsed.some((value) => value === null)) return null;
  const valid = parsed as ParsedUsd[];
  const scale = Math.max(...valid.map((value) => value.scale));
  const total = valid.reduce(
    (sum, value) => sum + value.units * 10n ** BigInt(scale - value.scale),
    0n,
  );
  const sign = total < 0n ? '-' : '';
  const digits = (total < 0n ? -total : total).toString().padStart(scale + 1, '0');
  return scale ? `${sign}${digits.slice(0, -scale)}.${digits.slice(-scale)}` : `${sign}${digits}`;
}

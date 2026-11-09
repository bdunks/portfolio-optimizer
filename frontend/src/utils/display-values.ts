export type ExactDisplayValue = string | null | undefined;

/** Preserve API decimal text exactly; presentation never converts it through a JS number. */
export function formatUsd(value: ExactDisplayValue, unavailableLabel = 'Unavailable'): string {
  if (value == null) return unavailableLabel;
  if (value === '') return 'Not provided';
  return `${value} USD`;
}

/** Preserve API percentage text exactly; presentation never converts it through a JS number. */
export function formatPercent(value: ExactDisplayValue, unavailableLabel = 'Unavailable'): string {
  if (value == null) return unavailableLabel;
  if (value === '') return 'Not provided';
  return `${value}%`;
}

export function displayCount(value: number | null | undefined): string {
  return value == null ? 'Unavailable' : String(value);
}

import { describe, expect, it } from 'vitest';
import { formatPercent, formatUsd } from './display-values';

describe('exact display formatting', () => {
  it('keeps money precision and distinguishes unavailable, blank, and zero', () => {
    expect(formatUsd(null)).toBe('Unavailable');
    expect(formatUsd(undefined)).toBe('Unavailable');
    expect(formatUsd('')).toBe('Not provided');
    expect(formatUsd('0.0000')).toBe('0.0000 USD');
    expect(formatUsd('12345678901234567890.1234567890')).toBe(
      '12345678901234567890.1234567890 USD',
    );
    expect(formatUsd(null, 'Not returned by API')).toBe('Not returned by API');
  });

  it('keeps percentage precision and distinguishes unavailable, blank, and zero', () => {
    expect(formatPercent(null)).toBe('Unavailable');
    expect(formatPercent(undefined)).toBe('Unavailable');
    expect(formatPercent('')).toBe('Not provided');
    expect(formatPercent('0.0000')).toBe('0.0000%');
    expect(formatPercent('5.309900000000000001')).toBe('5.309900000000000001%');
  });
});

import { describe, expect, it } from 'vitest';
import { isNegativeExactUsd, isZeroExactUsd, sumExactUsd } from './exact-usd';

describe('exact USD arithmetic', () => {
  it('sums decimal values without floating-point rounding and preserves the greatest scale', () => {
    expect(sumExactUsd(['0.10', '0.20', '-0.05'])).toBe('0.25');
    expect(sumExactUsd(['-9007199254740993.0001', '9007199254740994.0000'])).toBe('0.9999');
    expect(sumExactUsd(['1', '2.5000'])).toBe('3.5000');
  });

  it('normalizes supported server decimal notation and distinguishes invalid or missing input', () => {
    expect(sumExactUsd(['1e2', '-25.00'])).toBe('75.00');
    expect(isNegativeExactUsd('-0.0001')).toBe(true);
    expect(isNegativeExactUsd('0.0000')).toBe(false);
    expect(isZeroExactUsd('0E-8')).toBe(true);
    expect(isZeroExactUsd('-0E-8')).toBe(true);
    expect(isZeroExactUsd('.0')).toBeNull();
    expect(isZeroExactUsd('1e-8')).toBe(false);
    expect(isZeroExactUsd('-1e-8')).toBe(false);
    expect(isZeroExactUsd(null)).toBeNull();
    expect(isZeroExactUsd('invalid')).toBeNull();
    expect(isNegativeExactUsd(null)).toBeNull();
    expect(sumExactUsd(['1.00', 'invalid'])).toBeNull();
    expect(sumExactUsd([null, '2.00'])).toBeNull();
    expect(sumExactUsd([])).toBeNull();
  });
});

import { describe, expect, it } from 'vitest';
import {
  exactDecimalSumIsHundred,
  targetActivationIssues,
  type EditableSleeve,
} from './policy-form';

function sleeve(
  key: string,
  target: string,
  parent: string | null = null,
  enabled = true,
): EditableSleeve {
  return {
    sleeve_key: key,
    display_name: key,
    parent_sleeve_key: parent,
    target_pct: target,
    drift_band_pp: '0.25',
    enabled,
  };
}

describe('policy exact target validation', () => {
  it('sums decimal strings exactly without binary floating-point tolerance', () => {
    expect(exactDecimalSumIsHundred(['45.0000', '24', '17.00', '14', '0.000'])).toBe(true);
    expect(exactDecimalSumIsHundred(['0.1', '99.9'])).toBe(true);
    expect(exactDecimalSumIsHundred(['99.9999999999999999', '0'])).toBe(false);
    expect(exactDecimalSumIsHundred(['50', 'not-a-number'])).toBe(false);
  });

  it('validates top-level and each enabled nested target independently', () => {
    const valid = [
      sleeve('us', '45'),
      sleeve('dividend', '25'),
      sleeve('cash', '30'),
      sleeve('us-etf', '100', 'us'),
      sleeve('direct-index', '0', 'us'),
    ];
    expect(targetActivationIssues(valid)).toEqual([]);
    expect(
      targetActivationIssues([...valid, sleeve('ignored-disabled', '99', null, false)]),
    ).toEqual([]);
    expect(targetActivationIssues([sleeve('us', '45'), sleeve('other', '54.999999')])).toEqual([
      'Enabled top-level sleeve targets must total exactly 100%.',
    ]);
    expect(targetActivationIssues([sleeve('us', '100'), sleeve('us-etf', '99.9', 'us')])).toEqual([
      'Enabled child targets of “us” must total exactly 100%.',
    ]);
  });
});

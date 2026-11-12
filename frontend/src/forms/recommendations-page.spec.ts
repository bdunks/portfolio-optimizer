import { describe, expect, it } from 'vitest';
import {
  proposedTradeDateSchema,
  recommendationFilterDefaults,
  recommendationFilterFormSchema,
  recommendationTopNDefaults,
  recommendationTopNFormSchema,
  savedRunIdSchema,
} from './recommendations-page';

describe('recommendations page form schemas', () => {
  it('allows blank and calendar-valid dates without timezone or trading-calendar rules', () => {
    expect(proposedTradeDateSchema.safeParse('').success).toBe(true);
    expect(proposedTradeDateSchema.safeParse('2028-02-29').success).toBe(true);
    expect(proposedTradeDateSchema.safeParse('2027-02-29').success).toBe(false);
    expect(proposedTradeDateSchema.safeParse('2028-2-09').success).toBe(false);
  });

  it('requires a trimmed-nonempty saved ID without imposing UUID validation', () => {
    expect(savedRunIdSchema.safeParse('  ').success).toBe(false);
    const runId = '  run id/with-punctuation  ';
    expect(savedRunIdSchema.parse(runId)).toBe(runId);
  });

  it('keeps raw API filter keys and rank sorting in the filter form state', () => {
    expect(recommendationFilterDefaults).toEqual({
      sleeve: '',
      action: '',
      term: '',
      benefit: '',
      warning: '',
      groupType: '',
      sortOrder: 'rank-ascending',
    });
    expect(
      recommendationFilterFormSchema.safeParse({
        ...recommendationFilterDefaults,
        sleeve: 'historical-sleeve-key',
        groupType: 'unrecognized-historical-group-type',
        action: 'SELL',
        term: 'LT',
        benefit: 'unavailable',
        warning: 'without',
        sortOrder: 'rank-descending',
      }).success,
    ).toBe(true);
  });

  it('preserves the original top-N count inputs, including values normalized to zero', () => {
    expect(recommendationTopNDefaults).toEqual({ topN: 3 });
    for (const topN of [3, '2.6', '-1', '']) {
      expect(recommendationTopNFormSchema.safeParse({ topN }).success).toBe(true);
    }
  });
});

import { describe, expect, it } from 'vitest';
import {
  displayMoney,
  isMatchingCurrentRun,
  type CurrentPortfolioVersion,
  type CurrentRunVersion,
} from './overview-state';

const portfolio = {
  status: 'ready',
  sync: { generation: 7 },
  active_policy_revision_id: 'policy-current',
} satisfies CurrentPortfolioVersion;

const run = {
  source_generation: 7,
  policy_revision_id: 'policy-current',
} satisfies CurrentRunVersion;

describe('overview comparison safeguards', () => {
  it('only matches a current run for the current portfolio generation and policy', () => {
    expect(isMatchingCurrentRun(portfolio, run, 'current', false)).toBe(true);
    expect(isMatchingCurrentRun(portfolio, run, 'saved', false)).toBe(false);
    expect(isMatchingCurrentRun(portfolio, run, 'stale', true)).toBe(false);
    expect(isMatchingCurrentRun(portfolio, run, 'current', true)).toBe(false);
    expect(
      isMatchingCurrentRun(portfolio, { ...run, source_generation: 6 }, 'current', false),
    ).toBe(false);
    expect(
      isMatchingCurrentRun(
        portfolio,
        { ...run, policy_revision_id: 'policy-old' },
        'current',
        false,
      ),
    ).toBe(false);
  });

  it('keeps unavailable monetary values unavailable rather than displaying zero', () => {
    expect(displayMoney(null)).toBe('Unavailable');
    expect(displayMoney(undefined)).toBe('Unavailable');
    expect(displayMoney('12.3400')).toBe('12.3400 USD');
  });
});

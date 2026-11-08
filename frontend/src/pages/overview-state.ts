import type { OptimizerRecommendationsResponse, PortfolioReadyResponse } from '@/types/api';

export type CurrentPortfolioVersion = Pick<
  PortfolioReadyResponse,
  'status' | 'active_policy_revision_id'
> & {
  sync: Pick<PortfolioReadyResponse['sync'], 'generation'>;
};
export type CurrentRunVersion = Pick<
  OptimizerRecommendationsResponse,
  'source_generation' | 'policy_revision_id'
>;

export function isMatchingCurrentRun(
  portfolio: CurrentPortfolioVersion | null,
  run: CurrentRunVersion | null,
  view: 'current' | 'saved' | 'stale' | null,
  isStale: boolean,
): boolean {
  return (
    portfolio !== null &&
    portfolio.status === 'ready' &&
    run !== null &&
    view === 'current' &&
    !isStale &&
    run.source_generation === portfolio.sync.generation &&
    run.policy_revision_id === portfolio.active_policy_revision_id
  );
}

export function displayMoney(value: string | null | undefined): string {
  return value == null || value === '' ? 'Unavailable' : `${value} USD`;
}

export function displayCount(value: number | null | undefined): string {
  return value == null ? 'Unavailable' : String(value);
}

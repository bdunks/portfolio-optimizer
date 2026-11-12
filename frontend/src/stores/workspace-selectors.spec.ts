import { describe, expect, it } from 'vitest';
import type {
  HealthResponse,
  OptimizerRecommendationsResponse,
  PolicyRevisionResponse,
} from '../types/api';
import type { PortfolioReadyResponse } from '../types/api';
import type { WorkspaceResourceFreshness } from '../types/workspace-resources';
import {
  selectPortfolioLabelContext,
  selectResourceFreshnessNotices,
  selectRunPresentation,
  selectWorkspaceReadiness,
} from './workspace-selectors';

const health = {
  status: 'ok',
  schema_ready: true,
  broker_mode: 'fake',
  live_broker_enabled: false,
  order_submission_enabled: false,
} satisfies HealthResponse;
const portfolio = {
  status: 'ready',
  active_policy_revision_id: 'policy-1',
  sync: { generation: 3, complete: true },
} as unknown as PortfolioReadyResponse;
const activePolicy = {
  id: 'policy-1',
  activation_errors: [],
} as unknown as PolicyRevisionResponse;
const currentRun = {
  run_id: 'run-1',
  source_generation: 3,
  policy_revision_id: 'policy-1',
  portfolio_effects: null,
} as unknown as OptimizerRecommendationsResponse;
const freshResources = {
  health: { status: 'fresh', confirmedAt: '2026-01-01T00:00:00Z' },
  portfolio: { status: 'fresh', confirmedAt: '2026-01-01T00:00:00Z' },
  policy: { status: 'fresh', confirmedAt: '2026-01-01T00:00:00Z' },
  lots: { status: 'not-loaded', confirmedAt: null },
  washSales: { status: 'not-loaded', confirmedAt: null },
  activity: { status: 'not-loaded', confirmedAt: null },
} satisfies WorkspaceResourceFreshness;

function presentation(overrides: Partial<Parameters<typeof selectRunPresentation>[0]> = {}) {
  return selectRunPresentation({
    run: currentRun,
    summary: null,
    view: 'current',
    proposedRunIsStale: false,
    health,
    portfolio,
    activePolicy,
    resourceFreshness: freshResources,
    ...overrides,
  });
}

describe('shared workspace lifecycle selectors', () => {
  it('requires confirmed, matching portfolio and active policy metadata for readiness', () => {
    expect(
      selectWorkspaceReadiness({
        health,
        portfolio,
        activePolicy,
        resourceFreshness: freshResources,
      }).canRunOptimizer,
    ).toBe(true);
    expect(
      selectWorkspaceReadiness({
        health,
        portfolio,
        activePolicy,
        resourceFreshness: {
          ...freshResources,
          policy: { status: 'not-loaded', confirmedAt: null },
        },
      }).canRunOptimizer,
    ).toBe(false);
    expect(
      selectWorkspaceReadiness({
        health,
        portfolio,
        activePolicy: { ...activePolicy, id: 'policy-2' },
        resourceFreshness: freshResources,
      }).dataReady,
    ).toBe(false);
    expect(
      selectWorkspaceReadiness({
        health,
        portfolio,
        activePolicy,
        resourceFreshness: { ...freshResources, policy: { status: 'stale', confirmedAt: null } },
      }).canRunOptimizer,
    ).toBe(false);
    expect(
      selectWorkspaceReadiness({
        health,
        portfolio,
        activePolicy,
        resourceFreshness: freshResources,
        syncPending: true,

        resourceReadsPending: true,
      }),
    ).toMatchObject({ dataReady: true, pending: true, canRunOptimizer: false });
  });

  it('centralizes current, saved, stale and unverified run provenance/effects gates', () => {
    expect(presentation()).toMatchObject({
      state: 'current',
      currentRunMatches: true,
      effectsAvailable: true,
      provenanceLabel: 'Current run · API context',
    });
    expect(
      presentation({ portfolio: { ...portfolio, sync: { ...portfolio.sync, generation: 4 } } }),
    ).toMatchObject({ state: 'stale', currentRunMatches: false, effectsAvailable: false });
    expect(
      presentation({ portfolio: { ...portfolio, active_policy_revision_id: 'policy-2' } }),
    ).toMatchObject({ state: 'unverified', currentRunMatches: false, effectsAvailable: false });
    expect(
      presentation({
        resourceFreshness: { ...freshResources, policy: { status: 'stale', confirmedAt: null } },
      }),
    ).toMatchObject({ state: 'unverified', effectsAvailable: false });
    expect(presentation({ resourceReadsPending: true })).toMatchObject({
      state: 'unverified',
      currentRunMatches: false,
      effectsAvailable: false,
    });
    expect(
      presentation({
        resourceFreshness: {
          ...freshResources,
          policy: { status: 'not-loaded', confirmedAt: null },
        },
      }),
    ).toMatchObject({ state: 'unverified', effectsAvailable: false });
    expect(presentation({ reviewMutationPending: true })).toMatchObject({
      state: 'pending',
      currentRunMatches: false,
      effectsAvailable: false,
      reviewMutationPending: true,
      provenanceLabel: 'Review update pending · prior run withheld',
    });
    expect(
      presentation({
        view: 'saved',
        portfolio: null,
        activePolicy: null,
        resourceFreshness: { ...freshResources, portfolio: { status: 'error', confirmedAt: null } },
      }),
    ).toMatchObject({ state: 'saved', effectsAvailable: true, currentRunMatches: false });
    expect(presentation({ view: 'stale' })).toMatchObject({
      state: 'stale',
      effectsAvailable: false,
    });
  });

  it('labels cached and unavailable data honestly after failed resource reads', () => {
    expect(
      selectResourceFreshnessNotices({
        ...freshResources,
        portfolio: { status: 'stale', confirmedAt: '2026-01-01T00:00:00Z' },
        policy: { status: 'error', confirmedAt: null },
      }),
    ).toEqual([
      'The latest portfolio request failed; cached data is being shown. Last confirmed 2026-01-01T00:00:00Z.',
      'active policy data is unavailable because the latest request failed.',
    ]);
  });
  it('uses portfolio API keys unless active-policy and portfolio revisions match', () => {
    const portfolioForRevision = (revisionId: string | null) =>
      ({ ...portfolio, active_policy_revision_id: revisionId }) as PortfolioReadyResponse;
    const policyForRevision = (revisionId: string, label: string) =>
      ({
        id: revisionId,
        sleeves: [{ sleeve_key: 'us', display_name: label }],
      }) as PolicyRevisionResponse;
    const keys = ['us', 'transition_nested'];

    expect(
      selectPortfolioLabelContext({
        portfolio: portfolioForRevision('policy-a'),
        activePolicy: policyForRevision('policy-b', 'Policy B US'),
        sleeveKeys: keys,
      }),
    ).toMatchObject({
      revisionMismatch: true,
      labels: { us: 'us', transition_nested: 'transition_nested' },
    });
    expect(
      selectPortfolioLabelContext({
        portfolio: portfolioForRevision('policy-a'),
        activePolicy: policyForRevision('policy-a', 'Policy A US'),
        sleeveKeys: keys,
      }),
    ).toMatchObject({
      revisionsMatch: true,
      revisionMismatch: false,
      labels: { us: 'Policy A US', transition_nested: 'Unavailable (active policy label)' },
    });
  });
});

// @vitest-environment jsdom
import { flushPromises } from '@vue/test-utils';
import { createPinia, setActivePinia } from 'pinia';
import { afterEach, describe, expect, it } from 'vitest';
import { createMemoryHistory, createRouter } from 'vue-router';
import type {
  OptimizerRecommendationsResponse,
  RecommendationLegResponse,
  SelectedLotResponse,
} from '@/types/api';
import { workspaceQueryKeys } from '@/composables/queries/workspace-queries';
import { mountWorkspaceHarness, seedCurrentRunForTest } from '@/test-utils/workspace-harness';
import { mountWithWorkspace } from '@/test-utils/workspace-mount';
import type { PortfolioResponse } from '@/services/api';
import SelectedBasketReviewPage from './SelectedBasketReviewPage.vue';

const mountedWrappers: Array<{ unmount: () => void }> = [];
const frozenContext = {
  available: true,
  source: 'policy_revision',
  policy_revision_id: 'policy-r1',
  revision_number: 1,
  created_at: '2025-01-01T00:00:00Z',
  activated_at: '2025-01-01T00:00:00Z',
  sleeves: [],
  settings: {},
  allowed_securities: [],
  overrides: [],
  unavailable_reason: null,
} as const;

function lot(
  brokerLotId: string,
  realizedPl: string,
  selected: boolean,
  stLt: 'ST' | 'LT' = 'ST',
): SelectedLotResponse {
  return {
    broker_lot_id: brokerLotId,
    shares: '1',
    acquired_date: '2024-01-15',
    adjusted_basis_usd: '24.00',
    st_lt: stLt,
    realized_pl_usd: realizedPl,
    selected,
  };
}

function sellLeg(selected = true): RecommendationLegResponse {
  return {
    leg_id: 'sell-aapl',
    side: 'SELL',
    ticker: 'AAPL',
    shares: '2',
    estimated_unit_price_usd: '20.00',
    estimated_notional_usd: '40.00',
    net_st_realized_usd: '-1.25',
    net_lt_realized_usd: '0.00',
    selected,
    group_ids: ['group-a'],
    sequence: 1,
    dependencies: [],
    selected_lots: [
      lot('BROKER-LOT-ST', '-1.2500', selected, 'ST'),
      lot('BROKER-LOT-LT', '3.0000', selected, 'LT'),
      lot('BROKER-LOT-UNSELECTED', '-99.00', false),
    ],
    details: {},
  };
}

function buyLeg(selected = true, sequence = 3): RecommendationLegResponse {
  return {
    leg_id: 'buy-shared',
    side: 'BUY',
    ticker: 'VTI',
    shares: selected ? '1' : '0',
    estimated_unit_price_usd: '50.00',
    estimated_notional_usd: selected ? '50.00' : '0.00',
    net_st_realized_usd: '0.00',
    net_lt_realized_usd: '0.00',
    selected,
    group_ids: ['group-a', 'group-b'],
    sequence,
    dependencies: ['sell-aapl'],
    selected_lots: [],
    details: {},
  };
}

function runFixture(overrides: Partial<OptimizerRecommendationsResponse> = {}) {
  return {
    run_id: 'run-review-1',
    status: 'demo',
    mode: 'recommendations_only',
    policy_revision_id: 'policy-r1',
    source_generation: 7,
    as_of: '2025-02-01T12:00:00Z',
    solver_version: 'DEMO',
    demo: true,
    actionable: false,
    input_fingerprint: 'review-fixture',
    source_checksum: null,
    batch_settings: {},
    estimated_realized_st_usd: '0.10',
    estimated_realized_lt_usd: '-0.03',
    estimated_tax_benefit_usd: null,
    estimated_tax_benefit_status: 'tax_profile_incomplete',
    lots_sold_count: 2,
    positions_exited_count: 0,
    orders_count: 2,
    cash_before_usd: null,
    cash_after_usd: null,
    portfolio_effects: null,
    constraints_satisfied: null,
    no_trade_reason: null,
    warnings: [],
    tax_profile_configured: false,
    frozen_display_context: frozenContext,
    groups: [],
    consolidated_legs: [sellLeg(), buyLeg(), buyLeg(true, 3)],
    ...overrides,
  } as unknown as OptimizerRecommendationsResponse;
}

function mountReviewPage(
  run: OptimizerRecommendationsResponse | null = runFixture(),
  view: 'current' | 'saved' | 'stale' = 'current',
) {
  const pinia = createPinia();
  setActivePinia(pinia);
  const { workspace, queryClient } = mountWorkspaceHarness();
  if (run) {
    seedCurrentRunForTest(workspace, run);
    workspace.currentRunView = view;
  }
  queryClient.setQueryData(workspaceQueryKeys.health, {
    status: 'ok',
    schema_ready: true,
    broker_mode: 'demo',
    live_broker_enabled: false,
    order_submission_enabled: false,
  });
  queryClient.setQueryData(workspaceQueryKeys.portfolio, {
    status: 'ready',
    active_policy_revision_id: 'policy-r1',
    sync: { generation: 7, complete: true },
  } as unknown as PortfolioResponse);
  queryClient.setQueryData(workspaceQueryKeys.policy, {
    active: { id: 'policy-r1', activation_errors: [] },
    drafts: [],
    superseded: [],
  });
  const router = createRouter({ history: createMemoryHistory(), routes: [] });
  const wrapper = mountWithWorkspace(SelectedBasketReviewPage, {
    attachTo: document.body,
    global: { plugins: [pinia, router] },
  });
  mountedWrappers.push(wrapper);
  return { wrapper, workspace, queryClient };
}

afterEach(() => {
  mountedWrappers.splice(0).forEach((wrapper) => wrapper.unmount());
});

describe('SelectedBasketReviewPage', () => {
  it('renders only confirmed canonical selected legs and exact selected SELL lots', async () => {
    const { wrapper } = mountReviewPage();
    await flushPromises();

    expect(wrapper.get('h1').text()).toBe('Selected trades');
    expect(document.activeElement).toBe(wrapper.get('h1').element);
    expect(wrapper.get('[data-review-state="current"]').text()).toContain('not order approval');
    expect(wrapper.text()).toContain('run-review-1');
    expect(wrapper.text()).toContain('2025-02-01T12:00:00Z');
    expect(wrapper.text()).toContain('Frozen policy provenance');

    const legHeadings = wrapper.findAll('article.leg-card h3').map((heading) => heading.text());
    expect(legHeadings).toEqual(['Sequence 1 · SELL AAPL', 'Sequence 3 · BUY VTI']);
    expect(wrapper.text()).toContain('Requires API leg(s): sell-aapl');
    expect(wrapper.text()).toContain('BROKER-LOT-ST');
    expect(wrapper.text()).toContain('BROKER-LOT-LT');
    expect(wrapper.text()).not.toContain('BROKER-LOT-UNSELECTED');
    expect(wrapper.findAll('article.leg-card')).toHaveLength(2);
    expect(wrapper.findAll('[role="checkbox"]')).toHaveLength(0);

    expect(wrapper.get('#selected-basket-financials-title').text()).toBe(
      'Selected basket financial summary',
    );
    expect(wrapper.text()).toContain('Gross losses (selected SELL lots only)');
    expect(wrapper.text()).toContain('1.2500 USD');
    expect(wrapper.text()).toContain('Signed realized ST P/L (API estimate)');
    expect(wrapper.text()).toContain('0.10 USD');
    expect(wrapper.text()).toContain('-0.03 USD');
    expect(wrapper.text()).toContain('0.07 USD');
    expect(wrapper.text()).toContain('Unavailable (tax_profile_incomplete)');
    expect(wrapper.text()).toContain('not current remaining or available inventory');
    expect(wrapper.text()).toContain('Back to Recommendations to edit the selection');
  });

  it('withholds current basket details and totals when raw current state is unverified or stale', async () => {
    const { wrapper, queryClient, workspace } = mountReviewPage();
    await flushPromises();
    expect(wrapper.text()).toContain('BROKER-LOT-ST');
    workspace.reviewMutationCount = 1;
    await flushPromises();
    expect(wrapper.get('[data-review-state="pending"]').text()).toContain('withheld');
    expect(wrapper.text()).not.toContain('BROKER-LOT-ST');
    expect(wrapper.find('#selected-basket-financials-title').exists()).toBe(false);
    workspace.reviewMutationCount = 0;

    queryClient.setQueryData(workspaceQueryKeys.health, {
      status: 'ok',
      schema_ready: false,
      broker_mode: 'demo',
      live_broker_enabled: false,
      order_submission_enabled: false,
    });
    await flushPromises();
    expect(wrapper.get('[data-review-state="unverified"]').text()).toContain('withheld');
    expect(wrapper.text()).not.toContain('BROKER-LOT-ST');
    expect(wrapper.find('#selected-basket-financials-title').exists()).toBe(false);

    queryClient.setQueryData(workspaceQueryKeys.health, {
      status: 'ok',
      schema_ready: true,
      broker_mode: 'demo',
      live_broker_enabled: false,
      order_submission_enabled: false,
    });
    workspace.currentRunView = 'stale';
    await flushPromises();
    expect(wrapper.get('[data-review-state="stale"]').text()).toContain('withheld');
    expect(wrapper.text()).not.toContain('BROKER-LOT-ST');

    workspace.currentRunView = 'current';
    queryClient.setQueryData(workspaceQueryKeys.policy, {
      active: { id: 'policy-r2', activation_errors: [] },
      drafts: [],
      superseded: [],
    });
    await flushPromises();
    expect(wrapper.get('[data-review-state="unverified"]').text()).toContain('withheld');
    expect(wrapper.text()).not.toContain('BROKER-LOT-ST');

    queryClient.setQueryData(workspaceQueryKeys.policy, {
      active: { id: 'policy-r1', activation_errors: [] },
      drafts: [],
      superseded: [],
    });
    queryClient.setQueryData(workspaceQueryKeys.portfolio, {
      status: 'ready',
      active_policy_revision_id: 'policy-r1',
      sync: { generation: 8, complete: true },
    });
    await flushPromises();
    expect(wrapper.get('[data-review-state="stale"]').text()).toContain('withheld');
    expect(wrapper.text()).not.toContain('BROKER-LOT-ST');
  });

  it('treats a saved run as explicitly historical and never overlays current generation', async () => {
    const { wrapper } = mountReviewPage(runFixture(), 'saved');
    await flushPromises();

    expect(wrapper.get('[data-review-state="saved"]').text()).toContain('Historical saved run');
    expect(wrapper.text()).toContain('Not overlaid on historical run');
    expect(wrapper.text()).toContain('BROKER-LOT-ST');
    expect(wrapper.text()).toContain('1.2500 USD');
  });

  it('shows honest empty states for confirmed no-selection and no-run cases', async () => {
    const noSelection = mountReviewPage(
      runFixture({ consolidated_legs: [sellLeg(false), buyLeg(false)] }),
    );
    await flushPromises();
    expect(noSelection.wrapper.text()).toContain('No trades selected');
    expect(noSelection.wrapper.find('#selected-basket-financials-title').exists()).toBe(false);

    const noRun = mountReviewPage(null);
    await flushPromises();
    expect(noRun.wrapper.text()).toContain('No recommendation run is loaded');
    expect(noRun.wrapper.text()).toContain('does not automatically analyze a portfolio');
    expect(noRun.wrapper.text()).not.toContain('Selected basket financial summary');
  });

  it('withholds gross loss and signed ST/LT net when financial inputs are malformed', async () => {
    const malformedLeg = sellLeg();
    malformedLeg.selected_lots[0]!.realized_pl_usd = 'not-a-decimal';
    const { wrapper } = mountReviewPage(
      runFixture({
        consolidated_legs: [malformedLeg],
        estimated_realized_st_usd: 'malformed',
      }),
    );
    await flushPromises();

    expect(wrapper.text()).toContain('Gross losses (selected SELL lots only)');
    expect(wrapper.text()).toContain(
      'Unavailable (selected-lot realized P/L is missing or malformed)',
    );
    expect(wrapper.text()).toContain('Unavailable (not returned as a valid API decimal)');
    expect(wrapper.text()).toContain('Unavailable (ST/LT API estimates are missing or malformed)');
  });
});

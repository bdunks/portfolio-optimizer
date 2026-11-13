// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createMemoryHistory, createRouter } from 'vue-router';
import { createPinia, setActivePinia } from 'pinia';
import type { OptimizerRecommendationsResponse, USTransitionResponse } from '@/types/api';

import RecommendationsPage from './RecommendationsPage.vue';
import {
  mountWorkspaceHarness,
  seedCurrentRunForTest,
  currentRunForTest,
} from '@/test-utils/workspace-harness';

import { workspaceQueryKeys } from '@/composables/queries/workspace-queries';
import { getTestQueryClient, getTestQueryClientForPinia } from '@/test-utils/workspace-mount';
function frozenContext(displayName = 'Frozen US equity') {
  return {
    available: true,
    source: 'policy_revision' as const,
    policy_revision_id: 'policy-r1',
    revision_number: 1,
    created_at: '2025-01-01T00:00:00Z',
    activated_at: '2025-01-01T00:00:00Z',
    sleeves: [
      {
        sleeve_key: 'us',
        display_name: displayName,
        sort_order: 1,
        parent_sleeve_key: null,
        target_pct: '100.0000',
        drift_band_pp: '5.0000',
        enabled: true,
        is_direct_index_container: true,
        is_direct_index_sleeve: false,
        is_transition_destination: false,
        is_cash_sleeve: false,
      },
    ],
    settings: { target_retained_net_loss_usd: '3210.00' },
    allowed_securities: [],
    overrides: [],
    unavailable_reason: null,
  };
}

function transitionResponse(childKeys: string[], label: string): USTransitionResponse {
  const snapshot = {
    us_sleeve_value_usd: '100.00',
    us_sleeve_whole_portfolio_pct: '100.0000',
    etf_progress_pct: '0.0000',
    children: Object.fromEntries(
      childKeys.map((key) => [
        key,
        {
          value_usd: '100.00',
          within_us_sleeve_pct: `${100 / childKeys.length}.0000`,
          whole_portfolio_pct: `${100 / childKeys.length}.0000`,
        },
      ]),
    ),
  };
  return {
    sleeve_key: 'us',
    transition_destination_sleeve_key: childKeys[0] ?? null,
    label,
    current: snapshot,
    proposed_basket: snapshot,
    target: {
      us_sleeve_whole_portfolio_pct: '100.0000',
      children: Object.fromEntries(
        childKeys.map((key) => [
          key,
          {
            within_us_sleeve_pct: `${100 / childKeys.length}.0000`,
            whole_portfolio_pct: `${100 / childKeys.length}.0000`,
          },
        ]),
      ),
    },
  };
}
function distinctTransitionResponse(): USTransitionResponse {
  return {
    sleeve_key: 'us',
    transition_destination_sleeve_key: 'nested',
    label: 'Synthetic US transition',
    current: {
      us_sleeve_value_usd: '100.00',
      us_sleeve_whole_portfolio_pct: '40.0000',
      etf_progress_pct: '10.0000',
      children: {
        nested: {
          value_usd: '10.00',
          within_us_sleeve_pct: '10.0000',
          whole_portfolio_pct: '4.0000',
        },
      },
    },
    proposed_basket: {
      us_sleeve_value_usd: '101.00',
      us_sleeve_whole_portfolio_pct: '41.0000',
      etf_progress_pct: '20.0000',
      children: {
        nested: {
          value_usd: '20.00',
          within_us_sleeve_pct: '20.0000',
          whole_portfolio_pct: '8.0000',
        },
      },
    },
    target: {
      us_sleeve_whole_portfolio_pct: '50.0000',
      children: { nested: { within_us_sleeve_pct: '50.0000', whole_portfolio_pct: '25.0000' } },
    },
  };
}

function withRunTransition(
  run: OptimizerRecommendationsResponse,
  transition: USTransitionResponse,
): OptimizerRecommendationsResponse {
  return {
    ...run,
    portfolio_effects: {
      allocation: run.portfolio_effects?.allocation ?? {
        current: null,
        proposed: null,
        target: null,
      },
      us_transition: transition,
    },
  };
}

function frozenContextWithTransitionLabels() {
  const context = frozenContext();
  const usSleeve = context.sleeves[0]!;
  return {
    ...context,
    sleeves: [
      usSleeve,
      {
        ...usSleeve,
        sleeve_key: 'historical-us-direct',
        display_name: 'Historical direct-index sleeve',
        sort_order: 2,
        parent_sleeve_key: 'us',
        target_pct: '60.0000',
        is_direct_index_container: false,
        is_direct_index_sleeve: true,
      },
      {
        ...usSleeve,
        sleeve_key: 'historical-us-etf',
        display_name: 'Historical replacement ETF sleeve',
        sort_order: 3,
        parent_sleeve_key: 'us',
        target_pct: '40.0000',
        is_direct_index_container: false,
        is_direct_index_sleeve: false,
      },
    ],
  };
}
function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

function urlOf(input: RequestInfo | URL): URL {
  const value =
    typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
  return new URL(value, 'http://127.0.0.1:9000');
}

function makeRun(
  runId = 'run-current',
  selectedIds: string[] = [],
): OptimizerRecommendationsResponse {
  const selected = new Set(selectedIds);
  const allocation = {
    current: { total_portfolio_usd: '100.00', sleeve_weights_pct: { us: '100.0000' } },
    proposed: { total_portfolio_usd: '100.00', sleeve_weights_pct: { us: '100.0000' } },
    target: { sleeve_weights_pct: { us: '100.0000' } },
  };
  const groups = [
    {
      group_id: 'group-a',
      rank: 1,
      group_type: 'demo_loss_harvest',
      sleeve_key: 'us',
      rationale: 'API supplied rationale for AAPL lot harvest.',
      estimated_benefit_usd: null,
      impact: {
        demo: true,
        wash_status: 'not_validated_demo',
        selected_sell_lots_count: selected.has('group-a') ? 1 : 0,
        sell_proceeds_usd: '20.00',
        realized_st_usd: '-4.00',
        realized_lt_usd: '0.00',
        replacement_buy_shares: selected.size ? '1' : '0',
        replacement_buy_cost_usd: selected.size ? '50.00' : '0.00',
        cash_after_usd: '20.00',
        portfolio_effects: { allocation, us_transition: null },
        risk_tracking_score: null,
      },
      dependencies: [],
      selected: selected.has('group-a'),
      rejected: false,
      note: null,
      rejection_reason: null,
      leg_ids: ['sell-a', 'buy-shared'],
      warnings: [],
    },
    {
      group_id: 'group-b',
      rank: 2,
      group_type: 'demo_loss_harvest',
      sleeve_key: 'us',
      rationale: 'API supplied rationale for MSFT lot harvest.',
      estimated_benefit_usd: null,
      impact: {
        demo: true,
        wash_status: 'not_validated_demo',
        selected_sell_lots_count: selected.has('group-b') ? 1 : 0,
        sell_proceeds_usd: '30.00',
        realized_st_usd: '0.00',
        realized_lt_usd: '-2.00',
        replacement_buy_shares: selected.size ? '1' : '0',
        replacement_buy_cost_usd: selected.size ? '50.00' : '0.00',
        cash_after_usd: '30.00',
        portfolio_effects: { allocation, us_transition: null },
        risk_tracking_score: null,
      },
      dependencies: [],
      selected: selected.has('group-b'),
      rejected: false,
      note: null,
      rejection_reason: null,
      leg_ids: ['sell-b', 'buy-shared'],
      warnings: ['DEMO wash status not validated'],
    },
  ];
  const legs = [
    {
      leg_id: 'sell-a',
      side: 'SELL',
      ticker: 'AAPL',
      shares: '1',
      estimated_unit_price_usd: '20.00',
      estimated_notional_usd: '20.00',
      net_st_realized_usd: '-4.00',
      net_lt_realized_usd: '0.00',
      selected: selected.has('group-a'),
      group_ids: ['group-a'],
      sequence: 1,
      dependencies: [],
      selected_lots: [
        {
          broker_lot_id: 'BROKER-A1',
          shares: '1',
          acquired_date: '2024-01-15',
          adjusted_basis_usd: '24.00',
          st_lt: 'ST',
          realized_pl_usd: '-4.00',
          selected: selected.has('group-a'),
        },
      ],
      details: {},
    },
    {
      leg_id: 'sell-b',
      side: 'SELL',
      ticker: 'MSFT',
      shares: '1',
      estimated_unit_price_usd: '30.00',
      estimated_notional_usd: '30.00',
      net_st_realized_usd: '0.00',
      net_lt_realized_usd: '-2.00',
      selected: selected.has('group-b'),
      group_ids: ['group-b'],
      sequence: 2,
      dependencies: [],
      selected_lots: [
        {
          broker_lot_id: 'BROKER-B1',
          shares: '1',
          acquired_date: '2023-01-15',
          adjusted_basis_usd: '32.00',
          st_lt: 'LT',
          realized_pl_usd: '-2.00',
          selected: selected.has('group-b'),
        },
      ],
      details: {},
    },
    {
      leg_id: 'buy-shared',
      side: 'BUY',
      ticker: 'VTI',
      shares: selected.size ? '1' : '0',
      estimated_unit_price_usd: '50.00',
      estimated_notional_usd: selected.size ? '50.00' : '0.00',
      net_st_realized_usd: '0.00',
      net_lt_realized_usd: '0.00',
      selected: selected.size > 0,
      group_ids: ['group-a', 'group-b'],
      sequence: 3,
      dependencies: selected.size ? ['sell-a', 'sell-b'] : [],
      selected_lots: [],
      details: {},
    },
  ];
  return {
    run_id: runId,
    status: 'demo',
    mode: 'recommendations_only',
    policy_revision_id: 'policy-r1',
    source_generation: 7,
    as_of: '2025-02-01T12:00:00Z',
    solver_version: 'DEMO',
    demo: true,
    actionable: false,
    input_fingerprint: 'synthetic-fingerprint',
    source_checksum: null,
    batch_settings: { max_sell_lots_per_batch: 2 },
    estimated_realized_st_usd: selected.size ? '-4.00' : '0.00',
    estimated_realized_lt_usd: selected.size ? '-2.00' : '0.00',
    estimated_tax_benefit_usd: null,
    estimated_tax_benefit_status: 'optimizer_unavailable',
    lots_sold_count: selected.size,
    positions_exited_count: 0,
    orders_count: selected.size ? 3 : 0,
    cash_before_usd: null,
    cash_after_usd: null,
    portfolio_effects: { allocation, us_transition: null },
    constraints_satisfied: null,
    no_trade_reason: null,
    warnings: [],
    tax_profile_configured: false,
    frozen_display_context: frozenContext(),
    groups,
    consolidated_legs: legs,
  } as unknown as OptimizerRecommendationsResponse;
}

function makeMultiLotRun(
  runId: string,
  selectedLotIds: string[],
  totals: { shares: string; notional: string; selectedLotCount: number; realizedSt: string },
): OptimizerRecommendationsResponse {
  const selected = new Set(selectedLotIds);
  const base = makeRun(runId, totals.selectedLotCount > 0 ? ['group-a'] : []);
  return {
    ...base,
    estimated_realized_st_usd: totals.realizedSt,
    estimated_realized_lt_usd: '0.00',
    lots_sold_count: totals.selectedLotCount,
    orders_count: totals.selectedLotCount > 0 ? 2 : 0,
    groups: base.groups.map((group) =>
      group.group_id === 'group-a'
        ? {
            ...group,
            selected: totals.selectedLotCount > 0,
            impact: {
              ...group.impact,
              selected_sell_lots_count: totals.selectedLotCount,
              sell_proceeds_usd: totals.notional,
              realized_st_usd: totals.realizedSt,
              cash_after_usd: totals.notional,
            },
          }
        : group,
    ),
    consolidated_legs: base.consolidated_legs.map((leg) =>
      leg.leg_id === 'sell-a'
        ? {
            ...leg,
            shares: totals.shares,
            estimated_notional_usd: totals.notional,
            net_st_realized_usd: totals.realizedSt,
            selected: totals.selectedLotCount > 0,
            selected_lots: [
              { ...leg.selected_lots[0]!, selected: selected.has('BROKER-A1') },
              {
                broker_lot_id: 'BROKER-A2',
                shares: '1',
                acquired_date: '2024-02-01',
                adjusted_basis_usd: '24.00',
                st_lt: 'ST',
                realized_pl_usd: '-4.00',
                selected: selected.has('BROKER-A2'),
              },
            ],
          }
        : leg,
    ),
  };
}

function withGroupAnnotations(
  run: OptimizerRecommendationsResponse,
  annotations: Record<string, { note: string | null; rejectionReason: string | null }>,
): OptimizerRecommendationsResponse {
  return {
    ...run,
    groups: run.groups.map((group) => ({
      ...group,
      note: annotations[group.group_id]?.note ?? null,
      rejection_reason: annotations[group.group_id]?.rejectionReason ?? null,
    })),
  };
}

function readyPortfolio() {
  return {
    status: 'ready',
    demo: true,
    source: 'fixture',
    account: { display_name: 'Demo account', account_type: 'brokerage', tax_treatment: null },
    as_of: '2025-02-01T12:00:00Z',
    cash_usd: '0.00',
    settled_buying_power_usd: '0.00',
    positions_market_value_usd: '100.00',
    portfolio_total_usd: '100.00',
    position_count: 0,
    positions: [],
    active_policy_revision_id: 'policy-r1',
    unassigned_tickers: [],
    coverage: {},
    sync: {
      generation: 7,
      complete: true,
      started_at: null,
      completed_at: '2025-02-01T12:00:00Z',
      last_error_code: null,
      last_error_summary: null,
    },
    allocation: { current: null, proposed: null, target: null },
    us_transition: null,
  };
}

function portfolioWithTransition(revisionId: string) {
  const child = {
    value_usd: '100.00',
    within_us_sleeve_pct: '100.0000',
    whole_portfolio_pct: '100.0000',
  };
  const snapshot = {
    us_sleeve_value_usd: '100.00',
    us_sleeve_whole_portfolio_pct: '100.0000',
    etf_progress_pct: '0.0000',
    children: { transition_nested: child },
  };
  return {
    ...readyPortfolio(),
    active_policy_revision_id: revisionId,
    allocation: {
      current: { sleeve_weights_pct: { us: '65.0000' } },
      proposed: null,
      target: null,
    },
    us_transition: {
      sleeve_key: 'us',
      transition_destination_sleeve_key: 'transition_nested',
      label: 'Portfolio transition label',
      current: snapshot,
      proposed_basket: snapshot,
      target: {
        us_sleeve_whole_portfolio_pct: '100.0000',
        children: {
          transition_nested: { within_us_sleeve_pct: '100.0000', whole_portfolio_pct: '100.0000' },
        },
      },
    },
  };
}

function setup(run: OptimizerRecommendationsResponse | null = makeRun()) {
  const pinia = createPinia();
  setActivePinia(pinia);
  const store = mountWorkspaceHarness().workspace;
  if (run) {
    seedCurrentRunForTest(store, run);
    store.currentRunView = 'current';
  }
  return { pinia, store };
}

function mountRecommendationsPage(pinia: ReturnType<typeof createPinia>) {
  const queryClient = getTestQueryClientForPinia(pinia);
  queryClient.setQueryData(workspaceQueryKeys.health, {
    status: 'ok',
    schema_ready: true,
    broker_mode: 'demo',
    live_broker_enabled: false,
    order_submission_enabled: false,
  });
  queryClient.setQueryData(workspaceQueryKeys.portfolio, readyPortfolio());
  queryClient.setQueryData(workspaceQueryKeys.policy, {
    active: {
      id: 'policy-r1',
      activation_errors: [],
      sleeves: [{ sleeve_key: 'us', display_name: 'Active US (renamed)' }],
    },
    drafts: [],
    superseded: [],
  });
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/:pathMatch(.*)*', component: { template: '<div />' } }],
  });
  return mount(RecommendationsPage, { global: { plugins: [pinia, router] } });
}

async function openRecommendationGroup(
  wrapper: ReturnType<typeof mountRecommendationsPage>,
  groupId: string,
): Promise<void> {
  const trigger = wrapper.get(`button[data-group-id="${groupId}"]`);
  if (trigger.attributes('aria-expanded') !== 'true') await trigger.trigger('click');
  expect(trigger.attributes('aria-expanded')).toBe('true');
  await flushPromises();
}

beforeEach(() => vi.unstubAllGlobals());
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('RecommendationsPage', () => {
  it('keeps unlinked-leg warnings as a named neutral region, not an alert', async () => {
    const base = makeRun();
    const unlinkedRun = {
      ...base,
      consolidated_legs: [
        ...base.consolidated_legs,
        {
          ...base.consolidated_legs[0]!,
          leg_id: 'unlinked-api-leg',
          group_ids: ['unknown-group'],
          sequence: 99,
        },
      ],
    };
    const { pinia } = setup(unlinkedRun);
    const wrapper = mountRecommendationsPage(pinia);
    await flushPromises();

    const warning = wrapper.find('[aria-label="Unlinked API legs"]');
    expect(warning?.attributes('role')).toBe('region');
    expect(warning?.text()).toContain('Unlinked API legs — not executable');
    expect(warning?.text()).toContain('API group references are missing or inconsistent.');
    expect(wrapper.find('[role="alert"]').exists()).toBe(false);
    wrapper.unmount();
  });

  it('uses portfolio keys for allocation and nested transition when successful reads disagree', async () => {
    const { pinia } = setup();
    const wrapper = mountRecommendationsPage(pinia);
    const queryClient = getTestQueryClient(wrapper);
    queryClient.setQueryData(
      workspaceQueryKeys.portfolio,
      portfolioWithTransition('portfolio-revision-a'),
    );
    queryClient.setQueryData(workspaceQueryKeys.policy, {
      active: {
        id: 'active-policy-b',
        activation_errors: [],
        sleeves: [
          { sleeve_key: 'us', display_name: 'Active policy US label' },
          { sleeve_key: 'transition_nested', display_name: 'Active policy nested label' },
        ],
      },
      drafts: [],
      superseded: [],
    });
    await flushPromises();

    expect(wrapper.text()).toContain(
      'Portfolio effects use policy revision portfolio-revision-a; the active policy is active-policy-b.',
    );

    const mismatchBanner = wrapper
      .findAll('[role="status"]')
      .find((banner) =>
        banner.text().includes('Portfolio effects use policy revision portfolio-revision-a'),
      );
    expect(mismatchBanner?.attributes('role')).toBe('status');
    const effects = wrapper.get('.effects-panel').text();
    expect(effects).toContain('us');

    expect(effects).toContain('65.0000%');
    expect(effects).toContain('transition_nested');
    expect(effects).not.toContain('Active policy US label');
    expect(effects).not.toContain('Active policy nested label');
    const transition = wrapper.get('.transition-panel');
    expect(transition.text()).toContain(
      'Current US transition provenance is unverified; values are withheld.',
    );
    expect(transition.text()).not.toContain('100.00 USD');
    wrapper.unmount();
  });

  it('keeps cached portfolio keys after a failed follow-up portfolio read', async () => {
    const { pinia } = setup();
    const wrapper = mountRecommendationsPage(pinia);
    const queryClient = getTestQueryClient(wrapper);
    queryClient.setQueryData(
      workspaceQueryKeys.portfolio,
      portfolioWithTransition('portfolio-revision-a'),
    );
    queryClient.setQueryData(workspaceQueryKeys.policy, {
      active: {
        id: 'active-policy-b',
        activation_errors: [],
        sleeves: [
          { sleeve_key: 'us', display_name: 'Active policy US label' },
          { sleeve_key: 'transition_nested', display_name: 'Active policy nested label' },
        ],
      },
      drafts: [],
      superseded: [],
    });
    await queryClient
      .fetchQuery({
        queryKey: workspaceQueryKeys.portfolio,
        queryFn: () => Promise.reject(new Error('portfolio transport failed')),
        staleTime: 0,
        retry: false,
      })
      .catch(() => undefined);
    await flushPromises();

    expect(wrapper.text()).toContain('cached data is being shown');
    expect(wrapper.text()).toContain('Portfolio effects use policy revision portfolio-revision-a');
    const effects = wrapper.get('.effects-panel').text();
    expect(effects).toContain('65.0000%');
    expect(effects).not.toContain('Active policy US label');
    expect(effects).not.toContain('Active policy nested label');
    wrapper.unmount();
  });
  it('uses shared policy freshness and run provenance selectors before displaying effects', async () => {
    const { pinia, store } = setup(makeRun('run-current', ['group-a']));
    const wrapper = mountRecommendationsPage(pinia);
    const queryClient = getTestQueryClient(wrapper);
    await flushPromises();
    expect(wrapper.get('.selected-basket-summary').text()).toContain('1 / 1 / 2');
    expect(store.currentRunView).toBe('current');
    await queryClient
      .fetchQuery({
        queryKey: workspaceQueryKeys.policy,
        queryFn: () => Promise.reject(new Error('stale policy fixture')),
        staleTime: 0,
        retry: false,
      })
      .catch(() => undefined);
    await flushPromises();
    store.currentRunView = 'current';
    await flushPromises();
    expect(store.currentRunView).toBe('current');
    expect(wrapper.find('.selected-basket-summary').exists()).toBe(false);

    expect(wrapper.get('.provenance-banner').text()).toContain('Stale/unverified run · read-only');
    const selectionTools = wrapper.get('.selection-tools');
    expect((selectionTools.get('#recommendation-top-n').element as HTMLInputElement).disabled).toBe(
      true,
    );
    for (const button of selectionTools.findAll('button')) {
      expect((button.element as HTMLButtonElement).disabled).toBe(true);
    }
    expect(wrapper.get('.effects-panel').text()).toContain(
      'Current portfolio API values with active-policy labels',
    );
    expect(wrapper.text()).toContain('cached data is being shown');
    wrapper.unmount();
  });

  it('withholds current basket provenance during policy refresh and preserves saved context', async () => {
    const { pinia, store } = setup(makeRun('run-current', ['group-a']));
    const wrapper = mountRecommendationsPage(pinia);
    const queryClient = getTestQueryClient(wrapper);
    await flushPromises();
    expect(wrapper.get('.selected-basket-summary').text()).toContain('1 / 1 / 2');

    const currentPolicy = store.policy;
    if (!currentPolicy?.active) throw new Error('The current-policy fixture was not loaded');
    const refresh = deferred<Response>();
    vi.stubGlobal(
      'fetch',
      vi.fn(() => refresh.promise),
    );
    const loading = store.loadPolicy();
    expect(store.actionState.loadPolicy.pending).toBe(true);
    await flushPromises();
    expect(store.currentRunView).toBe('current');
    expect(wrapper.find('.selected-basket-summary').exists()).toBe(false);
    expect(wrapper.get('.provenance-banner').text()).toContain('Stale/unverified run · read-only');

    refresh.resolve(jsonResponse(currentPolicy));
    await loading;
    await flushPromises();
    expect(wrapper.get('.selected-basket-summary').text()).toContain('1 / 1 / 2');

    queryClient.setQueryData(workspaceQueryKeys.policy, {
      ...currentPolicy,
      active: { ...currentPolicy.active, id: 'policy-r99' },
    });
    await flushPromises();
    store.currentRunView = 'current';
    await flushPromises();
    expect(store.currentRunView).toBe('current');
    expect(wrapper.find('.selected-basket-summary').exists()).toBe(false);
    expect(wrapper.get('.provenance-banner').text()).toContain('Stale/unverified run · read-only');

    store.currentRunView = 'saved';
    await flushPromises();
    expect(wrapper.find('.selected-basket-summary').exists()).toBe(false);
    expect(wrapper.get('.frozen-context').text()).toContain('Frozen US equity');
    expect(wrapper.get('.provenance-banner').text()).toContain('Saved run · frozen API context');
    wrapper.unmount();
  });

  it('keeps run and selection actions independent of blank saved-run input', async () => {
    const { pinia } = setup(null);
    const run = makeRun('run-after-blank-saved-id');
    const selectedRun = makeRun(run.run_id, ['group-a', 'group-b']);
    const fetcher = vi.fn<typeof fetch>((input, init) => {
      const url = urlOf(input);
      if (url.pathname === '/api/v1/optimizer/runs' && init?.method === 'POST')
        return Promise.resolve(jsonResponse(run));
      if (url.pathname.endsWith('/selection') && init?.method === 'POST')
        return Promise.resolve(jsonResponse(selectedRun));
      return Promise.reject(
        new Error(`Unexpected request: ${init?.method ?? 'GET'} ${url.pathname}`),
      );
    });
    vi.stubGlobal('fetch', fetcher);
    const wrapper = mountRecommendationsPage(pinia);
    await flushPromises();

    await wrapper.get('#recommendation-saved-run-id').setValue('   ');
    expect((wrapper.get('form.saved-run-form button').element as HTMLButtonElement).disabled).toBe(
      true,
    );
    await wrapper.get('form.saved-run-form').trigger('submit');
    expect(fetcher).not.toHaveBeenCalled();

    await wrapper.get('button.primary-button').trigger('click');
    await flushPromises();
    expect(
      fetcher.mock.calls.some(
        ([input, init]) =>
          urlOf(input).pathname === '/api/v1/optimizer/runs' && init?.method === 'POST',
      ),
    ).toBe(true);

    const selectTopGroups = wrapper
      .findAll('button')
      .find((button) => button.text() === 'Select top N and re-solve');
    expect(selectTopGroups).toBeDefined();
    await selectTopGroups!.trigger('click');
    await flushPromises();
    const selectionCall = fetcher.mock.calls.find(
      ([input, init]) => urlOf(input).pathname.endsWith('/selection') && init?.method === 'POST',
    );
    expect(selectionCall).toBeDefined();
    expect(JSON.parse(selectionCall?.[1]?.body as string)).toEqual({
      selected_group_ids: ['group-a', 'group-b'],
      selected_sell_lots: { 'group-a': ['BROKER-A1'], 'group-b': ['BROKER-B1'] },
    });
    wrapper.unmount();
  });

  it('sends an explicit trade date and shows the persisted date in run provenance', async () => {
    const { pinia } = setup(null);
    const run = { ...makeRun('run-with-date'), proposed_trade_date: '2026-11-06' };
    const fetcher = vi.fn<typeof fetch>((input, init) => {
      const url = urlOf(input);
      if (url.pathname === '/api/v1/optimizer/runs' && init?.method === 'POST')
        return Promise.resolve(jsonResponse(run));
      return Promise.reject(
        new Error(`Unexpected request: ${init?.method ?? 'GET'} ${url.pathname}`),
      );
    });
    vi.stubGlobal('fetch', fetcher);
    const wrapper = mountRecommendationsPage(pinia);
    await flushPromises();
    await wrapper.get('input[type="date"]').setValue('2026-11-06');
    await wrapper.get('button.primary-button').trigger('click');
    await flushPromises();

    const createCall = fetcher.mock.calls.find(
      ([input]) => urlOf(input).pathname === '/api/v1/optimizer/runs',
    );
    expect(createCall).toBeDefined();
    expect(JSON.parse(createCall?.[1]?.body as string)).toEqual({
      proposed_trade_date: '2026-11-06',
      mode: 'recommendations_only',
    });
    expect(wrapper.text()).toContain('Proposed trade date 2026-11-06');
    wrapper.unmount();
  });

  it('keeps review-mutation pending state across recommendation-page unmount and remount', async () => {
    const { pinia, store } = setup();
    await flushPromises();
    const run = store.currentRun!;
    const response = {
      ...run,
      groups: run.groups.map((group) =>
        group.group_id === 'group-a' ? { ...group, note: 'confirmed after navigation' } : group,
      ),
    };
    const pendingResponse = deferred<Response>();
    const fetcher = vi.fn<typeof fetch>(() => pendingResponse.promise);
    vi.stubGlobal('fetch', fetcher);

    const pendingMutation = store.annotateGroup(run.run_id, 'group-a', {
      note: 'confirmed after navigation',
    });
    expect(store.reviewMutationPending).toBe(true);
    await Promise.resolve();
    const firstMount = mountRecommendationsPage(pinia);
    await flushPromises();
    expect(firstMount.text()).toContain('Previous basket effects are withheld');
    firstMount.unmount();

    const remounted = mountRecommendationsPage(pinia);
    await flushPromises();
    expect(remounted.text()).toContain('Previous basket effects are withheld');

    pendingResponse.resolve(jsonResponse(response));
    await pendingMutation;
    await flushPromises();
    expect(store.reviewMutationPending).toBe(false);
    expect(store.currentRun?.groups[0]?.note).toBe('confirmed after navigation');
    expect(remounted.text()).not.toContain('Previous basket effects are withheld');
    remounted.unmount();
  });

  it('shows API-only DEMO values, renders a shared BUY once, and re-solves group selections with broker lot IDs', async () => {
    const run = makeRun();
    const sharedBuy = run.consolidated_legs.find((leg) => leg.leg_id === 'buy-shared')!;
    const localBuy = {
      ...sharedBuy,
      leg_id: 'buy-local',
      ticker: 'VXUS',
      group_ids: ['group-a'],
      sequence: 4,
      dependencies: ['sell-a'],
    };
    const runWithLocalBuy = {
      ...run,
      groups: run.groups.map((group) =>
        group.group_id === 'group-a'
          ? { ...group, leg_ids: [...group.leg_ids, 'buy-local'] }
          : group,
      ),
      consolidated_legs: [...run.consolidated_legs, localBuy],
    };
    const { pinia, store } = setup(runWithLocalBuy);
    const updatedRun = makeRun('run-current', ['group-a', 'group-b']);
    const fetcher = vi.fn<typeof fetch>((input, init) => {
      const url = urlOf(input);
      if (url.pathname.endsWith('/selection') && init?.method === 'POST')
        return Promise.resolve(jsonResponse(updatedRun));
      return Promise.reject(
        new Error(`Unexpected request: ${init?.method ?? 'GET'} ${url.pathname}`),
      );
    });
    vi.stubGlobal('fetch', fetcher);
    const wrapper = mountRecommendationsPage(pinia);
    await flushPromises();
    await openRecommendationGroup(wrapper, 'group-a');
    await openRecommendationGroup(wrapper, 'group-b');
    expect(wrapper.get('.run-controls').element.tagName).toBe('SECTION');
    expect(wrapper.get('.effects-panel').element.tagName).toBe('SECTION');
    expect(wrapper.get('.review-panel').element.tagName).toBe('SECTION');
    expect(wrapper.get('.export-panel').element.tagName).toBe('SECTION');
    expect(wrapper.find('.filter-panel').exists()).toBe(true);
    expect(wrapper.get('.shared-leg-card').element.tagName).toBe('ARTICLE');

    expect(wrapper.text()).toContain('DEMO ONLY · non-actionable');
    expect(wrapper.text()).toContain('The real optimizer is unavailable');
    expect(wrapper.text()).toContain('Unavailable (not returned by API)');
    expect(wrapper.get('.workspace-page').classes()).toContain('recommendations-page');
    expect(wrapper.get('h1').text()).toBe('Recommendations');
    expect(
      wrapper.findAll('.leg-card').filter((card) => card.attributes('id') === 'leg-buy-shared'),
    ).toHaveLength(1);
    expect(wrapper.find('[aria-label="Recommendation filters"]').exists()).toBe(true);
    const legLinks = wrapper.findAll('.group-card a[href^="#/recommendations#"]');
    const legDetailIds = wrapper.findAll('.leg-card').map((detail) => detail.attributes('id'));
    expect(legDetailIds).toContain('leg-sell-a');
    expect(legDetailIds).toContain('leg-buy-local');
    expect(legDetailIds.filter((id) => id === 'leg-buy-shared')).toHaveLength(1);
    expect(
      legLinks.filter((link) => link.attributes('href') === '#/recommendations#leg-buy-shared'),
    ).toHaveLength(2);
    for (const link of legLinks) {
      const href = link.attributes('href') ?? '';
      expect(href).toMatch(/^#\/recommendations#leg-/);
      expect(
        legDetailIds.filter(
          (id) => id === decodeURIComponent(href.slice(href.lastIndexOf('#') + 1)),
        ),
      ).toHaveLength(1);
    }
    expect(
      wrapper
        .findAll('button')
        .filter((button) => /^(preview|approve|submit order)/i.test(button.text())),
    ).toHaveLength(0);

    await wrapper
      .findAll('button')
      .find((button) => button.text() === 'Select top N and re-solve')!
      .trigger('click');
    await flushPromises();
    const selectionCall = fetcher.mock.calls.find(([input]) =>
      urlOf(input).pathname.endsWith('/selection'),
    );
    expect(selectionCall).toBeDefined();
    expect(JSON.parse(selectionCall?.[1]?.body as string)).toEqual({
      selected_group_ids: ['group-a', 'group-b'],
      selected_sell_lots: { 'group-a': ['BROKER-A1'], 'group-b': ['BROKER-B1'] },
    });
    expect(store.currentRun?.groups.every((group) => group.selected)).toBe(true);
    expect(
      wrapper.findAll('.leg-card').filter((card) => card.attributes('id') === 'leg-buy-shared'),
    ).toHaveLength(1);
  });

  it('withholds prior basket effects and keeps the API-confirmed checkbox while re-solving', async () => {
    const { pinia } = setup();
    const updatedRun = makeRun('run-current', ['group-a']);
    let resolveSelection: ((response: Response) => void) | undefined;
    const fetcher = vi.fn<typeof fetch>(
      () =>
        new Promise((resolve) => {
          resolveSelection = resolve;
        }),
    );
    vi.stubGlobal('fetch', fetcher);
    const wrapper = mountRecommendationsPage(pinia);
    await flushPromises();
    await openRecommendationGroup(wrapper, 'group-a');

    const groupCheckbox = wrapper.get(
      '[role="checkbox"][aria-label="Select recommendation group group-a"]',
    );
    await groupCheckbox.trigger('click');
    expect(wrapper.text()).toContain('Previous basket effects are withheld');
    expect(wrapper.text()).not.toContain('-4.00 USD');
    expect(groupCheckbox.attributes('aria-checked')).toBe('false');

    resolveSelection?.(jsonResponse(updatedRun));
    await flushPromises();
    await openRecommendationGroup(wrapper, 'group-a');
    expect(
      wrapper
        .get('[role="checkbox"][aria-label="Select recommendation group group-a"]')
        .attributes('aria-checked'),
    ).toBe('true');
  });

  it('keeps the last successful selection after a failed last-lot removal and sends no orphan group', async () => {
    const selectedRun = makeRun('run-current', ['group-a']);
    const { pinia, store } = setup(selectedRun);
    const fetcher = vi.fn<typeof fetch>((input, init) => {
      const url = urlOf(input);
      if (url.pathname.endsWith('/selection') && init?.method === 'POST') {
        return Promise.resolve(
          jsonResponse(
            {
              code: 'empty_selected_group',
              message: 'Selection was refused',
              correlation_id: 'corr-selection',
              details: {},
            },
            422,
          ),
        );
      }
      return Promise.reject(new Error(`Unexpected request: ${url.pathname}`));
    });
    vi.stubGlobal('fetch', fetcher);
    const wrapper = mountRecommendationsPage(pinia);
    await flushPromises();
    await openRecommendationGroup(wrapper, 'group-a');
    await wrapper
      .get('[role="checkbox"][aria-label="Select SELL lot BROKER-A1 in group group-a"]')
      .trigger('click');
    await flushPromises();
    await openRecommendationGroup(wrapper, 'group-a');

    const payload = JSON.parse(fetcher.mock.calls[0]?.[1]?.body as string) as {
      selected_group_ids: string[];
      selected_sell_lots: Record<string, string[]>;
    };
    expect(payload).toEqual({ selected_group_ids: [], selected_sell_lots: {} });
    expect(currentRunForTest(store)).toBe(selectedRun);
    expect(
      wrapper
        .get('[role="checkbox"][aria-label="Select SELL lot BROKER-A1 in group group-a"]')
        .attributes('aria-checked'),
    ).toBe('true');
    expect(wrapper.text()).toContain(
      'Selection re-solve failed; the last successful API selection remains in view',
    );
    expect(wrapper.text()).not.toContain('requested group selected');
  });

  it('rejects a selected group with one full-run PATCH while preserving other selected groups', async () => {
    const initialRun = makeRun('run-current', ['group-a', 'group-b']);
    const baseUpdatedRun = withGroupAnnotations(makeRun('run-current', ['group-b']), {
      'group-a': { note: null, rejectionReason: 'Not appropriate for this batch' },
    });
    const updatedRun = {
      ...baseUpdatedRun,
      groups: baseUpdatedRun.groups.map((group) =>
        group.group_id === 'group-a' ? { ...group, rejected: true } : group,
      ),
    };
    const { pinia, store } = setup(initialRun);
    const fetcher = vi.fn<typeof fetch>((input, init) => {
      const url = urlOf(input);
      if (url.pathname.endsWith('/recommendations/group-a') && init?.method === 'PATCH')
        return Promise.resolve(jsonResponse(updatedRun));
      return Promise.reject(new Error(`Unexpected request: ${init?.method} ${url.pathname}`));
    });
    vi.stubGlobal('fetch', fetcher);
    const wrapper = mountRecommendationsPage(pinia);
    await flushPromises();
    await openRecommendationGroup(wrapper, 'group-a');

    const annotation = wrapper.get('[aria-label="Notes and rejection for group-a"]');
    await annotation.get('input').setValue('Not appropriate for this batch');
    await annotation
      .findAll('button')
      .find((button) => button.text().includes('Reject group'))!
      .trigger('click');
    await flushPromises();

    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(fetcher.mock.calls[0]?.[1]?.method).toBe('PATCH');
    expect(JSON.parse(fetcher.mock.calls[0]?.[1]?.body as string)).toEqual({
      rejected: true,
      rejection_reason: 'Not appropriate for this batch',
    });
    expect(fetcher.mock.calls.some(([, init]) => init?.method === 'POST')).toBe(false);
    expect(store.currentRun).toEqual(updatedRun);
    expect(store.currentRun?.groups.find((group) => group.group_id === 'group-a')).toMatchObject({
      rejected: true,
      selected: false,
    });
    expect(store.currentRun?.groups.find((group) => group.group_id === 'group-b')?.selected).toBe(
      true,
    );
    expect(
      store.currentRun?.consolidated_legs.find((leg) => leg.leg_id === 'buy-shared')?.selected,
    ).toBe(true);
    wrapper.unmount();
  });

  it('keeps the full basket on an overlong or failed rejection reason', async () => {
    const initialRun = makeRun('run-current', ['group-a', 'group-b']);
    const { pinia, store } = setup(initialRun);
    const fetcher = vi.fn<typeof fetch>(() =>
      Promise.resolve(
        jsonResponse(
          {
            code: 'invalid_annotation',
            message: 'The rejection reason is too long',
            correlation_id: 'rejection-error',
            details: {},
          },
          422,
        ),
      ),
    );
    vi.stubGlobal('fetch', fetcher);
    const wrapper = mountRecommendationsPage(pinia);
    await flushPromises();
    const previousRun = currentRunForTest(store);
    await openRecommendationGroup(wrapper, 'group-a');
    const annotation = wrapper.get('[aria-label="Notes and rejection for group-a"]');
    const reasonInput = annotation.get('input');
    expect(reasonInput.attributes('maxlength')).toBe('500');
    await reasonInput.setValue('x'.repeat(501));
    const rejectButton = annotation
      .findAll('button')
      .find((button) => button.text().includes('Reject group'))!;
    expect((rejectButton.element as HTMLButtonElement).disabled).toBe(true);
    await rejectButton.trigger('click');
    await flushPromises();
    expect(fetcher).not.toHaveBeenCalled();
    expect(currentRunForTest(store)).toBe(previousRun);

    await reasonInput.setValue('Valid reason');
    await rejectButton.trigger('click');
    await flushPromises();
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(fetcher.mock.calls[0]?.[1]?.method).toBe('PATCH');
    expect(fetcher.mock.calls.some(([, init]) => init?.method === 'POST')).toBe(false);
    expect(currentRunForTest(store)).toBe(previousRun);
    expect(
      store.currentRun?.groups.filter((group) => group.selected).map((group) => group.group_id),
    ).toEqual(['group-a', 'group-b']);
    expect(wrapper.text()).toContain('Group note or rejection was not saved');
    wrapper.unmount();
  });

  it('clears a saved note with an explicit null and replaces the full returned run', async () => {
    const initialRun = withGroupAnnotations(makeRun(), {
      'group-a': { note: 'Existing note', rejectionReason: null },
    });
    const updatedRun = withGroupAnnotations(makeRun(), {
      'group-a': { note: null, rejectionReason: null },
    });
    const { pinia, store } = setup(initialRun);
    const fetcher = vi.fn<typeof fetch>((input, init) => {
      if (urlOf(input).pathname.endsWith('/recommendations/group-a') && init?.method === 'PATCH')
        return Promise.resolve(jsonResponse(updatedRun));
      return Promise.reject(
        new Error(`Unexpected request: ${init?.method} ${urlOf(input).pathname}`),
      );
    });
    vi.stubGlobal('fetch', fetcher);
    const wrapper = mountRecommendationsPage(pinia);
    await flushPromises();
    await openRecommendationGroup(wrapper, 'group-a');
    const annotation = wrapper.get('[aria-label="Notes and rejection for group-a"]');
    const noteInput = annotation.get('textarea');
    expect(noteInput.attributes('maxlength')).toBe('2000');
    await noteInput.setValue('');
    await annotation
      .findAll('button')
      .find((button) => button.text() === 'Save note')!
      .trigger('click');
    await flushPromises();

    expect(JSON.parse(fetcher.mock.calls[0]?.[1]?.body as string)).toEqual({ note: null });
    expect(store.currentRun).toEqual(updatedRun);
    expect(store.currentRun?.groups.find((group) => group.group_id === 'group-a')?.note).toBeNull();
    expect((noteInput.element as HTMLTextAreaElement).value).toBe('');
    wrapper.unmount();
  });

  it('restores a rejected group without selecting it or clearing its note', async () => {
    const baseRun = withGroupAnnotations(makeRun('run-current', ['group-b']), {
      'group-a': { note: 'Keep this note', rejectionReason: 'Old rejection' },
    });
    const initialRun = {
      ...baseRun,
      groups: baseRun.groups.map((group) =>
        group.group_id === 'group-a' ? { ...group, rejected: true, selected: false } : group,
      ),
    };
    const updatedRun = withGroupAnnotations(baseRun, {
      'group-a': { note: 'Keep this note', rejectionReason: null },
    });
    const { pinia, store } = setup(initialRun);
    const fetcher = vi.fn<typeof fetch>((input, init) => {
      if (urlOf(input).pathname.endsWith('/recommendations/group-a') && init?.method === 'PATCH')
        return Promise.resolve(jsonResponse(updatedRun));
      return Promise.reject(
        new Error(`Unexpected request: ${init?.method} ${urlOf(input).pathname}`),
      );
    });
    vi.stubGlobal('fetch', fetcher);
    const wrapper = mountRecommendationsPage(pinia);
    await flushPromises();
    await openRecommendationGroup(wrapper, 'group-a');

    const annotation = wrapper.get('[aria-label="Notes and rejection for group-a"]');
    await annotation
      .findAll('button')
      .find((button) => button.text().includes('Restore rejected group'))!
      .trigger('click');
    await flushPromises();

    expect(JSON.parse(fetcher.mock.calls[0]?.[1]?.body as string)).toEqual({
      rejected: false,
    });
    expect(store.currentRun).toEqual(updatedRun);
    expect(store.currentRun?.groups.find((group) => group.group_id === 'group-a')).toMatchObject({
      rejected: false,
      selected: false,
      note: 'Keep this note',
      rejection_reason: null,
    });
    expect(store.currentRun?.groups.find((group) => group.group_id === 'group-b')?.selected).toBe(
      true,
    );
    expect(fetcher.mock.calls.some(([, init]) => init?.method === 'POST')).toBe(false);
    wrapper.unmount();
  });

  it('opens saved runs as frozen read-only context without running an optimizer on mount', async () => {
    const { pinia, store } = setup(null);
    const savedRun = makeRun('saved-run-1');
    const summary = { ...savedRun };
    const fetcher = vi.fn<typeof fetch>((input) => {
      const url = urlOf(input);
      if (url.pathname === '/api/v1/optimizer/runs/saved-run-1')
        return Promise.resolve(jsonResponse(summary));
      if (url.pathname === '/api/v1/optimizer/runs/saved-run-1/recommendations')
        return Promise.resolve(jsonResponse(savedRun));
      return Promise.reject(new Error(`Unexpected request: ${url.pathname}`));
    });
    vi.stubGlobal('fetch', fetcher);
    const wrapper = mountRecommendationsPage(pinia);
    await flushPromises();
    expect(fetcher).not.toHaveBeenCalled();
    await wrapper.get('input[placeholder="Run ID from Activity"]').setValue('saved-run-1');
    await wrapper.get('form.saved-run-form').trigger('submit');
    await flushPromises();
    await openRecommendationGroup(wrapper, 'group-a');

    expect(store.currentRunView).toBe('saved');
    expect(wrapper.text()).toContain('Saved run · frozen API context · read-only');
    const frozenContextPanel = wrapper.get('[aria-label="Frozen run display context"]');
    expect(frozenContextPanel.text()).toContain('Frozen US equity');
    expect(frozenContextPanel.text()).toContain('100.0000%');
    expect(frozenContextPanel.text()).toContain('3210.00');
    expect(frozenContextPanel.text()).not.toContain('Active US (renamed)');
    expect(
      wrapper
        .get('[role="checkbox"][aria-label="Select recommendation group group-a"]')
        .attributes('aria-disabled'),
    ).toBe('true');
    expect(fetcher.mock.calls.some(([, init]) => init?.method === 'POST')).toBe(false);
  });
  it('keeps stale-run group labels frozen while current portfolio effects use active-policy labels', async () => {
    const { pinia, store } = setup(makeRun());
    store.currentRunView = 'stale';
    const wrapper = mountRecommendationsPage(pinia);
    const queryClient = getTestQueryClient(wrapper);
    queryClient.setQueryData(workspaceQueryKeys.policy, {
      active: {
        id: 'policy-current',
        activation_errors: [],
        sleeves: [
          { sleeve_key: 'us', display_name: 'Current US policy label' },
          { sleeve_key: 'current-child', display_name: 'Current transition child' },
        ],
      },
      drafts: [],
      superseded: [],
    });
    queryClient.setQueryData(workspaceQueryKeys.portfolio, {
      ...readyPortfolio(),
      active_policy_revision_id: 'policy-current',
      allocation: {
        current: { total_portfolio_usd: '100.00', sleeve_weights_pct: { us: '80.0000' } },
        proposed: null,
        target: null,
      },
      us_transition: transitionResponse(['current-child'], 'Current portfolio transition'),
    });
    await flushPromises();

    const effects = wrapper.get('.effects-panel');
    const allocation = effects.get('.allocation-panel');
    const allocationTable = allocation.get('table').element as HTMLTableElement;
    expect(allocationTable.querySelectorAll('thead th[scope="col"]')).toHaveLength(4);
    expect(allocationTable.querySelector('caption')?.textContent?.replace(/\s+/g, ' ').trim()).toBe(
      'Current, proposed basket, and policy target allocation weights',
    );
    const allocationRegion = allocation.get(
      '[role="region"][aria-label="Portfolio allocation weights"]',
    );
    expect(allocationRegion.attributes('tabindex')).toBe('0');
    expect(effects.text()).toContain('Current portfolio API values with active-policy labels');
    expect(effects.get('.allocation-panel').text()).toContain('Current US policy label');
    expect(effects.get('.allocation-panel').text()).not.toContain('Frozen US equity');
    const transition = effects.get('.transition-panel');
    expect(transition.text()).toContain('Current transition child');
    expect(transition.text()).not.toContain('current-child');
    expect(transition.text()).toContain(
      'Selected-trade effects are stale; no proposed values are shown.',
    );
    expect(transition.text()).toContain('Unavailable (stale effects)');
    expect(transition.text()).not.toContain('Saved run · frozen context · read-only');
    const group = wrapper.get('.group-card');
    expect(group.text()).toContain('Frozen US equity');
    expect(group.text()).not.toContain('Current US policy label');
    wrapper.unmount();
  });
  it('withholds a current matching run basket when no selected sell trades exist', async () => {
    const run = withRunTransition(makeRun(), distinctTransitionResponse());
    const { pinia } = setup(run);
    const wrapper = mountRecommendationsPage(pinia);
    await flushPromises();

    const transition = wrapper.get('.transition-panel');
    const values = transition.get('tbody tr').findAll('td');
    expect(transition.text()).toContain('Current selected-basket API context');
    expect(transition.text()).toContain('No trades selected. Proposed values are not shown.');
    expect(transition.get('.whole-portfolio-summary').text()).not.toContain('101.00 USD');
    expect(values[0]?.text()).toContain('10.0000%');
    expect(values[1]?.text()).toBe('—');
    expect(values[1]?.text()).not.toContain('20.0000%');
    expect(values[2]?.text()).toContain('50.0000%');
    wrapper.unmount();
  });

  it('shows selected current-run API values only for the exact selected trade basket', async () => {
    const run = withRunTransition(
      makeRun('run-selected', ['group-a']),
      distinctTransitionResponse(),
    );
    const { pinia } = setup(run);
    const wrapper = mountRecommendationsPage(pinia);
    await flushPromises();

    const transition = wrapper.get('.transition-panel');
    const values = transition.get('tbody tr').findAll('td');
    expect(transition.text()).toContain('Current selected-basket API context');
    expect(transition.get('.whole-portfolio-summary').text()).toContain('101.00 USD · 41.0000%');
    expect(values[1]?.text()).toContain('20.0000%');
    expect(values[1]?.text()).toContain('within US sleeve');
    wrapper.unmount();
  });

  it('uses frozen labels for nested transition children in a saved run', async () => {
    const baseRun = makeRun('saved-transition-run', ['group-a']);
    const savedRun = {
      ...baseRun,
      portfolio_effects: {
        allocation: baseRun.portfolio_effects?.allocation ?? {
          current: null,
          proposed: null,
          target: null,
        },
        us_transition: transitionResponse(
          ['historical-us-direct', 'historical-us-etf'],
          'Historical US transition',
        ),
      },
      frozen_display_context: frozenContextWithTransitionLabels(),
    };
    const { pinia } = setup(null);
    const fetcher = vi.fn<typeof fetch>((input) => {
      const url = urlOf(input);
      if (url.pathname === '/api/v1/optimizer/runs/saved-transition-run')
        return Promise.resolve(jsonResponse(savedRun));
      if (url.pathname === '/api/v1/optimizer/runs/saved-transition-run/recommendations')
        return Promise.resolve(jsonResponse(savedRun));
      return Promise.reject(new Error(`Unexpected request: ${url.pathname}`));
    });
    vi.stubGlobal('fetch', fetcher);
    const wrapper = mountRecommendationsPage(pinia);
    await flushPromises();
    await wrapper.get('input[placeholder="Run ID from Activity"]').setValue('saved-transition-run');
    await wrapper.get('form.saved-run-form').trigger('submit');
    await flushPromises();

    const transition = wrapper.get('.transition-panel');
    expect(transition.text()).toContain('Historical direct-index sleeve');
    expect(transition.text()).toContain('Historical replacement ETF sleeve');
    expect(transition.text()).not.toContain('historical-us-direct');
    expect(transition.text()).not.toContain('historical-us-etf');
    expect(transition.text()).toContain('Saved run · frozen context · read-only');
    expect(transition.text()).toContain('After selected trades');
    expect(transition.text()).not.toContain('No trades selected. Proposed values are not shown.');
    expect(transition.text()).not.toContain('Active US (renamed)');
    expect(wrapper.get('.effects-panel').text()).toContain('Frozen run effects and labels');
    wrapper.unmount();
  });

  it('shows frozen-context unavailability instead of borrowing active-policy labels', async () => {
    const run = {
      ...makeRun(),
      frozen_display_context: {
        ...frozenContext(),
        available: false,
        source: null,
        sleeves: null,
        settings: null,
        allowed_securities: null,
        overrides: null,
        unavailable_reason: 'historical policy revision unavailable',
      },
    } as unknown as OptimizerRecommendationsResponse;
    const { pinia } = setup(run);
    const wrapper = mountRecommendationsPage(pinia);
    await flushPromises();

    const panel = wrapper.get('[aria-label="Frozen run display context"]');
    expect(panel.text()).toContain('Unavailable');
    expect(panel.text()).toContain('historical policy revision unavailable');
    expect(wrapper.text()).toContain('Unavailable (frozen run context)');
    expect(panel.text()).not.toContain('Active US (renamed)');
    wrapper.unmount();
  });

  it('exports the self-describing API JSON through a temporary object URL', async () => {
    const { pinia } = setup();
    const exportValue = {
      metadata: { run_id: 'run-current', demo: true, actionable: false },
      run: makeRun(),
    };
    const fetcher = vi.fn<typeof fetch>((input) => {
      const url = urlOf(input);
      if (url.pathname.endsWith('/export')) return Promise.resolve(jsonResponse(exportValue));
      return Promise.reject(new Error(`Unexpected request: ${url.pathname}`));
    });
    vi.stubGlobal('fetch', fetcher);
    const objectUrl = vi.fn(() => 'blob:recommendations');
    const revokeUrl = vi.fn();
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: objectUrl });
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: revokeUrl });
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, 'click')
      .mockImplementation(() => undefined);
    const wrapper = mountRecommendationsPage(pinia);
    await flushPromises();
    await wrapper
      .findAll('button')
      .find((button) => button.text() === 'Export JSON')!
      .trigger('click');
    await flushPromises();

    expect(urlOf(fetcher.mock.calls[0]![0]).searchParams.get('format')).toBe('json');
    expect(objectUrl).toHaveBeenCalledOnce();
    expect(click).toHaveBeenCalledOnce();
    expect(revokeUrl).toHaveBeenCalledWith('blob:recommendations');
  });

  it('hydrates saved annotations immediately on mount and remount', async () => {
    const run = withGroupAnnotations(makeRun(), {
      'group-a': { note: 'saved note A', rejectionReason: 'saved rejection A' },
      'group-b': { note: 'saved note B', rejectionReason: 'saved rejection B' },
    });
    const { pinia } = setup(run);
    const firstMount = mountRecommendationsPage(pinia);
    await flushPromises();
    await openRecommendationGroup(firstMount, 'group-a');

    const firstGroup = firstMount.get('[aria-label="Notes and rejection for group-a"]');
    expect((firstGroup.get('textarea').element as HTMLTextAreaElement).value).toBe('saved note A');
    expect((firstGroup.get('input').element as HTMLInputElement).value).toBe('saved rejection A');
    firstMount.unmount();

    const remount = mountRecommendationsPage(pinia);
    await flushPromises();
    await openRecommendationGroup(remount, 'group-a');
    const remountedGroup = remount.get('[aria-label="Notes and rejection for group-a"]');
    expect((remountedGroup.get('textarea').element as HTMLTextAreaElement).value).toBe(
      'saved note A',
    );
    expect((remountedGroup.get('input').element as HTMLInputElement).value).toBe(
      'saved rejection A',
    );
    remount.unmount();
  });

  it('posts the exact lot subset when re-adding a lot to a partially selected group', async () => {
    const totalsOne = {
      shares: '1',
      notional: '20.00',
      selectedLotCount: 1,
      realizedSt: '-4.00',
    };
    const initialRun = makeMultiLotRun('run-current', ['BROKER-A1'], totalsOne);
    const updatedRun = makeMultiLotRun('run-current', ['BROKER-A1', 'BROKER-A2'], {
      shares: '2',
      notional: '40.00',
      selectedLotCount: 2,
      realizedSt: '-8.00',
    });
    const { pinia } = setup(initialRun);
    const fetcher = vi.fn<typeof fetch>((input, init) => {
      const url = urlOf(input);
      if (url.pathname.endsWith('/selection') && init?.method === 'POST')
        return Promise.resolve(jsonResponse(updatedRun));
      return Promise.reject(new Error(`Unexpected request: ${init?.method} ${url.pathname}`));
    });
    vi.stubGlobal('fetch', fetcher);
    const wrapper = mountRecommendationsPage(pinia);
    await flushPromises();
    await openRecommendationGroup(wrapper, 'group-a');

    await wrapper
      .get('[role="checkbox"][aria-label="Select SELL lot BROKER-A2 in group group-a"]')
      .trigger('click');
    await flushPromises();

    const selectionCall = fetcher.mock.calls.find(([input]) =>
      urlOf(input).pathname.endsWith('/selection'),
    );
    expect(JSON.parse(selectionCall?.[1]?.body as string)).toEqual({
      selected_group_ids: ['group-a'],
      selected_sell_lots: { 'group-a': ['BROKER-A1', 'BROKER-A2'] },
    });
    wrapper.unmount();
  });

  it('posts one checked lot from a fully deselected group', async () => {
    const initialRun = makeMultiLotRun('run-current', [], {
      shares: '0',
      notional: '0.00',
      selectedLotCount: 0,
      realizedSt: '0.00',
    });
    const updatedRun = makeMultiLotRun('run-current', ['BROKER-A2'], {
      shares: '1',
      notional: '20.00',
      selectedLotCount: 1,
      realizedSt: '-4.00',
    });
    const { pinia } = setup(initialRun);
    const fetcher = vi.fn<typeof fetch>((input, init) => {
      const url = urlOf(input);
      if (url.pathname.endsWith('/selection') && init?.method === 'POST')
        return Promise.resolve(jsonResponse(updatedRun));
      return Promise.reject(new Error(`Unexpected request: ${init?.method} ${url.pathname}`));
    });
    vi.stubGlobal('fetch', fetcher);
    const wrapper = mountRecommendationsPage(pinia);
    await flushPromises();
    await openRecommendationGroup(wrapper, 'group-a');

    await wrapper
      .get('[role="checkbox"][aria-label="Select SELL lot BROKER-A2 in group group-a"]')
      .trigger('click');
    await flushPromises();

    const selectionCall = fetcher.mock.calls.find(([input]) =>
      urlOf(input).pathname.endsWith('/selection'),
    );
    expect(JSON.parse(selectionCall?.[1]?.body as string)).toEqual({
      selected_group_ids: ['group-a'],
      selected_sell_lots: { 'group-a': ['BROKER-A2'] },
    });
    wrapper.unmount();
  });

  it('preserves other dirty drafts across updates and confirms its own API save', async () => {
    const annotations = {
      'group-a': { note: 'saved note A', rejectionReason: 'saved rejection A' },
      'group-b': { note: 'saved note B', rejectionReason: 'saved rejection B' },
    };
    const initialRun = withGroupAnnotations(makeRun(), annotations);
    const selectedRun = withGroupAnnotations(makeRun('run-current', ['group-b']), annotations);
    const { pinia, store } = setup(initialRun);
    const annotatedRun = withGroupAnnotations(selectedRun, {
      ...annotations,
      'group-b': { note: 'confirmed note B', rejectionReason: 'saved rejection B' },
    });
    let annotationPayload: unknown;
    const fetcher = vi.fn<typeof fetch>((input, init) => {
      const url = urlOf(input);
      if (url.pathname.endsWith('/selection') && init?.method === 'POST')
        return Promise.resolve(jsonResponse(selectedRun));
      if (url.pathname.endsWith('/recommendations/group-b') && init?.method === 'PATCH') {
        annotationPayload = JSON.parse(init.body as string);
        return Promise.resolve(jsonResponse(annotatedRun));
      }
      return Promise.reject(new Error(`Unexpected request: ${init?.method} ${url.pathname}`));
    });
    vi.stubGlobal('fetch', fetcher);
    const wrapper = mountRecommendationsPage(pinia);
    await flushPromises();
    await openRecommendationGroup(wrapper, 'group-a');
    await openRecommendationGroup(wrapper, 'group-b');

    const groupA = wrapper.get('[aria-label="Notes and rejection for group-a"]');
    await groupA.get('textarea').setValue('unsaved note A');
    await groupA.get('input').setValue('unsaved rejection A');
    await wrapper
      .get('[role="checkbox"][aria-label="Select recommendation group group-b"]')
      .trigger('click');
    await flushPromises();
    await openRecommendationGroup(wrapper, 'group-a');
    await openRecommendationGroup(wrapper, 'group-b');

    const subsetGroupA = wrapper.get('[aria-label="Notes and rejection for group-a"]');
    const subsetNote = subsetGroupA.get('textarea').element as HTMLTextAreaElement;
    const subsetRejection = subsetGroupA.get('input').element as HTMLInputElement;
    expect(subsetNote.value).toBe('unsaved note A');
    expect(subsetRejection.value).toBe('unsaved rejection A');

    const groupB = wrapper.get('[aria-label="Notes and rejection for group-b"]');
    await groupB.get('textarea').setValue('  confirmed note B  ');
    await groupB.get('button').trigger('click');
    await flushPromises();
    await openRecommendationGroup(wrapper, 'group-a');
    await openRecommendationGroup(wrapper, 'group-b');

    expect(store.currentRun).toEqual(annotatedRun);
    expect(store.currentRun?.groups.find((group) => group.group_id === 'group-b')?.note).toBe(
      'confirmed note B',
    );
    expect(annotationPayload).toEqual({ note: 'confirmed note B' });
    const savedGroupA = wrapper.get('[aria-label="Notes and rejection for group-a"]');
    const savedGroupB = wrapper.get('[aria-label="Notes and rejection for group-b"]');
    const savedNote = savedGroupA.get('textarea').element as HTMLTextAreaElement;
    const savedRejection = savedGroupA.get('input').element as HTMLInputElement;
    expect((savedGroupB.get('textarea').element as HTMLTextAreaElement).value).toBe(
      'confirmed note B',
    );
    expect(savedNote.value).toBe('unsaved note A');
    expect(savedRejection.value).toBe('unsaved rejection A');
    wrapper.unmount();
  });

  it('resets drafts and hydrates annotations when clearing and switching runs', async () => {
    const initialRun = withGroupAnnotations(makeRun(), {
      'group-a': { note: 'old saved note', rejectionReason: 'old saved rejection' },
    });
    const nextRun = withGroupAnnotations(makeRun('run-new'), {
      'group-a': { note: 'new saved note', rejectionReason: 'new saved rejection' },
    });
    const { pinia, store } = setup(initialRun);
    const wrapper = mountRecommendationsPage(pinia);
    await flushPromises();
    await openRecommendationGroup(wrapper, 'group-a');

    const groupA = wrapper.get('[aria-label="Notes and rejection for group-a"]');
    await groupA.get('textarea').setValue('stale unsaved note');
    await groupA.get('input').setValue('stale unsaved rejection');
    seedCurrentRunForTest(store, null);
    await flushPromises();
    seedCurrentRunForTest(store, nextRun);
    store.currentRunView = 'current';
    await flushPromises();
    await openRecommendationGroup(wrapper, 'group-a');

    const nextGroup = wrapper.get('[aria-label="Notes and rejection for group-a"]');
    const nextNote = nextGroup.get('textarea').element as HTMLTextAreaElement;
    expect(nextNote.value).toBe('new saved note');
    expect((nextGroup.get('input').element as HTMLInputElement).value).toBe('new saved rejection');
    wrapper.unmount();
  });

  it('links both populated and empty recommendation views to the shared read-only review route', async () => {
    const populated = setup(makeRun());
    const populatedWrapper = mountRecommendationsPage(populated.pinia);
    await flushPromises();
    expect(populatedWrapper.findAll('a[href="/review"]')).toHaveLength(1);
    expect(populatedWrapper.get('a[href="/review"]').text()).toBe('Review selected trades');
    populatedWrapper.unmount();

    const empty = setup(null);
    const emptyWrapper = mountRecommendationsPage(empty.pinia);
    await flushPromises();
    expect(emptyWrapper.findAll('a[href="/review"]')).toHaveLength(1);
    expect(emptyWrapper.get('a[href="/review"]').text()).toBe('Review selected trades');
    emptyWrapper.unmount();
  });
});

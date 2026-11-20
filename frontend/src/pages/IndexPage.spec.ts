// @vitest-environment jsdom
import { flushPromises } from '@vue/test-utils';
import { mountWithWorkspace } from '@/test-utils/workspace-mount';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';
import { createMemoryHistory, createRouter } from 'vue-router';
import {
  mountWorkspaceHarness,
  seedCurrentRunForTest,
  currentRunForTest,
} from '@/test-utils/workspace-harness';
import { workspaceQueryKeys } from '@/composables/queries/workspace-queries';
import { getTestQueryClient, getTestQueryClientForPinia } from '@/test-utils/workspace-mount';
import type { QueryClient } from '@tanstack/vue-query';
import IndexPage from './IndexPage.vue';
import type { PolicyResponse } from '@/types/api';

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function portfolioFixture(revisionId: string) {
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
    status: 'ready',
    demo: true,
    account: { display_name: 'Demo account', account_type: 'brokerage', tax_treatment: null },
    cash_usd: '0.00',
    portfolio_total_usd: '100.00',
    position_count: 1,
    positions: [],
    active_policy_revision_id: revisionId,
    unassigned_tickers: [],
    sync: { generation: 7, complete: true, started_at: null, completed_at: '2026-01-01T00:00:00Z' },
    allocation: {
      current: { sleeve_weights_pct: { us: '100.0000' } },
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
    coverage: {},
  };
}

function seedMismatchedPortfolioAndPolicy(
  queryClient: QueryClient,
  portfolioRevisionId = 'portfolio-revision-a',
  policyRevisionId = 'active-policy-b',
) {
  const confirmedAt = Date.parse('2026-01-01T00:00:00Z');
  queryClient.setQueryData(
    workspaceQueryKeys.health,
    {
      status: 'ok',
      schema_ready: true,
      broker_mode: 'demo',
      live_broker_enabled: false,
      order_submission_enabled: false,
    },
    { updatedAt: confirmedAt },
  );
  queryClient.setQueryData(workspaceQueryKeys.portfolio, portfolioFixture(portfolioRevisionId), {
    updatedAt: confirmedAt,
  });
  queryClient.setQueryData(
    workspaceQueryKeys.policy,
    {
      active: {
        id: policyRevisionId,
        activation_errors: [],
        sleeves: [
          { sleeve_key: 'us', display_name: 'Active policy US label' },
          { sleeve_key: 'transition_nested', display_name: 'Active policy nested label' },
        ],
      },
      drafts: [],
      superseded: [],
    },
    { updatedAt: confirmedAt },
  );
}

function currentRunFixture(realizedSt = '-5.00', allocationWeight = '70.0000') {
  return {
    run_id: 'current-run',
    status: 'demo',
    policy_revision_id: 'active-policy-b',
    source_generation: 7,
    frozen_display_context: { available: false, unavailable_reason: 'fixture' },
    groups: [{ group_id: 'group-a', sleeve_key: 'us' }],
    portfolio_effects: {
      allocation: {
        current: { sleeve_weights_pct: { us: allocationWeight } },
        proposed: null,
        target: null,
      },
      us_transition: null,
    },
    estimated_realized_st_usd: realizedSt,
    estimated_realized_lt_usd: '0.00',
    estimated_tax_benefit_usd: null,
    estimated_tax_benefit_status: 'tax_profile_incomplete',
    lots_sold_count: 1,
    positions_exited_count: 0,
    orders_count: 1,
    cash_before_usd: '0.00',
    cash_after_usd: '0.00',
  };
}

function selectedOverviewRunFixture(withUnavailableGroupDetails = false) {
  return {
    ...currentRunFixture(),
    frozen_display_context: {
      available: true,
      source: 'policy_revision',
      policy_revision_id: 'active-policy-b',
      revision_number: 3,
      created_at: '2026-01-01T00:00:00Z',
      activated_at: '2026-01-01T00:00:00Z',
      sleeves: [
        {
          sleeve_key: 'us',
          display_name: 'U.S. direct-index container',
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
        {
          sleeve_key: 'legacy',
          display_name: 'Legacy U.S. holdings',
          sort_order: 2,
          parent_sleeve_key: 'us',
          target_pct: '70.0000',
          drift_band_pp: '5.0000',
          enabled: true,
          is_direct_index_container: false,
          is_direct_index_sleeve: true,
          is_transition_destination: false,
          is_cash_sleeve: false,
        },
        {
          sleeve_key: 'transition_nested',
          display_name: 'New U.S. holdings',
          sort_order: 3,
          parent_sleeve_key: 'us',
          target_pct: '30.0000',
          drift_band_pp: '5.0000',
          enabled: true,
          is_direct_index_container: false,
          is_direct_index_sleeve: false,
          is_transition_destination: true,
          is_cash_sleeve: false,
        },
      ],
      settings: { target_retained_net_loss_usd: '0.00' },
      allowed_securities: [],
      overrides: [],
      unavailable_reason: null,
    },
    estimated_realized_st_usd: '-5.00',
    estimated_realized_lt_usd: '2.00',
    estimated_tax_benefit_usd: null,
    estimated_tax_benefit_status: 'optimizer_unavailable',
    groups: [
      {
        group_id: 'group-lower-priority',
        rank: 4,
        sleeve_key: withUnavailableGroupDetails ? null : 'legacy',
        rationale: 'Reduce AAPL legacy exposure.',
        selected: true,
        rejected: false,
        leg_ids: ['sell-aapl', 'buy-shared'],
        impact: withUnavailableGroupDetails
          ? null
          : { realized_st_usd: '-5.00', realized_lt_usd: '0.00' },
      },
      {
        group_id: 'group-top-priority',
        rank: 1,
        sleeve_key: 'legacy',
        rationale: 'Reduce MSFT legacy exposure.',
        selected: true,
        rejected: false,
        leg_ids: ['sell-msft', 'buy-shared'],
        impact: { realized_st_usd: '0.00', realized_lt_usd: '2.00' },
      },
    ],
    consolidated_legs: [
      {
        leg_id: 'sell-aapl',
        side: 'SELL',
        ticker: 'AAPL',
        shares: '2',
        estimated_unit_price_usd: '20.00',
        estimated_notional_usd: '40.00',
        net_st_realized_usd: '-5.00',
        net_lt_realized_usd: '0.00',
        selected: true,
        group_ids: ['group-lower-priority'],
        sequence: 1,
        dependencies: [],
        selected_lots: [
          {
            broker_lot_id: 'AAPL-LOT-1',
            shares: '2',
            acquired_date: '2024-01-01',
            adjusted_basis_usd: '45.00',
            st_lt: 'ST',
            realized_pl_usd: '-5.00',
            selected: true,
          },
        ],
        details: {},
      },
      {
        leg_id: 'sell-msft',
        side: 'SELL',
        ticker: 'MSFT',
        shares: '1',
        estimated_unit_price_usd: '30.00',
        estimated_notional_usd: '30.00',
        net_st_realized_usd: '0.00',
        net_lt_realized_usd: '2.00',
        selected: true,
        group_ids: ['group-top-priority'],
        sequence: 2,
        dependencies: [],
        selected_lots: [
          {
            broker_lot_id: 'MSFT-LOT-1',
            shares: '1',
            acquired_date: '2020-01-01',
            adjusted_basis_usd: '28.00',
            st_lt: 'LT',
            realized_pl_usd: '-3.00',
            selected: true,
          },
        ],
        details: {},
      },
      {
        leg_id: 'buy-shared',
        side: 'BUY',
        ticker: 'VTI',
        shares: '1',
        estimated_unit_price_usd: '50.00',
        estimated_notional_usd: '50.00',
        net_st_realized_usd: '0.00',
        net_lt_realized_usd: '0.00',
        selected: true,
        group_ids: ['group-lower-priority', 'group-top-priority'],
        sequence: 3,
        dependencies: ['sell-aapl', 'sell-msft'],
        selected_lots: [],
        details: {},
      },
    ],
  } as never;
}

function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function requestUrl(input: RequestInfo | URL): string {
  if (typeof input === 'string') return input;
  if (input instanceof URL) return input.href;
  return input.url;
}

function exposureStatus(freshness: 'configured_missing' | 'current' | 'stale', failed = false) {
  return {
    ticker: 'ITOT',
    freshness,
    configured_provider: 'ishares',
    provider: freshness === 'configured_missing' ? null : 'ishares',
    as_of_date: freshness === 'configured_missing' ? null : '2026-11-17',
    fetched_at: freshness === 'configured_missing' ? null : '2026-11-18T14:08:29Z',
    last_attempt_at: failed ? '2026-11-19T01:00:00Z' : null,
    last_attempt_status: failed
      ? 'failure'
      : freshness === 'configured_missing'
        ? 'never'
        : 'success',
    last_error_code: failed ? 'provider_unavailable' : null,
    last_error_summary: failed ? 'Provider refresh failed' : null,
    publication_revision: 1,
    dimensions:
      freshness === 'configured_missing'
        ? []
        : [
            {
              dimension: 'sector',
              covered_weight: '0.834567890123456789',
              complete: false,
              observed_item_count: 10,
            },
          ],
  };
}

function seedWorkspaceReads(pinia: ReturnType<typeof createPinia>) {
  const queryClient = getTestQueryClientForPinia(pinia);
  queryClient.setQueryData(workspaceQueryKeys.health, { status: 'ok', schema_ready: false });
  queryClient.setQueryData(workspaceQueryKeys.portfolio, {
    status: 'not_synced',
    positions: [],
    coverage: {},
    sync: {
      generation: 0,
      complete: false,
      started_at: null,
      completed_at: null,
      last_error_code: null,
      last_error_summary: null,
    },
  });
  queryClient.setQueryData(workspaceQueryKeys.policy, {
    active: null,
    drafts: [],
    superseded: [],
  });
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe('IndexPage', () => {
  it('uses the shared workspace root for the overview screen', async () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    const router = createRouter({ history: createMemoryHistory(), routes: [] });
    const wrapper = mountWithWorkspace(IndexPage, {
      global: { plugins: [pinia, router] },
    });
    const queryClient = getTestQueryClient(wrapper);
    queryClient.setQueryData(workspaceQueryKeys.health, { status: 'ok', schema_ready: false });
    queryClient.setQueryData(workspaceQueryKeys.portfolio, {
      status: 'not_synced',
      positions: [],
      coverage: {},
      sync: {
        generation: 0,
        complete: false,
        started_at: null,
        completed_at: null,
        last_error_code: null,
        last_error_summary: null,
      },
    });
    queryClient.setQueryData(workspaceQueryKeys.policy, {
      active: null,
      drafts: [],
      superseded: [],
    });
    await flushPromises();

    expect(wrapper.get('.workspace-page').classes()).toContain('overview-page');
    expect(
      wrapper
        .findAll('[data-slot="card"]')
        .filter((card) => card.classes().includes('summary-card')),
    ).toHaveLength(4);
    expect(
      wrapper
        .findAll('[data-slot="card"]')
        .filter((card) => card.classes().includes('workspace-card')),
    ).toHaveLength(5);
    const summaryGrid = wrapper.get('.summary-grid');
    expect(summaryGrid.classes()).toEqual(
      expect.arrayContaining(['tw:grid-cols-1', 'tw:sm:grid-cols-2', 'tw:xl:grid-cols-4']),
    );
    const runButton = wrapper
      .findAll('button')
      .find((button) => button.text().includes('Run DEMO recommendations'));
    expect(runButton?.attributes('disabled')).toBeDefined();
    expect(wrapper.get('h1').text()).toBe('Overview');
    expect(wrapper.findAll('.overview-page-action')).toHaveLength(2);
    wrapper.unmount();
  });

  it('loads the empty unconfigured cache from the local API and keeps refresh visible without workspace data', async () => {
    const fetcher = vi.fn<typeof fetch>((input) => {
      if (input === '/api/v1/market-data/exposures/cache') return Promise.resolve(jsonResponse([]));
      if (input === '/health')
        return Promise.resolve(jsonResponse({ status: 'ok', schema_ready: false }));
      if (input === '/api/v1/portfolio')
        return Promise.resolve(
          jsonResponse({
            status: 'not_synced',
            positions: [],
            coverage: {},
            sync: {
              generation: 0,
              complete: false,
              started_at: null,
              completed_at: null,
              last_error_code: null,
              last_error_summary: null,
            },
          }),
        );
      if (input === '/api/v1/policy')
        return Promise.resolve(jsonResponse({ active: null, drafts: [], superseded: [] }));
      throw new Error(`Unexpected request: ${requestUrl(input)}`);
    });
    vi.stubGlobal('fetch', fetcher);
    const pinia = createPinia();
    setActivePinia(pinia);
    const router = createRouter({ history: createMemoryHistory(), routes: [] });
    const wrapper = mountWithWorkspace(IndexPage, { global: { plugins: [pinia, router] } });
    await flushPromises();

    expect(fetcher).toHaveBeenCalledWith(
      '/api/v1/market-data/exposures/cache',
      expect.objectContaining({ method: 'GET' }),
    );
    expect(wrapper.text()).toContain('No look-through source is configured.');
    expect(
      wrapper
        .findAll('button')
        .some((button) => button.text().includes('Refresh ETF Look-Through')),
    ).toBe(true);
    expect(fetcher.mock.calls.map(([url, init]) => [url, init?.method])).toEqual([
      ['/api/v1/market-data/exposures/cache', 'GET'],
      ['/health', 'GET'],
      ['/api/v1/portfolio', 'GET'],
      ['/api/v1/policy', 'GET'],
    ]);
    wrapper.unmount();
  });

  it('refreshes a configured missing source once with a bodyless POST and displays API state', async () => {
    const pendingPost = deferred<Response>();
    const fetcher = vi.fn<typeof fetch>((input) => {
      if (input === '/api/v1/market-data/exposures/cache')
        return Promise.resolve(jsonResponse([exposureStatus('configured_missing')]));
      if (input === '/api/v1/market-data/exposures/refresh') return pendingPost.promise;
      return Promise.resolve(jsonResponse({}));
    });
    vi.stubGlobal('fetch', fetcher);
    const pinia = createPinia();
    setActivePinia(pinia);
    seedWorkspaceReads(pinia);
    const router = createRouter({ history: createMemoryHistory(), routes: [] });
    const wrapper = mountWithWorkspace(IndexPage, { global: { plugins: [pinia, router] } });
    await flushPromises();
    expect(wrapper.text()).toContain('ITOT: not yet cached');

    const button = wrapper
      .findAll('button')
      .find((candidate) => candidate.text().includes('Refresh ETF Look-Through'))!;
    await button.trigger('click');
    await flushPromises();
    expect(button.attributes('disabled')).toBeDefined();
    expect(button.text()).toContain('Refreshing ETF Look-Through');
    await button.trigger('click');
    expect(
      fetcher.mock.calls.filter(([url]) => url === '/api/v1/market-data/exposures/refresh'),
    ).toHaveLength(1);
    const post = fetcher.mock.calls.find(
      ([url]) => url === '/api/v1/market-data/exposures/refresh',
    );
    expect(post?.[1]).toMatchObject({ method: 'POST' });
    expect(post?.[1]?.body).toBeUndefined();
    expect(new Headers(post?.[1]?.headers).has('Content-Type')).toBe(false);

    pendingPost.resolve(jsonResponse([exposureStatus('current')]));
    await flushPromises();
    expect(wrapper.text()).toContain('ITOT: current');
    expect(wrapper.text()).toContain('holdings as of 2026-11-17');
    expect(wrapper.text()).toContain('sector 0.834567890123456789');
    expect(
      fetcher.mock.calls.filter(([url]) => url === '/api/v1/market-data/exposures/cache'),
    ).toHaveLength(1);
    expect(
      fetcher.mock.calls
        .map(([url]) => url)
        .filter(
          (url) =>
            requestUrl(url).includes('/portfolio/sync') || requestUrl(url).includes('/optimizer/'),
        ),
    ).toEqual([]);
    wrapper.unmount();
  });

  it('retains prior cached dates and observed coverage while showing persisted refresh failure', async () => {
    const fetcher = vi.fn<typeof fetch>((input) => {
      if (input === '/api/v1/market-data/exposures/cache')
        return Promise.resolve(jsonResponse([exposureStatus('stale', true)]));
      if (input === '/api/v1/market-data/exposures/refresh')
        return Promise.resolve(
          jsonResponse(
            {
              code: 'exposure_refresh_failed',
              message: 'Could not refresh ETF holdings',
              details: {},
              correlation_id: 'corr-refresh',
            },
            502,
          ),
        );
      return Promise.resolve(jsonResponse({}));
    });
    vi.stubGlobal('fetch', fetcher);
    const pinia = createPinia();
    setActivePinia(pinia);
    seedWorkspaceReads(pinia);
    const router = createRouter({ history: createMemoryHistory(), routes: [] });
    const wrapper = mountWithWorkspace(IndexPage, { global: { plugins: [pinia, router] } });
    await flushPromises();
    await wrapper
      .findAll('button')
      .find((button) => button.text().includes('Refresh ETF Look-Through'))!
      .trigger('click');
    await flushPromises();

    expect(wrapper.text()).toContain('Could not refresh ETF holdings');
    expect(wrapper.text()).toContain('ITOT: stale');
    expect(wrapper.text()).toContain('holdings as of 2026-11-17');
    expect(wrapper.text()).toContain('sector 0.834567890123456789');
    expect(wrapper.text()).toContain('latest refresh failed: Provider refresh failed');
    expect(fetcher.mock.calls.map(([url, init]) => [url, init?.method])).toContainEqual([
      '/api/v1/market-data/exposures/cache',
      'GET',
    ]);
    expect(
      fetcher.mock.calls.filter(([url]) => url === '/api/v1/market-data/exposures/cache'),
    ).toHaveLength(2);
    expect(
      fetcher.mock.calls.filter(([url]) => url === '/api/v1/market-data/exposures/refresh'),
    ).toHaveLength(1);
    expect(
      fetcher.mock.calls
        .map(([url]) => url)
        .filter(
          (url) =>
            requestUrl(url).includes('/portfolio/sync') || requestUrl(url).includes('/optimizer/'),
        ),
    ).toEqual([]);
    wrapper.unmount();
  });

  it('does not allow a delayed mount-time cache read to overwrite a successful refresh response', async () => {
    const delayedGet = deferred<Response>();
    const fetcher = vi.fn<typeof fetch>((input) => {
      if (input === '/api/v1/market-data/exposures/cache') return delayedGet.promise;
      if (input === '/api/v1/market-data/exposures/refresh')
        return Promise.resolve(jsonResponse([exposureStatus('current')]));
      return Promise.resolve(jsonResponse({}));
    });
    vi.stubGlobal('fetch', fetcher);
    const pinia = createPinia();
    setActivePinia(pinia);
    seedWorkspaceReads(pinia);
    const router = createRouter({ history: createMemoryHistory(), routes: [] });
    const wrapper = mountWithWorkspace(IndexPage, { global: { plugins: [pinia, router] } });
    await wrapper
      .findAll('button')
      .find((button) => button.text().includes('Refresh ETF Look-Through'))!
      .trigger('click');
    await flushPromises();
    delayedGet.resolve(jsonResponse([exposureStatus('configured_missing')]));
    await flushPromises();

    expect(wrapper.text()).toContain('ITOT: current');
    expect(wrapper.text()).toContain('holdings as of 2026-11-17');
    expect(wrapper.text()).not.toContain('ITOT: not yet cached');
    expect(
      fetcher.mock.calls.filter(([url]) => url === '/api/v1/market-data/exposures/cache'),
    ).toHaveLength(1);
    wrapper.unmount();
  });

  it('leads with confirmed optimization outcomes and a grouped API-sourced preview', async () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    const store = mountWorkspaceHarness().workspace;
    seedCurrentRunForTest(store, selectedOverviewRunFixture());
    store.currentRunView = 'current';
    const queryClient = getTestQueryClientForPinia(pinia);
    seedMismatchedPortfolioAndPolicy(queryClient, 'active-policy-b', 'active-policy-b');
    queryClient.setQueryData(workspaceQueryKeys.health, {
      status: 'ok',
      schema_ready: true,
      broker_mode: 'demo',
      live_broker_enabled: false,
      order_submission_enabled: false,
    });
    queryClient.setQueryData(workspaceQueryKeys.portfolio, portfolioFixture('active-policy-b'));
    queryClient.setQueryData(workspaceQueryKeys.policy, {
      active: {
        id: 'active-policy-b',
        revision_number: 3,
        status: 'ACTIVE',
        created_at: '2026-01-01T00:00:00Z',
        activated_at: '2026-01-01T00:00:00Z',
        settings: {
          prefer_etf_buys: false,
          allow_gain_sales: false,
          permit_etf_harvest: false,
          permit_muni_exit: false,
          gain_budget_usd: '0.00',
          max_sell_tickers_per_batch: 2,
          max_sell_lots_per_batch: 4,
          max_total_orders_per_batch: 6,
        },
        sleeves: [
          {
            sleeve_key: 'us',
            display_name: 'U.S. direct-index container',
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
          {
            sleeve_key: 'legacy',
            display_name: 'Legacy U.S. holdings',
            sort_order: 2,
            parent_sleeve_key: 'us',
            target_pct: '70.0000',
            drift_band_pp: '5.0000',
            enabled: true,
            is_direct_index_container: false,
            is_direct_index_sleeve: true,
            is_transition_destination: false,
            is_cash_sleeve: false,
          },
          {
            sleeve_key: 'transition_nested',
            display_name: 'New U.S. holdings',
            sort_order: 3,
            parent_sleeve_key: 'us',
            target_pct: '30.0000',
            drift_band_pp: '5.0000',
            enabled: true,
            is_direct_index_container: false,
            is_direct_index_sleeve: false,
            is_transition_destination: true,
            is_cash_sleeve: false,
          },
          {
            sleeve_key: 'disabled-destination',
            display_name: 'Disabled destination',
            sort_order: 4,
            parent_sleeve_key: 'us',
            target_pct: '0.0000',
            drift_band_pp: '0.0000',
            enabled: false,
            is_direct_index_container: false,
            is_direct_index_sleeve: false,
            is_transition_destination: true,
            is_cash_sleeve: false,
          },
        ],
        allowed_securities: [
          {
            ticker: 'VTI',
            sleeve_key: 'transition_nested',
            sub_sleeve_key: 'new',
            replacement_set_id: 'new-us-set',
            priority: 1,
            enabled: true,
            exposure_suitability: 'broad-market',
          },
          {
            ticker: 'SCHB',
            sleeve_key: 'transition_nested',
            sub_sleeve_key: 'new',
            replacement_set_id: 'new-us-set',
            priority: 2,
            enabled: false,
            exposure_suitability: 'broad-market',
          },
          {
            ticker: 'VXF',
            sleeve_key: 'transition_nested',
            sub_sleeve_key: 'new',
            replacement_set_id: 'second-set',
            priority: 3,
            enabled: true,
            exposure_suitability: null,
          },
          {
            ticker: 'CUSTOM',
            sleeve_key: 'custom-destination',
            sub_sleeve_key: null,
            replacement_set_id: 'custom-set',
            priority: 1,
            enabled: false,
            exposure_suitability: 'custom-only',
          },
          {
            ticker: 'COLLISION-ONE',
            sleeve_key: 'a',
            sub_sleeve_key: 'b:c',
            replacement_set_id: 'd',
            priority: 1,
            enabled: true,
            exposure_suitability: null,
          },
          {
            ticker: 'COLLISION-TWO',
            sleeve_key: 'a',
            sub_sleeve_key: 'b',
            replacement_set_id: 'c:d',
            priority: 2,
            enabled: true,
            exposure_suitability: null,
          },
        ],
        overrides: [],
      },
      drafts: [],
      superseded: [],
    } as never);
    const router = createRouter({ history: createMemoryHistory(), routes: [] });
    const wrapper = mountWithWorkspace(IndexPage, {
      global: { plugins: [pinia, router] },
    });
    await flushPromises();

    const workspaceCards = wrapper.findAll('.workspace-card');
    expect(
      workspaceCards.map((card) =>
        card
          .classes()
          .find((name) =>
            [
              'transition-card',
              'allocation-card',
              'run-card',
              'policy-card',
              'account-card',
            ].includes(name),
          ),
      ),
    ).toEqual(['transition-card', 'allocation-card', 'run-card', 'policy-card', 'account-card']);
    const outcomes = wrapper.get('[aria-label="Current optimization outcomes"]');
    expect(outcomes.text()).toContain('Selected gross losses');
    expect(outcomes.text()).toContain('8.00 USD');
    expect(outcomes.text()).toContain('Estimated tax benefit');
    expect(outcomes.text()).toContain('Estimate unavailable');
    expect(outcomes.text()).toContain('ST-5.00 USD');
    expect(outcomes.text()).toContain('LT2.00 USD');
    expect(outcomes.text()).toContain('Net-3.00 USD');
    expect(outcomes.text()).toContain('Risk tracking Unavailable');

    const preview = wrapper.get('.run-card');
    expect(preview.text().indexOf('Priority 1')).toBeLessThan(preview.text().indexOf('Priority 4'));
    expect(preview.text()).toContain('Reduce MSFT legacy exposure.');
    expect(preview.text()).toContain('AAPL-LOT-1');
    expect(preview.text()).toContain('2 shares');
    expect(preview.text()).toContain('P/L -5.00 USD');
    expect(preview.text().split('BUY 1 shares VTI').length - 1).toBe(1);
    expect(preview.find('a[href="/recommendations"]').exists()).toBe(true);
    expect(preview.find('a[href="/review"]').exists()).toBe(true);

    const policy = wrapper.get('.policy-card');
    expect(policy.text()).toContain(
      'Individual equities, VB and VXF default to U.S. direct-index container',
    );
    expect(policy.text()).toContain('Configured U.S. new destination: New U.S. holdings');
    expect(policy.text()).toContain('Prefer ETF buysDisabled');
    expect(policy.text()).toContain('Allow gain salesDisabled');
    expect(policy.text()).toContain('Gain budget0.00 USD');
    expect(policy.text()).toContain('2 tickers · 4 lots · 6 total orders');
    expect(policy.text()).toContain(
      'Small legacy and DRIP lots are not blocked by a minimum SELL notional',
    );
    expect(policy.text()).toContain('new-us-set');
    expect(policy.text()).toContain('VTI');
    expect(policy.text()).toContain('SCHB');
    expect(policy.text()).toContain('Disabled · Suitability: broad-market');
    expect(policy.text()).toContain('second-set');
    expect(policy.text()).toContain('custom-destination (unconfigured destination)');
    expect(policy.text()).toContain('COLLISION-ONE');
    expect(policy.text()).toContain('COLLISION-TWO');
    const collisionGroups = policy
      .findAll('li')
      .filter(
        (item) =>
          item.classes().includes('tw:rounded-md') &&
          (item.text().includes('COLLISION-ONE') || item.text().includes('COLLISION-TWO')),
      );
    expect(collisionGroups).toHaveLength(2);
    expect(collisionGroups.map((item) => item.text())).toEqual([
      expect.stringContaining('COLLISION-ONE'),
      expect.stringContaining('COLLISION-TWO'),
    ]);
    const cachedPolicy = queryClient.getQueryData<PolicyResponse>(workspaceQueryKeys.policy);
    if (!cachedPolicy?.active) throw new Error('The active policy fixture is unavailable');
    queryClient.setQueryData(workspaceQueryKeys.policy, {
      ...cachedPolicy,
      active: {
        ...cachedPolicy.active,
        allowed_securities: [...cachedPolicy.active.allowed_securities].reverse(),
      },
    });
    await flushPromises();
    const reorderedCollisionGroups = policy
      .findAll('li')
      .filter(
        (item) =>
          item.classes().includes('tw:rounded-md') &&
          (item.text().includes('COLLISION-ONE') || item.text().includes('COLLISION-TWO')),
      );
    expect(reorderedCollisionGroups).toHaveLength(2);
    expect(reorderedCollisionGroups.map((item) => item.text())).toEqual([
      expect.stringContaining('COLLISION-TWO'),
      expect.stringContaining('COLLISION-ONE'),
    ]);
    expect(policy.find('a[href="/policy#replacement-sets"]').exists()).toBe(true);
    seedCurrentRunForTest(store, selectedOverviewRunFixture(true));
    store.currentRunView = 'current';
    await flushPromises();
    const unavailablePreview = wrapper.get('.run-card');
    expect(unavailablePreview.text()).toContain('Sleeve unavailable (not returned by API)');
    expect(unavailablePreview.text()).toContain(
      'Signed group P/L · ST Unavailable (not returned by API)',
    );
    wrapper.unmount();
  });

  it('uses shared freshness selectors to withhold an unconfirmed run comparison', async () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    const store = mountWorkspaceHarness().workspace;
    seedCurrentRunForTest(store, {
      run_id: 'run-current',
      source_generation: 7,
      policy_revision_id: 'policy-current',
      frozen_display_context: { available: false, unavailable_reason: 'missing' },
      portfolio_effects: null,
      groups: [],
    } as never);
    store.currentRunView = 'current';
    const router = createRouter({ history: createMemoryHistory(), routes: [] });
    const wrapper = mountWithWorkspace(IndexPage, {
      global: { plugins: [pinia, router] },
    });
    const queryClient = getTestQueryClient(wrapper);
    seedMismatchedPortfolioAndPolicy(queryClient, 'active-policy-b', 'policy-current');
    await queryClient
      .fetchQuery({
        queryKey: workspaceQueryKeys.policy,
        queryFn: () => Promise.reject(new Error('stale policy fixture')),
        staleTime: 0,
        retry: false,
      })
      .catch(() => undefined);
    await flushPromises();
    expect(wrapper.get('.policy-card').text()).toContain('Active allocation targets');
    expect(wrapper.get('.policy-card').text()).toContain('No enabled targets returned.');

    expect(wrapper.text()).toContain('No current matching recommendation run');

    expect(wrapper.text()).toContain('cached data is being shown');
    wrapper.unmount();
  });

  it('keeps a saved run context when the active policy renames or removes its sleeve', async () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    const store = mountWorkspaceHarness().workspace;
    seedCurrentRunForTest(store, {
      run_id: 'saved-historical-run',
      groups: [],
      portfolio_effects: null,
      frozen_display_context: {
        available: true,
        source: 'policy_revision',
        policy_revision_id: 'policy-old',
        revision_number: 2,
        created_at: '2024-01-01T00:00:00Z',
        activated_at: '2024-01-02T00:00:00Z',
        sleeves: [
          {
            sleeve_key: 'us',
            display_name: 'Historical US Equity',
            sort_order: 1,
            parent_sleeve_key: null,
            target_pct: '63.0000',
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
      },
    } as never);
    store.currentRunView = 'saved';
    const router = createRouter({ history: createMemoryHistory(), routes: [] });
    const wrapper = mountWithWorkspace(IndexPage, {
      global: { plugins: [pinia, router] },
    });
    const queryClient = getTestQueryClient(wrapper);
    queryClient.setQueryData(workspaceQueryKeys.health, { status: 'ok', schema_ready: false });
    queryClient.setQueryData(workspaceQueryKeys.portfolio, {
      status: 'not_synced',
      positions: [],
      coverage: {},
      sync: {
        generation: 0,
        complete: false,
        started_at: null,
        completed_at: null,
        last_error_code: null,
        last_error_summary: null,
      },
    });
    queryClient.setQueryData(workspaceQueryKeys.policy, {
      active: {
        id: 'policy-current',
        revision_number: 9,
        sleeves: [
          {
            sleeve_key: 'domestic',
            display_name: 'Current Domestic Equity',
            target_pct: '100.0000',
            enabled: true,
          },
        ],
        allowed_securities: [],
      },
      drafts: [],
      superseded: [],
    });
    await flushPromises();

    const historical = wrapper.get('[aria-label="Overview frozen run context"]');
    expect(historical.text()).toContain('Historical US Equity');
    expect(historical.text()).toContain('63.0000%');
    expect(historical.text()).toContain('3210.00');
    expect(historical.text()).not.toContain('Current Domestic Equity');
    expect(wrapper.text()).toContain('Current Domestic Equity');
    wrapper.unmount();
  });
  it('uses portfolio API sleeve keys when successful portfolio and policy reads disagree', async () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    const router = createRouter({ history: createMemoryHistory(), routes: [] });
    const wrapper = mountWithWorkspace(IndexPage, {
      global: { plugins: [pinia, router] },
    });
    seedMismatchedPortfolioAndPolicy(getTestQueryClient(wrapper));
    await flushPromises();

    expect(wrapper.text()).toContain(
      'Portfolio effects use policy revision portfolio-revision-a; the active policy is active-policy-b.',
    );
    const mismatchAlert = wrapper
      .findAll('[role="status"]')
      .find((alert) =>
        alert.text().includes('Portfolio effects use policy revision portfolio-revision-a'),
      );
    expect(mismatchAlert?.attributes('role')).toBe('status');
    expect(wrapper.get('.allocation-card').text()).toContain('us');
    expect(wrapper.get('.allocation-card').text()).toContain('100.0000%');
    expect(wrapper.get('.allocation-card').text()).not.toContain('Active policy US label');
    expect(wrapper.get('.transition-card').text()).toContain('transition_nested');
    expect(wrapper.get('.transition-card').text()).not.toContain('Active policy nested label');
    expect(wrapper.get('.transition-card').text()).toContain(
      'Current US transition data is stale; values are withheld. Review the freshness notice.',
    );
    expect(wrapper.get('.transition-card').text()).not.toContain('Currently in new holdings');
    expect(wrapper.get('.transition-card').text()).not.toContain('100.00 USD');
    wrapper.unmount();
  });

  it('keeps cached portfolio labels unlocalized after a failed follow-up policy read', async () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    const router = createRouter({ history: createMemoryHistory(), routes: [] });
    const wrapper = mountWithWorkspace(IndexPage, {
      global: { plugins: [pinia, router] },
    });
    const queryClient = getTestQueryClient(wrapper);
    seedMismatchedPortfolioAndPolicy(queryClient);
    await queryClient
      .fetchQuery({
        queryKey: workspaceQueryKeys.policy,
        queryFn: () => Promise.reject(new Error('policy transport failed')),
        staleTime: 0,
        retry: false,
      })
      .catch(() => undefined);
    await flushPromises();

    expect(wrapper.text()).toContain('cached data is being shown');
    expect(wrapper.text()).toContain('Portfolio effects use policy revision portfolio-revision-a');
    expect(wrapper.get('.allocation-card').text()).not.toContain('Active policy US label');
    expect(wrapper.get('.allocation-card').text()).toContain('100.0000%');
    expect(wrapper.get('.transition-card').text()).not.toContain('Active policy nested label');
    wrapper.unmount();
  });

  it('withholds Overview run metrics and effects across navigation until a selection confirms', async () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    const store = mountWorkspaceHarness().workspace;

    seedCurrentRunForTest(store, currentRunFixture() as never);
    store.currentRunView = 'current';
    const router = createRouter({ history: createMemoryHistory(), routes: [] });
    const wrapper = mountWithWorkspace(IndexPage, {
      global: { plugins: [pinia, router] },
    });
    seedMismatchedPortfolioAndPolicy(
      getTestQueryClient(wrapper),
      'active-policy-b',
      'active-policy-b',
    );
    await flushPromises();
    const response = deferred<Response>();
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>(() => response.promise),
    );

    const mutation = store.recalculateSelection({ selected_group_ids: ['group-a'] });
    await flushPromises();
    expect(store.reviewMutationPending).toBe(true);
    wrapper.unmount();

    const remounted = mountWithWorkspace(IndexPage, {
      global: { plugins: [pinia, router] },
    });
    seedMismatchedPortfolioAndPolicy(
      getTestQueryClient(remounted),
      'active-policy-b',
      'active-policy-b',
    );
    await flushPromises();
    expect(remounted.text()).toContain('awaiting API confirmation');
    expect(remounted.text()).not.toContain('-5.00');
    expect(remounted.find('.overview-metrics').exists()).toBe(false);
    expect(remounted.get('.allocation-card').text()).toContain('100.0000%');

    response.resolve(jsonResponse(currentRunFixture('-6.00', '80.0000')));
    await mutation;
    await flushPromises();
    expect(store.reviewMutationPending).toBe(false);
    expect(remounted.text()).not.toContain('awaiting API confirmation');
    expect(remounted.get('.overview-metrics').text()).toContain('-6.00');
    expect(remounted.get('.allocation-card').text()).toContain('80.0000%');
    remounted.unmount();
  });

  it('restores the last successful Overview run after a pending annotation fails', async () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    const store = mountWorkspaceHarness().workspace;

    const run = currentRunFixture();
    seedCurrentRunForTest(store, run as never);
    const previousRun = currentRunForTest(store)!;
    store.currentRunView = 'current';
    const router = createRouter({ history: createMemoryHistory(), routes: [] });
    const wrapper = mountWithWorkspace(IndexPage, {
      global: { plugins: [pinia, router] },
    });
    seedMismatchedPortfolioAndPolicy(
      getTestQueryClient(wrapper),
      'active-policy-b',
      'active-policy-b',
    );
    await flushPromises();
    const response = deferred<Response>();
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>(() => response.promise),
    );

    const mutation = store
      .annotateGroup('current-run', 'group-a', { note: 'pending note' })
      .catch(() => null);
    await flushPromises();
    expect(store.reviewMutationPending).toBe(true);
    wrapper.unmount();

    const remounted = mountWithWorkspace(IndexPage, {
      global: { plugins: [pinia, router] },
    });
    seedMismatchedPortfolioAndPolicy(
      getTestQueryClient(remounted),
      'active-policy-b',
      'active-policy-b',
    );
    await flushPromises();
    expect(remounted.text()).toContain('awaiting API confirmation');
    expect(remounted.find('.overview-metrics').exists()).toBe(false);

    response.reject(new Error('annotation transport failed'));
    await mutation;
    await flushPromises();
    expect(store.reviewMutationPending).toBe(false);
    expect(currentRunForTest(store)).toBe(previousRun);
    expect(store.currentRunView).toBe('current');
    expect(remounted.text()).not.toContain('awaiting API confirmation');
    expect(remounted.get('.overview-metrics').text()).toContain('-5.00');
    expect(remounted.get('.allocation-card').text()).toContain('70.0000%');
    remounted.unmount();
  });
});

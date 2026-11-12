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
import { getTestQueryClient } from '@/test-utils/workspace-mount';
import type { QueryClient } from '@tanstack/vue-query';
import IndexPage from './IndexPage.vue';

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

function jsonResponse(value: unknown): Response {
  return new Response(JSON.stringify(value), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
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
    expect(wrapper.get('.policy-subhead').classes()).toEqual(
      expect.arrayContaining(['tw:text-sm!', 'tw:text-muted-foreground', 'tw:uppercase']),
    );

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

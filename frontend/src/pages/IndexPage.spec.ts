// @vitest-environment jsdom
import { flushPromises } from '@vue/test-utils';
import { mountWorkspacePageWithQuasar } from '@/test-utils/quasar-mount';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';
import { createMemoryHistory, createRouter } from 'vue-router';
import { useWorkspaceStore } from '@/stores/workspace-store';
import IndexPage from './IndexPage.vue';
import { QBanner, QCard } from 'quasar';

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
  store: ReturnType<typeof useWorkspaceStore>,
  portfolioRevisionId = 'portfolio-revision-a',
  policyRevisionId = 'active-policy-b',
) {
  const confirmedAt = '2026-01-01T00:00:00Z';
  store.health = {
    status: 'ok',
    schema_ready: true,
    broker_mode: 'demo',
    live_broker_enabled: false,
    order_submission_enabled: false,
  };
  store.portfolio = portfolioFixture(portfolioRevisionId) as never;
  store.policy = {
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
  } as never;
  store.resourceFreshness.health = { status: 'fresh', confirmedAt };
  store.resourceFreshness.portfolio = { status: 'fresh', confirmedAt };
  store.resourceFreshness.policy = { status: 'fresh', confirmedAt };
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
  it('uses the shared workspace root for the overview screen', () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    const store = useWorkspaceStore();
    store.health = { status: 'ok', schema_ready: false } as never;
    store.portfolio = {
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
    } as never;
    store.policy = { active: null, drafts: [], superseded: [] };
    const router = createRouter({ history: createMemoryHistory(), routes: [] });
    const wrapper = mountWorkspacePageWithQuasar(IndexPage, {
      global: { plugins: [pinia, router] },
    });

    expect(wrapper.get('.workspace-page').classes()).toContain('overview-page');
    expect(
      wrapper.findAllComponents(QCard).filter((card) => card.classes().includes('summary-card')),
    ).toHaveLength(4);
    expect(
      wrapper.findAllComponents(QCard).filter((card) => card.classes().includes('workspace-card')),
    ).toHaveLength(5);
    expect(wrapper.get('h1').text()).toBe('Overview');

    expect(wrapper.findAll('.overview-page-action')).toHaveLength(2);
    wrapper.unmount();
  });
  it('uses shared freshness selectors to withhold an unconfirmed run comparison', () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    const store = useWorkspaceStore();
    store.health = {
      status: 'ok',
      schema_ready: true,
      broker_mode: 'demo',
      live_broker_enabled: false,
      order_submission_enabled: false,
    };
    store.portfolio = {
      status: 'ready',
      demo: true,
      source: 'fixture',
      account: { display_name: 'Demo account', account_type: 'brokerage', tax_treatment: null },
      as_of: '2026-01-01T00:00:00Z',
      cash_usd: '0.00',
      settled_buying_power_usd: '0.00',
      positions_market_value_usd: '0.00',
      portfolio_total_usd: '0.00',
      position_count: 0,
      positions: [],
      active_policy_revision_id: 'policy-current',
      unassigned_tickers: [],
      sync: {
        generation: 7,
        complete: true,
        started_at: null,
        completed_at: '2026-01-01T00:00:00Z',
        last_error_code: null,
        last_error_summary: null,
      },
      allocation: { current: null, proposed: null, target: null },
      us_transition: null,
      coverage: {},
    } as never;
    store.policy = {
      active: { id: 'policy-current', activation_errors: [] },
      drafts: [],
      superseded: [],
    } as never;
    store.resourceFreshness.policy = { status: 'stale', confirmedAt: '2026-01-01T00:00:00Z' };
    store.currentRun = {
      run_id: 'run-current',
      source_generation: 7,
      policy_revision_id: 'policy-current',
      frozen_display_context: { available: false, unavailable_reason: 'missing' },
      portfolio_effects: null,
      groups: [],
    } as never;
    store.currentRunView = 'current';
    const router = createRouter({ history: createMemoryHistory(), routes: [] });
    const wrapper = mountWorkspacePageWithQuasar(IndexPage, {
      global: { plugins: [pinia, router] },
    });
    expect(wrapper.get('.policy-subhead').classes()).toEqual(
      expect.arrayContaining(['text-subtitle2', 'text-blue-grey-8', 'text-uppercase']),
    );

    expect(wrapper.text()).toContain('No current matching recommendation run');

    expect(wrapper.text()).toContain('cached data is being shown');
    wrapper.unmount();
  });

  it('keeps a saved run context when the active policy renames or removes its sleeve', () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    const store = useWorkspaceStore();
    store.health = { status: 'ok', schema_ready: false } as never;
    store.portfolio = {
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
    } as never;
    store.policy = {
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
    } as never;
    store.currentRun = {
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
    } as never;
    store.currentRunView = 'saved';
    const router = createRouter({ history: createMemoryHistory(), routes: [] });
    const wrapper = mountWorkspacePageWithQuasar(IndexPage, {
      global: { plugins: [pinia, router] },
    });

    const historical = wrapper.get('[aria-label="Overview frozen run context"]');
    expect(historical.text()).toContain('Historical US Equity');
    expect(historical.text()).toContain('63.0000%');
    expect(historical.text()).toContain('3210.00');
    expect(historical.text()).not.toContain('Current Domestic Equity');
    expect(wrapper.text()).toContain('Current Domestic Equity');
    wrapper.unmount();
  });
  it('uses portfolio API sleeve keys when successful portfolio and policy reads disagree', () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    const store = useWorkspaceStore();
    seedMismatchedPortfolioAndPolicy(store);
    const router = createRouter({ history: createMemoryHistory(), routes: [] });
    const wrapper = mountWorkspacePageWithQuasar(IndexPage, {
      global: { plugins: [pinia, router] },
    });

    expect(wrapper.text()).toContain(
      'Portfolio effects use policy revision portfolio-revision-a; the active policy is active-policy-b.',
    );
    const mismatchBanner = wrapper
      .findAllComponents(QBanner)
      .find((banner) =>
        banner.text().includes('Portfolio effects use policy revision portfolio-revision-a'),
      );
    expect(mismatchBanner?.attributes('role')).toBe('status');
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
    const store = useWorkspaceStore();
    seedMismatchedPortfolioAndPolicy(store);
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>(() => Promise.reject(new Error('policy transport failed'))),
    );
    await expect(store.loadPolicy()).rejects.toThrow('policy transport failed');
    const router = createRouter({ history: createMemoryHistory(), routes: [] });
    const wrapper = mountWorkspacePageWithQuasar(IndexPage, {
      global: { plugins: [pinia, router] },
    });

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
    const store = useWorkspaceStore();
    seedMismatchedPortfolioAndPolicy(store, 'active-policy-b', 'active-policy-b');
    store.currentRun = currentRunFixture() as never;
    store.currentRunView = 'current';
    const router = createRouter({ history: createMemoryHistory(), routes: [] });
    const wrapper = mountWorkspacePageWithQuasar(IndexPage, {
      global: { plugins: [pinia, router] },
    });
    const response = deferred<Response>();
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>(() => response.promise),
    );

    const mutation = store.recalculateSelection({ selected_group_ids: ['group-a'] });
    await flushPromises();
    expect(store.reviewMutationPending).toBe(true);
    wrapper.unmount();

    const remounted = mountWorkspacePageWithQuasar(IndexPage, {
      global: { plugins: [pinia, router] },
    });
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
    const store = useWorkspaceStore();
    seedMismatchedPortfolioAndPolicy(store, 'active-policy-b', 'active-policy-b');
    const previousRun = currentRunFixture();
    store.currentRun = previousRun as never;
    store.currentRunView = 'current';
    const router = createRouter({ history: createMemoryHistory(), routes: [] });
    const wrapper = mountWorkspacePageWithQuasar(IndexPage, {
      global: { plugins: [pinia, router] },
    });
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

    const remounted = mountWorkspacePageWithQuasar(IndexPage, {
      global: { plugins: [pinia, router] },
    });
    await flushPromises();
    expect(remounted.text()).toContain('awaiting API confirmation');
    expect(remounted.find('.overview-metrics').exists()).toBe(false);

    response.reject(new Error('annotation transport failed'));
    await mutation;
    await flushPromises();
    expect(store.reviewMutationPending).toBe(false);
    expect(store.currentRun).toBe(previousRun);
    expect(store.currentRunView).toBe('current');
    expect(remounted.text()).not.toContain('awaiting API confirmation');
    expect(remounted.get('.overview-metrics').text()).toContain('-5.00');
    expect(remounted.get('.allocation-card').text()).toContain('70.0000%');
    remounted.unmount();
  });
});

// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';
import type { OptimizerRecommendationsResponse } from '@/types/api';
import RecommendationsPage from './RecommendationsPage.vue';
import { useWorkspaceStore } from '@/stores/workspace-store';

function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
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

function setup(run: OptimizerRecommendationsResponse | null = makeRun()) {
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
  store.portfolio = readyPortfolio() as never;
  store.policy = {
    active: {
      id: 'policy-r1',
      activation_errors: [],
      sleeves: [{ sleeve_key: 'us', display_name: 'US equity' }],
    },
    drafts: [],
    superseded: [],
  } as never;
  if (run) {
    store.currentRun = run;
    store.currentRunView = 'current';
  }
  return { pinia, store };
}

beforeEach(() => vi.unstubAllGlobals());
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('RecommendationsPage', () => {
  it('shows API-only DEMO values, renders a shared BUY once, and re-solves group selections with broker lot IDs', async () => {
    const { pinia, store } = setup();
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
    const wrapper = mount(RecommendationsPage, { global: { plugins: [pinia] } });
    await flushPromises();

    expect(wrapper.text()).toContain('DEMO ONLY · non-actionable');
    expect(wrapper.text()).toContain('The real optimizer is unavailable');
    expect(wrapper.text()).toContain('Unavailable (not returned by API)');
    expect(wrapper.get('.workspace-page').classes()).toContain('recommendations-page');
    expect(wrapper.get('h1').text()).toBe('Recommendations');
    expect(
      wrapper.findAll('.leg-card').filter((card) => card.attributes('id') === 'leg-buy-shared'),
    ).toHaveLength(1);
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
    const wrapper = mount(RecommendationsPage, { global: { plugins: [pinia] } });
    await flushPromises();

    const groupCheckbox = wrapper.get('input[aria-label="Select recommendation group group-a"]');
    await groupCheckbox.setValue(true);
    expect(wrapper.text()).toContain('Previous basket effects are withheld');
    expect(wrapper.text()).not.toContain('-4.00 USD');
    expect((groupCheckbox.element as HTMLInputElement).checked).toBe(false);

    resolveSelection?.(jsonResponse(updatedRun));
    await flushPromises();
    expect(
      (
        wrapper.get('input[aria-label="Select recommendation group group-a"]')
          .element as HTMLInputElement
      ).checked,
    ).toBe(true);
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
    const wrapper = mount(RecommendationsPage, { global: { plugins: [pinia] } });
    await flushPromises();
    const lot = wrapper.get('input[aria-label="Select SELL lot BROKER-A1 in group group-a"]');
    await lot.setValue(false);
    await flushPromises();

    const payload = JSON.parse(fetcher.mock.calls[0]?.[1]?.body as string) as {
      selected_group_ids: string[];
      selected_sell_lots: Record<string, string[]>;
    };
    expect(payload).toEqual({ selected_group_ids: [], selected_sell_lots: {} });
    expect(store.currentRun).toBe(selectedRun);
    expect(
      (
        wrapper.get('input[aria-label="Select SELL lot BROKER-A1 in group group-a"]')
          .element as HTMLInputElement
      ).checked,
    ).toBe(true);
    expect(wrapper.text()).toContain(
      'Selection re-solve failed; the last successful API selection remains in view',
    );
    expect(wrapper.text()).not.toContain('requested group selected');
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
    const wrapper = mount(RecommendationsPage, { global: { plugins: [pinia] } });
    await flushPromises();
    expect(fetcher).not.toHaveBeenCalled();
    await wrapper.get('input[placeholder="Run ID from Activity"]').setValue('saved-run-1');
    await wrapper.get('form.saved-run-form').trigger('submit');
    await flushPromises();

    expect(store.currentRunView).toBe('saved');
    expect(wrapper.text()).toContain('Saved run · frozen API context · read-only');
    expect(
      (
        wrapper.get('input[aria-label="Select recommendation group group-a"]')
          .element as HTMLInputElement
      ).disabled,
    ).toBe(true);
    expect(fetcher.mock.calls.some(([, init]) => init?.method === 'POST')).toBe(false);
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
    const wrapper = mount(RecommendationsPage, { global: { plugins: [pinia] } });
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
    const firstMount = mount(RecommendationsPage, { global: { plugins: [pinia] } });
    await flushPromises();

    const firstGroup = firstMount.get('[aria-label="Notes and rejection for group-a"]');
    expect((firstGroup.get('textarea').element as HTMLTextAreaElement).value).toBe('saved note A');
    expect((firstGroup.get('input').element as HTMLInputElement).value).toBe('saved rejection A');
    firstMount.unmount();

    const remount = mount(RecommendationsPage, { global: { plugins: [pinia] } });
    await flushPromises();
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
    const wrapper = mount(RecommendationsPage, { global: { plugins: [pinia] } });
    await flushPromises();

    const lotA2 = wrapper.get('input[aria-label="Select SELL lot BROKER-A2 in group group-a"]');
    await lotA2.setValue(true);
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
    const wrapper = mount(RecommendationsPage, { global: { plugins: [pinia] } });
    await flushPromises();

    const lotA2 = wrapper.get('input[aria-label="Select SELL lot BROKER-A2 in group group-a"]');
    await lotA2.setValue(true);
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
    let annotationPayload: unknown;
    const fetcher = vi.fn<typeof fetch>((input, init) => {
      const url = urlOf(input);
      if (url.pathname.endsWith('/selection') && init?.method === 'POST')
        return Promise.resolve(jsonResponse(selectedRun));
      if (url.pathname.endsWith('/recommendations/group-b') && init?.method === 'PATCH') {
        annotationPayload = JSON.parse(init.body as string);
        const group = selectedRun.groups.find((item) => item.group_id === 'group-b')!;
        return Promise.resolve(
          jsonResponse({ ...group, note: (annotationPayload as { note: string }).note }),
        );
      }
      return Promise.reject(new Error(`Unexpected request: ${init?.method} ${url.pathname}`));
    });
    vi.stubGlobal('fetch', fetcher);
    const wrapper = mount(RecommendationsPage, { global: { plugins: [pinia] } });
    await flushPromises();

    const groupA = wrapper.get('[aria-label="Notes and rejection for group-a"]');
    await groupA.get('textarea').setValue('unsaved note A');
    await groupA.get('input').setValue('unsaved rejection A');
    await wrapper.get('input[aria-label="Select recommendation group group-b"]').setValue(true);
    await flushPromises();

    const subsetGroupA = wrapper.get('[aria-label="Notes and rejection for group-a"]');
    const subsetNote = subsetGroupA.get('textarea').element as HTMLTextAreaElement;
    const subsetRejection = subsetGroupA.get('input').element as HTMLInputElement;
    expect(subsetNote.value).toBe('unsaved note A');
    expect(subsetRejection.value).toBe('unsaved rejection A');

    const groupB = wrapper.get('[aria-label="Notes and rejection for group-b"]');
    await groupB.get('textarea').setValue('  confirmed note B  ');
    await groupB.get('button').trigger('click');
    await flushPromises();

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
    const wrapper = mount(RecommendationsPage, { global: { plugins: [pinia] } });
    await flushPromises();

    const groupA = wrapper.get('[aria-label="Notes and rejection for group-a"]');
    await groupA.get('textarea').setValue('stale unsaved note');
    await groupA.get('input').setValue('stale unsaved rejection');
    store.currentRun = null;
    await flushPromises();
    store.currentRun = nextRun;
    store.currentRunView = 'current';
    await flushPromises();

    const nextGroup = wrapper.get('[aria-label="Notes and rejection for group-a"]');
    const nextNote = nextGroup.get('textarea').element as HTMLTextAreaElement;
    expect(nextNote.value).toBe('new saved note');
    expect((nextGroup.get('input').element as HTMLInputElement).value).toBe('new saved rejection');
    wrapper.unmount();
  });
});

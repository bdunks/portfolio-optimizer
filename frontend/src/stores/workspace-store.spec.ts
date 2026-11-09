import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';
import type {
  OptimizerRecommendationsResponse,
  PolicyResponse,
  PortfolioNotSyncedResponse,
  PortfolioReadyResponse,
} from '../types/api';
import { useWorkspaceStore } from './workspace-store';

function portfolioResponse(cash: string): PortfolioNotSyncedResponse {
  return {
    status: 'not_synced',
    demo: true,
    account: null,
    as_of: null,
    cash_usd: cash,
    portfolio_total_usd: cash,
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
    allocation: { current: null, proposed: null, target: null },
    us_transition: null,
  };
}

function readyPortfolio(
  generation: number,
  activePolicyRevisionId = 'policy-demo',
): PortfolioReadyResponse {
  return {
    status: 'ready',
    demo: true,
    source: 'FakeBroker',
    account: { display_name: 'Demo account', account_type: 'BROKERAGE', tax_treatment: null },
    as_of: `2026-01-0${generation}T00:00:00Z`,
    cash_usd: '0.00',
    settled_buying_power_usd: '0.00',
    positions_market_value_usd: '0.00',
    portfolio_total_usd: '0.00',
    position_count: 0,
    positions: [],
    active_policy_revision_id: activePolicyRevisionId,
    unassigned_tickers: [],
    coverage: {},
    sync: {
      generation,
      complete: true,
      started_at: null,
      completed_at: `2026-01-0${generation}T00:00:00Z`,
      last_error_code: null,
      last_error_summary: null,
    },
    allocation: { current: null, proposed: null, target: null },
    us_transition: null,
  };
}

function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function responsePromise(value: unknown, status = 200): Promise<Response> {
  return Promise.resolve(jsonResponse(value, status));
}

function requestString(input: RequestInfo | URL): string {
  if (typeof input === 'string') return input;
  if (input instanceof URL) return input.toString();
  return input.url;
}

function requestAddress(input: RequestInfo | URL): URL {
  return new URL(requestString(input), 'http://127.0.0.1:9000');
}

function bodyJson(init?: RequestInit): unknown {
  if (typeof init?.body !== 'string') throw new Error('Expected a serialized JSON request body');
  return JSON.parse(init.body) as unknown;
}

function demoRun(runId: string, warnings: string[] = []): OptimizerRecommendationsResponse {
  return {
    run_id: runId,
    status: 'demo',
    mode: 'recommendations_only',
    policy_revision_id: 'policy-demo',
    source_generation: 1,
    as_of: '2026-01-01T00:00:00Z',
    solver_version: 'DEMO',
    demo: true,
    actionable: false,
    input_fingerprint: null,
    source_checksum: null,
    batch_settings: {},
    estimated_realized_st_usd: '0.00',
    estimated_realized_lt_usd: '0.00',
    estimated_tax_benefit_usd: null,
    estimated_tax_benefit_status: 'optimizer_unavailable',
    lots_sold_count: 0,
    positions_exited_count: 0,
    orders_count: 0,
    cash_before_usd: null,
    cash_after_usd: null,
    portfolio_effects: null,
    constraints_satisfied: null,
    no_trade_reason: null,
    warnings,
    frozen_display_context: {
      available: true,
      source: 'policy_revision',
      policy_revision_id: 'policy-demo',
      revision_number: 1,
      created_at: '2026-01-01T00:00:00Z',
      activated_at: '2026-01-01T00:00:00Z',
      sleeves: [],
      settings: { target_retained_net_loss_usd: '3000.00' },
      allowed_securities: [],
      overrides: [],
      unavailable_reason: null,
    },
    tax_profile_configured: false,
    groups: [],
    consolidated_legs: [],
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

function installDefaultApi(): ReturnType<typeof vi.fn<typeof fetch>> {
  const fetcher = vi.fn<typeof fetch>((input, init) => {
    const url = requestAddress(input);
    const method = init?.method ?? 'GET';
    if (url.pathname === '/health') {
      return responsePromise({
        status: 'ok',
        schema_ready: true,
        broker_mode: 'fake',
        live_broker_enabled: false,
        order_submission_enabled: false,
      });
    }
    if (url.pathname === '/api/v1/portfolio/sync') {
      return responsePromise({
        generation: 1,
        status: 'complete',
        as_of: '2026-01-01T00:00:00Z',
        coverage: {},
        account: 'DEMO',
        demo: true,
      });
    }
    if (url.pathname === '/api/v1/portfolio') {
      return responsePromise({
        status: 'not_synced',
        demo: true,
        account: null,
        as_of: null,
        cash_usd: '0',
        portfolio_total_usd: '0',
        positions: [],
        coverage: {},
        sync: {},
        allocation: { current: null, proposed: null, target: null },
        us_transition: null,
      });
    }
    if (url.pathname === '/api/v1/policy') {
      return responsePromise({ active: null, drafts: [], superseded: [] });
    }
    if (url.pathname === '/api/v1/lots') {
      return responsePromise({ items: [], total: 0, offset: 0, limit: 100 });
    }
    if (url.pathname === '/api/v1/wash-sales') {
      return responsePromise({
        demo: true,
        source: 'FakeBroker',
        history: [],
        acquisitions: [],
        current_restrictions: [],
        proposed_restrictions: [],
        warnings: [],
      });
    }
    if (url.pathname === '/api/v1/activity') {
      return responsePromise({ items: [], total: 0, offset: 0, limit: 100 });
    }
    if (url.pathname === '/api/v1/optimizer/runs' && method === 'POST') {
      return responsePromise(demoRun('new-run'), 201);
    }
    if (url.pathname === '/api/v1/optimizer/runs/saved') {
      return responsePromise({ run_id: 'saved' });
    }
    if (url.pathname === '/api/v1/optimizer/runs/saved/recommendations') {
      return responsePromise(demoRun('saved'));
    }
    if (url.pathname.endsWith('/selection') && method === 'POST') {
      return responsePromise(demoRun('new-run', ['selection accepted']));
    }
    return Promise.reject(new Error(`Unhandled fake route: ${method} ${url.pathname}`));
  });
  vi.stubGlobal('fetch', fetcher);
  return fetcher;
}

beforeEach(() => {
  vi.unstubAllGlobals();
  setActivePinia(createPinia());
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('workspace store', () => {
  it('deduplicates the shared initial load across route consumers', async () => {
    const fetcher = installDefaultApi();
    const store = useWorkspaceStore();

    const first = store.ensureInitialWorkspace();
    const second = store.ensureInitialWorkspace();

    expect(store.initialWorkspacePending).toBe(true);
    expect(fetcher).toHaveBeenCalledTimes(3);
    await Promise.all([first, second]);
    expect(store.initialWorkspacePending).toBe(false);
    expect(fetcher).toHaveBeenCalledTimes(3);
  });

  it('publishes a successful generation-2 portfolio and marks failed policy cache stale', async () => {
    const fetcher = vi.fn<typeof fetch>((input) => {
      const url = requestAddress(input);
      if (url.pathname === '/api/v1/portfolio/sync')
        return responsePromise({
          generation: 2,
          status: 'complete',
          as_of: '2026-01-02T00:00:00Z',
          coverage: {},
          account: 'DEMO',
          demo: true,
        });
      if (url.pathname === '/health')
        return responsePromise({
          status: 'ok',
          schema_ready: true,
          broker_mode: 'fake',
          live_broker_enabled: false,
          order_submission_enabled: false,
        });
      if (url.pathname === '/api/v1/portfolio') return responsePromise(readyPortfolio(2));
      if (url.pathname === '/api/v1/policy')
        return responsePromise(
          {
            code: 'policy_unavailable',
            message: 'Policy read failed',
            details: {},
            correlation_id: 'policy-refresh-error',
          },
          503,
        );
      if (url.pathname === '/api/v1/lots')
        return responsePromise({ items: [], total: 0, offset: 0, limit: 100 });
      if (url.pathname === '/api/v1/wash-sales')
        return responsePromise({
          demo: true,
          source: 'FakeBroker',
          history: [],
          acquisitions: [],
          current_restrictions: [],
          proposed_restrictions: [],
          warnings: [],
        });
      if (url.pathname === '/api/v1/activity')
        return responsePromise({ items: [], total: 0, offset: 0, limit: 100 });
      return Promise.reject(new Error(`Unhandled fake route: ${url.pathname}`));
    });
    vi.stubGlobal('fetch', fetcher);
    const store = useWorkspaceStore();
    const cachedPolicy = {
      active: { id: 'policy-demo' },
      drafts: [],
      superseded: [],
    } as unknown as PolicyResponse;
    store.portfolio = readyPortfolio(1);
    store.policy = cachedPolicy;

    store.currentRun = demoRun('generation-1-run');
    store.currentRunView = 'current';

    await expect(store.syncPortfolio()).resolves.toMatchObject({ generation: 2 });

    expect(store.portfolio?.status).toBe('ready');
    expect(store.portfolio?.sync.generation).toBe(2);

    expect(store.lastSync?.generation).toBe(2);
    expect(store.currentRunView).toBe('stale');
    expect(store.policy).toBe(cachedPolicy);

    expect(store.resourceFreshness.portfolio.status).toBe('fresh');
    expect(store.resourceFreshness.policy.status).toBe('stale');
    expect(store.actionState.loadPolicy.error).toMatchObject({
      code: 'policy_unavailable',
      correlationId: 'policy-refresh-error',
    });
  });

  it('refreshes resources independently and exposes per-action status', async () => {
    const fetcher = installDefaultApi();
    const store = useWorkspaceStore();

    await store.refreshWorkspace();

    expect(store.portfolio?.status).toBe('not_synced');
    expect(store.policy).toEqual({ active: null, drafts: [], superseded: [] });
    expect(store.lots?.items).toEqual([]);
    expect(store.washSales?.source).toBe('FakeBroker');
    expect(store.activity?.total).toBe(0);
    expect(fetcher).toHaveBeenCalledTimes(6);
    expect(store.actionState.refreshWorkspace.pending).toBe(false);
    expect(store.actionState.refreshWorkspace.error).toBeNull();
  });

  it('does not let an older refresh overwrite newer portfolio or filtered lot loads', async () => {
    const stalePortfolio = deferred<Response>();
    const staleLots = deferred<Response>();
    let portfolioCalls = 0;
    const fetcher = vi.fn<typeof fetch>((input) => {
      const url = requestAddress(input);
      if (url.pathname === '/health')
        return responsePromise({
          status: 'ok',
          schema_ready: true,
          broker_mode: 'fake',
          live_broker_enabled: false,
          order_submission_enabled: false,
        });
      if (url.pathname === '/api/v1/portfolio') {
        portfolioCalls += 1;
        return portfolioCalls === 1
          ? stalePortfolio.promise
          : responsePromise(portfolioResponse('250.00'));
      }
      if (url.pathname === '/api/v1/policy')
        return responsePromise({ active: null, drafts: [], superseded: [] });
      if (url.pathname === '/api/v1/lots') {
        if (url.searchParams.get('ticker') === 'NEW')
          return responsePromise({ items: [], total: 1, offset: 0, limit: 100 });
        return staleLots.promise;
      }
      if (url.pathname === '/api/v1/wash-sales')
        return responsePromise({
          demo: true,
          source: 'FakeBroker',
          history: [],
          acquisitions: [],
          current_restrictions: [],
          proposed_restrictions: [],
          warnings: [],
        });
      if (url.pathname === '/api/v1/activity')
        return responsePromise({ items: [], total: 0, offset: 0, limit: 100 });
      return Promise.reject(new Error(`Unhandled fake route: ${url.pathname}`));
    });
    vi.stubGlobal('fetch', fetcher);
    const store = useWorkspaceStore();

    const oldRefresh = store.refreshWorkspace();
    const newerPortfolio = store.loadPortfolio();
    const newerLots = store.loadLots({ ticker: 'NEW' });
    await Promise.all([newerPortfolio, newerLots]);

    stalePortfolio.resolve(jsonResponse(portfolioResponse('0.00')));
    staleLots.resolve(jsonResponse({ items: [], total: 0, offset: 0, limit: 100 }));
    await oldRefresh;

    expect(store.portfolio?.status).toBe('not_synced');
    expect(store.portfolio?.cash_usd).toBe('250.00');
    expect(store.lotFilters).toEqual({ ticker: 'NEW' });
    expect(store.lots?.total).toBe(1);
    expect(fetcher).toHaveBeenCalledTimes(8);
  });

  it('synchronizes and reloads without auto-running the optimizer', async () => {
    const fetcher = installDefaultApi();
    const store = useWorkspaceStore();

    await store.syncPortfolio();

    expect(store.lastSync?.demo).toBe(true);
    expect(store.portfolio?.status).toBe('not_synced');
    expect(
      fetcher.mock.calls.some(([input]) => requestString(input) === '/api/v1/optimizer/runs'),
    ).toBe(false);
    expect(
      fetcher.mock.calls.some(([input]) => requestString(input) === '/api/v1/portfolio/sync'),
    ).toBe(true);
  });

  it('uses backend selection responses and preserves the previous run on errors', async () => {
    let rejectSelection = false;
    const fetcher = vi.fn<typeof fetch>((input, init) => {
      const url = requestAddress(input);
      if (url.pathname === '/api/v1/optimizer/runs' && init?.method === 'POST') {
        return responsePromise(demoRun('run-1'), 201);
      }
      if (url.pathname.endsWith('/selection')) {
        if (rejectSelection) {
          return responsePromise(
            {
              code: 'invalid_selection',
              message: 'The selected subset is infeasible',
              details: { group_id: 'group-1' },
              correlation_id: 'selection-error',
            },
            422,
          );
        }
        return responsePromise(demoRun('run-1', ['server-authoritative result']));
      }
      return Promise.reject(new Error(`Unhandled fake route: ${url.pathname}`));
    });
    vi.stubGlobal('fetch', fetcher);
    const store = useWorkspaceStore();
    await store.runOptimizer();
    const original = store.currentRun;
    const selected = {
      selected_group_ids: ['group/1'],
      selected_sell_lots: { 'group/1': ['lot #42'] },
    };

    const recalculated = await store.recalculateSelection(selected);
    expect(bodyJson(fetcher.mock.calls[1]?.[1])).toEqual(selected);
    expect(store.currentRun).toEqual(recalculated);
    expect(store.currentRun?.warnings).toEqual(['server-authoritative result']);

    rejectSelection = true;
    const lastValidRun = store.currentRun;
    await expect(store.recalculateSelection({ selected_group_ids: [] })).rejects.toMatchObject({
      code: 'invalid_selection',
      correlationId: 'selection-error',
    });
    expect(store.currentRun).toBe(lastValidRun);
    expect(store.currentRun).not.toBe(original);
    expect(store.actionState.recalculateSelection.error?.code).toBe('invalid_selection');
  });

  it('replaces annotated runs and matching summaries atomically after validating run IDs', async () => {
    const initial = {
      ...demoRun('annotated-run'),
      orders_count: 2,
      groups: [
        {
          group_id: 'group-1',
          selected: true,
          rejected: false,
          note: 'keep this note',
          rejection_reason: null,
        },
      ],
      consolidated_legs: [{ leg_id: 'sell-1', selected: true }],
    } as unknown as OptimizerRecommendationsResponse;
    const updated = {
      ...initial,
      warnings: ['full response after rejection'],
      orders_count: 0,
      groups: [
        {
          group_id: 'group-1',
          selected: false,
          rejected: true,
          note: 'keep this note',
          rejection_reason: 'not suitable',
        },
      ],
      consolidated_legs: [],
    } as unknown as OptimizerRecommendationsResponse;
    let response = updated;
    const fetcher = vi.fn<typeof fetch>((input, init) => {
      const url = requestAddress(input);
      if (url.pathname.endsWith('/recommendations/group-1') && init?.method === 'PATCH')
        return responsePromise(response);
      return Promise.reject(new Error(`Unhandled fake route: ${init?.method} ${url.pathname}`));
    });
    vi.stubGlobal('fetch', fetcher);
    const store = useWorkspaceStore();
    store.currentRun = initial;
    store.currentRunView = 'current';
    store.currentRunSummary = { ...demoRun('annotated-run'), orders_count: 2 };

    const result = await store.annotateGroup('annotated-run', 'group-1', {
      rejected: true,
      rejection_reason: 'not suitable',
    });
    expect(result).toEqual(updated);
    expect(store.currentRun).toEqual(updated);
    expect(store.currentRun?.groups[0]).toMatchObject({ selected: false, rejected: true });
    expect(store.currentRunSummary).toMatchObject({
      run_id: 'annotated-run',
      orders_count: 0,
      warnings: ['full response after rejection'],
    });

    const successfulRun = store.currentRun;
    const successfulSummary = store.currentRunSummary;
    response = { ...updated, run_id: 'different-run' };
    await expect(
      store.annotateGroup('annotated-run', 'group-1', { note: null }),
    ).rejects.toMatchObject({ code: 'run_id_mismatch' });
    expect(store.currentRun).toBe(successfulRun);
    expect(store.currentRunSummary).toBe(successfulSummary);
  });

  it('serializes annotations and selection so authoritative group updates are not overwritten', async () => {
    const group = (groupId: string) => ({
      group_id: groupId,
      selected: false,
      rejected: false,
      note: null,
      rejection_reason: null,
    });
    const initial = {
      ...demoRun('ordered-run'),
      groups: [group('group-1'), group('group-2')],
    } as unknown as OptimizerRecommendationsResponse;
    const firstAnnotationResponse = deferred<Response>();
    const requestOrder: string[] = [];
    let serverRun = initial;
    const patchGroup = (
      run: OptimizerRecommendationsResponse,
      groupId: string,
      patch: Record<string, unknown>,
    ) =>
      ({
        ...run,
        groups: run.groups.map((item) =>
          item.group_id === groupId ? { ...item, ...patch } : item,
        ),
      }) as OptimizerRecommendationsResponse;
    const fetcher = vi.fn<typeof fetch>((input, init) => {
      const url = requestAddress(input);
      if (url.pathname.endsWith('/recommendations/group-1') && init?.method === 'PATCH') {
        requestOrder.push('PATCH group-1');
        serverRun = patchGroup(serverRun, 'group-1', { note: 'confirmed one' });
        return firstAnnotationResponse.promise;
      }
      if (url.pathname.endsWith('/recommendations/group-2') && init?.method === 'PATCH') {
        requestOrder.push('PATCH group-2');
        serverRun = patchGroup(serverRun, 'group-2', { note: 'confirmed two' });
        return responsePromise(serverRun);
      }
      if (url.pathname.endsWith('/selection') && init?.method === 'POST') {
        requestOrder.push('POST selection');
        return responsePromise(serverRun);
      }
      return Promise.reject(new Error(`Unhandled fake route: ${init?.method} ${url.pathname}`));
    });
    vi.stubGlobal('fetch', fetcher);
    const store = useWorkspaceStore();
    store.currentRun = initial;
    store.currentRunView = 'current';

    const firstAnnotation = store.annotateGroup('ordered-run', 'group-1', {
      note: 'confirmed one',
    });
    const secondAnnotation = store.annotateGroup('ordered-run', 'group-2', {
      note: 'confirmed two',
    });
    const selection = store.recalculateSelection({ selected_group_ids: ['group-2'] });
    expect(store.reviewMutationPending).toBe(true);
    await Promise.resolve();
    expect(requestOrder).toEqual(['PATCH group-1']);

    firstAnnotationResponse.resolve(jsonResponse(serverRun));
    await firstAnnotation;
    await Promise.all([secondAnnotation, selection]);

    expect(requestOrder).toEqual(['PATCH group-1', 'PATCH group-2', 'POST selection']);
    expect(store.currentRun?.groups.map((item) => item.note)).toEqual([
      'confirmed one',
      'confirmed two',
    ]);
    expect(store.reviewMutationPending).toBe(false);
  });

  it('ignores late older run and selection completions after a newer view opens', async () => {
    const firstRunResponse = deferred<Response>();
    const oldSelectionResponse = deferred<Response>();
    let runCalls = 0;
    const fetcher = vi.fn<typeof fetch>((input, init) => {
      const url = requestAddress(input);
      if (url.pathname === '/api/v1/optimizer/runs' && init?.method === 'POST') {
        runCalls += 1;
        if (runCalls === 1) return firstRunResponse.promise;
        return responsePromise(demoRun('new-run'), 201);
      }
      if (url.pathname.endsWith('/selection')) return oldSelectionResponse.promise;
      if (url.pathname === '/api/v1/optimizer/runs/saved') {
        return responsePromise({ run_id: 'saved' });
      }
      if (url.pathname === '/api/v1/optimizer/runs/saved/recommendations') {
        return responsePromise(demoRun('saved'));
      }
      return Promise.reject(new Error(`Unhandled fake route: ${url.pathname}`));
    });
    vi.stubGlobal('fetch', fetcher);
    const store = useWorkspaceStore();

    const olderRun = store.runOptimizer();
    await store.runOptimizer();
    firstRunResponse.resolve(jsonResponse(demoRun('old-run'), 201));
    await olderRun;
    expect(store.currentRun?.run_id).toBe('new-run');

    const oldSelection = store.recalculateSelection({ selected_group_ids: ['old'] });
    await Promise.resolve();
    expect(
      fetcher.mock.calls.some(([input]) => requestAddress(input).pathname.endsWith('/selection')),
    ).toBe(true);
    await store.openSavedRun('saved');
    oldSelectionResponse.resolve(jsonResponse(demoRun('new-run', ['late selection'])));
    await expect(oldSelection).rejects.toMatchObject({ code: 'run_context_changed' });

    expect(store.currentRun?.run_id).toBe('saved');
    expect(store.currentRunView).toBe('saved');

    expect(store.reviewMutationPending).toBe(false);
  });

  it('invalidates a current comparison when the active policy revision changes', async () => {
    const fetcher = vi.fn<typeof fetch>((input, init) => {
      const url = requestAddress(input);
      if (url.pathname === '/api/v1/policy/policy-new/activate' && init?.method === 'POST')
        return responsePromise({ id: 'policy-new', status: 'ACTIVE' });
      if (url.pathname === '/health')
        return responsePromise({
          status: 'ok',
          schema_ready: true,
          broker_mode: 'fake',
          live_broker_enabled: false,
          order_submission_enabled: false,
        });
      if (url.pathname === '/api/v1/portfolio')
        return responsePromise(readyPortfolio(1, 'policy-new'));
      if (url.pathname === '/api/v1/policy')
        return responsePromise({
          active: { id: 'policy-new', status: 'ACTIVE', activation_errors: [] },
          drafts: [],
          superseded: [],
        });
      if (url.pathname === '/api/v1/lots')
        return responsePromise({ items: [], total: 0, offset: 0, limit: 100 });
      if (url.pathname === '/api/v1/wash-sales')
        return responsePromise({
          demo: true,
          source: 'FakeBroker',
          history: [],
          acquisitions: [],
          current_restrictions: [],
          proposed_restrictions: [],
          warnings: [],
        });
      if (url.pathname === '/api/v1/activity')
        return responsePromise({ items: [], total: 0, offset: 0, limit: 100 });
      return Promise.reject(new Error(`Unhandled fake route: ${init?.method} ${url.pathname}`));
    });
    vi.stubGlobal('fetch', fetcher);
    const store = useWorkspaceStore();
    store.policy = {
      active: { id: 'policy-demo', status: 'ACTIVE' },
      drafts: [],
      superseded: [],
    } as unknown as PolicyResponse;
    store.currentRun = demoRun('active-policy-run');
    store.currentRunView = 'current';

    await store.activatePolicy('policy-new');

    expect(store.policy?.active?.id).toBe('policy-new');
    expect(store.currentRunView).toBe('stale');
    expect(store.proposedRunIsStale).toBe(true);
  });
  it('only invalidates a comparison when a sync changes its source generation', async () => {
    let generation = 1;
    const fetcher = vi.fn<typeof fetch>((input, init) => {
      const url = requestAddress(input);
      if (url.pathname === '/api/v1/portfolio/sync')
        return responsePromise({
          generation,
          status: 'complete',
          as_of: `2026-01-0${generation}T00:00:00Z`,
          coverage: {},
          account: 'DEMO',
          demo: true,
        });
      if (url.pathname === '/health')
        return responsePromise({
          status: 'ok',
          schema_ready: true,
          broker_mode: 'fake',
          live_broker_enabled: false,
          order_submission_enabled: false,
        });
      if (url.pathname === '/api/v1/portfolio') return responsePromise(readyPortfolio(generation));
      if (url.pathname === '/api/v1/policy')
        return responsePromise({ active: { id: 'policy-demo' }, drafts: [], superseded: [] });
      if (url.pathname === '/api/v1/lots')
        return responsePromise({ items: [], total: 0, offset: 0, limit: 100 });
      if (url.pathname === '/api/v1/wash-sales')
        return responsePromise({
          demo: true,
          source: 'FakeBroker',
          history: [],
          acquisitions: [],
          current_restrictions: [],
          proposed_restrictions: [],
          warnings: [],
        });
      if (url.pathname === '/api/v1/activity')
        return responsePromise({ items: [], total: 0, offset: 0, limit: 100 });
      return Promise.reject(new Error(`Unhandled fake route: ${init?.method} ${url.pathname}`));
    });
    vi.stubGlobal('fetch', fetcher);
    const store = useWorkspaceStore();
    store.currentRun = demoRun('source-run');
    store.currentRunView = 'current';

    await store.syncPortfolio();
    expect(store.currentRunView).toBe('current');
    generation = 2;
    await store.syncPortfolio();

    expect(store.lastSync?.generation).toBe(2);
    expect(store.currentRunView).toBe('stale');
  });

  it('distinguishes an unknown active policy from a confirmed absence of an active revision', async () => {
    const fetcher = vi.fn<typeof fetch>((input, init) => {
      const url = requestAddress(input);
      if (url.pathname === '/api/v1/optimizer/runs' && init?.method === 'POST')
        return responsePromise(demoRun('run-without-active-policy'), 201);
      return Promise.reject(new Error(`Unhandled fake route: ${init?.method} ${url.pathname}`));
    });
    vi.stubGlobal('fetch', fetcher);
    const store = useWorkspaceStore();

    store.observeActivePolicyRevision(null);
    await store.runOptimizer();

    expect(store.currentRun?.run_id).toBe('run-without-active-policy');
    expect(store.currentRunView).toBe('stale');
  });

  it('keeps a run current when saving an inactive policy draft leaves the active revision unchanged', async () => {
    const fetcher = installDefaultApi();
    const activePolicy = { id: 'policy-demo', status: 'ACTIVE' };
    fetcher.mockImplementation((input, init) => {
      const url = requestAddress(input);
      if (url.pathname === '/api/v1/optimizer/runs' && init?.method === 'POST') {
        return responsePromise(demoRun('policy-run'), 201);
      }
      if (url.pathname === '/api/v1/policy/drafts' && init?.method === 'POST') {
        return responsePromise({ id: 'draft-2', status: 'DRAFT' }, 201);
      }
      if (url.pathname === '/api/v1/policy') {
        return responsePromise({
          active: activePolicy,
          drafts: [{ id: 'draft-2' }],
          superseded: [],
        });
      }
      return responsePromise({});
    });
    const store = useWorkspaceStore();
    store.policy = {
      active: activePolicy,
      drafts: [],
      superseded: [],
    } as unknown as PolicyResponse;
    await store.runOptimizer();

    await store.savePolicyDraft({ settings: {}, sleeves: [] });

    expect(store.policy?.active?.id).toBe('policy-demo');
    expect(store.currentRunView).toBe('current');
    expect(store.proposedRunIsStale).toBe(false);
    expect(store.currentRun?.run_id).toBe('policy-run');
  });
});

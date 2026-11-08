import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';
import type { OptimizerRecommendationsResponse, PortfolioNotSyncedResponse } from '../types/api';
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
  it('loads workspace data atomically and exposes per-action status', async () => {
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
    await store.openSavedRun('saved');
    oldSelectionResponse.resolve(jsonResponse(demoRun('new-run', ['late selection'])));
    await oldSelection;

    expect(store.currentRun?.run_id).toBe('saved');
    expect(store.currentRunView).toBe('saved');
  });

  it('marks proposed comparisons stale after policy changes', async () => {
    const fetcher = installDefaultApi();
    fetcher.mockImplementation((input, init) => {
      const url = requestAddress(input);
      if (url.pathname === '/api/v1/optimizer/runs' && init?.method === 'POST') {
        return responsePromise(demoRun('policy-run'), 201);
      }
      if (url.pathname === '/api/v1/policy/drafts' && init?.method === 'POST') {
        return responsePromise({ id: 'draft-2' }, 201);
      }
      if (url.pathname === '/api/v1/policy') {
        return responsePromise({ active: null, drafts: [{ id: 'draft-2' }], superseded: [] });
      }
      return responsePromise({});
    });
    const store = useWorkspaceStore();
    await store.runOptimizer();
    await store.savePolicyDraft({ settings: {}, sleeves: [] });

    expect(store.currentRunView).toBe('stale');
    expect(store.proposedRunIsStale).toBe(true);
    expect(store.currentRun?.run_id).toBe('policy-run');
  });
});

import { flushPromises } from '@vue/test-utils';
import { onlineManager } from '@tanstack/query-core';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';
import type {
  OptimizerRecommendationsResponse,
  PolicyResponse,
  PortfolioNotSyncedResponse,
  PortfolioReadyResponse,
} from '../types/api';
import { workspaceQueryKeys } from '../composables/queries/workspace-queries';
import { useWorkspaceStore } from './workspace-store';
import {
  mountWorkspaceHarness,
  seedCurrentRunForTest,
  seedCurrentRunSummaryForTest,
  currentRunForTest,
  currentRunSummaryForTest,
} from '../test-utils/workspace-harness';

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

function runWithSelectedSellLots(
  run: OptimizerRecommendationsResponse,
  brokerLotIds: string[],
  rejected = false,
): OptimizerRecommendationsResponse {
  return {
    ...run,
    groups: [
      {
        group_id: 'group-1',
        selected: brokerLotIds.length > 0,
        rejected,
      },
    ],
    consolidated_legs:
      brokerLotIds.length === 0
        ? []
        : [
            {
              side: 'SELL',
              selected_lots: brokerLotIds.map((broker_lot_id) => ({
                broker_lot_id,
                selected: true,
              })),
            },
          ],
  } as unknown as OptimizerRecommendationsResponse;
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
      return responsePromise({ items: [], total: 0, offset: 0, limit: 100, source_generation: 1 });
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
  it('owns run payloads in the Query cache instead of Pinia state', async () => {
    const { workspace, queryClient } = mountWorkspaceHarness();
    const run = demoRun('query-owned-run');

    seedCurrentRunForTest(workspace, run);
    await flushPromises();

    expect(workspace.currentRun).toEqual(run);
    expect(queryClient.getQueryData(workspaceQueryKeys.currentRun(run.run_id))).toEqual(run);
    expect('currentRun' in useWorkspaceStore()).toBe(false);
  });

  it('keeps the serialized review queue and accepted run across facade remounts', async () => {
    const firstResponse = deferred<Response>();
    const runId = 'shared-review-run';
    const initial = {
      ...demoRun(runId),
      groups: ['group-1', 'group-2'].map((group_id) => ({
        group_id,
        selected: true,
        rejected: false,
        note: null,
        rejection_reason: null,
      })),
    } as unknown as OptimizerRecommendationsResponse;
    const firstResult = { ...initial, warnings: ['first accepted'] };
    const secondResult = { ...initial, warnings: ['second accepted'] };
    const requestOrder: string[] = [];
    const fetcher = vi.fn<typeof fetch>((input) => {
      const url = requestAddress(input);
      if (url.pathname.endsWith('/recommendations/group-1')) {
        requestOrder.push('group-1');
        return firstResponse.promise;
      }
      if (url.pathname.endsWith('/recommendations/group-2')) {
        requestOrder.push('group-2');
        return responsePromise(secondResult);
      }
      return Promise.reject(new Error(`Unhandled fake route: ${url.pathname}`));
    });
    vi.stubGlobal('fetch', fetcher);

    const firstHarness = mountWorkspaceHarness();
    const firstFacade = firstHarness.workspace;
    seedCurrentRunForTest(firstFacade, initial);
    firstFacade.currentRunView = 'current';
    firstFacade.observeSourceGeneration(1);

    const firstWrite = firstFacade.annotateGroup(runId, 'group-1', { note: 'first' });
    await flushPromises();
    expect(requestOrder).toEqual(['group-1']);
    firstHarness.wrapper.unmount();

    const secondHarness = mountWorkspaceHarness();
    const secondFacade = secondHarness.workspace;
    expect(secondHarness.queryClient).toBe(firstHarness.queryClient);
    expect(secondFacade.reviewMutationPending).toBe(true);
    const secondWrite = secondFacade.annotateGroup(runId, 'group-2', { note: 'second' });
    await flushPromises();
    expect(requestOrder).toEqual(['group-1']);

    firstResponse.resolve(jsonResponse(firstResult));
    await firstWrite;
    await vi.waitFor(() => expect(requestOrder).toEqual(['group-1', 'group-2']));
    await secondWrite;

    expect(currentRunForTest(secondFacade)).toEqual(secondResult);
    expect(secondHarness.queryClient.getQueryData(workspaceQueryKeys.currentRun(runId))).toEqual(
      secondResult,
    );
    expect(secondFacade.reviewMutationPending).toBe(false);
    expect('currentRun' in useWorkspaceStore()).toBe(false);
  });

  it('loads saved summary and recommendations into the Query cache and keeps them read-only', async () => {
    const runId = 'saved-query-run';
    const summary = { ...demoRun(runId), orders_count: 4 };
    const recommendations = demoRun(runId);
    const fetcher = vi.fn<typeof fetch>((input, init) => {
      const url = requestAddress(input);
      if (url.pathname === `/api/v1/optimizer/runs/${runId}` && init?.method === 'GET')
        return responsePromise(summary);
      if (
        url.pathname === `/api/v1/optimizer/runs/${runId}/recommendations` &&
        init?.method === 'GET'
      )
        return responsePromise(recommendations);
      return Promise.reject(new Error(`Unhandled fake route: ${init?.method} ${url.pathname}`));
    });
    vi.stubGlobal('fetch', fetcher);
    const { workspace, queryClient } = mountWorkspaceHarness();

    await workspace.openSavedRun(runId);

    expect(workspace.currentRunView).toBe('saved');
    expect(queryClient.getQueryData(workspaceQueryKeys.currentRun(runId))).toEqual(recommendations);
    expect(queryClient.getQueryData(workspaceQueryKeys.currentRunSummary(runId))).toEqual(summary);
    await expect(
      workspace.annotateGroup(runId, 'group-1', { note: 'not allowed' }),
    ).rejects.toMatchObject({
      code: 'run_context_changed',
    });
    expect(fetcher).toHaveBeenCalledTimes(2);
    expect('currentRun' in useWorkspaceStore()).toBe(false);
    expect('currentRunSummary' in useWorkspaceStore()).toBe(false);
  });

  it('runs review mutations offline and rejects changed-context responses', async () => {
    const runId = 'offline-review-run';
    const initial = {
      ...demoRun(runId),
      groups: [
        {
          group_id: 'group-1',
          selected: true,
          rejected: false,
          note: null,
          rejection_reason: null,
        },
      ],
    } as unknown as OptimizerRecommendationsResponse;
    const staleResponse = deferred<Response>();
    const fetcher = vi.fn<typeof fetch>((input, init) => {
      const url = requestAddress(input);
      if (url.pathname.endsWith('/recommendations/group-1')) {
        return staleResponse.promise;
      }
      if (url.pathname === '/api/v1/optimizer/runs' && init?.method === 'POST') {
        return responsePromise(demoRun('offline-replacement-run'), 201);
      }
      return Promise.reject(new Error(`Unhandled fake route: ${init?.method} ${url.pathname}`));
    });
    vi.stubGlobal('fetch', fetcher);

    const { workspace } = mountWorkspaceHarness();
    seedCurrentRunForTest(workspace, initial);
    workspace.currentRunView = 'current';
    workspace.observeSourceGeneration(1);

    const wasOnline = onlineManager.isOnline();
    let annotationPromise: Promise<OptimizerRecommendationsResponse> | null = null;
    onlineManager.setOnline(false);
    try {
      annotationPromise = workspace.annotateGroup(runId, 'group-1', { note: 'offline request' });
      await vi.waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1));
      expect(workspace.reviewMutationPending).toBe(true);

      await workspace.runOptimizer();
      expect(currentRunForTest(workspace)?.run_id).toBe('offline-replacement-run');
      expect(workspace.reviewMutationPending).toBe(true);

      staleResponse.resolve(jsonResponse(initial));
      await expect(annotationPromise).rejects.toMatchObject({ code: 'run_context_changed' });
      expect(currentRunForTest(workspace)?.run_id).toBe('offline-replacement-run');
      expect(workspace.reviewMutationPending).toBe(false);
    } finally {
      onlineManager.setOnline(wasOnline);
      staleResponse.resolve(jsonResponse(initial));
      await annotationPromise?.catch(() => undefined);
    }
  });

  it('retains run and summary caches when saved loading completes unmounted', async () => {
    const runId = 'saved-after-unmount';
    const summary = { ...demoRun(runId), orders_count: 3 };
    const recommendations = demoRun(runId);
    const recommendationsResponse = deferred<Response>();
    const fetcher = vi.fn<typeof fetch>((input, init) => {
      const url = requestAddress(input);
      if (url.pathname === `/api/v1/optimizer/runs/${runId}` && init?.method === 'GET') {
        return responsePromise(summary);
      }
      if (
        url.pathname === `/api/v1/optimizer/runs/${runId}/recommendations` &&
        init?.method === 'GET'
      ) {
        return recommendationsResponse.promise;
      }
      return Promise.reject(new Error(`Unhandled fake route: ${init?.method} ${url.pathname}`));
    });
    vi.stubGlobal('fetch', fetcher);

    const firstHarness = mountWorkspaceHarness();
    const { workspace, queryClient } = firstHarness;
    const originalDefaults = queryClient.getDefaultOptions();
    queryClient.setDefaultOptions({
      ...originalDefaults,
      queries: { ...originalDefaults.queries, gcTime: 1 },
    });
    let opening: Promise<OptimizerRecommendationsResponse> | null = null;
    try {
      opening = workspace.openSavedRun(runId);
      await vi.waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2));
      firstHarness.wrapper.unmount();

      recommendationsResponse.resolve(jsonResponse(recommendations));
      await opening;
      await new Promise((resolve) => setTimeout(resolve, 25));

      expect(queryClient.getQueryData(workspaceQueryKeys.currentRun(runId))).toEqual(
        recommendations,
      );
      expect(queryClient.getQueryData(workspaceQueryKeys.currentRunSummary(runId))).toEqual(
        summary,
      );

      const { workspace: remounted } = mountWorkspaceHarness();
      await flushPromises();
      expect(remounted.currentRun?.run_id).toBe(runId);
      expect(remounted.currentRunSummary?.run_id).toBe(runId);
      expect(remounted.currentRunView).toBe('saved');
    } finally {
      recommendationsResponse.resolve(jsonResponse(recommendations));
      await opening?.catch(() => undefined);
      queryClient.setDefaultOptions(originalDefaults);
    }
  });

  it('deduplicates the shared initial load across route consumers', async () => {
    const fetcher = installDefaultApi();
    const { workspace: store } = mountWorkspaceHarness();

    const first = store.ensureInitialWorkspace();
    const second = store.ensureInitialWorkspace();

    expect(store.initialWorkspacePending).toBe(true);
    await Promise.all([first, second]);
    expect(store.initialWorkspacePending).toBe(false);
    expect(fetcher).toHaveBeenCalledTimes(3);
  });

  it('publishes generation-2 portfolio and stales failed policy cache', async () => {
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
        return responsePromise({
          items: [],
          total: 0,
          offset: 0,
          limit: 100,
          source_generation: 1,
        });
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
    const { workspace: store, queryClient } = mountWorkspaceHarness();
    const cachedPolicy = {
      active: { id: 'policy-demo' },
      drafts: [],
      superseded: [],
    } as unknown as PolicyResponse;
    queryClient.setQueryData(workspaceQueryKeys.portfolio, readyPortfolio(1));
    queryClient.setQueryData(workspaceQueryKeys.policy, cachedPolicy);

    seedCurrentRunForTest(store, demoRun('generation-1-run'));
    store.currentRunView = 'current';

    await expect(store.syncPortfolio()).resolves.toMatchObject({ generation: 2 });

    expect(store.portfolio?.status).toBe('ready');
    expect(store.portfolio?.sync.generation).toBe(2);

    expect(store.lastSync?.generation).toBe(2);
    expect(store.currentRunView).toBe('stale');
    expect(store.policy).toEqual(cachedPolicy);

    expect(store.resourceFreshness.portfolio.status).toBe('fresh');
    expect(store.resourceFreshness.policy.status).toBe('stale');
    expect(store.actionState.loadPolicy.error).toMatchObject({
      code: 'policy_unavailable',
      correlationId: 'policy-refresh-error',
    });
  });

  it('shares portfolio sync ordering across workspace facades', async () => {
    const staleSync = deferred<Response>();
    const latestSync = deferred<Response>();
    let syncCalls = 0;
    const fetcher = vi.fn<typeof fetch>((input) => {
      const url = requestAddress(input);
      if (url.pathname === '/api/v1/portfolio/sync') {
        syncCalls += 1;
        return syncCalls === 1 ? staleSync.promise : latestSync.promise;
      }
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
        return responsePromise({ active: null, drafts: [], superseded: [] });
      if (url.pathname === '/api/v1/lots')
        return responsePromise({
          items: [],
          total: 0,
          offset: 0,
          limit: 100,
          source_generation: 2,
        });
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

    const firstFacade = mountWorkspaceHarness().workspace;
    const secondFacade = mountWorkspaceHarness().workspace;
    const oldRequest = firstFacade.syncPortfolio();
    const newRequest = secondFacade.syncPortfolio();
    await vi.waitFor(() => expect(syncCalls).toBe(2));

    latestSync.resolve(
      jsonResponse({
        generation: 2,
        status: 'complete',
        as_of: '2026-01-02T00:00:00Z',
        coverage: {},
        account: 'DEMO',
        demo: true,
      }),
    );
    await newRequest;
    expect(firstFacade.lastSync?.generation).toBe(2);
    const refreshCalls = () =>
      fetcher.mock.calls.filter(
        ([input]) => requestAddress(input).pathname !== '/api/v1/portfolio/sync',
      );
    expect(refreshCalls()).toHaveLength(6);

    staleSync.resolve(
      jsonResponse({
        generation: 1,
        status: 'complete',
        as_of: '2026-01-01T00:00:00Z',
        coverage: {},
        account: 'DEMO',
        demo: true,
      }),
    );
    await oldRequest;
    expect(firstFacade.lastSync?.generation).toBe(2);
    expect(refreshCalls()).toHaveLength(6);
  });

  it('refreshes resources independently and exposes per-action status', async () => {
    const fetcher = installDefaultApi();
    const { workspace: store } = mountWorkspaceHarness();

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
          return responsePromise({
            items: [],
            total: 1,
            offset: 0,
            limit: 100,
            source_generation: 1,
          });
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
    const { workspace: store } = mountWorkspaceHarness();

    const oldRefresh = store.refreshWorkspace();
    await vi.waitFor(() => expect(fetcher).toHaveBeenCalledTimes(6));
    const newerPortfolio = store.loadPortfolio();
    const newerLots = store.loadLots({ ticker: 'NEW' });
    await Promise.all([newerPortfolio, newerLots]);

    stalePortfolio.resolve(jsonResponse(portfolioResponse('0.00')));
    staleLots.resolve(
      jsonResponse({
        items: [],
        total: 0,
        offset: 0,
        limit: 100,
        source_generation: 1,
      }),
    );
    await oldRefresh;

    expect(store.portfolio?.status).toBe('not_synced');
    expect(store.portfolio?.cash_usd).toBe('250.00');
    expect(store.lotFilters).toEqual({ ticker: 'NEW' });
    expect(store.lots?.total).toBe(1);
    expect(fetcher).toHaveBeenCalledTimes(8);
  });

  it('returns each uncached overlapping load result while only publishing the latest response', async () => {
    const olderResponse = deferred<Response>();
    const newerResponse = deferred<Response>();
    let portfolioCalls = 0;
    const fetcher = vi.fn<typeof fetch>((input) => {
      if (requestAddress(input).pathname !== '/api/v1/portfolio')
        return Promise.reject(new Error(`Unhandled fake route: ${requestAddress(input).pathname}`));
      portfolioCalls += 1;
      return portfolioCalls === 1 ? olderResponse.promise : newerResponse.promise;
    });
    vi.stubGlobal('fetch', fetcher);
    const { workspace: store, queryClient } = mountWorkspaceHarness();
    const { workspace: newerFacade } = mountWorkspaceHarness();

    const olderLoad = store.loadPortfolio();
    const newerLoad = newerFacade.loadPortfolio();
    await vi.waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2));
    expect(store.actionState.loadPortfolio.pendingCount).toBe(2);
    expect(queryClient.getQueryData(workspaceQueryKeys.portfolio)).toBeUndefined();

    newerResponse.resolve(jsonResponse(readyPortfolio(2)));
    await expect(newerLoad).resolves.toMatchObject({ sync: { generation: 2 } });
    expect(store.actionState.loadPortfolio.pendingCount).toBe(1);
    expect(store.observedSourceGeneration).toBe(2);

    olderResponse.resolve(jsonResponse(readyPortfolio(1)));
    await expect(olderLoad).resolves.toMatchObject({ sync: { generation: 1 } });
    expect(store.actionState.loadPortfolio.pendingCount).toBe(0);
    expect(store.portfolio?.sync.generation).toBe(2);
    expect(store.observedSourceGeneration).toBe(2);
  });

  it('returns an older cached-resource failure and keeps latest resource state authoritative', async () => {
    const olderResponse = deferred<Response>();
    const newerResponse = deferred<Response>();
    let portfolioCalls = 0;
    const fetcher = vi.fn<typeof fetch>((input) => {
      if (requestAddress(input).pathname !== '/api/v1/portfolio')
        return Promise.reject(new Error(`Unhandled fake route: ${requestAddress(input).pathname}`));
      portfolioCalls += 1;
      return portfolioCalls === 1 ? olderResponse.promise : newerResponse.promise;
    });
    vi.stubGlobal('fetch', fetcher);
    const { workspace: store, queryClient } = mountWorkspaceHarness();
    queryClient.setQueryData(workspaceQueryKeys.portfolio, readyPortfolio(1));

    const olderLoad = store.loadPortfolio();
    const newerLoad = store.loadPortfolio();
    await vi.waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2));
    expect(store.actionState.loadPortfolio.pendingCount).toBe(2);

    newerResponse.resolve(jsonResponse(readyPortfolio(2)));
    await newerLoad;
    expect(store.actionState.loadPortfolio.pendingCount).toBe(1);
    expect(store.resourceFreshness.portfolio.status).toBe('fresh');

    olderResponse.resolve(
      jsonResponse(
        {
          code: 'portfolio_unavailable',
          message: 'The older portfolio read failed',
          details: {},
          correlation_id: 'older-portfolio-failure',
        },
        503,
      ),
    );
    await expect(olderLoad).rejects.toMatchObject({
      code: 'portfolio_unavailable',
      correlationId: 'older-portfolio-failure',
    });
    expect(store.actionState.loadPortfolio.pendingCount).toBe(0);
    expect(store.actionState.loadPortfolio.error).toBeNull();
    expect(store.portfolio?.sync.generation).toBe(2);
    expect(store.resourceFreshness.portfolio.status).toBe('fresh');
  });

  it('sequences filtered lot reads resource-wide and preserves intent after an older null-generation response', async () => {
    const olderResponse = deferred<Response>();
    const newerResponse = deferred<Response>();
    let lotCalls = 0;
    const fetcher = vi.fn<typeof fetch>((input) => {
      if (requestAddress(input).pathname !== '/api/v1/lots')
        return Promise.reject(new Error(`Unhandled fake route: ${requestAddress(input).pathname}`));
      lotCalls += 1;
      return lotCalls === 1 ? olderResponse.promise : newerResponse.promise;
    });
    vi.stubGlobal('fetch', fetcher);
    const { workspace: store, queryClient } = mountWorkspaceHarness();

    store.observeSourceGeneration(2);
    expect(store.setLotReviewIntent('LOT-2', 'AAPL', 2, true)).toBe(true);
    const olderLoad = store.loadLots({ ticker: 'OLD' });
    const newerLoad = store.loadLots({ ticker: 'NEW' });
    await vi.waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2));
    expect(store.actionState.loadLots.pendingCount).toBe(2);

    newerResponse.resolve(
      jsonResponse({ items: [], total: 2, offset: 0, limit: 100, source_generation: 2 }),
    );
    await expect(newerLoad).resolves.toMatchObject({ total: 2, source_generation: 2 });
    expect(store.actionState.loadLots.pendingCount).toBe(1);

    olderResponse.resolve(
      jsonResponse({ items: [], total: 1, offset: 0, limit: 100, source_generation: null }),
    );
    await expect(olderLoad).resolves.toMatchObject({ total: 1, source_generation: null });

    expect(store.observedSourceGeneration).toBe(2);
    expect(store.lotReviewIntent).toMatchObject([
      { broker_lot_id: 'LOT-2', ticker: 'AAPL', source_generation: 2 },
    ]);
    expect(queryClient.getQueryData(workspaceQueryKeys.lots({ ticker: 'OLD' }))).toBeUndefined();
    expect(queryClient.getQueryData(workspaceQueryKeys.lots({ ticker: 'NEW' }))).toMatchObject({
      total: 2,
    });
    expect(store.actionState.loadLots.pendingCount).toBe(0);
  });

  it('orders equivalent filtered lot keys by resource request order despite property insertion order', async () => {
    const olderResponse = deferred<Response>();
    const newerResponse = deferred<Response>();
    let lotCalls = 0;
    const fetcher = vi.fn<typeof fetch>((input) => {
      if (requestAddress(input).pathname !== '/api/v1/lots')
        return Promise.reject(new Error(`Unhandled fake route: ${requestAddress(input).pathname}`));
      lotCalls += 1;
      return lotCalls === 1 ? olderResponse.promise : newerResponse.promise;
    });
    vi.stubGlobal('fetch', fetcher);
    const { workspace: store, queryClient } = mountWorkspaceHarness();
    const olderFilters = { ticker: 'AAPL', offset: 0, limit: 25 };
    const newerFilters = { limit: 25, offset: 0, ticker: 'AAPL' };

    const olderLoad = store.loadLots(olderFilters);
    const newerLoad = store.loadLots(newerFilters);
    await vi.waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2));

    newerResponse.resolve(
      jsonResponse({ items: [], total: 2, offset: 0, limit: 25, source_generation: 2 }),
    );
    await expect(newerLoad).resolves.toMatchObject({ total: 2 });
    olderResponse.resolve(
      jsonResponse({ items: [], total: 1, offset: 0, limit: 25, source_generation: 1 }),
    );
    await expect(olderLoad).resolves.toMatchObject({ total: 1 });

    expect(queryClient.getQueryData(workspaceQueryKeys.lots(olderFilters))).toMatchObject({
      total: 2,
    });
    expect(queryClient.getQueryData(workspaceQueryKeys.lots(newerFilters))).toMatchObject({
      total: 2,
    });
    expect(store.observedSourceGeneration).toBe(2);
    expect(store.actionState.loadLots.pendingCount).toBe(0);
  });

  it('publishes an unseen filtered load failure after immediate unmount for the next observer', async () => {
    const failedResponse = deferred<Response>();
    const fetcher = vi.fn<typeof fetch>((input) => {
      if (requestAddress(input).pathname !== '/api/v1/lots')
        return Promise.reject(new Error(`Unhandled fake route: ${requestAddress(input).pathname}`));
      return failedResponse.promise;
    });
    vi.stubGlobal('fetch', fetcher);
    const { workspace: store, queryClient, wrapper } = mountWorkspaceHarness();
    const filters = { ticker: 'UNSEEN' };

    const load = store.loadLots(filters);
    wrapper.unmount();
    expect(fetcher).toHaveBeenCalledTimes(1);

    failedResponse.resolve(
      jsonResponse(
        {
          code: 'lots_unavailable',
          message: 'The filtered lots read failed',
          details: {},
          correlation_id: 'unseen-lots-failure',
        },
        503,
      ),
    );
    await expect(load).rejects.toMatchObject({
      code: 'lots_unavailable',
      correlationId: 'unseen-lots-failure',
    });

    const key = workspaceQueryKeys.lots(filters);
    expect(queryClient.getQueryState(key)).toMatchObject({ status: 'error', fetchStatus: 'idle' });
    const { workspace: remounted } = mountWorkspaceHarness();
    expect(remounted.resourceFreshness.lots.status).toBe('error');
    expect(remounted.lots).toBeNull();
  });

  it('does not replay cached policy observations after a failed activation refresh, but observes identical successful reads', async () => {
    const oldPolicy = { active: { id: 'policy-old' }, drafts: [], superseded: [] };
    let policyReads = 0;
    const fetcher = vi.fn<typeof fetch>((input, init) => {
      const url = requestAddress(input);
      if (url.pathname === '/health')
        return responsePromise({
          status: 'ok',
          schema_ready: true,
          broker_mode: 'fake',
          live_broker_enabled: false,
          order_submission_enabled: false,
        });
      if (url.pathname === '/api/v1/portfolio') return responsePromise(readyPortfolio(1));
      if (url.pathname === '/api/v1/policy') {
        policyReads += 1;
        return policyReads === 2
          ? responsePromise(
              {
                code: 'policy_unavailable',
                message: 'Policy read failed',
                details: {},
                correlation_id: 'policy-refresh-error',
              },
              503,
            )
          : responsePromise(oldPolicy);
      }
      if (url.pathname.endsWith('/activate'))
        return responsePromise({ id: 'policy-new', status: 'ACTIVE' });
      if (url.pathname === '/api/v1/optimizer/runs' && init?.method === 'POST')
        return responsePromise(
          { ...demoRun('policy-new-run'), policy_revision_id: 'policy-new' },
          201,
        );
      if (url.pathname === '/api/v1/lots')
        return responsePromise({
          items: [],
          total: 0,
          offset: 0,
          limit: 100,
          source_generation: 1,
        });
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
    const { workspace: store, wrapper } = mountWorkspaceHarness();

    await store.loadPolicy();
    await store.activatePolicy('policy-new');
    expect(store.resourceFreshness.policy.status).toBe('stale');
    expect(store.policy?.active?.id).toBe('policy-old');
    await store.runOptimizer();
    expect(store.currentRunView).toBe('current');

    wrapper.unmount();
    const { workspace: remounted } = mountWorkspaceHarness();
    expect(remounted.currentRunView).toBe('current');

    const cachedPolicy = remounted.policy;
    const identicalPolicy = await remounted.loadPolicy();
    expect(remounted.policy).toBe(cachedPolicy);
    expect(identicalPolicy.active?.id).toBe('policy-old');
    expect(remounted.currentRunView).toBe('stale');
    expect(policyReads).toBe(3);
  });

  it('does not replay cached incomplete-portfolio observations on facade remount', async () => {
    const fetcher = vi.fn<typeof fetch>((input, init) => {
      const url = requestAddress(input);
      if (url.pathname === '/api/v1/portfolio') return responsePromise(portfolioResponse('0.00'));
      if (url.pathname === '/api/v1/optimizer/runs' && init?.method === 'POST')
        return responsePromise(demoRun('incomplete-portfolio-run'), 201);
      return Promise.reject(new Error(`Unhandled fake route: ${url.pathname}`));
    });
    vi.stubGlobal('fetch', fetcher);
    const { workspace: store, wrapper } = mountWorkspaceHarness();

    await store.loadPortfolio();
    expect(store.observedSourceGeneration).toBeNull();
    await store.runOptimizer();
    expect(store.currentRunView).toBe('current');

    wrapper.unmount();
    const { workspace: remounted } = mountWorkspaceHarness();
    expect(remounted.currentRunView).toBe('current');
  });

  it('publishes an accepted response observation after its component unmounts', async () => {
    const portfolioResponsePending = deferred<Response>();
    const fetcher = vi.fn<typeof fetch>((input) => {
      if (requestAddress(input).pathname !== '/api/v1/portfolio')
        return Promise.reject(new Error(`Unhandled fake route: ${requestAddress(input).pathname}`));
      return portfolioResponsePending.promise;
    });
    vi.stubGlobal('fetch', fetcher);
    const { workspace: store, queryClient, wrapper } = mountWorkspaceHarness();

    const pendingLoad = store.loadPortfolio();
    await vi.waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1));
    expect(store.actionState.loadPortfolio.pendingCount).toBe(1);
    wrapper.unmount();

    portfolioResponsePending.resolve(jsonResponse(readyPortfolio(9)));
    await expect(pendingLoad).resolves.toMatchObject({ sync: { generation: 9 } });
    expect(
      queryClient.getQueryData<PortfolioReadyResponse>(workspaceQueryKeys.portfolio)?.sync
        .generation,
    ).toBe(9);
    expect(store.observedSourceGeneration).toBe(9);
    expect(store.actionState.loadPortfolio.pendingCount).toBe(0);
  });

  it('synchronizes and reloads without auto-running the optimizer', async () => {
    const fetcher = installDefaultApi();
    const { workspace: store } = mountWorkspaceHarness();

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
    const store = mountWorkspaceHarness().workspace;
    await store.runOptimizer();
    const original = currentRunForTest(store);
    const selected = {
      selected_group_ids: ['group/1'],
      selected_sell_lots: { 'group/1': ['lot #42'] },
    };

    const recalculated = await store.recalculateSelection(selected);
    expect(bodyJson(fetcher.mock.calls[1]?.[1])).toEqual(selected);
    expect(store.currentRun).toEqual(recalculated);
    expect(store.currentRun?.warnings).toEqual(['server-authoritative result']);

    rejectSelection = true;
    const lastValidRun = currentRunForTest(store);
    await expect(store.recalculateSelection({ selected_group_ids: [] })).rejects.toMatchObject({
      code: 'invalid_selection',
      correlationId: 'selection-error',
    });
    expect(currentRunForTest(store)).toBe(lastValidRun);
    expect(currentRunForTest(store)).not.toBe(original);
    expect(store.actionState.recalculateSelection.error?.code).toBe('invalid_selection');
  });

  it('replaces annotated runs and summaries atomically after run ID validation', async () => {
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
    const store = mountWorkspaceHarness().workspace;
    seedCurrentRunForTest(store, initial);
    store.currentRunView = 'current';
    seedCurrentRunSummaryForTest(store, { ...demoRun('annotated-run'), orders_count: 2 });

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

    const successfulRun = currentRunForTest(store);
    const successfulSummary = currentRunSummaryForTest(store);
    response = { ...updated, run_id: 'different-run' };
    await expect(
      store.annotateGroup('annotated-run', 'group-1', { note: null }),
    ).rejects.toMatchObject({ code: 'run_id_mismatch' });
    expect(currentRunForTest(store)).toBe(successfulRun);
    expect(currentRunSummaryForTest(store)).toBe(successfulSummary);
  });

  it('serializes annotations, selection, and lot intent through the review queue', async () => {
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
    let intentBody: unknown;
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
      if (url.pathname.endsWith('/lot-review-intent') && init?.method === 'POST') {
        requestOrder.push('POST lot-review-intent');
        intentBody = bodyJson(init);
        return responsePromise(serverRun);
      }
      return Promise.reject(new Error(`Unhandled fake route: ${init?.method} ${url.pathname}`));
    });
    vi.stubGlobal('fetch', fetcher);
    const store = mountWorkspaceHarness().workspace;
    seedCurrentRunForTest(store, initial);
    store.currentRunView = 'current';
    store.observeSourceGeneration(1);

    const firstAnnotation = store.annotateGroup('ordered-run', 'group-1', {
      note: 'confirmed one',
    });
    const secondAnnotation = store.annotateGroup('ordered-run', 'group-2', {
      note: 'confirmed two',
    });
    const selection = store.recalculateSelection({ selected_group_ids: ['group-2'] });
    store.setLotReviewIntent('LOT-1', 'VB', 1, true);
    const lotIntent = store.applyLotReviewIntent();
    expect(store.reviewMutationPending).toBe(true);
    await flushPromises();
    expect(requestOrder).toEqual(['PATCH group-1']);

    firstAnnotationResponse.resolve(jsonResponse(serverRun));
    await firstAnnotation;
    await Promise.all([secondAnnotation, selection, lotIntent]);

    expect(requestOrder).toEqual([
      'PATCH group-1',
      'PATCH group-2',
      'POST selection',
      'POST lot-review-intent',
    ]);
    expect(intentBody).toEqual({ source_generation: 1, broker_lot_ids: ['LOT-1'] });
    expect(store.currentRun?.groups.map((item) => item.note)).toEqual([
      'confirmed one',
      'confirmed two',
    ]);
    expect(store.reviewMutationPending).toBe(false);
  });

  it('reconciles lot intent after selection and annotation responses', async () => {
    const runId = 'lot-intent-reconcile';
    let serverRun = runWithSelectedSellLots(demoRun(runId), ['LOT-1']);
    const appliedBodies: unknown[] = [];
    const fetcher = vi.fn<typeof fetch>((input, init) => {
      const url = requestAddress(input);
      if (url.pathname.endsWith('/lot-review-intent') && init?.method === 'POST') {
        appliedBodies.push(bodyJson(init));
        serverRun = runWithSelectedSellLots(demoRun(runId), ['LOT-1']);
        return responsePromise(serverRun);
      }
      if (url.pathname.endsWith('/selection') && init?.method === 'POST') {
        serverRun = runWithSelectedSellLots(demoRun(runId), ['LOT-2']);
        return responsePromise(serverRun);
      }
      if (url.pathname.endsWith('/recommendations/group-1') && init?.method === 'PATCH') {
        const annotation = bodyJson(init) as { rejected?: boolean };
        serverRun = runWithSelectedSellLots(
          demoRun(runId),
          annotation.rejected ? [] : ['LOT-1'],
          annotation.rejected,
        );
        return responsePromise(serverRun);
      }
      return Promise.reject(new Error(`Unhandled fake route: ${init?.method} ${url.pathname}`));
    });
    vi.stubGlobal('fetch', fetcher);
    const store = mountWorkspaceHarness().workspace;
    seedCurrentRunForTest(store, serverRun);
    store.currentRunView = 'current';
    store.observeSourceGeneration(1);
    store.setLotReviewIntent('LOT-1', 'VB', 1, true);

    await store.applyLotReviewIntent();
    expect(store.lotReviewIntentConfirmedRunId).toBe(runId);
    expect(store.lotReviewIntentDirty).toBe(false);

    await store.annotateGroup(runId, 'group-1', { note: 'same selected lots' });
    expect(store.lotReviewIntentConfirmedRunId).toBe(runId);
    expect(store.lotReviewIntentDirty).toBe(false);

    await store.recalculateSelection({ selected_group_ids: [] });
    expect(store.lotReviewIntentConfirmedRunId).toBeNull();
    expect(store.lotReviewIntentDirty).toBe(true);
    expect(store.lotReviewIntentNotice).toContain('Apply the requested set again');

    await store.applyLotReviewIntent();
    expect(store.lotReviewIntentConfirmedRunId).toBe(runId);
    expect(store.lotReviewIntentDirty).toBe(false);
    expect(appliedBodies).toEqual([
      { source_generation: 1, broker_lot_ids: ['LOT-1'] },
      { source_generation: 1, broker_lot_ids: ['LOT-1'] },
    ]);

    await store.annotateGroup(runId, 'group-1', { rejected: true });
    expect(store.lotReviewIntentConfirmedRunId).toBeNull();
    expect(store.lotReviewIntentDirty).toBe(true);
    expect(store.lotReviewIntentNotice).toContain('Apply the requested set again');
  });

  it('makes staged lots reapplicable when a new current run replaces the confirmed run', async () => {
    const previousRun = runWithSelectedSellLots(demoRun('previous-run'), ['LOT-1']);
    const newRun = runWithSelectedSellLots(demoRun('new-run'), ['LOT-2']);
    const newRunAfterIntent = runWithSelectedSellLots(demoRun('new-run'), ['LOT-1']);
    const lotIntentPaths: string[] = [];
    const fetcher = vi.fn<typeof fetch>((input, init) => {
      const url = requestAddress(input);
      if (url.pathname === '/api/v1/optimizer/runs' && init?.method === 'POST')
        return responsePromise(newRun, 201);
      if (url.pathname.endsWith('/lot-review-intent') && init?.method === 'POST') {
        lotIntentPaths.push(url.pathname);
        return responsePromise(
          url.pathname.includes('/new-run/') ? newRunAfterIntent : previousRun,
        );
      }
      return Promise.reject(new Error(`Unhandled fake route: ${init?.method} ${url.pathname}`));
    });
    vi.stubGlobal('fetch', fetcher);
    const store = mountWorkspaceHarness().workspace;
    seedCurrentRunForTest(store, previousRun);
    store.currentRunView = 'current';
    store.observeSourceGeneration(1);
    store.setLotReviewIntent('LOT-1', 'VB', 1, true);

    await store.applyLotReviewIntent();
    expect(store.lotReviewIntentConfirmedRunId).toBe('previous-run');
    expect(store.lotReviewIntentDirty).toBe(false);

    await store.runOptimizer();
    expect(store.currentRun?.run_id).toBe('new-run');
    expect(store.lotReviewIntentConfirmedRunId).toBeNull();
    expect(store.lotReviewIntentDirty).toBe(true);

    await store.applyLotReviewIntent();
    expect(store.lotReviewIntentConfirmedRunId).toBe('new-run');
    expect(store.lotReviewIntentDirty).toBe(false);
    expect(lotIntentPaths).toEqual([
      '/api/v1/optimizer/runs/previous-run/lot-review-intent',
      '/api/v1/optimizer/runs/new-run/lot-review-intent',
    ]);
  });

  it('does not confirm a lot intent superseded by edits while its request is in flight', async () => {
    const runId = 'in-flight-lot-intent';
    const response = deferred<Response>();
    let submittedBody: unknown;
    const fetcher = vi.fn<typeof fetch>((input, init) => {
      const url = requestAddress(input);
      if (url.pathname.endsWith('/lot-review-intent') && init?.method === 'POST') {
        submittedBody = bodyJson(init);
        return response.promise;
      }
      return Promise.reject(new Error(`Unhandled fake route: ${init?.method} ${url.pathname}`));
    });
    vi.stubGlobal('fetch', fetcher);
    const store = mountWorkspaceHarness().workspace;
    seedCurrentRunForTest(store, demoRun(runId));
    store.currentRunView = 'current';
    store.observeSourceGeneration(1);
    store.setLotReviewIntent('LOT-1', 'VB', 1, true);

    const applying = store.applyLotReviewIntent();
    await flushPromises();
    expect(submittedBody).toEqual({ source_generation: 1, broker_lot_ids: ['LOT-1'] });
    expect(store.lotReviewIntentConfirmedRunId).toBeNull();

    store.setLotReviewIntent('LOT-1', 'VB', 1, false);
    store.setLotReviewIntent('LOT-2', 'VB', 1, true);
    response.resolve(jsonResponse(runWithSelectedSellLots(demoRun(runId), ['LOT-1'])));
    await applying;

    expect(store.lotReviewIntent.map((entry) => entry.broker_lot_id)).toEqual(['LOT-2']);
    expect(store.lotReviewIntentConfirmedRunId).toBeNull();
    expect(store.lotReviewIntentDirty).toBe(true);
    expect(store.lotReviewIntentNotice).toContain('different SELL lots than the requested set');
  });

  it('invalidates requested lots on generation changes and treats null as unvalidated', () => {
    const store = mountWorkspaceHarness().workspace;
    seedCurrentRunForTest(store, { ...demoRun('source-3'), source_generation: 3 });
    store.currentRunView = 'current';
    store.observeSourceGeneration(3);
    store.setLotReviewIntent('LOT-3', 'VB', 3, true);

    store.observeSourceGeneration(4);
    expect(store.lotReviewIntent).toEqual([]);
    expect(store.lotReviewIntentGeneration).toBeNull();
    expect(store.lotReviewIntentNotice).toContain('Source generation changed to 4');
    expect(store.currentRunView).toBe('stale');

    store.setLotReviewIntent('LOT-4', 'VB', 4, true);
    store.observeSourceGeneration(3); // Late page responses cannot roll the generation back.
    expect(store.observedSourceGeneration).toBe(4);
    expect(store.lotReviewIntent).toHaveLength(1);

    store.observeSourceGeneration(null);
    expect(store.observedSourceGeneration).toBeNull();
    expect(store.lotReviewIntent).toEqual([]);
    expect(store.lotReviewIntentNotice).toContain('source generation is unavailable');
  });

  it('discards a late lot-intent response when a different run opens', async () => {
    const pendingIntentResponse = deferred<Response>();
    const fetcher = vi.fn<typeof fetch>((input) => {
      const url = requestAddress(input);
      if (url.pathname.endsWith('/lot-review-intent')) return pendingIntentResponse.promise;
      if (url.pathname === '/api/v1/optimizer/runs/saved')
        return responsePromise({ run_id: 'saved' });
      if (url.pathname === '/api/v1/optimizer/runs/saved/recommendations')
        return responsePromise(demoRun('saved'));
      return Promise.reject(new Error(`Unhandled fake route: ${url.pathname}`));
    });
    vi.stubGlobal('fetch', fetcher);
    const store = mountWorkspaceHarness().workspace;
    seedCurrentRunForTest(store, demoRun('intent-run'));
    store.currentRunView = 'current';
    store.observeSourceGeneration(1);
    store.setLotReviewIntent('LOT-1', 'VB', 1, true);

    const applying = store.applyLotReviewIntent();
    await Promise.resolve();
    await store.openSavedRun('saved');
    pendingIntentResponse.resolve(jsonResponse(demoRun('intent-run', ['late intent'])));

    await expect(applying).rejects.toMatchObject({ code: 'run_context_changed' });
    expect(store.currentRun?.run_id).toBe('saved');
    expect(store.currentRunView).toBe('saved');
    expect(store.lotReviewIntentConfirmedRunId).toBeNull();
    expect(store.lotReviewIntentDirty).toBe(true);
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
    const store = mountWorkspaceHarness().workspace;

    const olderRun = store.runOptimizer();
    await store.runOptimizer();
    firstRunResponse.resolve(jsonResponse(demoRun('old-run'), 201));
    await olderRun;
    expect(store.currentRun?.run_id).toBe('new-run');

    const oldSelection = store.recalculateSelection({ selected_group_ids: ['old'] });
    await flushPromises();
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
        return responsePromise({
          items: [],
          total: 0,
          offset: 0,
          limit: 100,
          source_generation: 1,
        });
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
    const { workspace: store, queryClient } = mountWorkspaceHarness();
    queryClient.setQueryData(workspaceQueryKeys.policy, {
      active: { id: 'policy-demo', status: 'ACTIVE' },
      drafts: [],
      superseded: [],
    } as unknown as PolicyResponse);
    seedCurrentRunForTest(store, demoRun('active-policy-run'));
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
        return responsePromise({
          items: [],
          total: 0,
          offset: 0,
          limit: 100,
          source_generation: 1,
        });
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
    const { workspace: store } = mountWorkspaceHarness();
    seedCurrentRunForTest(store, demoRun('source-run'));
    store.currentRunView = 'current';

    await store.syncPortfolio();
    expect(store.currentRunView).toBe('current');
    generation = 2;
    await store.syncPortfolio();

    expect(store.lastSync?.generation).toBe(2);
    expect(store.currentRunView).toBe('stale');
  });

  it('distinguishes unknown policy from confirmed absence', async () => {
    const fetcher = vi.fn<typeof fetch>((input, init) => {
      const url = requestAddress(input);
      if (url.pathname === '/api/v1/optimizer/runs' && init?.method === 'POST')
        return responsePromise(demoRun('run-without-active-policy'), 201);
      return Promise.reject(new Error(`Unhandled fake route: ${init?.method} ${url.pathname}`));
    });
    vi.stubGlobal('fetch', fetcher);
    const store = mountWorkspaceHarness().workspace;

    store.observeActivePolicyRevision(null);
    await store.runOptimizer();

    expect(store.currentRun?.run_id).toBe('run-without-active-policy');
    expect(store.currentRunView).toBe('stale');
  });

  it('keeps a run current when an inactive draft leaves active policy unchanged', async () => {
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
    const { workspace: store, queryClient } = mountWorkspaceHarness();
    queryClient.setQueryData(workspaceQueryKeys.policy, {
      active: activePolicy,
      drafts: [],
      superseded: [],
    } as unknown as PolicyResponse);
    await store.runOptimizer();

    await store.savePolicyDraft({ settings: {}, sleeves: [] });

    expect(store.policy?.active?.id).toBe('policy-demo');
    expect(store.currentRunView).toBe('current');
    expect(store.proposedRunIsStale).toBe(false);
    expect(store.currentRun?.run_id).toBe('policy-run');
  });
});

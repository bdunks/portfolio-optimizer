import { computed, ref, type Ref } from 'vue';
import {
  useQuery,
  useQueryClient,
  type QueryClient,
  type UseQueryOptions,
} from '@tanstack/vue-query';
import type { QueryClient as CoreQueryClient } from '@tanstack/query-core';
import type {
  ActivityPageResponse,
  HealthResponse,
  LotPageResponse,
  OptimizerRecommendationsResponse,
  OptimizerRunResponse,
  SyncResponseDTO,
  PolicyResponse,
  WashSalesResponse,
} from '../../types/api';
import type { ApiClient, ActivityQuery, LotQuery, PortfolioResponse } from '../../services/api';

import type { WorkspaceAction } from '../../stores/workspace-store';
import type {
  ResourceFreshness,
  WorkspaceResourceFreshness,
  WorkspaceResourceKey,
} from '../../types/workspace-resources';

export const workspaceQueryKeys = {
  all: ['workspace'] as const,
  lastSync: ['workspace', 'lastSync'] as const,
  currentRun: (runId: string) =>
    ['workspace', 'optimizer', 'run', runId, 'recommendations'] as const,
  currentRunSummary: (runId: string) =>
    ['workspace', 'optimizer', 'run', runId, 'summary'] as const,
  health: ['workspace', 'health'] as const,
  portfolio: ['workspace', 'portfolio'] as const,
  policy: ['workspace', 'policy'] as const,
  lots: (filters: LotQuery) => ['workspace', 'lots', { ...filters }] as const,
  washSales: ['workspace', 'washSales'] as const,
  activity: (filters: ActivityQuery) => ['workspace', 'activity', { ...filters }] as const,
};

export type WorkspaceQueryKey = WorkspaceResourceKey;
type Perform = <T>(action: WorkspaceAction, operation: () => Promise<T>) => Promise<T>;
type WorkspaceQueryCallbacks = {
  observeSourceGeneration: (generation: number | null) => void;
  observeActivePolicyRevision: (revisionId: string | null) => void;
};
type QueryOptions<TData> = Omit<UseQueryOptions<TData, Error, TData>, 'queryKey' | 'queryFn'> & {
  queryKey: readonly unknown[];
  queryFn: () => Promise<TData>;
};

const disabledFinancialQueries = {
  enabled: false,
  staleTime: Infinity,
  retry: false,
  refetchOnWindowFocus: false,
  refetchOnReconnect: false,
  refetchOnMount: false,
} as const;

const initialLoads = new WeakMap<
  QueryClient,
  { pending: Ref<boolean>; promise: Promise<void> | null }
>();

const loadSequences = new WeakMap<QueryClient, Map<WorkspaceResourceKey, number>>();

function nextLoadSequence(
  queryClient: QueryClient,
  resource: WorkspaceResourceKey,
): {
  isCurrent: () => boolean;
} {
  let sequences = loadSequences.get(queryClient);
  if (!sequences) {
    sequences = new Map();
    loadSequences.set(queryClient, sequences);
  }
  const sequence = (sequences.get(resource) ?? 0) + 1;
  sequences.set(resource, sequence);
  return { isCurrent: () => sequences.get(resource) === sequence };
}
function initialLoadState(queryClient: QueryClient) {
  let state = initialLoads.get(queryClient);
  if (!state) {
    state = { pending: ref(false), promise: null };
    initialLoads.set(queryClient, state);
  }
  return state;
}

function freshness<TData>(query: {
  data: Ref<TData | undefined>;
  dataUpdatedAt: Ref<number>;
  isError: Ref<boolean>;
}): Ref<ResourceFreshness> {
  return computed(() => {
    const hasData = query.data.value !== undefined;
    const status = !hasData
      ? query.isError.value
        ? 'error'
        : 'not-loaded'
      : query.isError.value
        ? 'stale'
        : 'fresh';
    return {
      status,
      confirmedAt:
        hasData && query.dataUpdatedAt.value > 0
          ? new Date(query.dataUpdatedAt.value).toISOString()
          : null,
    };
  });
}

export function useWorkspaceQueries(
  client: ApiClient,
  perform: Perform,
  callbacks: WorkspaceQueryCallbacks,
  filters: {
    lotFilters: Ref<LotQuery>;
    activityFilters: Ref<ActivityQuery>;
    currentRunId: Ref<string | null>;
    currentRunSummaryId: Ref<string | null>;
  },
) {
  const queryClient = useQueryClient();
  const initialState = initialLoadState(queryClient);

  const healthOptions: QueryOptions<HealthResponse> = {
    ...disabledFinancialQueries,
    queryKey: workspaceQueryKeys.health,
    queryFn: () => client.getHealth(),
  };
  const portfolioOptions: QueryOptions<PortfolioResponse> = {
    ...disabledFinancialQueries,
    queryKey: workspaceQueryKeys.portfolio,
    queryFn: () => client.getPortfolio(),
  };
  const policyOptions: QueryOptions<PolicyResponse> = {
    ...disabledFinancialQueries,
    queryKey: workspaceQueryKeys.policy,
    queryFn: () => client.getPolicy(),
  };
  const washSalesOptions: QueryOptions<WashSalesResponse> = {
    ...disabledFinancialQueries,
    queryKey: workspaceQueryKeys.washSales,
    queryFn: () => client.getWashSales(),
  };
  const lotOptions = (query: LotQuery): QueryOptions<LotPageResponse> => ({
    ...disabledFinancialQueries,
    queryKey: workspaceQueryKeys.lots(query),
    queryFn: () => client.getLots(query),
  });
  const activityOptions = (query: ActivityQuery): QueryOptions<ActivityPageResponse> => ({
    ...disabledFinancialQueries,
    queryKey: workspaceQueryKeys.activity(query),
    queryFn: () => client.getActivity(query),
  });

  const healthQuery = useQuery(healthOptions);
  const portfolioQuery = useQuery(portfolioOptions);
  const policyQuery = useQuery(policyOptions);
  const lotsQuery = useQuery({
    ...disabledFinancialQueries,
    queryKey: computed(() => workspaceQueryKeys.lots(filters.lotFilters.value)),
    queryFn: ({ queryKey }) => {
      const query = queryKey[2];
      return client.getLots(query);
    },
  });
  const washSalesQuery = useQuery(washSalesOptions);
  const activityQuery = useQuery({
    ...disabledFinancialQueries,
    queryKey: computed(() => workspaceQueryKeys.activity(filters.activityFilters.value)),
    queryFn: ({ queryKey }) => {
      const query = queryKey[2];
      return client.getActivity(query);
    },
  });
  const currentRunQuery = useQuery<OptimizerRecommendationsResponse>({
    ...disabledFinancialQueries,
    gcTime: Infinity,
    queryKey: computed(() => workspaceQueryKeys.currentRun(filters.currentRunId.value ?? '')),
    queryFn: () => {
      throw new Error('Current run recommendations are cache-only');
    },
  });
  const currentRunSummaryQuery = useQuery<OptimizerRunResponse>({
    ...disabledFinancialQueries,
    gcTime: Infinity,
    queryKey: computed(() =>
      workspaceQueryKeys.currentRunSummary(filters.currentRunSummaryId.value ?? ''),
    ),
    queryFn: () => {
      throw new Error('Current run summaries are cache-only');
    },
  });
  const lastSyncQuery = useQuery<SyncResponseDTO>({
    ...disabledFinancialQueries,
    gcTime: Infinity,
    queryKey: workspaceQueryKeys.lastSync,
    queryFn: () => {
      throw new Error('Portfolio sync results are cache-only');
    },
  });

  const health = computed(() => healthQuery.data.value ?? null);
  const portfolio = computed(() => portfolioQuery.data.value ?? null);
  const policy = computed(() => policyQuery.data.value ?? null);
  const lots = computed(() => lotsQuery.data.value ?? null);
  const washSales = computed(() => washSalesQuery.data.value ?? null);
  const activity = computed(() => activityQuery.data.value ?? null);
  const currentRun = computed(() => currentRunQuery.data.value ?? null);
  const currentRunSummary = computed(() => currentRunSummaryQuery.data.value ?? null);
  const lastSync = computed(() => lastSyncQuery.data.value ?? null);

  const healthFreshness = freshness(healthQuery);
  const portfolioFreshness = freshness(portfolioQuery);
  const policyFreshness = freshness(policyQuery);
  const lotsFreshness = freshness(lotsQuery);
  const washSalesFreshness = freshness(washSalesQuery);
  const activityFreshness = freshness(activityQuery);
  function ensureQueryEntry<TData>(key: readonly unknown[], options: QueryOptions<TData>): void {
    const queryCache = queryClient.getQueryCache();
    if (queryCache.find({ queryKey: key, exact: true })) return;
    queryCache.build<TData, Error, TData>(queryClient as unknown as CoreQueryClient, {
      queryKey: key,
      queryFn: options.queryFn,
    });
  }

  function publishQueryError<TData>(
    key: readonly unknown[],
    options: QueryOptions<TData>,
    error: unknown,
  ): void {
    const queryCache = queryClient.getQueryCache();
    const query =
      queryCache.find<TData, Error, TData>({ queryKey: key, exact: true }) ??
      queryCache.build<TData, Error, TData>(queryClient as unknown as CoreQueryClient, {
        queryKey: key,
        queryFn: options.queryFn,
      });
    query.setState({
      error: error instanceof Error ? error : new Error(String(error)),
      errorUpdatedAt: Date.now(),
      errorUpdateCount: query.state.errorUpdateCount + 1,
      status: 'error',
      fetchStatus: 'idle',
    });
  }

  async function load<TData>(
    action: WorkspaceAction,
    key: readonly unknown[],
    options: QueryOptions<TData>,
    onAcceptedSuccess?: (data: TData) => void,
  ): Promise<TData> {
    const request = nextLoadSequence(queryClient, key[1] as WorkspaceResourceKey);
    ensureQueryEntry(key, options);
    return perform(action, async () => {
      let result: TData;
      try {
        result = await options.queryFn();
      } catch (error) {
        if (request.isCurrent()) publishQueryError(key, options, error);
        throw error;
      }

      if (request.isCurrent()) {
        queryClient.setQueryData<TData>(key, result);
        onAcceptedSuccess?.(result);
      }
      return result;
    });
  }

  function loadHealth(): Promise<HealthResponse> {
    return load('loadHealth', workspaceQueryKeys.health, healthOptions);
  }
  function loadPortfolio(): Promise<PortfolioResponse> {
    return load('loadPortfolio', workspaceQueryKeys.portfolio, portfolioOptions, (value) =>
      callbacks.observeSourceGeneration(
        value.status === 'ready' && value.sync.complete ? value.sync.generation : null,
      ),
    );
  }
  function loadPolicy(): Promise<PolicyResponse> {
    return load('loadPolicy', workspaceQueryKeys.policy, policyOptions, (value) =>
      callbacks.observeActivePolicyRevision(value.active?.id ?? null),
    );
  }
  function loadLots(query?: LotQuery): Promise<LotPageResponse> {
    if (query) filters.lotFilters.value = { ...query };
    const currentFilters = { ...filters.lotFilters.value };
    return load(
      'loadLots',
      workspaceQueryKeys.lots(currentFilters),
      lotOptions(currentFilters),
      (value) => callbacks.observeSourceGeneration(value.source_generation),
    );
  }
  function loadWashSales(): Promise<WashSalesResponse> {
    return load('loadWashSales', workspaceQueryKeys.washSales, washSalesOptions);
  }
  function loadActivity(query?: ActivityQuery): Promise<ActivityPageResponse> {
    if (query) filters.activityFilters.value = { ...query };
    const currentFilters = { ...filters.activityFilters.value };
    return load(
      'loadActivity',
      workspaceQueryKeys.activity(currentFilters),
      activityOptions(currentFilters),
    );
  }

  function ensureInitialWorkspace(): Promise<void> {
    if (initialState.promise) return initialState.promise;
    initialState.pending.value = true;
    const requests: Promise<unknown>[] = [];
    if (queryClient.getQueryData(workspaceQueryKeys.health) === undefined)
      requests.push(loadHealth());
    if (queryClient.getQueryData(workspaceQueryKeys.portfolio) === undefined)
      requests.push(loadPortfolio());
    if (queryClient.getQueryData(workspaceQueryKeys.policy) === undefined)
      requests.push(loadPolicy());
    const tracked = Promise.allSettled(requests)
      .then(() => undefined)
      .finally(() => {
        initialState.pending.value = false;
        if (initialState.promise === tracked) initialState.promise = null;
      });
    initialState.promise = tracked;
    return tracked;
  }

  async function refreshWorkspace(): Promise<void> {
    await perform('refreshWorkspace', async () => {
      await Promise.allSettled([
        loadHealth(),
        loadPortfolio(),
        loadPolicy(),
        loadLots(),
        loadWashSales(),
        loadActivity(),
      ]);
    });
  }

  const resourceFreshness = computed<WorkspaceResourceFreshness>(() => ({
    health: healthFreshness.value,
    portfolio: portfolioFreshness.value,
    policy: policyFreshness.value,
    lots: lotsFreshness.value,
    washSales: washSalesFreshness.value,
    activity: activityFreshness.value,
  }));

  return {
    health,
    portfolio,
    policy,
    lots,
    washSales,
    activity,
    currentRun,
    currentRunSummary,
    lastSync,
    resourceFreshness,
    initialWorkspacePending: initialState.pending,
    loadHealth,
    loadPortfolio,
    loadPolicy,
    loadLots,
    loadWashSales,
    loadActivity,
    ensureInitialWorkspace,
    refreshWorkspace,
    queryClient,
  };
}

import { reactive, ref, shallowRef } from 'vue';
import type {
  ActivityPageResponse,
  HealthResponse,
  LotPageResponse,
  PolicyResponse,
  WashSalesResponse,
} from '../types/api';
import type { ApiClient, ActivityQuery, LotQuery, PortfolioResponse } from '../services/api';
import type { WorkspaceAction } from './workspace-store';

export type WorkspaceResourceKey =
  'health' | 'portfolio' | 'policy' | 'lots' | 'washSales' | 'activity';

export type ResourceFreshnessStatus = 'not-loaded' | 'fresh' | 'stale' | 'error';
export type ResourceFreshness = {
  status: ResourceFreshnessStatus;
  confirmedAt: string | null;
};
export type WorkspaceResourceFreshness = Record<WorkspaceResourceKey, ResourceFreshness>;

type Perform = <T>(action: WorkspaceAction, operation: () => Promise<T>) => Promise<T>;

type WorkspaceResourceCallbacks = {
  observeSourceGeneration: (generation: number | null) => void;
  observeActivePolicyRevision: (revisionId: string | null) => void;
};

function initialFreshness(): WorkspaceResourceFreshness {
  const state = (): ResourceFreshness => ({ status: 'not-loaded', confirmedAt: null });
  return {
    health: state(),
    portfolio: state(),
    policy: state(),
    lots: state(),
    washSales: state(),
    activity: state(),
  };
}

export function createWorkspaceResources(
  client: ApiClient,
  perform: Perform,
  callbacks: WorkspaceResourceCallbacks,
) {
  const health = shallowRef<HealthResponse | null>(null);
  const portfolio = shallowRef<PortfolioResponse | null>(null);
  const policy = shallowRef<PolicyResponse | null>(null);
  const lots = shallowRef<LotPageResponse | null>(null);
  const washSales = shallowRef<WashSalesResponse | null>(null);
  const activity = shallowRef<ActivityPageResponse | null>(null);
  const lotFilters = ref<LotQuery>({});
  const activityFilters = ref<ActivityQuery>({});
  const resourceFreshness = reactive(initialFreshness());
  const initialWorkspacePending = ref(false);

  const loadSequence: Record<WorkspaceResourceKey, number> = {
    health: 0,
    portfolio: 0,
    policy: 0,
    lots: 0,
    washSales: 0,
    activity: 0,
  };
  let initialWorkspacePromise: Promise<void> | null = null;

  async function loadValue<T>(
    key: WorkspaceResourceKey,
    action: WorkspaceAction,
    request: () => Promise<T>,
    hasCachedValue: () => boolean,
    apply: (value: T) => void,
  ): Promise<T> {
    const sequence = ++loadSequence[key];
    return perform(action, async () => {
      try {
        const value = await request();
        if (sequence === loadSequence[key]) {
          apply(value);
          resourceFreshness[key] = { status: 'fresh', confirmedAt: new Date().toISOString() };
        }
        return value;
      } catch (error) {
        if (sequence === loadSequence[key]) {
          resourceFreshness[key] = {
            status: hasCachedValue() ? 'stale' : 'error',
            confirmedAt: resourceFreshness[key].confirmedAt,
          };
        }
        throw error;
      }
    });
  }

  function loadHealth(): Promise<HealthResponse> {
    return loadValue(
      'health',
      'loadHealth',
      () => client.getHealth(),
      () => health.value !== null,
      (value) => {
        health.value = value;
      },
    );
  }

  function loadPortfolio(): Promise<PortfolioResponse> {
    return loadValue(
      'portfolio',
      'loadPortfolio',
      () => client.getPortfolio(),
      () => portfolio.value !== null,
      (value) => {
        portfolio.value = value;
        callbacks.observeSourceGeneration(
          value.status === 'ready' && value.sync.complete ? value.sync.generation : null,
        );
      },
    );
  }

  function loadPolicy(): Promise<PolicyResponse> {
    return loadValue(
      'policy',
      'loadPolicy',
      () => client.getPolicy(),
      () => policy.value !== null,
      (value) => {
        policy.value = value;
        callbacks.observeActivePolicyRevision(value.active?.id ?? null);
      },
    );
  }

  function loadLots(filters?: LotQuery): Promise<LotPageResponse> {
    if (filters) lotFilters.value = { ...filters };
    const query = { ...lotFilters.value };
    return loadValue(
      'lots',
      'loadLots',
      () => client.getLots(query),
      () => lots.value !== null,
      (value) => {
        lots.value = value;
        callbacks.observeSourceGeneration(value.source_generation);
      },
    );
  }

  function loadWashSales(): Promise<WashSalesResponse> {
    return loadValue(
      'washSales',
      'loadWashSales',
      () => client.getWashSales(),
      () => washSales.value !== null,
      (value) => {
        washSales.value = value;
      },
    );
  }

  function loadActivity(filters?: ActivityQuery): Promise<ActivityPageResponse> {
    if (filters) activityFilters.value = { ...filters };
    const query = { ...activityFilters.value };
    return loadValue(
      'activity',
      'loadActivity',
      () => client.getActivity(query),
      () => activity.value !== null,
      (value) => {
        activity.value = value;
      },
    );
  }

  function ensureInitialWorkspace(): Promise<void> {
    if (initialWorkspacePromise) return initialWorkspacePromise;
    initialWorkspacePending.value = true;
    const requests: Promise<unknown>[] = [];
    if (!health.value) requests.push(loadHealth());
    if (!portfolio.value) requests.push(loadPortfolio());
    if (!policy.value) requests.push(loadPolicy());
    const tracked = Promise.allSettled(requests)
      .then(() => undefined)
      .finally(() => {
        initialWorkspacePending.value = false;
        if (initialWorkspacePromise === tracked) initialWorkspacePromise = null;
      });
    initialWorkspacePromise = tracked;
    return tracked;
  }

  return {
    health,
    portfolio,
    policy,
    lots,
    washSales,
    activity,
    lotFilters,
    activityFilters,
    resourceFreshness,
    initialWorkspacePending,
    loadHealth,
    loadPortfolio,
    loadPolicy,
    loadLots,
    loadWashSales,
    loadActivity,
    ensureInitialWorkspace,
  };
}

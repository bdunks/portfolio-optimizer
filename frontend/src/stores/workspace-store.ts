import { computed, reactive, ref, shallowRef } from 'vue';
import { defineStore } from 'pinia';
import type {
  ActivityPageResponse,
  HealthResponse,
  LotPageResponse,
  OptimizerRecommendationsResponse,
  OptimizerRunResponse,
  OptimizerSelectionInput,
  PolicyDraftInput,
  PolicyResponse,
  PolicyRevisionResponse,
  RecommendationAnnotationInput,
  RecommendationGroupResponse,
  SyncResponseDTO,
  WashSalesResponse,
} from '../types/api';
import {
  api,
  ApiError,
  type ActivityQuery,
  type ApiClient,
  type ExportDownload,
  type ExportFormat,
  type LotQuery,
  type PortfolioResponse,
  type RecommendationsOnlyRunInput,
} from '../services/api';

type WorkspaceAction =
  | 'loadHealth'
  | 'loadPortfolio'
  | 'loadPolicy'
  | 'loadLots'
  | 'loadWashSales'
  | 'loadActivity'
  | 'refreshWorkspace'
  | 'syncPortfolio'
  | 'runOptimizer'
  | 'openSavedRun'
  | 'recalculateSelection'
  | 'annotateGroup'
  | 'savePolicyDraft'
  | 'activatePolicy'
  | 'exportRun';

type ActionStatus = { pending: boolean; error: ApiError | null; pendingCount: number };
type LoadKey = 'health' | 'portfolio' | 'policy' | 'lots' | 'washSales' | 'activity';
type RunView = 'current' | 'saved' | 'stale' | null;

const actionNames: WorkspaceAction[] = [
  'loadHealth',
  'loadPortfolio',
  'loadPolicy',
  'loadLots',
  'loadWashSales',
  'loadActivity',
  'refreshWorkspace',
  'syncPortfolio',
  'runOptimizer',
  'openSavedRun',
  'recalculateSelection',
  'annotateGroup',
  'savePolicyDraft',
  'activatePolicy',
  'exportRun',
];

function newActionStatus(): ActionStatus {
  return { pending: false, error: null, pendingCount: 0 };
}

function asApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error;
  const message = error instanceof Error ? error.message : 'The action could not be completed';
  return new ApiError('unexpected_error', message);
}

export function createWorkspaceStore(client: ApiClient = api) {
  return defineStore('workspace', () => {
    const health = shallowRef<HealthResponse | null>(null);
    const portfolio = shallowRef<PortfolioResponse | null>(null);
    const policy = shallowRef<PolicyResponse | null>(null);
    const lots = shallowRef<LotPageResponse | null>(null);
    const washSales = shallowRef<WashSalesResponse | null>(null);
    const activity = shallowRef<ActivityPageResponse | null>(null);
    const currentRun = shallowRef<OptimizerRecommendationsResponse | null>(null);
    const currentRunSummary = shallowRef<OptimizerRunResponse | null>(null);
    const currentRunView = ref<RunView>(null);
    const lastSync = shallowRef<SyncResponseDTO | null>(null);
    const lotFilters = ref<LotQuery>({});
    const activityFilters = ref<ActivityQuery>({});
    const actionState = reactive(
      Object.fromEntries(actionNames.map((name) => [name, newActionStatus()])) as Record<
        WorkspaceAction,
        ActionStatus
      >,
    );

    const proposedRunIsStale = computed(() => currentRunView.value === 'stale');
    const loadSequence: Record<LoadKey, number> = {
      health: 0,
      portfolio: 0,
      policy: 0,
      lots: 0,
      washSales: 0,
      activity: 0,
    };
    let refreshSequence = 0;
    let runSequence = 0;
    let selectionSequence = 0;
    let syncSequence = 0;
    let annotationSequence = 0;
    const actionSequence = Object.fromEntries(actionNames.map((name) => [name, 0])) as Record<
      WorkspaceAction,
      number
    >;

    async function perform<T>(action: WorkspaceAction, operation: () => Promise<T>): Promise<T> {
      const sequence = ++actionSequence[action];
      const status = actionState[action];
      status.pendingCount += 1;
      status.pending = true;
      status.error = null;
      try {
        return await operation();
      } catch (error) {
        if (sequence === actionSequence[action]) status.error = asApiError(error);
        throw error;
      } finally {
        status.pendingCount -= 1;
        status.pending = status.pendingCount > 0;
      }
    }

    function staleCurrentComparison(): void {
      runSequence += 1;
      selectionSequence += 1;
      if (currentRun.value && currentRunView.value === 'current') currentRunView.value = 'stale';
    }

    async function loadValue<K extends LoadKey, T>(
      key: K,
      action: WorkspaceAction,
      request: () => Promise<T>,
      apply: (value: T) => void,
    ): Promise<T> {
      const sequence = ++loadSequence[key];
      return perform(action, async () => {
        const value = await request();
        if (sequence === loadSequence[key]) apply(value);
        return value;
      });
    }

    function loadHealth(): Promise<HealthResponse> {
      return loadValue(
        'health',
        'loadHealth',
        () => client.getHealth(),
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
        (value) => {
          portfolio.value = value;
        },
      );
    }

    function loadPolicy(): Promise<PolicyResponse> {
      return loadValue(
        'policy',
        'loadPolicy',
        () => client.getPolicy(),
        (value) => {
          policy.value = value;
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
        (value) => {
          lots.value = value;
        },
      );
    }

    function loadWashSales(): Promise<WashSalesResponse> {
      return loadValue(
        'washSales',
        'loadWashSales',
        () => client.getWashSales(),
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
        (value) => {
          activity.value = value;
        },
      );
    }

    async function refreshWorkspace(): Promise<void> {
      const sequence = ++refreshSequence;
      const loadTokens = {
        health: ++loadSequence.health,
        portfolio: ++loadSequence.portfolio,
        policy: ++loadSequence.policy,
        lots: ++loadSequence.lots,
        washSales: ++loadSequence.washSales,
        activity: ++loadSequence.activity,
      };
      await perform('refreshWorkspace', async () => {
        const [nextHealth, nextPortfolio, nextPolicy, nextLots, nextWashSales, nextActivity] =
          await Promise.all([
            client.getHealth(),
            client.getPortfolio(),
            client.getPolicy(),
            client.getLots({ ...lotFilters.value }),
            client.getWashSales(),
            client.getActivity({ ...activityFilters.value }),
          ]);
        const stillLatest =
          sequence === refreshSequence &&
          Object.entries(loadTokens).every(
            ([key, token]) => loadSequence[key as LoadKey] === token,
          );
        if (stillLatest) {
          health.value = nextHealth;
          portfolio.value = nextPortfolio;
          policy.value = nextPolicy;
          lots.value = nextLots;
          washSales.value = nextWashSales;
          activity.value = nextActivity;
        }
      });
    }

    async function syncPortfolio(): Promise<SyncResponseDTO> {
      const sequence = ++syncSequence;
      return perform('syncPortfolio', async () => {
        const result = await client.syncPortfolio();
        if (sequence === syncSequence) {
          lastSync.value = result;
          staleCurrentComparison();
          await refreshWorkspace();
        }
        return result;
      });
    }

    async function runOptimizer(
      input: RecommendationsOnlyRunInput = {},
    ): Promise<OptimizerRecommendationsResponse> {
      const sequence = ++runSequence;
      selectionSequence += 1;
      currentRun.value = null;
      currentRunSummary.value = null;
      currentRunView.value = null;
      return perform('runOptimizer', async () => {
        const result = await client.createRun(input);
        if (sequence === runSequence) {
          currentRun.value = result;
          currentRunView.value = 'current';
        }
        return result;
      });
    }

    async function openSavedRun(runId: string): Promise<OptimizerRecommendationsResponse> {
      const sequence = ++runSequence;
      selectionSequence += 1;
      currentRun.value = null;
      currentRunSummary.value = null;
      currentRunView.value = null;
      return perform('openSavedRun', async () => {
        const summary = await client.getRun(runId);
        if (summary.run_id !== runId) {
          throw new ApiError('run_id_mismatch', 'The API returned a different saved run');
        }
        const recommendations = await client.getRecommendations(runId);
        if (recommendations.run_id !== runId) {
          throw new ApiError(
            'run_id_mismatch',
            'The API returned recommendations for a different run',
          );
        }
        if (sequence === runSequence) {
          currentRunSummary.value = summary;
          currentRun.value = recommendations;
          currentRunView.value = 'saved';
        }
        return recommendations;
      });
    }

    async function recalculateSelection(
      selection: OptimizerSelectionInput,
    ): Promise<OptimizerRecommendationsResponse> {
      const previous = currentRun.value;
      if (!previous) {
        throw new ApiError('no_current_run', 'Open or create a run before changing its selection');
      }
      const runId = previous.run_id;
      const runToken = runSequence;
      const sequence = ++selectionSequence;
      return perform('recalculateSelection', async () => {
        const result = await client.recalculateSelection(runId, selection);
        if (result.run_id !== runId) {
          throw new ApiError('run_id_mismatch', 'The API returned a different run selection');
        }
        if (
          sequence === selectionSequence &&
          runToken === runSequence &&
          currentRun.value?.run_id === runId
        ) {
          currentRun.value = result;
        }
        return result;
      });
    }

    async function annotateGroup(
      runId: string,
      groupId: string,
      annotation: RecommendationAnnotationInput,
    ): Promise<RecommendationGroupResponse> {
      const sequence = ++annotationSequence;
      const runToken = runSequence;
      return perform('annotateGroup', async () => {
        const result = await client.annotateGroup(runId, groupId, annotation);
        if (
          sequence === annotationSequence &&
          runToken === runSequence &&
          currentRun.value?.run_id === runId
        ) {
          const run = currentRun.value;
          currentRun.value = {
            ...run,
            groups: run.groups.map((group) => (group.group_id === groupId ? result : group)),
          };
        }
        return result;
      });
    }

    async function savePolicyDraft(payload: PolicyDraftInput): Promise<PolicyRevisionResponse> {
      return perform('savePolicyDraft', async () => {
        const result = await client.savePolicyDraft(payload);
        staleCurrentComparison();
        await loadPolicy();
        return result;
      });
    }

    async function activatePolicy(revisionId: string): Promise<PolicyRevisionResponse> {
      return perform('activatePolicy', async () => {
        const result = await client.activatePolicy(revisionId);
        staleCurrentComparison();
        await refreshWorkspace();
        return result;
      });
    }

    async function exportRun(
      runId: string,
      format: ExportFormat = 'json',
    ): Promise<ExportDownload> {
      return perform('exportRun', () => client.exportRun(runId, format));
    }

    return {
      health,
      portfolio,
      policy,
      lots,
      washSales,
      activity,
      currentRun,
      currentRunSummary,
      currentRunView,
      proposedRunIsStale,
      lastSync,
      lotFilters,
      activityFilters,
      actionState,
      loadHealth,
      loadPortfolio,
      loadPolicy,
      loadLots,
      loadWashSales,
      loadActivity,
      refreshWorkspace,
      syncPortfolio,
      runOptimizer,
      openSavedRun,
      recalculateSelection,
      annotateGroup,
      savePolicyDraft,
      activatePolicy,
      exportRun,
    };
  });
}

export const useWorkspaceStore = createWorkspaceStore();

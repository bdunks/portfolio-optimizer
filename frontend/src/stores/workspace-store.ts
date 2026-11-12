import { computed, reactive, ref } from 'vue';
import { defineStore } from 'pinia';
import type { PolicyDraftInput, PolicyRevisionResponse } from '../types/api';
import { ApiError, type ActivityQuery, type LotQuery } from '../services/api';
import { createWorkspacePolicyEditor } from './workspace-policy-editor';

export type WorkspaceAction =
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
  | 'applyLotReviewIntent'
  | 'savePolicyDraft'
  | 'activatePolicy'
  | 'exportRun';

type ActionStatus = { pending: boolean; error: ApiError | null; pendingCount: number };
type PolicyMutations = {
  savePolicyDraft: (payload: PolicyDraftInput) => Promise<PolicyRevisionResponse>;
  activatePolicy: (revisionId: string) => Promise<PolicyRevisionResponse>;
};

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
  'applyLotReviewIntent',
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

export function createWorkspaceStore() {
  return defineStore('workspace', () => {
    const actionState = reactive(
      Object.fromEntries(actionNames.map((name) => [name, newActionStatus()])) as Record<
        WorkspaceAction,
        ActionStatus
      >,
    );
    const actionSequence = Object.fromEntries(actionNames.map((name) => [name, 0])) as Record<
      WorkspaceAction,
      number
    >;
    const lotFilters = ref<LotQuery>({});
    const activityFilters = ref<ActivityQuery>({});
    const currentRunId = ref<string | null>(null);
    const currentRunSummaryId = ref<string | null>(null);
    const currentRunView = ref<'current' | 'saved' | 'stale' | null>(null);
    const reviewMutationCount = ref(0);
    const reviewMutationPending = computed(() => reviewMutationCount.value > 0);
    const proposedRunIsStale = computed(() => currentRunView.value === 'stale');
    const observedSourceGeneration = ref<number | null>(null);
    const lotReviewIntent = ref<
      { broker_lot_id: string; ticker: string; source_generation: number }[]
    >([]);
    const lotReviewIntentGeneration = ref<number | null>(null);
    const lotReviewIntentDirty = ref(false);
    const lotReviewIntentNotice = ref<string | null>(null);
    const lotReviewIntentConfirmedRunId = ref<string | null>(null);
    let policyMutations: PolicyMutations | null = null;
    let portfolioSyncSequence = 0;

    const workspaceResourceLoadPending = computed(
      () =>
        actionState.loadHealth.pending ||
        actionState.loadPortfolio.pending ||
        actionState.loadPolicy.pending,
    );

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

    const policyEditor = createWorkspacePolicyEditor({
      saveDraft: (payload) =>
        policyMutations
          ? policyMutations.savePolicyDraft(payload)
          : Promise.reject(
              new ApiError('workspace_not_ready', 'Workspace mutations are not initialized'),
            ),
      activateRevision: (revisionId) =>
        policyMutations
          ? policyMutations.activatePolicy(revisionId)
          : Promise.reject(
              new ApiError('workspace_not_ready', 'Workspace mutations are not initialized'),
            ),
    });

    function bindPolicyMutations(mutations: PolicyMutations): void {
      policyMutations = mutations;
    }

    function beginPortfolioSync(): number {
      portfolioSyncSequence += 1;
      return portfolioSyncSequence;
    }

    function isCurrentPortfolioSync(sequence: number): boolean {
      return sequence === portfolioSyncSequence;
    }

    return {
      lotFilters,
      activityFilters,
      currentRunId,
      currentRunSummaryId,
      currentRunView,
      proposedRunIsStale,
      reviewMutationCount,
      reviewMutationPending,
      observedSourceGeneration,
      lotReviewIntent,
      lotReviewIntentGeneration,
      lotReviewIntentDirty,
      lotReviewIntentNotice,
      lotReviewIntentConfirmedRunId,
      policyEditor,
      actionState,
      workspaceResourceLoadPending,
      performWorkspaceAction: perform,
      bindPolicyMutations,
      beginPortfolioSync,
      isCurrentPortfolioSync,
    };
  });
}

export const useWorkspaceStore = createWorkspaceStore();

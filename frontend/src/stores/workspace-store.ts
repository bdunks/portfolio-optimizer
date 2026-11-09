import { computed, reactive, ref } from 'vue';
import { defineStore } from 'pinia';
import type { SyncResponseDTO } from '../types/api';
import { api, ApiError, type ApiClient } from '../services/api';
import { createWorkspacePolicyLifecycle } from './workspace-policy';
import { createWorkspacePolicyEditor } from './workspace-policy-editor';
import { createWorkspaceResources } from './workspace-resources';
import { createWorkspaceReview } from './workspace-review';

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

export function createWorkspaceStore(client: ApiClient = api) {
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
    const lastSync = ref<SyncResponseDTO | null>(null);
    let syncSequence = 0;

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

    const review = createWorkspaceReview(client, perform);
    const resources = createWorkspaceResources(client, perform, {
      observeSourceGeneration: review.observeSourceGeneration,
      observeActivePolicyRevision: review.observeActivePolicyRevision,
    });

    async function refreshWorkspace(): Promise<void> {
      await perform('refreshWorkspace', async () => {
        await Promise.allSettled([
          resources.loadHealth(),
          resources.loadPortfolio(),
          resources.loadPolicy(),
          resources.loadLots(),
          resources.loadWashSales(),
          resources.loadActivity(),
        ]);
      });
    }

    const policyLifecycle = createWorkspacePolicyLifecycle(
      client,
      perform,
      resources,
      refreshWorkspace,
      review.observeActivePolicyRevision,
    );

    const policyEditor = createWorkspacePolicyEditor({
      saveDraft: policyLifecycle.savePolicyDraft,
      activateRevision: policyLifecycle.activatePolicy,
    });

    async function syncPortfolio(): Promise<SyncResponseDTO> {
      const sequence = ++syncSequence;
      return perform('syncPortfolio', async () => {
        const result = await client.syncPortfolio();
        if (sequence === syncSequence) {
          lastSync.value = result;
          review.observeSourceGeneration(result.generation);
          await refreshWorkspace();
        }
        return result;
      });
    }

    return {
      ...resources,
      ...review,
      ...policyLifecycle,
      policyEditor,
      lastSync,
      actionState,

      workspaceResourceLoadPending,
      refreshWorkspace,
      syncPortfolio,
    };
  });
}

export const useWorkspaceStore = createWorkspaceStore();

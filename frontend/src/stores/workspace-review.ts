import { computed, ref, shallowRef } from 'vue';
import type {
  OptimizerRecommendationsResponse,
  OptimizerRunResponse,
  OptimizerSelectionInput,
  RecommendationAnnotationInput,
} from '../types/api';
import type {
  ApiClient,
  ExportDownload,
  ExportFormat,
  RecommendationsOnlyRunInput,
} from '../services/api';
import { ApiError } from '../services/api';
import type { WorkspaceAction } from './workspace-store';

type Perform = <T>(action: WorkspaceAction, operation: () => Promise<T>) => Promise<T>;
type RunView = 'current' | 'saved' | 'stale' | null;
type ReviewMutation = 'recalculateSelection' | 'annotateGroup';

type RunContext = { runId: string; replacementGeneration: number; reviewGeneration: number };

function runSummaryFromRecommendations(
  run: OptimizerRecommendationsResponse,
): OptimizerRunResponse {
  const { groups: _groups, consolidated_legs: _legs, ...summary } = run;
  void _groups;
  void _legs;
  return summary;
}

export function createWorkspaceReview(client: ApiClient, perform: Perform) {
  const currentRun = shallowRef<OptimizerRecommendationsResponse | null>(null);
  const currentRunSummary = shallowRef<OptimizerRunResponse | null>(null);
  const currentRunView = ref<RunView>(null);
  const reviewMutationCount = ref(0);
  const reviewMutationPending = computed(() => reviewMutationCount.value > 0);
  const proposedRunIsStale = computed(() => currentRunView.value === 'stale');

  let replacementGeneration = 0;
  let reviewGeneration = 0;
  let observedSourceGeneration: number | null = null;
  let observedActivePolicyRevision: string | null = null;

  let activePolicyObservationKnown = false;
  let reviewQueue: Promise<void> = Promise.resolve();

  function markCurrentRunStale(): void {
    if (!currentRun.value || currentRunView.value !== 'current') return;
    currentRunView.value = 'stale';
    reviewGeneration += 1;
  }

  function observeSourceGeneration(generation: number): void {
    observedSourceGeneration = generation;
    if (currentRun.value && currentRun.value.source_generation !== generation)
      markCurrentRunStale();
  }

  function observeActivePolicyRevision(revisionId: string | null): void {
    activePolicyObservationKnown = true;
    observedActivePolicyRevision = revisionId;
    if (currentRun.value && currentRun.value.policy_revision_id !== revisionId) {
      markCurrentRunStale();
    }
  }

  function replacementMatchesObservedResources(run: OptimizerRecommendationsResponse): boolean {
    return (
      (observedSourceGeneration === null || run.source_generation === observedSourceGeneration) &&
      (!activePolicyObservationKnown || run.policy_revision_id === observedActivePolicyRevision)
    );
  }

  async function runOptimizer(
    input: RecommendationsOnlyRunInput = {},
  ): Promise<OptimizerRecommendationsResponse> {
    const sequence = ++replacementGeneration;
    reviewGeneration += 1;
    currentRun.value = null;
    currentRunSummary.value = null;
    currentRunView.value = null;
    return perform('runOptimizer', async () => {
      const result = await client.createRun(input);
      if (sequence === replacementGeneration) {
        currentRun.value = result;
        currentRunView.value = replacementMatchesObservedResources(result) ? 'current' : 'stale';
        if (currentRunView.value === 'stale') reviewGeneration += 1;
      }
      return result;
    });
  }

  async function openSavedRun(runId: string): Promise<OptimizerRecommendationsResponse> {
    const sequence = ++replacementGeneration;
    reviewGeneration += 1;
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
      if (sequence === replacementGeneration) {
        currentRunSummary.value = summary;
        currentRun.value = recommendations;
        currentRunView.value = 'saved';
      }
      return recommendations;
    });
  }

  function assertMutationContext(context: RunContext): void {
    if (
      context.replacementGeneration !== replacementGeneration ||
      context.reviewGeneration !== reviewGeneration ||
      currentRun.value?.run_id !== context.runId ||
      currentRunView.value !== 'current'
    ) {
      throw new ApiError(
        'run_context_changed',
        'The run changed before this review update could be confirmed',
      );
    }
  }

  function enqueueReviewMutation(
    action: ReviewMutation,
    runId: string,
    request: () => Promise<OptimizerRecommendationsResponse>,
    apply: (result: OptimizerRecommendationsResponse) => void,
  ): Promise<OptimizerRecommendationsResponse> {
    const context: RunContext = {
      runId,
      replacementGeneration,
      reviewGeneration,
    };
    reviewMutationCount.value += 1;
    const queued = reviewQueue.then(() =>
      perform(action, async () => {
        assertMutationContext(context);
        const result = await request();
        if (result.run_id !== runId) {
          throw new ApiError('run_id_mismatch', 'The API returned a different review run');
        }
        assertMutationContext(context);
        apply(result);
        return result;
      }),
    );
    reviewQueue = queued.then(
      () => undefined,
      () => undefined,
    );
    return queued.finally(() => {
      reviewMutationCount.value -= 1;
    });
  }

  function recalculateSelection(
    selection: OptimizerSelectionInput,
  ): Promise<OptimizerRecommendationsResponse> {
    const runId = currentRun.value?.run_id;
    if (!runId) {
      return Promise.reject(
        new ApiError('no_current_run', 'Open or create a run before changing its selection'),
      );
    }
    const requestBody: OptimizerSelectionInput = {
      selected_group_ids: [...(selection.selected_group_ids ?? [])],
      selected_sell_lots: Object.fromEntries(
        Object.entries(selection.selected_sell_lots ?? {}).map(([groupId, lotIds]) => [
          groupId,
          [...lotIds],
        ]),
      ),
    };
    return enqueueReviewMutation(
      'recalculateSelection',
      runId,
      () => client.recalculateSelection(runId, requestBody),
      (result) => {
        currentRun.value = result;
      },
    );
  }

  function annotateGroup(
    runId: string,
    groupId: string,
    annotation: RecommendationAnnotationInput,
  ): Promise<OptimizerRecommendationsResponse> {
    const requestBody = { ...annotation };
    return enqueueReviewMutation(
      'annotateGroup',
      runId,
      async () => {
        const result = await client.annotateGroup(runId, groupId, requestBody);
        if (!result.groups.some((group) => group.group_id === groupId)) {
          throw new ApiError(
            'recommendation_group_missing',
            'The annotated run did not include the requested recommendation group',
          );
        }
        return result;
      },
      (result) => {
        currentRun.value = result;
        if (currentRunSummary.value?.run_id === runId) {
          currentRunSummary.value = runSummaryFromRecommendations(result);
        }
      },
    );
  }

  function exportRun(runId: string, format: ExportFormat = 'json'): Promise<ExportDownload> {
    return perform('exportRun', () => client.exportRun(runId, format));
  }

  return {
    currentRun,
    currentRunSummary,
    currentRunView,
    proposedRunIsStale,
    reviewMutationPending,
    reviewMutationCount,
    observeSourceGeneration,
    observeActivePolicyRevision,
    runOptimizer,
    openSavedRun,
    recalculateSelection,
    annotateGroup,
    exportRun,
  };
}

import { computed, ref, shallowRef } from 'vue';
import type {
  OptimizerRecommendationsResponse,
  OptimizerLotReviewIntentInput,
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
type ReviewMutation = 'recalculateSelection' | 'annotateGroup' | 'applyLotReviewIntent';

export type LotReviewIntentEntry = {
  broker_lot_id: string;
  ticker: string;
  source_generation: number;
};

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

  const observedSourceGeneration = ref<number | null>(null);
  const lotReviewIntent = ref<LotReviewIntentEntry[]>([]);
  const lotReviewIntentGeneration = ref<number | null>(null);
  const lotReviewIntentDirty = ref(false);
  const lotReviewIntentNotice = ref<string | null>(null);
  const lotReviewIntentConfirmedRunId = ref<string | null>(null);
  let replacementGeneration = 0;
  let reviewGeneration = 0;
  let highestObservedSourceGeneration: number | null = null;
  let observedActivePolicyRevision: string | null = null;

  let activePolicyObservationKnown = false;
  let reviewQueue: Promise<void> = Promise.resolve();

  let lotReviewIntentRevision = 0;
  function markCurrentRunStale(): void {
    if (!currentRun.value || currentRunView.value !== 'current') return;
    currentRunView.value = 'stale';
    reviewGeneration += 1;
  }

  function invalidateLotReviewIntent(message: string): void {
    if (
      lotReviewIntent.value.length === 0 &&
      lotReviewIntentGeneration.value === null &&
      !lotReviewIntentDirty.value
    )
      return;
    lotReviewIntent.value = [];
    lotReviewIntentGeneration.value = null;
    lotReviewIntentConfirmedRunId.value = null;
    lotReviewIntentDirty.value = false;
    lotReviewIntentNotice.value = message;
    lotReviewIntentRevision += 1;
  }

  function observeSourceGeneration(generation: number | null): void {
    if (
      generation !== null &&
      highestObservedSourceGeneration !== null &&
      generation < highestObservedSourceGeneration
    ) {
      return;
    }

    const previousGeneration = observedSourceGeneration.value;
    observedSourceGeneration.value = generation;
    if (generation !== null) {
      highestObservedSourceGeneration = Math.max(
        highestObservedSourceGeneration ?? generation,
        generation,
      );
    }

    if (generation === null) {
      invalidateLotReviewIntent(
        'The current source generation is unavailable. Requested lot intent was cleared; refresh after sync and use a current DEMO run.',
      );
      markCurrentRunStale();
      return;
    }
    if (previousGeneration !== generation) {
      invalidateLotReviewIntent(
        `Source generation changed to ${generation}. Requested lot intent was cleared; review the current lots again.`,
      );
    }
    if (currentRun.value && currentRun.value.source_generation !== generation)
      markCurrentRunStale();
  }

  function observeActivePolicyRevision(revisionId: string | null): void {
    const policyChanged =
      activePolicyObservationKnown && observedActivePolicyRevision !== revisionId;
    activePolicyObservationKnown = true;
    observedActivePolicyRevision = revisionId;
    if (policyChanged) {
      invalidateLotReviewIntent(
        'The active policy changed. Requested lot intent was cleared; use a current DEMO run before applying a basket.',
      );
    }
    if (currentRun.value && currentRun.value.policy_revision_id !== revisionId) {
      invalidateLotReviewIntent(
        'The active policy does not match the loaded DEMO run. Requested lot intent was cleared.',
      );
      markCurrentRunStale();
    }
  }

  function replacementMatchesObservedResources(run: OptimizerRecommendationsResponse): boolean {
    return (
      (observedSourceGeneration.value === null ||
        run.source_generation === observedSourceGeneration.value) &&
      (!activePolicyObservationKnown || run.policy_revision_id === observedActivePolicyRevision)
    );
  }

  function selectedSellBrokerLotIds(run: OptimizerRecommendationsResponse): string[] {
    return run.consolidated_legs.flatMap((leg) =>
      leg.side === 'SELL'
        ? leg.selected_lots.filter((lot) => lot.selected).map((lot) => lot.broker_lot_id)
        : [],
    );
  }

  function hasSameLotIdSet(left: string[], right: string[]): boolean {
    const leftIds = new Set(left);
    const rightIds = new Set(right);
    return (
      leftIds.size === rightIds.size &&
      [...leftIds].every((brokerLotId) => rightIds.has(brokerLotId))
    );
  }

  function reconcileLotReviewIntent(
    run: OptimizerRecommendationsResponse,
    allowConfirmation = true,
  ): void {
    lotReviewIntentConfirmedRunId.value = null;
    const intentGeneration = lotReviewIntentGeneration.value;
    if (intentGeneration === null || intentGeneration !== observedSourceGeneration.value) return;

    const matchesSelectedLots = hasSameLotIdSet(
      lotReviewIntent.value.map((entry) => entry.broker_lot_id),
      selectedSellBrokerLotIds(run),
    );
    if (run.source_generation === intentGeneration && matchesSelectedLots && allowConfirmation) {
      lotReviewIntentConfirmedRunId.value = run.run_id;
      lotReviewIntentDirty.value = false;
      lotReviewIntentNotice.value = null;
      return;
    }

    lotReviewIntentDirty.value = true;
    lotReviewIntentDirty.value = true;
    if (run.source_generation !== intentGeneration) {
      lotReviewIntentNotice.value =
        'The loaded run uses a different source generation. Apply the requested set after opening a current run.';
    } else if (!allowConfirmation && matchesSelectedLots) {
      lotReviewIntentNotice.value =
        'The requested set has not been applied to a current run. Apply it explicitly when a current run is available.';
    } else if (!allowConfirmation) {
      lotReviewIntentNotice.value =
        'The loaded run selects different SELL lots than the requested set. Open a current run and apply the requested set again.';
    } else {
      lotReviewIntentNotice.value =
        'The loaded run selects different SELL lots than the requested set. Apply the requested set again to reconcile it.';
    }
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
        reconcileLotReviewIntent(result, currentRunView.value === 'current');
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
        reconcileLotReviewIntent(recommendations, false);
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
        reconcileLotReviewIntent(result);
      },
    );
  }

  function setLotReviewIntent(
    brokerLotId: string,
    ticker: string,
    generation: number | null,
    selected: boolean,
  ): boolean {
    if (
      generation === null ||
      observedSourceGeneration.value === null ||
      generation !== observedSourceGeneration.value
    ) {
      lotReviewIntentNotice.value =
        'This lot page is not validated against the current source generation. Refresh lots before marking a lot.';
      return false;
    }
    if (
      lotReviewIntentGeneration.value !== null &&
      lotReviewIntentGeneration.value !== generation
    ) {
      invalidateLotReviewIntent(
        'Source generation changed. The previous requested lot set was cleared; review the current lots again.',
      );
    }

    const next = lotReviewIntent.value.filter((entry) => entry.broker_lot_id !== brokerLotId);
    if (selected) {
      next.push({
        broker_lot_id: brokerLotId,
        ticker,
        source_generation: generation,
      });
    }
    lotReviewIntent.value = next;
    lotReviewIntentGeneration.value = generation;
    lotReviewIntentDirty.value = true;
    lotReviewIntentNotice.value = null;
    lotReviewIntentRevision += 1;
    return true;
  }

  function clearLotReviewIntent(): boolean {
    const generation = observedSourceGeneration.value;
    if (generation === null) {
      lotReviewIntentNotice.value =
        'The current source generation is unavailable. Refresh after sync before submitting an empty requested set.';
      return false;
    }
    lotReviewIntent.value = [];
    lotReviewIntentGeneration.value = generation;
    lotReviewIntentDirty.value = true;
    lotReviewIntentNotice.value = null;
    lotReviewIntentRevision += 1;
    return true;
  }

  function applyLotReviewIntent(): Promise<OptimizerRecommendationsResponse> {
    const run = currentRun.value;
    const generation = lotReviewIntentGeneration.value;
    if (!run || currentRunView.value !== 'current') {
      return Promise.reject(
        new ApiError(
          'no_current_run',
          'Create or reopen a current DEMO run before applying the requested lot set',
        ),
      );
    }
    if (
      generation === null ||
      observedSourceGeneration.value === null ||
      generation !== observedSourceGeneration.value ||
      run.source_generation !== generation
    ) {
      return Promise.reject(
        new ApiError(
          'stale_lot_review_intent',
          'The requested lot set does not match the current lot and DEMO run generation',
        ),
      );
    }
    if (!lotReviewIntentDirty.value) {
      return Promise.reject(
        new ApiError(
          'lot_review_intent_unchanged',
          'Change or explicitly clear the requested lot set first',
        ),
      );
    }

    const runId = run.run_id;
    const requestGeneration = generation;
    const intentRevision = lotReviewIntentRevision;
    const requestBody: OptimizerLotReviewIntentInput = {
      source_generation: requestGeneration,
      broker_lot_ids: lotReviewIntent.value.map((entry) => entry.broker_lot_id),
    };
    const mutation = enqueueReviewMutation(
      'applyLotReviewIntent',
      runId,
      () => {
        if (intentRevision !== lotReviewIntentRevision) {
          return Promise.reject(
            new ApiError(
              'lot_review_intent_superseded',
              'The requested lot set changed before submission',
            ),
          );
        }
        return client.applyLotReviewIntent(runId, requestBody);
      },
      (result) => {
        currentRun.value = result;
        reconcileLotReviewIntent(result);
        if (currentRunSummary.value?.run_id === runId) {
          currentRunSummary.value = runSummaryFromRecommendations(result);
        }
      },
    );
    return mutation.catch((error: unknown) => {
      if (error instanceof ApiError && error.code === 'stale_lot_review_intent') {
        invalidateLotReviewIntent(
          `${error.message}. Requested lot intent was cleared; refresh lots and use a current DEMO run.`,
        );
        markCurrentRunStale();
      }
      throw error;
    });
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
        reconcileLotReviewIntent(result);
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
    observedSourceGeneration,
    lotReviewIntent,
    lotReviewIntentGeneration,
    lotReviewIntentDirty,
    lotReviewIntentNotice,
    lotReviewIntentConfirmedRunId,
    observeActivePolicyRevision,
    runOptimizer,
    openSavedRun,
    recalculateSelection,
    setLotReviewIntent,
    clearLotReviewIntent,
    applyLotReviewIntent,
    annotateGroup,
    exportRun,
  };
}

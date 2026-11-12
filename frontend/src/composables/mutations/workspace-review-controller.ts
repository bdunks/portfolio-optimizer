import {
  ApiError,
  type ExportDownload,
  type ExportFormat,
  type RecommendationsOnlyRunInput,
} from '../../services/api';
import type { QueryClient } from '@tanstack/vue-query';
import type {
  OptimizerLotReviewIntentInput,
  OptimizerRecommendationsResponse,
  OptimizerRunResponse,
  OptimizerSelectionInput,
  RecommendationAnnotationInput,
} from '../../types/api';
import type { WorkspaceAction } from '../../stores/workspace-store';
import { workspaceQueryKeys } from '../queries/workspace-queries';

export type LotReviewIntentEntry = {
  broker_lot_id: string;
  ticker: string;
  source_generation: number;
};

type RunView = 'current' | 'saved' | 'stale' | null;
type ReviewMutation = 'recalculateSelection' | 'annotateGroup' | 'applyLotReviewIntent';
type Perform = <T>(action: WorkspaceAction, operation: () => Promise<T>) => Promise<T>;
type RunContext = { runId: string; replacementGeneration: number; reviewGeneration: number };

export type WorkspaceReviewState = {
  currentRunId: string | null;
  currentRunSummaryId: string | null;
  currentRunView: RunView;
  reviewMutationCount: number;
  observedSourceGeneration: number | null;
  lotReviewIntent: LotReviewIntentEntry[];
  lotReviewIntentGeneration: number | null;
  lotReviewIntentDirty: boolean;
  lotReviewIntentNotice: string | null;
  lotReviewIntentConfirmedRunId: string | null;
};

type ControllerOptions = {
  queryClient: QueryClient;
  state: WorkspaceReviewState;
  perform: Perform;
};

export type WorkspaceReviewController = ReturnType<typeof createWorkspaceReviewController>;

function runSummaryFromRecommendations(
  run: OptimizerRecommendationsResponse,
): OptimizerRunResponse {
  const { groups: _groups, consolidated_legs: _legs, ...summary } = run;
  void _groups;
  void _legs;
  return summary;
}

const controllers = new WeakMap<QueryClient, WeakMap<object, WorkspaceReviewController>>();

export function getWorkspaceReviewController(
  options: ControllerOptions & { scope: object },
): WorkspaceReviewController {
  let appControllers = controllers.get(options.queryClient);
  if (!appControllers) {
    appControllers = new WeakMap();
    controllers.set(options.queryClient, appControllers);
  }
  let controller = appControllers.get(options.scope);
  if (!controller) {
    controller = createWorkspaceReviewController(options);
    appControllers.set(options.scope, controller);
  }
  return controller;
}

function createWorkspaceReviewController({ queryClient, state, perform }: ControllerOptions) {
  let replacementGeneration = 0;
  let reviewGeneration = 0;
  let highestObservedSourceGeneration: number | null = null;
  let observedActivePolicyRevision: string | null = null;
  let activePolicyObservationKnown = false;
  let reviewQueue: Promise<void> = Promise.resolve();
  let lotReviewIntentRevision = 0;

  function currentRun(): OptimizerRecommendationsResponse | null {
    return state.currentRunId
      ? (queryClient.getQueryData<OptimizerRecommendationsResponse>(
          workspaceQueryKeys.currentRun(state.currentRunId),
        ) ?? null)
      : null;
  }

  function currentRunSummary(): OptimizerRunResponse | null {
    return state.currentRunSummaryId
      ? (queryClient.getQueryData<OptimizerRunResponse>(
          workspaceQueryKeys.currentRunSummary(state.currentRunSummaryId),
        ) ?? null)
      : null;
  }

  function setCurrentRun(run: OptimizerRecommendationsResponse): void {
    const queryKey = workspaceQueryKeys.currentRun(run.run_id);
    queryClient.setQueryDefaults(queryKey, { gcTime: Infinity });
    queryClient.setQueryData(queryKey, run);
    state.currentRunId = run.run_id;
  }

  function setCurrentRunSummary(summary: OptimizerRunResponse): void {
    const queryKey = workspaceQueryKeys.currentRunSummary(summary.run_id);
    queryClient.setQueryDefaults(queryKey, { gcTime: Infinity });
    queryClient.setQueryData(queryKey, summary);
    state.currentRunSummaryId = summary.run_id;
  }

  function clearCurrentRun(): void {
    state.currentRunId = null;
    state.currentRunSummaryId = null;
    state.currentRunView = null;
  }

  function markCurrentRunStale(): void {
    if (!currentRun() || state.currentRunView !== 'current') return;
    state.currentRunView = 'stale';
    reviewGeneration += 1;
  }

  function invalidateLotReviewIntent(message: string): void {
    if (
      state.lotReviewIntent.length === 0 &&
      state.lotReviewIntentGeneration === null &&
      !state.lotReviewIntentDirty
    )
      return;
    state.lotReviewIntent = [];
    state.lotReviewIntentGeneration = null;
    state.lotReviewIntentConfirmedRunId = null;
    state.lotReviewIntentDirty = false;
    state.lotReviewIntentNotice = message;
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

    const previousGeneration = state.observedSourceGeneration;
    state.observedSourceGeneration = generation;
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
    const run = currentRun();
    if (run && run.source_generation !== generation) markCurrentRunStale();
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
    const run = currentRun();
    if (run && run.policy_revision_id !== revisionId) {
      invalidateLotReviewIntent(
        'The active policy does not match the loaded DEMO run. Requested lot intent was cleared.',
      );
      markCurrentRunStale();
    }
  }

  function replacementMatchesObservedResources(run: OptimizerRecommendationsResponse): boolean {
    return (
      (state.observedSourceGeneration === null ||
        run.source_generation === state.observedSourceGeneration) &&
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
    state.lotReviewIntentConfirmedRunId = null;
    const intentGeneration = state.lotReviewIntentGeneration;
    if (intentGeneration === null || intentGeneration !== state.observedSourceGeneration) return;

    const matchesSelectedLots = hasSameLotIdSet(
      state.lotReviewIntent.map((entry) => entry.broker_lot_id),
      selectedSellBrokerLotIds(run),
    );
    if (run.source_generation === intentGeneration && matchesSelectedLots && allowConfirmation) {
      state.lotReviewIntentConfirmedRunId = run.run_id;
      state.lotReviewIntentDirty = false;
      state.lotReviewIntentNotice = null;
      return;
    }

    state.lotReviewIntentDirty = true;
    if (run.source_generation !== intentGeneration) {
      state.lotReviewIntentNotice =
        'The loaded run uses a different source generation. Apply the requested set after opening a current run.';
    } else if (!allowConfirmation && matchesSelectedLots) {
      state.lotReviewIntentNotice =
        'The requested set has not been applied to a current run. Apply it explicitly when a current run is available.';
    } else if (!allowConfirmation) {
      state.lotReviewIntentNotice =
        'The loaded run selects different SELL lots than the requested set. Open a current run and apply the requested set again.';
    } else {
      state.lotReviewIntentNotice =
        'The loaded run selects different SELL lots than the requested set. Apply the requested set again to reconcile it.';
    }
  }

  function runOptimizer(
    input: RecommendationsOnlyRunInput = {},
    request: (input: RecommendationsOnlyRunInput) => Promise<OptimizerRecommendationsResponse>,
  ): Promise<OptimizerRecommendationsResponse> {
    const sequence = ++replacementGeneration;
    reviewGeneration += 1;
    clearCurrentRun();
    return perform('runOptimizer', async () => {
      const result = await request(input);
      if (sequence === replacementGeneration) {
        setCurrentRun(result);
        state.currentRunView = replacementMatchesObservedResources(result) ? 'current' : 'stale';
        if (state.currentRunView === 'stale') reviewGeneration += 1;
        reconcileLotReviewIntent(result, state.currentRunView === 'current');
      }
      return result;
    });
  }

  function openSavedRun(
    runId: string,
    getSummary: (runId: string) => Promise<OptimizerRunResponse>,
    getRecommendations: (runId: string) => Promise<OptimizerRecommendationsResponse>,
  ): Promise<OptimizerRecommendationsResponse> {
    const sequence = ++replacementGeneration;
    reviewGeneration += 1;
    clearCurrentRun();
    return perform('openSavedRun', async () => {
      const summary = await getSummary(runId);
      if (summary.run_id !== runId) {
        throw new ApiError('run_id_mismatch', 'The API returned a different saved run');
      }
      const recommendations = await getRecommendations(runId);
      if (recommendations.run_id !== runId) {
        throw new ApiError(
          'run_id_mismatch',
          'The API returned recommendations for a different run',
        );
      }
      if (sequence === replacementGeneration) {
        setCurrentRunSummary(summary);
        setCurrentRun(recommendations);
        state.currentRunView = 'saved';
        reconcileLotReviewIntent(recommendations, false);
      }
      return recommendations;
    });
  }

  function assertMutationContext(context: RunContext): void {
    if (
      context.replacementGeneration !== replacementGeneration ||
      context.reviewGeneration !== reviewGeneration ||
      currentRun()?.run_id !== context.runId ||
      state.currentRunView !== 'current'
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
    const context: RunContext = { runId, replacementGeneration, reviewGeneration };
    state.reviewMutationCount += 1;
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
      state.reviewMutationCount -= 1;
    });
  }

  function recalculateSelection(
    selection: OptimizerSelectionInput,
    request: (
      runId: string,
      input: OptimizerSelectionInput,
    ) => Promise<OptimizerRecommendationsResponse>,
  ): Promise<OptimizerRecommendationsResponse> {
    const runId = currentRun()?.run_id;
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
      () => request(runId, requestBody),
      (result) => {
        setCurrentRun(result);
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
      state.observedSourceGeneration === null ||
      generation !== state.observedSourceGeneration
    ) {
      state.lotReviewIntentNotice =
        'This lot page is not validated against the current source generation. Refresh lots before marking a lot.';
      return false;
    }
    if (
      state.lotReviewIntentGeneration !== null &&
      state.lotReviewIntentGeneration !== generation
    ) {
      invalidateLotReviewIntent(
        'Source generation changed. The previous requested lot set was cleared; review the current lots again.',
      );
    }

    const next = state.lotReviewIntent.filter((entry) => entry.broker_lot_id !== brokerLotId);
    if (selected) {
      next.push({ broker_lot_id: brokerLotId, ticker, source_generation: generation });
    }
    state.lotReviewIntent = next;
    state.lotReviewIntentGeneration = generation;
    state.lotReviewIntentDirty = true;
    state.lotReviewIntentNotice = null;
    lotReviewIntentRevision += 1;
    return true;
  }

  function clearLotReviewIntent(): boolean {
    const generation = state.observedSourceGeneration;
    if (generation === null) {
      state.lotReviewIntentNotice =
        'The current source generation is unavailable. Refresh after sync before submitting an empty requested set.';
      return false;
    }
    state.lotReviewIntent = [];
    state.lotReviewIntentGeneration = generation;
    state.lotReviewIntentDirty = true;
    state.lotReviewIntentNotice = null;
    lotReviewIntentRevision += 1;
    return true;
  }

  function applyLotReviewIntent(
    request: (
      runId: string,
      input: OptimizerLotReviewIntentInput,
    ) => Promise<OptimizerRecommendationsResponse>,
  ): Promise<OptimizerRecommendationsResponse> {
    const run = currentRun();
    const generation = state.lotReviewIntentGeneration;
    if (!run || state.currentRunView !== 'current') {
      return Promise.reject(
        new ApiError(
          'no_current_run',
          'Create or reopen a current DEMO run before applying the requested lot set',
        ),
      );
    }
    if (
      generation === null ||
      state.observedSourceGeneration === null ||
      generation !== state.observedSourceGeneration ||
      run.source_generation !== generation
    ) {
      return Promise.reject(
        new ApiError(
          'stale_lot_review_intent',
          'The requested lot set does not match the current lot and DEMO run generation',
        ),
      );
    }
    if (!state.lotReviewIntentDirty) {
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
      broker_lot_ids: state.lotReviewIntent.map((entry) => entry.broker_lot_id),
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
        return request(runId, requestBody);
      },
      (result) => {
        setCurrentRun(result);
        reconcileLotReviewIntent(result);
        if (currentRunSummary()?.run_id === runId) {
          setCurrentRunSummary(runSummaryFromRecommendations(result));
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
    request: (
      runId: string,
      groupId: string,
      input: RecommendationAnnotationInput,
    ) => Promise<OptimizerRecommendationsResponse>,
  ): Promise<OptimizerRecommendationsResponse> {
    const requestBody = { ...annotation };
    return enqueueReviewMutation(
      'annotateGroup',
      runId,
      async () => {
        const result = await request(runId, groupId, requestBody);
        if (!result.groups.some((group) => group.group_id === groupId)) {
          throw new ApiError(
            'recommendation_group_missing',
            'The annotated run did not include the requested recommendation group',
          );
        }
        return result;
      },
      (result) => {
        setCurrentRun(result);
        reconcileLotReviewIntent(result);
        if (currentRunSummary()?.run_id === runId) {
          setCurrentRunSummary(runSummaryFromRecommendations(result));
        }
      },
    );
  }

  function exportRun(
    runId: string,
    format: ExportFormat,
    request: (runId: string, format: ExportFormat) => Promise<ExportDownload>,
  ): Promise<ExportDownload> {
    return perform('exportRun', () => request(runId, format));
  }

  return {
    observeSourceGeneration,
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

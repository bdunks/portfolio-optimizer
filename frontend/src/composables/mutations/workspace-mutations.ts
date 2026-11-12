import { useMutation, type QueryClient } from '@tanstack/vue-query';
import type {
  OptimizerLotReviewIntentInput,
  OptimizerRecommendationsResponse,
  OptimizerRunResponse,
  OptimizerSelectionInput,
  PolicyDraftInput,
  PolicyRevisionResponse,
  RecommendationAnnotationInput,
  SyncResponseDTO,
} from '../../types/api';
import type {
  ApiClient,
  ExportDownload,
  ExportFormat,
  RecommendationsOnlyRunInput,
} from '../../services/api';
import type { WorkspaceAction } from '../../stores/workspace-store';
import type { WorkspaceReviewController } from './workspace-review-controller';
import { workspaceQueryKeys } from '../queries/workspace-queries';

type Perform = <T>(action: WorkspaceAction, operation: () => Promise<T>) => Promise<T>;
type MutationsOptions = {
  client: ApiClient;
  queryClient: QueryClient;
  perform: Perform;
  reviewController: WorkspaceReviewController;
  refreshWorkspace: () => Promise<void>;
  loadPolicy: () => Promise<unknown>;
  observeSourceGeneration: (generation: number | null) => void;
  observeActivePolicyRevision: (revisionId: string | null) => void;
  beginPortfolioSync: () => number;
  isCurrentPortfolioSync: (sequence: number) => boolean;
};

export function createWorkspaceMutations(options: MutationsOptions) {
  const syncPortfolioMutation = useMutation({
    mutationKey: ['workspace', 'syncPortfolio'],
    mutationFn: () => options.client.syncPortfolio(),
    networkMode: 'always',
    retry: false,
  });
  const savePolicyDraftMutation = useMutation({
    mutationKey: ['workspace', 'savePolicyDraft'],
    mutationFn: (payload: PolicyDraftInput) => options.client.savePolicyDraft(payload),
    networkMode: 'always',
    retry: false,
  });
  const activatePolicyMutation = useMutation({
    mutationKey: ['workspace', 'activatePolicy'],
    mutationFn: (revisionId: string) => options.client.activatePolicy(revisionId),
    networkMode: 'always',
    retry: false,
  });
  const createRunMutation = useMutation({
    mutationKey: ['workspace', 'optimizer', 'createRun'],
    mutationFn: (input: RecommendationsOnlyRunInput) => options.client.createRun(input),
    networkMode: 'always',
    retry: false,
  });
  const summaryMutation = useMutation({
    mutationKey: ['workspace', 'optimizer', 'openSavedSummary'],
    mutationFn: (runId: string) => options.client.getRun(runId),
    networkMode: 'always',
    retry: false,
  });
  const recommendationsMutation = useMutation({
    mutationKey: ['workspace', 'optimizer', 'openSavedRecommendations'],
    mutationFn: (runId: string) => options.client.getRecommendations(runId),
    networkMode: 'always',
    retry: false,
  });
  const recalculateSelectionMutation = useMutation({
    mutationKey: ['workspace', 'optimizer', 'recalculateSelection'],
    mutationFn: ({ runId, selection }: { runId: string; selection: OptimizerSelectionInput }) =>
      options.client.recalculateSelection(runId, selection),
    networkMode: 'always',
    retry: false,
  });
  const annotateGroupMutation = useMutation({
    mutationKey: ['workspace', 'optimizer', 'annotateGroup'],
    mutationFn: ({
      runId,
      groupId,
      annotation,
    }: {
      runId: string;
      groupId: string;
      annotation: RecommendationAnnotationInput;
    }) => options.client.annotateGroup(runId, groupId, annotation),
    networkMode: 'always',
    retry: false,
  });
  const applyLotReviewIntentMutation = useMutation({
    mutationKey: ['workspace', 'optimizer', 'applyLotReviewIntent'],
    mutationFn: ({ runId, intent }: { runId: string; intent: OptimizerLotReviewIntentInput }) =>
      options.client.applyLotReviewIntent(runId, intent),
    networkMode: 'always',
    retry: false,
  });
  const exportRunMutation = useMutation({
    mutationKey: ['workspace', 'optimizer', 'exportRun'],
    mutationFn: ({ runId, format }: { runId: string; format: ExportFormat }) =>
      options.client.exportRun(runId, format),
    networkMode: 'always',
    retry: false,
  });

  function syncPortfolio(): Promise<SyncResponseDTO> {
    const sequence = options.beginPortfolioSync();
    return options.perform('syncPortfolio', async () => {
      const result = await syncPortfolioMutation.mutateAsync();
      if (options.isCurrentPortfolioSync(sequence)) {
        options.queryClient.setQueryData(workspaceQueryKeys.lastSync, result);
        options.observeSourceGeneration(result.generation);
        await options.refreshWorkspace();
      }
      return result;
    });
  }

  function savePolicyDraft(payload: PolicyDraftInput): Promise<PolicyRevisionResponse> {
    return options.perform('savePolicyDraft', async () => {
      const result = await savePolicyDraftMutation.mutateAsync(payload);
      // Draft writes do not change the active policy; a failed read does not fail the save.
      await options.loadPolicy().catch(() => undefined);
      return result;
    });
  }

  function activatePolicy(revisionId: string): Promise<PolicyRevisionResponse> {
    return options.perform('activatePolicy', async () => {
      const result = await activatePolicyMutation.mutateAsync(revisionId);
      if (result.status === 'ACTIVE') options.observeActivePolicyRevision(result.id);
      await options.refreshWorkspace();
      await options.queryClient.invalidateQueries({ queryKey: workspaceQueryKeys.all });
      return result;
    });
  }

  function runOptimizer(
    input: RecommendationsOnlyRunInput = {},
  ): Promise<OptimizerRecommendationsResponse> {
    return options.reviewController.runOptimizer(input, (request) =>
      createRunMutation.mutateAsync(request),
    );
  }

  function openSavedRun(runId: string): Promise<OptimizerRecommendationsResponse> {
    return options.reviewController.openSavedRun(
      runId,
      (requestedRunId): Promise<OptimizerRunResponse> =>
        summaryMutation.mutateAsync(requestedRunId),
      (requestedRunId) => recommendationsMutation.mutateAsync(requestedRunId),
    );
  }

  function recalculateSelection(
    selection: OptimizerSelectionInput,
  ): Promise<OptimizerRecommendationsResponse> {
    return options.reviewController.recalculateSelection(selection, (runId, request) =>
      recalculateSelectionMutation.mutateAsync({ runId, selection: request }),
    );
  }

  function annotateGroup(
    runId: string,
    groupId: string,
    annotation: RecommendationAnnotationInput,
  ): Promise<OptimizerRecommendationsResponse> {
    return options.reviewController.annotateGroup(
      runId,
      groupId,
      annotation,
      (id, group, request) =>
        annotateGroupMutation.mutateAsync({ runId: id, groupId: group, annotation: request }),
    );
  }

  function applyLotReviewIntent(): Promise<OptimizerRecommendationsResponse> {
    return options.reviewController.applyLotReviewIntent((runId, intent) =>
      applyLotReviewIntentMutation.mutateAsync({ runId, intent }),
    );
  }

  function exportRun(runId: string, format: ExportFormat = 'json'): Promise<ExportDownload> {
    return options.reviewController.exportRun(runId, format, (id, requestedFormat) =>
      exportRunMutation.mutateAsync({ runId: id, format: requestedFormat }),
    );
  }

  return {
    syncPortfolio,
    savePolicyDraft,
    activatePolicy,
    runOptimizer,
    openSavedRun,
    recalculateSelection,
    annotateGroup,
    applyLotReviewIntent,
    exportRun,
  };
}

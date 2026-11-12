import { proxyRefs, type ShallowUnwrapRef } from 'vue';
import { storeToRefs } from 'pinia';
import { useQueryClient } from '@tanstack/vue-query';
import { api } from '../services/api';
import { useWorkspaceStore } from '../stores/workspace-store';
import { createWorkspaceMutations } from './mutations/workspace-mutations';
import { getWorkspaceReviewController } from './mutations/workspace-review-controller';
import { useWorkspaceQueries } from './queries/workspace-queries';

export type WorkspaceFacade = ReturnType<typeof useWorkspaceStore> &
  ReturnType<typeof useWorkspaceQueries> &
  ReturnType<typeof createWorkspaceMutations> &
  Pick<
    ReturnType<typeof getWorkspaceReviewController>,
    | 'observeSourceGeneration'
    | 'observeActivePolicyRevision'
    | 'setLotReviewIntent'
    | 'clearLotReviewIntent'
  >;

export function useWorkspace(): ShallowUnwrapRef<WorkspaceFacade> {
  const store = useWorkspaceStore();
  const filters = storeToRefs(store);
  const queryClient = useQueryClient();
  const reviewController = getWorkspaceReviewController({
    queryClient,
    scope: store,
    state: store,
    perform: store.performWorkspaceAction,
  });
  const queries = useWorkspaceQueries(
    api,
    store.performWorkspaceAction,
    {
      observeSourceGeneration: reviewController.observeSourceGeneration,
      observeActivePolicyRevision: reviewController.observeActivePolicyRevision,
    },
    {
      lotFilters: filters.lotFilters,
      activityFilters: filters.activityFilters,
      currentRunId: filters.currentRunId,
      currentRunSummaryId: filters.currentRunSummaryId,
    },
  );
  const mutations = createWorkspaceMutations({
    client: api,
    queryClient,
    perform: store.performWorkspaceAction,
    reviewController,
    refreshWorkspace: queries.refreshWorkspace,
    loadPolicy: queries.loadPolicy,
    observeSourceGeneration: reviewController.observeSourceGeneration,
    observeActivePolicyRevision: reviewController.observeActivePolicyRevision,
    beginPortfolioSync: store.beginPortfolioSync,
    isCurrentPortfolioSync: store.isCurrentPortfolioSync,
  });
  store.bindPolicyMutations(mutations);

  const actions = Object.fromEntries(
    Object.entries(store).filter(([, value]) => typeof value === 'function'),
  );
  const facade = proxyRefs({
    ...store,
    ...actions,
    ...storeToRefs(store),
    ...reviewController,
    ...queries,
    ...mutations,
  }) as unknown as ShallowUnwrapRef<WorkspaceFacade>;

  return facade;
}

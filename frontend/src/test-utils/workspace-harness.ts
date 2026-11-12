import { afterEach } from 'vitest';
import { getActivePinia } from 'pinia';
import { defineComponent, h } from 'vue';
import type { VueWrapper } from '@vue/test-utils';
import {
  getTestQueryClient,
  getTestQueryClientForPinia,
  mountWithWorkspace,
} from './workspace-mount';
import { useWorkspace } from '../composables/use-workspace';
import type { OptimizerRecommendationsResponse, OptimizerRunResponse } from '../types/api';
import { workspaceQueryKeys } from '../composables/queries/workspace-queries';

import type { QueryClient } from '@tanstack/vue-query';

type WorkspaceRunSelection = {
  currentRunId: string | null;
  currentRunSummaryId: string | null;
};

const queryClientsByWorkspace = new WeakMap<object, QueryClient>();

function testQueryClient(workspace?: object): QueryClient {
  if (workspace) {
    const queryClient = queryClientsByWorkspace.get(workspace);
    if (queryClient) return queryClient;
  }
  const pinia = getActivePinia();
  if (!pinia) throw new Error('An active Pinia instance is required for workspace run fixtures');
  return getTestQueryClientForPinia(pinia);
}

export function seedCurrentRunForTest(
  workspace: WorkspaceRunSelection,
  run: OptimizerRecommendationsResponse | null,
): void {
  if (run) testQueryClient(workspace).setQueryData(workspaceQueryKeys.currentRun(run.run_id), run);
  workspace.currentRunId = run?.run_id ?? null;
}

export function seedCurrentRunSummaryForTest(
  workspace: WorkspaceRunSelection,
  summary: OptimizerRunResponse | null,
): void {
  if (summary)
    testQueryClient(workspace).setQueryData(
      workspaceQueryKeys.currentRunSummary(summary.run_id),
      summary,
    );
  workspace.currentRunSummaryId = summary?.run_id ?? null;
}

export function currentRunForTest(
  workspace: WorkspaceRunSelection,
): OptimizerRecommendationsResponse | null {
  return workspace.currentRunId
    ? (testQueryClient(workspace).getQueryData(
        workspaceQueryKeys.currentRun(workspace.currentRunId),
      ) ?? null)
    : null;
}

export function currentRunSummaryForTest(
  workspace: WorkspaceRunSelection,
): OptimizerRunResponse | null {
  return workspace.currentRunSummaryId
    ? (testQueryClient(workspace).getQueryData(
        workspaceQueryKeys.currentRunSummary(workspace.currentRunSummaryId),
      ) ?? null)
    : null;
}

const mountedWrappers: VueWrapper[] = [];

afterEach(() => {
  mountedWrappers.splice(0).forEach((wrapper) => wrapper.unmount());
});

export function mountWorkspaceHarness(): {
  workspace: ReturnType<typeof useWorkspace>;
  queryClient: QueryClient;
  wrapper: VueWrapper;
} {
  const pinia = getActivePinia();
  if (!pinia) throw new Error('An active Pinia instance is required for the workspace harness');

  let workspace!: ReturnType<typeof useWorkspace>;
  const host = defineComponent({
    setup() {
      workspace = useWorkspace();
      return () => h('div');
    },
  });
  const wrapper = mountWithWorkspace(host, { global: { plugins: [pinia] } });
  mountedWrappers.push(wrapper);
  const queryClient = getTestQueryClient(wrapper);
  queryClientsByWorkspace.set(workspace, queryClient);
  return { workspace, queryClient, wrapper };
}

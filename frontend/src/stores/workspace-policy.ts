import type { PolicyDraftInput, PolicyRevisionResponse } from '../types/api';
import type { ApiClient } from '../services/api';
import type { WorkspaceAction } from './workspace-store';
import type { createWorkspaceResources } from './workspace-resources';

type Perform = <T>(action: WorkspaceAction, operation: () => Promise<T>) => Promise<T>;
type WorkspaceResources = ReturnType<typeof createWorkspaceResources>;

export function createWorkspacePolicyLifecycle(
  client: ApiClient,
  perform: Perform,
  resources: WorkspaceResources,
  refreshWorkspace: () => Promise<void>,
  observeActivePolicyRevision: (revisionId: string | null) => void,
) {
  function savePolicyDraft(payload: PolicyDraftInput): Promise<PolicyRevisionResponse> {
    return perform('savePolicyDraft', async () => {
      const result = await client.savePolicyDraft(payload);
      // Saving a draft is independent of policy-read success and never invalidates an unchanged active revision.
      await resources.loadPolicy().catch(() => undefined);
      return result;
    });
  }

  function activatePolicy(revisionId: string): Promise<PolicyRevisionResponse> {
    return perform('activatePolicy', async () => {
      const result = await client.activatePolicy(revisionId);
      if (result.status === 'ACTIVE') observeActivePolicyRevision(result.id);
      await refreshWorkspace();
      return result;
    });
  }

  return { savePolicyDraft, activatePolicy };
}

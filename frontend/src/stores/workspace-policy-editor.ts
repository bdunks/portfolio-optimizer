import { computed, onScopeDispose, reactive, watch } from 'vue';
import type { PolicyDraftInput, PolicyResponse, PolicyRevisionResponse } from '../types/api';
import {
  createEmptyPolicyDraft,
  policyDraftSignature,
  policyDraftToPayload,
  revisionToDraft,
  targetActivationIssues,
  type EditablePolicyDraft,
} from '../pages/policy-form';

export type PolicyEditorState = {
  draft: EditablePolicyDraft;
  sourceRevisionId: string | null;
  selectedRevisionId: string | null;
  revisionChoice: string;
  savedRevisionId: string | null;
  lastSavedRevision: PolicyRevisionResponse | null;
  baselineSignature: string;
  pendingRevisionId: string | null;
  pendingSave: boolean;
  pendingActivation: boolean;
  initialized: boolean;
};

type PolicyEditorOperations = {
  saveDraft: (payload: PolicyDraftInput) => Promise<PolicyRevisionResponse>;
  activateRevision: (revisionId: string) => Promise<PolicyRevisionResponse>;
};

export function createWorkspacePolicyEditor(operations: PolicyEditorOperations) {
  const state = reactive<PolicyEditorState>({
    draft: createEmptyPolicyDraft(),
    sourceRevisionId: null,
    selectedRevisionId: null,
    revisionChoice: '',
    savedRevisionId: null,
    lastSavedRevision: null,
    baselineSignature: '',
    pendingRevisionId: null,
    pendingSave: false,
    pendingActivation: false,
    initialized: false,
  });
  const signature = computed(() => policyDraftSignature(state.draft));
  const dirty = computed(() => state.initialized && signature.value !== state.baselineSignature);
  const syntaxIssues = computed(
    () => policyDraftToPayload(state.draft, state.sourceRevisionId).issues,
  );
  const targetIssues = computed(() => targetActivationIssues(state.draft.sleeves));
  const backendIssues = computed(() => state.lastSavedRevision?.activation_errors ?? []);
  const activationIssues = computed(() => [
    ...targetIssues.value,
    ...backendIssues.value.map((issue) => `${issue.code}: ${issue.message}`),
  ]);
  const canActivate = computed(
    () =>
      !dirty.value &&
      !!state.savedRevisionId &&
      activationIssues.value.length === 0 &&
      !state.pendingSave &&
      !state.pendingActivation,
  );

  let sourceEpoch = 0;

  watch(
    () => [state.sourceRevisionId, state.selectedRevisionId],
    () => {
      sourceEpoch += 1;
    },
    { flush: 'sync' },
  );

  function replaceDraft(next: EditablePolicyDraft): void {
    Object.assign(state.draft.settings, next.settings);
    state.draft.sleeves = next.sleeves;
    state.draft.sectorBands = next.sectorBands;
    state.draft.allowedSecurities = next.allowedSecurities;
    state.draft.overrides = next.overrides;
    for (const key of Object.keys(state.draft.reassignments)) delete state.draft.reassignments[key];
    Object.assign(state.draft.reassignments, next.reassignments);
    for (const key of Object.keys(state.draft.reassignmentHoldings))
      delete state.draft.reassignmentHoldings[key];
    Object.assign(state.draft.reassignmentHoldings, next.reassignmentHoldings);
  }

  let editGeneration = 0;
  watch(
    signature,
    () => {
      editGeneration += 1;
    },
    { flush: 'sync' },
  );

  function clearDraft(): void {
    replaceDraft(createEmptyPolicyDraft());
    state.sourceRevisionId = null;
    state.selectedRevisionId = null;
    state.revisionChoice = '';
    state.savedRevisionId = null;
    state.lastSavedRevision = null;
    state.baselineSignature = policyDraftSignature(state.draft);
    state.pendingRevisionId = null;
    state.initialized = true;
  }

  function loadRevision(revision: PolicyRevisionResponse): void {
    replaceDraft(revisionToDraft(revision));
    state.sourceRevisionId = revision.id;
    state.selectedRevisionId = revision.id;
    state.revisionChoice = revision.id;
    state.savedRevisionId = revision.status === 'DRAFT' ? revision.id : null;
    state.lastSavedRevision = revision.status === 'DRAFT' ? revision : null;
    state.baselineSignature = policyDraftSignature(state.draft);
    state.pendingRevisionId = null;
    state.initialized = true;
  }

  function latestByRevisionNumber(revisions: readonly PolicyRevisionResponse[]) {
    return [...revisions].sort(
      (left, right) =>
        right.revision_number - left.revision_number ||
        right.created_at.localeCompare(left.created_at) ||
        right.id.localeCompare(left.id),
    )[0];
  }

  function initializeFromWorkspace(policy: PolicyResponse | null): void {
    if (state.initialized || state.pendingSave || state.pendingActivation) return;
    const preferred =
      latestByRevisionNumber(policy?.drafts ?? []) ??
      policy?.active ??
      latestByRevisionNumber(policy?.superseded ?? []);
    if (preferred) loadRevision(preferred);
    else clearDraft();
  }

  function switchToRevision(
    revisionId: string,
    revisions: readonly PolicyRevisionResponse[],
  ): boolean {
    if (revisionId === '') {
      clearDraft();
      return true;
    }
    const revision = revisions.find((item) => item.id === revisionId);
    if (!revision) return false;
    loadRevision(revision);
    return true;
  }

  function requestRevisionChange(
    revisionId: string,
    revisions: readonly PolicyRevisionResponse[],
  ): 'loaded' | 'confirm' | 'unchanged' | 'blocked' | 'missing' {
    if (state.pendingSave || state.pendingActivation) {
      state.revisionChoice = state.selectedRevisionId ?? '';
      return 'blocked';
    }
    state.revisionChoice = revisionId;
    if (revisionId === (state.selectedRevisionId ?? '')) return 'unchanged';
    if (dirty.value) {
      state.pendingRevisionId = revisionId;
      state.revisionChoice = state.selectedRevisionId ?? '';
      return 'confirm';
    }
    const loaded = switchToRevision(revisionId, revisions);
    if (!loaded) {
      state.revisionChoice = state.selectedRevisionId ?? '';
      return 'missing';
    }
    return 'loaded';
  }

  function cancelRevisionChange(): void {
    if (state.pendingSave || state.pendingActivation) return;
    state.pendingRevisionId = null;
    state.revisionChoice = state.selectedRevisionId ?? '';
  }

  function discardAndLoadRevision(revisions: readonly PolicyRevisionResponse[]): boolean {
    if (state.pendingSave || state.pendingActivation || state.pendingRevisionId === null)
      return false;
    const pendingId = state.pendingRevisionId;
    return switchToRevision(pendingId, revisions);
  }

  function sameOverride(
    left: EditablePolicyDraft['overrides'][number] | undefined,
    right: EditablePolicyDraft['overrides'][number] | undefined,
  ): boolean {
    if (!left || !right) return left === right;
    return (
      left.ticker === right.ticker &&
      left.sleeve_key === right.sleeve_key &&
      (left.sub_sleeve_key ?? null) === (right.sub_sleeve_key ?? null)
    );
  }

  function reconcileSavedOverrides(
    submitted: EditablePolicyDraft['overrides'],
    current: EditablePolicyDraft['overrides'],
    returned: PolicyRevisionResponse['overrides'],
  ) {
    const submittedByTicker = new Map(submitted.map((override) => [override.ticker, override]));
    const currentByTicker = new Map(current.map((override) => [override.ticker, override]));
    const returnedTickers = new Set(returned.map((override) => override.ticker));
    const reconciled = returned.flatMap((serverOverride) => {
      const currentOverride = currentByTicker.get(serverOverride.ticker);
      const submittedOverride = submittedByTicker.get(serverOverride.ticker);
      return sameOverride(currentOverride, submittedOverride)
        ? [{ ...serverOverride }]
        : currentOverride
          ? [{ ...currentOverride }]
          : [];
    });
    for (const currentOverride of current) {
      if (
        !returnedTickers.has(currentOverride.ticker) &&
        !sameOverride(currentOverride, submittedByTicker.get(currentOverride.ticker))
      ) {
        reconciled.push({ ...currentOverride });
      }
    }
    return reconciled;
  }
  function reassignmentOverride(
    ticker: string,
    targetKey: string,
  ): EditablePolicyDraft['overrides'][number] | null {
    const target = state.draft.sleeves.find((sleeve) => sleeve.sleeve_key === targetKey);
    if (!target || target.enabled === false) return null;
    if (!target.parent_sleeve_key)
      return { ticker, sleeve_key: target.sleeve_key, sub_sleeve_key: null };
    const parent = state.draft.sleeves.find(
      (sleeve) => sleeve.sleeve_key === target.parent_sleeve_key,
    );
    if (!parent || parent.enabled === false) return null;
    return { ticker, sleeve_key: parent.sleeve_key, sub_sleeve_key: target.sleeve_key };
  }

  function applyChangedReassignments(
    submitted: EditablePolicyDraft,
    editedOverrideTickers: ReadonlySet<string>,
  ): void {
    for (const [sourceKey, targetKey] of Object.entries(state.draft.reassignments)) {
      if (!targetKey || submitted.reassignments[sourceKey] === targetKey) continue;
      for (const ticker of state.draft.reassignmentHoldings[sourceKey] ?? []) {
        if (
          submitted.overrides.some((override) => override.ticker === ticker) ||
          editedOverrideTickers.has(ticker)
        )
          continue;
        const override = reassignmentOverride(ticker, targetKey);
        if (!override) continue;
        const index = state.draft.overrides.findIndex((item) => item.ticker === ticker);
        if (index < 0) state.draft.overrides.push(override);
        else state.draft.overrides[index] = override;
      }
    }
  }

  function cloneDraft(draft: EditablePolicyDraft): EditablePolicyDraft {
    return JSON.parse(JSON.stringify(draft)) as EditablePolicyDraft;
  }

  async function saveDraft(allowSave = true): Promise<boolean> {
    if (!allowSave || state.pendingSave || state.pendingActivation) return false;
    const converted = policyDraftToPayload(state.draft, state.sourceRevisionId);
    if (!converted.payload) return false;
    const payload = converted.payload;
    const submitted = cloneDraft(state.draft);
    const submittedGeneration = editGeneration;
    const submittedSourceEpoch = sourceEpoch;
    state.pendingSave = true;
    try {
      const revision = await operations.saveDraft(payload);
      if (submittedSourceEpoch !== sourceEpoch) return true;

      const editedAfterSubmit = editGeneration !== submittedGeneration;

      const currentOverrides = state.draft.overrides;
      const submittedOverridesByTicker = new Map(
        submitted.overrides.map((override) => [override.ticker, override]),
      );
      const currentOverridesByTicker = new Map(
        currentOverrides.map((override) => [override.ticker, override]),
      );
      const editedOverrideTickers = new Set(
        [...submittedOverridesByTicker.keys(), ...currentOverridesByTicker.keys()].filter(
          (ticker) =>
            !sameOverride(
              currentOverridesByTicker.get(ticker),
              submittedOverridesByTicker.get(ticker),
            ),
        ),
      );
      state.draft.overrides = reconcileSavedOverrides(
        submitted.overrides,
        currentOverrides,
        revision.overrides,
      );
      applyChangedReassignments(submitted, editedOverrideTickers);
      for (const [key, target] of Object.entries(submitted.reassignments)) {
        if (state.draft.reassignments[key] === target) {
          delete state.draft.reassignments[key];
          delete state.draft.reassignmentHoldings[key];
        }
      }
      for (const key of Object.keys(state.draft.reassignmentHoldings)) {
        if (!state.draft.reassignments[key]) delete state.draft.reassignmentHoldings[key];
      }
      const submittedBaseline = cloneDraft(submitted);
      submittedBaseline.overrides = revision.overrides.map((override) => ({ ...override }));
      submittedBaseline.reassignments = {};
      submittedBaseline.reassignmentHoldings = {};
      const exactSubmittedBaseline = policyDraftSignature(submittedBaseline);
      state.baselineSignature = editedAfterSubmit ? exactSubmittedBaseline : signature.value;
      state.sourceRevisionId = revision.id;
      state.selectedRevisionId = revision.id;
      state.revisionChoice = revision.id;
      state.savedRevisionId = revision.status === 'DRAFT' ? revision.id : null;
      state.lastSavedRevision = revision;
      return true;
    } catch {
      return false;
    } finally {
      state.pendingSave = false;
    }
  }

  async function saveAndLoadRevision(
    revisions: readonly PolicyRevisionResponse[],
    allowSave = true,
  ): Promise<boolean> {
    const pendingId = state.pendingRevisionId;
    if (pendingId === null || !allowSave) return false;
    const didSave = await saveDraft(allowSave);
    if (!didSave || state.pendingRevisionId !== pendingId || dirty.value) return didSave;
    return discardAndLoadRevision(revisions);
  }

  async function activateSaved(): Promise<boolean> {
    if (!canActivate.value || !state.savedRevisionId) return false;
    const revisionId = state.savedRevisionId;
    const activationSourceEpoch = sourceEpoch;
    state.pendingActivation = true;
    try {
      const activated = await operations.activateRevision(revisionId);
      if (activationSourceEpoch !== sourceEpoch || state.savedRevisionId !== revisionId)
        return true;
      state.lastSavedRevision = activated;
      state.savedRevisionId = null;
      state.sourceRevisionId = activated.id;
      state.selectedRevisionId = activated.id;
      state.revisionChoice = activated.id;
      return true;
    } catch {
      return false;
    } finally {
      state.pendingActivation = false;
    }
  }

  const beforeUnload = (event: BeforeUnloadEvent) => {
    if (!dirty.value && !state.pendingSave) return;
    event.preventDefault();
    event.returnValue = '';
  };
  if (typeof window !== 'undefined') {
    window.addEventListener('beforeunload', beforeUnload);
    onScopeDispose(() => window.removeEventListener('beforeunload', beforeUnload));
  }

  return {
    state,
    signature,
    dirty,
    syntaxIssues,
    targetIssues,
    backendIssues,
    activationIssues,
    canActivate,
    initializeFromWorkspace,
    requestRevisionChange,
    cancelRevisionChange,
    discardAndLoadRevision,
    saveDraft,
    saveAndLoadRevision,
    activateSaved,
  };
}

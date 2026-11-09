<template>
  <q-page
    class="workspace-page policy-page"
    :inert="saving || activating"
    :aria-busy="saving || activating"
  >
    <WorkspacePageHeader
      eyebrow="Allocation and tax profile"
      title="Allocation Policy"
      title-id="policy-title"
      subtitle="Configure versioned sleeve targets, replacement ETF candidates, holding overrides, and every persisted tax and batch setting. Target values remain exact decimal strings."
    >
      <template #actions>
        <button type="button" class="secondary-button" :disabled="loading" @click="refreshPolicy">
          {{ loading ? 'Loading…' : 'Refresh policy list' }}
        </button>
        <button type="button" class="primary-button" :disabled="!canSave" @click="saveDraft">
          {{ saving ? 'Saving…' : 'Save new draft revision' }}
        </button>
        <button
          type="button"
          class="secondary-button"
          :disabled="!canActivate"
          @click="activateSaved"
        >
          {{ activating ? 'Activating…' : 'Activate saved revision' }}
        </button>
      </template>
    </WorkspacePageHeader>

    <WorkspaceCapabilityNotice label="Local policy only.">
      This editor makes no broker, OAuth, order-preview, or order submission calls. Tax rates are
      sent in API fraction units (for example, 0.25 means 25%); all money, targets, and percentage
      values are preserved as entered.
    </WorkspaceCapabilityNotice>

    <div class="error-stack" aria-label="Policy request errors">
      <ApiActionError
        :error="store.actionState.loadPolicy.error"
        title="Policy could not be loaded"
      />
      <ApiActionError
        :error="store.actionState.loadPortfolio.error"
        title="Holdings for overrides could not be loaded"
      />
      <ApiActionError
        :error="store.actionState.savePolicyDraft.error"
        title="Policy draft could not be saved"
      />
      <ApiActionError
        :error="store.actionState.activatePolicy.error"
        title="Policy revision could not be activated"
      />
    </div>

    <ResourceFreshnessNotice :resources="['portfolio', 'policy']" />

    <section class="revision-panel" aria-labelledby="revision-title">
      <div class="section-heading">
        <div>
          <h2 id="revision-title">Policy revision</h2>
          <p class="section-subtitle">
            Revisions are immutable after save. Editing a revision always creates a new revision
            from the selected source; unsaved form edits are never replaced by refreshes.
          </p>
        </div>
        <span class="status-badge">{{ revisionStatus }}</span>
      </div>
      <div class="revision-controls">
        <label class="field revision-select">
          <span>Select source revision</span>
          <select
            v-model="revisionChoice"
            :disabled="saving || activating"
            aria-label="Select policy source revision"
            @change="requestRevisionChange"
          >
            <option value="">New policy (no source revision)</option>
            <option v-for="revision in revisions" :key="revision.id" :value="revision.id">
              Revision {{ revision.revision_number }} · {{ revision.status }} · {{ revision.id }}
            </option>
          </select>
        </label>
        <div class="revision-id">
          <span>Source revision ID</span>
          <code>{{ sourceRevisionId ?? 'None — creating the first policy revision' }}</code>
        </div>
        <button type="button" class="text-button" :disabled="loading" @click="refreshPolicy">
          Load latest revisions
        </button>
      </div>
      <div v-if="pendingRevisionId !== null" class="notice-card" role="alert">
        <p>There are unsaved edits. Loading another revision will discard them.</p>
        <div class="button-row">
          <button
            type="button"
            class="primary-button"
            :disabled="!canSave"
            @click="saveAndLoadRevision"
          >
            Save edits and load
          </button>
          <button
            type="button"
            class="secondary-button"
            :disabled="saving || activating"
            @click="cancelRevisionChange"
          >
            Keep editing
          </button>
          <button
            type="button"
            class="danger-button"
            :disabled="saving || activating"
            @click="discardAndLoadRevision"
          >
            Discard edits and load
          </button>
        </div>
      </div>
      <p v-if="dirty" class="state-message" role="status">
        Unsaved changes. This draft stays in memory while the workspace is open; reload would
        discard it. Activation is unavailable until this exact form is saved as a revision.
      </p>
      <p v-else-if="savedRevisionId" class="success-message" role="status">
        Current form matches saved revision {{ savedRevisionId }}. Only this saved content can be
        activated.
      </p>
      <p v-else-if="!loading && initialized" class="state-message">
        Save this configuration to create an immutable revision before activation.
      </p>
    </section>

    <PolicySleevesEditor
      :draft="editorState.draft"
      :positions="portfolio?.positions ?? null"
      :target-issues="targetIssues"
      :source-revision-id="sourceRevisionId"
      @update:sleeves="updateSleeves"
      @update:reassignments="updateReassignments"
    />

    <PolicyReplacementSetsEditor
      :draft="editorState.draft"
      @update:allowed-securities="updateAllowedSecurities"
    />

    <PolicyHoldingOverridesEditor
      :draft="editorState.draft"
      :positions="portfolio?.positions ?? null"
      :portfolio-available="store.portfolio !== null"
      :portfolio-loading="store.actionState.loadPortfolio.pending"
      @update:overrides="updateOverrides"
    />

    <PolicyTaxBatchSettings :settings="settings" @update:settings="updateSettings" />
    <ul
      v-if="formIssues.length"
      class="form-issues"
      role="alert"
      aria-label="Form fields that must be completed before saving"
    >
      <li v-for="issue in formIssues" :key="issue">{{ issue }}</li>
    </ul>

    <section class="activation-panel" aria-labelledby="activation-title">
      <div class="section-heading">
        <div>
          <h2 id="activation-title">Activation validation</h2>
          <p class="section-subtitle">
            Invalid exact target sums may be saved as drafts. Only a saved, unchanged revision can
            be activated; the backend remains authoritative.
          </p>
        </div>
        <span
          :class="['status-badge', activationIssues.length ? 'status-warning' : 'status-ready']"
          >{{ activationIssues.length ? 'Needs attention' : 'Target sums valid' }}</span
        >
      </div>
      <div v-if="activationIssues.length" class="validation-card" role="status">
        <strong>Activation errors for saved revision</strong>
        <ul>
          <li v-for="issue in activationIssues" :key="issue">{{ issue }}</li>
        </ul>
      </div>
      <p v-else class="success-card">
        No target-sum errors are currently reported. Other backend validation can still reject
        activation.
      </p>
      <p v-if="lastSavedRevision?.activation_errors?.length" class="api-errors-label">
        Backend activation_errors for revision {{ lastSavedRevision.id }}:
      </p>
      <ul
        v-if="lastSavedRevision?.activation_errors?.length"
        class="backend-errors"
        aria-label="Backend activation errors"
      >
        <li
          v-for="error in lastSavedRevision.activation_errors"
          :key="`${error.code}:${error.message}`"
        >
          <strong>{{ error.code }}</strong> — {{ error.message }}
        </li>
      </ul>
      <p class="capability-note">
        The accepted policy API persists sleeves, ETF candidate metadata, overrides and the fields
        shown above. It does not expose per-sleeve tracking/exposure tolerances, liquidity limits,
        or ETF-consolidation preference; those controls are not invented here. Portfolio
        look-through suitability is stored only as the API's user-entered text.
      </p>
    </section>
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, toRef } from 'vue';
import type { AllowedSecurityInput, OverrideInput } from '@/types/api';
import ApiActionError from '@/components/ApiActionError.vue';
import WorkspacePageHeader from '@/components/WorkspacePageHeader.vue';
import WorkspaceCapabilityNotice from '@/components/WorkspaceCapabilityNotice.vue';

import ResourceFreshnessNotice from '@/components/ResourceFreshnessNotice.vue';
import PolicyHoldingOverridesEditor from '@/components/PolicyHoldingOverridesEditor.vue';
import PolicyReplacementSetsEditor from '@/components/PolicyReplacementSetsEditor.vue';
import PolicySleevesEditor from '@/components/PolicySleevesEditor.vue';
import PolicyTaxBatchSettings from '@/components/PolicyTaxBatchSettings.vue';
import { useWorkspaceStore } from '@/stores/workspace-store';
import type { EditablePolicyDraft, EditablePolicySettings, EditableSleeve } from './policy-form';

const store = useWorkspaceStore();
const editor = store.policyEditor;
const editorState = editor.state;
const settings = editorState.draft.settings;
const sleeves = computed(() => editorState.draft.sleeves);
const allowedSecurities = computed(() => editorState.draft.allowedSecurities);
const overrides = computed(() => editorState.draft.overrides);
const reassignments = computed(() => editorState.draft.reassignments);
const sourceRevisionId = toRef(editorState, 'sourceRevisionId');
const selectedRevisionId = toRef(editorState, 'selectedRevisionId');
const revisionChoice = toRef(editorState, 'revisionChoice');
const savedRevisionId = toRef(editorState, 'savedRevisionId');
const lastSavedRevision = toRef(editorState, 'lastSavedRevision');
const pendingRevisionId = toRef(editorState, 'pendingRevisionId');
const initialized = toRef(editorState, 'initialized');
const dirty = computed(() => editor.dirty);
const syntaxIssues = computed(() => editor.syntaxIssues);
const targetIssues = computed(() => editor.targetIssues);
const activationIssues = computed(() => editor.activationIssues);
const canActivate = computed(() => editor.canActivate);

const revisions = computed(() => {
  const policy = store.policy;
  if (!policy) return [];
  const all = [...policy.superseded, ...(policy.active ? [policy.active] : []), ...policy.drafts];
  return all
    .filter(
      (revision, index) => all.findIndex((candidate) => candidate.id === revision.id) === index,
    )
    .sort((left, right) => left.revision_number - right.revision_number);
});
const portfolio = computed(() => (store.portfolio?.status === 'ready' ? store.portfolio : null));
const revisionStatus = computed(() => {
  if (lastSavedRevision.value?.status === 'ACTIVE')
    return `ACTIVE · revision ${lastSavedRevision.value.revision_number}`;
  if (savedRevisionId.value)
    return `Saved · revision ${lastSavedRevision.value?.revision_number ?? savedRevisionId.value}`;
  if (sourceRevisionId.value)
    return `Editing source ${selectedRevisionId.value ?? sourceRevisionId.value}`;
  return initialized.value ? 'New unsaved policy' : 'Loading policy';
});
const loading = computed(
  () => store.actionState.loadPolicy.pending || store.actionState.loadPortfolio.pending,
);
const saving = computed(() => editorState.pendingSave);
const activating = computed(() => editorState.pendingActivation);

const formIssues = computed(() => {
  const issues: string[] = [...syntaxIssues.value];
  if (sleeves.value.some((sleeve) => !sleeve.sleeve_key.trim() || !sleeve.display_name.trim()))
    issues.push('Each sleeve needs a key and display name before saving.');
  if (!unique(sleeves.value.map((sleeve) => sleeve.sleeve_key.trim())))
    issues.push('Sleeve keys must be unique.');
  if (
    sleeves.value.some(
      (sleeve) =>
        sleeve.parent_sleeve_key &&
        !sleeves.value.some((candidate) => candidate.sleeve_key === sleeve.parent_sleeve_key),
    )
  )
    issues.push('Every nested sleeve must reference a sleeve in this draft.');
  if (
    allowedSecurities.value.some(
      (security) =>
        !security.ticker.trim() ||
        !security.sleeve_key.trim() ||
        !security.replacement_set_id?.trim(),
    )
  )
    issues.push(
      'Each ETF candidate needs a ticker, parent sleeve, and replacement-set ID before saving.',
    );
  if (allowedSecurities.value.some((security) => !Number.isSafeInteger(security.priority)))
    issues.push('ETF candidate priorities must be whole numbers.');
  if (
    allowedSecurities.value.some(
      (security) =>
        security.sub_sleeve_key &&
        !sleeves.value.some(
          (sleeve) =>
            sleeve.sleeve_key === security.sub_sleeve_key &&
            sleeve.parent_sleeve_key === security.sleeve_key,
        ),
    )
  )
    issues.push('Each ETF sub-sleeve must be a direct child of its selected parent sleeve.');
  if (overrides.value.some((override) => !override.ticker.trim() || !override.sleeve_key.trim()))
    issues.push('Each explicit holding override needs a ticker and destination sleeve.');
  if (
    overrides.value.some((override) => {
      const destination = sleeves.value.find(
        (sleeve) => sleeve.sleeve_key === (override.sub_sleeve_key ?? override.sleeve_key),
      );
      return (
        !destination ||
        destination.enabled === false ||
        (override.sub_sleeve_key && destination.parent_sleeve_key !== override.sleeve_key)
      );
    })
  )
    issues.push(
      'Explicit overrides must target an enabled sleeve ' +
        '(and any sub-sleeve must be its direct child).',
    );
  for (const sleeve of sleeves.value.filter((item) => item.enabled === false)) {
    if (
      heldInSleeve(sleeve.sleeve_key).some(
        (holding) => !overrides.value.some((override) => override.ticker === holding.ticker),
      ) &&
      !reassignments.value[sleeve.sleeve_key]
    )
      issues.push(
        'Choose a holding reassignment for disabled sleeve “' +
          `${sleeve.display_name || sleeve.sleeve_key}”.`,
      );
  }
  return [...new Set(issues)];
});
const canSave = computed(
  () => initialized.value && formIssues.value.length === 0 && !saving.value && !activating.value,
);

function updateSleeves(sleeves: EditableSleeve[]): void {
  editorState.draft.sleeves = sleeves;
}

function updateAllowedSecurities(securities: AllowedSecurityInput[]): void {
  editorState.draft.allowedSecurities = securities;
}

function updateOverrides(overrides: OverrideInput[]): void {
  editorState.draft.overrides = overrides;
}

function updateReassignments(
  reassignments: EditablePolicyDraft['reassignments'],
  reassignmentHoldings: EditablePolicyDraft['reassignmentHoldings'],
): void {
  editorState.draft.reassignments = reassignments;
  editorState.draft.reassignmentHoldings = reassignmentHoldings;
}

function updateSettings(settings: EditablePolicySettings): void {
  Object.assign(editorState.draft.settings, settings);
}

function unique(values: string[]): boolean {
  return new Set(values).size === values.length;
}

function initializeFromWorkspace(): void {
  editor.initializeFromWorkspace(store.policy);
}

async function loadInitial(): Promise<void> {
  await store.ensureInitialWorkspace();
  initializeFromWorkspace();
}

async function refreshPolicy(): Promise<void> {
  await store.loadPolicy().catch(() => undefined);
  // Refresh only the revision list; the controller deliberately retains the in-memory form.
}

function requestRevisionChange(): void {
  editor.requestRevisionChange(revisionChoice.value, revisions.value);
}

function cancelRevisionChange(): void {
  editor.cancelRevisionChange();
}

function discardAndLoadRevision(): void {
  editor.discardAndLoadRevision(revisions.value);
}

async function saveDraft(): Promise<void> {
  if (canSave.value) await editor.saveDraft(canSave.value);
}

async function saveAndLoadRevision(): Promise<void> {
  await editor.saveAndLoadRevision(revisions.value, canSave.value);
}

async function activateSaved(): Promise<void> {
  await editor.activateSaved();
}
function heldInSleeve(key: string): Array<{ ticker: string }> {
  return (
    portfolio.value?.positions.filter(
      (position) => position.sleeve_key === key || position.sub_sleeve_key === key,
    ) ?? []
  );
}

onMounted(() => {
  void loadInitial();
});
</script>

<style scoped src="../components/policy-editor-sections.css"></style>

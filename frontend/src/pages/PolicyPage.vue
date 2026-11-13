<template>
  <section
    class="workspace-page policy-page tw:mx-auto tw:w-full tw:max-w-[1800px] tw:px-4 tw:py-4"
    aria-labelledby="policy-title"
    :inert="saving || activating"
    :aria-busy="saving || activating"
  >
    <WorkspacePageHeader
      eyebrow="Allocation and tax profile"
      title="Allocation Policy"
      title-id="policy-title"
      subtitle="Configure versioned sleeve targets, replacement-set securities, holding overrides, and every persisted tax and batch setting. Target values remain exact decimal strings."
    >
      <template #actions>
        <Button
          type="button"
          variant="outline"
          size="sm"
          :disabled="loading"
          @click="refreshPolicy"
        >
          {{ loading ? 'Loading…' : 'Refresh policy list' }}
        </Button>
        <Button
          type="button"
          variant="default"
          size="sm"
          class="primary-button"
          :disabled="!canSave"
          @click="saveDraft"
        >
          {{ saving ? 'Saving…' : 'Save new draft revision' }}
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          :disabled="!canActivate"
          @click="activateSaved"
        >
          {{ activating ? 'Activating…' : 'Activate saved revision' }}
        </Button>
      </template>
    </WorkspacePageHeader>

    <WorkspaceCapabilityNotice label="Local policy only.">
      This editor makes no broker, OAuth, order-preview, or order submission calls. Tax rates are
      sent in API fraction units (for example, 0.25 means 25%); all money, targets, and percentage
      values are preserved as entered.
    </WorkspaceCapabilityNotice>

    <div class="tw:grid tw:gap-2" aria-label="Policy request errors">
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
      <Card>
        <CardHeader
          class="tw:gap-3 tw:md:flex tw:md:flex-row tw:md:items-start tw:md:justify-between"
        >
          <div class="tw:space-y-2">
            <h2 id="revision-title" class="tw:m-0! tw:text-lg tw:font-semibold tw:leading-tight">
              Policy revision
            </h2>
            <p class="tw:m-0! tw:max-w-prose tw:text-sm tw:text-muted-foreground">
              Revisions are immutable after save. Editing a revision always creates a new revision
              from the selected source; unsaved form edits are never replaced by refreshes.
            </p>
          </div>
          <Badge as="span" variant="secondary" role="status">{{ revisionStatus }}</Badge>
        </CardHeader>
        <CardContent class="tw:grid tw:gap-4">
          <div class="tw:grid tw:items-end tw:gap-4 tw:md:grid-cols-[minmax(0,1fr)_auto_auto]">
            <revisionForm.Field name="revisionId">
              <template #default="{ field }">
                <Field class="tw:max-w-xl">
                  <FieldLabel for="policy-revision-select">Select source revision</FieldLabel>
                  <Select
                    :model-value="revisionSelectValue"
                    :disabled="saving || activating"
                    @update:model-value="handleRevisionSelection"
                  >
                    <SelectTrigger
                      id="policy-revision-select"
                      aria-label="Select policy source revision"
                      :aria-invalid="field.state.meta.errors.length ? 'true' : undefined"
                      :aria-describedby="
                        field.state.meta.errors.length ? 'policy-revision-select-error' : undefined
                      "
                    >
                      <SelectValue placeholder="Select a policy revision" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectGroup>
                        <SelectItem :value="NEW_POLICY_SELECT_VALUE">
                          New policy (no source revision)
                        </SelectItem>
                        <SelectItem
                          v-for="revision in revisions"
                          :key="revision.id"
                          :value="revision.id"
                        >
                          Revision {{ revision.revision_number }} · {{ revision.status }} ·
                          {{ revision.id }}
                        </SelectItem>
                      </SelectGroup>
                    </SelectContent>
                  </Select>
                  <FieldError
                    v-if="field.state.meta.errors.length"
                    id="policy-revision-select-error"
                    :errors="field.state.meta.errors"
                  />
                </Field>
              </template>
            </revisionForm.Field>
            <div class="tw:grid tw:gap-1">
              <span class="tw:text-sm tw:font-medium">Source revision ID</span>
              <code class="tw:break-all tw:text-sm">{{
                sourceRevisionId ?? 'None — creating the first policy revision'
              }}</code>
            </div>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              :disabled="loading"
              @click="refreshPolicy"
            >
              Load latest revisions
            </Button>
          </div>

          <Alert
            v-if="pendingRevisionId !== null"
            role="alert"
            class="tw:border-amber-300 tw:bg-amber-50 tw:text-amber-950"
          >
            <AlertDescription class="tw:text-current">
              <p class="tw:m-0!">
                There are unsaved edits. Loading another revision will discard them.
              </p>
            </AlertDescription>
            <div class="tw:flex tw:flex-wrap tw:items-center tw:gap-2">
              <Button
                type="button"
                variant="default"
                size="sm"
                class="primary-button"
                :disabled="!canSave"
                @click="saveAndLoadRevision"
              >
                Save edits and load
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                :disabled="saving || activating"
                @click="cancelRevisionChange"
              >
                Keep editing
              </Button>
              <Button
                type="button"
                variant="destructive"
                size="sm"
                :disabled="saving || activating"
                @click="discardAndLoadRevision"
              >
                Discard edits and load
              </Button>
            </div>
          </Alert>
          <Alert v-if="dirty" role="status" class="tw:border-sky-200 tw:bg-sky-50">
            <AlertDescription>
              Unsaved changes. This draft stays in memory while the workspace is open; reload would
              discard it. Activation is unavailable until this exact form is saved as a revision.
            </AlertDescription>
          </Alert>
          <Alert
            v-else-if="savedRevisionId"
            role="status"
            class="tw:border-emerald-200 tw:bg-emerald-50"
          >
            <AlertDescription>
              Current form matches saved revision {{ savedRevisionId }}. Only this saved content can
              be activated.
            </AlertDescription>
          </Alert>
          <p
            v-else-if="!loading && initialized"
            class="tw:m-0! tw:text-sm tw:text-muted-foreground"
          >
            Save this configuration to create an immutable revision before activation.
          </p>
        </CardContent>
      </Card>
    </section>

    <PolicyUSTransitionSettings
      :draft="editorState.draft"
      @update:sleeves="updateSleeves"
      @open-replacements="openUSReplacements"
    />

    <PolicySleevesEditor
      :draft="editorState.draft"
      :positions="portfolio?.positions ?? null"
      :target-issues="targetIssues"
      :source-revision-id="sourceRevisionId"
      @update:sleeves="updateSleeves"
      @update:reassignments="updateReassignments"
      @open-replacements="openSleeveReplacements"
    />

    <section
      class="tw:flex tw:flex-col tw:gap-2 tw:rounded-md tw:border tw:p-4 tw:md:flex-row tw:md:items-center tw:md:justify-between"
    >
      <div class="tw:space-y-1">
        <h2 class="tw:m-0! tw:text-base tw:font-semibold">Replacement sets</h2>
        <p class="tw:m-0! tw:text-sm tw:text-muted-foreground">
          Open all configured candidates to reach custom, disabled, unassigned, or otherwise
          unavailable assignments.
        </p>
      </div>
      <Button
        type="button"
        variant="outline"
        size="sm"
        data-all-replacement-sets-trigger
        @click="openAllReplacementSets"
      >
        All configured replacement sets
      </Button>
    </section>

    <Sheet v-model:open="replacementEditorOpen">
      <SheetContent
        side="right"
        class="tw:w-full tw:max-w-[96vw] tw:gap-4 tw:overflow-y-auto tw:sm:max-w-[96vw]"
        @close-auto-focus="restoreReplacementFocus"
      >
        <SheetHeader class="tw:sr-only">
          <SheetTitle>
            {{
              replacementContext
                ? `Replacement sets for ${replacementContext.label}`
                : 'All configured replacement sets'
            }}
          </SheetTitle>
          <SheetDescription>
            Edit the current policy draft's replacement-set securities. Other configured candidates
            remain unchanged.
          </SheetDescription>
        </SheetHeader>
        <PolicyReplacementSetsEditor
          :draft="editorState.draft"
          :context="replacementContext"
          @update:allowed-securities="updateAllowedSecurities"
        />
      </SheetContent>
    </Sheet>
    <PolicyHoldingOverridesEditor
      :draft="editorState.draft"
      :positions="portfolio?.positions ?? null"
      :portfolio-available="store.portfolio !== null"
      :portfolio-loading="store.actionState.loadPortfolio.pending"
      @update:overrides="updateOverrides"
    />

    <PolicyTaxBatchSettings
      :settings="settings"
      :source-revision-id="sourceRevisionId"
      @update:settings="updateSettings"
    />

    <Alert
      v-if="formIssues.length"
      role="alert"
      aria-label="Form fields that must be completed before saving"
      variant="destructive"
    >
      <AlertDescription>
        <ul class="tw:list-disc tw:pl-5">
          <li v-for="issue in formIssues" :key="issue">{{ issue }}</li>
        </ul>
      </AlertDescription>
    </Alert>

    <section class="activation-panel" aria-labelledby="activation-title">
      <Card>
        <CardHeader
          class="tw:gap-3 tw:md:flex tw:md:flex-row tw:md:items-start tw:md:justify-between"
        >
          <div class="tw:space-y-2">
            <h2 id="activation-title" class="tw:m-0! tw:text-lg tw:font-semibold tw:leading-tight">
              Activation validation
            </h2>
            <p class="tw:m-0! tw:max-w-prose tw:text-sm tw:text-muted-foreground">
              Invalid exact target sums may be saved as drafts. Only a saved, unchanged revision can
              be activated; the backend remains authoritative.
            </p>
          </div>
          <Badge
            as="span"
            :variant="activationIssues.length ? 'destructive' : 'secondary'"
            role="status"
          >
            {{ activationIssues.length ? 'Needs attention' : 'Target sums valid' }}
          </Badge>
        </CardHeader>
        <CardContent class="tw:grid tw:gap-4">
          <Alert
            v-if="activationIssues.length"
            role="status"
            class="tw:border-amber-300 tw:bg-amber-50"
          >
            <AlertDescription class="tw:text-amber-950">
              <strong>Activation errors for saved revision</strong>
              <ul class="tw:mt-2 tw:list-disc tw:pl-5">
                <li v-for="issue in activationIssues" :key="issue">{{ issue }}</li>
              </ul>
            </AlertDescription>
          </Alert>
          <p
            v-else
            class="tw:m-0! tw:rounded-lg tw:border tw:border-emerald-200 tw:bg-emerald-50 tw:p-4 tw:text-sm"
          >
            No target-sum errors are currently reported. Other backend validation can still reject
            activation.
          </p>
          <template v-if="lastSavedRevision?.activation_errors?.length">
            <p class="tw:m-0! tw:text-sm tw:font-medium">
              Backend activation_errors for revision {{ lastSavedRevision.id }}:
            </p>
            <ul aria-label="Backend activation errors" class="tw:list-disc tw:space-y-1 tw:pl-5">
              <li
                v-for="error in lastSavedRevision.activation_errors"
                :key="`${error.code}:${error.message}`"
              >
                <strong>{{ error.code }}</strong> — {{ error.message }}
              </li>
            </ul>
          </template>
          <p class="tw:m-0! tw:border-t tw:pt-4 tw:text-sm tw:text-muted-foreground">
            The accepted policy API persists sleeves, replacement-set security metadata, overrides
            and the fields shown above. It does not expose per-sleeve tracking/exposure tolerances,
            liquidity limits, or ETF-consolidation preference; those controls are not invented here.
            Portfolio look-through suitability is stored only as the API's user-entered text.
          </p>
        </CardContent>
      </Card>
    </section>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref, toRef, watch } from 'vue';
import { useForm } from '@tanstack/vue-form';
import type { AllowedSecurityInput, OverrideInput } from '@/types/api';
import ApiActionError from '@/components/ApiActionError.vue';
import WorkspacePageHeader from '@/components/WorkspacePageHeader.vue';
import WorkspaceCapabilityNotice from '@/components/WorkspaceCapabilityNotice.vue';

import ResourceFreshnessNotice from '@/components/ResourceFreshnessNotice.vue';
import PolicyHoldingOverridesEditor from '@/components/PolicyHoldingOverridesEditor.vue';
import PolicyReplacementSetsEditor from '@/components/PolicyReplacementSetsEditor.vue';
import PolicyUSTransitionSettings from '@/components/PolicyUSTransitionSettings.vue';
import PolicySleevesEditor from '@/components/PolicySleevesEditor.vue';
import PolicyTaxBatchSettings from '@/components/PolicyTaxBatchSettings.vue';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { Field, FieldError, FieldLabel } from '@/components/ui/field';
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { useWorkspace } from '@/composables/use-workspace';
import type { EditablePolicyDraft, EditablePolicySettings, EditableSleeve } from './policy-form';
import {
  createPolicyRevisionSelectionSchema,
  type PolicyRevisionFormValues,
} from '@/forms/policy-revision';

type ReplacementSetsContext = {
  sleeveKey: string;
  label: string;
  requireSubSleeve?: boolean;
  newSubSleeveKey?: string;
};

const store = useWorkspace();
const editor = store.policyEditor;
const editorState = editor.state;
const settings = editorState.draft.settings;
const sleeves = computed(() => editorState.draft.sleeves);
const allowedSecurities = computed(() => editorState.draft.allowedSecurities);
const replacementEditorOpen = ref(false);
const replacementContext = ref<ReplacementSetsContext | null>(null);
const replacementTrigger = ref<HTMLElement | null>(null);
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
const NEW_POLICY_SELECT_VALUE = '__new_policy__';
const revisionSelectionSchema = createPolicyRevisionSelectionSchema(() =>
  revisions.value.map((revision) => revision.id),
);
const revisionForm = useForm({
  defaultValues: { revisionId: revisionChoice.value } satisfies PolicyRevisionFormValues,
  validators: { onChange: revisionSelectionSchema },
});
const revisionFormValues = revisionForm.useSelector((state) => state.values);
const revisionSelectValue = computed(() =>
  revisionFormValues.value.revisionId === ''
    ? NEW_POLICY_SELECT_VALUE
    : revisionFormValues.value.revisionId,
);

watch(revisionChoice, (revisionId) => revisionForm.reset({ revisionId }), { flush: 'sync' });
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
      'Each replacement-set security needs a ticker, parent sleeve, and replacement-set ID before saving.',
    );
  if (allowedSecurities.value.some((security) => !Number.isSafeInteger(security.priority)))
    issues.push('Replacement-set security priorities must be whole numbers.');
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
    issues.push(
      'Each replacement-set security sub-sleeve must be a direct child of its selected parent sleeve.',
    );
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

function openAllReplacementSets(event: MouseEvent): void {
  replacementContext.value = null;
  replacementTrigger.value = event.currentTarget as HTMLElement;
  replacementEditorOpen.value = true;
}

function openSleeveReplacements(sleeveKey: string, trigger: HTMLElement): void {
  const sleeve = sleeves.value.find((item) => item.sleeve_key === sleeveKey);
  if (!sleeve) return;
  const destinations = sleeves.value.filter((item) => item.is_transition_destination === true);
  const newDestination =
    destinations.length === 1 && destinations[0]?.parent_sleeve_key === sleeveKey
      ? destinations[0].sleeve_key
      : undefined;
  replacementContext.value = {
    sleeveKey,
    label: sleeve.display_name.trim() || sleeve.sleeve_key,
    ...(sleeve.is_direct_index_container === true ? { requireSubSleeve: true } : {}),
    ...(newDestination ? { newSubSleeveKey: newDestination } : {}),
  };
  replacementTrigger.value = trigger;
  replacementEditorOpen.value = true;
}

function openUSReplacements(
  sleeveKey: string,
  newSubSleeveKey: string | null,
  trigger: HTMLElement,
): void {
  const sleeve = sleeves.value.find((item) => item.sleeve_key === sleeveKey);
  if (!sleeve) return;
  const destination = newSubSleeveKey
    ? sleeves.value.find((item) => item.sleeve_key === newSubSleeveKey)
    : undefined;
  replacementContext.value = {
    sleeveKey,
    label: `${sleeve.display_name.trim() || sleeve.sleeve_key} (US allocation)`,
    requireSubSleeve: true,
    ...(newSubSleeveKey && destination?.parent_sleeve_key === sleeveKey ? { newSubSleeveKey } : {}),
  };
  replacementTrigger.value = trigger;
  replacementEditorOpen.value = true;
}

function restoreReplacementFocus(event: Event): void {
  event.preventDefault();
  void nextTick(() => {
    if (replacementTrigger.value?.isConnected) replacementTrigger.value.focus();
    else document.querySelector<HTMLButtonElement>('[data-all-replacement-sets-trigger]')?.focus();
  });
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

function requestRevisionChange(value: string): void {
  editor.requestRevisionChange(value, revisions.value);
}

function handleRevisionSelection(value: unknown): void {
  if (typeof value !== 'string') return;
  const revisionId = value === NEW_POLICY_SELECT_VALUE ? '' : value;
  revisionForm.setFieldValue('revisionId', revisionId);
  if (!revisionSelectionSchema.safeParse({ revisionId }).success) return;
  requestRevisionChange(revisionId);
  revisionForm.reset({ revisionId: revisionChoice.value });
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

<style scoped>
.policy-page :deep(.page-actions) {
  flex-wrap: wrap;
}

.policy-page > .revision-panel h2,
.policy-page > .activation-panel h2 {
  color: var(--foreground);
  font-size: 1.125rem;
  font-weight: 600;
  line-height: 1.25;
}
</style>

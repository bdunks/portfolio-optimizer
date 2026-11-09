<template>
  <section class="target-panel" :aria-labelledby="`${sectionId}-title`">
    <div class="section-heading">
      <div>
        <h2 :id="`${sectionId}-title`">Sleeves and allocation targets</h2>
        <p class="section-subtitle">
          Top-level targets and every populated nested allocation must total exactly 100%. Drift
          bands use percentage points. No tolerance, implicit cash sleeve, or normalization is
          applied. Transition progress uses an explicitly designated destination sub-sleeve and all
          descendants regardless of security type; it remains unavailable when no destination is
          configured.
        </p>
      </div>
      <button type="button" class="secondary-button" @click="addSleeve">+ Add sleeve</button>
    </div>
    <div v-if="targetIssues.length" class="validation-card" role="status" aria-live="polite">
      <strong>Target check — activation is not valid yet</strong>
      <ul>
        <li v-for="issue in targetIssues" :key="issue">{{ issue }}</li>
      </ul>
      <p>These client-side checks are guidance only; the backend response is authoritative.</p>
    </div>
    <div v-else class="success-card" role="status">
      Enabled top-level and nested target sums are exactly 100%.
    </div>
    <p v-if="deleteError && !pendingDeleteSleeve" class="inline-error" role="alert">
      {{ deleteError }}
    </p>
    <WorkspaceTableFrame class="table-scroll" label="Sleeve allocation policy settings">
      <table class="editor-table sleeves-table">
        <thead>
          <tr>
            <th>Order / sleeve key</th>
            <th>Name</th>
            <th>Parent</th>
            <th>Target (%)</th>
            <th>Drift band (pp)</th>
            <th>Designations</th>
            <th>Enabled</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="(sleeve, index) in sleeves"
            :key="`${sleeve.sleeve_key}-${index}`"
            :class="{ 'disabled-row': !sleeve.enabled }"
          >
            <td>
              <div class="order-tools">
                <button
                  type="button"
                  class="icon-button"
                  :aria-label="`Move ${sleeve.display_name || 'sleeve'} up`"
                  :disabled="!canMoveSleeve(index, -1)"
                  @click="moveSleeve(index, -1)"
                >
                  ↑
                </button>
                <button
                  type="button"
                  class="icon-button"
                  :aria-label="`Move ${sleeve.display_name || 'sleeve'} down`"
                  :disabled="!canMoveSleeve(index, 1)"
                  @click="moveSleeve(index, 1)"
                >
                  ↓
                </button>
              </div>
              <code class="sleeve-key">{{ sleeve.sleeve_key || 'new sleeve' }}</code>
            </td>
            <td>
              <label class="compact-field"
                ><span class="sr-only">Sleeve name</span
                ><input
                  :value="sleeve.display_name"
                  @input="setSleeveText(sleeve.sleeve_key, 'display_name', $event)"
                  aria-label="Sleeve display name"
                  placeholder="Display name"
              /></label>
            </td>
            <td>
              <label class="compact-field"
                ><span class="sr-only">Parent sleeve</span>
                <select
                  :value="sleeve.parent_sleeve_key"
                  aria-label="Parent sleeve"
                  @change="setSleeveParent(sleeve.sleeve_key, $event)"
                >
                  <option :value="null">Top level</option>
                  <option
                    v-for="parent in parentOptions(sleeve)"
                    :key="parent.sleeve_key"
                    :value="parent.sleeve_key"
                  >
                    {{ parent.display_name || parent.sleeve_key }}
                  </option>
                </select>
              </label>
            </td>
            <td>
              <label class="compact-field target-input"
                ><span class="sr-only">Target percent</span
                ><input
                  :value="sleeve.target_pct"
                  @input="setSleeveText(sleeve.sleeve_key, 'target_pct', $event)"
                  inputmode="decimal"
                  aria-label="Target percent"
                  placeholder="0"
              /></label>
            </td>
            <td>
              <label class="compact-field target-input"
                ><span class="sr-only">Drift band percentage points</span
                ><input
                  :value="sleeve.drift_band_pp"
                  @input="setSleeveText(sleeve.sleeve_key, 'drift_band_pp', $event)"
                  inputmode="decimal"
                  aria-label="Drift band in percentage points"
                  placeholder="0"
              /></label>
            </td>
            <td class="designation-cell">
              <label
                ><input
                  type="checkbox"
                  :checked="sleeve.is_direct_index_container"
                  @change="setDirectIndexContainer(sleeve.sleeve_key, $event)"
                />
                Direct-index container</label
              >
              <label
                ><input
                  :checked="sleeve.is_direct_index_sleeve"
                  type="checkbox"
                  @change="setSleeveRole(sleeve.sleeve_key, 'is_direct_index_sleeve', $event)"
                />
                Direct-index sleeve</label
              >
              <label
                ><input
                  type="checkbox"
                  aria-label="Transition destination sub-sleeve"
                  :checked="sleeve.is_transition_destination"
                  @change="setTransitionDestination(sleeve.sleeve_key, $event)"
                />
                Transition destination sub-sleeve</label
              >
              <label
                ><input
                  :checked="sleeve.is_cash_sleeve"
                  type="checkbox"
                  @change="setSleeveRole(sleeve.sleeve_key, 'is_cash_sleeve', $event)"
                />
                Cash sleeve</label
              >
            </td>
            <td>
              <label class="toggle-field"
                ><input
                  :checked="sleeve.enabled"
                  type="checkbox"
                  @change="setSleeveEnabled(sleeve.sleeve_key, $event)"
                /><span>{{ sleeve.enabled ? 'Enabled' : 'Disabled' }}</span></label
              >
              <label v-if="!sleeve.enabled" class="compact-field reassignment-field">
                <span>Reassign held assets to</span>
                <select
                  :value="reassignments[sleeve.sleeve_key] ?? ''"
                  @change="setReassignment(sleeve.sleeve_key, $event)"
                  :aria-label="`Reassign holdings from ${sleeve.display_name || sleeve.sleeve_key}`"
                >
                  <option value="">Choose destination</option>
                  <option
                    v-for="target in reassignmentOptions(sleeve.sleeve_key)"
                    :key="target.sleeve_key"
                    :value="target.sleeve_key"
                  >
                    {{ target.display_name || target.sleeve_key }}
                  </option>
                </select>
              </label>
            </td>
            <td>
              <button
                type="button"
                class="danger-button small-button"
                @click="beginDeleteSleeve(sleeve.sleeve_key)"
              >
                Delete
              </button>
            </td>
          </tr>
          <tr v-if="sleeves.length === 0">
            <td colspan="8" class="empty-cell">
              No sleeves configured. Add a sleeve and enter its policy values.
            </td>
          </tr>
        </tbody>
      </table>
    </WorkspaceTableFrame>
    <div
      v-if="pendingDeleteSleeve"
      class="delete-panel"
      role="group"
      :aria-labelledby="`${sectionId}-delete-title`"
    >
      <h3 :id="`${sectionId}-delete-title`">
        Delete {{ pendingDeleteSleeve.display_name || pendingDeleteSleeve.sleeve_key }}
      </h3>
      <p>
        Choose an enabled destination for any holdings currently assigned here. Reassignments are
        explicit; no holdings are silently orphaned.
      </p>
      <label v-if="heldInSleeve(pendingDeleteSleeve.sleeve_key).length" class="field">
        <span>Holding reassignment destination</span>
        <select v-model="deleteTargetKey" aria-label="Holding reassignment destination">
          <option value="">Choose destination</option>
          <option
            v-for="target in reassignmentOptions(pendingDeleteSleeve.sleeve_key)"
            :key="target.sleeve_key"
            :value="target.sleeve_key"
          >
            {{ target.display_name || target.sleeve_key }}
          </option>
        </select>
      </label>
      <div
        v-for="child in childrenOf(pendingDeleteSleeve.sleeve_key)"
        :key="child.sleeve_key"
        class="reparent-row"
      >
        <label class="field"
          ><span>Move child “{{ child.display_name || child.sleeve_key }}” under</span>
          <select
            v-model="childReparents[child.sleeve_key]"
            :aria-label="`New parent for ${child.display_name || child.sleeve_key}`"
          >
            <option value="">Choose new parent</option>
            <option :value="null">Top level</option>
            <option
              v-for="parent in reparentOptions(pendingDeleteSleeve.sleeve_key, child.sleeve_key)"
              :key="parent.sleeve_key"
              :value="parent.sleeve_key"
            >
              {{ parent.display_name || parent.sleeve_key }}
            </option>
          </select>
        </label>
      </div>
      <p v-if="deleteError" class="inline-error" role="alert">{{ deleteError }}</p>
      <div class="button-row">
        <button type="button" class="danger-button" @click="confirmDeleteSleeve">
          Confirm delete
        </button>
        <button type="button" class="text-button" @click="cancelDeleteSleeve">Cancel</button>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, reactive, ref, useId, watch } from 'vue';
import WorkspaceTableFrame from '@/components/WorkspaceTableFrame.vue';
import type { PositionResponse } from '@/types/api';
import type { EditablePolicyDraft, EditableSleeve } from '@/pages/policy-form';

const props = defineProps<{
  draft: EditablePolicyDraft;
  positions: readonly PositionResponse[] | null;
  targetIssues: readonly string[];
  sourceRevisionId: string | null;
}>();
const emit = defineEmits<{
  'update:sleeves': [sleeves: EditableSleeve[]];
  'update:reassignments': [
    reassignments: Record<string, string>,
    reassignmentHoldings: Record<string, string[]>,
  ];
}>();
const sectionId = useId();
const targetIssues = computed(() => props.targetIssues);
const sleeves = computed(() => props.draft.sleeves);
const reassignments = computed(() => props.draft.reassignments);
const portfolio = computed(() => (props.positions ? { positions: props.positions } : null));
const enabledSleeves = computed(() => sleeves.value.filter((sleeve) => sleeve.enabled !== false));
const enabledTopLevelSleeves = computed(() =>
  enabledSleeves.value.filter((sleeve) => !sleeve.parent_sleeve_key),
);
const deleteSleeveKey = ref<string | null>(null);
const deleteTargetKey = ref('');
const childReparents = reactive<Record<string, string | null>>({});
const deleteError = ref('');
const nextSleeveNumber = ref(1);
const pendingDeleteSleeve = computed(
  () => sleeves.value.find((sleeve) => sleeve.sleeve_key === deleteSleeveKey.value) ?? null,
);

watch(
  () =>
    `${props.sourceRevisionId ?? ''}:${JSON.stringify(props.draft.sleeves.map((sleeve) => sleeve.sleeve_key))}`,
  cancelDeleteSleeve,
);

function emitSleeves(next: EditableSleeve[]): void {
  emit('update:sleeves', next);
}

function updateSleeve(key: string, patch: Partial<EditableSleeve>): void {
  if (!sleeves.value.some((sleeve) => sleeve.sleeve_key === key)) return;
  emitSleeves(
    sleeves.value.map((sleeve) => (sleeve.sleeve_key === key ? { ...sleeve, ...patch } : sleeve)),
  );
}

function setSleeveText(
  key: string,
  field: 'display_name' | 'target_pct' | 'drift_band_pp',
  event: Event,
): void {
  const value = (event.target as HTMLInputElement).value;
  if (field === 'display_name') updateSleeve(key, { display_name: value });
  else if (field === 'target_pct') updateSleeve(key, { target_pct: value });
  else updateSleeve(key, { drift_band_pp: value });
}

function selectedValue(event: Event): unknown {
  const select = event.target as HTMLSelectElement;
  const option = select.options[select.selectedIndex] as
    (HTMLOptionElement & { _value?: unknown }) | undefined;
  if (!option) return null;
  return '_value' in option ? option._value : option.value;
}

function setSleeveParent(key: string, event: Event): void {
  const value = selectedValue(event);
  if (value === null || typeof value === 'string') updateSleeve(key, { parent_sleeve_key: value });
}

function addSleeve(): void {
  let key: string;
  do {
    key = `sleeve-new-${nextSleeveNumber.value++}`;
  } while (sleeves.value.some((sleeve) => sleeve.sleeve_key === key));

  emitSleeves([
    ...sleeves.value,
    {
      sleeve_key: key,
      display_name: '',
      sort_order: sleeves.value.length,
      parent_sleeve_key: null,
      target_pct: '',
      drift_band_pp: '',
      is_direct_index_container: false,
      is_direct_index_sleeve: false,
      is_transition_destination: false,
      is_cash_sleeve: false,
      enabled: true,
    },
  ]);
}

function hasEnabledChild(key: string): boolean {
  return sleeves.value.some(
    (sleeve) => sleeve.enabled !== false && sleeve.parent_sleeve_key === key,
  );
}

function heldInSleeve(key: string): Array<{ ticker: string }> {
  return (
    portfolio.value?.positions.filter(
      (position) => position.sleeve_key === key || position.sub_sleeve_key === key,
    ) ?? []
  );
}

function emitReassignments(next: Record<string, string>, holdings: Record<string, string[]>): void {
  emit('update:reassignments', next, holdings);
}

function updateReassignment(sourceKey: string, targetKey: string | null): void {
  const next = { ...reassignments.value };
  const holdings = { ...props.draft.reassignmentHoldings };
  if (targetKey) {
    next[sourceKey] = targetKey;
    holdings[sourceKey] = heldInSleeve(sourceKey).map((position) => position.ticker);
  } else {
    delete next[sourceKey];
    delete holdings[sourceKey];
  }
  emitReassignments(next, holdings);
}

function setReassignment(sourceKey: string, event: Event): void {
  const targetKey = (event.target as HTMLSelectElement).value;
  updateReassignment(sourceKey, targetKey || null);
}

function setSleeveEnabled(key: string, event: Event): void {
  const enabled = (event.target as HTMLInputElement).checked;
  if (!enabled && hasEnabledChild(key)) {
    (event.target as HTMLInputElement).checked = true;
    deleteError.value = 'Disable or reparent enabled child sleeves before disabling this parent.';
    return;
  }
  updateSleeve(key, { enabled });
  if (enabled) updateReassignment(key, null);
  deleteError.value = '';
}

function setDirectIndexContainer(key: string, event: Event): void {
  const enabled = (event.target as HTMLInputElement).checked;
  emitSleeves(
    sleeves.value.map((sleeve) => ({
      ...sleeve,
      is_direct_index_container: sleeve.sleeve_key === key && enabled,
    })),
  );
}

function setSleeveRole(
  key: string,
  role: 'is_direct_index_sleeve' | 'is_cash_sleeve',
  event: Event,
): void {
  const enabled = (event.target as HTMLInputElement).checked;
  if (role === 'is_direct_index_sleeve') updateSleeve(key, { is_direct_index_sleeve: enabled });
  else updateSleeve(key, { is_cash_sleeve: enabled });
}

function setTransitionDestination(key: string, event: Event): void {
  const enabled = (event.target as HTMLInputElement).checked;
  emitSleeves(
    sleeves.value.map((sleeve) => ({
      ...sleeve,
      is_transition_destination: sleeve.sleeve_key === key && enabled,
    })),
  );
}

function childrenOf(key: string): EditableSleeve[] {
  return sleeves.value.filter((sleeve) => sleeve.parent_sleeve_key === key);
}

function isDescendant(candidateKey: string, ancestorKey: string): boolean {
  let current = sleeves.value.find((sleeve) => sleeve.sleeve_key === candidateKey);
  while (current?.parent_sleeve_key) {
    if (current.parent_sleeve_key === ancestorKey) return true;
    current = sleeves.value.find((sleeve) => sleeve.sleeve_key === current?.parent_sleeve_key);
  }
  return false;
}

function parentOptions(sleeve: EditableSleeve): EditableSleeve[] {
  return enabledSleeves.value.filter(
    (candidate) =>
      candidate.sleeve_key !== sleeve.sleeve_key &&
      !isDescendant(candidate.sleeve_key, sleeve.sleeve_key),
  );
}

function sleeveSiblingTargetIndex(index: number, direction: -1 | 1): number | null {
  const sleeve = sleeves.value[index];
  if (!sleeve) return null;
  const siblings = sleeves.value
    .map((candidate, candidateIndex) => ({ candidate, candidateIndex }))
    .filter(({ candidate }) => candidate.parent_sleeve_key === sleeve.parent_sleeve_key);
  const siblingPosition = siblings.findIndex(({ candidateIndex }) => candidateIndex === index);
  return siblings[siblingPosition + direction]?.candidateIndex ?? null;
}

function canMoveSleeve(index: number, direction: -1 | 1): boolean {
  return sleeveSiblingTargetIndex(index, direction) !== null;
}

function moveSleeve(index: number, direction: -1 | 1): void {
  const targetIndex = sleeveSiblingTargetIndex(index, direction);
  if (targetIndex === null) return;
  const next = sleeves.value.map((sleeve) => ({ ...sleeve }));
  [next[index], next[targetIndex]] = [next[targetIndex]!, next[index]!];
  emitSleeves(next);
}

function reassignmentOptions(excludedKey: string): EditableSleeve[] {
  return enabledSleeves.value.filter((sleeve) => sleeve.sleeve_key !== excludedKey);
}

function beginDeleteSleeve(key: string): void {
  deleteSleeveKey.value = key;
  deleteTargetKey.value = '';
  deleteError.value = '';
  for (const child of childrenOf(key)) childReparents[child.sleeve_key] = '';
}

function reparentOptions(deletingKey: string, childKey: string): EditableSleeve[] {
  return enabledTopLevelSleeves.value.filter(
    (sleeve) =>
      sleeve.sleeve_key !== deletingKey &&
      sleeve.sleeve_key !== childKey &&
      !isDescendant(sleeve.sleeve_key, childKey),
  );
}

function confirmDeleteSleeve(): void {
  const key = deleteSleeveKey.value;
  if (!key) return;
  const children = childrenOf(key);
  if (children.some((child) => childReparents[child.sleeve_key] === '')) {
    deleteError.value = 'Choose a new parent or top-level placement for every child sleeve.';
    return;
  }
  const holdings = heldInSleeve(key);
  if (holdings.length && !deleteTargetKey.value) {
    deleteError.value =
      'Choose an enabled holding reassignment destination before deleting this sleeve.';
    return;
  }
  updateReassignment(key, holdings.length ? deleteTargetKey.value : null);
  const next = sleeves.value
    .filter((sleeve) => sleeve.sleeve_key !== key)
    .map((sleeve) =>
      sleeve.parent_sleeve_key === key
        ? { ...sleeve, parent_sleeve_key: childReparents[sleeve.sleeve_key] || null }
        : sleeve,
    );
  emitSleeves(next);
  deleteSleeveKey.value = null;
  deleteError.value = '';
}

function cancelDeleteSleeve(): void {
  deleteSleeveKey.value = null;
  deleteTargetKey.value = '';
  deleteError.value = '';
  for (const key of Object.keys(childReparents)) delete childReparents[key];
}
</script>

<style scoped src="./policy-editor-sections.css"></style>

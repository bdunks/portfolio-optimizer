<template>
  <section class="panel" :aria-labelledby="`${sectionId}-title`">
    <div class="section-heading">
      <div>
        <h2 :id="`${sectionId}-title`">Approved ETF replacement sets</h2>
        <p class="section-subtitle">
          Set ID groups candidate pairs or triplets; priority, suitability, enabled status, and
          sleeve assignments are explicit policy data. Distinct approved funds are a user
          assumption, not a wash-sale guarantee or automated exposure-equivalence check.
        </p>
      </div>
      <q-btn unelevated no-caps type="button" class="secondary-button" @click="addSecurity">
        + Add ETF candidate
      </q-btn>
    </div>
    <WorkspaceTableFrame class="table-scroll" label="Replacement security candidates">
      <table class="editor-table securities-table">
        <thead>
          <tr>
            <th>Order</th>
            <th>Ticker</th>
            <th>Replacement set ID</th>
            <th>Priority</th>
            <th>Parent sleeve</th>
            <th>Sub-sleeve</th>
            <th>Exposure suitability (API note)</th>
            <th>Enabled</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="(security, index) in allowedSecurities"
            :key="`${security.ticker}-${security.replacement_set_id}-${index}`"
          >
            <td>
              <div class="order-tools">
                <q-btn
                  unelevated
                  no-caps
                  type="button"
                  class="icon-button"
                  :aria-label="`Move ${security.ticker || 'candidate'} up`"
                  :disable="!canMoveSecurity(index, -1)"
                  @click="moveSecurity(index, -1)"
                >
                  ↑
                </q-btn>
                <q-btn
                  unelevated
                  no-caps
                  type="button"
                  class="icon-button"
                  :aria-label="`Move ${security.ticker || 'candidate'} down`"
                  :disable="!canMoveSecurity(index, 1)"
                  @click="moveSecurity(index, 1)"
                >
                  ↓
                </q-btn>
              </div>
            </td>
            <td>
              <label class="compact-field"
                ><span class="sr-only">ETF ticker</span
                ><input
                  :value="security.ticker"
                  @input="setSecurityText(index, 'ticker', $event)"
                  aria-label="ETF ticker"
                  placeholder="Ticker"
              /></label>
            </td>
            <td>
              <label class="compact-field"
                ><span class="sr-only">Replacement set ID</span
                ><input
                  :value="security.replacement_set_id"
                  @input="setSecurityText(index, 'replacement_set_id', $event)"
                  aria-label="Replacement set ID"
                  placeholder="Set ID"
              /></label>
            </td>
            <td>
              <label class="compact-field priority-input"
                ><span class="sr-only">Candidate priority</span
                ><input
                  :value="security.priority"
                  @input="setSecurityPriority(index, $event)"
                  type="number"
                  step="1"
                  aria-label="Candidate priority"
              /></label>
            </td>
            <td>
              <label class="compact-field"
                ><span class="sr-only">Candidate parent sleeve</span
                ><q-select
                  :model-value="security.sleeve_key"
                  :options="[
                    { label: 'Choose sleeve', value: '' },
                    ...enabledTopLevelSleeves.map((sleeve) => ({
                      label: sleeve.display_name || sleeve.sleeve_key,
                      value: sleeve.sleeve_key,
                    })),
                  ]"
                  emit-value
                  map-options
                  outlined
                  dense
                  hide-bottom-space
                  aria-label="Candidate parent sleeve"
                  @update:model-value="setSecurityParent(index, $event)"
              /></label>
            </td>
            <td>
              <label class="compact-field"
                ><span class="sr-only">Candidate sub-sleeve</span
                ><q-select
                  :model-value="security.sub_sleeve_key"
                  :options="[
                    { label: 'None', value: null },
                    ...enabledChildren(security.sleeve_key).map((child) => ({
                      label: child.display_name || child.sleeve_key,
                      value: child.sleeve_key,
                    })),
                  ]"
                  emit-value
                  map-options
                  outlined
                  dense
                  hide-bottom-space
                  aria-label="Candidate sub-sleeve"
                  @update:model-value="setSecuritySubSleeve(index, $event)"
              /></label>
            </td>
            <td>
              <label class="compact-field"
                ><span class="sr-only">Exposure suitability note</span
                ><input
                  :value="security.exposure_suitability ?? ''"
                  @input="setSecurityText(index, 'exposure_suitability', $event)"
                  aria-label="Exposure suitability note"
                  placeholder="Optional API text"
              /></label>
            </td>
            <td>
              <q-checkbox
                class="toggle-field"
                dense
                color="primary"
                :model-value="security.enabled"
                :label="security.enabled ? 'Enabled' : 'Disabled'"
                @update:model-value="setSecurityEnabled(index, $event)"
              />
            </td>
            <td>
              <q-btn
                unelevated
                no-caps
                type="button"
                class="danger-button small-button"
                :aria-label="`Remove ${security.ticker || 'ETF candidate'}`"
                @click="removeSecurity(index)"
              >
                Remove
              </q-btn>
            </td>
          </tr>
          <tr v-if="allowedSecurities.length === 0">
            <td colspan="9" class="empty-cell">
              No replacement candidates configured. Nothing is inferred or added automatically.
            </td>
          </tr>
        </tbody>
      </table>
    </WorkspaceTableFrame>
  </section>
</template>

<script setup lang="ts">
import { computed, useId } from 'vue';
import WorkspaceTableFrame from '@/components/WorkspaceTableFrame.vue';
import type { AllowedSecurityInput } from '@/types/api';
import type { EditablePolicyDraft, EditableSleeve } from '@/pages/policy-form';

const props = defineProps<{ draft: EditablePolicyDraft }>();
const emit = defineEmits<{
  'update:allowed-securities': [securities: AllowedSecurityInput[]];
}>();
const sectionId = useId();
const allowedSecurities = computed(() => props.draft.allowedSecurities);
const sleeves = computed(() => props.draft.sleeves);
const enabledSleeves = computed(() => sleeves.value.filter((sleeve) => sleeve.enabled !== false));
const enabledTopLevelSleeves = computed(() =>
  enabledSleeves.value.filter((sleeve) => !sleeve.parent_sleeve_key),
);

function enabledChildren(parentKey: string): EditableSleeve[] {
  return enabledSleeves.value.filter((sleeve) => sleeve.parent_sleeve_key === parentKey);
}

function emitSecurities(securities: AllowedSecurityInput[]): void {
  emit('update:allowed-securities', securities);
}

function updateSecurity(index: number, patch: Partial<AllowedSecurityInput>): void {
  const current = allowedSecurities.value[index];
  if (!current) return;
  emitSecurities(
    allowedSecurities.value.map((security, securityIndex) =>
      securityIndex === index ? { ...security, ...patch } : security,
    ),
  );
}

function setSecurityText(
  index: number,
  key: 'ticker' | 'replacement_set_id' | 'exposure_suitability',
  event: Event,
): void {
  const value = (event.target as HTMLInputElement).value;
  if (key === 'ticker') updateSecurity(index, { ticker: value });
  else if (key === 'replacement_set_id') updateSecurity(index, { replacement_set_id: value });
  else updateSecurity(index, { exposure_suitability: value });
}

function setSecurityParent(index: number, value: string): void {
  updateSecurity(index, { sleeve_key: value });
}

function setSecuritySubSleeve(index: number, value: string | null): void {
  updateSecurity(index, { sub_sleeve_key: value });
}

function setSecurityPriority(index: number, event: Event): void {
  const value = (event.target as HTMLInputElement).value;
  updateSecurity(index, { priority: value.trim() ? Number(value) : Number.NaN });
}

function setSecurityEnabled(index: number, enabled: boolean): void {
  updateSecurity(index, { enabled });
}

function addSecurity(): void {
  emitSecurities([
    ...allowedSecurities.value,
    {
      ticker: '',
      sleeve_key: '',
      sub_sleeve_key: null,
      replacement_set_id: '',
      priority: allowedSecurities.value.length,
      enabled: true,
      exposure_suitability: null,
    },
  ]);
}

function removeSecurity(index: number): void {
  emitSecurities(allowedSecurities.value.filter((_, securityIndex) => securityIndex !== index));
}

function securitySiblingTargetIndex(index: number, direction: -1 | 1): number | null {
  const security = allowedSecurities.value[index];
  if (!security) return null;
  const siblings = allowedSecurities.value
    .map((candidate, candidateIndex) => ({ candidate, candidateIndex }))
    .filter(
      ({ candidate }) =>
        candidate.sleeve_key === security.sleeve_key &&
        candidate.replacement_set_id === security.replacement_set_id,
    );
  const siblingPosition = siblings.findIndex(({ candidateIndex }) => candidateIndex === index);
  return siblings[siblingPosition + direction]?.candidateIndex ?? null;
}

function canMoveSecurity(index: number, direction: -1 | 1): boolean {
  return securitySiblingTargetIndex(index, direction) !== null;
}

function moveSecurity(index: number, direction: -1 | 1): void {
  const targetIndex = securitySiblingTargetIndex(index, direction);
  if (targetIndex === null) return;
  const securities = allowedSecurities.value.map((security) => ({ ...security }));
  const current = securities[index]!;
  const next = securities[targetIndex]!;
  [securities[index], securities[targetIndex]] = [next, current];
  const oldPriority = current.priority ?? 0;
  current.priority = next.priority ?? 0;
  next.priority = oldPriority;
  emitSecurities(securities);
}
</script>

<style scoped src="./policy-editor-sections.css"></style>

<template>
  <q-card tag="section" class="panel q-pa-md" :aria-labelledby="`${sectionId}-title`">
    <div class="section-heading items-center row justify-between q-gutter-md q-mb-md">
      <div>
        <h2 class="q-ma-none text-h6" :id="`${sectionId}-title`">Approved ETF replacement sets</h2>
        <p class="section-subtitle q-mt-sm q-mb-none q-mx-none">
          Set ID groups candidate pairs or triplets; priority, suitability, enabled status, and
          sleeve assignments are explicit policy data. Distinct approved funds are a user
          assumption, not a wash-sale guarantee or automated exposure-equivalence check.
        </p>
      </div>
      <q-btn
        no-caps
        type="button"
        class="secondary-button"
        outline
        color="primary"
        size="sm"
        @click="addSecurity"
      >
        + Add ETF candidate
      </q-btn>
    </div>
    <WorkspaceTableFrame label="Replacement security candidates">
      <q-markup-table class="editor-table securities-table" wrap-cells>
        <caption class="sr-only">
          Configured ETF replacement candidates and policy settings
        </caption>
        <thead>
          <tr>
            <th scope="col">Order</th>
            <th scope="col">Ticker</th>
            <th scope="col">Replacement set ID</th>
            <th scope="col">Priority</th>
            <th scope="col">Parent sleeve</th>
            <th scope="col">Sub-sleeve</th>
            <th scope="col">Exposure suitability (API note)</th>
            <th scope="col">Enabled</th>
            <th scope="col">Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="(security, index) in allowedSecurities"
            :key="`${security.ticker}-${security.replacement_set_id}-${index}`"
          >
            <td>
              <div class="order-tools row no-wrap q-gutter-xs q-mb-xs">
                <q-btn
                  no-caps
                  type="button"
                  class="icon-button"
                  outline
                  color="primary"
                  dense
                  size="sm"
                  :aria-label="`Move ${security.ticker || 'candidate'} up`"
                  :disable="!canMoveSecurity(index, -1)"
                  @click="moveSecurity(index, -1)"
                >
                  ↑
                </q-btn>
                <q-btn
                  no-caps
                  type="button"
                  class="icon-button"
                  outline
                  color="primary"
                  dense
                  size="sm"
                  :aria-label="`Move ${security.ticker || 'candidate'} down`"
                  :disable="!canMoveSecurity(index, 1)"
                  @click="moveSecurity(index, 1)"
                >
                  ↓
                </q-btn>
              </div>
            </td>
            <td>
              <label class="compact-field column no-wrap q-gutter-y-xs"
                ><span class="sr-only">ETF ticker</span
                ><q-input
                  outlined
                  dense
                  hide-bottom-space
                  :model-value="security.ticker"
                  @update:model-value="setSecurityText(index, 'ticker', String($event ?? ''))"
                  aria-label="ETF ticker"
                  placeholder="Ticker"
              /></label>
            </td>
            <td>
              <label class="compact-field column no-wrap q-gutter-y-xs"
                ><span class="sr-only">Replacement set ID</span
                ><q-input
                  outlined
                  dense
                  hide-bottom-space
                  :model-value="security.replacement_set_id"
                  @update:model-value="
                    setSecurityText(index, 'replacement_set_id', String($event ?? ''))
                  "
                  aria-label="Replacement set ID"
                  placeholder="Set ID"
              /></label>
            </td>
            <td>
              <label class="compact-field priority-input column no-wrap q-gutter-y-xs"
                ><span class="sr-only">Candidate priority</span
                ><q-input
                  outlined
                  dense
                  hide-bottom-space
                  :model-value="security.priority"
                  @update:model-value="setSecurityPriority(index, String($event ?? ''))"
                  type="number"
                  step="1"
                  aria-label="Candidate priority"
              /></label>
            </td>
            <td>
              <label class="compact-field column no-wrap q-gutter-y-xs"
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
              <label class="compact-field column no-wrap q-gutter-y-xs"
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
              <label class="compact-field column no-wrap q-gutter-y-xs"
                ><span class="sr-only">Exposure suitability note</span
                ><q-input
                  outlined
                  dense
                  hide-bottom-space
                  :model-value="security.exposure_suitability ?? ''"
                  @update:model-value="
                    setSecurityText(index, 'exposure_suitability', String($event ?? ''))
                  "
                  aria-label="Exposure suitability note"
                  placeholder="Optional API text"
              /></label>
            </td>
            <td>
              <q-checkbox
                class="text-caption text-weight-bold text-blue-grey-8"
                dense
                color="primary"
                :model-value="security.enabled"
                :label="security.enabled ? 'Enabled' : 'Disabled'"
                @update:model-value="setSecurityEnabled(index, $event)"
              />
            </td>
            <td>
              <q-btn
                no-caps
                type="button"
                class="danger-button small-button"
                outline
                color="negative"
                size="0.68rem"
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
      </q-markup-table>
    </WorkspaceTableFrame>
  </q-card>
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
  value: string,
): void {
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

function setSecurityPriority(index: number, value: string): void {
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

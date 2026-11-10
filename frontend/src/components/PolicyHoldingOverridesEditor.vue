<template>
  <q-card tag="section" class="panel q-pa-md" :aria-labelledby="`${sectionId}-title`">
    <div class="section-heading row items-center justify-between q-gutter-md q-mb-md">
      <div>
        <h2 class="q-ma-none text-h6" :id="`${sectionId}-title`">Explicit holding overrides</h2>
        <p class="section-subtitle q-mt-sm q-mb-none q-mx-none">
          “Use default resolution” removes an override. The API resolves approved ETFs by configured
          assignment and individual equities plus VB/VXF by the direct-index container unless
          explicitly overridden; this page does not infer new assignments.
        </p>
      </div>
    </div>
    <q-banner
      v-if="portfolioLoading && !portfolioAvailable"
      class="q-mt-md q-mb-none q-mx-none rounded bg-blue-grey-1 text-blue-grey-10"
      role="status"
    >
      Loading the current single-account holding list…
    </q-banner>
    <p v-else-if="!portfolioAvailable" class="empty-note q-mt-md q-mb-none q-mx-none">
      Current holdings are unavailable. Existing saved overrides remain editable below; no holdings
      are guessed.
    </p>
    <WorkspaceTableFrame label="Holding sleeve overrides">
      <q-markup-table class="editor-table override-table" wrap-cells>
        <caption class="sr-only">
          Current API sleeve resolutions and explicit overrides by ticker
        </caption>
        <thead>
          <tr>
            <th scope="col">Ticker</th>
            <th scope="col">Current API resolution</th>
            <th scope="col">Explicit override</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="holding in overrideHoldings" :key="holding.ticker">
            <td>
              <strong>{{ holding.ticker }}</strong>
            </td>
            <td>{{ holding.currentLabel }}</td>
            <td>
              <label class="compact-field override-select column no-wrap q-gutter-y-xs"
                ><span class="sr-only">Explicit override for {{ holding.ticker }}</span>
                <q-select
                  :model-value="overrideTarget(holding.ticker)"
                  :options="[
                    { label: 'Use default resolution', value: '' },
                    ...(currentOverrideTargetIsDisabled(holding.ticker)
                      ? [
                          {
                            label: 'Current assignment — disabled; choose a valid target or remove',
                            value: overrideTarget(holding.ticker),
                            disable: true,
                          },
                        ]
                      : []),
                    ...overrideOptions.map((target) => ({
                      label: target.display_name || target.sleeve_key,
                      value: target.sleeve_key,
                    })),
                  ]"
                  emit-value
                  map-options
                  outlined
                  dense
                  hide-bottom-space
                  :aria-label="`Explicit override for ${holding.ticker}`"
                  @update:model-value="setOverrideTarget(holding.ticker, $event)"
                />
              </label>
            </td>
          </tr>
          <tr v-if="overrideHoldings.length === 0">
            <td colspan="3" class="empty-cell">
              No current holdings or explicit overrides have been returned.
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
import type { OverrideInput, PositionResponse } from '@/types/api';
import type { EditablePolicyDraft } from '@/pages/policy-form';

const props = defineProps<{
  draft: EditablePolicyDraft;
  positions: readonly PositionResponse[] | null;
  portfolioAvailable: boolean;
  portfolioLoading: boolean;
}>();
const emit = defineEmits<{
  'update:overrides': [overrides: OverrideInput[]];
}>();
const sectionId = useId();
const overrides = computed(() => props.draft.overrides);
const sleeves = computed(() => props.draft.sleeves);
const enabledSleeves = computed(() => sleeves.value.filter((sleeve) => sleeve.enabled !== false));
const overrideOptions = computed(() => enabledSleeves.value);
const overrideHoldings = computed(() => {
  const holdings =
    props.positions?.map((position) => ({
      ticker: position.ticker,
      currentLabel: position.sub_sleeve_key
        ? `${position.sleeve_key} → ${position.sub_sleeve_key}`
        : (position.sleeve_key ?? 'No API sleeve resolution'),
    })) ?? [];
  const present = new Set(holdings.map((holding) => holding.ticker));
  for (const override of overrides.value) {
    if (!present.has(override.ticker))
      holdings.push({
        ticker: override.ticker,
        currentLabel: 'Override returned by policy API; holding not in current portfolio response',
      });
  }
  return holdings;
});

function currentOverrideTargetIsDisabled(ticker: string): boolean {
  const value = overrideTarget(ticker);
  return !!value && !enabledSleeves.value.some((sleeve) => sleeve.sleeve_key === value);
}

function overrideTarget(ticker: string): string {
  const override = overrides.value.find((item) => item.ticker === ticker);
  return override?.sub_sleeve_key ?? override?.sleeve_key ?? '';
}

function setOverrideTarget(ticker: string, targetKey: string): void {
  const existing = overrides.value.findIndex((override) => override.ticker === ticker);
  const next = overrides.value.map((override) => ({ ...override }));
  if (!targetKey) {
    if (existing >= 0) {
      next.splice(existing, 1);
      emit('update:overrides', next);
    }
    return;
  }
  const target = sleeves.value.find((sleeve) => sleeve.sleeve_key === targetKey);
  if (!target) return;
  const override: OverrideInput = target.parent_sleeve_key
    ? { ticker, sleeve_key: target.parent_sleeve_key, sub_sleeve_key: target.sleeve_key }
    : { ticker, sleeve_key: target.sleeve_key, sub_sleeve_key: null };
  if (existing >= 0) next[existing] = override;
  else next.push(override);
  emit('update:overrides', next);
}
</script>

<style scoped src="./policy-editor-sections.css"></style>

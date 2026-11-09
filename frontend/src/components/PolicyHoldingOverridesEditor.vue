<template>
  <section class="panel" :aria-labelledby="`${sectionId}-title`">
    <div class="section-heading">
      <div>
        <h2 :id="`${sectionId}-title`">Explicit holding overrides</h2>
        <p class="section-subtitle">
          “Use default resolution” removes an override. The API resolves approved ETFs by configured
          assignment and individual equities plus VB/VXF by the direct-index container unless
          explicitly overridden; this page does not infer new assignments.
        </p>
      </div>
    </div>
    <p v-if="portfolioLoading && !portfolioAvailable" class="state-message" role="status">
      Loading the current single-account holding list…
    </p>
    <p v-else-if="!portfolioAvailable" class="empty-note">
      Current holdings are unavailable. Existing saved overrides remain editable below; no holdings
      are guessed.
    </p>
    <WorkspaceTableFrame class="table-scroll" label="Holding sleeve overrides">
      <table class="editor-table override-table">
        <thead>
          <tr>
            <th>Ticker</th>
            <th>Current API resolution</th>
            <th>Explicit override</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="holding in overrideHoldings" :key="holding.ticker">
            <td>
              <strong>{{ holding.ticker }}</strong>
            </td>
            <td>{{ holding.currentLabel }}</td>
            <td>
              <label class="compact-field override-select"
                ><span class="sr-only">Explicit override for {{ holding.ticker }}</span>
                <select
                  :value="overrideTarget(holding.ticker)"
                  :aria-label="`Explicit override for ${holding.ticker}`"
                  @change="setOverrideTarget(holding.ticker, $event)"
                >
                  <option value="">Use default resolution</option>
                  <option
                    v-if="currentOverrideTargetIsDisabled(holding.ticker)"
                    :value="overrideTarget(holding.ticker)"
                  >
                    Current assignment — disabled; choose a valid target or remove
                  </option>
                  <option
                    v-for="target in overrideOptions"
                    :key="target.sleeve_key"
                    :value="target.sleeve_key"
                  >
                    {{ target.display_name || target.sleeve_key }}
                  </option>
                </select>
              </label>
            </td>
          </tr>
          <tr v-if="overrideHoldings.length === 0">
            <td colspan="3" class="empty-cell">
              No current holdings or explicit overrides have been returned.
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

function setOverrideTarget(ticker: string, event: Event): void {
  const targetKey = (event.target as HTMLSelectElement).value;
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

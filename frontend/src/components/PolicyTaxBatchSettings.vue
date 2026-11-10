<template>
  <q-card
    tag="section"
    class="panel settings-panel q-pa-md"
    :aria-labelledby="`${sectionId}-title`"
  >
    <div class="section-heading items-center row justify-between q-gutter-md q-mb-md">
      <div>
        <h2 class="q-ma-none text-h6" :id="`${sectionId}-title`">Tax &amp; Batch Settings</h2>
        <p class="section-subtitle q-mt-sm q-mb-none q-mx-none">
          Blank nullable values are sent as null; blank required values are never guessed as zero.
          Amounts remain exact API decimal strings.
        </p>
      </div>
    </div>
    <div class="settings-group q-py-md q-px-none">
      <h3 class="q-mt-none q-mb-sm q-mx-none">
        Tax rates, carryforwards, and YTD realized amounts
      </h3>
      <p class="unit-note q-mt-none q-mb-md q-mx-none">
        ST/LT tax rates use fraction units (0–1); 0.25 means 25%. Missing rate stays null and makes
        tax estimates unavailable.
      </p>
      <div class="field-grid">
        <label class="field column no-wrap q-gutter-y-xs"
          ><span>Short-term marginal tax rate (fraction, nullable)</span
          ><q-input
            outlined
            dense
            hide-bottom-space
            :model-value="props.settings.short_term_tax_rate"
            @update:model-value="updateTextSetting('short_term_tax_rate', String($event ?? ''))"
            inputmode="decimal"
            placeholder="Leave blank if unknown"
        /></label>
        <label class="field column no-wrap q-gutter-y-xs"
          ><span>Long-term marginal tax rate (fraction, nullable)</span
          ><q-input
            outlined
            dense
            hide-bottom-space
            :model-value="props.settings.long_term_tax_rate"
            @update:model-value="updateTextSetting('long_term_tax_rate', String($event ?? ''))"
            inputmode="decimal"
            placeholder="Leave blank if unknown"
        /></label>
        <label class="field column no-wrap q-gutter-y-xs"
          ><span>ST loss carryforward (USD)</span
          ><q-input
            outlined
            dense
            hide-bottom-space
            :model-value="props.settings.st_loss_carryforward_usd"
            @update:model-value="
              updateTextSetting('st_loss_carryforward_usd', String($event ?? ''))
            "
            inputmode="decimal"
        /></label>
        <label class="field column no-wrap q-gutter-y-xs"
          ><span>LT loss carryforward (USD)</span
          ><q-input
            outlined
            dense
            hide-bottom-space
            :model-value="props.settings.lt_loss_carryforward_usd"
            @update:model-value="
              updateTextSetting('lt_loss_carryforward_usd', String($event ?? ''))
            "
            inputmode="decimal"
        /></label>
        <label class="field column no-wrap q-gutter-y-xs"
          ><span>YTD realized ST gain / loss (USD)</span
          ><q-input
            outlined
            dense
            hide-bottom-space
            :model-value="props.settings.ytd_realized_st_usd"
            @update:model-value="updateTextSetting('ytd_realized_st_usd', String($event ?? ''))"
            inputmode="decimal"
        /></label>
        <label class="field column no-wrap q-gutter-y-xs"
          ><span>YTD realized LT gain / loss (USD)</span
          ><q-input
            outlined
            dense
            hide-bottom-space
            :model-value="props.settings.ytd_realized_lt_usd"
            @update:model-value="updateTextSetting('ytd_realized_lt_usd', String($event ?? ''))"
            inputmode="decimal"
        /></label>
        <label class="field column no-wrap q-gutter-y-xs"
          ><span>YTD source (nullable)</span
          ><q-input
            outlined
            dense
            hide-bottom-space
            :model-value="props.settings.ytd_source"
            @update:model-value="updateTextSetting('ytd_source', String($event ?? ''))"
            placeholder="Broker or manual profile source"
        /></label>
        <label class="field column no-wrap q-gutter-y-xs"
          ><span>YTD as-of date (nullable)</span
          ><q-input
            outlined
            dense
            hide-bottom-space
            :model-value="props.settings.ytd_as_of"
            @update:model-value="updateTextSetting('ytd_as_of', String($event ?? ''))"
            type="date"
        /></label>
      </div>
      <p class="unit-note q-mt-none q-mb-md q-mx-none">
        YTD source and date identify the returned YTD values. Enter explicit manual adjustments in
        the YTD fields; the editor does not combine broker and manual amounts.
      </p>
    </div>
    <div class="settings-group q-py-md q-px-none">
      <h3 class="q-mt-none q-mb-sm q-mx-none">Retained loss and gain / tax budgets</h3>
      <div class="field-grid">
        <label class="field column no-wrap q-gutter-y-xs"
          ><span>Target retained net loss (USD)</span
          ><q-input
            outlined
            dense
            hide-bottom-space
            :model-value="props.settings.target_retained_net_loss_usd"
            @update:model-value="
              updateTextSetting('target_retained_net_loss_usd', String($event ?? ''))
            "
            inputmode="decimal"
        /></label>
        <label class="field column no-wrap q-gutter-y-xs"
          ><span>Ordinary-income deduction limit (USD)</span
          ><q-input
            outlined
            dense
            hide-bottom-space
            :model-value="props.settings.ordinary_income_deduction_limit_usd"
            @update:model-value="
              updateTextSetting('ordinary_income_deduction_limit_usd', String($event ?? ''))
            "
            inputmode="decimal"
        /></label>
        <label class="field column no-wrap q-gutter-y-xs"
          ><span>Carryforward loss discount factor (fraction, 0–1)</span
          ><q-input
            outlined
            dense
            hide-bottom-space
            :model-value="props.settings.carryforward_loss_discount_factor"
            @update:model-value="
              updateTextSetting('carryforward_loss_discount_factor', String($event ?? ''))
            "
            inputmode="decimal"
        /></label>
        <label class="field column no-wrap q-gutter-y-xs"
          ><span>Incremental realized-gain budget (USD, nullable)</span
          ><q-input
            outlined
            dense
            hide-bottom-space
            :model-value="props.settings.gain_budget_usd"
            @update:model-value="updateTextSetting('gain_budget_usd', String($event ?? ''))"
            inputmode="decimal"
            placeholder="No limit"
        /></label>
        <label class="field column no-wrap q-gutter-y-xs"
          ><span>Maximum incremental estimated tax cost (USD, nullable)</span
          ><q-input
            outlined
            dense
            hide-bottom-space
            :model-value="props.settings.max_incremental_tax_cost_usd"
            @update:model-value="
              updateTextSetting('max_incremental_tax_cost_usd', String($event ?? ''))
            "
            inputmode="decimal"
            placeholder="No limit"
        /></label>
        <label class="field column no-wrap q-gutter-y-xs"
          ><span>ST gain limit (USD, nullable)</span
          ><q-input
            outlined
            dense
            hide-bottom-space
            :model-value="props.settings.st_gain_limit_usd"
            @update:model-value="updateTextSetting('st_gain_limit_usd', String($event ?? ''))"
            inputmode="decimal"
            placeholder="No separate limit"
        /></label>
        <label class="field column no-wrap q-gutter-y-xs"
          ><span>LT gain limit (USD, nullable)</span
          ><q-input
            outlined
            dense
            hide-bottom-space
            :model-value="props.settings.lt_gain_limit_usd"
            @update:model-value="updateTextSetting('lt_gain_limit_usd', String($event ?? ''))"
            inputmode="decimal"
            placeholder="No separate limit"
        /></label>
        <label class="field column no-wrap q-gutter-y-xs"
          ><span>Budget period (API value)</span
          ><q-input
            outlined
            dense
            hide-bottom-space
            :model-value="props.settings.budget_period"
            @update:model-value="updateTextSetting('budget_period', String($event ?? ''))"
            placeholder="e.g. calendar_year"
        /></label>
      </div>
    </div>
    <div class="settings-group q-py-md q-px-none">
      <h3 class="q-mt-none q-mb-sm q-mx-none">Small-batch limits and trading preferences</h3>
      <div class="field-grid">
        <label class="field column no-wrap q-gutter-y-xs"
          ><span>Maximum sell tickers per batch</span
          ><q-input
            outlined
            dense
            hide-bottom-space
            :model-value="props.settings.max_sell_tickers_per_batch"
            @update:model-value="
              updateTextSetting('max_sell_tickers_per_batch', String($event ?? ''))
            "
            inputmode="numeric"
        /></label>
        <label class="field column no-wrap q-gutter-y-xs"
          ><span>Maximum sell lots per batch</span
          ><q-input
            outlined
            dense
            hide-bottom-space
            :model-value="props.settings.max_sell_lots_per_batch"
            @update:model-value="updateTextSetting('max_sell_lots_per_batch', String($event ?? ''))"
            inputmode="numeric"
        /></label>
        <label class="field column no-wrap q-gutter-y-xs"
          ><span>Maximum total orders per batch</span
          ><q-input
            outlined
            dense
            hide-bottom-space
            :model-value="props.settings.max_total_orders_per_batch"
            @update:model-value="
              updateTextSetting('max_total_orders_per_batch', String($event ?? ''))
            "
            inputmode="numeric"
        /></label>
        <label class="field column no-wrap q-gutter-y-xs"
          ><span>Maximum batch turnover (%)</span
          ><q-input
            outlined
            dense
            hide-bottom-space
            :model-value="props.settings.max_batch_turnover_pct"
            @update:model-value="updateTextSetting('max_batch_turnover_pct', String($event ?? ''))"
            inputmode="decimal"
        /></label>
        <label class="field column no-wrap q-gutter-y-xs"
          ><span>Minimum replacement BUY notional (USD)</span
          ><q-input
            outlined
            dense
            hide-bottom-space
            :model-value="props.settings.min_buy_order_notional_usd"
            @update:model-value="
              updateTextSetting('min_buy_order_notional_usd', String($event ?? ''))
            "
            inputmode="decimal"
        /></label>
        <label class="field column no-wrap q-gutter-y-xs"
          ><span>Cash reserve (USD)</span
          ><q-input
            outlined
            dense
            hide-bottom-space
            :model-value="props.settings.cash_reserve_usd"
            @update:model-value="updateTextSetting('cash_reserve_usd', String($event ?? ''))"
            inputmode="decimal"
        /></label>
      </div>
      <div class="toggle-grid q-mt-md">
        <label class="field column no-wrap q-gutter-y-xs"
          ><span>Prefer ETF buys</span
          ><q-select
            :model-value="props.settings.prefer_etf_buys"
            :options="toggleOptions"
            emit-value
            map-options
            outlined
            dense
            hide-bottom-space
            aria-label="Prefer ETF buys"
            @update:model-value="updateToggle('prefer_etf_buys', $event)"
        /></label>
        <label class="field column no-wrap q-gutter-y-xs"
          ><span>Allow appreciated-gain sales</span
          ><q-select
            :model-value="props.settings.allow_gain_sales"
            :options="toggleOptions"
            emit-value
            map-options
            outlined
            dense
            hide-bottom-space
            aria-label="Allow appreciated-gain sales"
            @update:model-value="updateToggle('allow_gain_sales', $event)"
        /></label>
        <label class="field column no-wrap q-gutter-y-xs"
          ><span>Permit ETF harvesting</span
          ><q-select
            :model-value="props.settings.permit_etf_harvest"
            :options="toggleOptions"
            emit-value
            map-options
            outlined
            dense
            hide-bottom-space
            aria-label="Permit ETF harvesting"
            @update:model-value="updateToggle('permit_etf_harvest', $event)"
        /></label>
        <label class="field column no-wrap q-gutter-y-xs"
          ><span>Permit municipal-bond exit</span
          ><q-select
            :model-value="props.settings.permit_muni_exit"
            :options="toggleOptions"
            emit-value
            map-options
            outlined
            dense
            hide-bottom-space
            aria-label="Permit municipal-bond exit"
            @update:model-value="updateToggle('permit_muni_exit', $event)"
        /></label>
      </div>
      <p class="unit-note q-mt-none q-mb-md q-mx-none">
        No minimum SELL notional is configured here. The minimum notional applies only to
        replacement ETF BUY legs.
      </p>
    </div>
  </q-card>
</template>

<script setup lang="ts">
import { useId } from 'vue';
import type { EditablePolicySettings } from '@/pages/policy-form';

const props = defineProps<{ settings: EditablePolicySettings }>();
const emit = defineEmits<{
  'update:settings': [settings: EditablePolicySettings];
}>();
const sectionId = useId();
const toggleOptions = [
  { label: 'Choose', value: null },
  { label: 'Enabled', value: true },
  { label: 'Disabled', value: false },
];
function updateTextSetting(key: keyof EditablePolicySettings, value: string): void {
  emit('update:settings', { ...props.settings, [key]: value });
}

function updateToggle(
  key: 'prefer_etf_buys' | 'allow_gain_sales' | 'permit_etf_harvest' | 'permit_muni_exit',
  value: boolean | null,
): void {
  emit('update:settings', { ...props.settings, [key]: value });
}
</script>

<style scoped src="./policy-editor-sections.css"></style>

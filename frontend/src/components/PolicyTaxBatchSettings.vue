<template>
  <section class="panel settings-panel" :aria-labelledby="`${sectionId}-title`">
    <div class="section-heading">
      <div>
        <h2 :id="`${sectionId}-title`">Tax &amp; Batch Settings</h2>
        <p class="section-subtitle">
          Blank nullable values are sent as null; blank required values are never guessed as zero.
          Amounts remain exact API decimal strings.
        </p>
      </div>
    </div>
    <div class="settings-group">
      <h3>Tax rates, carryforwards, and YTD realized amounts</h3>
      <p class="unit-note">
        ST/LT tax rates use fraction units (0–1); 0.25 means 25%. Missing rate stays null and makes
        tax estimates unavailable.
      </p>
      <div class="field-grid">
        <label class="field"
          ><span>Short-term marginal tax rate (fraction, nullable)</span
          ><input
            :value="props.settings.short_term_tax_rate"
            @input="updateTextSetting('short_term_tax_rate', $event)"
            inputmode="decimal"
            placeholder="Leave blank if unknown"
        /></label>
        <label class="field"
          ><span>Long-term marginal tax rate (fraction, nullable)</span
          ><input
            :value="props.settings.long_term_tax_rate"
            @input="updateTextSetting('long_term_tax_rate', $event)"
            inputmode="decimal"
            placeholder="Leave blank if unknown"
        /></label>
        <label class="field"
          ><span>ST loss carryforward (USD)</span
          ><input
            :value="props.settings.st_loss_carryforward_usd"
            @input="updateTextSetting('st_loss_carryforward_usd', $event)"
            inputmode="decimal"
        /></label>
        <label class="field"
          ><span>LT loss carryforward (USD)</span
          ><input
            :value="props.settings.lt_loss_carryforward_usd"
            @input="updateTextSetting('lt_loss_carryforward_usd', $event)"
            inputmode="decimal"
        /></label>
        <label class="field"
          ><span>YTD realized ST gain / loss (USD)</span
          ><input
            :value="props.settings.ytd_realized_st_usd"
            @input="updateTextSetting('ytd_realized_st_usd', $event)"
            inputmode="decimal"
        /></label>
        <label class="field"
          ><span>YTD realized LT gain / loss (USD)</span
          ><input
            :value="props.settings.ytd_realized_lt_usd"
            @input="updateTextSetting('ytd_realized_lt_usd', $event)"
            inputmode="decimal"
        /></label>
        <label class="field"
          ><span>YTD source (nullable)</span
          ><input
            :value="props.settings.ytd_source"
            @input="updateTextSetting('ytd_source', $event)"
            placeholder="Broker or manual profile source"
        /></label>
        <label class="field"
          ><span>YTD as-of date (nullable)</span
          ><input
            :value="props.settings.ytd_as_of"
            @input="updateTextSetting('ytd_as_of', $event)"
            type="date"
        /></label>
      </div>
      <p class="unit-note">
        YTD source and date identify the returned YTD values. Enter explicit manual adjustments in
        the YTD fields; the editor does not combine broker and manual amounts.
      </p>
    </div>
    <div class="settings-group">
      <h3>Retained loss and gain / tax budgets</h3>
      <div class="field-grid">
        <label class="field"
          ><span>Target retained net loss (USD)</span
          ><input
            :value="props.settings.target_retained_net_loss_usd"
            @input="updateTextSetting('target_retained_net_loss_usd', $event)"
            inputmode="decimal"
        /></label>
        <label class="field"
          ><span>Ordinary-income deduction limit (USD)</span
          ><input
            :value="props.settings.ordinary_income_deduction_limit_usd"
            @input="updateTextSetting('ordinary_income_deduction_limit_usd', $event)"
            inputmode="decimal"
        /></label>
        <label class="field"
          ><span>Carryforward loss discount factor (fraction, 0–1)</span
          ><input
            :value="props.settings.carryforward_loss_discount_factor"
            @input="updateTextSetting('carryforward_loss_discount_factor', $event)"
            inputmode="decimal"
        /></label>
        <label class="field"
          ><span>Incremental realized-gain budget (USD, nullable)</span
          ><input
            :value="props.settings.gain_budget_usd"
            @input="updateTextSetting('gain_budget_usd', $event)"
            inputmode="decimal"
            placeholder="No limit"
        /></label>
        <label class="field"
          ><span>Maximum incremental estimated tax cost (USD, nullable)</span
          ><input
            :value="props.settings.max_incremental_tax_cost_usd"
            @input="updateTextSetting('max_incremental_tax_cost_usd', $event)"
            inputmode="decimal"
            placeholder="No limit"
        /></label>
        <label class="field"
          ><span>ST gain limit (USD, nullable)</span
          ><input
            :value="props.settings.st_gain_limit_usd"
            @input="updateTextSetting('st_gain_limit_usd', $event)"
            inputmode="decimal"
            placeholder="No separate limit"
        /></label>
        <label class="field"
          ><span>LT gain limit (USD, nullable)</span
          ><input
            :value="props.settings.lt_gain_limit_usd"
            @input="updateTextSetting('lt_gain_limit_usd', $event)"
            inputmode="decimal"
            placeholder="No separate limit"
        /></label>
        <label class="field"
          ><span>Budget period (API value)</span
          ><input
            :value="props.settings.budget_period"
            @input="updateTextSetting('budget_period', $event)"
            placeholder="e.g. calendar_year"
        /></label>
      </div>
    </div>
    <div class="settings-group">
      <h3>Small-batch limits and trading preferences</h3>
      <div class="field-grid">
        <label class="field"
          ><span>Maximum sell tickers per batch</span
          ><input
            :value="props.settings.max_sell_tickers_per_batch"
            @input="updateTextSetting('max_sell_tickers_per_batch', $event)"
            inputmode="numeric"
        /></label>
        <label class="field"
          ><span>Maximum sell lots per batch</span
          ><input
            :value="props.settings.max_sell_lots_per_batch"
            @input="updateTextSetting('max_sell_lots_per_batch', $event)"
            inputmode="numeric"
        /></label>
        <label class="field"
          ><span>Maximum total orders per batch</span
          ><input
            :value="props.settings.max_total_orders_per_batch"
            @input="updateTextSetting('max_total_orders_per_batch', $event)"
            inputmode="numeric"
        /></label>
        <label class="field"
          ><span>Maximum batch turnover (%)</span
          ><input
            :value="props.settings.max_batch_turnover_pct"
            @input="updateTextSetting('max_batch_turnover_pct', $event)"
            inputmode="decimal"
        /></label>
        <label class="field"
          ><span>Minimum replacement BUY notional (USD)</span
          ><input
            :value="props.settings.min_buy_order_notional_usd"
            @input="updateTextSetting('min_buy_order_notional_usd', $event)"
            inputmode="decimal"
        /></label>
        <label class="field"
          ><span>Cash reserve (USD)</span
          ><input
            :value="props.settings.cash_reserve_usd"
            @input="updateTextSetting('cash_reserve_usd', $event)"
            inputmode="decimal"
        /></label>
      </div>
      <div class="toggle-grid">
        <label class="field"
          ><span>Prefer ETF buys</span
          ><select
            :value="props.settings.prefer_etf_buys"
            @change="updateToggle('prefer_etf_buys', $event)"
          >
            <option :value="null">Choose</option>
            <option :value="true">Enabled</option>
            <option :value="false">Disabled</option>
          </select></label
        >
        <label class="field"
          ><span>Allow appreciated-gain sales</span
          ><select
            :value="props.settings.allow_gain_sales"
            @change="updateToggle('allow_gain_sales', $event)"
          >
            <option :value="null">Choose</option>
            <option :value="true">Enabled</option>
            <option :value="false">Disabled</option>
          </select></label
        >
        <label class="field"
          ><span>Permit ETF harvesting</span
          ><select
            :value="props.settings.permit_etf_harvest"
            @change="updateToggle('permit_etf_harvest', $event)"
          >
            <option :value="null">Choose</option>
            <option :value="true">Enabled</option>
            <option :value="false">Disabled</option>
          </select></label
        >
        <label class="field"
          ><span>Permit municipal-bond exit</span
          ><select
            :value="props.settings.permit_muni_exit"
            @change="updateToggle('permit_muni_exit', $event)"
          >
            <option :value="null">Choose</option>
            <option :value="true">Enabled</option>
            <option :value="false">Disabled</option>
          </select></label
        >
      </div>
      <p class="unit-note">
        No minimum SELL notional is configured here. The minimum notional applies only to
        replacement ETF BUY legs.
      </p>
    </div>
  </section>
</template>

<script setup lang="ts">
import { useId } from 'vue';
import type { EditablePolicySettings } from '@/pages/policy-form';

const props = defineProps<{ settings: EditablePolicySettings }>();
const emit = defineEmits<{
  'update:settings': [settings: EditablePolicySettings];
}>();
const sectionId = useId();
function updateTextSetting(key: keyof EditablePolicySettings, event: Event): void {
  const value = (event.target as HTMLInputElement).value;
  emit('update:settings', { ...props.settings, [key]: value });
}

function updateToggle(key: keyof EditablePolicySettings, event: Event): void {
  const value = (event.target as HTMLSelectElement).value;
  const booleanValue = value === 'true' ? true : value === 'false' ? false : null;
  emit('update:settings', {
    ...props.settings,
    [key]: booleanValue,
  });
}
</script>

<style scoped src="./policy-editor-sections.css"></style>

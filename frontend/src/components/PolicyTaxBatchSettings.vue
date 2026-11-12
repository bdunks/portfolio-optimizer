<template>
  <section
    class="workspace-foundation tax-settings-root tw:min-w-0"
    data-workspace-foundation
    data-policy-tax-settings-root
    :aria-labelledby="`${sectionId}-title`"
  >
    <Card class="tw:min-w-0">
      <CardHeader>
        <CardTitle :id="`${sectionId}-title`" class="tax-title" role="heading" aria-level="2">
          Tax &amp; Batch Settings
        </CardTitle>
        <CardDescription class="tax-intro tw:m-0">
          Blank nullable values are sent as null; blank required values are never guessed as zero.
          Amounts remain exact API decimal strings.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form :id="`${sectionId}-form`" aria-label="Tax and batch settings" @submit.prevent>
          <div class="tax-settings-group tw:flex tw:flex-col tw:gap-3">
            <h3 class="tax-group-title tw:m-0">
              Tax rates, carryforwards, and YTD realized amounts
            </h3>
            <FieldDescription class="tax-help tw:m-0">
              ST/LT tax rates use fraction units (0–1); 0.25 means 25%. Missing rate stays null and
              makes tax estimates unavailable.
            </FieldDescription>
            <FieldGroup
              class="tax-fields tw:grid tw:grid-cols-1 tw:gap-4 tw:md:grid-cols-2 tw:xl:grid-cols-3"
            >
              <settingsForm.Field name="short_term_tax_rate">
                <template #default="{ field }">
                  <UiField :data-invalid="hasVisibleError(field) ? 'true' : undefined">
                    <FieldLabel :for="`${sectionId}-short-term-tax-rate`">
                      Short-term marginal tax rate (fraction, nullable)
                    </FieldLabel>
                    <Input
                      :id="`${sectionId}-short-term-tax-rate`"
                      :model-value="field.state.value ?? ''"
                      inputmode="decimal"
                      placeholder="Leave blank if unknown"
                      :aria-invalid="hasVisibleError(field) ? 'true' : undefined"
                      :aria-describedby="
                        fieldErrorId(field, `${sectionId}-short-term-tax-rate-error`)
                      "
                      @update:model-value="field.handleChange(String($event ?? ''))"
                      @blur="field.handleBlur"
                    />
                    <FieldError
                      v-if="field.state.meta.isTouched && field.state.meta.errors.length"
                      :id="`${sectionId}-short-term-tax-rate-error`"
                      :errors="field.state.meta.errors"
                    />
                  </UiField>
                </template>
              </settingsForm.Field>
              <settingsForm.Field name="long_term_tax_rate">
                <template #default="{ field }">
                  <UiField :data-invalid="hasVisibleError(field) ? 'true' : undefined">
                    <FieldLabel :for="`${sectionId}-long-term-tax-rate`">
                      Long-term marginal tax rate (fraction, nullable)
                    </FieldLabel>
                    <Input
                      :id="`${sectionId}-long-term-tax-rate`"
                      :model-value="field.state.value ?? ''"
                      inputmode="decimal"
                      placeholder="Leave blank if unknown"
                      :aria-invalid="hasVisibleError(field) ? 'true' : undefined"
                      :aria-describedby="
                        fieldErrorId(field, `${sectionId}-long-term-tax-rate-error`)
                      "
                      @update:model-value="field.handleChange(String($event ?? ''))"
                      @blur="field.handleBlur"
                    />
                    <FieldError
                      v-if="field.state.meta.isTouched && field.state.meta.errors.length"
                      :id="`${sectionId}-long-term-tax-rate-error`"
                      :errors="field.state.meta.errors"
                    />
                  </UiField>
                </template>
              </settingsForm.Field>
              <settingsForm.Field name="st_loss_carryforward_usd">
                <template #default="{ field }">
                  <UiField :data-invalid="hasVisibleError(field) ? 'true' : undefined">
                    <FieldLabel :for="`${sectionId}-st-loss-carryforward`"
                      >ST loss carryforward (USD)</FieldLabel
                    >
                    <Input
                      :id="`${sectionId}-st-loss-carryforward`"
                      :model-value="field.state.value ?? ''"
                      inputmode="decimal"
                      :aria-invalid="hasVisibleError(field) ? 'true' : undefined"
                      :aria-describedby="
                        fieldErrorId(field, `${sectionId}-st-loss-carryforward-error`)
                      "
                      @update:model-value="field.handleChange(String($event ?? ''))"
                      @blur="field.handleBlur"
                    />
                    <FieldError
                      v-if="field.state.meta.isTouched && field.state.meta.errors.length"
                      :id="`${sectionId}-st-loss-carryforward-error`"
                      :errors="field.state.meta.errors"
                    />
                  </UiField>
                </template>
              </settingsForm.Field>
              <settingsForm.Field name="lt_loss_carryforward_usd">
                <template #default="{ field }">
                  <UiField :data-invalid="hasVisibleError(field) ? 'true' : undefined">
                    <FieldLabel :for="`${sectionId}-lt-loss-carryforward`"
                      >LT loss carryforward (USD)</FieldLabel
                    >
                    <Input
                      :id="`${sectionId}-lt-loss-carryforward`"
                      :model-value="field.state.value ?? ''"
                      inputmode="decimal"
                      :aria-invalid="hasVisibleError(field) ? 'true' : undefined"
                      :aria-describedby="
                        fieldErrorId(field, `${sectionId}-lt-loss-carryforward-error`)
                      "
                      @update:model-value="field.handleChange(String($event ?? ''))"
                      @blur="field.handleBlur"
                    />
                    <FieldError
                      v-if="field.state.meta.isTouched && field.state.meta.errors.length"
                      :id="`${sectionId}-lt-loss-carryforward-error`"
                      :errors="field.state.meta.errors"
                    />
                  </UiField>
                </template>
              </settingsForm.Field>
              <settingsForm.Field name="ytd_realized_st_usd">
                <template #default="{ field }">
                  <UiField :data-invalid="hasVisibleError(field) ? 'true' : undefined">
                    <FieldLabel :for="`${sectionId}-ytd-realized-st`"
                      >YTD realized ST gain / loss (USD)</FieldLabel
                    >
                    <Input
                      :id="`${sectionId}-ytd-realized-st`"
                      :model-value="field.state.value ?? ''"
                      inputmode="decimal"
                      :aria-invalid="hasVisibleError(field) ? 'true' : undefined"
                      :aria-describedby="fieldErrorId(field, `${sectionId}-ytd-realized-st-error`)"
                      @update:model-value="field.handleChange(String($event ?? ''))"
                      @blur="field.handleBlur"
                    />
                    <FieldError
                      v-if="field.state.meta.isTouched && field.state.meta.errors.length"
                      :id="`${sectionId}-ytd-realized-st-error`"
                      :errors="field.state.meta.errors"
                    />
                  </UiField>
                </template>
              </settingsForm.Field>
              <settingsForm.Field name="ytd_realized_lt_usd">
                <template #default="{ field }">
                  <UiField :data-invalid="hasVisibleError(field) ? 'true' : undefined">
                    <FieldLabel :for="`${sectionId}-ytd-realized-lt`"
                      >YTD realized LT gain / loss (USD)</FieldLabel
                    >
                    <Input
                      :id="`${sectionId}-ytd-realized-lt`"
                      :model-value="field.state.value ?? ''"
                      inputmode="decimal"
                      :aria-invalid="hasVisibleError(field) ? 'true' : undefined"
                      :aria-describedby="fieldErrorId(field, `${sectionId}-ytd-realized-lt-error`)"
                      @update:model-value="field.handleChange(String($event ?? ''))"
                      @blur="field.handleBlur"
                    />
                    <FieldError
                      v-if="field.state.meta.isTouched && field.state.meta.errors.length"
                      :id="`${sectionId}-ytd-realized-lt-error`"
                      :errors="field.state.meta.errors"
                    />
                  </UiField>
                </template>
              </settingsForm.Field>
              <settingsForm.Field name="ytd_source">
                <template #default="{ field }">
                  <UiField :data-invalid="hasVisibleError(field) ? 'true' : undefined">
                    <FieldLabel :for="`${sectionId}-ytd-source`">YTD source (nullable)</FieldLabel>
                    <Input
                      :id="`${sectionId}-ytd-source`"
                      :model-value="field.state.value ?? ''"
                      placeholder="Broker or manual profile source"
                      :aria-invalid="hasVisibleError(field) ? 'true' : undefined"
                      :aria-describedby="fieldErrorId(field, `${sectionId}-ytd-source-error`)"
                      @update:model-value="field.handleChange(String($event ?? ''))"
                      @blur="field.handleBlur"
                    />
                    <FieldError
                      v-if="field.state.meta.isTouched && field.state.meta.errors.length"
                      :id="`${sectionId}-ytd-source-error`"
                      :errors="field.state.meta.errors"
                    />
                  </UiField>
                </template>
              </settingsForm.Field>
              <settingsForm.Field name="ytd_as_of">
                <template #default="{ field }">
                  <UiField :data-invalid="hasVisibleError(field) ? 'true' : undefined">
                    <FieldLabel :for="`${sectionId}-ytd-as-of`"
                      >YTD as-of date (nullable)</FieldLabel
                    >
                    <Input
                      :id="`${sectionId}-ytd-as-of`"
                      type="date"
                      :model-value="field.state.value ?? ''"
                      :aria-invalid="hasVisibleError(field) ? 'true' : undefined"
                      :aria-describedby="fieldErrorId(field, `${sectionId}-ytd-as-of-error`)"
                      @update:model-value="field.handleChange(String($event ?? ''))"
                      @blur="field.handleBlur"
                    />
                    <FieldError
                      v-if="field.state.meta.isTouched && field.state.meta.errors.length"
                      :id="`${sectionId}-ytd-as-of-error`"
                      :errors="field.state.meta.errors"
                    />
                  </UiField>
                </template>
              </settingsForm.Field>
            </FieldGroup>
            <FieldDescription class="tax-help tw:m-0">
              YTD source and date identify the returned YTD values. Enter explicit manual
              adjustments in the YTD fields; the editor does not combine broker and manual amounts.
            </FieldDescription>
          </div>

          <div class="tax-settings-group tw:flex tw:flex-col tw:gap-3">
            <h3 class="tax-group-title tw:m-0">Retained loss and gain / tax budgets</h3>
            <FieldGroup
              class="tax-fields tw:grid tw:grid-cols-1 tw:gap-4 tw:md:grid-cols-2 tw:xl:grid-cols-3"
            >
              <settingsForm.Field name="target_retained_net_loss_usd">
                <template #default="{ field }">
                  <UiField :data-invalid="hasVisibleError(field) ? 'true' : undefined">
                    <FieldLabel :for="`${sectionId}-target-retained-net-loss`"
                      >Target retained net loss (USD)</FieldLabel
                    >
                    <Input
                      :id="`${sectionId}-target-retained-net-loss`"
                      :model-value="field.state.value ?? ''"
                      inputmode="decimal"
                      :aria-invalid="hasVisibleError(field) ? 'true' : undefined"
                      :aria-describedby="
                        fieldErrorId(field, `${sectionId}-target-retained-net-loss-error`)
                      "
                      @update:model-value="field.handleChange(String($event ?? ''))"
                      @blur="field.handleBlur"
                    />
                    <FieldError
                      v-if="field.state.meta.isTouched && field.state.meta.errors.length"
                      :id="`${sectionId}-target-retained-net-loss-error`"
                      :errors="field.state.meta.errors"
                    />
                  </UiField>
                </template>
              </settingsForm.Field>
              <settingsForm.Field name="ordinary_income_deduction_limit_usd">
                <template #default="{ field }">
                  <UiField :data-invalid="hasVisibleError(field) ? 'true' : undefined">
                    <FieldLabel :for="`${sectionId}-ordinary-income-deduction-limit`">
                      Ordinary-income deduction limit (USD)
                    </FieldLabel>
                    <Input
                      :id="`${sectionId}-ordinary-income-deduction-limit`"
                      :model-value="field.state.value ?? ''"
                      inputmode="decimal"
                      :aria-invalid="hasVisibleError(field) ? 'true' : undefined"
                      :aria-describedby="
                        fieldErrorId(field, `${sectionId}-ordinary-income-deduction-limit-error`)
                      "
                      @update:model-value="field.handleChange(String($event ?? ''))"
                      @blur="field.handleBlur"
                    />
                    <FieldError
                      v-if="field.state.meta.isTouched && field.state.meta.errors.length"
                      :id="`${sectionId}-ordinary-income-deduction-limit-error`"
                      :errors="field.state.meta.errors"
                    />
                  </UiField>
                </template>
              </settingsForm.Field>
              <settingsForm.Field name="carryforward_loss_discount_factor">
                <template #default="{ field }">
                  <UiField :data-invalid="hasVisibleError(field) ? 'true' : undefined">
                    <FieldLabel :for="`${sectionId}-carryforward-loss-discount-factor`">
                      Carryforward loss discount factor (fraction, 0–1)
                    </FieldLabel>
                    <Input
                      :id="`${sectionId}-carryforward-loss-discount-factor`"
                      :model-value="field.state.value ?? ''"
                      inputmode="decimal"
                      :aria-invalid="hasVisibleError(field) ? 'true' : undefined"
                      :aria-describedby="
                        fieldErrorId(field, `${sectionId}-carryforward-loss-discount-factor-error`)
                      "
                      @update:model-value="field.handleChange(String($event ?? ''))"
                      @blur="field.handleBlur"
                    />
                    <FieldError
                      v-if="field.state.meta.isTouched && field.state.meta.errors.length"
                      :id="`${sectionId}-carryforward-loss-discount-factor-error`"
                      :errors="field.state.meta.errors"
                    />
                  </UiField>
                </template>
              </settingsForm.Field>
              <settingsForm.Field name="gain_budget_usd">
                <template #default="{ field }">
                  <UiField :data-invalid="hasVisibleError(field) ? 'true' : undefined">
                    <FieldLabel :for="`${sectionId}-gain-budget`">
                      Incremental realized-gain budget (USD, nullable)
                    </FieldLabel>
                    <Input
                      :id="`${sectionId}-gain-budget`"
                      :model-value="field.state.value ?? ''"
                      inputmode="decimal"
                      placeholder="No limit"
                      :aria-invalid="hasVisibleError(field) ? 'true' : undefined"
                      :aria-describedby="fieldErrorId(field, `${sectionId}-gain-budget-error`)"
                      @update:model-value="field.handleChange(String($event ?? ''))"
                      @blur="field.handleBlur"
                    />
                    <FieldError
                      v-if="field.state.meta.isTouched && field.state.meta.errors.length"
                      :id="`${sectionId}-gain-budget-error`"
                      :errors="field.state.meta.errors"
                    />
                  </UiField>
                </template>
              </settingsForm.Field>
              <settingsForm.Field name="max_incremental_tax_cost_usd">
                <template #default="{ field }">
                  <UiField :data-invalid="hasVisibleError(field) ? 'true' : undefined">
                    <FieldLabel :for="`${sectionId}-max-incremental-tax-cost`">
                      Maximum incremental estimated tax cost (USD, nullable)
                    </FieldLabel>
                    <Input
                      :id="`${sectionId}-max-incremental-tax-cost`"
                      :model-value="field.state.value ?? ''"
                      inputmode="decimal"
                      placeholder="No limit"
                      :aria-invalid="hasVisibleError(field) ? 'true' : undefined"
                      :aria-describedby="
                        fieldErrorId(field, `${sectionId}-max-incremental-tax-cost-error`)
                      "
                      @update:model-value="field.handleChange(String($event ?? ''))"
                      @blur="field.handleBlur"
                    />
                    <FieldError
                      v-if="field.state.meta.isTouched && field.state.meta.errors.length"
                      :id="`${sectionId}-max-incremental-tax-cost-error`"
                      :errors="field.state.meta.errors"
                    />
                  </UiField>
                </template>
              </settingsForm.Field>
              <settingsForm.Field name="st_gain_limit_usd">
                <template #default="{ field }">
                  <UiField :data-invalid="hasVisibleError(field) ? 'true' : undefined">
                    <FieldLabel :for="`${sectionId}-st-gain-limit`"
                      >ST gain limit (USD, nullable)</FieldLabel
                    >
                    <Input
                      :id="`${sectionId}-st-gain-limit`"
                      :model-value="field.state.value ?? ''"
                      inputmode="decimal"
                      placeholder="No separate limit"
                      :aria-invalid="hasVisibleError(field) ? 'true' : undefined"
                      :aria-describedby="fieldErrorId(field, `${sectionId}-st-gain-limit-error`)"
                      @update:model-value="field.handleChange(String($event ?? ''))"
                      @blur="field.handleBlur"
                    />
                    <FieldError
                      v-if="field.state.meta.isTouched && field.state.meta.errors.length"
                      :id="`${sectionId}-st-gain-limit-error`"
                      :errors="field.state.meta.errors"
                    />
                  </UiField>
                </template>
              </settingsForm.Field>
              <settingsForm.Field name="lt_gain_limit_usd">
                <template #default="{ field }">
                  <UiField :data-invalid="hasVisibleError(field) ? 'true' : undefined">
                    <FieldLabel :for="`${sectionId}-lt-gain-limit`"
                      >LT gain limit (USD, nullable)</FieldLabel
                    >
                    <Input
                      :id="`${sectionId}-lt-gain-limit`"
                      :model-value="field.state.value ?? ''"
                      inputmode="decimal"
                      placeholder="No separate limit"
                      :aria-invalid="hasVisibleError(field) ? 'true' : undefined"
                      :aria-describedby="fieldErrorId(field, `${sectionId}-lt-gain-limit-error`)"
                      @update:model-value="field.handleChange(String($event ?? ''))"
                      @blur="field.handleBlur"
                    />
                    <FieldError
                      v-if="field.state.meta.isTouched && field.state.meta.errors.length"
                      :id="`${sectionId}-lt-gain-limit-error`"
                      :errors="field.state.meta.errors"
                    />
                  </UiField>
                </template>
              </settingsForm.Field>
              <settingsForm.Field name="budget_period">
                <template #default="{ field }">
                  <UiField :data-invalid="hasVisibleError(field) ? 'true' : undefined">
                    <FieldLabel :for="`${sectionId}-budget-period`"
                      >Budget period (API value)</FieldLabel
                    >
                    <Input
                      :id="`${sectionId}-budget-period`"
                      :model-value="field.state.value ?? ''"
                      placeholder="e.g. calendar_year"
                      :aria-invalid="hasVisibleError(field) ? 'true' : undefined"
                      :aria-describedby="fieldErrorId(field, `${sectionId}-budget-period-error`)"
                      @update:model-value="field.handleChange(String($event ?? ''))"
                      @blur="field.handleBlur"
                    />
                    <FieldError
                      v-if="field.state.meta.isTouched && field.state.meta.errors.length"
                      :id="`${sectionId}-budget-period-error`"
                      :errors="field.state.meta.errors"
                    />
                  </UiField>
                </template>
              </settingsForm.Field>
            </FieldGroup>
          </div>

          <div class="tax-settings-group tw:flex tw:flex-col tw:gap-3">
            <h3 class="tax-group-title tw:m-0">Small-batch limits and trading preferences</h3>
            <FieldGroup
              class="tax-fields tw:grid tw:grid-cols-1 tw:gap-4 tw:md:grid-cols-2 tw:xl:grid-cols-3"
            >
              <settingsForm.Field name="max_sell_tickers_per_batch">
                <template #default="{ field }">
                  <UiField :data-invalid="hasVisibleError(field) ? 'true' : undefined">
                    <FieldLabel :for="`${sectionId}-max-sell-tickers`"
                      >Maximum sell tickers per batch</FieldLabel
                    >
                    <Input
                      :id="`${sectionId}-max-sell-tickers`"
                      :model-value="field.state.value ?? ''"
                      inputmode="numeric"
                      :aria-invalid="hasVisibleError(field) ? 'true' : undefined"
                      :aria-describedby="fieldErrorId(field, `${sectionId}-max-sell-tickers-error`)"
                      @update:model-value="field.handleChange(String($event ?? ''))"
                      @blur="field.handleBlur"
                    />
                    <FieldError
                      v-if="field.state.meta.isTouched && field.state.meta.errors.length"
                      :id="`${sectionId}-max-sell-tickers-error`"
                      :errors="field.state.meta.errors"
                    />
                  </UiField>
                </template>
              </settingsForm.Field>
              <settingsForm.Field name="max_sell_lots_per_batch">
                <template #default="{ field }">
                  <UiField :data-invalid="hasVisibleError(field) ? 'true' : undefined">
                    <FieldLabel :for="`${sectionId}-max-sell-lots`"
                      >Maximum sell lots per batch</FieldLabel
                    >
                    <Input
                      :id="`${sectionId}-max-sell-lots`"
                      :model-value="field.state.value ?? ''"
                      inputmode="numeric"
                      :aria-invalid="hasVisibleError(field) ? 'true' : undefined"
                      :aria-describedby="fieldErrorId(field, `${sectionId}-max-sell-lots-error`)"
                      @update:model-value="field.handleChange(String($event ?? ''))"
                      @blur="field.handleBlur"
                    />
                    <FieldError
                      v-if="field.state.meta.isTouched && field.state.meta.errors.length"
                      :id="`${sectionId}-max-sell-lots-error`"
                      :errors="field.state.meta.errors"
                    />
                  </UiField>
                </template>
              </settingsForm.Field>
              <settingsForm.Field name="max_total_orders_per_batch">
                <template #default="{ field }">
                  <UiField :data-invalid="hasVisibleError(field) ? 'true' : undefined">
                    <FieldLabel :for="`${sectionId}-max-total-orders`"
                      >Maximum total orders per batch</FieldLabel
                    >
                    <Input
                      :id="`${sectionId}-max-total-orders`"
                      :model-value="field.state.value ?? ''"
                      inputmode="numeric"
                      :aria-invalid="hasVisibleError(field) ? 'true' : undefined"
                      :aria-describedby="fieldErrorId(field, `${sectionId}-max-total-orders-error`)"
                      @update:model-value="field.handleChange(String($event ?? ''))"
                      @blur="field.handleBlur"
                    />
                    <FieldError
                      v-if="field.state.meta.isTouched && field.state.meta.errors.length"
                      :id="`${sectionId}-max-total-orders-error`"
                      :errors="field.state.meta.errors"
                    />
                  </UiField>
                </template>
              </settingsForm.Field>
              <settingsForm.Field name="max_batch_turnover_pct">
                <template #default="{ field }">
                  <UiField :data-invalid="hasVisibleError(field) ? 'true' : undefined">
                    <FieldLabel :for="`${sectionId}-max-batch-turnover`"
                      >Maximum batch turnover (%)</FieldLabel
                    >
                    <Input
                      :id="`${sectionId}-max-batch-turnover`"
                      :model-value="field.state.value ?? ''"
                      inputmode="decimal"
                      :aria-invalid="hasVisibleError(field) ? 'true' : undefined"
                      :aria-describedby="
                        fieldErrorId(field, `${sectionId}-max-batch-turnover-error`)
                      "
                      @update:model-value="field.handleChange(String($event ?? ''))"
                      @blur="field.handleBlur"
                    />
                    <FieldError
                      v-if="field.state.meta.isTouched && field.state.meta.errors.length"
                      :id="`${sectionId}-max-batch-turnover-error`"
                      :errors="field.state.meta.errors"
                    />
                  </UiField>
                </template>
              </settingsForm.Field>
              <settingsForm.Field name="min_buy_order_notional_usd">
                <template #default="{ field }">
                  <UiField :data-invalid="hasVisibleError(field) ? 'true' : undefined">
                    <FieldLabel :for="`${sectionId}-min-buy-notional`">
                      Minimum replacement BUY notional (USD)
                    </FieldLabel>
                    <Input
                      :id="`${sectionId}-min-buy-notional`"
                      :model-value="field.state.value ?? ''"
                      inputmode="decimal"
                      :aria-invalid="hasVisibleError(field) ? 'true' : undefined"
                      :aria-describedby="fieldErrorId(field, `${sectionId}-min-buy-notional-error`)"
                      @update:model-value="field.handleChange(String($event ?? ''))"
                      @blur="field.handleBlur"
                    />
                    <FieldError
                      v-if="field.state.meta.isTouched && field.state.meta.errors.length"
                      :id="`${sectionId}-min-buy-notional-error`"
                      :errors="field.state.meta.errors"
                    />
                  </UiField>
                </template>
              </settingsForm.Field>
              <settingsForm.Field name="cash_reserve_usd">
                <template #default="{ field }">
                  <UiField :data-invalid="hasVisibleError(field) ? 'true' : undefined">
                    <FieldLabel :for="`${sectionId}-cash-reserve`">Cash reserve (USD)</FieldLabel>
                    <Input
                      :id="`${sectionId}-cash-reserve`"
                      :model-value="field.state.value ?? ''"
                      inputmode="decimal"
                      :aria-invalid="hasVisibleError(field) ? 'true' : undefined"
                      :aria-describedby="fieldErrorId(field, `${sectionId}-cash-reserve-error`)"
                      @update:model-value="field.handleChange(String($event ?? ''))"
                      @blur="field.handleBlur"
                    />
                    <FieldError
                      v-if="field.state.meta.isTouched && field.state.meta.errors.length"
                      :id="`${sectionId}-cash-reserve-error`"
                      :errors="field.state.meta.errors"
                    />
                  </UiField>
                </template>
              </settingsForm.Field>
            </FieldGroup>
            <FieldGroup
              class="tax-toggle-grid tw:grid tw:grid-cols-1 tw:gap-4 tw:md:grid-cols-2 tw:xl:grid-cols-4"
            >
              <settingsForm.Field name="prefer_etf_buys">
                <template #default="{ field }">
                  <UiField :data-invalid="hasVisibleError(field) ? 'true' : undefined">
                    <FieldLabel
                      :id="`${sectionId}-prefer-etf-buys-label`"
                      :for="`${sectionId}-prefer-etf-buys`"
                      >Prefer ETF buys</FieldLabel
                    >
                    <Select
                      :model-value="
                        field.state.value === null
                          ? 'choose'
                          : field.state.value
                            ? 'enabled'
                            : 'disabled'
                      "
                      @update:model-value="field.handleChange(toggleValue($event))"
                    >
                      <SelectTrigger
                        :id="`${sectionId}-prefer-etf-buys`"
                        :aria-labelledby="`${sectionId}-prefer-etf-buys-label`"
                        class="tw:w-full"
                        :aria-invalid="hasVisibleError(field) ? 'true' : undefined"
                        :aria-describedby="
                          fieldErrorId(field, `${sectionId}-prefer-etf-buys-error`)
                        "
                        @blur="field.handleBlur"
                      >
                        <SelectValue placeholder="Choose" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectGroup>
                          <SelectItem value="choose">Choose</SelectItem>
                          <SelectItem value="enabled">Enabled</SelectItem>
                          <SelectItem value="disabled">Disabled</SelectItem>
                        </SelectGroup>
                      </SelectContent>
                    </Select>
                    <FieldError
                      v-if="field.state.meta.isTouched && field.state.meta.errors.length"
                      :id="`${sectionId}-prefer-etf-buys-error`"
                      :errors="field.state.meta.errors"
                    />
                  </UiField>
                </template>
              </settingsForm.Field>
              <settingsForm.Field name="allow_gain_sales">
                <template #default="{ field }">
                  <UiField :data-invalid="hasVisibleError(field) ? 'true' : undefined">
                    <FieldLabel
                      :id="`${sectionId}-allow-gain-sales-label`"
                      :for="`${sectionId}-allow-gain-sales`"
                      >Allow appreciated-gain sales</FieldLabel
                    >
                    <Select
                      :model-value="
                        field.state.value === null
                          ? 'choose'
                          : field.state.value
                            ? 'enabled'
                            : 'disabled'
                      "
                      @update:model-value="field.handleChange(toggleValue($event))"
                    >
                      <SelectTrigger
                        :id="`${sectionId}-allow-gain-sales`"
                        :aria-labelledby="`${sectionId}-allow-gain-sales-label`"
                        class="tw:w-full"
                        :aria-invalid="hasVisibleError(field) ? 'true' : undefined"
                        :aria-describedby="
                          fieldErrorId(field, `${sectionId}-allow-gain-sales-error`)
                        "
                        @blur="field.handleBlur"
                      >
                        <SelectValue placeholder="Choose" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectGroup>
                          <SelectItem value="choose">Choose</SelectItem>
                          <SelectItem value="enabled">Enabled</SelectItem>
                          <SelectItem value="disabled">Disabled</SelectItem>
                        </SelectGroup>
                      </SelectContent>
                    </Select>
                    <FieldError
                      v-if="field.state.meta.isTouched && field.state.meta.errors.length"
                      :id="`${sectionId}-allow-gain-sales-error`"
                      :errors="field.state.meta.errors"
                    />
                  </UiField>
                </template>
              </settingsForm.Field>
              <settingsForm.Field name="permit_etf_harvest">
                <template #default="{ field }">
                  <UiField :data-invalid="hasVisibleError(field) ? 'true' : undefined">
                    <FieldLabel
                      :id="`${sectionId}-permit-etf-harvest-label`"
                      :for="`${sectionId}-permit-etf-harvest`"
                      >Permit ETF harvesting</FieldLabel
                    >
                    <Select
                      :model-value="
                        field.state.value === null
                          ? 'choose'
                          : field.state.value
                            ? 'enabled'
                            : 'disabled'
                      "
                      @update:model-value="field.handleChange(toggleValue($event))"
                    >
                      <SelectTrigger
                        :id="`${sectionId}-permit-etf-harvest`"
                        :aria-labelledby="`${sectionId}-permit-etf-harvest-label`"
                        class="tw:w-full"
                        :aria-invalid="hasVisibleError(field) ? 'true' : undefined"
                        :aria-describedby="
                          fieldErrorId(field, `${sectionId}-permit-etf-harvest-error`)
                        "
                        @blur="field.handleBlur"
                      >
                        <SelectValue placeholder="Choose" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectGroup>
                          <SelectItem value="choose">Choose</SelectItem>
                          <SelectItem value="enabled">Enabled</SelectItem>
                          <SelectItem value="disabled">Disabled</SelectItem>
                        </SelectGroup>
                      </SelectContent>
                    </Select>
                    <FieldError
                      v-if="field.state.meta.isTouched && field.state.meta.errors.length"
                      :id="`${sectionId}-permit-etf-harvest-error`"
                      :errors="field.state.meta.errors"
                    />
                  </UiField>
                </template>
              </settingsForm.Field>
              <settingsForm.Field name="permit_muni_exit">
                <template #default="{ field }">
                  <UiField :data-invalid="hasVisibleError(field) ? 'true' : undefined">
                    <FieldLabel
                      :id="`${sectionId}-permit-muni-exit-label`"
                      :for="`${sectionId}-permit-muni-exit`"
                      >Permit municipal-bond exit</FieldLabel
                    >
                    <Select
                      :model-value="
                        field.state.value === null
                          ? 'choose'
                          : field.state.value
                            ? 'enabled'
                            : 'disabled'
                      "
                      @update:model-value="field.handleChange(toggleValue($event))"
                    >
                      <SelectTrigger
                        :id="`${sectionId}-permit-muni-exit`"
                        :aria-labelledby="`${sectionId}-permit-muni-exit-label`"
                        class="tw:w-full"
                        :aria-invalid="hasVisibleError(field) ? 'true' : undefined"
                        :aria-describedby="
                          fieldErrorId(field, `${sectionId}-permit-muni-exit-error`)
                        "
                        @blur="field.handleBlur"
                      >
                        <SelectValue placeholder="Choose" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectGroup>
                          <SelectItem value="choose">Choose</SelectItem>
                          <SelectItem value="enabled">Enabled</SelectItem>
                          <SelectItem value="disabled">Disabled</SelectItem>
                        </SelectGroup>
                      </SelectContent>
                    </Select>
                    <FieldError
                      v-if="field.state.meta.isTouched && field.state.meta.errors.length"
                      :id="`${sectionId}-permit-muni-exit-error`"
                      :errors="field.state.meta.errors"
                    />
                  </UiField>
                </template>
              </settingsForm.Field>
            </FieldGroup>
            <FieldDescription class="tax-help tw:m-0">
              No minimum SELL notional is configured here. The minimum notional applies only to
              replacement ETF BUY legs.
            </FieldDescription>
          </div>
        </form>
      </CardContent>
    </Card>
  </section>
</template>

<script setup lang="ts">
import { useForm } from '@tanstack/vue-form';
import { useId, watch } from 'vue';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import {
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel,
  Field as UiField,
} from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import type { EditablePolicySettings } from '@/pages/policy-form';
import { policyTaxSettingsSchema } from '@/forms/policy-tax-settings';

const props = defineProps<{ settings: EditablePolicySettings; sourceRevisionId: string | null }>();
const emit = defineEmits<{
  'update:settings': [settings: EditablePolicySettings];
}>();
const sectionId = useId();
const settingsForm = useForm({
  formId: `${sectionId}-form`,
  defaultValues: { ...props.settings },
  validators: { onChange: policyTaxSettingsSchema },
});
const formValues = settingsForm.useSelector((state) => state.values);

function sameSettings(left: EditablePolicySettings, right: EditablePolicySettings): boolean {
  return (Object.keys(left) as Array<keyof EditablePolicySettings>).every(
    (key) => left[key] === right[key],
  );
}

type FieldErrorState = {
  state: { meta: { isTouched: boolean; errors: readonly unknown[] } };
};

function hasVisibleError(field: FieldErrorState): boolean {
  return field.state.meta.isTouched && field.state.meta.errors.length > 0;
}

function fieldErrorId(field: FieldErrorState, id: string): string | undefined {
  return hasVisibleError(field) ? id : undefined;
}

function toggleValue(value: unknown): boolean | null {
  if (value === 'enabled') return true;
  if (value === 'disabled') return false;
  return null;
}

watch(
  formValues,
  (settings) => {
    if (!sameSettings(settings, props.settings)) emit('update:settings', { ...settings });
  },
  { deep: true, flush: 'sync' },
);

watch(
  () => props.sourceRevisionId,
  () => settingsForm.reset({ ...props.settings }),
  { flush: 'sync' },
);

watch(
  () => props.settings,
  (settings) => {
    if (!sameSettings(formValues.value, settings)) settingsForm.reset({ ...settings });
  },
  { deep: true, flush: 'sync' },
);
</script>

<style scoped>
:global([data-policy-tax-settings-root]) {
  color: var(--foreground);
}

:global([data-policy-tax-settings-root] .tax-title) {
  color: var(--foreground);
  font-size: var(--tw-text-lg);
  font-weight: var(--tw-font-weight-semibold);
  letter-spacing: var(--tw-tracking-tight);
  line-height: var(--tw-text-lg--line-height);
}

:global([data-policy-tax-settings-root] .tax-group-title) {
  color: var(--foreground);
  font-size: var(--tw-text-sm);
  font-weight: var(--tw-font-weight-semibold);
  line-height: var(--tw-text-sm--line-height);
}

:global([data-policy-tax-settings-root] .tax-intro),
:global([data-policy-tax-settings-root] .tax-help) {
  color: var(--muted-foreground);
  font-size: var(--tw-text-sm);
  font-weight: var(--tw-font-weight-normal);
  line-height: var(--tw-text-sm--line-height);
}

:global([data-policy-tax-settings-root] input[data-slot='input']) {
  appearance: none;
  border: 1px solid var(--input);
  border-radius: var(--radius-md);
  background-color: transparent;
  color: var(--foreground);
  font-family: inherit;
  font-size: var(--tw-text-sm);
  line-height: var(--tw-text-sm--line-height);
}

:global([data-policy-tax-settings-root] button[data-slot='select-trigger']) {
  appearance: none;
  border: 1px solid var(--input);
  background-color: transparent;
  color: var(--foreground);
  font-family: inherit;
  font-size: var(--tw-text-sm);
  line-height: var(--tw-text-sm--line-height);
  text-transform: none;
}
</style>

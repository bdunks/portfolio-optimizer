import { z } from 'zod';
import type { EditablePolicySettings } from '@/pages/policy-form';

const decimalPattern = /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$/;
const positiveIntegerPattern = /^[1-9]\d*$/;
const maxSafeInteger = 9007199254740991n;

function requiredDecimal(label: string) {
  return z.string().superRefine((value, context) => {
    if (!value.trim()) {
      context.addIssue({
        code: 'custom',
        message: `${label} is required; blank values are not changed to zero.`,
      });
    } else if (!decimalPattern.test(value.trim())) {
      context.addIssue({
        code: 'custom',
        message: `${label} must be an exact decimal string.`,
      });
    }
  });
}

function nullableDecimal(label: string, nonnegative = false) {
  return z
    .string()
    .nullable()
    .superRefine((value, context) => {
      if (
        value !== null &&
        value.trim() &&
        (!decimalPattern.test(value.trim()) || (nonnegative && value.trim().startsWith('-')))
      ) {
        context.addIssue({
          code: 'custom',
          message: `${label} must be an exact decimal string or blank (null).`,
        });
      }
    });
}

function requiredBatchInteger(label: string) {
  return z.string().superRefine((value, context) => {
    if (!positiveIntegerPattern.test(value.trim())) {
      context.addIssue({
        code: 'custom',
        message: `${label} must be a positive safe whole number.`,
      });
    } else if (BigInt(value) > maxSafeInteger) {
      context.addIssue({
        code: 'custom',
        message: `${label} must be a positive safe whole number.`,
      });
    }
  });
}

function requiredToggle() {
  return z
    .boolean()
    .nullable()
    .refine((value) => value !== null, {
      message: 'Choose this policy rule explicitly.',
    });
}

export const policyTaxSettingsSchema = z.object({
  short_term_tax_rate: nullableDecimal('ST tax rate'),
  long_term_tax_rate: nullableDecimal('LT tax rate'),
  st_loss_carryforward_usd: requiredDecimal('ST loss carryforward'),
  lt_loss_carryforward_usd: requiredDecimal('LT loss carryforward'),
  ytd_realized_st_usd: requiredDecimal('YTD realized ST'),
  ytd_realized_lt_usd: requiredDecimal('YTD realized LT'),
  ytd_source: z.string().nullable(),
  ytd_as_of: z
    .string()
    .nullable()
    .superRefine((value, context) => {
      if (value !== null && value.trim() && !/^\d{4}-\d{2}-\d{2}$/.test(value.trim())) {
        context.addIssue({ code: 'custom', message: 'YTD as-of must be a date or blank (null).' });
      }
    }),
  target_retained_net_loss_usd: requiredDecimal('retained net loss target'),
  ordinary_income_deduction_limit_usd: requiredDecimal('ordinary-income deduction limit'),
  carryforward_loss_discount_factor: requiredDecimal('carryforward discount factor'),
  gain_budget_usd: nullableDecimal('gain budget'),
  max_incremental_tax_cost_usd: nullableDecimal('maximum tax cost'),
  st_gain_limit_usd: nullableDecimal('ST gain limit'),
  lt_gain_limit_usd: nullableDecimal('LT gain limit'),
  budget_period: z.string().superRefine((value, context) => {
    if (!value.trim()) {
      context.addIssue({ code: 'custom', message: 'Budget period is required.' });
    }
  }),
  max_sell_tickers_per_batch: requiredBatchInteger('max sell tickers per batch'),
  max_sell_lots_per_batch: requiredBatchInteger('max sell lots per batch'),
  max_total_orders_per_batch: requiredBatchInteger('max total orders per batch'),
  max_batch_turnover_pct: requiredDecimal('maximum batch turnover'),
  min_buy_order_notional_usd: requiredDecimal('minimum replacement BUY notional'),
  cash_reserve_usd: requiredDecimal('cash reserve'),
  prefer_etf_buys: requiredToggle(),
  allow_gain_sales: requiredToggle(),
  permit_etf_harvest: requiredToggle(),
  permit_muni_exit: requiredToggle(),
  objective_band_weight: nullableDecimal('band objective weight', true),
  objective_allocation_weight: nullableDecimal('allocation objective weight', true),
  objective_tax_weight: nullableDecimal('tax objective weight', true),
  objective_trading_cost_weight: nullableDecimal('trading-cost objective weight', true),
  objective_turnover_weight: nullableDecimal('turnover objective weight', true),
  objective_cleanup_weight: nullableDecimal('cleanup objective weight', true),
  estimated_spread_bps: nullableDecimal('estimated spread', true),
  estimated_fee_per_order_usd: nullableDecimal('estimated fee per order', true),
}) satisfies z.ZodType<EditablePolicySettings>;

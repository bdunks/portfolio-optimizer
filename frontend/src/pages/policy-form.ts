import type {
  PolicyDraftInput,
  PolicyRevisionResponse,
  PolicySettingsInput,
  PolicySettingsResponse,
  PolicySleeveResponse,
  SleeveInput,
} from '@/types/api';

export type EditableSleeve = SleeveInput & {
  target_pct: string;
  drift_band_pp: string;
};

function decimalParts(value: string): { coefficient: bigint; scale: number } | null {
  const match = /^([+-]?)(\d*)(?:\.(\d*))?$/.exec(value.trim());
  if (!match || (!match[2] && !match[3])) return null;
  const fraction = match[3] ?? '';
  const integer = match[2] || '0';
  const coefficient = BigInt(`${match[1] === '-' ? '-' : ''}${integer}${fraction}`);
  return { coefficient, scale: fraction.length };
}

export function exactDecimalSumIsHundred(values: readonly string[]): boolean {
  if (values.length === 0) return false;
  const parts = values.map(decimalParts);
  if (parts.some((part) => part === null)) return false;
  const decimals = parts as Array<{ coefficient: bigint; scale: number }>;
  const scale = Math.max(...decimals.map((part) => part.scale));
  const sum = decimals.reduce(
    (total, part) => total + part.coefficient * 10n ** BigInt(scale - part.scale),
    0n,
  );
  return sum === 100n * 10n ** BigInt(scale);
}

export function targetActivationIssues(sleeves: readonly EditableSleeve[]): string[] {
  const enabled = sleeves.filter((sleeve) => sleeve.enabled !== false);
  const topLevel = enabled.filter((sleeve) => !sleeve.parent_sleeve_key);
  const issues: string[] = [];
  if (topLevel.length === 0) {
    issues.push('At least one enabled top-level sleeve is required.');
  } else if (!exactDecimalSumIsHundred(topLevel.map((sleeve) => sleeve.target_pct))) {
    issues.push('Enabled top-level sleeve targets must total exactly 100%.');
  }
  for (const parent of enabled) {
    const children = enabled.filter((sleeve) => sleeve.parent_sleeve_key === parent.sleeve_key);
    if (children.length && !exactDecimalSumIsHundred(children.map((sleeve) => sleeve.target_pct))) {
      issues.push(
        `Enabled child targets of “${parent.display_name || parent.sleeve_key}” must total exactly 100%.`,
      );
    }
  }
  return issues;
}

export function editableSleevesFromRevision(
  sleeves: readonly PolicySleeveResponse[],
): EditableSleeve[] {
  return sleeves.map((sleeve) => ({
    sleeve_key: sleeve.sleeve_key,
    display_name: sleeve.display_name,
    sort_order: sleeve.sort_order,
    parent_sleeve_key: sleeve.parent_sleeve_key,
    target_pct: sleeve.target_pct,
    drift_band_pp: sleeve.drift_band_pp,
    is_direct_index_container: sleeve.is_direct_index_container,
    is_direct_index_sleeve: sleeve.is_direct_index_sleeve,
    is_cash_sleeve: sleeve.is_cash_sleeve,
    enabled: sleeve.enabled,
  }));
}

export function settingsFromRevision(settings: PolicySettingsResponse): PolicySettingsInput {
  return {
    short_term_tax_rate: settings.short_term_tax_rate,
    long_term_tax_rate: settings.long_term_tax_rate,
    st_loss_carryforward_usd: settings.st_loss_carryforward_usd,
    lt_loss_carryforward_usd: settings.lt_loss_carryforward_usd,
    ytd_realized_st_usd: settings.ytd_realized_st_usd,
    ytd_realized_lt_usd: settings.ytd_realized_lt_usd,
    ytd_source: settings.ytd_source,
    ytd_as_of: settings.ytd_as_of,
    target_retained_net_loss_usd: settings.target_retained_net_loss_usd,
    ordinary_income_deduction_limit_usd: settings.ordinary_income_deduction_limit_usd,
    carryforward_loss_discount_factor: settings.carryforward_loss_discount_factor,
    gain_budget_usd: settings.gain_budget_usd,
    max_incremental_tax_cost_usd: settings.max_incremental_tax_cost_usd,
    st_gain_limit_usd: settings.st_gain_limit_usd,
    lt_gain_limit_usd: settings.lt_gain_limit_usd,
    budget_period: settings.budget_period,
    max_sell_tickers_per_batch: settings.max_sell_tickers_per_batch,
    max_sell_lots_per_batch: settings.max_sell_lots_per_batch,
    max_total_orders_per_batch: settings.max_total_orders_per_batch,
    max_batch_turnover_pct: settings.max_batch_turnover_pct,
    min_buy_order_notional_usd: settings.min_buy_order_notional_usd,
    cash_reserve_usd: settings.cash_reserve_usd,
    prefer_etf_buys: settings.prefer_etf_buys,
    allow_gain_sales: settings.allow_gain_sales,
    permit_etf_harvest: settings.permit_etf_harvest,
    permit_muni_exit: settings.permit_muni_exit,
  };
}

export function revisionToDraft(revision: PolicyRevisionResponse): PolicyDraftInput {
  return {
    source_revision_id: revision.id,
    settings: settingsFromRevision(revision.settings),
    sleeves: editableSleevesFromRevision(revision.sleeves),
    allowed_securities: revision.allowed_securities.map((security) => ({ ...security })),
    overrides: revision.overrides.map((override) => ({ ...override })),
    reassignments: {},
  };
}

import type {
  AllowedSecurityInput,
  OverrideInput,
  PolicyDraftInput,
  PolicyRevisionResponse,
  PolicySettingsInput,
  PolicySettingsResponse,
  PolicySleeveResponse,
  SleeveInput,
} from '@/types/api';

export type EditableSleeve = Omit<SleeveInput, 'target_pct' | 'drift_band_pp'> & {
  target_pct: string;
  drift_band_pp: string;
};

type EditorSettingValue<T> =
  Exclude<T, undefined> extends boolean
    ? boolean | null
    : Exclude<T, undefined> extends number
      ? string
      : string | null;

/** Editable settings stay keyed and typed from the generated API input contract. */
export type EditablePolicySettings = {
  [Key in keyof PolicySettingsInput]-?: EditorSettingValue<PolicySettingsInput[Key]>;
};

export type EditablePolicyDraft = {
  settings: EditablePolicySettings;
  sleeves: EditableSleeve[];
  allowedSecurities: AllowedSecurityInput[];
  overrides: OverrideInput[];
  reassignments: Record<string, string>;
  reassignmentHoldings: Record<string, string[]>;
};

const decimalPattern = /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$/;
const positiveIntegerPattern = /^[1-9]\d*$/;
const batchIntegerFields = [
  'max_sell_tickers_per_batch',
  'max_sell_lots_per_batch',
  'max_total_orders_per_batch',
] as const;
const requiredDecimalFields = [
  ['ST loss carryforward', 'st_loss_carryforward_usd'],
  ['LT loss carryforward', 'lt_loss_carryforward_usd'],
  ['YTD realized ST', 'ytd_realized_st_usd'],
  ['YTD realized LT', 'ytd_realized_lt_usd'],
  ['retained net loss target', 'target_retained_net_loss_usd'],
  ['ordinary-income deduction limit', 'ordinary_income_deduction_limit_usd'],
  ['carryforward discount factor', 'carryforward_loss_discount_factor'],
  ['maximum batch turnover', 'max_batch_turnover_pct'],
  ['minimum replacement BUY notional', 'min_buy_order_notional_usd'],
  ['cash reserve', 'cash_reserve_usd'],
] as const satisfies ReadonlyArray<[string, keyof EditablePolicySettings]>;
const nullableDecimalFields = [
  ['ST tax rate', 'short_term_tax_rate'],
  ['LT tax rate', 'long_term_tax_rate'],
  ['gain budget', 'gain_budget_usd'],
  ['maximum tax cost', 'max_incremental_tax_cost_usd'],
  ['ST gain limit', 'st_gain_limit_usd'],
  ['LT gain limit', 'lt_gain_limit_usd'],
] as const satisfies ReadonlyArray<[string, keyof EditablePolicySettings]>;
const decimalSettingKeys = new Set<keyof EditablePolicySettings>([
  ...requiredDecimalFields.map(([, key]) => key),
  ...nullableDecimalFields.map(([, key]) => key),
]);
const maxNormalizedDecimalLength = 4096;
const scientificDecimalPattern = /^([+-]?)(?:(\d+)(?:\.(\d*))?|\.(\d+))[eE]([+-]?\d+)$/;

export function normalizeServerDecimalNotation(value: string): string {
  if (value.length > maxNormalizedDecimalLength) return value;
  const match = scientificDecimalPattern.exec(value);
  if (!match) return value;

  const sign = match[1] ?? '';
  const integer = match[2] ?? '';
  const fraction = match[3] ?? match[4] ?? '';
  const digits = `${integer}${fraction}`;
  if (/^0+$/.test(digits)) return '0';

  const exponentText = match[5]!;
  if (exponentText.length > 6) return value;
  const exponent = BigInt(exponentText);
  if (
    exponent > BigInt(maxNormalizedDecimalLength) ||
    exponent < -BigInt(maxNormalizedDecimalLength)
  )
    return value;

  const point = integer.length + Number(exponent);
  const normalized =
    point <= 0
      ? `0.${'0'.repeat(-point)}${digits}`
      : point >= digits.length
        ? `${digits}${'0'.repeat(point - digits.length)}`
        : `${digits.slice(0, point)}.${digits.slice(point)}`;
  const result = `${sign}${normalized}`;
  return result.length <= maxNormalizedDecimalLength ? result : value;
}
const booleanFields = [
  'prefer_etf_buys',
  'allow_gain_sales',
  'permit_etf_harvest',
  'permit_muni_exit',
] as const satisfies ReadonlyArray<keyof EditablePolicySettings>;

export function createEmptyPolicySettings(): EditablePolicySettings {
  return {
    short_term_tax_rate: '',
    long_term_tax_rate: '',
    st_loss_carryforward_usd: '',
    lt_loss_carryforward_usd: '',
    ytd_realized_st_usd: '',
    ytd_realized_lt_usd: '',
    ytd_source: '',
    ytd_as_of: '',
    target_retained_net_loss_usd: '',
    ordinary_income_deduction_limit_usd: '',
    carryforward_loss_discount_factor: '',
    gain_budget_usd: '',
    max_incremental_tax_cost_usd: '',
    st_gain_limit_usd: '',
    lt_gain_limit_usd: '',
    budget_period: '',
    max_sell_tickers_per_batch: '',
    max_sell_lots_per_batch: '',
    max_total_orders_per_batch: '',
    max_batch_turnover_pct: '',
    min_buy_order_notional_usd: '',
    cash_reserve_usd: '',
    prefer_etf_buys: null,
    allow_gain_sales: null,
    permit_etf_harvest: null,
    permit_muni_exit: null,
  };
}

export function createEmptyPolicyDraft(): EditablePolicyDraft {
  return {
    settings: createEmptyPolicySettings(),
    sleeves: [],
    allowedSecurities: [],
    overrides: [],
    reassignments: {},
    reassignmentHoldings: {},
  };
}

export function editableSettingsFromRevision(
  settings: PolicySettingsResponse,
): EditablePolicySettings {
  const editable = {} as EditablePolicySettings;
  for (const key of Object.keys(createEmptyPolicySettings()) as Array<keyof PolicySettingsInput>) {
    const value = settings[key];
    (editable as Record<string, unknown>)[key] =
      typeof value === 'number'
        ? String(value)
        : typeof value === 'string' && decimalSettingKeys.has(key)
          ? normalizeServerDecimalNotation(value)
          : value;
  }
  return editable;
}

export function editableSleevesFromRevision(
  sleeves: readonly PolicySleeveResponse[],
): EditableSleeve[] {
  return sleeves.map((sleeve) => ({
    sleeve_key: sleeve.sleeve_key,
    display_name: sleeve.display_name,
    sort_order: sleeve.sort_order,
    parent_sleeve_key: sleeve.parent_sleeve_key,
    target_pct: normalizeServerDecimalNotation(sleeve.target_pct),
    drift_band_pp: normalizeServerDecimalNotation(sleeve.drift_band_pp),
    is_direct_index_container: sleeve.is_direct_index_container,
    is_direct_index_sleeve: sleeve.is_direct_index_sleeve,
    is_transition_destination: sleeve.is_transition_destination,
    is_cash_sleeve: sleeve.is_cash_sleeve,
    enabled: sleeve.enabled,
  }));
}

export function revisionToDraft(revision: PolicyRevisionResponse): EditablePolicyDraft {
  return {
    settings: editableSettingsFromRevision(revision.settings),
    sleeves: editableSleevesFromRevision(revision.sleeves),
    allowedSecurities: revision.allowed_securities.map((security) => ({ ...security })),
    overrides: revision.overrides.map((override) => ({ ...override })),
    reassignments: {},
    reassignmentHoldings: {},
  };
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

function decimalParts(value: string): { coefficient: bigint; scale: number } | null {
  const match = /^([+-]?)(\d*)(?:\.(\d*))?$/.exec(value.trim());
  if (!match || (!match[2] && !match[3])) return null;
  const fraction = match[3] ?? '';
  const integer = match[2] || '0';
  const coefficient = BigInt(`${match[1] === '-' ? '-' : ''}${integer}${fraction}`);
  return { coefficient, scale: fraction.length };
}

export type USTransitionSelection = {
  usKey: string;
  legacyKey: string;
  destinationKey: string;
  destinationTarget: string;
};

export type USTransitionApplyResult = {
  sleeves: EditableSleeve[] | null;
  issues: string[];
  ordinaryTwoChild: boolean;
};

/** Return an exact 100-minus-target decimal string, preserving the input scale. */
export function exactHundredComplement(value: string): string | null {
  const parts = decimalParts(value);
  if (!parts || parts.coefficient < 0n) return null;
  const scaleFactor = 10n ** BigInt(parts.scale);
  const hundred = 100n * scaleFactor;
  if (parts.coefficient > hundred) return null;
  const complement = hundred - parts.coefficient;
  const whole = complement / scaleFactor;
  if (parts.scale === 0) return whole.toString();
  const fraction = (complement % scaleFactor).toString().padStart(parts.scale, '0');
  return `${whole}.${fraction}`;
}

function isEnabledSleeve(sleeve: EditableSleeve | undefined): sleeve is EditableSleeve {
  return sleeve !== undefined && sleeve.enabled !== false;
}

export function isStrictDescendantOf(
  sleeves: readonly EditableSleeve[],
  sleeveKey: string,
  ancestorKey: string,
): boolean {
  if (sleeveKey === ancestorKey) return false;
  const visited = new Set<string>();
  let current = sleeves.find((sleeve) => sleeve.sleeve_key === sleeveKey);
  while (current?.parent_sleeve_key) {
    const parentKey = current.parent_sleeve_key;
    if (parentKey === ancestorKey) return true;
    if (visited.has(parentKey)) return false;
    visited.add(parentKey);
    current = sleeves.find((sleeve) => sleeve.sleeve_key === parentKey);
  }
  return false;
}

export function isOrdinaryTwoChildUSTransition(
  sleeves: readonly EditableSleeve[],
  selection: Pick<USTransitionSelection, 'usKey' | 'legacyKey' | 'destinationKey'>,
): boolean {
  if (!selection.usKey || !selection.legacyKey || !selection.destinationKey) return false;
  const children = sleeves.filter(
    (sleeve) => sleeve.enabled !== false && sleeve.parent_sleeve_key === selection.usKey,
  );
  return (
    children.length === 2 &&
    children.some((sleeve) => sleeve.sleeve_key === selection.legacyKey) &&
    children.some((sleeve) => sleeve.sleeve_key === selection.destinationKey) &&
    selection.legacyKey !== selection.destinationKey
  );
}

const unsupportedLegacyMappingMessage =
  'Existing Legacy routing uses multiple sleeves or is not a direct child of one US allocation. Guided editing is unavailable; custom Legacy role mappings are preserved and read-only in guided settings. Existing explicit nested targets can still be edited in the allocation editor.';

export function unsupportedLegacyMappingIssue(
  sleeves: readonly EditableSleeve[],
  selectedUsKey?: string,
): string | null {
  const legacySleeves = sleeves.filter((sleeve) => sleeve.is_direct_index_sleeve === true);
  if (legacySleeves.length > 1) return unsupportedLegacyMappingMessage;
  if (legacySleeves.length === 0) return null;

  const containers = sleeves.filter((sleeve) => sleeve.is_direct_index_container === true);
  if (containers.length > 1) return unsupportedLegacyMappingMessage;
  if (containers.length === 1) {
    return legacySleeves[0]?.parent_sleeve_key === containers[0]?.sleeve_key
      ? null
      : unsupportedLegacyMappingMessage;
  }
  if (selectedUsKey && legacySleeves[0]?.parent_sleeve_key !== selectedUsKey) {
    return unsupportedLegacyMappingMessage;
  }
  return null;
}

export function applyExplicitUSTransitionSettings(
  sleeves: readonly EditableSleeve[],
  selection: USTransitionSelection,
): USTransitionApplyResult {
  const unsupported = unsupportedLegacyMappingIssue(sleeves, selection.usKey);
  if (unsupported) return { sleeves: null, issues: [unsupported], ordinaryTwoChild: false };
  const issues: string[] = [];
  const uniqueSleeve = (key: string): EditableSleeve | undefined => {
    const matches = sleeves.filter((sleeve) => sleeve.sleeve_key === key);
    return matches.length === 1 ? matches[0] : undefined;
  };
  const us = uniqueSleeve(selection.usKey);
  const legacy = uniqueSleeve(selection.legacyKey);
  const destination = uniqueSleeve(selection.destinationKey);

  if (!isEnabledSleeve(us)) issues.push('Choose one enabled US allocation.');
  if (!isEnabledSleeve(legacy)) issues.push('Choose one enabled Legacy holdings sleeve.');
  if (!isEnabledSleeve(destination)) issues.push('Choose one enabled New holdings sleeve.');
  if (
    isEnabledSleeve(us) &&
    isEnabledSleeve(legacy) &&
    legacy.parent_sleeve_key !== us.sleeve_key
  ) {
    issues.push(
      'Legacy holdings must be a direct child of the US allocation for default equity and VB/VXF routing.',
    );
  }
  if (
    isEnabledSleeve(us) &&
    isEnabledSleeve(destination) &&
    !isStrictDescendantOf(sleeves, destination.sleeve_key, us.sleeve_key)
  ) {
    issues.push('New holdings must be a strict descendant of the US allocation.');
  }
  if (selection.legacyKey && selection.legacyKey === selection.destinationKey) {
    issues.push('Legacy and New holdings must be different sleeves.');
  } else if (
    isEnabledSleeve(legacy) &&
    isEnabledSleeve(destination) &&
    (isStrictDescendantOf(sleeves, legacy.sleeve_key, destination.sleeve_key) ||
      isStrictDescendantOf(sleeves, destination.sleeve_key, legacy.sleeve_key))
  ) {
    issues.push('Legacy and New holdings branches must not overlap.');
  }

  const ordinaryTwoChild = isOrdinaryTwoChildUSTransition(sleeves, selection);
  const complement = ordinaryTwoChild ? exactHundredComplement(selection.destinationTarget) : null;
  if (ordinaryTwoChild && complement === null) {
    issues.push('New holdings target must be an exact decimal from 0 to 100.');
  }
  if (issues.length) return { sleeves: null, issues, ordinaryTwoChild };

  const destinationTarget = selection.destinationTarget.trim();
  const next = sleeves.map((sleeve) => ({
    ...sleeve,
    is_direct_index_container: sleeve.sleeve_key === selection.usKey,
    is_direct_index_sleeve: sleeve.sleeve_key === selection.legacyKey,
    is_transition_destination: sleeve.sleeve_key === selection.destinationKey,
    ...(ordinaryTwoChild && sleeve.sleeve_key === selection.destinationKey
      ? { target_pct: destinationTarget }
      : {}),
    ...(ordinaryTwoChild && sleeve.sleeve_key === selection.legacyKey
      ? { target_pct: complement! }
      : {}),
  }));
  return { sleeves: next, issues: [], ordinaryTwoChild };
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
      const parentName = parent.display_name || parent.sleeve_key;
      issues.push(`Enabled child targets of “${parentName}” must total exactly 100%.`);
    }
  }
  return issues;
}

function batchInteger(
  value: string | null,
  label: string,
): { value: number | null; issue?: string } {
  const trimmed = value?.trim() ?? '';
  if (!positiveIntegerPattern.test(trimmed)) {
    return { value: null, issue: `${label} must be a positive safe whole number.` };
  }
  const exact = BigInt(trimmed);
  if (exact > BigInt(Number.MAX_SAFE_INTEGER)) {
    return { value: null, issue: `${label} must be a positive safe whole number.` };
  }
  return { value: Number(exact) };
}

export function policySettingsValidationIssues(settings: EditablePolicySettings): string[] {
  const issues: string[] = [];
  for (const [label, key] of requiredDecimalFields) {
    const value = settings[key];
    if (typeof value !== 'string' || !value.trim()) {
      issues.push(`${label} is required; blank values are not changed to zero.`);
    } else if (!decimalPattern.test(value.trim())) {
      issues.push(`${label} must be an exact decimal string.`);
    }
  }
  for (const [label, key] of nullableDecimalFields) {
    const value = settings[key];
    if (typeof value === 'string' && value.trim() && !decimalPattern.test(value.trim())) {
      issues.push(`${label} must be an exact decimal string or blank (null).`);
    }
  }
  const budgetPeriod = settings.budget_period;
  if (typeof budgetPeriod !== 'string' || !budgetPeriod.trim()) {
    issues.push('Budget period is required.');
  }
  const ytdAsOf = settings.ytd_as_of;
  if (
    typeof ytdAsOf === 'string' &&
    ytdAsOf.trim() &&
    !/^\d{4}-\d{2}-\d{2}$/.test(ytdAsOf.trim())
  ) {
    issues.push('YTD as-of must be a date or blank (null).');
  }
  for (const key of booleanFields) {
    if (settings[key] === null) issues.push('Choose each policy rule toggle explicitly.');
  }
  for (const key of batchIntegerFields) {
    const parsed = batchInteger(settings[key], key.replaceAll('_', ' '));
    if (parsed.issue) issues.push(parsed.issue);
  }
  return [...new Set(issues)];
}

export function policySettingsToInput(settings: EditablePolicySettings): {
  value: PolicySettingsInput | null;
  issues: string[];
} {
  const issues = policySettingsValidationIssues(settings);
  if (issues.length) return { value: null, issues };
  const nullable = (value: string | null): string | null => (!value?.trim() ? null : value.trim());
  const required = (value: string | null): string => value!.trim();
  const parsedIntegers = batchIntegerFields.map((key) => batchInteger(settings[key], key));
  if (parsedIntegers.some((item) => item.value === null)) {
    return { value: null, issues: ['Batch limits must be positive safe whole numbers.'] };
  }
  const integers = parsedIntegers.map((item) => item.value as number);
  const value: PolicySettingsInput = {
    short_term_tax_rate: nullable(settings.short_term_tax_rate),
    long_term_tax_rate: nullable(settings.long_term_tax_rate),
    st_loss_carryforward_usd: required(settings.st_loss_carryforward_usd),
    lt_loss_carryforward_usd: required(settings.lt_loss_carryforward_usd),
    ytd_realized_st_usd: required(settings.ytd_realized_st_usd),
    ytd_realized_lt_usd: required(settings.ytd_realized_lt_usd),
    ytd_source: nullable(settings.ytd_source),
    ytd_as_of: nullable(settings.ytd_as_of),
    target_retained_net_loss_usd: required(settings.target_retained_net_loss_usd),
    ordinary_income_deduction_limit_usd: required(settings.ordinary_income_deduction_limit_usd),
    carryforward_loss_discount_factor: required(settings.carryforward_loss_discount_factor),
    gain_budget_usd: nullable(settings.gain_budget_usd),
    max_incremental_tax_cost_usd: nullable(settings.max_incremental_tax_cost_usd),
    st_gain_limit_usd: nullable(settings.st_gain_limit_usd),
    lt_gain_limit_usd: nullable(settings.lt_gain_limit_usd),
    budget_period: required(settings.budget_period),
    max_sell_tickers_per_batch: integers[0]!,
    max_sell_lots_per_batch: integers[1]!,
    max_total_orders_per_batch: integers[2]!,
    max_batch_turnover_pct: required(settings.max_batch_turnover_pct),
    min_buy_order_notional_usd: required(settings.min_buy_order_notional_usd),
    cash_reserve_usd: required(settings.cash_reserve_usd),
    prefer_etf_buys: settings.prefer_etf_buys as boolean,
    allow_gain_sales: settings.allow_gain_sales as boolean,
    permit_etf_harvest: settings.permit_etf_harvest as boolean,
    permit_muni_exit: settings.permit_muni_exit as boolean,
  };
  return { value, issues: [] };
}

export function policyDraftSignature(draft: EditablePolicyDraft): string {
  return JSON.stringify({
    settings: draft.settings,
    sleeves: draft.sleeves,
    allowedSecurities: draft.allowedSecurities,
    overrides: draft.overrides,
    reassignments: draft.reassignments,
    reassignmentHoldings: draft.reassignmentHoldings,
  });
}

export function policyDraftToPayload(
  draft: EditablePolicyDraft,
  sourceRevisionId: string | null,
): { payload: PolicyDraftInput | null; issues: string[] } {
  const settings = policySettingsToInput(draft.settings);
  const issues = [...settings.issues];
  for (const sleeve of draft.sleeves) {
    if (!sleeve.target_pct.trim() || !decimalPattern.test(sleeve.target_pct.trim())) {
      issues.push('Sleeve targets must be exact decimal strings.');
    }
    if (!sleeve.drift_band_pp.trim() || !decimalPattern.test(sleeve.drift_band_pp.trim())) {
      issues.push('Sleeve drift bands must be exact decimal strings.');
    }
  }
  if (issues.length || !settings.value) return { payload: null, issues: [...new Set(issues)] };
  return {
    payload: {
      source_revision_id: sourceRevisionId,
      settings: settings.value,
      sleeves: draft.sleeves.map((sleeve, index) => ({
        ...sleeve,
        sort_order: index,
        target_pct: sleeve.target_pct.trim(),
        drift_band_pp: sleeve.drift_band_pp.trim(),
      })),
      allowed_securities: draft.allowedSecurities.map((security) => ({
        ...security,
        exposure_suitability: !security.exposure_suitability?.trim()
          ? null
          : security.exposure_suitability,
      })),
      overrides: draft.overrides.map((override) => ({ ...override })),
      reassignments: Object.fromEntries(
        Object.entries(draft.reassignments).filter(([, target]) => !!target),
      ),
    },
    issues: [],
  };
}

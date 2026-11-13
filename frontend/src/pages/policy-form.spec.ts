import { describe, expect, it } from 'vitest';
import {
  createEmptyPolicyDraft,
  createEmptyPolicySettings,
  editableSettingsFromRevision,
  exactDecimalSumIsHundred,
  applyExplicitUSTransitionSettings,
  exactHundredComplement,
  policyDraftToPayload,
  policySettingsToInput,
  revisionToDraft,
  targetActivationIssues,
  type EditablePolicySettings,
  type EditableSleeve,
} from './policy-form';
import type { PolicyRevisionResponse, PolicySettingsResponse } from '@/types/api';

function sleeve(
  key: string,
  target: string,
  parent: string | null = null,
  enabled = true,
): EditableSleeve {
  return {
    sleeve_key: key,
    display_name: key,
    parent_sleeve_key: parent,
    target_pct: target,
    drift_band_pp: '0.25',
    enabled,
  };
}

describe('policy exact target validation', () => {
  it('sums decimal strings exactly without binary floating-point tolerance', () => {
    expect(exactDecimalSumIsHundred(['45.0000', '24', '17.00', '14', '0.000'])).toBe(true);
    expect(exactDecimalSumIsHundred(['0.1', '99.9'])).toBe(true);
    expect(exactDecimalSumIsHundred(['99.9999999999999999', '0'])).toBe(false);
    expect(exactDecimalSumIsHundred(['50', 'not-a-number'])).toBe(false);
  });

  it('validates top-level and each enabled nested target independently', () => {
    const valid = [
      sleeve('us', '45'),
      sleeve('dividend', '25'),
      sleeve('cash', '30'),
      sleeve('us-etf', '100', 'us'),
      sleeve('direct-index', '0', 'us'),
    ];
    expect(targetActivationIssues(valid)).toEqual([]);
    expect(
      targetActivationIssues([...valid, sleeve('ignored-disabled', '99', null, false)]),
    ).toEqual([]);
    expect(targetActivationIssues([sleeve('us', '45'), sleeve('other', '54.999999')])).toEqual([
      'Enabled top-level sleeve targets must total exactly 100%.',
    ]);
    expect(targetActivationIssues([sleeve('us', '100'), sleeve('us-etf', '99.9', 'us')])).toEqual([
      'Enabled child targets of “us” must total exactly 100%.',
    ]);
  });
});

describe('explicit US transition settings', () => {
  it('computes exact complements and rejects blank, malformed, or out-of-range targets', () => {
    expect(exactHundredComplement('45.00000000000000000001')).toBe('54.99999999999999999999');
    expect(exactHundredComplement('0')).toBe('100');
    expect(exactHundredComplement('100.00')).toBe('0.00');
    expect(exactHundredComplement('+000.10')).toBe('99.90');
    expect(exactHundredComplement('.5')).toBe('99.5');
    for (const invalid of ['', '   ', '-0.01', '100.0001', 'not a number', '1e2']) {
      expect(exactHundredComplement(invalid)).toBeNull();
    }
  });

  it('applies exact ordinary two-child targets and preserves unrelated sleeve data', () => {
    const sleeves: EditableSleeve[] = [
      {
        ...sleeve('us', '70'),
        is_direct_index_container: false,
        is_direct_index_sleeve: false,
        is_transition_destination: false,
        is_cash_sleeve: false,
      },
      {
        ...sleeve('legacy', '40.0000', 'us'),
        is_direct_index_container: false,
        is_direct_index_sleeve: true,
        is_transition_destination: false,
        is_cash_sleeve: false,
      },
      {
        ...sleeve('destination', '60.0000', 'us'),
        is_direct_index_container: false,
        is_direct_index_sleeve: false,
        is_transition_destination: true,
        is_cash_sleeve: false,
      },
      {
        ...sleeve('cash', '30'),
        is_direct_index_container: false,
        is_direct_index_sleeve: false,
        is_transition_destination: false,
        is_cash_sleeve: true,
      },
    ];
    const result = applyExplicitUSTransitionSettings(sleeves, {
      usKey: 'us',
      legacyKey: 'legacy',
      destinationKey: 'destination',
      destinationTarget: '37.00000000000000000001',
    });

    expect(result.issues).toEqual([]);
    expect(result.ordinaryTwoChild).toBe(true);
    expect(result.sleeves?.map((item) => item.sleeve_key)).toEqual([
      'us',
      'legacy',
      'destination',
      'cash',
    ]);
    expect(result.sleeves?.map((item) => item.target_pct)).toEqual([
      '70',
      '62.99999999999999999999',
      '37.00000000000000000001',
      '30',
    ]);
    expect(result.sleeves?.map((item) => item.is_direct_index_container)).toEqual([
      true,
      false,
      false,
      false,
    ]);
    expect(result.sleeves?.map((item) => item.is_direct_index_sleeve)).toEqual([
      false,
      true,
      false,
      false,
    ]);
    expect(result.sleeves?.map((item) => item.is_transition_destination)).toEqual([
      false,
      false,
      true,
      false,
    ]);
    expect(result.sleeves?.[3]?.is_cash_sleeve).toBe(true);
  });

  it('refuses guided rewrites of multiple or nested Legacy mappings without changing flags or targets', () => {
    const sleeves: EditableSleeve[] = [
      { ...sleeve('us', '80'), is_direct_index_container: true },
      { ...sleeve('legacy', '25.00', 'us'), is_direct_index_sleeve: true },
      sleeve('new-group', '75.00', 'us'),
      { ...sleeve('nested-legacy', '12.5', 'new-group'), is_direct_index_sleeve: true },
      { ...sleeve('destination', '42.5', 'new-group'), is_transition_destination: true },
    ];
    const original = sleeves.map((item) => ({ ...item }));

    const result = applyExplicitUSTransitionSettings(sleeves, {
      usKey: 'us',
      legacyKey: 'legacy',
      destinationKey: 'destination',
      destinationTarget: '99',
    });

    expect(result.sleeves).toBeNull();
    expect(result.issues).toContain(
      'Existing Legacy routing uses multiple sleeves or is not a direct child of one US allocation. Guided editing is unavailable; custom Legacy role mappings are preserved and read-only in guided settings. Existing explicit nested targets can still be edited in the allocation editor.',
    );
    expect(sleeves).toEqual(original);
  });

  it('allows New destinations below the US allocation but rejects a nested Legacy choice', () => {
    const sleeves = [
      { ...sleeve('us', '100'), is_direct_index_container: true },
      sleeve('legacy', '50', 'us'),
      sleeve('new-group', '50', 'us'),
      sleeve('nested-legacy', '40', 'new-group'),
      { ...sleeve('destination', '60', 'new-group'), is_transition_destination: true },
    ];
    const result = applyExplicitUSTransitionSettings(sleeves, {
      usKey: 'us',
      legacyKey: 'nested-legacy',
      destinationKey: 'destination',
      destinationTarget: '60',
    });

    expect(result.sleeves).toBeNull();
    expect(result.issues).toContain(
      'Legacy holdings must be a direct child of the US allocation for default equity and VB/VXF routing.',
    );
  });

  it('preserves nested targets and validates explicit roles', () => {
    const nested = [
      sleeve('us', '70'),
      sleeve('legacy', '31.25', 'us'),
      sleeve('new-parent', '68.75', 'us'),
      sleeve('destination', '45.5', 'new-parent'),
      sleeve('other', '0', null, false),
    ];
    const custom = applyExplicitUSTransitionSettings(nested, {
      usKey: 'us',
      legacyKey: 'legacy',
      destinationKey: 'destination',
      destinationTarget: 'not-a-number',
    });
    expect(custom.issues).toEqual([]);
    expect(custom.ordinaryTwoChild).toBe(false);
    expect(custom.sleeves?.map((item) => item.target_pct)).toEqual([
      '70',
      '31.25',
      '68.75',
      '45.5',
      '0',
    ]);

    const sameBranch = applyExplicitUSTransitionSettings(nested, {
      usKey: 'us',
      legacyKey: 'legacy',
      destinationKey: 'legacy',
      destinationTarget: '50',
    });
    expect(sameBranch.issues).toContain('Legacy and New holdings must be different sleeves.');

    const overlapping = applyExplicitUSTransitionSettings(nested, {
      usKey: 'us',
      legacyKey: 'new-parent',
      destinationKey: 'destination',
      destinationTarget: '50',
    });
    expect(overlapping.issues).toContain('Legacy and New holdings branches must not overlap.');

    const disabled = applyExplicitUSTransitionSettings(nested, {
      usKey: 'us',
      legacyKey: 'legacy',
      destinationKey: 'other',
      destinationTarget: '50',
    });
    expect(disabled.issues).toContain('Choose one enabled New holdings sleeve.');

    const outside = applyExplicitUSTransitionSettings(nested, {
      usKey: 'us',
      legacyKey: 'other',
      destinationKey: 'destination',
      destinationTarget: '50',
    });
    expect(outside.issues).toContain('Choose one enabled Legacy holdings sleeve.');
  });

  it('does not auto-complement custom multi-child US allocations', () => {
    const multiChild = [
      sleeve('us', '100'),
      sleeve('legacy', '20.0', 'us'),
      sleeve('destination', '30.0', 'us'),
      sleeve('other', '50.0', 'us'),
    ];
    const result = applyExplicitUSTransitionSettings(multiChild, {
      usKey: 'us',
      legacyKey: 'legacy',
      destinationKey: 'destination',
      destinationTarget: 'not-a-number',
    });

    expect(result.issues).toEqual([]);
    expect(result.ordinaryTwoChild).toBe(false);
    expect(result.sleeves?.map((item) => item.target_pct)).toEqual(['100', '20.0', '30.0', '50.0']);
  });
});

describe('central policy conversion boundary', () => {
  const apiSettings: PolicySettingsResponse = {
    short_term_tax_rate: '0.2500000000000000000000000000000001',
    long_term_tax_rate: null,
    st_loss_carryforward_usd: '-12345678901234567890.00000000000000000001',
    lt_loss_carryforward_usd: '0.0000',
    ytd_realized_st_usd: '1.0000000000000000000000000000000002',
    ytd_realized_lt_usd: '-2.5000000000000000000000000000000001',
    ytd_source: null,
    ytd_as_of: null,
    target_retained_net_loss_usd: '0',
    ordinary_income_deduction_limit_usd: '3000.00',
    carryforward_loss_discount_factor: '0.50000000000000000001',
    gain_budget_usd: null,
    max_incremental_tax_cost_usd: '0.000',
    st_gain_limit_usd: null,
    lt_gain_limit_usd: '100.00000000000000000001',
    budget_period: 'calendar_year',
    max_sell_tickers_per_batch: Number.MAX_SAFE_INTEGER,
    max_sell_lots_per_batch: 1,
    max_total_orders_per_batch: 12,
    max_batch_turnover_pct: '0.00000000000000000001',
    min_buy_order_notional_usd: '500.0000',
    cash_reserve_usd: '0.0000',
    prefer_etf_buys: false,
    allow_gain_sales: true,
    permit_etf_harvest: false,
    permit_muni_exit: true,
    objective_band_weight: '1.00000000000000000001',
    objective_allocation_weight: null,
    objective_tax_weight: '0.75',
    objective_trading_cost_weight: '0.5',
    objective_turnover_weight: '0.25',
    objective_cleanup_weight: '2.0',
    estimated_spread_bps: '5.00',
    estimated_fee_per_order_usd: '1.00',
  };

  function validSettings(): EditablePolicySettings {
    return editableSettingsFromRevision(apiSettings);
  }

  it('round-trips every generated persisted setting with exact decimal and boolean values', () => {
    const editable = validSettings();
    expect(editable.max_sell_tickers_per_batch).toBe(String(Number.MAX_SAFE_INTEGER));
    expect(editable.short_term_tax_rate).toBe(apiSettings.short_term_tax_rate);
    expect(editable.long_term_tax_rate).toBeNull();
    expect(policySettingsToInput(editable)).toEqual({ value: apiSettings, issues: [] });

    const revision: PolicyRevisionResponse = {
      id: 'policy-draft-roundtrip',
      revision_number: 4,
      status: 'DRAFT',
      created_at: '2025-01-01T00:00:00Z',
      activated_at: null,
      settings: apiSettings,
      sleeves: [],
      allowed_securities: [],
      overrides: [],
      activation_errors: [],
    };
    expect(revisionToDraft(revision).settings).toEqual(editable);
    expect(Object.keys(apiSettings)).toHaveLength(34);
  });
  it('normalizes bounded API exponent decimals losslessly without expanding hostile exponents', () => {
    const sourceSettings: PolicySettingsResponse = {
      ...apiSettings,
      cash_reserve_usd: '1E-8',
      target_retained_net_loss_usd: '1.234567890123456789E-8',
    };
    const draft = revisionToDraft({
      id: 'exponent-decimals',
      revision_number: 5,
      status: 'DRAFT',
      created_at: '2025-01-01T00:00:00Z',
      activated_at: null,
      settings: sourceSettings,
      sleeves: [
        {
          sleeve_key: 'tiny',
          display_name: 'Tiny decimal',
          sort_order: 0,
          parent_sleeve_key: null,
          target_pct: '1E-8',
          drift_band_pp: '9.876543210987654321E-8',
          is_direct_index_container: false,
          is_direct_index_sleeve: false,
          is_transition_destination: false,
          is_cash_sleeve: false,
          enabled: true,
        },
      ],
      allowed_securities: [],
      overrides: [],
      activation_errors: [],
    });

    expect(draft.settings.cash_reserve_usd).toBe('0.00000001');
    expect(draft.settings.target_retained_net_loss_usd).toBe('0.00000001234567890123456789');
    expect(draft.sleeves[0]?.target_pct).toBe('0.00000001');
    expect(draft.sleeves[0]?.drift_band_pp).toBe('0.00000009876543210987654321');
    expect(policyDraftToPayload(draft, 'source').payload?.settings.cash_reserve_usd).toBe(
      '0.00000001',
    );

    const huge = revisionToDraft({
      id: 'huge-exponent',
      revision_number: 6,
      status: 'DRAFT',
      created_at: '2025-01-01T00:00:00Z',
      activated_at: null,
      settings: { ...apiSettings, cash_reserve_usd: '1E-10000000' },
      sleeves: [],
      allowed_securities: [],
      overrides: [],
      activation_errors: [],
    });
    expect(huge.settings.cash_reserve_usd).toBe('1E-10000000');
    expect(policyDraftToPayload(huge, 'source').payload).toBeNull();
  });

  it('distinguishes null, blank, and numeric zero without coercion', () => {
    const editable = validSettings();
    expect(editable.long_term_tax_rate).toBeNull();
    expect(createEmptyPolicySettings().short_term_tax_rate).toBe('');
    editable.short_term_tax_rate = '';
    editable.gain_budget_usd = '';
    editable.cash_reserve_usd = '0.0000';
    const converted = policySettingsToInput(editable);
    expect(converted.value?.short_term_tax_rate).toBeNull();
    expect(converted.value?.long_term_tax_rate).toBeNull();
    expect(converted.value?.gain_budget_usd).toBeNull();
    expect(converted.value?.cash_reserve_usd).toBe('0.0000');
    expect(converted.value?.target_retained_net_loss_usd).toBe('0');

    editable.cash_reserve_usd = '';
    expect(policySettingsToInput(editable).value).toBeNull();
    expect(policySettingsToInput(editable).issues).toContain(
      'cash reserve is required; blank values are not changed to zero.',
    );
  });

  it('converts positive safe integer limits and rejects invalid values', () => {
    const editable = validSettings();
    expect(policySettingsToInput(editable).value?.max_sell_tickers_per_batch).toBe(
      Number.MAX_SAFE_INTEGER,
    );
    for (const invalid of ['', '0', '1.5', '9007199254740992', '1e2']) {
      editable.max_sell_tickers_per_batch = invalid;
      expect(policySettingsToInput(editable).value).toBeNull();
      expect(policySettingsToInput(editable).issues.join(' ')).toContain(
        'max sell tickers per batch must be a positive safe whole number.',
      );
    }
  });

  it('blocks invalid exact-decimal syntax but allows a valid non-100% target draft', () => {
    const draft = createEmptyPolicyDraft();
    draft.settings = validSettings();
    draft.sleeves = [sleeve('custom', '99.99999999999999999999')];
    draft.sleeves[0]!.is_cash_sleeve = true;
    draft.sleeves.push(sleeve('nested-custom', '100', 'custom'));
    draft.allowedSecurities = [
      {
        ticker: 'AAA',
        sleeve_key: 'custom',
        replacement_set_id: 'custom-set',
        priority: 1,
        enabled: true,
        exposure_suitability: 'first',
      },
      {
        ticker: 'BBB',
        sleeve_key: 'custom',
        replacement_set_id: 'custom-set',
        priority: 0,
        enabled: true,
        exposure_suitability: null,
      },
    ];
    draft.overrides = [{ ticker: 'AAPL', sleeve_key: 'custom', sub_sleeve_key: null }];
    draft.reassignments = { retired: 'custom' };
    const converted = policyDraftToPayload(draft, 'source-revision');
    expect(converted.issues).toEqual([]);
    expect(converted.payload?.source_revision_id).toBe('source-revision');
    expect(converted.payload?.sleeves.map((item) => item.sleeve_key)).toEqual([
      'custom',
      'nested-custom',
    ]);
    const tickerOrder = converted.payload?.allowed_securities?.map((item) => item.ticker);
    expect(tickerOrder).toEqual(['AAA', 'BBB']);
    expect(converted.payload?.overrides).toEqual(draft.overrides);
    expect(converted.payload?.reassignments).toEqual({ retired: 'custom' });
    expect(targetActivationIssues(draft.sleeves)).toContain(
      'Enabled top-level sleeve targets must total exactly 100%.',
    );

    draft.settings.ytd_realized_st_usd = '1.0000000000000000000000000000000003x';
    expect(policyDraftToPayload(draft, 'source-revision').payload).toBeNull();
  });

  it('does not collapse explicit false booleans or emit unresolved nullable booleans', () => {
    const editable = validSettings();
    expect(policySettingsToInput(editable).value?.prefer_etf_buys).toBe(false);
    editable.prefer_etf_buys = null;
    expect(policySettingsToInput(editable).value).toBeNull();
    expect(policySettingsToInput(editable).issues).toContain(
      'Choose each policy rule toggle explicitly.',
    );
  });
});

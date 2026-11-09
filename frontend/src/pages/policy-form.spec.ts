import { describe, expect, it } from 'vitest';
import {
  createEmptyPolicyDraft,
  createEmptyPolicySettings,
  editableSettingsFromRevision,
  exactDecimalSumIsHundred,
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
    expect(Object.keys(apiSettings)).toHaveLength(26);
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

// @vitest-environment jsdom
import { flushPromises } from '@vue/test-utils';
import { mountWithWorkspace } from '@/test-utils/workspace-mount';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';
import type {
  OptimizerRecommendationsResponse,
  PolicyDraftInput,
  PolicyRevisionResponse,
  PolicyResponse,
  PolicySettingsResponse,
  PortfolioReadyResponse,
  USTransitionResponse,
} from '@/types/api';
import PolicyPage from './PolicyPage.vue';
import { useWorkspaceStore } from '@/stores/workspace-store';
import { Select } from '@/components/ui/select';
import { seedCurrentRunForTest } from '@/test-utils/workspace-harness';
import { getTestQueryClientForPinia } from '@/test-utils/workspace-mount';
import { workspaceQueryKeys } from '@/composables/queries/workspace-queries';

function labelForSleeveControl(wrapper: ReturnType<typeof mountWithWorkspace>, labelText: string) {
  const label = wrapper
    .findAll('label')
    .find((candidate) => candidate.text().replace(/\s+/g, ' ').trim() === labelText);
  if (!label) throw new Error(`Sleeve control label not found: ${labelText}`);
  return label;
}

async function setSleeveCheckbox(
  wrapper: ReturnType<typeof mountWithWorkspace>,
  labelText: string,
  checked: boolean,
): Promise<void> {
  const label = labelForSleeveControl(wrapper, labelText);
  const id = label.attributes('for');
  if (!id) throw new Error(`Sleeve checkbox label is not associated: ${labelText}`);
  const control = wrapper.find(`[data-slot="checkbox"][id="${id}"]`);
  if (!control.exists()) throw new Error(`Sleeve checkbox not found: ${labelText}`);
  if (control.attributes('aria-checked') !== String(checked)) await control.trigger('click');
  await flushPromises();
}

async function setSleeveSelect(
  wrapper: ReturnType<typeof mountWithWorkspace>,
  labelText: string,
  optionLabel: string,
): Promise<void> {
  const label = labelForSleeveControl(wrapper, labelText);
  const labelId = label.attributes('id');
  if (!labelId) throw new Error(`Sleeve select label has no ID: ${labelText}`);
  const control = wrapper
    .findAllComponents(Select)
    .find((candidate) =>
      candidate.find(`[data-slot="select-trigger"][aria-labelledby="${labelId}"]`).exists(),
    );
  if (!control) throw new Error(`Sleeve select not found: ${labelText}`);
  const triggerId = control
    .get(`[data-slot="select-trigger"][aria-labelledby="${labelId}"]`)
    .attributes('id');
  const sectionLabel = wrapper.get('[data-policy-sleeves-root]').attributes('aria-labelledby');
  const sectionId = sectionLabel?.replace(/-title$/, '');
  if (!sectionId || !triggerId) throw new Error(`Sleeve select has no stable ID: ${labelText}`);
  let kind: string;
  if (triggerId.startsWith(`${sectionId}-delete-parent-`)) {
    kind = `delete-parent-${decodeURIComponent(triggerId.slice(`${sectionId}-delete-parent-`.length))}`;
  } else if (triggerId.endsWith('-parent')) {
    kind = 'parent';
  } else {
    kind = 'reassignment';
  }
  let domainValue: string | null;
  if (optionLabel === 'Top level') {
    domainValue = null;
  } else if (optionLabel === 'Choose destination' || optionLabel === 'Choose new parent') {
    domainValue = '';
  } else {
    const row = wrapper.findAll('[data-policy-sleeves-root] tbody tr').find((candidate) => {
      const nameInput = candidate.find('input[aria-label^="Sleeve display name for "]');
      const key = candidate.find('.sleeve-key').text().trim();
      return (
        (nameInput.exists() &&
          nameInput.attributes('aria-label') === `Sleeve display name for ${optionLabel}`) ||
        key.toLowerCase() === optionLabel.toLowerCase()
      );
    });
    if (!row) throw new Error(`Sleeve select option not found: ${optionLabel}`);
    domainValue = row.get('.sleeve-key').text().trim();
  }
  const token = `${sectionId}-${kind}-${domainValue === null ? 'none' : `value-${encodeURIComponent(domainValue)}`}`;
  control.vm.$emit('update:modelValue', token);
  await flushPromises();
}

const settings: PolicySettingsResponse = {
  short_term_tax_rate: '0.2500',
  long_term_tax_rate: null,
  st_loss_carryforward_usd: '0.00',
  lt_loss_carryforward_usd: '15.20',
  ytd_realized_st_usd: '-4.01',
  ytd_realized_lt_usd: '0.00',
  ytd_source: 'FakeBroker',
  ytd_as_of: '2025-01-31',
  target_retained_net_loss_usd: '3000.00',
  ordinary_income_deduction_limit_usd: '3000.00',
  carryforward_loss_discount_factor: '0.5000',
  gain_budget_usd: null,
  max_incremental_tax_cost_usd: '25.00',
  st_gain_limit_usd: null,
  lt_gain_limit_usd: '100.00',
  budget_period: 'calendar_year',
  max_sell_tickers_per_batch: 10,
  max_sell_lots_per_batch: 20,
  max_total_orders_per_batch: 12,
  max_batch_turnover_pct: '5.00',
  min_buy_order_notional_usd: '500.00',
  cash_reserve_usd: '0.00',
  prefer_etf_buys: true,
  allow_gain_sales: false,
  permit_etf_harvest: true,
  permit_muni_exit: false,
  objective_band_weight: null,
  objective_allocation_weight: null,
  objective_tax_weight: null,
  objective_trading_cost_weight: null,
  objective_turnover_weight: null,
  objective_cleanup_weight: null,
  estimated_spread_bps: null,
  estimated_fee_per_order_usd: null,
};

const activeRevision: PolicyRevisionResponse = {
  id: 'revision-active-synthetic',
  revision_number: 7,
  status: 'ACTIVE',
  created_at: '2025-01-01T00:00:00Z',
  activated_at: '2025-01-02T00:00:00Z',
  settings,
  sleeves: [
    {
      sleeve_key: 'us',
      display_name: 'US equity',
      sort_order: 0,
      parent_sleeve_key: null,
      target_pct: '100.0000',
      drift_band_pp: '2.2500',
      is_direct_index_container: true,
      is_direct_index_sleeve: false,
      is_transition_destination: false,
      is_cash_sleeve: false,
      enabled: true,
    },
  ],
  allowed_securities: [
    {
      ticker: 'VTI',
      sleeve_key: 'us',
      sub_sleeve_key: null,
      replacement_set_id: 'us-core',
      priority: 0,
      enabled: true,
      exposure_suitability: 'Broad US equity',
    },
  ],
  overrides: [],
  activation_errors: [],
};

function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function requestAddress(input: RequestInfo | URL): URL {
  const address =
    typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
  return new URL(address, 'http://127.0.0.1:9000');
}

function notSyncedPortfolioResponse() {
  return {
    status: 'not_synced',
    demo: true,
    account: null,
    as_of: null,
    cash_usd: '0',
    portfolio_total_usd: '0',
    positions: [],
    coverage: {},
    sync: {
      generation: 0,
      complete: false,
      started_at: null,
      completed_at: null,
      last_error_code: null,
      last_error_summary: null,
    },
    allocation: { current: null, proposed: null, target: null },
    us_transition: null,
  };
}

function transitionResponse(
  options: {
    destination?: string | null;
    proposedNew?: string;
  } = {},
): USTransitionResponse {
  const destination = options.destination === undefined ? 'new' : options.destination;
  const proposedNew = options.proposedNew ?? '30.0000';
  const child = (within: string) => ({
    value_usd: '100.00',
    within_us_sleeve_pct: within,
    whole_portfolio_pct: within,
  });
  return {
    sleeve_key: 'us',
    transition_destination_sleeve_key: destination,
    label: 'API transition label',
    current: {
      us_sleeve_value_usd: '200.00',
      us_sleeve_whole_portfolio_pct: '80.0000',
      etf_progress_pct: destination === null ? null : '20.0000',
      children: { legacy: child('80.0000'), new: child('20.0000') },
    },
    proposed_basket: {
      us_sleeve_value_usd: '200.00',
      us_sleeve_whole_portfolio_pct: '80.0000',
      etf_progress_pct: destination === null ? null : proposedNew,
      children: { legacy: child(String(100 - Number(proposedNew))), new: child(proposedNew) },
    },
    target: {
      us_sleeve_whole_portfolio_pct: '80.0000',
      children: {
        legacy: { within_us_sleeve_pct: '60.0000', whole_portfolio_pct: '48.0000' },
        new: { within_us_sleeve_pct: '40.0000', whole_portfolio_pct: '32.0000' },
      },
    },
  };
}

function transitionPolicy(destinationConfigured = true): PolicyRevisionResponse {
  return {
    ...activeRevision,
    sleeves: [
      ...activeRevision.sleeves,
      {
        sleeve_key: 'legacy',
        display_name: 'API Legacy label',
        sort_order: 1,
        parent_sleeve_key: 'us',
        target_pct: '60.0000',
        drift_band_pp: '0.0000',
        is_direct_index_container: false,
        is_direct_index_sleeve: true,
        is_transition_destination: false,
        is_cash_sleeve: false,
        enabled: true,
      },
      {
        sleeve_key: 'new',
        display_name: 'API New label',
        sort_order: 2,
        parent_sleeve_key: 'us',
        target_pct: '40.0000',
        drift_band_pp: '0.0000',
        is_direct_index_container: false,
        is_direct_index_sleeve: false,
        is_transition_destination: destinationConfigured,
        is_cash_sleeve: false,
        enabled: true,
      },
    ],
    activation_errors: [],
  };
}

function readyTransitionPortfolio(
  activeRevisionId: string,
  usTransition: USTransitionResponse | null = transitionResponse(),
  portfolioRevisionId = activeRevisionId,
  currentWeights?: Record<string, string>,
): PortfolioReadyResponse {
  return {
    status: 'ready',
    demo: true,
    source: 'FakeBroker',
    account: { display_name: 'Fixture account', account_type: 'brokerage', tax_treatment: null },
    as_of: '2026-01-01T12:00:00Z',
    cash_usd: '0.00',
    settled_buying_power_usd: '0.00',
    positions_market_value_usd: '250.00',
    portfolio_total_usd: '250.00',
    position_count: 0,
    positions: [],
    active_policy_revision_id: portfolioRevisionId,
    unassigned_tickers: [],
    coverage: {},
    sync: {
      generation: 7,
      complete: true,
      started_at: '2026-01-01T11:00:00Z',
      completed_at: '2026-01-01T12:00:00Z',
      last_error_code: null,
      last_error_summary: null,
    },
    allocation: {
      current: currentWeights
        ? { total_portfolio_usd: '250.00', sleeve_weights_pct: currentWeights }
        : null,
      proposed: null,
      target: null,
    },
    us_transition: usTransition,
  };
}

function selectedRunFixture(
  options: {
    revisionId?: string;
    generation?: number;
    selected?: boolean;
    usTransition?: USTransitionResponse | null;
  } = {},
): OptimizerRecommendationsResponse {
  const selected = options.selected ?? true;
  return {
    run_id: 'transition-policy-run',
    status: 'demo',
    mode: 'recommendations_only',
    policy_revision_id: options.revisionId ?? transitionPolicy().id,
    source_generation: options.generation ?? 7,
    as_of: '2026-01-01T12:00:00Z',
    solver_version: 'DEMO',
    demo: true,
    actionable: false,
    input_fingerprint: null,
    source_checksum: null,
    batch_settings: {},
    estimated_realized_st_usd: '-1.00',
    estimated_realized_lt_usd: '0.00',
    estimated_tax_benefit_usd: null,
    estimated_tax_benefit_status: 'tax_profile_incomplete',
    lots_sold_count: selected ? 1 : 0,
    positions_exited_count: 0,
    orders_count: selected ? 1 : 0,
    cash_before_usd: '0.00',
    cash_after_usd: '0.00',
    portfolio_effects: {
      allocation: { current: null, proposed: null, target: null },
      us_transition: options.usTransition ?? transitionResponse({ proposedNew: '35.0000' }),
    },
    constraints_satisfied: null,
    no_trade_reason: null,
    warnings: [],
    tax_profile_configured: false,
    frozen_display_context: { available: false, unavailable_reason: 'test fixture' },
    groups: [
      {
        group_id: 'selected-group',
        rank: 1,
        group_type: 'demo_loss_harvest',
        sleeve_key: 'us',
        rationale: 'test fixture',
        estimated_benefit_usd: null,
        impact: {} as never,
        dependencies: [],
        selected,
        rejected: false,
        note: null,
        rejection_reason: null,
        leg_ids: ['selected-sell'],
        warnings: [],
      },
    ],
    consolidated_legs: [
      {
        leg_id: 'selected-sell',
        side: 'SELL',
        ticker: 'VTI',
        shares: '1',
        estimated_unit_price_usd: '10.00',
        estimated_notional_usd: '10.00',
        net_st_realized_usd: '-1.00',
        selected,
        group_ids: ['selected-group'],
        net_lt_realized_usd: '0.00',
        sequence: 1,
        dependencies: [],
        selected_lots: [
          {
            broker_lot_id: 'fixture-lot-1',
            shares: '1',
            acquired_date: '2025-01-01',
            adjusted_basis_usd: '11.00',
            st_lt: 'ST',
            realized_pl_usd: '-1.00',
            selected,
          },
        ],
        details: {},
      },
    ],
  } as unknown as OptimizerRecommendationsResponse;
}

async function mountTransitionPolicy(
  options: {
    activePolicy?: PolicyRevisionResponse;
    portfolioRevisionId?: string;
    usTransition?: USTransitionResponse | null;
    currentWeights?: Record<string, string>;
  } = {},
) {
  const active = options.activePolicy ?? transitionPolicy();
  const portfolio = readyTransitionPortfolio(
    active.id,
    options.usTransition === undefined ? transitionResponse() : options.usTransition,
    options.portfolioRevisionId ?? active.id,
    options.currentWeights,
  );
  const fetcher = vi.fn<typeof fetch>((input) => {
    const url = requestAddress(input);
    if (url.pathname === '/health')
      return Promise.resolve(
        jsonResponse({
          status: 'ok',
          schema_ready: true,
          broker_mode: 'demo',
          live_broker_enabled: false,
          order_submission_enabled: false,
        }),
      );
    if (url.pathname === '/api/v1/policy')
      return Promise.resolve(
        jsonResponse({ active, drafts: [], superseded: [] } satisfies PolicyResponse),
      );
    if (url.pathname === '/api/v1/portfolio') return Promise.resolve(jsonResponse(portfolio));
    return Promise.reject(new Error(`Unhandled local API request: ${url.pathname}`));
  });
  vi.stubGlobal('fetch', fetcher);
  const pinia = createPinia();
  setActivePinia(pinia);
  const wrapper = mountWithWorkspace(PolicyPage, { global: { plugins: [pinia] } });
  await flushPromises();
  return { wrapper, pinia, active, portfolio, fetcher };
}

function revisionFromPayload(payload: PolicyDraftInput): PolicyRevisionResponse {
  return {
    ...activeRevision,
    id: 'revision-draft-synthetic',
    revision_number: 8,
    status: 'DRAFT',
    activated_at: null,
    settings: {
      ...settings,
      ...payload.settings,
      short_term_tax_rate: payload.settings.short_term_tax_rate ?? null,
      long_term_tax_rate: payload.settings.long_term_tax_rate ?? null,
      st_loss_carryforward_usd: String(payload.settings.st_loss_carryforward_usd),
      lt_loss_carryforward_usd: String(payload.settings.lt_loss_carryforward_usd),
      ytd_realized_st_usd: String(payload.settings.ytd_realized_st_usd),
      ytd_realized_lt_usd: String(payload.settings.ytd_realized_lt_usd),
      target_retained_net_loss_usd: String(payload.settings.target_retained_net_loss_usd),
      ordinary_income_deduction_limit_usd: String(
        payload.settings.ordinary_income_deduction_limit_usd,
      ),
      carryforward_loss_discount_factor: String(payload.settings.carryforward_loss_discount_factor),
      gain_budget_usd: payload.settings.gain_budget_usd ?? null,
      max_incremental_tax_cost_usd: payload.settings.max_incremental_tax_cost_usd ?? null,
      st_gain_limit_usd: payload.settings.st_gain_limit_usd ?? null,
      lt_gain_limit_usd: payload.settings.lt_gain_limit_usd ?? null,
      max_sell_tickers_per_batch: Number(payload.settings.max_sell_tickers_per_batch),
      max_sell_lots_per_batch: Number(payload.settings.max_sell_lots_per_batch),
      max_total_orders_per_batch: Number(payload.settings.max_total_orders_per_batch),
      max_batch_turnover_pct: String(payload.settings.max_batch_turnover_pct),
      min_buy_order_notional_usd: String(payload.settings.min_buy_order_notional_usd),
      cash_reserve_usd: String(payload.settings.cash_reserve_usd),
    },
    sleeves: payload.sleeves.map((sleeve) => ({
      sleeve_key: sleeve.sleeve_key,
      display_name: sleeve.display_name,
      sort_order: sleeve.sort_order ?? 0,
      parent_sleeve_key: sleeve.parent_sleeve_key ?? null,
      target_pct: sleeve.target_pct ?? '',
      drift_band_pp: sleeve.drift_band_pp ?? '',
      is_direct_index_container: sleeve.is_direct_index_container ?? false,
      is_direct_index_sleeve: sleeve.is_direct_index_sleeve ?? false,
      is_transition_destination: sleeve.is_transition_destination ?? false,
      is_cash_sleeve: sleeve.is_cash_sleeve ?? false,
      enabled: sleeve.enabled ?? true,
    })),
    allowed_securities:
      payload.allowed_securities?.map((security) => ({
        ticker: security.ticker,
        sleeve_key: security.sleeve_key,
        sub_sleeve_key: security.sub_sleeve_key ?? null,
        replacement_set_id: security.replacement_set_id ?? 'default',
        priority: security.priority ?? 0,
        enabled: security.enabled ?? true,
        exposure_suitability: security.exposure_suitability ?? null,
      })) ?? [],
    overrides:
      payload.overrides?.map((override) => ({
        ...override,
        sub_sleeve_key: override.sub_sleeve_key ?? null,
      })) ?? [],
    activation_errors: [
      {
        code: 'top_level_target_sum',
        message: 'Enabled top-level targets must sum exactly to 100%',
      },
    ],
  };
}

function taxInputByLabel(wrapper: ReturnType<typeof mountWithWorkspace>, labelText: string) {
  const taxSettings = wrapper.get('[data-policy-tax-settings-root]');
  const label = taxSettings
    .findAll('label')
    .find((candidate) => candidate.text().includes(labelText));
  if (!label) throw new Error(`Tax settings label not found: ${labelText}`);
  const inputId = label.attributes('for');
  if (!inputId) throw new Error(`Tax settings label has no input association: ${labelText}`);
  return taxSettings.get(`input[data-slot="input"][id="${inputId}"]`);
}

beforeEach(() => {
  vi.unstubAllGlobals();
  setActivePinia(createPinia());
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('PolicyPage', () => {
  it('validates revision choices and keeps controller selection resets authoritative', async () => {
    const knownRevision: PolicyRevisionResponse = {
      ...activeRevision,
      id: 'revision-known-synthetic',
      revision_number: 8,
      status: 'DRAFT',
      activated_at: null,
    };
    const fetcher = vi.fn<typeof fetch>((input) => {
      const url = requestAddress(input);
      if (url.pathname === '/api/v1/policy') {
        return Promise.resolve(
          jsonResponse({ active: activeRevision, drafts: [knownRevision], superseded: [] }),
        );
      }
      if (url.pathname === '/api/v1/portfolio')
        return Promise.resolve(jsonResponse(notSyncedPortfolioResponse()));
      return Promise.reject(new Error(`Unhandled local API request: ${url.pathname}`));
    });
    vi.stubGlobal('fetch', fetcher);
    const pinia = createPinia();
    const wrapper = mountWithWorkspace(PolicyPage, {
      global: { plugins: [pinia] },
    });
    await flushPromises();

    const policySelect = wrapper
      .findAllComponents(Select)
      .find((select) => select.find('#policy-revision-select').exists());
    if (!policySelect) throw new Error('Policy revision selector not found');
    const editor = useWorkspaceStore(pinia).policyEditor;
    const requestRevisionChange = vi.spyOn(editor, 'requestRevisionChange');

    policySelect.vm.$emit('update:modelValue', 'revision-not-available');
    await flushPromises();
    const trigger = wrapper.get('#policy-revision-select');
    expect(trigger.attributes('aria-invalid')).toBe('true');
    expect(trigger.attributes('aria-describedby')).toBe('policy-revision-select-error');
    expect(wrapper.get('#policy-revision-select-error').attributes('role')).toBe('alert');
    expect(wrapper.get('#policy-revision-select-error').text()).toContain(
      'Select a policy revision that is currently available.',
    );
    expect(requestRevisionChange).not.toHaveBeenCalled();
    expect(editor.state.selectedRevisionId).toBe(knownRevision.id);

    editor.state.revisionChoice = '';
    await flushPromises();
    expect(policySelect.props('modelValue')).toBe('__new_policy__');
    expect(wrapper.find('#policy-revision-select-error').exists()).toBe(false);
    expect(requestRevisionChange).not.toHaveBeenCalled();

    editor.state.revisionChoice = knownRevision.id;
    await flushPromises();
    expect(policySelect.props('modelValue')).toBe(knownRevision.id);
    expect(requestRevisionChange).not.toHaveBeenCalled();

    policySelect.vm.$emit('update:modelValue', activeRevision.id);
    await flushPromises();
    expect(requestRevisionChange).toHaveBeenCalledTimes(1);
    expect(requestRevisionChange).toHaveBeenCalledWith(activeRevision.id, expect.any(Array));
    expect(editor.state.selectedRevisionId).toBe(activeRevision.id);
    expect(policySelect.props('modelValue')).toBe(activeRevision.id);
    expect(wrapper.find('#policy-revision-select-error').exists()).toBe(false);
    wrapper.unmount();
  });

  it('edits a source revision as a new draft and cannot activate dirty or invalid target content', async () => {
    let savedRevision: PolicyRevisionResponse | null = null;
    const draftPayloads: PolicyDraftInput[] = [];
    let activationCalls = 0;
    const fetcher = vi.fn<typeof fetch>((input, init) => {
      const url = requestAddress(input);
      if (url.pathname === '/api/v1/policy' && init?.method !== 'POST') {
        const policy: PolicyResponse = {
          active: activeRevision,
          drafts: savedRevision ? [savedRevision] : [],
          superseded: [],
        };
        return Promise.resolve(jsonResponse(policy));
      }
      if (url.pathname === '/api/v1/portfolio') {
        return Promise.resolve(
          jsonResponse({
            status: 'not_synced',
            demo: true,
            account: null,
            as_of: null,
            cash_usd: '0',
            portfolio_total_usd: '0',
            positions: [],
            coverage: {},
            sync: {
              generation: 0,
              complete: false,
              started_at: null,
              completed_at: null,
              last_error_code: null,
              last_error_summary: null,
            },
            allocation: { current: null, proposed: null, target: null },
            us_transition: null,
          }),
        );
      }
      if (url.pathname === '/api/v1/policy/drafts' && init?.method === 'POST') {
        if (typeof init.body !== 'string') throw new Error('Expected serialized policy input');
        const payload = JSON.parse(init.body) as PolicyDraftInput;
        draftPayloads.push(payload);
        savedRevision = revisionFromPayload(payload);
        return Promise.resolve(jsonResponse(savedRevision, 201));
      }
      if (url.pathname.includes('/activate')) {
        activationCalls += 1;
        return Promise.resolve(jsonResponse(savedRevision ?? activeRevision));
      }
      return Promise.reject(
        new Error(`Unhandled local API request: ${init?.method ?? 'GET'} ${url.pathname}`),
      );
    });
    vi.stubGlobal('fetch', fetcher);
    const wrapper = mountWithWorkspace(PolicyPage, {
      global: { plugins: [createPinia()] },
    });
    await flushPromises();
    const revisionCard = wrapper.get('.revision-panel');
    const activationCard = wrapper.get('.activation-panel');
    expect(revisionCard.element.tagName).toBe('SECTION');
    expect(revisionCard.attributes('aria-labelledby')).toBe('revision-title');
    expect(activationCard.element.tagName).toBe('SECTION');
    expect(activationCard.attributes('aria-labelledby')).toBe('activation-title');
    expect(revisionCard.find('[data-slot="card"]').exists()).toBe(true);
    expect(activationCard.find('[data-slot="card"]').exists()).toBe(true);
    expect(wrapper.get('#revision-title').element.tagName).toBe('H2');
    expect(wrapper.get('#activation-title').element.tagName).toBe('H2');
    const statusBadges = [
      ...revisionCard.findAll('[data-slot="badge"]'),
      ...activationCard.findAll('[data-slot="badge"]'),
    ];
    expect(statusBadges.map((badge) => badge.text())).toEqual([
      'Editing source revision-active-synthetic',
      'Target sums valid',
    ]);
    expect(statusBadges.every((badge) => badge.attributes('role') === 'status')).toBe(true);
    expect(statusBadges.every((badge) => badge.attributes('data-variant') === 'secondary')).toBe(
      true,
    );
    expect(wrapper.get('.activation-panel').text()).toContain(
      'No target-sum errors are currently reported.',
    );
    const policySelect = wrapper
      .findAllComponents(Select)
      .find((select) => select.find('#policy-revision-select').exists());
    expect(policySelect?.props('modelValue')).toBe('revision-active-synthetic');
    expect(wrapper.get('#policy-revision-select').attributes('aria-label')).toBe(
      'Select policy source revision',
    );

    policySelect?.vm.$emit('update:modelValue', '__new_policy__');
    await flushPromises();
    expect(policySelect?.props('modelValue')).toBe('__new_policy__');
    expect(wrapper.get('.revision-panel').text()).toContain(
      'None — creating the first policy revision',
    );
    policySelect?.vm.$emit('update:modelValue', 'revision-active-synthetic');
    await flushPromises();
    expect(policySelect?.props('modelValue')).toBe('revision-active-synthetic');

    expect(wrapper.get('.workspace-page').classes()).toContain('policy-page');
    expect(wrapper.text()).toContain('Allocation Policy');
    expect(wrapper.text()).toContain('ST/LT tax rates use fraction units');
    const target = wrapper.find('input[aria-label="Target percent of portfolio for US equity"]');
    expect(wrapper.find('[data-slot="checkbox"][id$="-transition-destination"]').exists()).toBe(
      false,
    );
    await target.setValue('99.9999999999999999');
    expect((wrapper.get('button.primary-button').element as HTMLButtonElement).disabled).toBe(
      false,
    );
    expect(
      (
        wrapper
          .findAll('button')
          .find((button) => button.text().includes('Activate saved revision'))?.element as
          HTMLButtonElement | undefined
      )?.disabled,
    ).toBe(true);
    await wrapper.find('button.primary-button').trigger('click');
    await flushPromises();

    const savedPayload = draftPayloads[0];
    expect(savedPayload?.source_revision_id).toBe('revision-active-synthetic');
    expect(savedPayload?.sleeves[0]?.is_transition_destination).toBe(false);
    expect(savedPayload?.sleeves[0]?.target_pct).toBe('99.9999999999999999');
    expect(savedPayload?.settings.short_term_tax_rate).toBe('0.2500');
    expect(savedPayload?.settings.long_term_tax_rate).toBeNull();
    expect(wrapper.text()).toContain('top_level_target_sum');
    const attentionBadge = wrapper
      .findAll('[data-slot="badge"]')
      .find((badge) => badge.text() === 'Needs attention');
    expect(attentionBadge?.attributes('role')).toBe('status');
    expect(attentionBadge?.attributes('data-variant')).toBe('destructive');
    expect(wrapper.text()).toContain('Only this saved content can be activated');
    expect(activationCalls).toBe(0);
  });
  it('preserves server-generated holding overrides across consecutive saves', async () => {
    const otherSleeve = {
      ...activeRevision.sleeves[0]!,
      sleeve_key: 'other',
      display_name: 'Other sleeve',
      sort_order: 1,
      target_pct: '0.0000',
      is_direct_index_container: false,
    };
    const sourceRevision = {
      ...activeRevision,
      sleeves: [...activeRevision.sleeves, otherSleeve],
      // Keep the synthetic ETF candidate assigned to an enabled sleeve so the first save payload is valid.
      allowed_securities: activeRevision.allowed_securities.map((candidate) => ({
        ...candidate,
        sleeve_key: 'other',
      })),
    };
    const readyPortfolio = {
      status: 'ready',
      demo: true,
      source: 'synthetic',
      account: {},
      as_of: '2025-01-31T00:00:00Z',
      cash_usd: '0',
      settled_buying_power_usd: '0',
      positions_market_value_usd: '100.00',
      portfolio_total_usd: '100.00',
      position_count: 1,
      positions: [
        {
          ticker: 'AAPL',
          asset_type: 'EQUITY',
          shares: '1',
          market_value_usd: '100.00',
          last_price_usd: '100.00',
          quote_source: 'fixture',
          quote_as_of: '2025-01-31T00:00:00Z',
          sleeve_key: 'us',
          sub_sleeve_key: null,
        },
      ],
      active_policy_revision_id: sourceRevision.id,
      unassigned_tickers: [],
      coverage: {},
      sync: {
        generation: 1,
        complete: true,
        started_at: null,
        completed_at: '2025-01-31T00:00:00Z',
        last_error_code: null,
        last_error_summary: null,
      },
      allocation: { current: null, proposed: null, target: null },
      us_transition: null,
    };
    const draftPayloads: PolicyDraftInput[] = [];
    let savedRevision: PolicyRevisionResponse | null = null;
    const returnedRevisions: PolicyRevisionResponse[] = [];
    const fetcher = vi.fn<typeof fetch>((input, init) => {
      const url = requestAddress(input);
      if (url.pathname === '/api/v1/policy' && init?.method !== 'POST') {
        return Promise.resolve(
          jsonResponse({
            active: sourceRevision,
            drafts: savedRevision ? [savedRevision] : [],
            superseded: [],
          }),
        );
      }
      if (url.pathname === '/api/v1/portfolio')
        return Promise.resolve(jsonResponse(readyPortfolio));
      if (url.pathname === '/api/v1/policy/drafts' && init?.method === 'POST') {
        if (typeof init.body !== 'string') throw new Error('Expected serialized policy input');
        const payload = JSON.parse(init.body) as PolicyDraftInput;
        draftPayloads.push(payload);
        const revision = revisionFromPayload(payload);
        const responseRevision = {
          ...revision,
          overrides: [
            ...revision.overrides,
            ...(payload.reassignments?.us
              ? [{ ticker: 'AAPL', sleeve_key: 'other', sub_sleeve_key: null }]
              : []),
          ],
        };
        savedRevision = responseRevision;
        returnedRevisions.push(responseRevision);
        return Promise.resolve(jsonResponse(responseRevision, 201));
      }
      return Promise.reject(
        new Error(`Unhandled local API request: ${init?.method ?? 'GET'} ${url.pathname}`),
      );
    });
    vi.stubGlobal('fetch', fetcher);
    const wrapper = mountWithWorkspace(PolicyPage, {
      global: { plugins: [createPinia()] },
    });
    await flushPromises();

    await setSleeveCheckbox(wrapper, 'Enabled US equity', false);
    await setSleeveSelect(wrapper, 'Reassign holdings from US equity', 'Other');
    await wrapper.find('button.primary-button').trigger('click');
    await flushPromises();

    expect(draftPayloads[0]?.reassignments).toEqual({ us: 'other' });
    expect(returnedRevisions[0]?.overrides).toContainEqual({
      ticker: 'AAPL',
      sleeve_key: 'other',
      sub_sleeve_key: null,
    });
    expect(wrapper.text()).toContain('Current form matches saved revision');
    expect(wrapper.text()).not.toContain('Choose a holding reassignment for disabled sleeve');

    await taxInputByLabel(wrapper, 'Short-term marginal tax rate').setValue('0.3000');
    await wrapper.find('button.primary-button').trigger('click');
    await flushPromises();

    expect(draftPayloads).toHaveLength(2);
    expect(draftPayloads[1]?.source_revision_id).toBe('revision-draft-synthetic');
    expect(draftPayloads[1]?.overrides).toContainEqual({
      ticker: 'AAPL',
      sleeve_key: 'other',
      sub_sleeve_key: null,
    });
    expect(draftPayloads[1]?.reassignments).toEqual({});
    expect(wrapper.text()).toContain('Current form matches saved revision');
  });

  it('generates a sleeve key absent from saved sleeves after remount', async () => {
    let savedRevision: PolicyRevisionResponse | null = null;
    const savedSleeveKeys: string[][] = [];
    const fetcher = vi.fn<typeof fetch>((input, init) => {
      const url = requestAddress(input);
      if (url.pathname === '/api/v1/policy' && init?.method !== 'POST') {
        return Promise.resolve(
          jsonResponse({
            active: activeRevision,
            drafts: savedRevision ? [savedRevision] : [],
            superseded: [],
          }),
        );
      }
      if (url.pathname === '/api/v1/portfolio')
        return Promise.resolve(jsonResponse(notSyncedPortfolioResponse()));
      if (url.pathname === '/api/v1/policy/drafts' && init?.method === 'POST') {
        if (typeof init.body !== 'string') throw new Error('Expected serialized policy input');
        const revision = revisionFromPayload(JSON.parse(init.body) as PolicyDraftInput);
        savedRevision = revision;
        savedSleeveKeys.push(revision.sleeves.map((sleeve) => sleeve.sleeve_key));
        return Promise.resolve(jsonResponse(revision, 201));
      }
      return Promise.reject(
        new Error(`Unhandled local API request: ${init?.method ?? 'GET'} ${url.pathname}`),
      );
    });
    vi.stubGlobal('fetch', fetcher);
    const mountPage = () =>
      mountWithWorkspace(PolicyPage, {
        global: { plugins: [createPinia()] },
      });
    const firstMount = mountPage();
    await flushPromises();

    await firstMount
      .findAll('button')
      .find((button) => button.text().includes('Add allocation'))!
      .trigger('click');
    const firstNames = firstMount.findAll(
      'input[aria-label="Sleeve display name for sleeve-new-1"]',
    );
    const firstTargets = firstMount.findAll(
      'input[aria-label="Target percent of portfolio for sleeve-new-1"]',
    );
    const firstDriftBands = firstMount.findAll(
      'input[aria-label="Drift band in percentage points for sleeve-new-1"]',
    );
    await firstNames[0]!.setValue('New sleeve');
    await firstTargets[0]!.setValue('0');
    await firstDriftBands[0]!.setValue('0.25');
    await firstMount.find('button.primary-button').trigger('click');
    await flushPromises();
    expect(savedSleeveKeys[0]).toContain('sleeve-new-1');
    firstMount.unmount();

    const secondMount = mountPage();
    await flushPromises();
    await secondMount
      .findAll('button')
      .find((button) => button.text().includes('Add allocation'))!
      .trigger('click');
    const sleeveKeys = secondMount.findAll('.sleeve-key').map((element) => element.text());
    expect(sleeveKeys).toContain('sleeve-new-1');
    expect(sleeveKeys).toContain('sleeve-new-2');
    expect(new Set(sleeveKeys).size).toBe(sleeveKeys.length);
  });

  it('keeps activation edits dirty while a saved revision activation is pending', async () => {
    const savedDraft: PolicyRevisionResponse = {
      ...activeRevision,
      id: 'revision-saved-synthetic',
      revision_number: 8,
      status: 'DRAFT',
      activated_at: null,
      activation_errors: [],
    };
    let resolveActivation!: (response: Response) => void;
    const fetcher = vi.fn<typeof fetch>((input, init) => {
      const url = requestAddress(input);
      if (url.pathname === '/api/v1/policy' && init?.method !== 'POST') {
        return Promise.resolve(
          jsonResponse({ active: activeRevision, drafts: [savedDraft], superseded: [] }),
        );
      }
      if (url.pathname === '/api/v1/portfolio')
        return Promise.resolve(jsonResponse(notSyncedPortfolioResponse()));
      if (url.pathname.endsWith('/activate'))
        return new Promise<Response>((resolve) => {
          resolveActivation = resolve;
        });
      return Promise.resolve(jsonResponse({}));
    });
    vi.stubGlobal('fetch', fetcher);
    const wrapper = mountWithWorkspace(PolicyPage, {
      global: { plugins: [createPinia()] },
    });
    await flushPromises();
    const activate = wrapper
      .findAll('button')
      .find((button) => button.text().includes('Activate saved revision'))!;
    expect((activate.element as HTMLButtonElement).disabled).toBe(false);

    await activate.trigger('click');
    await flushPromises();
    expect(wrapper.get('.policy-page').element.hasAttribute('inert')).toBe(true);
    expect(wrapper.get('.policy-page').attributes('aria-busy')).toBe('true');
    const taxRate = taxInputByLabel(wrapper, 'Short-term marginal tax rate');
    await taxRate.setValue('0.3000');
    expect(wrapper.text()).toContain('Unsaved changes.');

    resolveActivation(
      jsonResponse({ ...savedDraft, status: 'ACTIVE', activated_at: '2025-02-01T00:00:00Z' }),
    );
    await flushPromises();

    expect(wrapper.text()).toContain('Unsaved changes.');
    expect(wrapper.text()).not.toContain('Current form matches saved revision');
  });

  it('shows parent-disable validation beside the sleeve editor', async () => {
    const parent = activeRevision.sleeves[0]!;
    const revisionWithChild: PolicyRevisionResponse = {
      ...activeRevision,
      sleeves: [
        parent,
        {
          ...parent,
          sleeve_key: 'direct-index',
          display_name: 'Direct index',
          sort_order: 1,
          parent_sleeve_key: 'us',
          target_pct: '100.0000',
          is_direct_index_container: false,
        },
      ],
    };
    const fetcher = vi.fn<typeof fetch>((input) => {
      const url = requestAddress(input);
      if (url.pathname === '/api/v1/policy')
        return Promise.resolve(
          jsonResponse({ active: revisionWithChild, drafts: [], superseded: [] }),
        );
      if (url.pathname === '/api/v1/portfolio')
        return Promise.resolve(jsonResponse(notSyncedPortfolioResponse()));
      return Promise.reject(new Error(`Unhandled local API request: ${url.pathname}`));
    });
    vi.stubGlobal('fetch', fetcher);
    const wrapper = mountWithWorkspace(PolicyPage, {
      global: { plugins: [createPinia()] },
    });
    await flushPromises();

    await setSleeveCheckbox(wrapper, 'Enabled US equity', false);

    expect(wrapper.findAll('[role="group"]').some((group) => group.find('h3').exists())).toBe(
      false,
    );
    const alert = wrapper.get('[role="alert"]');
    expect(alert.text()).toContain(
      'Disable or reparent enabled child sleeves before disabling this parent.',
    );
  });

  it('preserves a dirty editor across refresh and PolicyPage remounts', async () => {
    let policyReads = 0;
    const fetcher = vi.fn<typeof fetch>((input) => {
      const url = requestAddress(input);
      if (url.pathname === '/api/v1/policy') {
        policyReads += 1;
        const policyResponse: PolicyResponse = {
          active: activeRevision,
          drafts: [],
          superseded: [],
        };
        return Promise.resolve(jsonResponse(policyResponse));
      }
      if (url.pathname === '/api/v1/portfolio')
        return Promise.resolve(jsonResponse(notSyncedPortfolioResponse()));
      return Promise.reject(new Error(`Unhandled local API request: ${url.pathname}`));
    });
    vi.stubGlobal('fetch', fetcher);
    const pinia = createPinia();
    const mountPage = () =>
      mountWithWorkspace(PolicyPage, {
        global: { plugins: [pinia] },
      });
    const first = mountPage();
    await flushPromises();
    const taxRate = () => taxInputByLabel(first, 'Short-term marginal tax rate');
    await taxRate().setValue('0.2750000000000000001');
    expect(first.text()).toContain('Unsaved changes.');

    await first
      .findAll('button')
      .find((button) => button.text().includes('Refresh policy list'))!
      .trigger('click');
    await flushPromises();
    expect(taxRate().element).toHaveProperty('value', '0.2750000000000000001');
    expect(policyReads).toBe(2);
    first.unmount();

    const remounted = mountPage();
    await flushPromises();
    expect(taxInputByLabel(remounted, 'Short-term marginal tax rate').element).toHaveProperty(
      'value',
      '0.2750000000000000001',
    );
    expect(remounted.text()).toContain('Unsaved changes.');
    expect(remounted.text()).toContain(activeRevision.id);
    remounted.unmount();

    const unload = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(unload);
    expect(unload.defaultPrevented).toBe(true);
  });
  it('shares one contextual editor with US destination and all-configured draft views', async () => {
    const destination = {
      sleeve_key: 'new',
      display_name: 'Future holdings',
      sort_order: 0,
      parent_sleeve_key: 'us',
      target_pct: '100.0000',
      drift_band_pp: '0.0000',
      is_direct_index_container: false,
      is_direct_index_sleeve: false,
      is_transition_destination: true,
      is_cash_sleeve: false,
      enabled: true,
    };
    const contextualRevision: PolicyRevisionResponse = {
      ...activeRevision,
      sleeves: [...activeRevision.sleeves, destination],
      allowed_securities: [
        ...activeRevision.allowed_securities,
        {
          ticker: 'ITOT',
          sleeve_key: 'us',
          sub_sleeve_key: 'new',
          replacement_set_id: 'us-core',
          priority: 1,
          enabled: true,
          exposure_suitability: null,
        },
        {
          ticker: 'VEA',
          sleeve_key: 'custom-parent',
          sub_sleeve_key: null,
          replacement_set_id: 'custom-set',
          priority: 0,
          enabled: false,
          exposure_suitability: 'Preserved custom destination',
        },
      ],
    };
    const fetcher = vi.fn<typeof fetch>((input) => {
      const url = requestAddress(input);
      if (url.pathname === '/api/v1/policy') {
        const response: PolicyResponse = { active: contextualRevision, drafts: [], superseded: [] };
        return Promise.resolve(jsonResponse(response));
      }
      if (url.pathname === '/api/v1/portfolio')
        return Promise.resolve(jsonResponse(notSyncedPortfolioResponse()));
      return Promise.reject(new Error(`Unhandled local API request: ${url.pathname}`));
    });
    vi.stubGlobal('fetch', fetcher);
    const pinia = createPinia();
    const wrapper = mountWithWorkspace(PolicyPage, {
      attachTo: document.body,
      global: { plugins: [pinia] },
    });
    await flushPromises();

    const transition = wrapper.get('[data-us-transition-settings-root]');
    expect(transition.text()).toContain('New holdings (Future holdings)');
    const usTrigger = wrapper.get('button[data-transition-replacement-trigger="us"]');
    await usTrigger.trigger('click');
    await flushPromises();
    let editorRoot = document.body.querySelector<HTMLElement>(
      '[data-policy-replacement-sets-root]',
    );
    expect(editorRoot).not.toBeNull();
    expect(editorRoot?.querySelectorAll('input[placeholder="Ticker"]').length).toBe(2);
    const itotInput = [
      ...(editorRoot?.querySelectorAll<HTMLInputElement>('input[placeholder="Ticker"]') ?? []),
    ].find((input) => input.value === 'ITOT');
    if (!itotInput) throw new Error('Contextual US candidate ITOT was not rendered');
    itotInput.value = 'ITOT-EDITED';
    itotInput.dispatchEvent(new Event('input', { bubbles: true }));
    await flushPromises();
    expect(useWorkspaceStore(pinia).policyEditor.state.draft.allowedSecurities[1]?.ticker).toBe(
      'ITOT-EDITED',
    );
    const closeButton = document.body.querySelector<HTMLButtonElement>(
      'button[data-slot="sheet-close"]',
    );
    if (!closeButton) throw new Error('Replacement editor close button was not rendered');
    closeButton.click();
    await flushPromises();
    expect(document.activeElement).toBe(usTrigger.element);
    expect(transition.text()).toContain('ITOT-EDITED');

    const destinationTrigger = wrapper.get('button[data-replacement-trigger-key="new"]');
    await destinationTrigger.trigger('click');
    await flushPromises();
    editorRoot = document.body.querySelector<HTMLElement>('[data-policy-replacement-sets-root]');
    expect(editorRoot?.querySelector('h2')?.textContent).toContain('Future holdings');
    expect(
      [...document.body.querySelectorAll<HTMLInputElement>('input[placeholder="Ticker"]')].map(
        (input) => input.value,
      ),
    ).toEqual(['ITOT-EDITED']);
    const childCloseButton = document.body.querySelector<HTMLButtonElement>(
      'button[data-slot="sheet-close"]',
    );
    if (!childCloseButton) throw new Error('Replacement editor close button was not rendered');
    childCloseButton.click();
    await flushPromises();
    expect(document.activeElement).toBe(destinationTrigger.element);

    const allConfiguredTrigger = wrapper.get('button[data-all-replacement-sets-trigger]');
    await allConfiguredTrigger.trigger('click');
    await flushPromises();
    editorRoot = document.body.querySelector<HTMLElement>('[data-policy-replacement-sets-root]');
    expect(editorRoot).not.toBeNull();
    expect(
      [...document.body.querySelectorAll<HTMLInputElement>('input[placeholder="Ticker"]')].map(
        (input) => input.value,
      ),
    ).toEqual(['VTI', 'ITOT-EDITED', 'VEA']);
    const allCloseButton = document.body.querySelector<HTMLButtonElement>(
      'button[data-slot="sheet-close"]',
    );
    if (!allCloseButton) throw new Error('Replacement editor close button was not rendered');
    allCloseButton.click();
    await flushPromises();
    expect(document.activeElement).toBe(allConfiguredTrigger.element);
    wrapper.unmount();
  });
  it('shows only the confirmed active-policy transition and matching selected current-run effects', async () => {
    const { wrapper, pinia, active } = await mountTransitionPolicy();
    const store = useWorkspaceStore(pinia);
    seedCurrentRunForTest(store, selectedRunFixture({ revisionId: active.id }));
    store.currentRunView = 'current';
    await flushPromises();

    const card = wrapper.get('[data-us-transition-settings-root]');
    const table = card.get('[aria-label="US allocation transition comparison"] table');
    const newHoldingsRow = table
      .findAll('tbody tr')
      .find((row) => row.text().includes('API New label'));
    expect(newHoldingsRow?.text()).toContain('20.0000%');
    expect(newHoldingsRow?.text()).toContain('35.0000%');
    expect(newHoldingsRow?.text()).toContain('40.0000%');
    expect(card.text()).toContain('Currently in new holdings');
    expect(card.text()).toContain('Current selected-basket API context');
    expect(
      wrapper
        .findAll('h2')
        .filter((heading) => heading.text().trim() === 'US Equities Transition Policy'),
    ).toHaveLength(1);
    wrapper.unmount();
  });

  it('shows no-selection and setup guidance for an unconfigured destination', async () => {
    const { wrapper } = await mountTransitionPolicy({
      activePolicy: transitionPolicy(false),
      usTransition: transitionResponse({ destination: null }),
    });
    const card = wrapper.get('[data-us-transition-settings-root]');
    expect(card.text()).toContain('Set up US transition');
    expect(card.text()).toContain('No transition destination is designated');
    expect(card.text()).toContain('No trades selected. Proposed values are not shown.');
    expect(card.get('.transition-headline').text()).not.toContain('0.0000%');
    const noTrades = await mountTransitionPolicy();
    const noTradeStore = useWorkspaceStore(noTrades.pinia);
    seedCurrentRunForTest(
      noTradeStore,
      selectedRunFixture({
        revisionId: noTrades.active.id,
        selected: false,
        usTransition: transitionResponse({ proposedNew: '55.0000' }),
      }),
    );
    noTradeStore.currentRunView = 'current';
    await flushPromises();
    const noTradeCard = noTrades.wrapper.get('[data-us-transition-settings-root]');
    expect(noTradeCard.text()).toContain('Current portfolio API context');
    expect(noTradeCard.text()).toContain('No trades selected. Proposed values are not shown.');
    const noTradeRow = noTradeCard
      .get('[aria-label="US allocation transition comparison"] table')
      .findAll('tbody tr')
      .find((row) => row.text().includes('API New label'));
    expect(noTradeRow?.text()).toContain('20.0000%');
    expect(noTradeRow?.text()).toContain('40.0000%');
    expect(noTradeRow?.text()).not.toContain('55.0000%');
    noTrades.wrapper.unmount();
    const table = card.get('[aria-label="US allocation transition comparison"] table');
    expect(table.text()).toContain('40.0000%');
    wrapper.unmount();
  });

  it('withholds selected-trade effects while review is pending or run is stale', async () => {
    const pending = await mountTransitionPolicy();
    const pendingStore = useWorkspaceStore(pending.pinia);
    seedCurrentRunForTest(pendingStore, selectedRunFixture({ revisionId: pending.active.id }));
    pendingStore.currentRunView = 'current';
    pendingStore.reviewMutationCount = 1;
    await flushPromises();
    const pendingCard = pending.wrapper.get('[data-us-transition-settings-root]');
    const pendingRow = pendingCard
      .get('[aria-label="US allocation transition comparison"] table')
      .findAll('tbody tr')
      .find((row) => row.text().includes('API New label'));
    expect(pendingRow?.text()).toContain('Pending');
    expect(pendingRow?.text()).not.toContain('35.0000%');
    pending.wrapper.unmount();

    const stale = await mountTransitionPolicy();
    const staleStore = useWorkspaceStore(stale.pinia);
    seedCurrentRunForTest(
      staleStore,
      selectedRunFixture({ revisionId: stale.active.id, generation: 6 }),
    );
    staleStore.currentRunView = 'current';
    await flushPromises();
    const staleCard = stale.wrapper.get('[data-us-transition-settings-root]');
    const staleRow = staleCard
      .get('[aria-label="US allocation transition comparison"] table')
      .findAll('tbody tr')
      .find((row) => row.text().includes('API New label'));
    expect(staleRow?.text()).toContain('Unavailable (stale effects)');
    expect(staleRow?.text()).not.toContain('35.0000%');
    stale.wrapper.unmount();
  });

  it('withholds backend values for draft editors without losing exact targets', async () => {
    const dirty = await mountTransitionPolicy();
    const dirtyEditor = useWorkspaceStore(dirty.pinia).policyEditor;
    const draftDestination = dirtyEditor.state.draft.sleeves.find(
      (sleeve) => sleeve.sleeve_key === 'new',
    );
    if (!draftDestination) throw new Error('The editable destination sleeve is missing');
    draftDestination.display_name = 'Draft New label';
    draftDestination.target_pct = '73.000000000000000001';
    await flushPromises();
    const dirtyCard = dirty.wrapper.get('[data-us-transition-settings-root]');
    expect(dirtyCard.text()).toContain('unsaved policy draft');
    expect(dirtyCard.text()).toContain('status is withheld');
    expect(dirtyCard.text()).not.toContain('20.0000%');
    expect(dirtyCard.text()).not.toContain('40.0000%');
    const draftTransitionTable = dirtyCard.get(
      '[aria-label="US allocation transition comparison"] table',
    );
    expect(draftTransitionTable.text()).not.toContain('API New label');
    expect(
      dirty.wrapper
        .findAll('input[aria-label^="Target percent"]')
        .some((input) => (input.element as HTMLInputElement).value === '73.000000000000000001'),
    ).toBe(true);
    dirty.wrapper.unmount();

    const inactive = await mountTransitionPolicy();
    const inactiveEditor = useWorkspaceStore(inactive.pinia).policyEditor.state;
    inactiveEditor.sourceRevisionId = 'revision-inactive';
    inactiveEditor.selectedRevisionId = 'revision-inactive';
    await flushPromises();
    const inactiveCard = inactive.wrapper.get('[data-us-transition-settings-root]');
    expect(inactiveCard.text()).toContain('inactive or differently sourced policy revision');
    expect(inactiveCard.text()).not.toContain('20.0000%');
    expect(inactiveCard.text()).not.toContain('40.0000%');
    inactive.wrapper.unmount();
  });

  it('marks portfolio values unverified when revisions differ', async () => {
    const { wrapper } = await mountTransitionPolicy({ portfolioRevisionId: 'revision-previous' });
    const card = wrapper.get('[data-us-transition-settings-root]');
    expect(card.text()).toContain('Unavailable (unverified data)');
    expect(card.text()).not.toContain('20.0000%');
    expect(card.text()).not.toContain('40.0000%');
    wrapper.unmount();
  });
  it('compares only confirmed whole-portfolio root weights against exact same-base targets', async () => {
    const { wrapper } = await mountTransitionPolicy({ currentWeights: { us: '96.0000' } });
    const status = wrapper.get('[aria-labelledby="current-allocation-title"]');
    expect(status.text()).toContain('US equity: current 96.0000% of portfolio; target 100.0000%');
    expect(status.text()).toContain('outside band');
    expect(status.text()).toContain('Nested allocation weights are not supplied');
    wrapper.unmount();
  });
  it('reports exact inclusive allocation bands and unavailable values honestly', async () => {
    for (const [weight, expected] of [
      ['102.2500', 'within band'],
      ['102.250000000000000001', 'outside band'],
      ['-1', 'outside band'],
      ['invalid', 'status unavailable'],
    ] as const) {
      const { wrapper } = await mountTransitionPolicy({ currentWeights: { us: weight } });
      const status = wrapper.get('[aria-labelledby="current-allocation-title"]');
      expect(status.text()).toContain(expected);
      wrapper.unmount();
    }

    const missing = await mountTransitionPolicy({ currentWeights: {} });
    expect(missing.wrapper.get('[aria-labelledby="current-allocation-title"]').text()).toContain(
      'status unavailable',
    );
    missing.wrapper.unmount();
  });

  it('keeps populated allocation weights withheld for dirty or mismatched policy context', async () => {
    const dirty = await mountTransitionPolicy({ currentWeights: { us: '96.0000' } });
    const dirtyEditor = useWorkspaceStore(dirty.pinia).policyEditor.state.draft;
    dirtyEditor.sleeves.find((sleeve) => sleeve.sleeve_key === 'us')!.target_pct = '99';
    await flushPromises();
    expect(dirty.wrapper.get('[aria-labelledby="current-allocation-title"]').text()).not.toContain(
      'US equity: current',
    );
    dirty.wrapper.unmount();

    const mismatch = await mountTransitionPolicy({
      currentWeights: { us: '96.0000' },
      portfolioRevisionId: 'revision-previous',
    });
    expect(
      mismatch.wrapper.get('[aria-labelledby="current-allocation-title"]').text(),
    ).not.toContain('US equity: current');
    mismatch.wrapper.unmount();

    const stale = await mountTransitionPolicy({ currentWeights: { us: '96.0000' } });
    getTestQueryClientForPinia(stale.pinia)
      .getQueryCache()
      .find({ queryKey: workspaceQueryKeys.portfolio })
      ?.setState({
        status: 'error',
        error: new Error('test stale portfolio read'),
        fetchStatus: 'idle',
        errorUpdateCount: 1,
      });
    await flushPromises();
    expect(stale.wrapper.get('[aria-labelledby="current-allocation-title"]').text()).not.toContain(
      'US equity: current',
    );
    stale.wrapper.unmount();
  });

  it('places the gradual-target explanation beside allocation editing', async () => {
    const { wrapper } = await mountTransitionPolicy();
    const allocation = wrapper.get('[aria-labelledby="current-allocation-title"]').element;
    const explanation = allocation.nextElementSibling;
    expect(explanation?.textContent).toContain('gradual destinations, not immediate liquidation');
    expect(explanation?.textContent).toContain('tax, wash-sale, gain-budget, batch, and risk');
    expect(explanation?.textContent).toContain('0% target does not mean sell immediately');
    expect(explanation?.textContent).toContain('individual user approval');
    wrapper.unmount();
  });

  it('summarizes edited policy limits and approval behavior without presenting draft weights as current', async () => {
    const { wrapper, pinia } = await mountTransitionPolicy();
    const overview = wrapper.get('[aria-labelledby="policy-overview-title"]');
    expect(overview.text()).toContain(
      'Enabled allocation count includes top-level and nested sleeves',
    );
    expect(overview.text()).toContain('3 of 3 (top-level and nested)');
    expect(overview.text()).toContain('2.2500, 0.0000 percentage points by allocation');
    expect(overview.text()).toContain('Not configured');
    const budget = useWorkspaceStore(pinia).policyEditor.state.draft.settings;
    budget.gain_budget_usd = '';
    await flushPromises();
    expect(overview.text()).toContain('Not configured USD');
    budget.gain_budget_usd = '0';
    await flushPromises();
    expect(overview.text()).toContain('0 USD');
    expect(overview.text()).toContain('10 / 20 / 12');
    expect(wrapper.get('[data-policy-tax-settings-root]').text()).toContain(
      'each order requires individual user approval',
    );
    expect(wrapper.get('[aria-labelledby="current-allocation-title"]').text()).toContain(
      'unverified',
    );
    wrapper.unmount();
  });
});

// @vitest-environment jsdom
import { flushPromises } from '@vue/test-utils';
import { mountWithWorkspace } from '@/test-utils/workspace-mount';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';
import type {
  PolicyDraftInput,
  PolicyRevisionResponse,
  PolicyResponse,
  PolicySettingsResponse,
} from '@/types/api';
import PolicyPage from './PolicyPage.vue';
import { useWorkspaceStore } from '@/stores/workspace-store';
import { Select } from '@/components/ui/select';

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
    const row = wrapper.findAll('tbody tr').find((candidate) => {
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
    const statusBadges = wrapper.findAll('[data-slot="badge"]');
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
    const target = wrapper.find('input[aria-label="Target percent for US equity"]');
    await setSleeveCheckbox(wrapper, 'Transition destination sub-sleeve for US equity', true);
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
    expect(savedPayload?.sleeves[0]?.is_transition_destination).toBe(true);
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
      .find((button) => button.text().includes('Add sleeve'))!
      .trigger('click');
    const firstNames = firstMount.findAll(
      'input[aria-label="Sleeve display name for sleeve-new-1"]',
    );
    const firstTargets = firstMount.findAll('input[aria-label="Target percent for sleeve-new-1"]');
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
      .find((button) => button.text().includes('Add sleeve'))!
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
});

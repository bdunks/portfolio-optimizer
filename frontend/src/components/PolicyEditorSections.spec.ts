// @vitest-environment jsdom
import { mount } from '@vue/test-utils';
import { reactive } from 'vue';
import { QBanner, QCard, QCheckbox, QMarkupTable, QSelect } from 'quasar';
import { findQuasarComponent, setQuasarModelValue } from '@/test-utils/quasar-mount';
import { describe, expect, it } from 'vitest';
import PolicyHoldingOverridesEditor from './PolicyHoldingOverridesEditor.vue';
import PolicyReplacementSetsEditor from './PolicyReplacementSetsEditor.vue';
import PolicySleevesEditor from './PolicySleevesEditor.vue';
import PolicyTaxBatchSettings from './PolicyTaxBatchSettings.vue';
import {
  createEmptyPolicyDraft,
  createEmptyPolicySettings,
  type EditableSleeve,
  type EditablePolicySettings,
} from '@/pages/policy-form';
import type { PositionResponse } from '@/types/api';

function sleeve(key: string, values: Partial<EditableSleeve> = {}): EditableSleeve {
  return {
    sleeve_key: key,
    display_name: key,
    sort_order: 0,
    parent_sleeve_key: null,
    target_pct: '0',
    drift_band_pp: '0',
    is_direct_index_container: false,
    is_direct_index_sleeve: false,
    is_transition_destination: false,
    is_cash_sleeve: false,
    enabled: true,
    ...values,
  };
}

function position(
  ticker: string,
  sleeveKey: string | null,
  subSleeveKey: string | null = null,
): PositionResponse {
  return {
    ticker,
    asset_type: 'EQUITY',
    shares: '1',
    market_value_usd: '100.00',
    last_price_usd: '100.00',
    quote_source: 'fixture',
    quote_as_of: '2025-01-31T00:00:00Z',
    sleeve_key: sleeveKey,
    sub_sleeve_key: subSleeveKey,
  };
}

function expectRealMarkupTable(wrapper: ReturnType<typeof mount>, caption: string): void {
  expectRealQuasarCard(wrapper);
  const markup = wrapper.findComponent(QMarkupTable);
  expect(markup.exists()).toBe(true);
  expect(markup.attributes('tabindex')).toBe('0');
  const tables = markup.element.querySelectorAll('table');
  expect(tables).toHaveLength(1);
  const table = tables.item(0);
  expect(table.querySelector('caption')?.textContent?.replace(/\s+/g, ' ').trim()).toBe(caption);
  const headers = table.querySelectorAll('thead th');
  expect(headers.length).toBeGreaterThan(0);
  expect(table.querySelectorAll('thead th[scope="col"]')).toHaveLength(headers.length);
  const region = markup.element.closest('[role="region"]');
  expect(region?.getAttribute('tabindex')).toBe('0');
  expect(region?.getAttribute('aria-label')).toBeTruthy();
}

function expectRealQuasarCard(wrapper: ReturnType<typeof mount>, tagName = 'section'): void {
  const card = wrapper.findComponent(QCard);
  expect(card.exists()).toBe(true);
  expect(card.element.tagName.toLowerCase()).toBe(tagName);
  expect(card.classes()).toContain('q-card');
  expect(card.classes()).toContain('q-pa-md');
}

describe('purpose-built policy editor sections', () => {
  it('keeps financial settings and batch limits as editable strings and preserves explicit booleans', async () => {
    const settings = reactive(createEmptyPolicySettings());
    const wrapper = mount(PolicyTaxBatchSettings, {
      props: {
        settings,
        'onUpdate:settings': (next: EditablePolicySettings) => Object.assign(settings, next),
      },
    });
    expectRealQuasarCard(wrapper);
    const field = (label: string) =>
      wrapper.findAll('label').find((candidate) => candidate.text().includes(label))!;

    await field('Short-term marginal tax rate').get('input').setValue('0.2500000000000000001');
    expect(settings.short_term_tax_rate).toBe('0.2500000000000000001');
    await field('ST loss carryforward').get('input').setValue('');
    expect(settings.st_loss_carryforward_usd).toBe('');
    await field('Maximum sell tickers per batch').get('input').setValue('12');
    expect(settings.max_sell_tickers_per_batch).toBe('12');
    await field('Cash reserve').get('input').setValue('0.00');
    expect(settings.cash_reserve_usd).toBe('0.00');
    await setQuasarModelValue(wrapper, QSelect, 'Prefer ETF buys', false);
    expect(settings.prefer_etf_buys).toBe(false);
  });

  it('gives multiple instances distinct accessible section IDs', () => {
    const host = {
      components: { PolicyTaxBatchSettings },
      setup: () => ({
        first: reactive(createEmptyPolicySettings()),
        second: reactive(createEmptyPolicySettings()),
      }),
      template:
        '<div><PolicyTaxBatchSettings :settings="first" /><PolicyTaxBatchSettings :settings="second" /></div>',
    };
    const wrapper = mount(host);
    const cards = wrapper.findAllComponents(QCard);
    expect(cards).toHaveLength(2);
    expect(cards.map((card) => card.element.tagName.toLowerCase())).toEqual(['section', 'section']);
    const headings = wrapper.findAll('h2');
    const ids = headings.map((heading) => heading.attributes('id'));
    expect(new Set(ids).size).toBe(2);
    expect(headings[0]?.element.closest('section')?.getAttribute('aria-labelledby')).toBe(ids[0]);
    expect(headings[1]?.element.closest('section')?.getAttribute('aria-labelledby')).toBe(ids[1]);
  });

  it('edits nested sleeve roles, stable keys, order, and explicit holdings on deletion', async () => {
    const draft = reactive(createEmptyPolicyDraft());
    draft.sleeves = [
      sleeve('us', { display_name: 'US equities', is_direct_index_container: true }),
      sleeve('legacy', {
        display_name: 'Direct indexing',
        parent_sleeve_key: 'us',
        is_direct_index_sleeve: true,
      }),
      sleeve('destination', {
        display_name: 'Transition destination',
        parent_sleeve_key: 'us',
        is_transition_destination: true,
      }),
      sleeve('cash', { display_name: 'Cash', is_cash_sleeve: true }),
      sleeve('other', { display_name: 'Other' }),
    ];
    const wrapper = mount(PolicySleevesEditor, {
      props: {
        draft,
        positions: [position('AAPL', 'us', 'legacy')],
        targetIssues: [],
        sourceRevisionId: null,
        'onUpdate:sleeves': (next: EditableSleeve[]) => {
          draft.sleeves = next;
        },
        'onUpdate:reassignments': (
          next: Record<string, string>,
          holdings: Record<string, string[]>,
        ) => {
          draft.reassignments = next;
          draft.reassignmentHoldings = holdings;
        },
      },
    });
    expectRealMarkupTable(wrapper, 'Configured sleeves and their allocation policy settings');

    await wrapper.find('input[aria-label="Target percent"]').setValue('45.000000000000001');
    expect(draft.sleeves[0]?.target_pct).toBe('45.000000000000001');
    await wrapper.find('button[aria-label="Move Direct indexing down"]').trigger('click');
    expect(draft.sleeves.map((item) => item.sleeve_key)).toEqual([
      'us',
      'destination',
      'legacy',
      'cash',
      'other',
    ]);
    await wrapper.find('button[aria-label="Move Other up"]').trigger('click');
    expect(draft.sleeves.map((item) => item.sleeve_key).slice(-2)).toEqual(['other', 'cash']);

    const container = wrapper.findAllComponents(QCheckbox)[0]!;
    const otherContainer = wrapper
      .findAllComponents(QCheckbox)
      .find(
        (checkbox) =>
          checkbox.props().label === 'Direct-index container' &&
          checkbox.element.closest('tr')?.querySelector('.sleeve-key')?.textContent?.trim() ===
            'other',
      )!;
    const designationCell = otherContainer.element.closest('td');
    expect(designationCell?.classList.contains('text-caption')).toBe(true);
    expect(designationCell?.classList.contains('text-blue-grey-8')).toBe(true);
    otherContainer.vm.$emit('update:modelValue', true);
    expect(draft.sleeves.find((item) => item.sleeve_key === 'us')?.is_direct_index_container).toBe(
      false,
    );
    expect(
      draft.sleeves.find((item) => item.sleeve_key === 'other')?.is_direct_index_container,
    ).toBe(true);
    expect(container.exists()).toBe(true);
    expect(draft.sleeves.find((item) => item.sleeve_key === 'cash')?.is_cash_sleeve).toBe(true);
    expect(
      draft.sleeves.find((item) => item.sleeve_key === 'destination')?.is_transition_destination,
    ).toBe(true);

    await wrapper
      .findAll('button')
      .find(
        (button) =>
          button.text() === 'Delete' &&
          button.element.closest('tr')?.querySelector('.sleeve-key')?.textContent?.trim() === 'us',
      )!
      .trigger('click');
    const deletePanel = wrapper.get('.delete-panel.q-card[role="group"]');
    expect(deletePanel.attributes('aria-labelledby')).toBe(deletePanel.get('h3').attributes('id'));
    await setQuasarModelValue(wrapper, QSelect, 'Holding reassignment destination', 'other');
    await setQuasarModelValue(wrapper, QSelect, 'New parent for Direct indexing', 'other');
    await setQuasarModelValue(wrapper, QSelect, 'New parent for Transition destination', 'other');
    await wrapper.find('button.danger-button:not(.small-button)').trigger('click');

    expect(draft.sleeves.some((item) => item.sleeve_key === 'us')).toBe(false);
    expect(draft.sleeves.find((item) => item.sleeve_key === 'legacy')?.parent_sleeve_key).toBe(
      'other',
    );
    expect(draft.sleeves.find((item) => item.sleeve_key === 'destination')?.parent_sleeve_key).toBe(
      'other',
    );
    expect(draft.reassignments).toEqual({ us: 'other' });
    expect(draft.reassignmentHoldings).toEqual({ us: ['AAPL'] });
  });

  it('keeps replacement candidate ordering grouped by set and edits enabled metadata', async () => {
    const draft = reactive(createEmptyPolicyDraft());
    draft.sleeves = [
      sleeve('us', { display_name: 'US equities' }),
      sleeve('new', { display_name: 'Transition destination', parent_sleeve_key: 'us' }),
    ];
    draft.allowedSecurities = [
      {
        ticker: 'VTI',
        sleeve_key: 'us',
        sub_sleeve_key: null,
        replacement_set_id: 'us-core',
        priority: 0,
        enabled: true,
        exposure_suitability: 'Broad market',
      },
      {
        ticker: 'ITOT',
        sleeve_key: 'us',
        sub_sleeve_key: null,
        replacement_set_id: 'us-core',
        priority: 1,
        enabled: true,
        exposure_suitability: null,
      },
    ];
    const wrapper = mount(PolicyReplacementSetsEditor, {
      props: {
        draft,
        'onUpdate:allowed-securities': (next) => {
          draft.allowedSecurities = next;
        },
      },
    });
    expectRealMarkupTable(wrapper, 'Configured ETF replacement candidates and policy settings');
    const enabledToggle = findQuasarComponent(wrapper, QCheckbox, 'Enabled');
    expect(enabledToggle.classes()).toEqual(
      expect.arrayContaining(['text-caption', 'text-weight-bold', 'text-blue-grey-8']),
    );

    await wrapper.find('button[aria-label="Move VTI down"]').trigger('click');
    expect(draft.allowedSecurities.map((item) => [item.ticker, item.priority])).toEqual([
      ['ITOT', 0],
      ['VTI', 1],
    ]);
    await wrapper
      .find('input[aria-label="Exposure suitability note"]')
      .setValue('Total-market ETF');
    expect(draft.allowedSecurities[0]?.exposure_suitability).toBe('Total-market ETF');
    await setQuasarModelValue(wrapper, QCheckbox, 'Enabled', false);
    expect(draft.allowedSecurities[0]?.enabled).toBe(false);
    await wrapper.find('button[aria-label="Remove ITOT"]').trigger('click');
    expect(draft.allowedSecurities.map((item) => item.ticker)).toEqual(['VTI']);
  });

  it('supports explicit sub-sleeve reassignment, default removal, and disabled saved targets', async () => {
    const draft = reactive(createEmptyPolicyDraft());
    draft.sleeves = [
      sleeve('us', { display_name: 'US equities' }),
      sleeve('direct', { display_name: 'Direct index', parent_sleeve_key: 'us' }),
      sleeve('other', { display_name: 'Other' }),
      sleeve('disabled', { display_name: 'Legacy disabled', enabled: false }),
    ];
    draft.overrides = [
      { ticker: 'AAPL', sleeve_key: 'us', sub_sleeve_key: 'direct' },
      { ticker: 'OLD', sleeve_key: 'disabled', sub_sleeve_key: null },
    ];
    const wrapper = mount(PolicyHoldingOverridesEditor, {
      props: {
        draft,
        positions: [position('AAPL', 'us', 'direct')],
        portfolioAvailable: true,
        portfolioLoading: false,
        'onUpdate:overrides': (next) => {
          draft.overrides = next;
        },
      },
    });
    expectRealMarkupTable(
      wrapper,
      'Current API sleeve resolutions and explicit overrides by ticker',
    );

    expect(wrapper.text()).toContain('us → direct');
    expect(findQuasarComponent(wrapper, QSelect, 'Explicit override for OLD').text()).toContain(
      'Current assignment — disabled',
    );
    await setQuasarModelValue(wrapper, QSelect, 'Explicit override for AAPL', 'other');
    expect(draft.overrides.find((item) => item.ticker === 'AAPL')).toEqual({
      ticker: 'AAPL',
      sleeve_key: 'other',
      sub_sleeve_key: null,
    });
    await setQuasarModelValue(wrapper, QSelect, 'Explicit override for AAPL', '');
    expect(draft.overrides.map((item) => item.ticker)).toEqual(['OLD']);
    expect(wrapper.text()).toContain('OLD');
  });
  it('emits typed section updates without mutating draft props before the parent applies them', async () => {
    const sleeveDraft = reactive(createEmptyPolicyDraft());
    sleeveDraft.sleeves = [sleeve('us')];
    const sleevesBefore = sleeveDraft.sleeves;
    const sleeveWrapper = mount(PolicySleevesEditor, {
      props: {
        draft: sleeveDraft,
        positions: null,
        targetIssues: [],
        sourceRevisionId: 'source',
      },
    });
    await sleeveWrapper.find('input[aria-label="Target percent"]').setValue('0.00000001');
    expect(sleeveDraft.sleeves).toBe(sleevesBefore);
    expect(sleeveDraft.sleeves[0]?.target_pct).toBe('0');
    const sleeveUpdate = sleeveWrapper.emitted('update:sleeves')?.[0]?.[0] as EditableSleeve[];
    expect(sleeveUpdate[0]?.target_pct).toBe('0.00000001');

    const replacementDraft = reactive(createEmptyPolicyDraft());
    replacementDraft.allowedSecurities = [
      {
        ticker: 'VTI',
        sleeve_key: 'us',
        replacement_set_id: 'us-core',
        priority: 0,
        enabled: true,
        exposure_suitability: 'Before edit',
      },
    ];
    const securitiesBefore = replacementDraft.allowedSecurities;
    const replacementWrapper = mount(PolicyReplacementSetsEditor, {
      props: { draft: replacementDraft },
    });
    await replacementWrapper
      .find('input[aria-label="Exposure suitability note"]')
      .setValue('After edit');
    expect(replacementDraft.allowedSecurities).toBe(securitiesBefore);
    expect(replacementDraft.allowedSecurities[0]?.exposure_suitability).toBe('Before edit');
    const securityUpdate = replacementWrapper.emitted('update:allowed-securities')?.[0]?.[0] as {
      exposure_suitability?: string | null;
    }[];
    expect(securityUpdate[0]?.exposure_suitability).toBe('After edit');

    const overrideDraft = reactive(createEmptyPolicyDraft());
    overrideDraft.sleeves = [sleeve('us'), sleeve('other')];
    overrideDraft.overrides = [{ ticker: 'AAPL', sleeve_key: 'us', sub_sleeve_key: null }];
    const overridesBefore = overrideDraft.overrides;
    const overrideWrapper = mount(PolicyHoldingOverridesEditor, {
      props: {
        draft: overrideDraft,
        positions: [position('AAPL', 'us')],
        portfolioAvailable: true,
        portfolioLoading: false,
      },
    });
    await setQuasarModelValue(overrideWrapper, QSelect, 'Explicit override for AAPL', 'other');
    expect(overrideDraft.overrides).toBe(overridesBefore);
    expect(overrideDraft.overrides[0]?.sleeve_key).toBe('us');
    const overrideUpdate = overrideWrapper.emitted('update:overrides')?.[0]?.[0] as {
      ticker: string;
      sleeve_key: string;
      sub_sleeve_key: string | null;
    }[];
    expect(overrideUpdate).toEqual([{ ticker: 'AAPL', sleeve_key: 'other', sub_sleeve_key: null }]);

    sleeveWrapper.unmount();
    replacementWrapper.unmount();
    overrideWrapper.unmount();
  });
  it('renders policy feedback as explicit polite or assertive Quasar banners', async () => {
    const loading = mount(PolicyHoldingOverridesEditor, {
      props: {
        draft: createEmptyPolicyDraft(),
        positions: null,
        portfolioAvailable: false,
        portfolioLoading: true,
      },
    });
    const loadingBanner = loading.getComponent(QBanner);
    expect(loadingBanner.attributes('role')).toBe('status');
    expect(loadingBanner.text()).toContain('Loading the current single-account holding list');

    const invalidDraft = reactive(createEmptyPolicyDraft());
    invalidDraft.sleeves = [sleeve('us')];
    const validation = mount(PolicySleevesEditor, {
      props: {
        draft: invalidDraft,
        positions: null,
        targetIssues: ['Enabled targets must sum exactly 100%'],
        sourceRevisionId: null,
      },
    });
    const validationBanner = validation.getComponent(QBanner);
    expect(validationBanner.attributes('role')).toBe('status');
    expect(validationBanner.attributes('aria-live')).toBe('polite');
    expect(validationBanner.text()).toContain('Enabled targets must sum exactly 100%');

    const errorDraft = reactive(createEmptyPolicyDraft());
    errorDraft.sleeves = [sleeve('parent'), sleeve('child', { parent_sleeve_key: 'parent' })];
    const editor = mount(PolicySleevesEditor, {
      props: {
        draft: errorDraft,
        positions: null,
        targetIssues: [],
        sourceRevisionId: null,
      },
    });
    await setQuasarModelValue(editor, QCheckbox, 'Enabled', false);
    const alertBanner = editor
      .findAllComponents(QBanner)
      .find((banner) => banner.attributes('role') === 'alert');
    expect(alertBanner).toBeDefined();
    expect(alertBanner!.text()).toContain('Disable or reparent enabled child sleeves');
  });
});

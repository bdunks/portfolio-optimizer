// @vitest-environment jsdom
import { mount } from '@vue/test-utils';
import { nextTick, reactive } from 'vue';
import { describe, expect, it } from 'vitest';
import PolicyHoldingOverridesEditor from './PolicyHoldingOverridesEditor.vue';
import PolicyReplacementSetsEditor from './PolicyReplacementSetsEditor.vue';
import PolicySleevesEditor from './PolicySleevesEditor.vue';
import PolicyTaxBatchSettings from './PolicyTaxBatchSettings.vue';
import { Checkbox } from '@/components/ui/checkbox';
import { Select, SelectItem } from '@/components/ui/select';
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

function expectSleeveTable(wrapper: ReturnType<typeof mount>, caption: string): void {
  const editor = wrapper.find('[data-policy-sleeves-root]');
  expect(editor.exists()).toBe(true);
  expect(editor.find('[data-slot="card"]').exists()).toBe(true);
  const region = editor.find('[role="region"][aria-label="Sleeve allocation policy settings"]');
  expect(region.exists()).toBe(true);
  expect(region.attributes('tabindex')).toBe('0');
  const table = region.get('table');
  expect(table.find('caption').text().replace(/\s+/g, ' ').trim()).toBe(caption);
  expect(table.findAll('thead th[scope="col"]').map((header) => header.text().trim())).toEqual([
    'Order / sleeve key',
    'Name',
    'Parent',
    'Target (%)',
    'Drift band (pp)',
    'Designations',
    'Enabled',
    'Actions',
  ]);
  const controls = editor.findAll(
    'input, button[data-slot="checkbox"], button[data-slot="select-trigger"]',
  );
  const ids = controls.map((control) => control.attributes('id'));
  expect(ids.every(Boolean)).toBe(true);
  expect(new Set(ids).size).toBe(ids.length);
}

function sleeveCheckbox(wrapper: ReturnType<typeof mount>, labelText: string) {
  const label = wrapper
    .findAll('label')
    .find((candidate) => candidate.text().replace(/\s+/g, ' ').trim() === labelText);
  if (!label) throw new Error(`Sleeve checkbox label not found: ${labelText}`);
  const id = label.attributes('for');
  if (!id) throw new Error(`Sleeve checkbox label is not associated: ${labelText}`);
  return wrapper.get(`[data-slot="checkbox"][id="${id}"]`);
}

async function setSleeveCheckboxValue(
  wrapper: ReturnType<typeof mount>,
  labelText: string,
  checked: boolean,
): Promise<void> {
  const checkbox = sleeveCheckbox(wrapper, labelText);
  if (checkbox.attributes('aria-checked') !== String(checked)) await checkbox.trigger('click');
  await nextTick();
}

function sleeveDeletionPanel(wrapper: ReturnType<typeof mount>) {
  return wrapper.findAll('[role="group"]').find((candidate) => candidate.find('h3').exists());
}

function sleeveSelect(wrapper: ReturnType<typeof mount>, labelText: string) {
  const label = wrapper
    .findAll('label')
    .find((candidate) => candidate.text().replace(/\s+/g, ' ').trim() === labelText);
  if (!label) throw new Error(`Sleeve select label not found: ${labelText}`);
  const labelId = label.attributes('id');
  if (!labelId) throw new Error(`Sleeve select label has no ID: ${labelText}`);
  const select = wrapper
    .findAllComponents(Select)
    .find((candidate) =>
      candidate.find(`[data-slot="select-trigger"][aria-labelledby="${labelId}"]`).exists(),
    );
  if (!select) throw new Error(`Sleeve select not found: ${labelText}`);
  return {
    select,
    triggerId: select
      .get(`[data-slot="select-trigger"][aria-labelledby="${labelId}"]`)
      .attributes('id'),
  };
}

async function setSleeveSelectValue(
  wrapper: ReturnType<typeof mount>,
  labelText: string,
  optionLabel: string,
): Promise<void> {
  const { select, triggerId } = sleeveSelect(wrapper, labelText);
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
  select.vm.$emit('update:modelValue', token);
  await nextTick();
}

function expectOverrideTable(wrapper: ReturnType<typeof mount>, caption: string): HTMLTableElement {
  const editor = wrapper.find('[data-policy-holding-overrides-root]');
  expect(editor.exists()).toBe(true);
  expect(editor.find('[data-slot="card"]').exists()).toBe(true);
  const region = editor.find('[role="region"][aria-label="Holding sleeve overrides"]');
  expect(region.exists()).toBe(true);
  expect(region.attributes('tabindex')).toBe('0');
  const table = region.get('table');
  expect(table.find('caption').text().replace(/\s+/g, ' ').trim()).toBe(caption);
  const headers = table.findAll('thead th[scope="col"]');
  expect(headers.map((header) => header.text().trim())).toEqual([
    'Ticker',
    'Current API resolution',
    'Explicit override',
  ]);
  const controls = table.findAll('button[data-slot="select-trigger"]');
  const controlIds = controls.map((control) => control.attributes('id'));
  expect(controlIds.every(Boolean)).toBe(true);
  expect(new Set(controlIds).size).toBe(controlIds.length);
  for (const control of controls) {
    const labelId = control.attributes('aria-labelledby');
    const label = labelId ? wrapper.element.querySelector(`[id="${labelId}"]`) : null;
    expect(label?.textContent).toMatch(/^\s*Explicit override for \S+\s*$/);
  }
  return table.element;
}
function expectReplacementTable(
  wrapper: ReturnType<typeof mount>,
  caption: string,
): HTMLTableElement {
  const editor = wrapper.find('[data-policy-replacement-sets-root]');
  expect(editor.exists()).toBe(true);
  expect(editor.find('[data-slot="card"]').exists()).toBe(true);
  const region = editor.find('[role="region"][aria-label="Replacement security candidates"]');
  expect(region.exists()).toBe(true);
  expect(region.attributes('tabindex')).toBe('0');
  const table = region.get('table');
  expect(table.find('caption').text().replace(/\s+/g, ' ').trim()).toBe(caption);
  expect(table.findAll('thead th[scope="col"]').map((header) => header.text().trim())).toEqual([
    'Order',
    'Ticker',
    'Replacement set ID',
    'Priority',
    'Parent sleeve',
    'Sub-sleeve',
    'Exposure suitability (API note)',
    'Enabled',
    'Actions',
  ]);
  return table.element;
}

function replacementInput(wrapper: ReturnType<typeof mount>, labelText: string) {
  const label = wrapper
    .findAll('label')
    .find((candidate) => candidate.text().replace(/\s+/g, ' ').trim() === labelText);
  if (!label) throw new Error(`Replacement input label not found: ${labelText}`);
  const inputId = label.attributes('for');
  if (!inputId) throw new Error(`Replacement input label is not associated: ${labelText}`);
  return wrapper.get(`[id="${inputId}"]`);
}

function overrideSelect(wrapper: ReturnType<typeof mount>, ticker: string) {
  const row = wrapper
    .findAll('tbody tr')
    .find((candidate) => candidate.find('th[scope="row"]').text().trim() === ticker);
  if (!row) throw new Error(`Override table row not found: ${ticker}`);
  const select = row.findComponent(Select);
  if (!select.exists()) throw new Error(`Override select not found: ${ticker}`);
  return select;
}

async function setOverrideSelectValue(
  wrapper: ReturnType<typeof mount>,
  ticker: string,
  value: string,
): Promise<void> {
  overrideSelect(wrapper, ticker).vm.$emit('update:modelValue', value);
  await nextTick();
}

async function openOverrideSelect(
  wrapper: ReturnType<typeof mount>,
  ticker: string,
): Promise<void> {
  await overrideSelect(wrapper, ticker).get('[data-slot="select-trigger"]').trigger('click');
  await nextTick();
}

function findOverrideOption(wrapper: ReturnType<typeof mount>, label: string) {
  return wrapper
    .findAllComponents(SelectItem)
    .find((item) => item.text().replace(/\s+/g, ' ').trim() === label);
}

describe('purpose-built policy editor sections', () => {
  it('keeps financial settings and batch limits as editable strings and preserves explicit booleans', async () => {
    const settings = reactive(createEmptyPolicySettings());
    const wrapper = mount(PolicyTaxBatchSettings, {
      props: {
        settings,
        sourceRevisionId: null,
        'onUpdate:settings': (next: EditablePolicySettings) => Object.assign(settings, next),
      },
    });
    expect(wrapper.find('section[data-policy-tax-settings-root]').exists()).toBe(true);
    expect(wrapper.get('[role="heading"][aria-level="2"]').text()).toContain(
      'Tax & Batch Settings',
    );
    const label = (labelText: string) =>
      wrapper.findAll('label').find((candidate) => candidate.text().includes(labelText))!;
    const field = (labelText: string) =>
      wrapper.get(`[id="${label(labelText).attributes('for')}"]`);

    const shortTermLabel = label('Short-term marginal tax rate');
    const shortTermInput = field('Short-term marginal tax rate');
    expect(shortTermLabel.attributes('for')).toBe(shortTermInput.attributes('id'));
    await shortTermInput.setValue('0.2500000000000000001');
    expect(settings.short_term_tax_rate).toBe('0.2500000000000000001');
    await field('ST loss carryforward').setValue('');
    expect(settings.st_loss_carryforward_usd).toBe('');
    await field('Maximum sell tickers per batch').setValue('12');
    expect(settings.max_sell_tickers_per_batch).toBe('12');
    await field('Cash reserve').setValue('0.00');
    expect(settings.cash_reserve_usd).toBe('0.00');
    const preference = wrapper.findComponent(Select);
    expect(preference.exists()).toBe(true);
    preference.vm.$emit('update:modelValue', 'disabled');
    expect(settings.prefer_etf_buys).toBe(false);
    preference.vm.$emit('update:modelValue', 'choose');
    expect(settings.prefer_etf_buys).toBeNull();
  });
  it('gives multiple instances distinct accessible section IDs', () => {
    const host = {
      components: { PolicyTaxBatchSettings },
      setup: () => ({
        first: reactive(createEmptyPolicySettings()),
        second: reactive(createEmptyPolicySettings()),
      }),
      template: `
        <div>
          <PolicyTaxBatchSettings :settings="first" source-revision-id="first" />
          <PolicyTaxBatchSettings :settings="second" source-revision-id="second" />
        </div>
      `,
    };
    const wrapper = mount(host);
    const sections = wrapper.findAll('section[data-policy-tax-settings-root]');
    expect(sections).toHaveLength(2);
    const headings = wrapper.findAll('[role="heading"][aria-level="2"]');
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
    const originalSleeves = draft.sleeves;
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
    expectSleeveTable(wrapper, 'Configured sleeves and their allocation policy settings');
    expect(wrapper.text()).toContain(
      'Top-level targets and every populated nested allocation must total exactly 100%. Drift bands use percentage points. No tolerance, implicit cash sleeve, or normalization is applied. Transition progress uses an explicitly designated destination sub-sleeve and all descendants regardless of security type; it remains unavailable when no destination is configured.',
    );

    await wrapper
      .get('input[aria-label="Target percent for US equities"]')
      .setValue('45.000000000000001');
    expect(draft.sleeves).not.toBe(originalSleeves);
    expect(draft.sleeves[0]?.target_pct).toBe('45.000000000000001');
    await wrapper.get('button[aria-label="Move Direct indexing down"]').trigger('click');
    expect(draft.sleeves.map((item) => item.sleeve_key)).toEqual([
      'us',
      'destination',
      'legacy',
      'cash',
      'other',
    ]);
    await wrapper.get('button[aria-label="Move Other up"]').trigger('click');
    expect(draft.sleeves.map((item) => item.sleeve_key).slice(-2)).toEqual(['other', 'cash']);

    await setSleeveCheckboxValue(wrapper, 'Direct-index container for Other', true);
    expect(draft.sleeves.find((item) => item.sleeve_key === 'us')?.is_direct_index_container).toBe(
      false,
    );
    expect(
      draft.sleeves.find((item) => item.sleeve_key === 'other')?.is_direct_index_container,
    ).toBe(true);
    await setSleeveCheckboxValue(wrapper, 'Direct-index sleeve for Other', true);
    expect(draft.sleeves.find((item) => item.sleeve_key === 'legacy')?.is_direct_index_sleeve).toBe(
      true,
    );
    expect(draft.sleeves.find((item) => item.sleeve_key === 'other')?.is_direct_index_sleeve).toBe(
      true,
    );
    await setSleeveCheckboxValue(wrapper, 'Transition destination sub-sleeve for Other', true);
    expect(
      draft.sleeves.find((item) => item.sleeve_key === 'destination')?.is_transition_destination,
    ).toBe(false);
    expect(
      draft.sleeves.find((item) => item.sleeve_key === 'other')?.is_transition_destination,
    ).toBe(true);
    expect(draft.sleeves.find((item) => item.sleeve_key === 'cash')?.is_cash_sleeve).toBe(true);

    await wrapper.get('button[aria-label="Delete US equities"]').trigger('click');
    const deletePanel = sleeveDeletionPanel(wrapper)!;
    expect(deletePanel.attributes('aria-labelledby')).toBe(deletePanel.get('h3').attributes('id'));
    await setSleeveSelectValue(wrapper, 'Holding reassignment destination', 'Other');
    await setSleeveSelectValue(wrapper, 'Move child “Direct indexing” under', 'Other');
    await setSleeveSelectValue(wrapper, 'Move child “Transition destination” under', 'Other');
    const confirmDelete = wrapper
      .findAll('button')
      .find((button) => button.text() === 'Confirm delete');
    expect(confirmDelete).toBeDefined();
    await confirmDelete!.trigger('click');

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

  it('adds unique new sleeves without coercing blank target and drift strings', async () => {
    const draft = reactive(createEmptyPolicyDraft());
    draft.sleeves = [sleeve('sleeve-new-1')];
    const wrapper = mount(PolicySleevesEditor, {
      props: {
        draft,
        positions: null,
        targetIssues: [],
        sourceRevisionId: null,
        'onUpdate:sleeves': (next: EditableSleeve[]) => {
          draft.sleeves = next;
        },
      },
    });

    const addButton = wrapper.findAll('button').find((button) => button.text() === 'Add sleeve');
    expect(addButton).toBeDefined();
    await addButton!.trigger('click');

    expect(draft.sleeves.map((item) => item.sleeve_key)).toEqual(['sleeve-new-1', 'sleeve-new-2']);
    expect(draft.sleeves[1]).toMatchObject({
      target_pct: '',
      drift_band_pp: '',
      parent_sleeve_key: null,
      enabled: true,
    });
    expect(typeof draft.sleeves[1]?.target_pct).toBe('string');
    expect(typeof draft.sleeves[1]?.drift_band_pp).toBe('string');
  });

  it('requires an explicit holdings destination when disabling and clears reassignment on reenable', async () => {
    const draft = reactive(createEmptyPolicyDraft());
    draft.sleeves = [
      sleeve('us', { display_name: 'US equities' }),
      sleeve('other', { display_name: 'Other' }),
    ];
    draft.reassignments = { us: 'stale' };
    draft.reassignmentHoldings = { us: ['OLD'] };
    const wrapper = mount(PolicySleevesEditor, {
      props: {
        draft,
        positions: [position('AAPL', 'us'), position('BND', null, 'us')],
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

    await setSleeveCheckboxValue(wrapper, 'Enabled US equities', false);
    expect(draft.sleeves.find((item) => item.sleeve_key === 'us')?.enabled).toBe(false);
    await setSleeveSelectValue(wrapper, 'Reassign holdings from US equities', 'Other');
    expect(draft.reassignments).toEqual({ us: 'other' });
    expect(draft.reassignmentHoldings).toEqual({ us: ['AAPL', 'BND'] });

    await setSleeveCheckboxValue(wrapper, 'Disabled US equities', true);
    expect(draft.sleeves.find((item) => item.sleeve_key === 'us')?.enabled).toBe(true);
    expect(draft.reassignments).toEqual({});
    expect(draft.reassignmentHoldings).toEqual({});
  });

  it('cancels two-step deletion and resets pending child choices on source revision changes', async () => {
    const draft = reactive(createEmptyPolicyDraft());
    draft.sleeves = [
      sleeve('parent', { display_name: 'Parent' }),
      sleeve('child', { display_name: 'Child', parent_sleeve_key: 'parent' }),
      sleeve('other', { display_name: 'Other' }),
    ];
    const wrapper = mount(PolicySleevesEditor, {
      props: {
        draft,
        positions: null,
        targetIssues: [],
        sourceRevisionId: 'revision-1',
        'onUpdate:sleeves': (next: EditableSleeve[]) => {
          draft.sleeves = next;
        },
      },
    });

    await wrapper.get('button[aria-label="Delete Parent"]').trigger('click');
    await setSleeveSelectValue(wrapper, 'Move child “Child” under', 'Other');
    const cancelButton = wrapper.findAll('button').find((button) => button.text() === 'Cancel');
    expect(cancelButton).toBeDefined();
    await cancelButton!.trigger('click');
    expect(sleeveDeletionPanel(wrapper) !== undefined).toBe(false);
    expect(draft.sleeves.map((item) => item.sleeve_key)).toEqual(['parent', 'child', 'other']);

    await wrapper.get('button[aria-label="Delete Parent"]').trigger('click');
    await setSleeveSelectValue(wrapper, 'Move child “Child” under', 'Other');
    await wrapper.setProps({ sourceRevisionId: 'revision-2' });
    expect(sleeveDeletionPanel(wrapper) !== undefined).toBe(false);
    expect(draft.sleeves.map((item) => item.sleeve_key)).toEqual(['parent', 'child', 'other']);
  });

  it('displays a top-level child reparent selection before deletion is confirmed', async () => {
    const draft = reactive(createEmptyPolicyDraft());
    draft.sleeves = [
      sleeve('parent', { display_name: 'Parent' }),
      sleeve('child', { display_name: 'Child', parent_sleeve_key: 'parent' }),
    ];
    const wrapper = mount(PolicySleevesEditor, {
      props: {
        draft,
        positions: null,
        targetIssues: [],
        sourceRevisionId: 'revision-1',
        'onUpdate:sleeves': (next: EditableSleeve[]) => {
          draft.sleeves = next;
        },
      },
    });

    await wrapper.get('button[aria-label="Delete Parent"]').trigger('click');
    const childParentLabel = 'Move child “Child” under';
    await setSleeveSelectValue(wrapper, childParentLabel, 'Top level');

    const { triggerId } = sleeveSelect(wrapper, childParentLabel);
    const childParentTrigger = wrapper.get(`[data-slot="select-trigger"][id="${triggerId}"]`);
    expect(childParentTrigger.text()).toContain('Top level');
    expect(draft.sleeves.find((item) => item.sleeve_key === 'child')?.parent_sleeve_key).toBe(
      'parent',
    );

    const confirmButton = wrapper
      .findAll('button')
      .find((button) => button.text() === 'Confirm delete');
    expect(confirmButton).toBeDefined();
    await confirmButton!.trigger('click');
    expect(draft.sleeves.find((item) => item.sleeve_key === 'parent')).toBeUndefined();
    expect(draft.sleeves.find((item) => item.sleeve_key === 'child')?.parent_sleeve_key).toBeNull();
    wrapper.unmount();
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
    const table = expectReplacementTable(
      wrapper,
      'Configured ETF replacement candidates and policy settings',
    );
    const enabledToggle = wrapper.findAllComponents(Checkbox)[0]!;
    expect(enabledToggle.props('modelValue')).toBe(true);
    expect(table.querySelectorAll('tbody tr')).toHaveLength(2);

    await wrapper.find('button[aria-label="Move VTI down"]').trigger('click');
    expect(draft.allowedSecurities.map((item) => [item.ticker, item.priority])).toEqual([
      ['ITOT', 0],
      ['VTI', 1],
    ]);

    await replacementInput(wrapper, 'Exposure suitability note').setValue('Total-market ETF');
    expect(draft.allowedSecurities[0]?.exposure_suitability).toBe('Total-market ETF');
    const itotRow = wrapper
      .findAll('tbody tr')
      .find((row) => row.find('button[aria-label="Remove ITOT"]').exists());
    if (!itotRow) throw new Error('Replacement row not found: ITOT');
    itotRow.findComponent(Checkbox).vm.$emit('update:modelValue', false);
    await nextTick();
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
      { ticker: 'GONE', sleeve_key: 'deleted', sub_sleeve_key: null },
    ];
    const wrapper = mount(PolicyHoldingOverridesEditor, {
      props: {
        draft,
        positions: [position('AAPL', 'us', 'direct'), position('AAPL', 'us', 'direct')],
        portfolioAvailable: true,
        portfolioLoading: false,
        'onUpdate:overrides': (next) => {
          draft.overrides = next;
        },
      },
    });
    const table = expectOverrideTable(
      wrapper,
      'Current API sleeve resolutions and explicit overrides by ticker',
    );
    expect(
      [...table.querySelectorAll('tbody th[scope="row"]')].map((cell) => cell.textContent?.trim()),
    ).toEqual(['AAPL', 'OLD', 'GONE']);
    expect(table.querySelectorAll('tbody tr')).toHaveLength(3);
    expect(table.querySelector('tbody tr:first-child td')?.textContent).toContain('us → direct');

    await openOverrideSelect(wrapper, 'OLD');
    const disabledAssignment = wrapper
      .findAllComponents(SelectItem)
      .find((item) => item.text().includes('Current assignment — disabled'));
    expect(disabledAssignment).toBeDefined();
    expect(disabledAssignment!.props('disabled')).toBe(true);
    await setOverrideSelectValue(wrapper, 'OLD', 'disabled');
    expect(draft.overrides[1]).toEqual({
      ticker: 'OLD',
      sleeve_key: 'disabled',
      sub_sleeve_key: null,
    });
    await setOverrideSelectValue(wrapper, 'OLD', 'other');
    expect(draft.overrides[1]).toEqual({
      ticker: 'OLD',
      sleeve_key: 'other',
      sub_sleeve_key: null,
    });

    await openOverrideSelect(wrapper, 'GONE');
    const missingAssignment = wrapper
      .findAllComponents(SelectItem)
      .find((item) => item.text().includes('Current assignment — missing target'));
    expect(missingAssignment).toBeDefined();
    expect(missingAssignment!.props('disabled')).toBe(true);
    await setOverrideSelectValue(wrapper, 'GONE', 'deleted');
    expect(draft.overrides[2]).toEqual({
      ticker: 'GONE',
      sleeve_key: 'deleted',
      sub_sleeve_key: null,
    });

    await openOverrideSelect(wrapper, 'AAPL');
    const defaultOption = findOverrideOption(wrapper, 'Use default resolution');
    expect(defaultOption).toBeDefined();
    const defaultValue = defaultOption!.props('value') as string;
    await setOverrideSelectValue(wrapper, 'AAPL', 'other');
    expect(draft.overrides[0]).toEqual({
      ticker: 'AAPL',
      sleeve_key: 'other',
      sub_sleeve_key: null,
    });
    await setOverrideSelectValue(wrapper, 'AAPL', 'direct');
    expect(draft.overrides[0]).toEqual({
      ticker: 'AAPL',
      sleeve_key: 'us',
      sub_sleeve_key: 'direct',
    });
    await setOverrideSelectValue(wrapper, 'AAPL', defaultValue);
    expect(draft.overrides.map((item) => item.ticker)).toEqual(['OLD', 'GONE']);
    expect(wrapper.text()).toContain('OLD');
    expect(wrapper.text()).toContain('GONE');
    wrapper.unmount();
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
    await sleeveWrapper.find('input[aria-label="Target percent for us"]').setValue('0.00000001');
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

    await replacementInput(replacementWrapper, 'Exposure suitability note').setValue('After edit');
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
    await setOverrideSelectValue(overrideWrapper, 'AAPL', 'other');
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

  it('resets form selections on same and new draft updates with unique row and instance labels', async () => {
    const draft = reactive(createEmptyPolicyDraft());
    draft.sleeves = [sleeve('us'), sleeve('direct', { parent_sleeve_key: 'us' }), sleeve('other')];
    draft.overrides = [{ ticker: 'AAPL', sleeve_key: 'us', sub_sleeve_key: null }];
    const wrapper = mount(PolicyHoldingOverridesEditor, {
      props: {
        draft,
        positions: [position('AAPL', 'us')],
        portfolioAvailable: true,
        portfolioLoading: false,
        'onUpdate:overrides': (next) => {
          draft.overrides = next;
        },
      },
    });
    const initialControl = overrideSelect(wrapper, 'AAPL');
    expect(initialControl.props('modelValue')).toBe('us');

    await setOverrideSelectValue(wrapper, 'AAPL', 'other');
    expect(draft.overrides[0]?.sleeve_key).toBe('other');
    expect(overrideSelect(wrapper, 'AAPL').props('modelValue')).toBe('other');
    draft.overrides = [{ ticker: 'AAPL', sleeve_key: 'direct', sub_sleeve_key: null }];
    await nextTick();
    expect(overrideSelect(wrapper, 'AAPL').props('modelValue')).toBe('direct');

    const replacementDraft = reactive(createEmptyPolicyDraft());
    replacementDraft.sleeves = [sleeve('us'), sleeve('other')];
    replacementDraft.overrides = [{ ticker: 'MSFT', sleeve_key: 'other', sub_sleeve_key: null }];
    await wrapper.setProps({ draft: replacementDraft, positions: [position('MSFT', 'us')] });
    expect(overrideSelect(wrapper, 'MSFT').props('modelValue')).toBe('other');
    const table = expectOverrideTable(
      wrapper,
      'Current API sleeve resolutions and explicit overrides by ticker',
    );
    expect(
      [...table.querySelectorAll('tbody th[scope="row"]')].map((cell) => cell.textContent?.trim()),
    ).toEqual(['MSFT']);

    const siblingDraft = reactive(createEmptyPolicyDraft());
    siblingDraft.sleeves = [sleeve('us'), sleeve('other')];
    siblingDraft.overrides = [{ ticker: 'GOOG', sleeve_key: 'us', sub_sleeve_key: null }];
    const siblings = mount({
      components: { PolicyHoldingOverridesEditor },
      setup: () => ({
        firstDraft: replacementDraft,
        secondDraft: siblingDraft,
        firstPositions: [position('MSFT', 'us')],
        secondPositions: [position('GOOG', 'us')],
      }),
      template: `
        <div>
          <PolicyHoldingOverridesEditor
            :draft="firstDraft"
            :positions="firstPositions"
            :portfolio-available="true"
            :portfolio-loading="false"
          />
          <PolicyHoldingOverridesEditor
            :draft="secondDraft"
            :positions="secondPositions"
            :portfolio-available="true"
            :portfolio-loading="false"
          />
        </div>
      `,
    });
    const controls = siblings.findAll('button[data-slot="select-trigger"]');
    expect(controls).toHaveLength(2);
    expect(new Set(controls.map((control) => control.attributes('id'))).size).toBe(2);
    const labelIds = controls.map((control) => control.attributes('aria-labelledby'));
    expect(new Set(labelIds).size).toBe(2);
    expect(
      labelIds.map((labelId) =>
        siblings.element.querySelector(`[id="${labelId}"]`)?.textContent?.trim(),
      ),
    ).toEqual(['Explicit override for MSFT', 'Explicit override for GOOG']);
    wrapper.unmount();
    siblings.unmount();
  });
  it('renders holding feedback with shadcn alerts and accessible roles', async () => {
    const loading = mount(PolicyHoldingOverridesEditor, {
      props: {
        draft: createEmptyPolicyDraft(),
        positions: null,
        portfolioAvailable: false,
        portfolioLoading: true,
      },
    });
    const loadingBanner = loading.get('[data-slot="alert"]');
    expect(loadingBanner.attributes('role')).toBe('status');
    expect(loadingBanner.text()).toContain('Loading the current single-account holding list');

    const unavailableDraft = reactive(createEmptyPolicyDraft());
    unavailableDraft.sleeves = [sleeve('us'), sleeve('other')];
    unavailableDraft.overrides = [{ ticker: 'SAVED', sleeve_key: 'us', sub_sleeve_key: null }];
    const unavailable = mount(PolicyHoldingOverridesEditor, {
      props: {
        draft: unavailableDraft,
        positions: null,
        portfolioAvailable: false,
        portfolioLoading: false,
      },
    });
    expect(unavailable.get('[data-slot="alert"]').text()).toContain(
      'Current holdings are unavailable. Existing saved overrides remain editable below; no holdings are guessed.',
    );
    const unavailableTable = expectOverrideTable(
      unavailable,
      'Current API sleeve resolutions and explicit overrides by ticker',
    );
    expect(
      [...unavailableTable.querySelectorAll('tbody th[scope="row"]')].map((cell) =>
        cell.textContent?.trim(),
      ),
    ).toEqual(['SAVED']);
    expect(unavailable.find('button[data-slot="select-trigger"]').exists()).toBe(true);

    const empty = mount(PolicyHoldingOverridesEditor, {
      props: {
        draft: createEmptyPolicyDraft(),
        positions: [],
        portfolioAvailable: true,
        portfolioLoading: false,
      },
    });
    const emptyTable = expectOverrideTable(
      empty,
      'Current API sleeve resolutions and explicit overrides by ticker',
    );
    expect(emptyTable.querySelector('[data-slot="empty-title"]')?.textContent).toBe(
      'No current holdings or explicit overrides',
    );
    expect(emptyTable.querySelectorAll('tbody th[scope="row"]')).toHaveLength(0);
    loading.unmount();
    unavailable.unmount();
    empty.unmount();
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
    const validationAlert = validation.get('[role="status"]');
    expect(validationAlert.attributes('aria-live')).toBe('polite');
    expect(validationAlert.text()).toContain('Enabled targets must sum exactly 100%');
    expect(validationAlert.text()).toContain(
      'These client-side checks are guidance only; the backend response is authoritative.',
    );

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
    await setSleeveCheckboxValue(editor, 'Enabled parent', false);
    const alert = editor.get('[role="alert"]');
    expect(alert.text()).toBe(
      'Disable or reparent enabled child sleeves before disabling this parent.',
    );
  });
});

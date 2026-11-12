// @vitest-environment jsdom
import { mount } from '@vue/test-utils';
import { nextTick, reactive } from 'vue';
import { describe, expect, it } from 'vitest';
import { Input } from '@/components/ui/input';
import { Select, SelectItem } from '@/components/ui/select';
import PolicyReplacementSetsEditor from './PolicyReplacementSetsEditor.vue';
import { createEmptyPolicyDraft } from '@/pages/policy-form';
import type { EditableSleeve } from '@/pages/policy-form';
import type { AllowedSecurityInput } from '@/types/api';

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

function candidate(
  ticker: string,
  sleeve_key: string,
  replacement_set_id: string,
  priority?: number,
  extra: Partial<AllowedSecurityInput> = {},
): AllowedSecurityInput {
  return {
    ticker,
    sleeve_key,
    sub_sleeve_key: null,
    replacement_set_id,
    ...(priority === undefined ? {} : { priority }),
    enabled: true,
    exposure_suitability: null,
    ...extra,
  };
}

function mountEditor(
  draft = reactive(createEmptyPolicyDraft()),
  onUpdate: (securities: AllowedSecurityInput[]) => void = (securities) => {
    draft.allowedSecurities = securities;
  },
) {
  return mount(PolicyReplacementSetsEditor, {
    props: {
      draft,
      'onUpdate:allowed-securities': onUpdate,
    },
  });
}

function labeledInput(wrapper: ReturnType<typeof mount>, labelText: string) {
  const label = wrapper
    .findAll('label')
    .find((item) => item.text().replace(/\s+/g, ' ').trim() === labelText);
  if (!label) throw new Error(`Input label not found: ${labelText}`);
  const id = label.attributes('for');
  if (!id) throw new Error(`Input label is not associated: ${labelText}`);
  return wrapper.get(`[id="${id}"]`);
}

function selectOption(wrapper: ReturnType<typeof mount>, label: string): string {
  const option = wrapper
    .findAllComponents(SelectItem)
    .find((item) => item.text().replace(/\s+/g, ' ').trim() === label);
  if (!option) throw new Error(`Select option not found: ${label}`);
  return option.props('value') as string;
}

async function openSelect(wrapper: ReturnType<typeof mount>, selectIndex: number) {
  const select = wrapper.findAllComponents(Select)[selectIndex];
  if (!select) throw new Error(`Select not found at index ${selectIndex}`);
  await select.get('[data-slot="select-trigger"]').trigger('click');
  await nextTick();
  return select;
}

async function chooseSelectOption(
  wrapper: ReturnType<typeof mount>,
  selectIndex: number,
  label: string,
): Promise<void> {
  const select = await openSelect(wrapper, selectIndex);
  select.vm.$emit('update:modelValue', selectOption(wrapper, label));
  await nextTick();
}

describe('PolicyReplacementSetsEditor', () => {
  it('adds and removes whole candidates with complete default values', async () => {
    const draft = reactive(createEmptyPolicyDraft());
    const wrapper = mountEditor(draft);

    await wrapper.get('button[id$="-add-candidate"]').trigger('click');
    await nextTick();

    expect(draft.allowedSecurities).toEqual([
      {
        ticker: '',
        sleeve_key: '',
        sub_sleeve_key: null,
        replacement_set_id: '',
        priority: 0,
        enabled: true,
        exposure_suitability: null,
      },
    ]);

    expect(labeledInput(wrapper, 'Candidate priority').attributes('aria-invalid')).not.toBe('true');

    await wrapper.get('button[aria-label="Remove ETF candidate"]').trigger('click');
    await nextTick();
    expect(draft.allowedSecurities).toEqual([]);
  });

  it('moves same-sleeve/set siblings and swaps priorities immutably', async () => {
    const draft = reactive(createEmptyPolicyDraft());
    draft.allowedSecurities = [
      candidate('A', 'us', 'same', undefined, { exposure_suitability: null }),
      candidate('X', 'us', 'different-set', 11),
      candidate('B', 'us', 'same', 7),
      candidate('C', 'international', 'same', 13),
      candidate('D', 'us', 'same', 19),
    ];
    const wrapper = mountEditor(draft);
    const before = draft.allowedSecurities;

    expect(wrapper.get('button[aria-label="Move X up"]').attributes('disabled')).toBeDefined();
    expect(wrapper.get('button[aria-label="Move X down"]').attributes('disabled')).toBeDefined();
    expect(wrapper.get('button[aria-label="Move C up"]').attributes('disabled')).toBeDefined();
    expect(wrapper.get('button[aria-label="Move B up"]').attributes('disabled')).toBeUndefined();

    await wrapper.get('button[aria-label="Move B up"]').trigger('click');
    await nextTick();

    expect(draft.allowedSecurities).not.toBe(before);
    expect(draft.allowedSecurities.map((item) => item.ticker)).toEqual(['B', 'X', 'A', 'C', 'D']);
    expect(draft.allowedSecurities.map((item) => item.priority)).toEqual([0, 11, 7, 13, 19]);
    expect(draft.allowedSecurities[2]?.exposure_suitability).toBeNull();
  });

  it('repairs saved disabled or missing sleeves without clearing sub-sleeves', async () => {
    const draft = reactive(createEmptyPolicyDraft());
    draft.sleeves = [
      sleeve('us', { display_name: 'US equities' }),
      sleeve('child', { display_name: 'US small cap', parent_sleeve_key: 'us' }),
      sleeve('disabled', { display_name: 'Legacy parent', enabled: false }),
      sleeve('legacy-child', {
        display_name: 'Legacy child',
        parent_sleeve_key: 'disabled',
        enabled: false,
      }),
    ];
    draft.allowedSecurities = [
      candidate('OLD', 'disabled', 'legacy', 0, { sub_sleeve_key: 'legacy-child' }),
    ];
    const wrapper = mountEditor(draft);

    await openSelect(wrapper, 0);
    expect(wrapper.findAllComponents(SelectItem).map((item) => item.text())).toContain(
      'Current parent sleeve — disabled (Legacy parent)',
    );
    await openSelect(wrapper, 1);
    expect(wrapper.findAllComponents(SelectItem).map((item) => item.text())).toContain(
      'Current sub-sleeve — disabled (Legacy child)',
    );
    await chooseSelectOption(wrapper, 0, 'US equities');
    await nextTick();

    expect(draft.allowedSecurities[0]?.sleeve_key).toBe('us');
    expect(draft.allowedSecurities[0]?.sub_sleeve_key).toBe('legacy-child');
    await openSelect(wrapper, 0);
    expect(wrapper.findAllComponents(SelectItem).map((item) => item.text())).not.toContain(
      'Current parent sleeve — disabled (Legacy parent)',
    );
    await openSelect(wrapper, 1);

    expect(wrapper.findAllComponents(SelectItem).map((item) => item.text())).toContain(
      'Current sub-sleeve — disabled (Legacy child)',
    );
    await chooseSelectOption(wrapper, 1, 'US small cap');
    expect(draft.allowedSecurities[0]?.sleeve_key).toBe('us');
    expect(draft.allowedSecurities[0]?.sub_sleeve_key).toBe('child');
    await openSelect(wrapper, 1);
    expect(wrapper.findAllComponents(SelectItem).map((item) => item.text())).toContain(
      'US small cap',
    );
    expect(wrapper.findAllComponents(SelectItem).map((item) => item.text())).not.toContain(
      'Current sub-sleeve — disabled (Legacy child)',
    );
  });

  it('preserves null and empty notes while resyncing external edits without echo', async () => {
    const draft = reactive(createEmptyPolicyDraft());
    draft.allowedSecurities = [
      candidate('NULL', 'us', 'core', 0, { exposure_suitability: null }),
      candidate('EMPTY', 'us', 'core', 1, { exposure_suitability: '' }),
    ];
    const emissions: AllowedSecurityInput[][] = [];
    const wrapper = mountEditor(draft, (securities) => {
      emissions.push(securities);
      draft.allowedSecurities = securities;
    });

    await labeledInput(wrapper, 'ETF ticker').setValue('NULL2');
    await nextTick();
    expect(draft.allowedSecurities.map((item) => item.exposure_suitability)).toEqual([null, '']);
    expect(emissions).toHaveLength(1);

    draft.allowedSecurities = [
      candidate('EXTERNAL', 'us', 'external', 3, {
        sub_sleeve_key: 'child',
        exposure_suitability: '',
      }),
    ];
    await nextTick();

    expect(wrapper.findAllComponents(Input).map((input) => input.props('modelValue'))).toEqual([
      'EXTERNAL',
      'external',
      3,
      '',
    ]);
    expect(emissions).toHaveLength(1);
    expect(draft.allowedSecurities[0]?.sub_sleeve_key).toBe('child');
  });

  it('keeps blank priority invalid and associates the validation error', async () => {
    const draft = reactive(createEmptyPolicyDraft());
    draft.allowedSecurities = [candidate('VTI', 'us', 'core', 0)];
    const wrapper = mountEditor(draft);

    const priority = labeledInput(wrapper, 'Candidate priority');
    await priority.setValue('');
    await nextTick();

    expect(priority.attributes('aria-invalid')).toBe('true');
    const errorId = priority.attributes('aria-describedby');
    expect(errorId).toBeTruthy();
    expect(wrapper.get(`[id="${errorId}"]`).text()).toContain(
      'Invalid input: expected number, received NaN',
    );
    expect(Number.isNaN(draft.allowedSecurities[0]?.priority)).toBe(true);
  });

  it('updates the enabled value through the checkbox control', async () => {
    const draft = reactive(createEmptyPolicyDraft());
    draft.allowedSecurities = [candidate('VTI', 'us', 'core', 0)];
    const wrapper = mountEditor(draft);

    await wrapper.get('[role="checkbox"]').trigger('click');
    await nextTick();
    expect(draft.allowedSecurities[0]?.enabled).toBe(false);
  });

  it('uses per-instance IDs and keeps saved missing parent values visible for repair', async () => {
    const firstDraft = reactive(createEmptyPolicyDraft());
    const secondDraft = reactive(createEmptyPolicyDraft());
    firstDraft.allowedSecurities = [candidate('ONE', 'missing-one', 'set', 0)];
    secondDraft.allowedSecurities = [candidate('TWO', 'missing-two', 'set', 0)];
    const wrapper = mount({
      components: { PolicyReplacementSetsEditor },
      setup: () => ({ firstDraft, secondDraft }),
      template: `
        <div>
          <PolicyReplacementSetsEditor :draft="firstDraft" />
          <PolicyReplacementSetsEditor :draft="secondDraft" />
        </div>
      `,
    });

    const triggers = wrapper.findAll('button[data-slot="select-trigger"]');
    expect(triggers).toHaveLength(4);
    const ids = triggers.map((trigger) => trigger.attributes('id'));
    expect(ids.every(Boolean)).toBe(true);
    expect(new Set(ids).size).toBe(ids.length);
    await openSelect(wrapper, 0);
    expect(selectOption(wrapper, 'Current parent sleeve — missing (missing-one)')).toBeTruthy();
    await openSelect(wrapper, 2);
    expect(selectOption(wrapper, 'Current parent sleeve — missing (missing-two)')).toBeTruthy();
  });
});

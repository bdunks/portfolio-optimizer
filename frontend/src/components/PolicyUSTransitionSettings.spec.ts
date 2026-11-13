// @vitest-environment jsdom
import { mount } from '@vue/test-utils';
import { nextTick, reactive } from 'vue';
import { describe, expect, it, vi } from 'vitest';
import PolicyUSTransitionSettings from './PolicyUSTransitionSettings.vue';
import { Input } from '@/components/ui/input';
import { Select, SelectItem } from '@/components/ui/select';
import { SheetContent } from '@/components/ui/sheet';
import { createEmptyPolicyDraft, type EditableSleeve } from '@/pages/policy-form';

function sleeve(key: string, target: string, parent: string | null = null): EditableSleeve {
  return {
    sleeve_key: key,
    display_name: key,
    sort_order: 0,
    parent_sleeve_key: parent,
    target_pct: target,
    drift_band_pp: '0',
    is_direct_index_container: false,
    is_direct_index_sleeve: false,
    is_transition_destination: false,
    is_cash_sleeve: false,
    enabled: true,
  };
}

function roleSleeves(): EditableSleeve[] {
  return [
    { ...sleeve('us-equities', '80'), display_name: 'US equities' },
    { ...sleeve('legacy', '40.00', 'us-equities'), display_name: 'Legacy holdings' },
    { ...sleeve('new', '60.00', 'us-equities'), display_name: 'New holdings' },
    { ...sleeve('cash', '20'), display_name: 'Cash', is_cash_sleeve: true },
  ];
}

function findButton(text: string): HTMLButtonElement {
  const button = Array.from(document.body.querySelectorAll<HTMLButtonElement>('button')).find(
    (candidate) => candidate.textContent?.replace(/\s+/g, ' ').trim() === text,
  );
  if (!button) throw new Error(`Button not found: ${text}`);
  return button;
}

function targetInput(): HTMLInputElement | null {
  return document.body.querySelector<HTMLInputElement>('input[id$="-target"]');
}

describe('PolicyUSTransitionSettings', () => {
  it('does not infer roles or mutate the draft on cancelled setup', async () => {
    const draft = reactive(createEmptyPolicyDraft());
    draft.sleeves = roleSleeves();
    const originalSleeves = draft.sleeves;
    const wrapper = mount(PolicyUSTransitionSettings, {
      attachTo: document.body,
      props: {
        draft,
        'onUpdate:sleeves': (next: EditableSleeve[]) => {
          draft.sleeves = next;
        },
      },
    });

    expect(wrapper.text()).toContain('Set up US transition');
    expect(draft.sleeves.every((item) => !item.is_direct_index_container)).toBe(true);
    expect(draft.sleeves.every((item) => !item.is_direct_index_sleeve)).toBe(true);
    expect(draft.sleeves.every((item) => !item.is_transition_destination)).toBe(true);

    const triggerWrapper = wrapper.get('button[data-transition-settings-trigger]');
    const trigger = triggerWrapper.element as HTMLButtonElement;
    await triggerWrapper.trigger('click');
    await nextTick();
    const selects = wrapper.findAllComponents(Select);
    expect(selects).toHaveLength(3);
    expect(selects.map((select) => select.props('modelValue'))).toEqual(['', '', '']);
    expect(targetInput()?.disabled).toBe(true);
    expect(wrapper.emitted('update:sleeves')).toBeUndefined();

    findButton('Cancel').click();
    await nextTick();
    expect(draft.sleeves).toBe(originalSleeves);
    expect(draft.sleeves.every((item) => !item.is_transition_destination)).toBe(true);
    expect(wrapper.emitted('update:sleeves')).toBeUndefined();

    const otherFocusTarget = document.createElement('button');
    document.body.append(otherFocusTarget);
    otherFocusTarget.focus();
    const sheet = wrapper.findComponent(SheetContent);
    const focusEvent = { preventDefault: vi.fn() };
    sheet.vm.$emit('closeAutoFocus', focusEvent);
    await nextTick();
    expect(focusEvent.preventDefault).toHaveBeenCalledOnce();
    expect(document.activeElement).toBe(trigger);
    otherFocusTarget.remove();
    wrapper.unmount();
  });

  it('applies selected roles and exact targets to the current draft', async () => {
    const draft = reactive(createEmptyPolicyDraft());
    draft.sleeves = roleSleeves();
    draft.settings.cash_reserve_usd = '123.45';
    draft.allowedSecurities = [
      { ticker: 'VTI', sleeve_key: 'us-equities', replacement_set_id: 'core', priority: 1 },
    ];
    draft.overrides = [{ ticker: 'AAPL', sleeve_key: 'us-equities', sub_sleeve_key: 'legacy' }];
    draft.reassignments = { old: 'new' };
    draft.reassignmentHoldings = { old: ['AAPL'] };
    const settings = draft.settings;
    const allowedSecurities = draft.allowedSecurities;
    const overrides = draft.overrides;
    const reassignments = draft.reassignments;
    const reassignmentHoldings = draft.reassignmentHoldings;
    const wrapper = mount(PolicyUSTransitionSettings, {
      attachTo: document.body,
      props: {
        draft,
        'onUpdate:sleeves': (next: EditableSleeve[]) => {
          draft.sleeves = next;
        },
      },
    });

    await wrapper.get('button[data-transition-settings-trigger]').trigger('click');
    const selects = wrapper.findAllComponents(Select);
    selects[0]!.vm.$emit('update:modelValue', 'us-equities');
    await nextTick();
    selects[1]!.vm.$emit('update:modelValue', 'legacy');
    selects[2]!.vm.$emit('update:modelValue', 'new');
    await nextTick();
    expect(document.body.textContent ?? '').toContain('Enter an exact percentage from 0 to 100.');
    expect(targetInput()?.disabled).toBe(false);
    wrapper.findComponent(Input).vm.$emit('update:modelValue', '37.00000000000000000001');
    await nextTick();

    findButton('Apply settings').click();
    await nextTick();
    expect(draft.sleeves.map((item) => item.target_pct)).toEqual([
      '80',
      '62.99999999999999999999',
      '37.00000000000000000001',
      '20',
    ]);
    expect(draft.sleeves.map((item) => item.is_direct_index_container)).toEqual([
      true,
      false,
      false,
      false,
    ]);
    expect(draft.sleeves.map((item) => item.is_direct_index_sleeve)).toEqual([
      false,
      true,
      false,
      false,
    ]);
    expect(draft.sleeves.map((item) => item.is_transition_destination)).toEqual([
      false,
      false,
      true,
      false,
    ]);
    expect(draft.sleeves[3]?.is_cash_sleeve).toBe(true);
    expect(draft.settings).toBe(settings);
    expect(draft.settings.cash_reserve_usd).toBe('123.45');
    expect(draft.allowedSecurities).toBe(allowedSecurities);
    expect(draft.overrides).toBe(overrides);
    expect(draft.reassignments).toBe(reassignments);
    expect(draft.reassignmentHoldings).toBe(reassignmentHoldings);
    expect(wrapper.text()).toContain('Edit settings');
    wrapper.unmount();
  });

  it('shows custom Legacy mappings and exact targets without offering destructive Apply', async () => {
    const draft = reactive(createEmptyPolicyDraft());
    draft.sleeves = [
      { ...sleeve('us', '80'), is_direct_index_container: true },
      { ...sleeve('legacy', '25.00', 'us'), is_direct_index_sleeve: true },
      sleeve('new-group', '75.00', 'us'),
      { ...sleeve('nested-legacy', '12.5', 'new-group'), is_direct_index_sleeve: true },
      { ...sleeve('destination', '42.5', 'new-group'), is_transition_destination: true },
    ];
    const original = draft.sleeves.map((item) => ({ ...item }));
    const wrapper = mount(PolicyUSTransitionSettings, {
      attachTo: document.body,
      props: { draft },
    });

    expect(wrapper.text()).toContain('Guided editing is unavailable');
    expect(wrapper.text()).toContain('target 25.00% within us');
    expect(wrapper.text()).toContain('target 12.5% within new-group');
    await wrapper.get('button[data-transition-settings-trigger]').trigger('click');
    await nextTick();

    expect(wrapper.findAllComponents(Select)).toHaveLength(0);
    expect(document.body.textContent ?? '').not.toContain('Apply settings');
    findButton('Close').click();
    await nextTick();
    expect(draft.sleeves).toEqual(original);
    expect(wrapper.emitted('update:sleeves')).toBeUndefined();
    wrapper.unmount();
  });

  it('offers only direct enabled children for new Legacy selections', async () => {
    const draft = reactive(createEmptyPolicyDraft());
    draft.sleeves = [
      sleeve('us', '100'),
      sleeve('legacy', '50', 'us'),
      sleeve('new-group', '50', 'us'),
      { ...sleeve('disabled-legacy', '0', 'us'), enabled: false },
      sleeve('nested', '50', 'new-group'),
    ];
    const wrapper = mount(PolicyUSTransitionSettings, {
      attachTo: document.body,
      props: { draft },
    });

    await wrapper.get('button[data-transition-settings-trigger]').trigger('click');
    const selects = wrapper.findAllComponents(Select);
    selects[0]!.vm.$emit('update:modelValue', 'us');
    await nextTick();
    await selects[1]!.get('[data-slot="select-trigger"]').trigger('click');
    await nextTick();
    const legacyOptions = selects[1]!.findAllComponents(SelectItem).map((item) => item.text());

    expect(legacyOptions).toContain('legacy');
    expect(legacyOptions).not.toContain('nested');
    expect(legacyOptions).not.toContain('disabled-legacy');
    wrapper.unmount();
  });

  it('preserves nested targets and guides target edits to the allocation editor', async () => {
    const draft = reactive(createEmptyPolicyDraft());
    const us = { ...sleeve('us', '80'), is_direct_index_container: true };
    const legacy = { ...sleeve('legacy', '25.00', 'us'), is_direct_index_sleeve: true };
    const newGroup = sleeve('new-group', '75.00', 'us');
    const destination = {
      ...sleeve('destination', '42.5', 'new-group'),
      is_transition_destination: true,
    };
    draft.sleeves = [us, legacy, newGroup, destination];
    const wrapper = mount(PolicyUSTransitionSettings, {
      attachTo: document.body,
      props: {
        draft,
        'onUpdate:sleeves': (next: EditableSleeve[]) => {
          draft.sleeves = next;
        },
      },
    });

    expect(wrapper.text()).toContain('Edit settings');
    await wrapper.get('button[data-transition-settings-trigger]').trigger('click');
    expect(document.body.textContent ?? '').toContain(
      'edit nested targets in the allocation editor.',
    );
    expect(targetInput()?.disabled).toBe(true);
    findButton('Apply settings').click();
    await nextTick();
    expect(draft.sleeves.map((item) => item.target_pct)).toEqual(['80', '25.00', '75.00', '42.5']);
    wrapper.unmount();
  });
});

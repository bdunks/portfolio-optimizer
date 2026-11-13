// @vitest-environment jsdom
import { mount } from '@vue/test-utils';
import { nextTick, reactive } from 'vue';
import { describe, expect, it, vi } from 'vitest';
import { Select } from '@/components/ui/select';
import { createEmptyPolicySettings, type EditablePolicySettings } from '@/pages/policy-form';
import PolicyTaxBatchSettings from './PolicyTaxBatchSettings.vue';

describe('PolicyTaxBatchSettings form', () => {
  it('preserves financial text and nullable blanks while exposing labelled controls', async () => {
    const settings = reactive(createEmptyPolicySettings());
    const wrapper = mount(PolicyTaxBatchSettings, {
      props: {
        settings,
        sourceRevisionId: null,
        'onUpdate:settings': (next: EditablePolicySettings) => Object.assign(settings, next),
      },
    });

    const inputs = wrapper.findAll('input[data-slot="input"]');
    const selectors = wrapper.findAll('button[role="combobox"]');
    expect(inputs).toHaveLength(30);
    expect(selectors).toHaveLength(4);
    for (const control of [...inputs, ...selectors]) {
      const id = control.attributes('id');
      expect(id).toBeTruthy();
      expect(wrapper.findAll('label').some((label) => label.attributes('for') === id)).toBe(true);
    }

    const label = (labelText: string) =>
      wrapper.findAll('label').find((candidate) => candidate.text().includes(labelText))!;
    const field = (labelText: string) =>
      wrapper.get(`[id="${label(labelText).attributes('for')}"]`);
    await field('Short-term marginal tax rate').setValue('0.2500000000000000001');
    expect(settings.short_term_tax_rate).toBe('0.2500000000000000001');
    await field('Incremental realized-gain budget').setValue('');
    expect(settings.gain_budget_usd).toBe('');
    await field('YTD source').setValue('');
    expect(settings.ytd_source).toBe('');
    expect(wrapper.text()).toContain('No minimum SELL notional is configured here.');

    await field('Band objective weight').setValue('1.25');
    expect(settings.objective_band_weight).toBe('1.25');
    expect(wrapper.text()).toContain('1 bp = 0.01%');
    wrapper.unmount();
  });

  it('keeps tri-state toggle values as boolean or null without string leakage', () => {
    const settings = reactive(createEmptyPolicySettings());
    const wrapper = mount(PolicyTaxBatchSettings, {
      props: {
        settings,
        sourceRevisionId: null,
        'onUpdate:settings': (next: EditablePolicySettings) => Object.assign(settings, next),
      },
    });
    const selectors = wrapper.findAllComponents(Select);
    expect(selectors).toHaveLength(4);

    selectors[0]!.vm.$emit('update:modelValue', 'disabled');
    expect(settings.prefer_etf_buys).toBe(false);
    expect(typeof settings.prefer_etf_buys).toBe('boolean');
    selectors[0]!.vm.$emit('update:modelValue', 'choose');
    expect(settings.prefer_etf_buys).toBeNull();

    wrapper.unmount();
  });

  it('resets from external draft loads without emitting a feedback update', async () => {
    const settings = reactive(createEmptyPolicySettings());
    const updateSettings = vi.fn((next: EditablePolicySettings) => Object.assign(settings, next));
    const wrapper = mount(PolicyTaxBatchSettings, {
      props: { settings, sourceRevisionId: 'revision-1', 'onUpdate:settings': updateSettings },
    });
    const shortTerm = wrapper.get('input[id$="-short-term-tax-rate"]');
    const preference = wrapper.get('button[id$="-prefer-etf-buys"]');

    settings.short_term_tax_rate = '0.2500000000000000001';
    settings.prefer_etf_buys = false;
    await nextTick();
    expect((shortTerm.element as HTMLInputElement).value).toBe('0.2500000000000000001');
    expect(preference.text()).toContain('Disabled');
    expect(updateSettings).not.toHaveBeenCalled();

    settings.short_term_tax_rate = null;
    settings.prefer_etf_buys = null;
    await nextTick();
    expect((shortTerm.element as HTMLInputElement).value).toBe('');
    expect(preference.text()).toContain('Choose');
    expect(updateSettings).not.toHaveBeenCalled();

    await shortTerm.setValue('0.00');
    expect(updateSettings).toHaveBeenCalledTimes(1);
    expect(settings.short_term_tax_rate).toBe('0.00');
    const stLoss = wrapper.get('input[id$="-st-loss-carryforward"]');
    const stLossError = () => wrapper.find('[id$="-st-loss-carryforward-error"]');
    await stLoss.setValue('not-a-number');
    await stLoss.trigger('blur');
    expect(stLoss.attributes('aria-invalid')).toBe('true');
    expect(stLossError().exists()).toBe(true);

    settings.st_loss_carryforward_usd = '0.00';
    await wrapper.setProps({ sourceRevisionId: 'revision-2' });
    expect((stLoss.element as HTMLInputElement).value).toBe('0.00');
    expect(stLoss.attributes('aria-invalid')).toBeUndefined();
    expect(stLossError().exists()).toBe(false);

    await stLoss.setValue('not-a-number');
    await stLoss.trigger('blur');
    expect(stLossError().exists()).toBe(true);
    await stLoss.setValue('still-invalid');
    expect((stLoss.element as HTMLInputElement).value).toBe('still-invalid');
    expect(stLossError().exists()).toBe(true);

    await wrapper.setProps({ sourceRevisionId: 'revision-3' });
    expect((stLoss.element as HTMLInputElement).value).toBe('still-invalid');
    expect(stLoss.attributes('aria-invalid')).toBeUndefined();
    expect(stLossError().exists()).toBe(false);
    expect(updateSettings).toHaveBeenCalledTimes(4);
    wrapper.unmount();
  });
});

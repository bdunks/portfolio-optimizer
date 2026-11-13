// @vitest-environment jsdom
import { mount } from '@vue/test-utils';
import { nextTick } from 'vue';
import { describe, expect, it } from 'vitest';
import PolicySectorBandsEditor from './PolicySectorBandsEditor.vue';
import type { EditableSectorBand } from '@/pages/policy-form';

describe('PolicySectorBandsEditor', () => {
  it('adds and removes rows and emits exact string edits without normalizing blanks', async () => {
    let updated: EditableSectorBand[] = [];
    const initial: EditableSectorBand[] = [
      { sector_key: 'Technology', target_weight_pct: '33.333333333333333333', band_pct: '0' },
    ];
    const wrapper = mount(PolicySectorBandsEditor, {
      props: {
        sectorBands: initial,
        'onUpdate:sectorBands': (value: EditableSectorBand[]) => {
          updated = value;
        },
      },
    });
    await wrapper.get('input[inputmode="decimal"]').setValue('');
    await nextTick();
    expect(updated[0]?.target_weight_pct).toBe('');
    await wrapper.setProps({ sectorBands: updated });

    await wrapper
      .findAll('button')
      .find((button) => button.text() === 'Add sector band')
      ?.trigger('click');
    await nextTick();
    expect(updated).toHaveLength(2);
    expect(updated[1]).toEqual({ sector_key: '', target_weight_pct: '', band_pct: '' });
    expect(wrapper.findAll('label').map((label) => label.text())).toContain('Sector key');
    await wrapper.setProps({ sectorBands: updated });
    expect(wrapper.get('section').classes()).toContain('tw:space-y-3');
    expect(wrapper.find('.tw\\:sm\\:grid-cols-4').exists()).toBe(true);

    const remove = wrapper
      .findAll('button')
      .find((button) => button.text() === 'Remove sector band');
    await remove?.trigger('click');
    await nextTick();
    expect(updated).toHaveLength(1);
  });
});

// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils';
import { nextTick } from 'vue';
import { describe, expect, it } from 'vitest';
import type { AllocationResponse } from '@/types/api';
import AllocationTargets from './AllocationTargets.vue';

function allocationFixture(): AllocationResponse {
  return {
    current: {
      total_portfolio_usd: '100.00',
      sleeve_weights_pct: { us: '80.0000', bonds: '20.0000' },
    },
    proposed: {
      total_portfolio_usd: '100.00',
      sleeve_weights_pct: { intl: '10.000000', us: '90.000000' },
    },
    target: { sleeve_weights_pct: { bonds: '15.0000', alternatives: '5.000' } },
  };
}

describe('AllocationTargets', () => {
  it('preserves API key order, exact percentage text, labels, and the four-column table', async () => {
    const wrapper = mount(AllocationTargets, {
      props: {
        allocation: allocationFixture(),
        labels: { us: 'U.S. equities', bonds: 'Fixed income' },
      },
    });
    await flushPromises();

    const table = wrapper.get('table');
    expect([...table.findAll('thead th')].map((header) => header.text())).toEqual([
      'Sleeve',
      'Current',
      'Proposed basket',
      'Policy target',
    ]);
    expect(table.findAll('thead th')).toHaveLength(4);
    expect(table.get('caption').text()).toBe(
      'Current, proposed basket, and policy target allocation weights',
    );

    const rows = table.findAll('tbody tr');
    expect(rows).toHaveLength(4);
    expect(rows.map((row) => row.text())).toEqual([
      'U.S. equities80.0000%90.000000%Unavailable',
      'Fixed income20.0000%Unavailable15.0000%',
      'intlUnavailable10.000000%Unavailable',
      'alternativesUnavailableUnavailable5.000%',
    ]);
    expect(wrapper.find('.ts-chart-host').exists()).toBe(true);
    wrapper.unmount();
  });

  it('distinguishes unavailable allocation data from an allocation response without weights', () => {
    const wrapper = mount(AllocationTargets, { props: { allocation: null } });
    expect(wrapper.text()).toContain('Allocation data is unavailable from the portfolio API.');
    expect(wrapper.text()).not.toContain('No allocation weights were returned.');
    wrapper.unmount();

    const empty = mount(AllocationTargets, {
      props: { allocation: { current: null, proposed: null, target: null } },
    });
    expect(empty.text()).toContain('No allocation weights were returned.');
    expect(empty.text()).not.toContain('Allocation data is unavailable from the portfolio API.');
    expect(empty.find('table').exists()).toBe(false);
    expect(empty.find('.ts-chart-host').exists()).toBe(false);
    empty.unmount();
  });

  it('keeps the matching-run warning conditional and updates labels and values reactively', async () => {
    const wrapper = mount(AllocationTargets, {
      props: {
        allocation: allocationFixture(),
        labels: { us: 'U.S. equities' },
        showNoCurrentBasket: true,
      },
    });
    expect(wrapper.find('[role="status"]').text()).toContain(
      'No current proposed basket from a matching optimizer run.',
    );

    await wrapper.setProps({
      allocation: {
        current: { total_portfolio_usd: '100.00', sleeve_weights_pct: { us: '81.00000' } },
        proposed: null,
        target: null,
      },
      labels: { us: 'Updated U.S. label' },
      showNoCurrentBasket: false,
    });
    await flushPromises();
    await nextTick();

    expect(wrapper.find('[role="status"]').exists()).toBe(false);
    expect(wrapper.findAll('tbody tr')).toHaveLength(1);
    expect(wrapper.get('tbody tr').text()).toBe(
      'Updated U.S. label81.00000%UnavailableUnavailable',
    );
    wrapper.unmount();
  });
});

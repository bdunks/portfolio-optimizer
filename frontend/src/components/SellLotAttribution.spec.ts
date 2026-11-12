import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';
import SellLotAttribution from './SellLotAttribution.vue';
import type { RecommendationLegResponse } from '@/types/api';

function sellLeg(
  selectedLots: RecommendationLegResponse['selected_lots'],
  overrides: Partial<RecommendationLegResponse> = {},
): RecommendationLegResponse {
  return {
    leg_id: 'sell-aapl',
    side: 'SELL',
    ticker: 'AAPL',
    shares: '2',
    estimated_unit_price_usd: '20.00',
    estimated_notional_usd: '40.00',
    net_st_realized_usd: '-8.00',
    net_lt_realized_usd: '0.00',
    selected: true,
    group_ids: ['group-a'],
    sequence: 1,
    dependencies: [],
    selected_lots: selectedLots,
    details: {},
    ...overrides,
  };
}

const proposedLot: RecommendationLegResponse['selected_lots'][number] = {
  broker_lot_id: 'BROKER-A1',
  shares: '2',
  acquired_date: '2024-01-15',
  adjusted_basis_usd: '24.0000',
  st_lt: 'ST',
  realized_pl_usd: '-8.0000',
  selected: true,
};

const selectionLabel = 'Select SELL lot BROKER-A1 in group group-a';

describe('SellLotAttribution', () => {
  it('renders the API SELL table and emits exact controlled lot-selection intent', async () => {
    const wrapper = mount(SellLotAttribution, {
      props: { leg: sellLeg([proposedLot]), groupId: 'group-a', canChangeSelection: true },
    });

    expect(wrapper.get('caption').text()).toContain('AAPL');
    const table = wrapper.get('table');
    expect(table.element.querySelectorAll('thead th[scope="col"]')).toHaveLength(8);
    expect(table.element.querySelectorAll('thead th')).toHaveLength(8);
    expect(wrapper.get('[role="region"]').attributes('aria-label')).toBe(
      'SELL broker-lot attribution for leg sell-aapl',
    );
    expect(wrapper.get('[role="region"]').attributes('tabindex')).toBe('0');
    expect(wrapper.text()).toContain('API proposed sale shares');
    expect(wrapper.text()).toContain('not current remaining or available inventory');
    expect(wrapper.text()).toContain('BROKER-A1');
    expect(wrapper.text()).toContain('2024-01-15');
    expect(wrapper.text()).toContain('24.0000 USD');
    expect(wrapper.text()).toContain('20.00 USD');
    expect(wrapper.text()).toContain('2');
    expect(wrapper.text()).toContain('ST');
    expect(wrapper.text()).toContain('-8.0000 USD');
    expect(wrapper.text()).toContain('API selected');
    expect(wrapper.text()).not.toContain('Available shares');

    const selection = wrapper.get(`[role="checkbox"][aria-label="${selectionLabel}"]`);
    expect(selection.attributes('aria-checked')).toBe('true');
    await selection.trigger('click');
    expect(wrapper.emitted('lotSelection')).toEqual([
      [{ groupId: 'group-a', brokerLotId: 'BROKER-A1', selected: false }],
    ]);
    expect(selection.attributes('aria-checked')).toBe('true');

    await wrapper.setProps({ leg: sellLeg([{ ...proposedLot, selected: false }]) });
    const confirmedSelection = wrapper.get(`[role="checkbox"][aria-label="${selectionLabel}"]`);
    expect(confirmedSelection.attributes('aria-checked')).toBe('false');
    expect(wrapper.text()).toContain('Not selected');
    await confirmedSelection.trigger('click');
    expect(wrapper.emitted('lotSelection')?.[1]).toEqual([
      { groupId: 'group-a', brokerLotId: 'BROKER-A1', selected: true },
    ]);
  });

  it('uses unique control IDs and matching labels for repeated broker lots across groups', () => {
    const wrapper = mount({
      components: { SellLotAttribution },
      data: () => ({ leg: sellLeg([proposedLot]) }),
      template: `
        <div>
          <SellLotAttribution
            v-for="groupId in ['group-a', 'group-b']"
            :key="groupId"
            :leg="leg"
            :group-id="groupId"
            :can-change-selection="true"
          />
        </div>
      `,
    });
    const checkboxes = wrapper.findAll('[role="checkbox"]');
    const ids = checkboxes.map((checkbox) => checkbox.attributes('id'));
    expect(checkboxes).toHaveLength(2);
    expect(new Set(ids).size).toBe(2);
    expect(checkboxes.map((checkbox) => checkbox.attributes('aria-label'))).toEqual([
      'Select SELL lot BROKER-A1 in group group-a',
      'Select SELL lot BROKER-A1 in group group-b',
    ]);
    const labels = wrapper.findAll('label[for]');
    for (const id of ids) {
      expect(id).toBeTruthy();
      const matchingLabels = labels.filter((label) => label.attributes('for') === id);
      expect(matchingLabels).toHaveLength(1);
      expect(matchingLabels[0]?.text()).toContain('API selected');
    }
  });

  it('disables changes while pending, read-only, or rejected', async () => {
    for (const props of [{ pending: true }, { canChangeSelection: false }, { rejected: true }]) {
      const wrapper = mount(SellLotAttribution, {
        props: {
          leg: sellLeg([proposedLot]),
          groupId: 'group-a',
          canChangeSelection: true,
          ...props,
        },
      });
      const selection = wrapper.get(`[role="checkbox"][aria-label="${selectionLabel}"]`);
      expect(selection.attributes('aria-disabled')).toBe('true');
      await selection.trigger('click');
      expect(wrapper.emitted('lotSelection')).toBeUndefined();
    }
  });

  it('keeps an explicit empty SELL row and hides the section for BUY legs', () => {
    const empty = mount(SellLotAttribution, {
      props: { leg: sellLeg([]), groupId: 'group-empty', canChangeSelection: false },
    });
    expect(empty.text()).toContain('No broker-lot rows were returned for this SELL leg.');
    expect(empty.get('td').attributes('colspan')).toBe('8');
    expect(empty.text()).toContain('not current remaining or available inventory');

    const buy = mount(SellLotAttribution, {
      props: {
        leg: sellLeg([], { side: 'BUY' }),
        groupId: 'group-buy',
        canChangeSelection: true,
      },
    });
    expect(buy.find('section').exists()).toBe(false);
  });
});

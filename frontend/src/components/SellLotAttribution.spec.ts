import { mount } from '@vue/test-utils';
import { QCheckbox } from 'quasar';
import { findQuasarComponent, setQuasarModelValue } from '@/test-utils/quasar-mount';
import { describe, expect, it } from 'vitest';
import SellLotAttribution from './SellLotAttribution.vue';
import type { RecommendationLegResponse } from '@/types/api';

function sellLeg(
  selectedLots: RecommendationLegResponse['selected_lots'],
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

describe('SellLotAttribution', () => {
  it('labels API-proposed shares separately from inventory and emits exact lot selection intent', async () => {
    const wrapper = mount(SellLotAttribution, {
      props: { leg: sellLeg([proposedLot]), groupId: 'group-a', canChangeSelection: true },
    });

    expect(wrapper.get('caption').text()).toContain('AAPL');
    expect(wrapper.text()).toContain('API proposed sale shares');
    expect(wrapper.text()).toContain('not current remaining or available inventory');
    expect(wrapper.text()).toContain('BROKER-A1');
    expect(wrapper.text()).toContain('24.0000 USD');
    expect(wrapper.text()).toContain('2');
    expect(wrapper.text()).not.toContain('Available shares');

    await setQuasarModelValue(
      wrapper,
      QCheckbox,
      'Select SELL lot BROKER-A1 in group group-a',
      false,
    );
    expect(wrapper.emitted('lotSelection')).toEqual([
      [{ groupId: 'group-a', brokerLotId: 'BROKER-A1', selected: false }],
    ]);
  });

  it('disables edits while pending and presents an explicit empty lot state', () => {
    const pending = mount(SellLotAttribution, {
      props: {
        leg: sellLeg([proposedLot]),
        groupId: 'group-a',
        canChangeSelection: true,
        pending: true,
      },
    });
    expect(
      findQuasarComponent(
        pending,
        QCheckbox,
        'Select SELL lot BROKER-A1 in group group-a',
      ).attributes('aria-disabled'),
    ).toBe('true');
    const empty = mount(SellLotAttribution, {
      props: { leg: sellLeg([]), groupId: 'group-empty', canChangeSelection: false },
    });
    expect(empty.text()).toContain('No broker-lot rows were returned for this SELL leg.');
    expect(empty.text()).toContain('not current remaining or available inventory');
  });
});

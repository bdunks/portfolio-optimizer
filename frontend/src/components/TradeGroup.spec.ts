import { mount } from '@vue/test-utils';
import { QCheckbox } from 'quasar';
import { findQuasarComponent, setQuasarModelValue } from '@/test-utils/quasar-mount';
import { describe, expect, it } from 'vitest';
import TradeGroup from './TradeGroup.vue';
import type { TradeGroupLegReference } from './trade-review-types';
import type { RecommendationGroupResponse, RecommendationLegResponse } from '@/types/api';

function group(overrides: Partial<RecommendationGroupResponse> = {}): RecommendationGroupResponse {
  return {
    group_id: 'group-a',
    rank: 1,
    group_type: 'demo_loss_harvest',
    sleeve_key: 'us',
    rationale: 'API supplied rationale.',
    estimated_benefit_usd: null,
    impact: {
      demo: true,
      wash_status: 'not_validated_demo',
      selected_sell_lots_count: 1,
      sell_proceeds_usd: '20.00',
      realized_st_usd: '-4.00',
      realized_lt_usd: '0.00',
      replacement_buy_shares: '1',
      replacement_buy_cost_usd: '50.00',
      cash_after_usd: '20.00',
      portfolio_effects: {
        allocation: { current: null, proposed: null, target: null },
        us_transition: null,
      },
      risk_tracking_score: null,
    },
    dependencies: [],
    selected: false,
    rejected: false,
    note: null,
    rejection_reason: null,
    leg_ids: ['sell-a'],
    warnings: [],
    ...overrides,
  };
}

const sellLot: RecommendationLegResponse['selected_lots'][number] = {
  broker_lot_id: 'BROKER-A1',
  shares: '1',
  acquired_date: '2024-01-15',
  adjusted_basis_usd: '24.00',
  st_lt: 'ST',
  realized_pl_usd: '-4.00',
  selected: true,
};

const sellLeg: RecommendationLegResponse = {
  leg_id: 'sell-a',
  side: 'SELL',
  ticker: 'AAPL',
  shares: '1',
  estimated_unit_price_usd: '20.00',
  estimated_notional_usd: '20.00',
  net_st_realized_usd: '-4.00',
  net_lt_realized_usd: '0.00',
  selected: true,
  group_ids: ['group-a'],
  sequence: 1,
  dependencies: [],
  selected_lots: [sellLot],
  details: {},
};

const linkedReference: TradeGroupLegReference = {
  legId: 'sell-a',
  label: 'Sequence 1 SELL AAPL',
  status: 'linked',
};

function mountGroup(props: Partial<InstanceType<typeof TradeGroup>['$props']> = {}) {
  return mount(TradeGroup, {
    props: {
      group: group(),
      legs: [sellLeg],
      legReferences: [linkedReference],
      sleeveLabel: 'US Equity',
      hasSellLots: true,
      hasSharedLeg: false,
      noteDraft: '',
      rejectionDraft: '',
      canChangeSelection: true,
      ...props,
    },
  });
}

describe('TradeGroup', () => {
  it('emits group, lot, note, and reject intent without performing page actions', async () => {
    const wrapper = mountGroup();
    expect(
      findQuasarComponent(wrapper, QCheckbox, 'Select recommendation group group-a').exists(),
    ).toBe(true);
    expect(wrapper.get('[aria-label="Notes and rejection for group-a"]')).toBeDefined();

    await setQuasarModelValue(wrapper, QCheckbox, 'Select recommendation group group-a', true);
    expect(wrapper.emitted('groupSelection')).toEqual([[{ groupId: 'group-a', selected: true }]]);

    await wrapper.get('textarea').setValue('Review this proposal');
    expect(wrapper.emitted('noteDraftChange')).toEqual([
      [{ groupId: 'group-a', value: 'Review this proposal' }],
    ]);
    await wrapper.setProps({ noteDraft: 'Review this proposal' });
    const saveNote = wrapper.findAll('button').find((button) => button.text() === 'Save note');
    await saveNote!.trigger('click');
    expect(wrapper.emitted('saveNote')).toEqual([
      [{ groupId: 'group-a', note: 'Review this proposal' }],
    ]);

    const rejection = wrapper.find('input[type="text"]');
    await rejection.setValue('Avoid this trade');
    expect(wrapper.emitted('rejectionDraftChange')).toEqual([
      [{ groupId: 'group-a', value: 'Avoid this trade' }],
    ]);
    await wrapper.setProps({ rejectionDraft: 'Avoid this trade' });
    const reject = wrapper
      .findAll('button')
      .find((button) => button.text().startsWith('Reject group'));
    await reject!.trigger('click');
    expect(wrapper.emitted('rejectGroup')).toEqual([
      [{ groupId: 'group-a', reason: 'Avoid this trade' }],
    ]);

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

  it('disables group review controls while pending and exposes missing references without claims', () => {
    const pending = mountGroup({ pending: true });
    expect(
      findQuasarComponent(pending, QCheckbox, 'Select recommendation group group-a').attributes(
        'aria-disabled',
      ),
    ).toBe('true');
    expect(pending.get('textarea').attributes('disabled')).toBeDefined();
    expect(
      findQuasarComponent(
        pending,
        QCheckbox,
        'Select SELL lot BROKER-A1 in group group-a',
      ).attributes('aria-disabled'),
    ).toBe('true');

    const missing = mountGroup({
      legs: [],
      legReferences: [{ legId: 'missing-leg', label: 'Missing API leg', status: 'missing' }],
    });
    expect(missing.text()).toContain('Missing API leg missing-leg');
    expect(missing.text()).toContain('this reference is not executable');
  });

  it('links shared legs but leaves canonical detail for one shared rendering site', () => {
    const sharedReference: TradeGroupLegReference = {
      legId: 'buy-shared',
      label: 'Sequence 2 BUY VTI',
      status: 'shared',
    };
    const parent = mount({
      components: { TradeGroup },
      data: () => ({
        groupProps: [
          {
            group: group({ group_id: 'group-a', leg_ids: ['buy-shared'] }),
            legs: [],
            legReferences: [sharedReference],
            sleeveLabel: 'US Equity',
            hasSellLots: false,
            hasSharedLeg: true,
            noteDraft: '',
            rejectionDraft: '',
            canChangeSelection: true,
          },
          {
            group: group({ group_id: 'group-b', leg_ids: ['buy-shared'] }),
            legs: [],
            legReferences: [sharedReference],
            sleeveLabel: 'US Equity',
            hasSellLots: false,
            hasSharedLeg: true,
            noteDraft: '',
            rejectionDraft: '',
            canChangeSelection: true,
          },
        ],
      }),
      template: `
        <div>
          <TradeGroup v-for="item in groupProps" :key="item.group.group_id" v-bind="item" />
        </div>
      `,
    });
    expect(parent.findAll('.group-leg-detail')).toHaveLength(0);
    expect(parent.findAll('.leg-card')).toHaveLength(0);
    expect(parent.text().match(/canonical details appear once/g)).toHaveLength(2);
  });

  it('restores a rejected group through a user-intent event', async () => {
    const wrapper = mountGroup({
      group: group({ rejected: true, rejection_reason: 'API saved reason' }),
    });
    const restore = wrapper
      .findAll('button')
      .find((button) => button.text().startsWith('Restore rejected'));
    await restore!.trigger('click');
    expect(wrapper.emitted('restoreGroup')).toEqual([[{ groupId: 'group-a' }]]);
    expect(wrapper.text()).toContain('API saved reason');
  });
});

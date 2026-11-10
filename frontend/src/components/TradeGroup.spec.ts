import { mount } from '@vue/test-utils';
import { QBadge, QCard, QCheckbox, QChip, QExpansionItem } from 'quasar';
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
  it('uses a collapsed Quasar disclosure with an accessible header', () => {
    const wrapper = mountGroup();
    expect(wrapper.findComponent(QExpansionItem).exists()).toBe(true);
    const card = wrapper.findComponent(QCard);
    expect(card.exists()).toBe(true);
    expect(card.classes()).toContain('q-card');
    expect(wrapper.get('.group-body').classes()).toContain('q-px-md');
    const header = wrapper.get('.q-expansion-item .q-item[role="button"]');
    expect(header.attributes('aria-expanded')).toBe('false');
    expect(header.text()).toContain('Priority 1');
    const priorityChip = wrapper.findComponent(QChip);
    expect(priorityChip.text()).toBe('Priority 1');
    expect(priorityChip.props('clickable')).toBe(false);
    expect(priorityChip.attributes('role')).toBeUndefined();
    expect(wrapper.findAllComponents(QBadge)).toHaveLength(0);
  });

  it('shows selected and rejected API states as explicit Quasar status badges', () => {
    const wrapper = mountGroup({ group: group({ selected: true, rejected: true }) });
    const statusBadges = wrapper.findAllComponents(QBadge);

    expect(statusBadges.map((badge) => badge.text())).toEqual([
      'Selected by API',
      'Rejected by user',
    ]);
    expect(statusBadges.map((badge) => badge.attributes('role'))).toEqual(['status', 'status']);
    expect(statusBadges.map((badge) => badge.props('color'))).toEqual(['teal-1', 'red-1']);
  });

  it('emits group, lot, note, and reject intent without performing page actions', async () => {
    const wrapper = mountGroup();
    const groupSelection = findQuasarComponent(
      wrapper,
      QCheckbox,
      'Select recommendation group group-a',
    );
    expect(groupSelection.exists()).toBe(true);
    expect(groupSelection.classes()).toEqual(
      expect.arrayContaining(['text-caption', 'text-weight-bold', 'text-blue-grey-8']),
    );
    expect(wrapper.get('[aria-label="Notes and rejection for group-a"]')).toBeDefined();
    const annotationLabels = wrapper.findAll('.annotation-panel label.column');
    expect(annotationLabels).toHaveLength(2);
    expect(annotationLabels[0]?.classes()).toEqual(
      expect.arrayContaining(['text-caption', 'text-weight-bold', 'text-blue-grey-8']),
    );

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
    expect(parent.findAll('span.shared-note.block')).toHaveLength(2);
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

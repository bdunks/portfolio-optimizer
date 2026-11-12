import { flushPromises, mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';
import TradeGroup from './TradeGroup.vue';
import type { TradeGroupLegReference } from './trade-review-types';
import type { RecommendationGroupResponse, RecommendationLegResponse } from '@/types/api';
import {
  tradeGroupNoteSchema,
  tradeGroupRejectionReasonSchema,
} from '@/forms/trade-group-annotations';

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

async function openGroup(wrapper: ReturnType<typeof mountGroup>): Promise<void> {
  const trigger = wrapper.get('button[aria-label="Recommendation group group-a"]');
  expect(trigger.attributes('aria-expanded')).toBe('false');
  await trigger.trigger('click');
  await flushPromises();
  expect(trigger.attributes('aria-expanded')).toBe('true');
}

describe('TradeGroup', () => {
  it('keeps disclosure collapsed and priority/status noninteractive', async () => {
    const first = mountGroup({ group: group({ selected: true, rejected: true }) });
    const second = mountGroup({ group: group({ group_id: 'group-b' }) });
    const firstTrigger = first.get('button[aria-label="Recommendation group group-a"]');
    const secondTrigger = second.get('button[aria-label="Recommendation group group-b"]');

    expect(firstTrigger.attributes('aria-expanded')).toBe('false');
    expect(secondTrigger.attributes('aria-expanded')).toBe('false');
    expect(first.find('[aria-label="Notes and rejection for group-a"]').exists()).toBe(false);
    expect(first.text()).toContain('Priority 1');
    expect(first.findAll('[role="status"]').map((badge) => badge.text())).toEqual([
      'Selected by API',
      'Rejected by user',
    ]);
    const priorityBadge = first.find('[data-slot="badge"]');
    expect(priorityBadge.text()).toBe('Priority 1');
    expect(priorityBadge.element.tagName).not.toBe('BUTTON');
    expect(priorityBadge.attributes('role')).toBeUndefined();

    await firstTrigger.trigger('click');
    expect(firstTrigger.attributes('aria-expanded')).toBe('true');
    expect(secondTrigger.attributes('aria-expanded')).toBe('false');
  });

  it('renders financial facts and distinct leg-reference statuses', async () => {
    const wrapper = mountGroup({
      group: group({
        dependencies: ['group-prerequisite'],
        warnings: ['API supplied wash-sale warning.'],
      }),
      legs: [],
      hasSharedLeg: true,
      legReferences: [
        linkedReference,
        { legId: 'shared/leg', label: 'Sequence 2 BUY VTI', status: 'shared' },
        { legId: 'unlinked-leg', label: 'Unlinked API leg', status: 'unlinked' },
        { legId: 'missing-leg', label: 'Missing API leg', status: 'missing' },
      ],
    });
    await openGroup(wrapper);

    const facts = wrapper.get('.group-facts');
    expect(facts.text()).toContain('Group IDgroup-a');
    expect(facts.text()).toContain('Priority rank1');
    expect(facts.text()).toContain('Expected benefit Unavailable (not returned by API)');
    expect(facts.text()).toContain('Selected sell-lot count 1');
    expect(facts.text()).toContain('API sell proceeds 20.00 USD');
    expect(facts.text()).toContain('API realized ST / LT -4.00 USD / 0.00 USD');
    expect(facts.text()).toContain('API replacement BUY shares / cost 1 / 50.00 USD');
    expect(facts.text()).toContain('API cash after20.00 USD');
    expect(facts.text()).toContain('Risk / tracking score Unavailable (not returned by API)');
    expect(facts.text()).toContain('Wash statusnot_validated_demo');
    expect(wrapper.text()).toContain('API supplied rationale.');
    expect(wrapper.text()).toContain('Group dependencies (API IDs): group-prerequisite');
    expect(wrapper.text()).toContain('this is not blanket approval');
    expect(wrapper.text()).toContain('API supplied wash-sale warning.');
    expect(wrapper.get('a[href="#/recommendations#leg-sell-a"]').text()).toContain(
      'Sequence 1 SELL AAPL',
    );
    expect(wrapper.get('a[href="#/recommendations#leg-shared%252Fleg"]').text()).toContain(
      'Sequence 2 BUY VTI',
    );
    expect(wrapper.text()).toContain(
      'Shared consolidated leg; canonical details appear once below the groups.',
    );
    expect(wrapper.text()).toContain(
      'API group references are inconsistent; this leg is not executable.',
    );
    expect(wrapper.text()).toContain(
      'Missing API leg missing-leg; this reference is not executable.',
    );
    expect(wrapper.text()).toContain('Replacement BUYs are consolidated canonical legs');
    expect(wrapper.text()).not.toContain('0.00 USD USD');
    expect(wrapper.find('form').exists()).toBe(false);
  });

  it('emits controlled group, lot, raw note, and raw rejection intents only', async () => {
    const wrapper = mountGroup();
    await openGroup(wrapper);

    const groupCheckbox = wrapper.get(
      '[role="checkbox"][aria-label="Select recommendation group group-a"]',
    );
    await groupCheckbox.trigger('click');
    expect(wrapper.emitted('groupSelection')).toEqual([[{ groupId: 'group-a', selected: true }]]);
    expect(groupCheckbox.attributes('aria-checked')).toBe('false');

    const note = wrapper.get('textarea');
    expect(note.attributes('maxlength')).toBe('2000');
    await note.setValue('Review this proposal');
    expect(wrapper.emitted('noteDraftChange')).toEqual([
      [{ groupId: 'group-a', value: 'Review this proposal' }],
    ]);
    await wrapper.setProps({ noteDraft: 'Review this proposal' });
    const saveNote = wrapper.findAll('button').find((button) => button.text() === 'Save note');
    await saveNote!.trigger('click');
    await flushPromises();
    expect(wrapper.emitted('saveNote')).toEqual([
      [{ groupId: 'group-a', note: 'Review this proposal' }],
    ]);

    const rejection = wrapper.get('input[type="text"]');
    expect(rejection.attributes('maxlength')).toBe('500');
    await rejection.setValue('  Avoid this trade  ');
    expect(wrapper.emitted('rejectionDraftChange')).toEqual([
      [{ groupId: 'group-a', value: '  Avoid this trade  ' }],
    ]);
    await wrapper.setProps({ rejectionDraft: '  Avoid this trade  ' });
    const reject = wrapper
      .findAll('button')
      .find((button) => button.text().startsWith('Reject group'));
    await reject!.trigger('click');
    await flushPromises();
    expect(wrapper.emitted('rejectGroup')).toEqual([
      [{ groupId: 'group-a', reason: '  Avoid this trade  ' }],
    ]);
    expect(wrapper.emitted('approveOrder')).toBeUndefined();
    expect(wrapper.find('form').exists()).toBe(false);

    await wrapper
      .get('[role="checkbox"][aria-label="Select SELL lot BROKER-A1 in group group-a"]')
      .trigger('click');
    expect(wrapper.emitted('lotSelection')).toEqual([
      [{ groupId: 'group-a', brokerLotId: 'BROKER-A1', selected: false }],
    ]);
  });

  it('allows empty notes and preserves raw rejection drafts across parent resets', async () => {
    const wrapper = mountGroup({ noteDraft: 'Saved note', rejectionDraft: '' });
    await openGroup(wrapper);
    expect((wrapper.get('textarea').element as HTMLTextAreaElement).value).toBe('Saved note');
    expect((wrapper.get('input[type="text"]').element as HTMLInputElement).value).toBe('');

    await wrapper.get('textarea').setValue('');
    expect(wrapper.emitted('noteDraftChange')?.at(-1)).toEqual([{ groupId: 'group-a', value: '' }]);
    await wrapper.setProps({ noteDraft: '' });
    const saveNote = wrapper.findAll('button').find((button) => button.text() === 'Save note');
    await saveNote!.trigger('click');
    expect(wrapper.emitted('saveNote')?.at(-1)).toEqual([{ groupId: 'group-a', note: '' }]);

    await wrapper.setProps({ rejectionDraft: 'Saved reason' });
    const rejection = wrapper.get('input[type="text"]');
    await rejection.setValue('   ');
    await rejection.trigger('blur');
    expect(wrapper.emitted('rejectionDraftChange')?.at(-1)).toEqual([
      { groupId: 'group-a', value: '   ' },
    ]);
    const reject = wrapper
      .findAll('button')
      .find((button) => button.text().startsWith('Reject group'))!;
    expect((reject.element as HTMLButtonElement).disabled).toBe(false);
    expect(rejection.attributes('aria-invalid')).toBe('true');
    await wrapper.setProps({ rejectionDraft: '   ' });
    expect((wrapper.get('input[type="text"]').element as HTMLInputElement).value).toBe('   ');
    expect(
      (
        wrapper.findAll('button').find((button) => button.text().startsWith('Reject group'))!
          .element as HTMLButtonElement
      ).disabled,
    ).toBe(true);
    await wrapper.setProps({ rejectionDraft: '  replacement reason  ', noteDraft: 'new note' });
    expect((wrapper.get('textarea').element as HTMLTextAreaElement).value).toBe('new note');
    expect((wrapper.get('input[type="text"]').element as HTMLInputElement).value).toBe(
      '  replacement reason  ',
    );
  });

  it('guards pending/read-only controls and preserves rejected-group restore rules', async () => {
    const pending = mountGroup({ pending: true });
    await openGroup(pending);
    expect(
      pending
        .get('[role="checkbox"][aria-label="Select recommendation group group-a"]')
        .attributes('data-disabled'),
    ).toBeDefined();
    expect(pending.get('textarea').attributes('disabled')).toBeDefined();
    expect(pending.get('input[type="text"]').attributes('disabled')).toBeDefined();
    expect(
      (
        pending.findAll('button').find((button) => button.text() === 'Save note')!
          .element as HTMLButtonElement
      ).disabled,
    ).toBe(true);
    expect(
      pending
        .findAll('button')
        .find((button) => button.text().startsWith('Reject group'))!
        .attributes('disabled'),
    ).toBeDefined();
    expect(
      pending
        .get('[role="checkbox"][aria-label="Select SELL lot BROKER-A1 in group group-a"]')
        .attributes('aria-disabled'),
    ).toBe('true');

    const readOnly = mountGroup({ canChangeSelection: false, hasSellLots: false });
    await openGroup(readOnly);
    expect(
      readOnly
        .get('[role="checkbox"][aria-label="Select recommendation group group-a"]')
        .attributes('disabled'),
    ).toBeDefined();

    const noSellLots = mountGroup({ hasSellLots: false });
    await openGroup(noSellLots);
    expect(
      noSellLots
        .get('[role="checkbox"][aria-label="Select recommendation group group-a"]')
        .attributes('disabled'),
    ).toBeDefined();
    const rejected = mountGroup({
      group: group({ rejected: true, rejection_reason: 'API saved reason', selected: false }),
      noteDraft: 'Keep this note',
    });
    await openGroup(rejected);
    expect(rejected.text()).toContain('API saved reason');
    expect(rejected.find('input[type="text"]').exists()).toBe(false);
    expect((rejected.get('textarea').element as HTMLTextAreaElement).value).toBe('Keep this note');
    expect(
      rejected
        .get('[role="checkbox"][aria-label="Select recommendation group group-a"]')
        .attributes('disabled'),
    ).toBeDefined();
    await rejected
      .findAll('button')
      .find((button) => button.text().startsWith('Restore rejected'))!
      .trigger('click');
    expect(rejected.emitted('restoreGroup')).toEqual([[{ groupId: 'group-a' }]]);
    expect(rejected.emitted('groupSelection')).toBeUndefined();
  });

  it('keeps shared canonical details outside the group renderings', async () => {
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
          <article id="leg-buy-shared" class="leg-card">Canonical shared BUY details</article>
        </div>
      `,
    });

    await parent.get('button[aria-label="Recommendation group group-a"]').trigger('click');
    await parent.get('button[aria-label="Recommendation group group-b"]').trigger('click');
    expect(parent.findAll('.group-leg-detail')).toHaveLength(0);
    expect(parent.findAll('.leg-card')).toHaveLength(1);
    expect(parent.text().match(/canonical details appear once/g)).toHaveLength(2);
    expect(parent.findAll('a[href="#/recommendations#leg-buy-shared"]')).toHaveLength(2);
  });

  it('validates annotation limits without normalizing the raw rejection reason', () => {
    expect(tradeGroupNoteSchema.safeParse('').success).toBe(true);
    expect(tradeGroupNoteSchema.safeParse('x'.repeat(2001)).success).toBe(false);
    expect(tradeGroupRejectionReasonSchema.safeParse('   ').success).toBe(false);
    expect(tradeGroupRejectionReasonSchema.safeParse('  reason  ')).toMatchObject({
      success: true,
      data: '  reason  ',
    });
    expect(tradeGroupRejectionReasonSchema.safeParse('x'.repeat(501)).success).toBe(false);
  });
});

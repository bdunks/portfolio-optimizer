import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';

import RunSummary from './RunSummary.vue';
import type {
  FrozenRunDisplayContextResponse,
  OptimizerRecommendationsResponse,
  OptimizerRunResponse,
} from '@/types/api';

const context: FrozenRunDisplayContextResponse = {
  available: true,
  source: 'frozen_input_bundle',
  policy_revision_id: 'historical-policy-r1',
  revision_number: 1,
  created_at: null,
  activated_at: null,
  sleeves: [
    {
      sleeve_key: 'historical-us',
      display_name: 'Historical US sleeve',
      sort_order: 1,
      parent_sleeve_key: null,
      target_pct: '63.0000',
      drift_band_pp: '5.0000',
      enabled: true,
      is_direct_index_container: true,
      is_direct_index_sleeve: false,
      is_transition_destination: false,
      is_cash_sleeve: false,
    },
  ],
  settings: { target_retained_net_loss_usd: '3210.00' },
  allowed_securities: [],
  overrides: [],
  unavailable_reason: null,
};

const savedRun: OptimizerRunResponse = {
  run_id: 'saved-run-1',
  status: 'demo',
  mode: 'recommendations_only',
  policy_revision_id: 'historical-policy-r1',
  source_generation: 4,
  as_of: '2025-01-01T00:00:00Z',
  solver_version: 'DEMO',
  proposed_trade_date: '2025-01-02',
  demo: true,
  actionable: false,
  input_fingerprint: 'historical-fingerprint',
  source_checksum: null,
  batch_settings: { max_sell_lots_per_batch: 2 },
  estimated_realized_st_usd: '-8.00',
  estimated_realized_lt_usd: '0.00',
  estimated_tax_benefit_usd: null,
  estimated_tax_benefit_status: 'tax_profile_incomplete',
  lots_sold_count: 1,
  positions_exited_count: 0,
  orders_count: 1,
  cash_before_usd: null,
  cash_after_usd: '100.00',
  portfolio_effects: null,
  constraints_satisfied: null,
  no_trade_reason: null,
  warnings: [],
  tax_profile_configured: false,
  frozen_display_context: context,
};

const fullRun: OptimizerRecommendationsResponse = {
  ...savedRun,
  groups: [],
  consolidated_legs: [],
};

const unavailableContext: FrozenRunDisplayContextResponse = {
  ...context,
  available: false,
  source: null,
  sleeves: null,
  settings: null,
  allowed_securities: null,
  overrides: null,
  unavailable_reason: 'the saved summary has no frozen policy data',
};

describe('RunSummary', () => {
  it('keeps saved summaries frozen and assigns unique heading IDs to multiple instances', () => {
    const wrapper = mount({
      components: { RunSummary },
      data: () => ({ runs: [savedRun, { ...savedRun, run_id: 'saved-run-2' }] }),
      template: `
        <div>
          <RunSummary v-for="item in runs" :key="item.run_id" mode="saved" :summary="item" />
        </div>
      `,
    });
    const summaryCards = wrapper.findAll('.run-summary');
    expect(
      summaryCards.every(
        (card) => card.attributes('role') === 'region' && card.attributes('data-slot') === 'card',
      ),
    ).toBe(true);
    const headings = wrapper.findAll('.run-summary h2');
    const ids = headings.map((heading) => heading.attributes('id'));
    expect(new Set(ids).size).toBe(2);
    expect(wrapper.text()).toContain('Historical US sleeve');
    expect(wrapper.text()).toContain('historical-policy-r1');
    expect(wrapper.text()).toContain('3210.00');
    expect(wrapper.text()).not.toContain('active-policy-r99');
    expect(wrapper.text()).toContain('DEMO · non-actionable');
    const statusBadges = wrapper.findAll('[data-slot="badge"]');
    expect(statusBadges).toHaveLength(2);
    expect(statusBadges.map((badge) => badge.text())).toEqual([
      'DEMO · non-actionable',
      'DEMO · non-actionable',
    ]);
    expect(statusBadges.every((badge) => badge.attributes('role') === 'status')).toBe(true);
    expect(
      statusBadges.every(
        (badge) =>
          badge.classes().includes('tw:bg-secondary') &&
          badge.classes().includes('tw:text-secondary-foreground'),
      ),
    ).toBe(true);
  });

  // Synthetic future API variants exercise existing wording; the current DEMO API schema stays unchanged.
  it('preserves API actionability wording in status badges', () => {
    const actionable = mount(RunSummary, {
      props: {
        mode: 'review',
        run: {
          ...fullRun,
          demo: false,
          actionable: true,
        } as unknown as OptimizerRecommendationsResponse,
      },
    });
    const actionableBadge = actionable.get('[data-slot="badge"]');
    expect(actionableBadge.text()).toBe('API-marked actionable · no order controls');
    expect(actionableBadge.attributes('role')).toBe('status');

    const nonActionable = mount(RunSummary, {
      props: {
        mode: 'review',
        run: {
          ...fullRun,
          demo: false,
          actionable: false,
        } as unknown as OptimizerRecommendationsResponse,
      },
    });
    expect(nonActionable.get('[data-slot="badge"]').text()).toBe('NON-ACTIONABLE');
  });

  it('withholds previous financial values while a review update is pending', () => {
    const wrapper = mount(RunSummary, {
      props: {
        mode: 'review',
        run: {
          ...fullRun,
          estimated_realized_st_usd: '-999.00',
        },
        context,
        pending: true,
        view: 'current',
        provenanceLabel: 'Review update pending · prior run withheld',
      },
    });
    expect(wrapper.get('[role="status"]').text()).toContain(
      'Review update pending · prior run withheld',
    );
    const pendingBanner = wrapper
      .findAll('[data-slot="alert"]')
      .find((banner) =>
        banner.text().includes('requested selection or annotation is being saved or re-solved'),
      );
    expect(pendingBanner?.attributes('role')).toBe('status');
    expect(wrapper.text()).not.toContain('999.00 USD');
  });

  it('shows no-trade and unavailable-provenance states without inferring context', () => {
    const wrapper = mount(RunSummary, {
      props: {
        mode: 'review',
        run: { ...fullRun, estimated_tax_benefit_status: 'tax_profile_incomplete' },
        context: unavailableContext,
      },
    });
    expect(wrapper.text()).toContain('No beneficial trades identified');
    expect(wrapper.text()).toContain('tax_profile_incomplete');
    expect(wrapper.text()).toContain('the saved summary has no frozen policy data');
    expect(wrapper.text()).toContain('No order preview, approval, or submission controls');
  });
  it('keeps provenance polite and static warnings neutral instead of announcing them as alerts', () => {
    const wrapper = mount(RunSummary, {
      props: {
        mode: 'review',
        run: {
          ...fullRun,
          estimated_tax_benefit_status: 'optimizer_unavailable',
        },
        view: 'stale',
        provenanceLabel: 'Stale/unverified run · read-only',
      },
    });
    const banners = wrapper.findAll('[data-slot="alert"]');
    expect(banners.map((banner) => banner.attributes('role'))).toEqual([
      'status',
      'group',
      'group',
    ]);
    expect(banners[0]?.classes()).toContain('tw:text-destructive');
    expect(banners[0]?.classes()).toContain('tw:bg-card');
    expect(banners[0]?.text()).toContain('Stale/unverified run · read-only');
    expect(wrapper.get('[aria-label="DEMO solver output notice"]').text()).toContain(
      'hypothetical and non-executable',
    );
    const taxNotice = wrapper.get('[aria-label="Tax estimate availability notice"]');
    expect(taxNotice.classes()).toContain('tw:text-destructive');
    expect(taxNotice.classes()).toContain('tw:bg-card');
    expect(wrapper.get('[aria-label="Tax estimate availability notice"]').text()).toContain(
      'No production optimization or feasibility claim is made.',
    );
    expect(wrapper.find('[role="alert"]').exists()).toBe(false);
  });
  it('uses a native keyboard-accessible frozen-assumptions disclosure', async () => {
    const wrapper = mount(RunSummary, {
      props: { mode: 'overview', run: fullRun, context },
    });
    const details = wrapper.get('details');
    const summary = wrapper.get('details summary');

    expect(summary.element.tagName).toBe('SUMMARY');
    expect(details.attributes('open')).toBeUndefined();
    await summary.trigger('click');
    expect(details.attributes('open')).toBe('');
  });
});

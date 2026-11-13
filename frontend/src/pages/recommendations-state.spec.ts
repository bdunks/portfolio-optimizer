import { describe, expect, it } from 'vitest';
import type {
  FrozenRunDisplayContextResponse,
  OptimizerRecommendationsResponse,
} from '@/types/api';

import {
  buildSelectionPayload,
  canonicalLegs,
  requestLotSelection,
  selectedSellGrossLossUsd,
  sharedLegs,
} from './recommendations-state';

const frozenDisplayContext = {
  available: true,
  source: 'policy_revision',
  policy_revision_id: 'policy-fixture',
  revision_number: 1,
  created_at: '2025-01-01T00:00:00Z',
  activated_at: '2025-01-01T00:00:00Z',
  sleeves: [],
  settings: { target_retained_net_loss_usd: '3000.00' },
  allowed_securities: [],
  overrides: [],
  unavailable_reason: null,
} satisfies FrozenRunDisplayContextResponse;
const run = {
  run_id: 'run-fixture',
  status: 'demo',
  mode: 'recommendations_only',
  policy_revision_id: 'policy-fixture',
  source_generation: 1,
  as_of: '2025-01-01T00:00:00Z',
  solver_version: 'DEMO',
  demo: true,
  actionable: false,
  input_fingerprint: null,
  source_checksum: null,
  batch_settings: {},
  estimated_realized_st_usd: '-4.00',
  estimated_realized_lt_usd: '0.00',
  estimated_tax_benefit_usd: null,
  estimated_tax_benefit_status: 'optimizer_unavailable',
  lots_sold_count: 0,
  positions_exited_count: 0,
  orders_count: 0,
  cash_before_usd: null,
  cash_after_usd: null,
  portfolio_effects: null,
  constraints_satisfied: null,
  no_trade_reason: null,
  warnings: [],
  tax_profile_configured: false,
  frozen_display_context: frozenDisplayContext,
  groups: [
    {
      group_id: 'group-a',
      rank: 1,
      group_type: 'demo_loss_harvest',
      sleeve_key: 'us',
      rationale: 'Fixture rationale',
      estimated_benefit_usd: null,
      impact: {
        demo: true,
        wash_status: 'not_validated_demo',
        selected_sell_lots_count: 0,
        sell_proceeds_usd: '20.00',
        realized_st_usd: '-4.00',
        realized_lt_usd: '0.00',
        replacement_buy_shares: '0',
        replacement_buy_cost_usd: '0.00',
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
      leg_ids: ['sell-a', 'buy-shared'],
      warnings: [],
    },
    {
      group_id: 'group-b',
      rank: 2,
      group_type: 'demo_loss_harvest',
      sleeve_key: 'us',
      rationale: 'Second fixture rationale',
      estimated_benefit_usd: null,
      impact: {
        demo: true,
        wash_status: 'not_validated_demo',
        selected_sell_lots_count: 0,
        sell_proceeds_usd: '30.00',
        realized_st_usd: '-2.00',
        realized_lt_usd: '0.00',
        replacement_buy_shares: '0',
        replacement_buy_cost_usd: '0.00',
        cash_after_usd: '30.00',
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
      leg_ids: ['sell-b', 'buy-shared'],
      warnings: [],
    },
  ],
  consolidated_legs: [
    {
      leg_id: 'sell-a',
      side: 'SELL',
      ticker: 'AAPL',
      shares: '1',
      estimated_unit_price_usd: '20.00',
      estimated_notional_usd: '20.00',
      net_st_realized_usd: '-4.00',
      net_lt_realized_usd: '0.00',
      selected: false,
      group_ids: ['group-a'],
      sequence: 1,
      dependencies: [],
      selected_lots: [
        {
          broker_lot_id: 'broker-lot-a',
          shares: '1',
          acquired_date: '2024-01-01',
          adjusted_basis_usd: '24.00',
          st_lt: 'ST',
          realized_pl_usd: '-4.00',
          selected: false,
        },
      ],
      details: {},
    },
    {
      leg_id: 'sell-b',
      side: 'SELL',
      ticker: 'MSFT',
      shares: '1',
      estimated_unit_price_usd: '30.00',
      estimated_notional_usd: '30.00',
      net_st_realized_usd: '-2.00',
      net_lt_realized_usd: '0.00',
      selected: false,
      group_ids: ['group-b'],
      sequence: 2,
      dependencies: [],
      selected_lots: [
        {
          broker_lot_id: 'broker-lot-b',
          shares: '1',
          acquired_date: '2023-01-01',
          adjusted_basis_usd: '32.00',
          st_lt: 'LT',
          realized_pl_usd: '-2.00',
          selected: false,
        },
      ],
      details: {},
    },
    {
      leg_id: 'buy-shared',
      side: 'BUY',
      ticker: 'VTI',
      shares: '1',
      estimated_unit_price_usd: '50.00',
      estimated_notional_usd: '50.00',
      net_st_realized_usd: '0.00',
      net_lt_realized_usd: '0.00',
      selected: false,
      group_ids: ['group-a', 'group-b'],
      sequence: 3,
      dependencies: ['sell-a', 'sell-b'],
      selected_lots: [],
      details: {},
    },
  ],
} satisfies OptimizerRecommendationsResponse;

function multiLotRun(
  selectedLotIds: string[],
  totals: { shares: string; notional: string; selectedLotCount: number; realizedSt: string },
): OptimizerRecommendationsResponse {
  const selected = new Set(selectedLotIds);
  return {
    ...run,
    estimated_realized_st_usd: totals.realizedSt,
    estimated_realized_lt_usd: '0.00',
    lots_sold_count: totals.selectedLotCount,
    orders_count: totals.selectedLotCount > 0 ? 2 : 0,
    groups: run.groups.map((group) =>
      group.group_id === 'group-a'
        ? {
            ...group,
            selected: totals.selectedLotCount > 0,
            impact: {
              ...group.impact,
              selected_sell_lots_count: totals.selectedLotCount,
              sell_proceeds_usd: totals.notional,
              realized_st_usd: totals.realizedSt,
              cash_after_usd: totals.notional,
            },
          }
        : group,
    ),
    consolidated_legs: run.consolidated_legs.map((leg) =>
      leg.leg_id === 'sell-a'
        ? {
            ...leg,
            shares: totals.shares,
            estimated_notional_usd: totals.notional,
            net_st_realized_usd: totals.realizedSt,
            selected: totals.selectedLotCount > 0,
            selected_lots: [
              { ...leg.selected_lots[0]!, selected: selected.has('broker-lot-a') },
              {
                broker_lot_id: 'broker-lot-a2',
                shares: '1',
                acquired_date: '2024-02-01',
                adjusted_basis_usd: '24.00',
                st_lt: 'ST',
                realized_pl_usd: '-4.00',
                selected: selected.has('broker-lot-a2'),
              },
            ],
          }
        : leg,
    ),
  };
}

describe('recommendations selection state', () => {
  it('sums selected negative lot P/L exactly and excludes signed leg nets and unselected lots', () => {
    const firstSell = run.consolidated_legs[0]!;
    const secondSell = run.consolidated_legs[1]!;
    const selectedFirst = {
      ...firstSell,
      selected: true,
      selected_lots: [
        { ...firstSell.selected_lots[0]!, realized_pl_usd: '-1.25', selected: true },
        {
          ...firstSell.selected_lots[0]!,
          broker_lot_id: 'positive-lot',
          realized_pl_usd: '3.00',
          selected: true,
        },
        {
          ...firstSell.selected_lots[0]!,
          broker_lot_id: 'unselected-loss',
          realized_pl_usd: '-8.00',
          selected: false,
        },
      ],
    };
    const selectedSecond = {
      ...secondSell,
      selected: true,
      selected_lots: [
        { ...secondSell.selected_lots[0]!, realized_pl_usd: '-0.05', selected: true },
      ],
    };
    const selectedBuy = { ...run.consolidated_legs[2]!, selected: true };

    expect(selectedSellGrossLossUsd([selectedFirst, selectedSecond, selectedBuy])).toBe('1.30');
  });

  it('returns exact zero for no selected SELL losses and withholds malformed selected lot values', () => {
    const sell = run.consolidated_legs[0]!;
    expect(selectedSellGrossLossUsd([sell])).toBe('0.00');
    expect(
      selectedSellGrossLossUsd([
        {
          ...sell,
          selected: true,
          selected_lots: [{ ...sell.selected_lots[0]!, selected: false }],
        },
      ]),
    ).toBeNull();
    expect(
      selectedSellGrossLossUsd([
        {
          ...sell,
          selected: true,
          selected_lots: [
            { ...sell.selected_lots[0]!, realized_pl_usd: 'not-a-decimal', selected: true },
          ],
        },
      ]),
    ).toBeNull();
  });

  it('keeps a canonical shared BUY leg unique and links it from both groups', () => {
    expect(canonicalLegs(run).filter((leg) => leg.leg_id === 'buy-shared')).toHaveLength(1);
    expect(sharedLegs(run).map((leg) => leg.leg_id)).toEqual(['buy-shared']);
  });

  it('serializes only selected groups and exact known broker lot IDs', () => {
    expect(
      buildSelectionPayload(run, ['group-a', 'unknown'], {
        'group-a': ['broker-lot-a', 'made-up'],
      }),
    ).toEqual({
      selected_group_ids: ['group-a'],
      selected_sell_lots: { 'group-a': ['broker-lot-a'] },
    });
  });

  it('deselects a group when its final SELL lot is removed instead of sending an empty group', () => {
    const selectedRun: OptimizerRecommendationsResponse = {
      ...run,
      groups: run.groups.map((group) =>
        group.group_id === 'group-a' ? { ...group, selected: true } : group,
      ),
      consolidated_legs: run.consolidated_legs.map((leg) =>
        leg.leg_id === 'sell-a'
          ? {
              ...leg,
              selected: true,
              selected_lots: leg.selected_lots.map((lot) => ({ ...lot, selected: true })),
            }
          : leg,
      ),
    };

    expect(requestLotSelection(selectedRun, 'group-a', 'broker-lot-a', false)).toEqual({
      selected_group_ids: [],
      selected_sell_lots: {},
    });
  });
  it('re-adds a lot without dropping the existing selected lot subset', () => {
    const selectedRun = multiLotRun(['broker-lot-a'], {
      shares: '1',
      notional: '20.00',
      selectedLotCount: 1,
      realizedSt: '-4.00',
    });

    expect(requestLotSelection(selectedRun, 'group-a', 'broker-lot-a2', true)).toEqual({
      selected_group_ids: ['group-a'],
      selected_sell_lots: { 'group-a': ['broker-lot-a', 'broker-lot-a2'] },
    });
  });

  it('selects only the requested lot from a fully deselected multi-lot group', () => {
    const deselectedRun = multiLotRun([], {
      shares: '0',
      notional: '0.00',
      selectedLotCount: 0,
      realizedSt: '0.00',
    });

    expect(requestLotSelection(deselectedRun, 'group-a', 'broker-lot-a2', true)).toEqual({
      selected_group_ids: ['group-a'],
      selected_sell_lots: { 'group-a': ['broker-lot-a2'] },
    });
  });
});

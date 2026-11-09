import { describe, expect, it } from 'vitest';
import type { FrozenRunDisplayContextResponse } from '@/types/api';
import {
  completeFrozenRunSleeveLabels,
  frozenRunSleeveLabel,
  selectRunDisplayContext,
} from './run-context';

const frozenContext: FrozenRunDisplayContextResponse = {
  available: true,
  source: 'policy_revision',
  policy_revision_id: 'policy-historical',
  revision_number: 3,
  created_at: '2024-01-01T00:00:00Z',
  activated_at: '2024-01-02T00:00:00Z',
  sleeves: [
    {
      sleeve_key: 'us',
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

describe('shared frozen run context selection', () => {
  it('prefers the full run context and falls back to a saved summary only when needed', () => {
    const detailed = { run_id: 'run-1', frozen_display_context: frozenContext };
    const summary = { run_id: 'run-1', frozen_display_context: frozenContext };
    expect(selectRunDisplayContext(detailed, summary)).toBe(frozenContext);
    expect(selectRunDisplayContext(null, summary)).toBe(frozenContext);
  });

  it('renders missing or unavailable frozen labels as unavailable, never from active policy data', () => {
    const unavailable: FrozenRunDisplayContextResponse = {
      ...frozenContext,
      available: false,
      source: null,
      sleeves: null,
      settings: null,
      allowed_securities: null,
      overrides: null,
      unavailable_reason: 'exact policy revision was not retained',
    };
    expect(selectRunDisplayContext(null, null)).toBeNull();
    expect(frozenRunSleeveLabel(null, 'us')).toContain('Unavailable');
    expect(frozenRunSleeveLabel(unavailable, 'us')).toContain('Unavailable');
    expect(completeFrozenRunSleeveLabels(unavailable, ['us'])).toEqual({
      us: 'Unavailable (frozen run context)',
    });
    expect(frozenRunSleeveLabel(frozenContext, 'us')).toBe('Historical US sleeve');
  });
});

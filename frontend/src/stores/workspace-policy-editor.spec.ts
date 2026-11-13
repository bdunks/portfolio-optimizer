// @vitest-environment jsdom
import { effectScope } from 'vue';
import { describe, expect, it, vi } from 'vitest';
import type {
  PolicyDraftInput,
  PolicyResponse,
  PolicyRevisionResponse,
  PolicySettingsResponse,
} from '../types/api';
import { policyDraftSignature } from '../pages/policy-form';
import { createWorkspacePolicyEditor } from './workspace-policy-editor';

const settings: PolicySettingsResponse = {
  short_term_tax_rate: '0.2500',
  long_term_tax_rate: null,
  st_loss_carryforward_usd: '0.00',
  lt_loss_carryforward_usd: '15.20',
  ytd_realized_st_usd: '-4.01',
  ytd_realized_lt_usd: '0.00',
  ytd_source: 'fixture',
  ytd_as_of: '2025-01-31',
  target_retained_net_loss_usd: '3000.00',
  ordinary_income_deduction_limit_usd: '3000.00',
  carryforward_loss_discount_factor: '0.5000',
  gain_budget_usd: null,
  max_incremental_tax_cost_usd: '25.00',
  st_gain_limit_usd: null,
  lt_gain_limit_usd: '100.00',
  budget_period: 'calendar_year',
  max_sell_tickers_per_batch: 10,
  max_sell_lots_per_batch: 20,
  max_total_orders_per_batch: 12,
  max_batch_turnover_pct: '5.00',
  min_buy_order_notional_usd: '500.00',
  cash_reserve_usd: '0.00',
  prefer_etf_buys: true,
  allow_gain_sales: false,
  permit_etf_harvest: true,
  permit_muni_exit: false,
  objective_band_weight: null,
  objective_allocation_weight: null,
  objective_tax_weight: null,
  objective_trading_cost_weight: null,
  objective_turnover_weight: null,
  objective_cleanup_weight: null,
  estimated_spread_bps: null,
  estimated_fee_per_order_usd: null,
};

function revision(
  id: string,
  number: number,
  status: PolicyRevisionResponse['status'] = 'ACTIVE',
  overrides: PolicyRevisionResponse['overrides'] = [],
): PolicyRevisionResponse {
  return {
    id,
    revision_number: number,
    status,
    created_at: `2025-01-${String(number).padStart(2, '0')}T00:00:00Z`,
    activated_at: status === 'ACTIVE' ? '2025-01-01T00:00:00Z' : null,
    settings,
    sleeves: [
      {
        sleeve_key: `sleeve-${id}`,
        display_name: `Sleeve ${id}`,
        sort_order: 0,
        parent_sleeve_key: null,
        target_pct: '100.0000',
        drift_band_pp: '2.2500',
        is_direct_index_container: false,
        is_direct_index_sleeve: false,
        is_transition_destination: false,
        is_cash_sleeve: false,
        enabled: true,
      },
    ],
    allowed_securities: [],
    overrides,
    activation_errors: [],
  };
}

function policy(
  drafts: PolicyRevisionResponse[] = [],
  active: PolicyRevisionResponse | null = null,
  superseded: PolicyRevisionResponse[] = [],
): PolicyResponse {
  return { active, drafts, superseded };
}

function scopedEditor(operations?: {
  saveDraft?: (payload: PolicyDraftInput) => Promise<PolicyRevisionResponse>;
  activateRevision?: (id: string) => Promise<PolicyRevisionResponse>;
}) {
  const scope = effectScope();
  let editor!: ReturnType<typeof createWorkspacePolicyEditor>;
  scope.run(() => {
    editor = createWorkspacePolicyEditor({
      saveDraft:
        operations?.saveDraft ?? (() => Promise.resolve(revision('saved-result', 20, 'DRAFT'))),
      activateRevision:
        operations?.activateRevision ?? ((id) => Promise.resolve(revision(id, 20, 'ACTIVE'))),
    });
  });
  return { editor, dispose: () => scope.stop() };
}

function beforeUnloadEvent(): BeforeUnloadEvent {
  return new Event('beforeunload', { cancelable: true });
}

describe('workspace-owned policy editor', () => {
  it('selects the latest draft and ignores later refreshes', () => {
    const { editor, dispose } = scopedEditor();
    const draft4 = revision('draft-4', 4, 'DRAFT');
    const draft11 = revision('draft-11', 11, 'DRAFT');
    editor.initializeFromWorkspace(policy([draft4, draft11], revision('active', 9)));
    expect(editor.state.sourceRevisionId).toBe('draft-11');
    expect(editor.dirty.value).toBe(false);

    editor.state.draft.settings.cash_reserve_usd = '77.00';
    editor.initializeFromWorkspace(policy([revision('newly-returned', 100, 'DRAFT')], null));
    expect(editor.state.sourceRevisionId).toBe('draft-11');
    expect(editor.state.draft.settings.cash_reserve_usd).toBe('77.00');
    expect(editor.dirty.value).toBe(true);
    dispose();
  });

  it('keeps a submitted snapshot baseline and later edits when a save resolves', async () => {
    let resolveSave!: (result: PolicyRevisionResponse) => void;
    let submittedPayload!: PolicyDraftInput;
    const { editor, dispose } = scopedEditor({
      saveDraft: vi.fn((payload) => {
        submittedPayload = payload;
        return new Promise<PolicyRevisionResponse>((resolve) => {
          resolveSave = resolve;
        });
      }),
    });
    const source = revision('source', 1);
    const other = revision('other', 2, 'DRAFT');
    editor.initializeFromWorkspace(policy([], source));
    editor.state.draft.settings.cash_reserve_usd = '1.00';
    const submitted = JSON.parse(JSON.stringify(editor.state.draft)) as typeof editor.state.draft;
    const savePending = editor.saveDraft();
    expect(editor.state.pendingSave).toBe(true);

    editor.state.draft.settings.cash_reserve_usd = '2.00';
    editor.state.draft.sleeves[0]!.target_pct = '99.99999999999999999999';
    expect(editor.requestRevisionChange(other.id, [source, other])).toBe('blocked');
    expect(editor.state.sourceRevisionId).toBe(source.id);

    const authoritative = [{ ticker: 'AAPL', sleeve_key: 'server', sub_sleeve_key: null }];
    const saved = revision('saved-result', 3, 'DRAFT', authoritative);
    resolveSave(saved);
    expect(await savePending).toBe(true);

    expect(submittedPayload.source_revision_id).toBe(source.id);
    expect(submittedPayload.settings.cash_reserve_usd).toBe('1.00');
    expect(editor.state.sourceRevisionId).toBe(saved.id);
    expect(editor.state.draft.settings.cash_reserve_usd).toBe('2.00');
    expect(editor.state.draft.sleeves[0]?.target_pct).toBe('99.99999999999999999999');
    expect(editor.state.draft.overrides).toEqual(authoritative);
    submitted.overrides = authoritative;
    submitted.reassignments = {};
    expect(editor.state.baselineSignature).toBe(policyDraftSignature(submitted));
    expect(editor.dirty.value).toBe(true);
    expect(editor.state.pendingSave).toBe(false);
    dispose();
  });
  it('reconciles changed pending reassignment commands onto exact generated holding overrides', async () => {
    const pendingResolves: Array<(result: PolicyRevisionResponse) => void> = [];
    const submittedPayloads: PolicyDraftInput[] = [];
    const { editor, dispose } = scopedEditor({
      saveDraft: vi.fn((payload) => {
        submittedPayloads.push(payload);
        return new Promise<PolicyRevisionResponse>((resolve) => pendingResolves.push(resolve));
      }),
    });
    const source = revision('source', 1);
    editor.initializeFromWorkspace(policy([], source));
    const baseSleeve = editor.state.draft.sleeves[0]!;
    editor.state.draft.sleeves = [
      { ...baseSleeve, sleeve_key: 'target-a', display_name: 'Target A' },
      { ...baseSleeve, sleeve_key: 'target-b', display_name: 'Target B' },
      { ...baseSleeve, sleeve_key: 'other', display_name: 'Other' },
    ];
    editor.state.draft.overrides = [
      { ticker: 'VTI', sleeve_key: 'other', sub_sleeve_key: null },
      { ticker: 'BND', sleeve_key: 'other', sub_sleeve_key: null },
    ];
    editor.state.draft.reassignments = { retired: 'target-a' };
    editor.state.draft.reassignmentHoldings = { retired: ['AAPL', 'MSFT', 'VTI'] };

    const firstSave = editor.saveDraft();
    expect(submittedPayloads[0]?.reassignments).toEqual({ retired: 'target-a' });
    editor.state.draft.reassignments.retired = 'target-b';
    editor.state.draft.overrides[1]!.sleeve_key = 'target-b';
    const firstOverrides = [
      { ticker: 'AAPL', sleeve_key: 'target-a', sub_sleeve_key: null },
      { ticker: 'MSFT', sleeve_key: 'target-a', sub_sleeve_key: null },
      { ticker: 'VTI', sleeve_key: 'other', sub_sleeve_key: null },
      { ticker: 'BND', sleeve_key: 'other', sub_sleeve_key: null },
    ];
    pendingResolves[0]!(revision('saved-a', 2, 'DRAFT', firstOverrides));
    expect(await firstSave).toBe(true);

    expect(editor.state.sourceRevisionId).toBe('saved-a');
    expect(editor.state.draft.reassignments).toEqual({ retired: 'target-b' });
    expect(editor.state.draft.overrides).toEqual([
      { ticker: 'AAPL', sleeve_key: 'target-b', sub_sleeve_key: null },
      { ticker: 'MSFT', sleeve_key: 'target-b', sub_sleeve_key: null },
      { ticker: 'VTI', sleeve_key: 'other', sub_sleeve_key: null },
      { ticker: 'BND', sleeve_key: 'target-b', sub_sleeve_key: null },
    ]);
    expect(editor.state.draft.reassignmentHoldings).toEqual({ retired: ['AAPL', 'MSFT', 'VTI'] });
    expect(editor.dirty.value).toBe(true);

    const secondSave = editor.saveDraft();
    expect(submittedPayloads[1]?.source_revision_id).toBe('saved-a');
    expect(submittedPayloads[1]?.overrides).toEqual(editor.state.draft.overrides);
    expect(submittedPayloads[1]?.reassignments).toEqual({ retired: 'target-b' });
    pendingResolves[1]!(
      revision('saved-b', 3, 'DRAFT', [
        { ticker: 'AAPL', sleeve_key: 'target-b', sub_sleeve_key: null },
        { ticker: 'MSFT', sleeve_key: 'target-b', sub_sleeve_key: null },
        { ticker: 'VTI', sleeve_key: 'other', sub_sleeve_key: null },
        { ticker: 'BND', sleeve_key: 'target-b', sub_sleeve_key: null },
      ]),
    );
    expect(await secondSave).toBe(true);
    expect(editor.state.draft.overrides).toEqual([
      { ticker: 'AAPL', sleeve_key: 'target-b', sub_sleeve_key: null },
      { ticker: 'MSFT', sleeve_key: 'target-b', sub_sleeve_key: null },
      { ticker: 'VTI', sleeve_key: 'other', sub_sleeve_key: null },
      { ticker: 'BND', sleeve_key: 'target-b', sub_sleeve_key: null },
    ]);
    expect(editor.state.draft.reassignments).toEqual({});
    expect(editor.state.draft.reassignmentHoldings).toEqual({});
    expect(editor.dirty.value).toBe(false);
    dispose();
  });

  it('does not overwrite edits made while activation is pending', async () => {
    let resolveActivation!: (result: PolicyRevisionResponse) => void;
    const draft = revision('draft', 5, 'DRAFT');
    const { editor, dispose } = scopedEditor({
      activateRevision: () =>
        new Promise<PolicyRevisionResponse>((resolve) => {
          resolveActivation = resolve;
        }),
    });
    editor.initializeFromWorkspace(policy([draft]));
    const originalBaseline = editor.state.baselineSignature;
    expect(editor.canActivate.value).toBe(true);
    const activationPending = editor.activateSaved();
    expect(editor.state.pendingActivation).toBe(true);
    editor.state.draft.settings.cash_reserve_usd = '9.00';

    resolveActivation({ ...draft, status: 'ACTIVE', activated_at: '2025-02-01T00:00:00Z' });
    expect(await activationPending).toBe(true);
    expect(editor.state.draft.settings.cash_reserve_usd).toBe('9.00');
    expect(editor.state.sourceRevisionId).toBe(draft.id);
    expect(editor.state.savedRevisionId).toBeNull();
    expect(editor.state.lastSavedRevision?.status).toBe('ACTIVE');
    expect(editor.state.baselineSignature).toBe(originalBaseline);
    expect(editor.dirty.value).toBe(true);
    expect(editor.state.pendingActivation).toBe(false);
    dispose();
  });

  it('supports explicit revision-switch cancel, discard, and save choices', async () => {
    const source = revision('source', 1);
    const target = revision('target', 2, 'DRAFT');
    const saved = revision('intermediate-save', 3, 'DRAFT');
    const { editor, dispose } = scopedEditor({ saveDraft: () => Promise.resolve(saved) });
    editor.initializeFromWorkspace(policy([], source));

    editor.state.draft.settings.cash_reserve_usd = '1.00';
    expect(editor.requestRevisionChange(target.id, [source, target])).toBe('confirm');
    expect(editor.state.pendingRevisionId).toBe(target.id);
    editor.cancelRevisionChange();
    expect(editor.state.sourceRevisionId).toBe(source.id);
    expect(editor.state.draft.settings.cash_reserve_usd).toBe('1.00');
    expect(editor.state.pendingRevisionId).toBeNull();

    expect(editor.requestRevisionChange(target.id, [source, target])).toBe('confirm');
    expect(editor.discardAndLoadRevision([source, target])).toBe(true);
    expect(editor.state.sourceRevisionId).toBe(target.id);
    expect(editor.dirty.value).toBe(false);

    editor.state.draft.settings.cash_reserve_usd = '2.00';
    const next = revision('next', 4, 'DRAFT');
    expect(editor.requestRevisionChange(next.id, [target, next])).toBe('confirm');
    expect(await editor.saveAndLoadRevision([target, next])).toBe(true);
    expect(editor.state.sourceRevisionId).toBe(next.id);
    expect(editor.state.draft.settings.cash_reserve_usd).toBe(settings.cash_reserve_usd);
    expect(editor.dirty.value).toBe(false);
    dispose();
  });

  it('warns on beforeunload while dirty and releases the listener with the store scope', () => {
    const { editor, dispose } = scopedEditor();
    const source = revision('source', 1);
    editor.initializeFromWorkspace(policy([], source));
    const cleanUnload = beforeUnloadEvent();
    window.dispatchEvent(cleanUnload);
    expect(cleanUnload.defaultPrevented).toBe(false);

    editor.state.draft.settings.cash_reserve_usd = '1.00';
    const dirtyUnload = beforeUnloadEvent();
    window.dispatchEvent(dirtyUnload);
    expect(dirtyUnload.defaultPrevented).toBe(true);

    dispose();
    const afterDispose = beforeUnloadEvent();
    window.dispatchEvent(afterDispose);
    expect(afterDispose.defaultPrevented).toBe(false);
  });
});

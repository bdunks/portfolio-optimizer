import { existsSync, mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createPinia } from 'pinia';
import { flushPromises, type VueWrapper } from '@vue/test-utils';
import { mountWithQuasar } from '@/test-utils/quasar-mount';
import {
  availableLoopbackPort,
  startIsolatedBackend,
  type IsolatedBackendProcess as BackendProcess,
} from '@/test-utils/isolated-backend';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { createMemoryHistory, createRouter } from 'vue-router';
import App from '@/App.vue';
import routes from '@/router/routes';
import { useWorkspaceStore } from '@/stores/workspace-store';
import type { OptimizerRecommendationsResponse } from '@/types/api';

type MountedWorkspace = {
  pinia: ReturnType<typeof createPinia>;
  router: ReturnType<typeof createRouter>;
  wrapper: VueWrapper;
};

function delay(milliseconds: number): Promise<void> {
  return new Promise((resolveDelay) => setTimeout(resolveDelay, milliseconds));
}

async function mountWorkspace(): Promise<MountedWorkspace> {
  const pinia = createPinia();
  const router = createRouter({ history: createMemoryHistory(), routes });
  await router.push('/');
  await router.isReady();
  const wrapper = mountWithQuasar(App, {
    global: { plugins: [pinia, router] },
  });
  await flushPromises();
  return { pinia, router, wrapper };
}

async function visit(workspace: MountedWorkspace, path: string): Promise<void> {
  await workspace.router.push(path);
  await flushPromises();
  expect(workspace.router.currentRoute.value.path).toBe(path);
}

async function waitFor(check: () => boolean, description: string): Promise<void> {
  const deadline = Date.now() + 15_000;
  while (Date.now() < deadline) {
    await flushPromises();
    if (check()) return;
    await delay(25);
  }
  throw new Error(`Timed out waiting for ${description}`);
}

function assertCanonicalLegGraph(run: OptimizerRecommendationsResponse): void {
  const legsById = new Map(run.consolidated_legs.map((leg) => [leg.leg_id, leg]));
  expect(legsById.size).toBe(run.consolidated_legs.length);
  const buyTickers = run.consolidated_legs
    .filter((leg) => leg.side === 'BUY')
    .map((leg) => leg.ticker);
  expect(new Set(buyTickers).size).toBe(buyTickers.length);

  for (const group of run.groups) {
    expect(group.leg_ids.length).toBeGreaterThan(0);
    for (const legId of group.leg_ids) {
      expect(legsById.has(legId)).toBe(true);
      expect(legsById.get(legId)?.group_ids).toContain(group.group_id);
    }
  }
  for (const leg of run.consolidated_legs) {
    for (const dependencyId of leg.dependencies) {
      expect(leg.side).toBe('BUY');
      expect(legsById.get(dependencyId)?.side).toBe('SELL');
    }
    if (leg.side === 'BUY' && leg.selected) {
      expect(leg.dependencies.length).toBeGreaterThan(0);
      for (const dependencyId of leg.dependencies) {
        expect(legsById.get(dependencyId)?.selected).toBe(true);
      }
    }
  }
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('isolated local backend smoke', () => {
  it('uses isolated DEMO lot intent and review workflows', async () => {
    const tempDirectory = mkdtempSync(join(tmpdir(), 'portfolio-optimizer-stage-e-'));
    const databasePath = join(tempDirectory, 'isolated-demo.sqlite3');
    const port = await availableLoopbackPort();
    let backend: BackendProcess | null = null;
    let workspace: MountedWorkspace | null = null;
    const urlDescriptors = {
      create: Object.getOwnPropertyDescriptor(URL, 'createObjectURL'),
      revoke: Object.getOwnPropertyDescriptor(URL, 'revokeObjectURL'),
    };
    const downloads: Blob[] = [];
    const requests: string[] = [];
    const annotationBodies: string[] = [];
    const lotIntentBodies: string[] = [];
    let holdNextDraftWrite = false;
    const releaseWrite = {
      draft: null as (() => void) | null,
      activation: null as (() => void) | null,
    };
    let holdNextActivationWrite = false;

    try {
      backend = await startIsolatedBackend(databasePath, port, true);
      let backendBase = backend.baseUrl;
      const networkFetch = globalThis.fetch.bind(globalThis);
      vi.stubGlobal('fetch', async (input: RequestInfo | URL, init?: RequestInit) => {
        const value =
          typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
        const address = new URL(value, `${backendBase}/`);
        if (address.origin !== backendBase || address.hostname !== '127.0.0.1') {
          throw new Error(`Integration test refuses non-local API traffic: ${address.origin}`);
        }
        const method = init?.method ?? 'GET';
        requests.push(`${method} ${address.pathname}${address.search}`);
        if (
          method === 'PATCH' &&
          address.pathname.includes('/recommendations/') &&
          typeof init?.body === 'string'
        )
          annotationBodies.push(init.body);
        if (
          method === 'POST' &&
          address.pathname.endsWith('/lot-review-intent') &&
          typeof init?.body === 'string'
        )
          lotIntentBodies.push(init.body);
        if (
          method === 'POST' &&
          address.pathname === '/api/v1/policy/drafts' &&
          holdNextDraftWrite
        ) {
          holdNextDraftWrite = false;
          await new Promise<void>((resolve) => {
            releaseWrite.draft = resolve;
          });
        }
        if (
          method === 'POST' &&
          address.pathname.endsWith('/activate') &&
          holdNextActivationWrite
        ) {
          holdNextActivationWrite = false;
          await new Promise<void>((resolve) => {
            releaseWrite.activation = resolve;
          });
        }
        return networkFetch(address, init);
      });

      const health = await (await fetch(`${backend.baseUrl}/health`)).json();
      expect(health).toMatchObject({
        status: 'ok',
        broker_mode: 'fake',
        live_broker_enabled: false,
        order_submission_enabled: false,
      });
      workspace = await mountWorkspace();
      await waitFor(() => {
        const store = useWorkspaceStore(workspace!.pinia);
        return (
          store.health?.status === 'ok' &&
          store.portfolio?.status === 'ready' &&
          store.policy?.active != null
        );
      }, 'initial health, portfolio, and policy API responses');
      expect(workspace.wrapper.find('h1').text()).toBe('Overview');
      expect(workspace.wrapper.text()).toContain('DEMO analysis only.');
      expect(workspace.wrapper.text()).toContain('DEMO — Hypothetical Account');

      await visit(workspace, '/recommendations');
      expect(workspace.wrapper.text()).toContain('No recommendation run loaded');
      await workspace.wrapper
        .get('input[placeholder="Run ID from Activity"]')
        .setValue('missing-stage-e-run');
      await workspace.wrapper.get('form.saved-run-form').trigger('submit');
      await flushPromises();
      await waitFor(
        () => workspace!.wrapper.text().includes('run_not_found'),
        'real missing-run API error',
      );
      expect(workspace.wrapper.text()).toContain('run_not_found');
      expect(workspace.wrapper.text()).toContain('Optimizer run was not found');

      await visit(workspace, '/lots');
      expect(workspace.wrapper.find('h1').text()).toBe('Tax Lots');
      await waitFor(
        () => workspace!.wrapper.text().includes('DEMO-VB-LOT-1'),
        'real tax-lot API response',
      );
      expect(workspace.wrapper.text()).toContain('DEMO-VB-LOT-1');
      await visit(workspace, '/wash-sales');
      await waitFor(
        () => useWorkspaceStore(workspace!.pinia).washSales !== null,
        'real wash-sales API response',
      );
      expect(workspace.wrapper.find('h1').text()).toBe('Wash Sales');
      expect(workspace.wrapper.text()).toContain('DEMO ONLY.');
      await visit(workspace, '/activity');
      expect(workspace.wrapper.find('h1').text()).toBe('Activity');
      await waitFor(
        () => useWorkspaceStore(workspace!.pinia).activity !== null,
        'real seeded activity API response',
      );
      await workspace.wrapper.findAll('input[type="search"]')[0]!.setValue('stage-e-no-match');
      await workspace.wrapper.get('form.filter-panel').trigger('submit');
      await waitFor(
        () => useWorkspaceStore(workspace!.pinia).activity?.total === 0,
        'filtered zero-event activity response',
      );
      expect(workspace.wrapper.text()).toContain('No activity events returned');

      await visit(workspace, '/policy');
      await waitFor(
        () => useWorkspaceStore(workspace!.pinia).policy?.active != null,
        'seed policy API response',
      );
      expect(workspace.wrapper.text()).toContain('Tax & Batch Settings');
      const lifecycleStore = useWorkspaceStore(workspace.pinia);
      await waitFor(
        () => lifecycleStore.policyEditor.state.initialized,
        'persistent policy editor initialization',
      );
      const initialSource = lifecycleStore.policyEditor.state.sourceRevisionId;
      expect(initialSource).toBe(lifecycleStore.policy?.active?.id);
      await lifecycleStore.runOptimizer();
      expect(lifecycleStore.currentRunView).toBe('current');
      const findRetainedLossInput = () =>
        workspace!.wrapper
          .findAll('.settings-group input')
          .find((input) =>
            input.element.closest('.field')?.textContent?.includes('Target retained net loss'),
          );
      const retainedLossInput = findRetainedLossInput();
      expect(retainedLossInput).toBeDefined();
      const exactRetainedLoss = '2345.670000000000001';
      await retainedLossInput!.setValue(exactRetainedLoss);
      expect(lifecycleStore.policyEditor.dirty).toBe(true);
      expect(workspace.wrapper.text()).toContain(
        'This draft stays in memory while the workspace is open; reload would discard it.',
      );

      await visit(workspace, '/activity');
      await waitFor(() => workspace!.wrapper.find('h1').text() === 'Activity', 'policy route exit');
      expect(lifecycleStore.policyEditor.state.sourceRevisionId).toBe(initialSource);
      expect(lifecycleStore.policyEditor.state.draft.settings.target_retained_net_loss_usd).toBe(
        exactRetainedLoss,
      );
      const unloadAfterLeavingPolicy = new Event('beforeunload', { cancelable: true });
      window.dispatchEvent(unloadAfterLeavingPolicy);
      expect(unloadAfterLeavingPolicy.defaultPrevented).toBe(true);

      await visit(workspace, '/policy');
      await waitFor(() => !!findRetainedLossInput()?.element, 'dirty policy editor remount');
      expect((findRetainedLossInput()!.element as HTMLInputElement).value).toBe(exactRetainedLoss);
      const refreshPolicy = workspace.wrapper
        .findAll('button')
        .find((button) => button.text() === 'Refresh policy list');
      expect(refreshPolicy).toBeDefined();
      await refreshPolicy!.trigger('click');
      await waitFor(
        () => !lifecycleStore.actionState.loadPolicy.pending,
        'policy revision-list refresh while the editor is dirty',
      );
      expect(lifecycleStore.policyEditor.state.sourceRevisionId).toBe(initialSource);
      expect(lifecycleStore.policyEditor.state.draft.settings.target_retained_net_loss_usd).toBe(
        exactRetainedLoss,
      );

      holdNextDraftWrite = true;
      const saveDraft = workspace.wrapper
        .findAll('button')
        .find((button) => button.text().includes('Save new draft revision'));
      expect(saveDraft).toBeDefined();
      await saveDraft!.trigger('click');
      await waitFor(
        () => lifecycleStore.policyEditor.state.pendingSave,
        'policy draft save pending',
      );
      await visit(workspace, '/activity');
      expect(lifecycleStore.policyEditor.state.pendingSave).toBe(true);
      expect(lifecycleStore.policyEditor.state.sourceRevisionId).toBe(initialSource);
      expect(lifecycleStore.policyEditor.state.draft.settings.target_retained_net_loss_usd).toBe(
        exactRetainedLoss,
      );
      expect(releaseWrite.draft).not.toBeNull();
      releaseWrite.draft?.();
      releaseWrite.draft = null;
      await waitFor(
        () =>
          !lifecycleStore.policyEditor.state.pendingSave &&
          (lifecycleStore.policy?.drafts.some(
            (draft) => draft.settings.target_retained_net_loss_usd === exactRetainedLoss,
          ) ??
            false),
        'pending draft save and API revision refresh after route exit',
      );
      await visit(workspace, '/policy');
      await waitFor(
        () =>
          (findRetainedLossInput()?.element as HTMLInputElement | undefined)?.value ===
          exactRetainedLoss,
        'saved policy draft remount',
      );
      expect(workspace.wrapper.text()).toContain('Current form matches saved revision');
      const savedSource = lifecycleStore.policyEditor.state.sourceRevisionId;
      expect(savedSource).not.toBe(initialSource);
      expect(lifecycleStore.currentRunView).toBe('current');

      const activateDraft = workspace.wrapper
        .findAll('button')
        .find((button) => button.text().includes('Activate saved revision'));
      expect(activateDraft).toBeDefined();
      expect((activateDraft!.element as HTMLButtonElement).disabled).toBe(false);
      holdNextActivationWrite = true;
      await activateDraft!.trigger('click');
      await waitFor(
        () => lifecycleStore.policyEditor.state.pendingActivation,
        'policy activation pending',
      );
      await visit(workspace, '/activity');
      expect(lifecycleStore.policyEditor.state.pendingActivation).toBe(true);
      expect(lifecycleStore.policyEditor.state.sourceRevisionId).toBe(savedSource);
      expect(lifecycleStore.policyEditor.state.draft.settings.target_retained_net_loss_usd).toBe(
        exactRetainedLoss,
      );
      expect(releaseWrite.activation).not.toBeNull();
      releaseWrite.activation?.();
      releaseWrite.activation = null;
      await waitFor(
        () =>
          !lifecycleStore.policyEditor.state.pendingActivation &&
          useWorkspaceStore(workspace!.pinia).policy?.active?.settings
            .target_retained_net_loss_usd === exactRetainedLoss,
        'policy activation and refreshed active revision after route exit',
      );
      expect(lifecycleStore.currentRunView).toBe('stale');
      const savedValue = useWorkspaceStore(workspace.pinia).policy?.active?.settings
        .target_retained_net_loss_usd;
      expect(savedValue).toBe(exactRetainedLoss);
      await visit(workspace, '/policy');
      await waitFor(
        () => workspace!.wrapper.text().includes('Revision 2 · ACTIVE'),
        'active policy remount after activation',
      );
      expect(workspace.wrapper.text()).toContain('Revision 2 · ACTIVE');
      workspace.wrapper.unmount();
      workspace = null;
      await backend.stop();
      backend = null;
      backend = await startIsolatedBackend(databasePath, port, false);
      backendBase = backend.baseUrl;
      workspace = await mountWorkspace();
      await visit(workspace, '/policy');
      await waitFor(
        () =>
          useWorkspaceStore(workspace!.pinia).policy?.active?.settings
            .target_retained_net_loss_usd === exactRetainedLoss,
        'restarted backend persisted active policy',
      );
      expect(
        useWorkspaceStore(workspace.pinia).policy?.active?.settings.target_retained_net_loss_usd,
      ).toBe(exactRetainedLoss);
      await waitFor(() => {
        const retainedLossInput = workspace!.wrapper
          .findAll('.settings-group input')
          .find((input) =>
            input.element.closest('.field')?.textContent?.includes('Target retained net loss'),
          );
        return (
          (retainedLossInput?.element as HTMLInputElement | undefined)?.value === exactRetainedLoss
        );
      }, 'policy page reload of persisted target retained loss setting');
      expect(
        (
          workspace.wrapper
            .findAll('.settings-group input')
            .find((input) =>
              input.element.closest('.field')?.textContent?.includes('Target retained net loss'),
            )?.element as HTMLInputElement | undefined
        )?.value,
      ).toBe(exactRetainedLoss);

      const decimalStore = useWorkspaceStore(workspace.pinia);
      await waitFor(
        () => decimalStore.policyEditor.state.initialized,
        'restarted policy editor initialization',
      );
      const decimalEditor = decimalStore.policyEditor;
      const decimalSleeve = decimalEditor.state.draft.sleeves.find(
        (sleeve) => sleeve.parent_sleeve_key === null,
      )!;
      const decimalSleeveKey = decimalSleeve.sleeve_key;
      decimalEditor.state.draft.settings.cash_reserve_usd = '0.00000001';
      decimalSleeve.target_pct = '0.00000001';
      decimalSleeve.drift_band_pp = '0.00000001234567890123456789';
      expect(await decimalEditor.saveDraft()).toBe(true);
      const exponentRevision = decimalEditor.state.lastSavedRevision!;
      expect(exponentRevision.settings.cash_reserve_usd).toBe('1E-8');
      expect(
        exponentRevision.sleeves.find((sleeve) => sleeve.sleeve_key === decimalSleeveKey)
          ?.target_pct,
      ).toBe('1E-8');
      expect(
        exponentRevision.sleeves.find((sleeve) => sleeve.sleeve_key === decimalSleeveKey)
          ?.drift_band_pp,
      ).toBe('1.234567890123456789E-8');

      workspace.wrapper.unmount();
      workspace = null;
      workspace = await mountWorkspace();
      await visit(workspace, '/policy');
      const reopenedStore = useWorkspaceStore(workspace.pinia);
      await waitFor(
        () => reopenedStore.policyEditor.state.sourceRevisionId === exponentRevision.id,
        'reopened exponent-decimal policy revision',
      );
      await waitFor(
        () => reopenedStore.portfolio?.status === 'ready',
        'ready holdings for exact reassignment identity capture',
      );
      expect(reopenedStore.policyEditor.state.draft.settings.cash_reserve_usd).toBe('0.00000001');
      expect(
        reopenedStore.policyEditor.state.draft.sleeves.find(
          (sleeve) => sleeve.sleeve_key === decimalSleeveKey,
        )?.target_pct,
      ).toBe('0.00000001');
      expect(
        reopenedStore.policyEditor.state.draft.sleeves.find(
          (sleeve) => sleeve.sleeve_key === decimalSleeveKey,
        )?.drift_band_pp,
      ).toBe('0.00000001234567890123456789');
      expect(reopenedStore.policyEditor.dirty).toBe(false);
      reopenedStore.policyEditor.state.draft.settings.cash_reserve_usd =
        '0.000000010000000000000001';
      expect(await reopenedStore.policyEditor.saveDraft()).toBe(true);
      expect(reopenedStore.policyEditor.state.lastSavedRevision?.settings.cash_reserve_usd).toBe(
        '1.0000000000000001E-8',
      );

      const reassignmentEditor = reopenedStore.policyEditor;
      const retiredSleeve = reassignmentEditor.state.draft.sleeves.find(
        (sleeve) => sleeve.sleeve_key === 'direct_indexing',
      )!;
      const targetParent = reassignmentEditor.state.draft.sleeves.find(
        (sleeve) => sleeve.sleeve_key === 'us_equities',
      )!;
      const heldTickers = reopenedStore
        .portfolio!.positions.filter(
          (position) =>
            position.sleeve_key === retiredSleeve.sleeve_key ||
            position.sub_sleeve_key === retiredSleeve.sleeve_key,
        )
        .map((position) => position.ticker);
      expect(heldTickers).toEqual(expect.arrayContaining(['AAPL', 'VB']));
      const targetA = reassignmentEditor.state.draft.sleeves.find(
        (sleeve) => sleeve.sleeve_key === 'us_etf',
      )!;
      retiredSleeve.enabled = false;
      reassignmentEditor.state.draft.sleeves.push({
        ...targetA,
        sleeve_key: 'race-target-b',
        display_name: 'Reassignment target B',
        sort_order: reassignmentEditor.state.draft.sleeves.length,
        parent_sleeve_key: targetParent.sleeve_key,
        target_pct: '0',
        is_direct_index_container: false,
        is_direct_index_sleeve: false,
        is_transition_destination: false,
        is_cash_sleeve: false,
        enabled: true,
      });
      reassignmentEditor.state.draft.overrides.push({
        ticker: 'AAPL',
        sleeve_key: 'us_equities',
        sub_sleeve_key: null,
      });
      reassignmentEditor.state.draft.overrides.push({
        ticker: 'VTI',
        sleeve_key: 'us_equities',
        sub_sleeve_key: 'us_etf',
      });
      reassignmentEditor.state.draft.reassignments.direct_indexing = 'us_etf';
      reassignmentEditor.state.draft.reassignmentHoldings.direct_indexing = heldTickers;

      holdNextDraftWrite = true;
      const reassignmentSave = reassignmentEditor.saveDraft();
      await waitFor(() => reassignmentEditor.state.pendingSave, 'reassignment save pending');
      reassignmentEditor.state.draft.reassignments.direct_indexing = 'race-target-b';
      const releaseReassignmentWrite = releaseWrite.draft as (() => void) | null;
      expect(releaseReassignmentWrite).not.toBeNull();
      releaseReassignmentWrite?.();
      releaseWrite.draft = null;
      expect(await reassignmentSave).toBe(true);
      const firstReassignmentRevision = reassignmentEditor.state.lastSavedRevision!;
      expect(
        firstReassignmentRevision.overrides.find((override) => override.ticker === 'AAPL'),
      ).toEqual({ ticker: 'AAPL', sleeve_key: 'us_equities', sub_sleeve_key: null });
      const generatedHeldTickers = heldTickers.filter((ticker) => ticker !== 'AAPL');
      expect(
        generatedHeldTickers.map((ticker) =>
          firstReassignmentRevision.overrides.find((override) => override.ticker === ticker),
        ),
      ).toEqual(
        generatedHeldTickers.map((ticker) => ({
          ticker,
          sleeve_key: 'us_equities',
          sub_sleeve_key: 'us_etf',
        })),
      );
      expect(
        reassignmentEditor.state.draft.overrides.find((override) => override.ticker === 'AAPL'),
      ).toEqual({ ticker: 'AAPL', sleeve_key: 'us_equities', sub_sleeve_key: null });
      expect(
        generatedHeldTickers.map((ticker) =>
          reassignmentEditor.state.draft.overrides.find((override) => override.ticker === ticker),
        ),
      ).toEqual(
        generatedHeldTickers.map((ticker) => ({
          ticker,
          sleeve_key: 'us_equities',
          sub_sleeve_key: 'race-target-b',
        })),
      );
      expect(
        reassignmentEditor.state.draft.overrides.find((override) => override.ticker === 'VTI'),
      ).toEqual({ ticker: 'VTI', sleeve_key: 'us_equities', sub_sleeve_key: 'us_etf' });

      expect(await reassignmentEditor.saveDraft()).toBe(true);
      const finalReassignmentRevision = reassignmentEditor.state.lastSavedRevision!;
      expect(
        finalReassignmentRevision.overrides.find((override) => override.ticker === 'AAPL'),
      ).toEqual({ ticker: 'AAPL', sleeve_key: 'us_equities', sub_sleeve_key: null });
      expect(
        generatedHeldTickers.map((ticker) =>
          finalReassignmentRevision.overrides.find((override) => override.ticker === ticker),
        ),
      ).toEqual(
        generatedHeldTickers.map((ticker) => ({
          ticker,
          sleeve_key: 'us_equities',
          sub_sleeve_key: 'race-target-b',
        })),
      );
      expect(
        finalReassignmentRevision.overrides.find((override) => override.ticker === 'VTI'),
      ).toEqual({ ticker: 'VTI', sleeve_key: 'us_equities', sub_sleeve_key: 'us_etf' });

      await visit(workspace, '/');
      await waitFor(() => {
        const store = useWorkspaceStore(workspace!.pinia);
        return (
          store.health?.status === 'ok' &&
          store.portfolio?.status === 'ready' &&
          store.policy?.active != null
        );
      }, 'ready portfolio and active policy before running');
      const runButton = workspace.wrapper
        .findAll('button')
        .find((button) => button.text().includes('Run DEMO recommendations'));
      expect(runButton).toBeDefined();
      await runButton!.trigger('click');
      await flushPromises();
      await waitFor(
        () =>
          workspace!.router.currentRoute.value.path === '/recommendations' &&
          useWorkspaceStore(workspace!.pinia).currentRun !== null,
        'real DEMO run response and recommendations navigation',
      );
      expect(workspace.router.currentRoute.value.path).toBe('/recommendations');
      const store = useWorkspaceStore(workspace.pinia);
      const firstRun = store.currentRun;
      expect(firstRun).not.toBeNull();
      expect(firstRun).toMatchObject({
        status: 'demo',
        solver_version: 'DEMO',
        demo: true,
        actionable: false,
      });
      expect(firstRun!.groups.length).toBeGreaterThan(0);
      expect(workspace.wrapper.text()).toContain('DEMO hypothetical data');
      const firstSell = firstRun!.consolidated_legs.find((leg) => leg.side === 'SELL');
      expect(firstSell?.selected_lots.map((lot) => lot.broker_lot_id)).toEqual(['DEMO-VB-LOT-1']);
      expect(firstRun!.groups[0]!.leg_ids).toContain(firstSell?.leg_id);
      assertCanonicalLegGraph(firstRun!);

      const firstRunId = firstRun!.run_id;
      await visit(workspace, '/activity');
      await waitFor(
        () =>
          workspace!.wrapper
            .findAll('button.reopen-button')
            .some((button) => button.element.closest('li')?.textContent?.includes(firstRunId)),
        'saved run event from Activity API',
      );
      const firstRunReopenButton = workspace.wrapper
        .findAll('button.reopen-button')
        .find((button) => button.element.closest('li')?.textContent?.includes(firstRunId));
      expect(firstRunReopenButton).toBeDefined();
      await firstRunReopenButton!.trigger('click');
      await flushPromises();
      await waitFor(
        () => store.currentRunView === 'saved',
        'saved run summary and recommendations reopening',
      );
      expect(workspace.router.currentRoute.value.path).toBe('/recommendations');
      expect(store.currentRunView).toBe('saved');
      expect(workspace.wrapper.text()).toContain('Saved run · frozen API context · read-only');
      expect(store.currentRun?.run_id).toBe(firstRunId);

      const rerunButton = workspace.wrapper
        .findAll('button')
        .find((button) => button.text().includes('Run DEMO recommendations'));
      expect(rerunButton).toBeDefined();
      await rerunButton!.trigger('click');
      await flushPromises();
      await waitFor(
        () => store.currentRunView === 'current' && store.currentRun?.run_id !== firstRunId,
        'second real DEMO run for interactive subset selection',
      );
      expect(store.currentRunView).toBe('current');
      const run = store.currentRun;
      expect(run?.groups.length).toBeGreaterThan(0);
      assertCanonicalLegGraph(run!);

      const clearSelection = workspace.wrapper
        .findAll('button')
        .find((button) => button.text().includes('Clear selected groups and re-solve'));
      expect(clearSelection).toBeDefined();
      await clearSelection!.trigger('click');
      await flushPromises();
      await waitFor(
        () => store.currentRun?.orders_count === 0 && Boolean(store.currentRun.no_trade_reason),
        'real no-trade subset response',
      );
      expect(store.currentRun?.orders_count).toBe(0);
      expect(store.currentRun?.no_trade_reason).toBeTruthy();
      expect(workspace.wrapper.text()).toContain(
        'No beneficial trades identified / API no-trade reason',
      );
      assertCanonicalLegGraph(store.currentRun!);

      const groupId = store.currentRun!.groups[0]!.group_id;
      await workspace.wrapper
        .get(`[role="checkbox"][aria-label="Select recommendation group ${groupId}"]`)
        .trigger('click');
      await flushPromises();
      await waitFor(
        () => store.currentRun?.orders_count === 2 && store.currentRun.groups[0]?.selected === true,
        'real selected-group re-solve with funding BUY',
      );
      expect(store.currentRun?.orders_count).toBe(2);
      expect(store.currentRun?.groups[0]?.selected).toBe(true);
      const selectedBuy = store.currentRun?.consolidated_legs.find((leg) => leg.side === 'BUY');
      expect(selectedBuy?.ticker).toBe('VTI');
      expect(selectedBuy?.shares).toBe('2');
      expect(selectedBuy?.dependencies).toEqual([
        store.currentRun?.consolidated_legs.find((leg) => leg.side === 'SELL')?.leg_id,
      ]);
      assertCanonicalLegGraph(store.currentRun!);

      await visit(workspace, '/lots');
      const vbLotLabel = 'Request VB lot DEMO-VB-LOT-1';
      await waitFor(
        () => workspace!.wrapper.find(`[role="checkbox"][aria-label="${vbLotLabel}"]`).exists(),
        'current VB lot page',
      );
      await workspace.wrapper.get(`[role="checkbox"][aria-label="${vbLotLabel}"]`).trigger('click');
      const applyLotIntent = () =>
        workspace!.wrapper
          .findAll('button')
          .find((button) => button.text().includes('Apply complete set to current DEMO run'));
      expect(applyLotIntent()).toBeDefined();
      await applyLotIntent()!.trigger('click');
      await flushPromises();
      await waitFor(
        () =>
          Boolean(
            useWorkspaceStore(workspace!.pinia)
              .currentRun?.consolidated_legs.find((leg) => leg.side === 'SELL')
              ?.selected_lots.some((lot) => lot.broker_lot_id === 'DEMO-VB-LOT-1' && lot.selected),
          ),
        'successful full lot-intent DEMO re-solve',
      );
      expect(JSON.parse(lotIntentBodies[0]!)).toEqual({
        source_generation: run!.source_generation,
        broker_lot_ids: ['DEMO-VB-LOT-1'],
      });
      const confirmedAfterValidIntent = store.currentRun;
      await waitFor(() => !store.reviewMutationPending, 'lot intent mutation queue release');

      const aaplLotLabel = 'Request AAPL lot DEMO-AAPL-LOT-1';
      await waitFor(
        () => workspace!.wrapper.find(`[role="checkbox"][aria-label="${aaplLotLabel}"]`).exists(),
        'AAPL current lot row',
      );
      await workspace.wrapper
        .get(`[role="checkbox"][aria-label="${aaplLotLabel}"]`)
        .trigger('click');
      await waitFor(
        () => store.lotReviewIntent.length === 2 && !store.reviewMutationPending,
        'complete desired set after adding unsupported AAPL lot',
      );
      const rejectedApplyButton = applyLotIntent();
      expect(rejectedApplyButton).toBeDefined();
      await rejectedApplyButton!.trigger('click');
      await flushPromises();
      await waitFor(
        () => Boolean(store.actionState.applyLotReviewIntent.error),
        'atomic unsupported lot-intent rejection',
      );
      expect(JSON.parse(lotIntentBodies[1]!)).toEqual({
        source_generation: run!.source_generation,
        broker_lot_ids: ['DEMO-VB-LOT-1', 'DEMO-AAPL-LOT-1'],
      });
      expect(store.currentRun).toEqual(confirmedAfterValidIntent);
      expect(workspace.wrapper.text()).toContain('lot_review_intent_rejected');
      expect(workspace.wrapper.text()).toContain('outside_saved_demo_candidates');
      expect(workspace.wrapper.text()).toContain('rejected the complete request atomically');
      const persistedRecommendations = (await (
        await fetch(`${backendBase}/api/v1/optimizer/runs/${run!.run_id}/recommendations`)
      ).json()) as OptimizerRecommendationsResponse;
      expect(
        persistedRecommendations.consolidated_legs
          .filter((leg) => leg.side === 'SELL')
          .flatMap((leg) =>
            leg.selected_lots.filter((lot) => lot.selected).map((lot) => lot.broker_lot_id),
          ),
      ).toEqual(['DEMO-VB-LOT-1']);
      await visit(workspace, '/recommendations');
      Object.defineProperty(URL, 'createObjectURL', {
        configurable: true,
        value: (blob: Blob) => {
          downloads.push(blob);
          return `blob:stage-e-${downloads.length}`;
        },
      });
      Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: () => undefined });
      vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
      for (const format of ['json', 'csv'] as const) {
        const exportButton = workspace.wrapper
          .findAll('button')
          .find((button) => button.text() === `Export ${format.toUpperCase()}`);
        expect(exportButton).toBeDefined();
        await exportButton!.trigger('click');
        await waitFor(
          () => downloads.length === (format === 'json' ? 1 : 2),
          `real ${format.toUpperCase()} export response`,
        );
      }
      expect(downloads).toHaveLength(2);
      const jsonExport = JSON.parse(await downloads[0]!.text()) as {
        metadata: { run_id: string; demo: boolean; actionable: boolean };
        run: { consolidated_legs: Array<{ side: string }> };
      };
      expect(jsonExport.metadata).toMatchObject({
        run_id: run!.run_id,
        demo: true,
        actionable: false,
      });
      expect(jsonExport.run.consolidated_legs.some((leg) => leg.side === 'BUY')).toBe(true);
      const csvExport = await downloads[1]!.text();
      expect(csvExport).toContain('run_id,record_type');
      expect(csvExport).toContain(run!.run_id);
      expect(csvExport).toContain('DEMO-VB-LOT-1');
      expect(requests).toContain(`GET /api/v1/optimizer/runs/${run!.run_id}/export?format=json`);
      const rejectionPanel = workspace.wrapper.get(
        `[aria-label="Notes and rejection for ${groupId}"]`,
      );
      await rejectionPanel.get('input').setValue('Integration rejection reason');
      const selectionRequestCount = requests.filter((request) =>
        request.includes('/selection'),
      ).length;
      await rejectionPanel
        .findAll('button')
        .find((button) => button.text().includes('Reject group'))!
        .trigger('click');
      await flushPromises();
      await waitFor(
        () =>
          store.currentRun?.groups.find((group) => group.group_id === groupId)?.rejected === true,
        'atomic full-run annotation PATCH response',
      );
      expect(requests).toContain(
        `PATCH /api/v1/optimizer/runs/${run!.run_id}/recommendations/${groupId}`,
      );
      expect(requests.filter((request) => request.includes('/selection'))).toHaveLength(
        selectionRequestCount,
      );
      expect(store.currentRun?.groups.find((group) => group.group_id === groupId)).toMatchObject({
        rejected: true,
        selected: false,
        rejection_reason: 'Integration rejection reason',
      });
      expect(store.currentRun?.orders_count).toBe(0);
      expect(annotationBodies).toHaveLength(1);
      expect(JSON.parse(annotationBodies[0]!)).toEqual({
        rejected: true,
        rejection_reason: 'Integration rejection reason',
      });
      const restorePanel = workspace.wrapper.get(
        `[aria-label="Notes and rejection for ${groupId}"]`,
      );
      await restorePanel
        .findAll('button')
        .find((button) => button.text().includes('Restore rejected group'))!
        .trigger('click');
      await flushPromises();
      await waitFor(() => {
        const group = store.currentRun?.groups.find((item) => item.group_id === groupId);
        return group?.rejected === false && group.rejection_reason === null;
      }, 'real rejected-group restore PATCH response');
      expect(annotationBodies).toHaveLength(2);
      expect(JSON.parse(annotationBodies[1]!)).toEqual({ rejected: false });
      expect(requests.filter((request) => request.includes('/selection'))).toHaveLength(
        selectionRequestCount,
      );
      expect(store.currentRun?.groups.find((group) => group.group_id === groupId)).toMatchObject({
        rejected: false,
        selected: false,
        rejection_reason: null,
      });
      expect(requests).toContain(`GET /api/v1/optimizer/runs/${run!.run_id}/export?format=csv`);
    } finally {
      releaseWrite.draft?.();
      releaseWrite.activation?.();
      workspace?.wrapper.unmount();
      await backend?.stop();
      rmSync(tempDirectory, { recursive: true, force: true });
      expect(existsSync(tempDirectory), 'isolated SQLite temp directory removed').toBe(false);
      if (urlDescriptors.create)
        Object.defineProperty(URL, 'createObjectURL', urlDescriptors.create);
      else Reflect.deleteProperty(URL, 'createObjectURL');
      if (urlDescriptors.revoke)
        Object.defineProperty(URL, 'revokeObjectURL', urlDescriptors.revoke);
      else Reflect.deleteProperty(URL, 'revokeObjectURL');
    }
  }, 120_000);
});

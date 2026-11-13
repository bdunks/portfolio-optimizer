// @vitest-environment jsdom
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createPinia, getActivePinia, setActivePinia } from 'pinia';
import { createMemoryHistory, createRouter } from 'vue-router';
import { Select } from '@/components/ui/select';
import { workspaceQueryKeys } from '@/composables/queries/workspace-queries';
import { mountWorkspaceHarness } from '@/test-utils/workspace-harness';
import { getTestQueryClientForPinia } from '@/test-utils/workspace-mount';
import type {
  ActivityEventResponse,
  ActivityPageResponse,
  FrozenRunDisplayContextResponse,
  OptimizerRecommendationsResponse,
  OptimizerRunResponse,
} from '@/types/api';
import ActivityPage from './ActivityPage.vue';

const frozenDisplayContext: FrozenRunDisplayContextResponse = {
  available: true,
  source: 'policy_revision',
  policy_revision_id: 'policy-synthetic',
  revision_number: 4,
  created_at: '2024-01-01T00:00:00Z',
  activated_at: '2024-01-02T00:00:00Z',
  sleeves: [
    {
      sleeve_key: 'us',
      display_name: 'Historical US equity',
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
  run_id: 'saved-run-synthetic',
  status: 'demo',
  mode: 'recommendations_only',
  policy_revision_id: 'policy-synthetic',
  source_generation: 7,
  as_of: '2025-02-01T12:00:00Z',
  solver_version: 'DEMO',
  demo: true,
  actionable: false,
  input_fingerprint: 'synthetic-input-fingerprint',
  source_checksum: null,
  batch_settings: { max_sell_tickers_per_batch: 2, loss_budget_usd: '25.00' },
  estimated_realized_st_usd: '-20.00',
  estimated_realized_lt_usd: '0.00',
  estimated_tax_benefit_usd: null,
  estimated_tax_benefit_status: 'tax_profile_incomplete',
  lots_sold_count: 1,
  positions_exited_count: 0,
  orders_count: 1,
  cash_before_usd: '100.00',
  cash_after_usd: '80.00',
  portfolio_effects: null,
  constraints_satisfied: null,
  no_trade_reason: null,
  warnings: ['Synthetic saved-run warning'],
  tax_profile_configured: false,
  frozen_display_context: frozenDisplayContext,
};

const savedRecommendations: OptimizerRecommendationsResponse = {
  ...savedRun,
  groups: [],
  consolidated_legs: [],
};

const runEvent: ActivityEventResponse = {
  id: 'event-run-synthetic',
  created_at: '2025-02-01T12:01:00Z',
  event_type: 'optimizer_run',
  status: 'complete',
  correlation_id: 'correlation-synthetic',
  details: { run_id: 'saved-run-synthetic', policy_revision_id: 'policy-synthetic' },
};

const errorEvent: ActivityEventResponse = {
  id: 'event-error-synthetic',
  created_at: '2025-02-01T12:02:00Z',
  event_type: 'sync',
  status: 'error',
  correlation_id: 'correlation-error-synthetic',
  details: { error_code: 'synthetic_sync_error', error_summary: 'Synthetic failure detail' },
};

function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function requestUrl(input: RequestInfo | URL): URL {
  const address =
    typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
  return new URL(address, 'http://127.0.0.1:9000');
}

function activityPage(
  items: ActivityEventResponse[],
  total = items.length,
  offset = 0,
  limit = 25,
): ActivityPageResponse {
  return { items, total, offset, limit };
}

function testRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/activity', component: ActivityPage },
      {
        path: '/recommendations',
        component: { template: '<div>Recommendations placeholder</div>' },
      },
    ],
  });
}

const mountedPages: VueWrapper[] = [];

beforeEach(() => {
  vi.unstubAllGlobals();
  setActivePinia(createPinia());
  mountWorkspaceHarness();
});

afterEach(() => {
  mountedPages.splice(0).forEach((wrapper) => wrapper.unmount());
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

async function mountActivityPage() {
  const router = testRouter();
  await router.push('/activity');
  await router.isReady();
  const wrapper = mount(ActivityPage, { global: { plugins: [router] } });
  mountedPages.push(wrapper);
  await flushPromises();
  return { router, wrapper };
}

async function setPageLimit(wrapper: VueWrapper, limit: number): Promise<void> {
  const select = wrapper.findComponent(Select);
  if (!select.exists()) throw new Error('Activity page-size select was not found');
  select.vm.$emit('update:modelValue', String(limit));
  await flushPromises();
}

async function refreshActivity(wrapper: VueWrapper): Promise<void> {
  const refreshButton = wrapper
    .findAll('button')
    .find((button) => button.text().trim() === 'Refresh activity');
  if (!refreshButton) throw new Error('Activity refresh button was not found');
  await refreshButton.trigger('click');
  await flushPromises();
}

describe('ActivityPage', () => {
  it('filters API events, preserves server pagination, and clears to the first 25-row page', async () => {
    vi.stubEnv('TZ', 'America/Los_Angeles');
    expect(new Date('2025-02-01T00:00:00').getTimezoneOffset()).toBe(480);
    const fetcher = vi.fn<typeof fetch>((input) => {
      const url = requestUrl(input);
      const offset = Number(url.searchParams.get('offset') ?? '0');
      const limit = Number(url.searchParams.get('limit') ?? '25');
      const responseOffset = offset === 50 ? 51 : offset;
      return Promise.resolve(jsonResponse(activityPage([runEvent], 51, responseOffset, limit)));
    });
    vi.stubGlobal('fetch', fetcher);
    const { wrapper } = await mountActivityPage();

    expect(wrapper.get('.workspace-page').classes()).toContain('activity-page');
    expect(wrapper.get('form[aria-label="Activity filters"]')).toBeDefined();
    expect(wrapper.get('input[type="datetime-local"]#activity-since').attributes('step')).toBe(
      'any',
    );
    expect(wrapper.get('li > .event-card').element.tagName).toBe('DIV');
    expect(wrapper.get('[aria-label="Activity events"]').element.tagName).toBe('OL');
    expect(wrapper.get('[data-slot="badge"]').attributes('data-variant')).toBe('secondary');

    await wrapper.get('#activity-event-type').setValue(' optimizer_run ');
    await wrapper.get('#activity-status').setValue(' complete ');
    await wrapper.get('#activity-correlation-id').setValue(' correlation-synthetic ');
    await wrapper.get('#activity-since').setValue('2025-02-01T00:00');
    await setPageLimit(wrapper, 50);
    await wrapper.get('form[aria-label="Activity filters"]').trigger('submit');
    await flushPromises();

    const filtered = requestUrl(fetcher.mock.calls[1]![0]);
    expect(filtered.searchParams.get('event_type')).toBe('optimizer_run');
    expect(filtered.searchParams.get('status')).toBe('complete');
    expect(filtered.searchParams.get('correlation_id')).toBe('correlation-synthetic');
    expect(filtered.searchParams.get('since')).toBe('2025-02-01T00:00:00Z');
    expect(filtered.searchParams.get('limit')).toBe('50');
    expect(wrapper.text()).toContain('page 1 of 2');

    await wrapper.get('button[aria-label="Next page"]').trigger('click');
    await flushPromises();
    const nextPageRequest = requestUrl(fetcher.mock.calls[2]![0]);
    expect(nextPageRequest.searchParams.get('offset')).toBe('50');
    expect(nextPageRequest.searchParams.get('limit')).toBe('50');
    expect(wrapper.text()).toContain('page 2 of 2');

    await refreshActivity(wrapper);
    const refreshRequest = requestUrl(fetcher.mock.calls[3]![0]);
    expect(refreshRequest.searchParams.get('offset')).toBe('51');

    const clearFiltersButton = wrapper
      .findAll('button')
      .find((button) => button.text() === 'Clear filters');
    expect(clearFiltersButton).toBeDefined();
    await clearFiltersButton!.trigger('click');
    await flushPromises();
    const clearRequest = requestUrl(fetcher.mock.calls[4]![0]);
    expect(clearRequest.searchParams.get('offset')).toBe('0');
    expect(clearRequest.searchParams.get('limit')).toBe('25');
    expect(clearRequest.searchParams.has('event_type')).toBe(false);
    expect(clearRequest.searchParams.has('status')).toBe(false);
    expect(clearRequest.searchParams.has('correlation_id')).toBe(false);
    expect(clearRequest.searchParams.has('since')).toBe(false);
    expect(clearRequest.searchParams.has('until')).toBe(false);
  });

  it('restores saved filters and UTC date inputs while preserving unedited offset bounds verbatim', async () => {
    vi.stubEnv('TZ', 'America/Los_Angeles');
    const { workspace } = mountWorkspaceHarness();
    const savedSince = '2025-02-01T00:00:00.987+05:30';
    const savedUntil = '2025-02-03T12:30:45.123456-07:00';
    workspace.activityFilters = {
      event_type: 'sync',
      status: 'failed',
      correlation_id: 'restored-correlation',
      since: savedSince,
      until: savedUntil,
      offset: 25,
      limit: 50,
    };
    const fetcher = vi.fn<typeof fetch>((input) => {
      const url = requestUrl(input);
      const offset = Number(url.searchParams.get('offset') ?? '0');
      const limit = Number(url.searchParams.get('limit') ?? '25');
      return Promise.resolve(jsonResponse(activityPage([runEvent], 51, offset, limit)));
    });
    vi.stubGlobal('fetch', fetcher);
    const { wrapper } = await mountActivityPage();

    expect([
      (wrapper.get('#activity-event-type').element as HTMLInputElement).value,
      (wrapper.get('#activity-status').element as HTMLInputElement).value,
      (wrapper.get('#activity-correlation-id').element as HTMLInputElement).value,
    ]).toEqual(['sync', 'failed', 'restored-correlation']);
    expect([
      (wrapper.get('#activity-since').element as HTMLInputElement).value,
      (wrapper.get('#activity-until').element as HTMLInputElement).value,
    ]).toEqual(['2025-01-31T18:30:00.987', '2025-02-03T19:30:45.123']);
    expect(wrapper.get('button[aria-label="Rows per page"]').text()).toContain('50');
    expect(wrapper.text()).toContain('Since (UTC)');
    expect(wrapper.text()).toContain('Until (UTC)');

    const restoredRequest = requestUrl(fetcher.mock.calls[0]![0]);
    expect(restoredRequest.searchParams.get('event_type')).toBe('sync');
    expect(restoredRequest.searchParams.get('status')).toBe('failed');
    expect(restoredRequest.searchParams.get('correlation_id')).toBe('restored-correlation');
    expect(restoredRequest.searchParams.get('since')).toBe(savedSince);
    expect(restoredRequest.searchParams.get('until')).toBe(savedUntil);
    expect(restoredRequest.searchParams.get('offset')).toBe('25');
    expect(restoredRequest.searchParams.get('limit')).toBe('50');

    await wrapper.get('#activity-since').setValue('2025-02-02T08:09');
    await wrapper.get('form[aria-label="Activity filters"]').trigger('submit');
    await flushPromises();
    const editedRequest = requestUrl(fetcher.mock.calls[1]![0]);
    expect(editedRequest.searchParams.get('since')).toBe('2025-02-02T08:09:00Z');
    expect(editedRequest.searchParams.get('until')).toBe(savedUntil);
  });

  it('reopens only a qualifying saved optimizer run through the store and exposes the returned read-only summary', async () => {
    const arrayDetailsEvent: ActivityEventResponse = {
      ...runEvent,
      id: 'event-array-details',
      details: ['saved-run-synthetic'],
    };
    const emptyRunIdEvent: ActivityEventResponse = {
      ...runEvent,
      id: 'event-empty-run-id',
      details: { run_id: '' },
    };
    const otherEventType: ActivityEventResponse = {
      ...runEvent,
      id: 'event-other-type',
      event_type: 'optimizer_run_saved',
    };
    const events = [arrayDetailsEvent, emptyRunIdEvent, otherEventType, runEvent];
    const fetcher = vi.fn<typeof fetch>((input) => {
      const url = requestUrl(input);
      if (url.pathname === '/api/v1/activity') {
        return Promise.resolve(jsonResponse(activityPage(events)));
      }
      if (url.pathname === '/api/v1/optimizer/runs/saved-run-synthetic') {
        return Promise.resolve(jsonResponse(savedRun));
      }
      if (url.pathname === '/api/v1/optimizer/runs/saved-run-synthetic/recommendations') {
        return Promise.resolve(jsonResponse(savedRecommendations));
      }
      return Promise.reject(new Error(`Unhandled local API request: ${url.pathname}`));
    });
    vi.stubGlobal('fetch', fetcher);
    const { workspace, queryClient } = mountWorkspaceHarness();
    const pinia = getActivePinia();
    if (!pinia) throw new Error('ActivityPage test has no active Pinia instance');
    getTestQueryClientForPinia(pinia).setQueryData(workspaceQueryKeys.policy, {
      active: {
        id: 'policy-current',
        sleeves: [{ sleeve_key: 'us', display_name: 'Current US renamed' }],
      },
      drafts: [],
      superseded: [],
    });
    expect(workspace).toBeDefined();
    expect(queryClient).toBeDefined();
    const { router, wrapper } = await mountActivityPage();

    expect(wrapper.findAll('button.reopen-button')).toHaveLength(1);
    expect(
      wrapper.findAll('button').some((button) => /order preview|submit order/i.test(button.text())),
    ).toBe(false);
    await wrapper.get('button.reopen-button').trigger('click');
    await flushPromises();

    expect(router.currentRoute.value.path).toBe('/recommendations');
    expect(wrapper.text()).toContain('Saved run summary and frozen settings');
    expect(wrapper.text()).toContain('policy-synthetic');
    const summaryCard = wrapper.get('.run-summary');
    expect(summaryCard.text()).toContain('Historical US equity');
    expect(summaryCard.text()).toContain('63.0000%');
    expect(summaryCard.text()).toContain('3210.00');
    expect(summaryCard.text()).not.toContain('Current US renamed');
    expect(workspace.currentRunSummary?.frozen_display_context).toEqual(frozenDisplayContext);
    expect(wrapper.text()).toContain('loss_budget_usd');
    expect(wrapper.text()).toContain('25.00');
    expect(wrapper.text()).toContain('Synthetic saved-run warning');
    expect(
      fetcher.mock.calls.some(([input]) => requestUrl(input).pathname.includes('/orders/')),
    ).toBe(false);
  });

  it('shows raw error details, retries a failed API request, and reports an empty response', async () => {
    let calls = 0;
    const fetcher = vi.fn<typeof fetch>(() => {
      calls += 1;
      if (calls === 1) {
        return Promise.resolve(
          jsonResponse(
            {
              code: 'activity_unavailable',
              message: 'Synthetic activity API error',
              details: {},
              correlation_id: 'activity-test-correlation',
            },
            503,
          ),
        );
      }
      if (calls === 2) return Promise.resolve(jsonResponse(activityPage([errorEvent])));
      return Promise.resolve(jsonResponse(activityPage([], 0)));
    });
    vi.stubGlobal('fetch', fetcher);
    const { wrapper } = await mountActivityPage();

    expect(wrapper.text()).toContain('activity_unavailable');
    expect(wrapper.text()).toContain('Synthetic activity API error');
    await refreshActivity(wrapper);
    expect(wrapper.text()).toContain('Synthetic failure detail');
    const errorStatus = wrapper.get('[data-slot="badge"]');
    expect(errorStatus.attributes('role')).toBe('status');
    expect(errorStatus.attributes('data-variant')).toBe('destructive');
    expect(wrapper.get('time').text()).toBe(errorEvent.created_at);
    expect(wrapper.text()).toContain(errorEvent.correlation_id);

    await refreshActivity(wrapper);
    expect(wrapper.text()).toContain('No activity events returned');
    expect(calls).toBe(3);
  });

  it('presents supported and unknown event summaries while common filters retain exact API codes', async () => {
    const events: ActivityEventResponse[] = [
      { ...errorEvent, details: { code: 'sync_failed', message: 'Snapshot unavailable' } },
      { ...runEvent, id: 'unknown-event', event_type: 'future_event_kind', details: null },
      {
        ...runEvent,
        id: 'constructor-event',
        event_type: 'constructor',
        status: 'constructor',
        details: {},
      },
      {
        ...runEvent,
        id: 'to-string-event',
        event_type: 'toString',
        status: 'toString',
        details: {},
      },
      {
        ...runEvent,
        id: 'pending-sync',
        event_type: 'sync',
        status: 'pending',
        details: { generation: 9 },
      },
      {
        ...runEvent,
        id: 'unknown-status-sync',
        event_type: 'sync',
        status: 'queued',
        details: {},
      },
      {
        ...runEvent,
        id: 'pending-policy',
        event_type: 'policy_activation',
        status: 'pending',
        details: { revision_number: 8 },
      },
      {
        ...runEvent,
        id: 'pending-selection',
        event_type: 'recommendation_selection',
        status: 'pending',
        details: { selected_group_ids: ['group-1'] },
      },
    ];
    const fetcher = vi.fn<typeof fetch>(() => Promise.resolve(jsonResponse(activityPage(events))));
    vi.stubGlobal('fetch', fetcher);
    const { wrapper } = await mountActivityPage();

    expect(wrapper.text()).toContain('Portfolio sync');
    expect(wrapper.text()).toContain('Snapshot unavailable · Code: sync_failed');
    expect(wrapper.text()).toContain('API event: sync');
    expect(wrapper.text()).toContain('API event: future_event_kind');
    expect(wrapper.text()).toContain('constructor-event');
    expect(wrapper.text()).toContain('API event: constructor');
    expect(wrapper.text()).toContain('Other activity event');
    expect(wrapper.text()).toContain('constructor');
    expect(wrapper.text()).toContain('toString');
    expect(wrapper.text()).toContain('pending-sync');
    expect(wrapper.text()).toContain(
      'Activity recorded; see the returned details for information.',
    );
    expect(wrapper.text()).not.toContain('Portfolio sync completed for generation 9');
    expect(wrapper.text()).not.toContain('Policy revision 8 was activated');
    expect(wrapper.text()).not.toContain('Recommendation selection updated');
    expect(wrapper.text()).toContain('additional details were not returned');
    await wrapper.get('details summary').trigger('click');
    expect(wrapper.text()).toContain('"message": "Snapshot unavailable"');

    await wrapper.get('#activity-common-event-type').setValue('recommendation_selection');
    await wrapper.get('form[aria-label="Activity filters"]').trigger('submit');
    await flushPromises();
    expect(requestUrl(fetcher.mock.calls[1]![0]).searchParams.get('event_type')).toBe(
      'recommendation_selection',
    );
  });

  it('announces loading politely and then presents the empty result', async () => {
    let resolveActivity!: (response: Response) => void;
    const fetcher = vi.fn<typeof fetch>(
      () =>
        new Promise<Response>((resolve) => {
          resolveActivity = resolve;
        }),
    );
    vi.stubGlobal('fetch', fetcher);
    const { wrapper } = await mountActivityPage();

    const loadingAlert = wrapper
      .findAll('[role="status"]')
      .find((notice) => notice.text().includes('Loading activity from the local API'));
    expect(loadingAlert?.attributes('aria-live')).toBe('polite');
    expect(loadingAlert?.text()).toContain('Loading activity from the local API');

    resolveActivity(jsonResponse(activityPage([], 0)));
    await flushPromises();
    expect(
      wrapper
        .findAll('[role="status"]')
        .some((notice) => notice.text().includes('Loading activity from the local API')),
    ).toBe(false);
    const emptyState = wrapper
      .findAll('[role="status"]')
      .find((notice) => notice.text().includes('No activity events returned'));
    expect(emptyState).toBeDefined();
    expect(emptyState?.attributes('aria-live')).toBe('polite');
  });
});

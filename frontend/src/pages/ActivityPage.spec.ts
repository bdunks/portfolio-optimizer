// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';
import { createMemoryHistory, createRouter } from 'vue-router';
import type {
  ActivityEventResponse,
  ActivityPageResponse,
  OptimizerRecommendationsResponse,
  OptimizerRunResponse,
} from '@/types/api';
import ActivityPage from './ActivityPage.vue';
import { useWorkspaceStore } from '@/stores/workspace-store';

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

beforeEach(() => {
  vi.unstubAllGlobals();
  setActivePinia(createPinia());
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe('ActivityPage', () => {
  it('filters API events and paginates by the returned page limit', async () => {
    vi.stubEnv('TZ', 'America/Los_Angeles');
    expect(new Date('2025-02-01T00:00:00').getTimezoneOffset()).toBe(480);
    const fetcher = vi.fn<typeof fetch>((input) => {
      const url = requestUrl(input);
      const offset = Number(url.searchParams.get('offset') ?? '0');
      const limit = Number(url.searchParams.get('limit') ?? '25');
      return Promise.resolve(jsonResponse(activityPage([runEvent], 51, offset, limit)));
    });
    vi.stubGlobal('fetch', fetcher);
    const router = testRouter();
    await router.push('/activity');
    await router.isReady();
    const wrapper = mount(ActivityPage, { global: { plugins: [router] } });
    await flushPromises();
    expect(wrapper.get('.workspace-page').classes()).toContain('activity-page');

    const searchInputs = wrapper.findAll('input[type="search"]');
    await searchInputs[0]!.setValue('optimizer_run');
    await searchInputs[1]!.setValue('complete');
    await searchInputs[2]!.setValue('correlation-synthetic');
    await wrapper.find('input[type="datetime-local"]').setValue('2025-02-01T00:00');
    await wrapper.findAll('select')[0]!.setValue('50');
    await wrapper.get('form').trigger('submit');
    await flushPromises();

    const filtered = requestUrl(fetcher.mock.calls[1]![0]);
    expect(filtered.searchParams.get('event_type')).toBe('optimizer_run');
    expect(filtered.searchParams.get('status')).toBe('complete');
    expect(filtered.searchParams.get('correlation_id')).toBe('correlation-synthetic');
    expect(filtered.searchParams.get('since')).toBe('2025-02-01T00:00:00Z');
    expect(filtered.searchParams.get('limit')).toBe('50');
    expect(wrapper.text()).toContain('page 1 of 2');

    await wrapper
      .findAll('button')
      .find((button) => button.text().includes('Next page'))!
      .trigger('click');
    await flushPromises();
    const nextPageRequest = requestUrl(fetcher.mock.calls[2]![0]);
    expect(nextPageRequest.searchParams.get('offset')).toBe('50');
    expect(nextPageRequest.searchParams.get('limit')).toBe('50');
  });

  it('restores saved filters and datetime inputs when the page is remounted', async () => {
    const store = useWorkspaceStore();
    store.activityFilters = {
      event_type: 'sync',
      status: 'failed',
      correlation_id: 'restored-correlation',
      since: '2025-02-01T00:00:00Z',
      until: '2025-02-03T12:30:45.123Z',
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
    const router = testRouter();
    await router.push('/activity');
    await router.isReady();
    const wrapper = mount(ActivityPage, { global: { plugins: [router] } });
    await flushPromises();

    const searchInputs = wrapper.findAll('input[type="search"]');
    expect(searchInputs.map((input) => (input.element as HTMLInputElement).value)).toEqual([
      'sync',
      'failed',
      'restored-correlation',
    ]);
    const dateInputs = wrapper.findAll('input[type="datetime-local"]');
    expect(dateInputs.map((input) => (input.element as HTMLInputElement).value)).toEqual([
      '2025-02-01T00:00',
      '2025-02-03T12:30:45.123',
    ]);
    expect((wrapper.findAll('select')[0]!.element as HTMLSelectElement).value).toBe('50');
    expect(wrapper.text()).toContain('Since (UTC)');
    expect(wrapper.text()).toContain('Until (UTC)');

    const restoredRequest = requestUrl(fetcher.mock.calls[0]![0]);
    expect(restoredRequest.searchParams.get('event_type')).toBe('sync');
    expect(restoredRequest.searchParams.get('status')).toBe('failed');
    expect(restoredRequest.searchParams.get('correlation_id')).toBe('restored-correlation');
    expect(restoredRequest.searchParams.get('since')).toBe('2025-02-01T00:00:00Z');
    expect(restoredRequest.searchParams.get('until')).toBe('2025-02-03T12:30:45.123Z');
    expect(restoredRequest.searchParams.get('offset')).toBe('25');
    expect(restoredRequest.searchParams.get('limit')).toBe('50');
  });

  it('reopens a saved optimizer run through the store and exposes only returned summary settings', async () => {
    const fetcher = vi.fn<typeof fetch>((input) => {
      const url = requestUrl(input);
      if (url.pathname === '/api/v1/activity') {
        return Promise.resolve(jsonResponse(activityPage([runEvent])));
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
    const router = testRouter();
    await router.push('/activity');
    await router.isReady();
    const wrapper = mount(ActivityPage, { global: { plugins: [router] } });
    await flushPromises();

    expect(wrapper.findAll('button.reopen-button')).toHaveLength(1);
    await wrapper.get('button.reopen-button').trigger('click');
    await flushPromises();

    expect(router.currentRoute.value.path).toBe('/recommendations');
    expect(wrapper.text()).toContain('Saved run summary and frozen settings');
    expect(wrapper.text()).toContain('policy-synthetic');
    expect(wrapper.text()).toContain('loss_budget_usd');
    expect(wrapper.text()).toContain('25.00');
    expect(wrapper.text()).toContain('Synthetic saved-run warning');
    expect(
      fetcher.mock.calls.some(([input]) => requestUrl(input).pathname.includes('/orders/')),
    ).toBe(false);
  });

  it('shows event error details, retries an API failure, and reports an empty response', async () => {
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
    const router = testRouter();
    await router.push('/activity');
    await router.isReady();
    const wrapper = mount(ActivityPage, { global: { plugins: [router] } });
    await flushPromises();

    expect(wrapper.text()).toContain('activity_unavailable');
    expect(wrapper.text()).toContain('Synthetic activity API error');
    await wrapper.get('button').trigger('click');
    await flushPromises();
    expect(wrapper.text()).toContain('Synthetic failure detail');
    expect(wrapper.text()).toContain('error');
    await wrapper.get('button.primary-button').trigger('click');
    await flushPromises();
    expect(wrapper.text()).toContain('No activity events returned');
    expect(calls).toBe(3);
  });
});

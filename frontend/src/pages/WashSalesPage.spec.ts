// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';
import type { WashSalesResponse } from '@/types/api';
import WashSalesPage from './WashSalesPage.vue';

const response: WashSalesResponse = {
  demo: true,
  source: 'synthetic-test-source',
  history: [
    {
      broker_transaction_key: 'TX-BUY-1',
      ticker: 'SYN',
      transaction_kind: 'BUY',
      trade_date: '2025-01-04',
      transaction_time: '2025-01-04T14:30:00Z',
      shares: '1.2500',
      source: 'synthetic-history',
      is_acquisition: true,
    },
    {
      broker_transaction_key: 'TX-SELL-2',
      ticker: 'SYN',
      transaction_kind: 'SELL',
      trade_date: '2025-02-10',
      transaction_time: '2025-02-10T14:30:00Z',
      shares: '0.5000',
      source: 'synthetic-history',
      is_acquisition: false,
    },
  ],
  acquisitions: [
    {
      broker_transaction_key: 'TX-BUY-1',
      ticker: 'SYN',
      transaction_kind: 'BUY',
      trade_date: '2025-01-04',
      transaction_time: '2025-01-04T14:30:00Z',
      shares: '1.2500',
      source: 'synthetic-history',
      is_acquisition: true,
      lookback_window_end_date: '2025-02-03',
    },
  ],
  current_restrictions: [
    {
      ticker: 'SYN',
      trigger: 'synthetic-current-loss',
      loss_sale_date: '2025-02-10',
      source: 'synthetic-current-source',
      next_eligible_purchase_date: '2025-03-13',
      validation: 'synthetic-current-validation',
    },
  ],
  proposed_restrictions: [
    {
      run_id: 'run-synthetic-1',
      ticker: 'SYN',
      trigger: 'synthetic-proposed-loss',
      loss_sale_date: '2025-02-11',
      source: 'synthetic-proposed-source',
      next_eligible_purchase_date: '2025-03-14',
      validation: 'synthetic-not-live-validated',
    },
  ],
  warnings: ['Synthetic coverage warning; no live validation.'],
};

function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

beforeEach(() => {
  vi.unstubAllGlobals();
  setActivePinia(createPinia());
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('WashSalesPage', () => {
  it('renders API history, current and proposed restrictions, next eligible dates, and coverage limits', async () => {
    const fetcher = vi.fn<typeof fetch>(() => Promise.resolve(jsonResponse(response)));
    vi.stubGlobal('fetch', fetcher);
    const wrapper = mount(WashSalesPage);
    await flushPromises();

    expect(wrapper.text()).toContain('synthetic-test-source');
    expect(wrapper.text()).toContain('TX-BUY-1');
    expect(wrapper.text()).toContain('2025-02-03');
    expect(wrapper.text()).toContain('Current');
    expect(wrapper.text()).toContain('Proposed');
    expect(wrapper.text()).toContain('2025-03-14');
    expect(wrapper.text()).toContain('Synthetic coverage warning; no live validation.');
    expect(wrapper.text()).toContain('affected tax-lot IDs are not included');
    expect(wrapper.text()).toContain('DEMO ONLY');

    await wrapper.find('input[type="search"]').setValue('synthetic-proposed-loss');
    expect(wrapper.text()).toContain('synthetic-proposed-loss');
    expect(wrapper.text()).not.toContain('synthetic-current-loss');
  });

  it('filters transaction history by kind without changing API-supplied decimal quantities', async () => {
    const fetcher = vi.fn<typeof fetch>(() => Promise.resolve(jsonResponse(response)));
    vi.stubGlobal('fetch', fetcher);
    const wrapper = mount(WashSalesPage);
    await flushPromises();

    await wrapper.find('select').setValue('BUY');
    expect(wrapper.text()).toContain('1.2500');
    expect(wrapper.text()).not.toContain('TX-SELL-2');
  });

  it('reports request errors, retries, and displays explicit empty states', async () => {
    let calls = 0;
    const emptyResponse: WashSalesResponse = {
      demo: true,
      source: 'synthetic-empty-source',
      history: [],
      acquisitions: [],
      current_restrictions: [],
      proposed_restrictions: [],
      warnings: [],
    };
    const fetcher = vi.fn<typeof fetch>(() => {
      calls += 1;
      if (calls === 1) {
        return Promise.resolve(
          jsonResponse(
            {
              code: 'wash_unavailable',
              message: 'Synthetic wash API error',
              details: {},
              correlation_id: 'wash-test-correlation',
            },
            503,
          ),
        );
      }
      return Promise.resolve(jsonResponse(emptyResponse));
    });
    vi.stubGlobal('fetch', fetcher);
    const wrapper = mount(WashSalesPage);
    await flushPromises();

    expect(wrapper.text()).toContain('wash_unavailable');
    expect(wrapper.text()).toContain('Synthetic wash API error');
    await wrapper.get('button').trigger('click');
    await flushPromises();
    expect(wrapper.text()).toContain('The API returned no transaction-history rows.');
    expect(wrapper.text()).toContain('The API returned no current or proposed restrictions.');
    expect(calls).toBe(2);
  });
});

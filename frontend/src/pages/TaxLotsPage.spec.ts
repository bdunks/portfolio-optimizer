// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';
import type { LotResponse } from '@/types/api';
import TaxLotsPage from './TaxLotsPage.vue';

const lot: LotResponse = {
  ticker: 'SYN',
  asset_type: 'EQUITY',
  broker_lot_id: 'BROKER-LOT-0007',
  acquired_date: '2025-02-03',
  remaining_shares: '1.2500',
  available_shares: '1.2500',
  adjusted_unit_basis_usd: '123.4500',
  adjusted_total_basis_usd: '154.3125',
  current_price_usd: '130.0000',
  unrealized_pl_usd: '8.1875',
  unrealized_pl_pct: '5.3099',
  source: 'synthetic-test-source',
  as_of: '2025-02-04T12:00:00Z',
  term: 'LT',
  sleeve_key: 'synthetic-sleeve',
  sub_sleeve_key: null,
  quality_flags: ['synthetic-quality-flag'],
  small_lot_cleanup_candidate: false,
  position_cleanup_candidate: true,
  whole_shares_available: '1',
  fractional_shares: '0.2500',
  fractional_cleanup_unsupported: true,
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

function page(items: LotResponse[], offset = 0, total = items.length) {
  return { items, total, offset, limit: 100 };
}

beforeEach(() => {
  vi.unstubAllGlobals();
  setActivePinia(createPinia());
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('TaxLotsPage', () => {
  it('renders exact API lot values, groups by security, and marks lots for review only', async () => {
    const fetcher = vi.fn<typeof fetch>(() => Promise.resolve(jsonResponse(page([lot]))));
    vi.stubGlobal('fetch', fetcher);
    const wrapper = mount(TaxLotsPage);
    await flushPromises();

    expect(wrapper.text()).toContain('SYN');
    expect(wrapper.text()).toContain('BROKER-LOT-0007');
    expect(wrapper.text()).toContain('1.2500 / 1.2500');
    expect(wrapper.text()).toContain('123.4500 USD / 154.3125 USD');
    expect(wrapper.text()).toContain('8.1875 USD / 5.3099%');
    expect(wrapper.text()).toContain('synthetic-quality-flag');
    expect(wrapper.text()).toContain('Fractional cleanup unsupported; not executable');
    expect(wrapper.text()).toContain('DEMO ONLY');

    await wrapper.get('input[type="checkbox"]').setValue(true);
    expect(wrapper.text()).toContain('Marked for review · 1');
    expect(wrapper.text()).toContain('These local marks are a review aid only');
    expect(fetcher.mock.calls.map(([input]) => requestUrl(input).pathname)).toEqual([
      '/api/v1/lots',
    ]);
    expect(
      fetcher.mock.calls.some(([input]) => requestUrl(input).pathname.includes('/orders/')),
    ).toBe(false);
  });

  it('sends term and unsupported-fractional filters through the typed lots endpoint', async () => {
    const fetcher = vi.fn<typeof fetch>(() => Promise.resolve(jsonResponse(page([lot]))));
    vi.stubGlobal('fetch', fetcher);
    const wrapper = mount(TaxLotsPage);
    await flushPromises();

    await wrapper.findAll('select')[0]!.setValue('ST');
    await wrapper.findAll('select')[1]!.setValue('true');
    await wrapper.get('form').trigger('submit');
    await flushPromises();

    const filteredRequest = requestUrl(fetcher.mock.calls[1]![0]);
    expect(filteredRequest.pathname).toBe('/api/v1/lots');
    expect(filteredRequest.searchParams.get('term')).toBe('ST');
    expect(filteredRequest.searchParams.get('fractional')).toBe('true');
    expect(filteredRequest.searchParams.get('offset')).toBe('0');
    expect(filteredRequest.searchParams.get('limit')).toBe('100');
  });

  it('keeps pagination available when a non-final API page is empty', async () => {
    const fetcher = vi.fn<typeof fetch>((input) => {
      const url = requestUrl(input);
      const offset = Number(url.searchParams.get('offset') ?? '0');
      return Promise.resolve(
        offset === 100 ? jsonResponse(page([], 100, 101)) : jsonResponse(page([lot], 0, 101)),
      );
    });
    vi.stubGlobal('fetch', fetcher);
    const wrapper = mount(TaxLotsPage);
    await flushPromises();

    await wrapper.get('nav[aria-label="Tax lot API pages"] button:last-child').trigger('click');
    await flushPromises();
    expect(wrapper.text()).toContain('No lots returned');
    expect(wrapper.text()).toContain('Page 2 of 2');

    const previousPage = wrapper.get('nav[aria-label="Tax lot API pages"] button:first-child');
    expect((previousPage.element as HTMLButtonElement).disabled).toBe(false);
    await previousPage.trigger('click');
    await flushPromises();

    expect(
      fetcher.mock.calls.map(([input]) => requestUrl(input).searchParams.get('offset')),
    ).toEqual(['0', '100', '0']);
    expect(wrapper.text()).toContain('BROKER-LOT-0007');
  });

  it('shows an API error with retry and an honest empty response', async () => {
    let calls = 0;
    const fetcher = vi.fn<typeof fetch>(() => {
      calls += 1;
      if (calls === 1) {
        return Promise.resolve(
          jsonResponse(
            {
              code: 'lots_unavailable',
              message: 'Synthetic API failure',
              details: {},
              correlation_id: 'test-correlation',
            },
            503,
          ),
        );
      }
      return Promise.resolve(jsonResponse(page([])));
    });
    vi.stubGlobal('fetch', fetcher);
    const wrapper = mount(TaxLotsPage);
    await flushPromises();

    expect(wrapper.text()).toContain('lots_unavailable');
    expect(wrapper.text()).toContain('Synthetic API failure');
    await wrapper.get('button').trigger('click');
    await flushPromises();
    expect(wrapper.text()).toContain('No lots returned');
    expect(calls).toBe(2);
  });
});

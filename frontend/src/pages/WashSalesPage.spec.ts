// @vitest-environment jsdom
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';
import type { WashSalesResponse } from '@/types/api';
import WashSalesPage from './WashSalesPage.vue';
import { Select } from '@/components/ui/select';

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
    {
      broker_transaction_key: 'TX-DIV-3',
      ticker: 'SYN',
      transaction_kind: 'DIVIDEND',
      trade_date: '2025-02-11',
      transaction_time: '2025-02-11T14:30:00Z',
      shares: '0.0100',
      source: 'synthetic-dividend-source',
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

const emptyResponse: WashSalesResponse = {
  demo: true,
  source: 'synthetic-empty-source',
  history: [],
  acquisitions: [],
  current_restrictions: [],
  proposed_restrictions: [],
  warnings: [],
};

const mountedWrappers: VueWrapper[] = [];

function mountWashSalesPage(): VueWrapper {
  const wrapper = mount(WashSalesPage, {
    global: {
      stubs: {
        RouterLink: { template: '<a href="/#/policy#replacement-sets"><slot /></a>' },
      },
    },
  });
  mountedWrappers.push(wrapper);
  return wrapper;
}

function rootElement(wrapper: VueWrapper): HTMLElement {
  return wrapper.element as HTMLElement;
}

function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function tableByCaption(wrapper: VueWrapper, captionText: string): HTMLTableElement {
  const table = Array.from(rootElement(wrapper).querySelectorAll('table')).find(
    (candidate) => candidate.caption?.textContent?.replace(/\s+/g, ' ').trim() === captionText,
  );
  if (!table) throw new Error(`Wash-sales table not found: ${captionText}`);
  return table;
}

beforeEach(() => {
  vi.unstubAllGlobals();
  setActivePinia(createPinia());
});

afterEach(() => {
  mountedWrappers.splice(0).forEach((wrapper) => wrapper.unmount());
  vi.unstubAllGlobals();
});

describe('WashSalesPage', () => {
  it('renders accessible history and labeled current/proposed restrictions', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>(() => Promise.resolve(jsonResponse(response))),
    );
    const wrapper = mountWashSalesPage();
    await flushPromises();

    expect(wrapper.get('[data-wash-sales-root]').attributes('aria-labelledby')).toBe('wash-title');
    const tables = Array.from(rootElement(wrapper).querySelectorAll('table'));
    expect(tables.map((table) => table.caption?.textContent?.replace(/\s+/g, ' ').trim())).toEqual([
      'Current and proposed purchase restrictions',
      'Acquisition history with API-provided lookback dates',
      'Managed-account transaction history returned by the API',
    ]);

    const regions = Array.from(rootElement(wrapper).querySelectorAll('[role="region"]'));
    expect(regions.map((region) => region.getAttribute('aria-label'))).toEqual([
      'Wash-sale purchase restrictions',
      'Wash-sale acquisition rows',
      'Wash-sale transaction history',
    ]);
    for (const region of regions) expect(region.getAttribute('tabindex')).toBe('0');
    for (const table of tables) {
      const columnHeaders = Array.from(table.querySelectorAll('thead th'));
      expect(columnHeaders.length).toBeGreaterThan(0);
      expect(columnHeaders.every((header) => header.getAttribute('scope') === 'col')).toBe(true);
      const rowHeaders = Array.from(table.querySelectorAll('tbody th'));
      expect(rowHeaders.length).toBeGreaterThan(0);
      expect(rowHeaders.every((header) => header.getAttribute('scope') === 'row')).toBe(true);
    }

    const historyTable = tableByCaption(
      wrapper,
      'Managed-account transaction history returned by the API',
    );
    expect(historyTable.textContent).toContain('TX-BUY-1');
    expect(historyTable.textContent).toContain('1.2500');
    expect(historyTable.textContent).toContain('TX-SELL-2');
    expect(
      tableByCaption(wrapper, 'Acquisition history with API-provided lookback dates').textContent,
    ).toContain('2025-02-03');

    expect(wrapper.text()).toContain('Source: synthetic-test-source');
    const restrictionRows = Array.from(
      tableByCaption(wrapper, 'Current and proposed purchase restrictions').querySelectorAll(
        'tbody tr',
      ),
    );
    expect(
      restrictionRows.map((row) => row.querySelector('th[scope="row"]')?.textContent?.trim()),
    ).toEqual(['Current', 'Proposed']);
    const restrictionsText =
      tableByCaption(wrapper, 'Current and proposed purchase restrictions').textContent ?? '';
    expect(restrictionsText).toContain('synthetic-current-source');
    expect(restrictionsText).toContain('synthetic-proposed-source');
    expect(restrictionsText).toContain('2025-03-13');
    expect(restrictionsText).toContain('2025-03-14');
    expect(wrapper.text()).toContain('Proposed records are not represented as executed sales.');
    expect(wrapper.text()).toContain('Overall API coverage is unknown beyond returned rows.');
    expect(wrapper.text()).toContain(
      'Conflicting-transaction links and affected tax-lot IDs are not included',
    );
    expect(wrapper.get('[aria-label="API coverage warnings"]').text()).toContain(
      'Synthetic coverage warning; no live validation.',
    );
    const pageText = wrapper.text();
    expect(pageText).toContain('Overall coverage is unknown beyond returned rows.');
    expect(pageText).toContain('DRIP is assumed disabled');
    expect(pageText).toContain('broker-authoritative adjusted basis and tacked acquisition dates');
    expect(pageText).toContain('prior 30 calendar days and in the proposed basket');
    expect(pageText).toContain('sold in full in the same trade group');
    expect(pageText).toContain('through day +30; day +31 is eligible');
    expect(pageText).toContain(
      'Different configured replacement tickers are assumed non-substantially-identical',
    );
    expect(pageText).toContain('same-ticker repurchases remain restricted');
    expect(wrapper.find('a[href="/#/policy#replacement-sets"]').exists()).toBe(true);
    const restrictionsHeading = rootElement(wrapper).querySelector('#restrictions-title');
    const historyHeading = rootElement(wrapper).querySelector('#history-title');
    expect(restrictionsHeading).not.toBeNull();
    expect(historyHeading).not.toBeNull();
    expect(restrictionsHeading!.compareDocumentPosition(historyHeading!)).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING,
    );
    expect(wrapper.get('[data-slot="badge"]').text()).toBe('DEMO');
  });

  it('distinguishes API and demo data and states broker actions are unavailable', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>(() => Promise.resolve(jsonResponse({ ...response, demo: false }))),
    );
    const wrapper = mountWashSalesPage();
    await flushPromises();

    expect(wrapper.get('[data-slot="badge"]').text()).toBe('API');
    expect(wrapper.text()).toContain('DEMO ONLY.');
    expect(wrapper.text()).toContain('not live E*TRADE validation');
    expect(wrapper.text()).toContain(
      'no broker connection, OAuth, preview, or trade submission is available.',
    );
    const orderButtons = wrapper
      .findAll('button')
      .filter((button) => /place order|preview order/i.test(button.text()));
    expect(orderButtons).toHaveLength(0);
  });

  it('filters source fields case-insensitively and by transaction kind', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>(() => Promise.resolve(jsonResponse(response))),
    );
    const wrapper = mountWashSalesPage();
    await flushPromises();

    const search = wrapper.get('input[type="search"]');
    await search.setValue('  TX-bUy-1  ');
    const historyText =
      tableByCaption(wrapper, 'Managed-account transaction history returned by the API')
        .textContent ?? '';
    expect(historyText).toContain('TX-BUY-1');
    expect(historyText).not.toContain('TX-SELL-2');
    const acquisitionText =
      tableByCaption(wrapper, 'Acquisition history with API-provided lookback dates').textContent ??
      '';
    expect(acquisitionText).toContain('TX-BUY-1');

    await search.setValue(' SYNTHETIC-PROPOSED-LOSS ');
    const restrictions = tableByCaption(wrapper, 'Current and proposed purchase restrictions');
    expect(restrictions.textContent).toContain('synthetic-proposed-loss');
    expect(restrictions.textContent).not.toContain('synthetic-current-loss');

    await search.setValue('');
    const transactionKindSelect = wrapper.findComponent(Select);
    expect(transactionKindSelect.exists()).toBe(true);
    transactionKindSelect.vm.$emit('update:modelValue', 'DIVIDEND');
    await flushPromises();

    const filteredHistory = tableByCaption(
      wrapper,
      'Managed-account transaction history returned by the API',
    );
    expect(filteredHistory.textContent).toContain('TX-DIV-3');
    expect(filteredHistory.textContent).not.toContain('TX-BUY-1');
    expect(filteredHistory.textContent).not.toContain('TX-SELL-2');
    expect(wrapper.get('#wash-transaction-kind').text()).toContain('DIVIDEND');
    const restrictionsAfterKind =
      tableByCaption(wrapper, 'Current and proposed purchase restrictions').textContent ?? '';
    expect(restrictionsAfterKind).toContain('synthetic-current-loss');
    expect(restrictionsAfterKind).toContain('synthetic-proposed-loss');
    expect(restrictionsAfterKind).toContain('2025-03-13');
    expect(restrictionsAfterKind).toContain('2025-03-14');
  });

  it('reports a request error, retries, and displays API-provided empty states', async () => {
    let calls = 0;
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
    const wrapper = mountWashSalesPage();
    await flushPromises();

    expect(wrapper.get('[role="alert"]').text()).toContain('wash_unavailable');
    expect(wrapper.get('[role="alert"]').text()).toContain('Synthetic wash API error');
    const retry = wrapper
      .findAll('button')
      .find((button) => button.text().includes('Retry loading wash data'));
    if (!retry) throw new Error('Wash-sales retry button is missing');
    await retry.trigger('click');
    await flushPromises();

    expect(wrapper.text()).toContain('The API returned no acquisition rows.');
    expect(wrapper.text()).toContain('The API returned no transaction-history rows.');
    expect(wrapper.text()).toContain('The API returned no current or proposed restrictions.');
    expect(wrapper.text()).toContain('The API returned no coverage warnings.');
    expect(calls).toBe(2);
  });

  it('announces loading politely and clears it after the API response', async () => {
    let resolveWashSales!: (value: Response) => void;
    const fetcher = vi.fn<typeof fetch>(
      () =>
        new Promise<Response>((resolve) => {
          resolveWashSales = resolve;
        }),
    );
    vi.stubGlobal('fetch', fetcher);
    const wrapper = mountWashSalesPage();
    await flushPromises();

    const loading = Array.from(rootElement(wrapper).querySelectorAll('[role="status"]')).find(
      (notice) => notice.textContent?.includes('Loading wash-sale history and restrictions'),
    );
    expect(loading?.getAttribute('aria-live')).toBe('polite');
    expect(loading?.textContent).toContain('from the local API');
    expect(wrapper.get('button').attributes('disabled')).toBeDefined();

    resolveWashSales(jsonResponse(response));
    await flushPromises();
    expect(
      Array.from(rootElement(wrapper).querySelectorAll('[role="status"]')).some((notice) =>
        notice.textContent?.includes('Loading wash-sale history and restrictions'),
      ),
    ).toBe(false);
  });
});

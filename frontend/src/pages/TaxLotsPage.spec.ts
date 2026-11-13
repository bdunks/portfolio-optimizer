// @vitest-environment jsdom
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';
import type { LotResponse, OptimizerRecommendationsResponse } from '@/types/api';
import {
  mountWorkspaceHarness,
  seedCurrentRunForTest,
  currentRunForTest,
} from '@/test-utils/workspace-harness';
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

function page(
  items: LotResponse[],
  offset = 0,
  total = items.length,
  sourceGeneration: number | null = 1,
) {
  return { items, total, offset, limit: 100, source_generation: sourceGeneration };
}

function recommendations(
  runId: string,
  selectedLotIds: string[],
  sourceGeneration = 1,
): OptimizerRecommendationsResponse {
  return {
    run_id: runId,
    status: 'demo',
    mode: 'recommendations_only',
    policy_revision_id: 'policy-demo',
    source_generation: sourceGeneration,
    as_of: '2025-02-04T12:00:00Z',
    solver_version: 'DEMO',
    demo: true,
    actionable: false,
    groups: [],
    consolidated_legs:
      selectedLotIds.length === 0
        ? []
        : [
            {
              leg_id: 'sell-leg',
              side: 'SELL',
              ticker: 'SYN',
              selected_lots: selectedLotIds.map((broker_lot_id) => ({
                broker_lot_id,
                shares: '1',
                acquired_date: '2025-02-03',
                adjusted_basis_usd: '100',
                st_lt: 'LT',
                realized_pl_usd: '0',
                selected: true,
              })),
            },
          ],
  } as unknown as OptimizerRecommendationsResponse;
}

function requestBody(init?: RequestInit): unknown {
  if (typeof init?.body !== 'string') throw new Error('Expected a JSON request body');
  return JSON.parse(init.body) as unknown;
}

async function selectOption(
  wrapper: VueWrapper,
  label: string,
  optionLabel: string,
): Promise<void> {
  const trigger = wrapper.get(`[role="combobox"][aria-label="${label}"]`);
  await trigger.trigger('keydown', { key: 'ArrowDown' });
  await flushPromises();
  const option = Array.from(document.body.querySelectorAll<HTMLElement>('[role="option"]')).find(
    (candidate) => candidate.textContent?.replace(/\s+/g, ' ').trim() === optionLabel,
  );
  if (!option) throw new Error(`Select option not found: ${optionLabel}`);
  option.dispatchEvent(new Event('pointerdown', { bubbles: true }));
  option.dispatchEvent(new Event('pointerup', { bubbles: true }));
  await flushPromises();
}

async function setCheckbox(
  wrapper: VueWrapper,
  accessibleName: string,
  requested: boolean,
): Promise<void> {
  const checkbox = wrapper.get(`[role="checkbox"][aria-label="${accessibleName}"]`);
  if (checkbox.attributes('aria-checked') === String(requested)) return;
  await checkbox.trigger('click');
  await flushPromises();
}

beforeEach(() => {
  vi.unstubAllGlobals();
  Object.defineProperty(Element.prototype, 'scrollIntoView', {
    configurable: true,
    value: vi.fn(),
  });
  setActivePinia(createPinia());
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('TaxLotsPage', () => {
  it('renders lots and separates requested intent from confirmed selection', async () => {
    const fetcher = vi.fn<typeof fetch>(() => Promise.resolve(jsonResponse(page([lot]))));
    vi.stubGlobal('fetch', fetcher);
    const store = mountWorkspaceHarness().workspace;
    const wrapper = mount(TaxLotsPage);
    await flushPromises();
    const filters = wrapper.get('form[aria-label="Tax lot filters"]');
    expect(filters.element.tagName).toBe('FORM');
    expect(wrapper.get('.security-card').element.tagName).toBe('SECTION');
    expect(wrapper.get('.security-card').attributes('aria-labelledby')).toBe('security-SYN');
    expect(wrapper.get('.review-summary').element.tagName).toBe('SECTION');

    const renderedTable = wrapper.get('table[data-slot="table"]');
    const caption = renderedTable.element.querySelector('caption')?.textContent;
    expect(caption?.replace(/\s+/g, ' ').trim()).toBe('Tax lots for SYN');
    expect(renderedTable.element.querySelectorAll('thead th[scope="col"]')).toHaveLength(
      renderedTable.element.querySelectorAll('thead th').length,
    );
    expect(renderedTable.element.querySelector('tbody th[scope="row"]')?.textContent).toContain(
      'BROKER-LOT-0007',
    );
    const region = wrapper.get('[role="region"][aria-label="Tax lots for SYN"]');
    expect(region.attributes('tabindex')).toBe('0');
    expect(wrapper.get('.workspace-page').classes()).toContain('workspace-page');
    expect(wrapper.text()).toContain('SYN');
    expect(wrapper.text()).toContain('BROKER-LOT-0007');
    expect(wrapper.text()).toContain('1.2500 / 1.2500');
    expect(wrapper.text()).toContain('123.4500 USD / 154.3125 USD');
    expect(wrapper.text()).toContain('8.1875 USD / 5.3099%');
    expect(wrapper.text()).toContain('synthetic-quality-flag');
    expect(wrapper.text()).toContain('Appreciated-lot review · not authorized');
    expect(wrapper.text()).toContain('Fractional cleanup unsupported; not executable');
    expect(wrapper.text()).toContain('synthetic-test-source · as of 2025-02-04T12:00:00Z');
    expect(wrapper.text()).toContain('DEMO ONLY');
    expect(wrapper.text()).toContain('complete replacement set');
    const noCurrentRun = wrapper
      .findAll('[role="status"]')
      .find((status) => status.text().includes('No current DEMO run is available'));
    expect(noCurrentRun).toBeDefined();

    await setCheckbox(wrapper, 'Request SYN lot BROKER-LOT-0007', true);

    expect(wrapper.text()).toContain('Requested lot intent · 1');
    expect(wrapper.text()).toContain(
      'Backend-confirmed selected SELL lot IDs in the loaded run: none',
    );
    expect(store.lotReviewIntent.map((entry) => entry.broker_lot_id)).toEqual(['BROKER-LOT-0007']);
    expect(store.currentRun).toBeNull();
    expect(fetcher.mock.calls.map(([input]) => requestUrl(input).pathname)).toEqual([
      '/api/v1/lots',
    ]);
    expect(
      fetcher.mock.calls.some(([input]) => requestUrl(input).pathname.includes('/orders/')),
    ).toBe(false);
  });

  it('labels loss, gain, and unavailable P/L as interpretation rather than eligibility', async () => {
    const lots: LotResponse[] = [
      { ...lot, broker_lot_id: 'LOSS-LOT', unrealized_pl_usd: '-0.0001' },
      { ...lot, broker_lot_id: 'GAIN-LOT', unrealized_pl_usd: '12.00' },
      { ...lot, broker_lot_id: 'UNKNOWN-LOT', unrealized_pl_usd: null },
      { ...lot, broker_lot_id: 'EXPONENT-ZERO-LOT', unrealized_pl_usd: '0E-8' },
      { ...lot, broker_lot_id: 'SIGNED-EXPONENT-ZERO-LOT', unrealized_pl_usd: '-0E-8' },
    ];
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>(() => Promise.resolve(jsonResponse(page(lots)))),
    );
    const wrapper = mount(TaxLotsPage);
    await flushPromises();

    expect(wrapper.text()).toContain('Loss opportunity · eligibility unknown');
    expect(wrapper.text()).toContain('Appreciated-lot review · not authorized');
    expect(wrapper.text()).toContain('Financial review unavailable');
    expect(wrapper.text()).toContain('No unrealized gain or loss');
    expect(wrapper.text()).toContain('Quality and cleanup flags');
    expect(wrapper.text()).toContain('Wash Sales');
    expect(wrapper.get('a[href="#/wash-sales"]').text()).toBe('Wash Sales');
    expect(wrapper.text()).toContain('Requested lot intent is a complete-set request');
  });

  it('sends server-side filters and sorting while preserving API row order', async () => {
    let requestCount = 0;
    const lowerProfitLot = {
      ...lot,
      broker_lot_id: 'BROKER-LOT-0001',
      unrealized_pl_usd: '-1.0000',
    };
    const fetcher = vi.fn<typeof fetch>(() => {
      requestCount += 1;
      return Promise.resolve(jsonResponse(page(requestCount >= 3 ? [lot, lowerProfitLot] : [lot])));
    });
    vi.stubGlobal('fetch', fetcher);
    const wrapper = mount(TaxLotsPage);
    await flushPromises();

    await wrapper.get('input[type="search"]').setValue('  ALL-ACCOUNT-RESULT  ');
    await selectOption(wrapper, 'Holding term', 'Short term');
    await selectOption(wrapper, 'Fractional cleanup', 'No unsupported fractional cleanup');
    await wrapper.get('form[aria-label="Tax lot filters"]').trigger('submit');
    await flushPromises();

    const filteredRequest = requestUrl(fetcher.mock.calls[1]![0]);
    expect(filteredRequest.pathname).toBe('/api/v1/lots');
    expect(filteredRequest.searchParams.get('search')).toBe('ALL-ACCOUNT-RESULT');
    expect(filteredRequest.searchParams.get('term')).toBe('ST');
    expect(filteredRequest.searchParams.get('fractional')).toBe('false');
    expect(filteredRequest.searchParams.get('offset')).toBe('0');
    expect(filteredRequest.searchParams.get('limit')).toBe('100');
    // The API owns filtering; returned API rows are rendered even when they do not match the search draft.
    expect(wrapper.text()).toContain('BROKER-LOT-0007');

    await selectOption(wrapper, 'Sort API results by', 'Unrealized P/L (USD)');
    await flushPromises();
    const sortedRequest = requestUrl(fetcher.mock.calls[2]![0]);
    expect(sortedRequest.searchParams.get('sort_by')).toBe('unrealized_pl_usd');
    expect(sortedRequest.searchParams.get('sort_direction')).toBe('asc');
    expect(sortedRequest.searchParams.get('offset')).toBe('0');
    expect(wrapper.findAll('tbody th[scope="row"]').map((cell) => cell.text())).toEqual([
      'BROKER-LOT-0007',
      'BROKER-LOT-0001',
    ]);
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

    await wrapper
      .get('nav[aria-label="Tax lot API pages"] button[aria-label="Next page"]')
      .trigger('click');
    await flushPromises();
    expect(wrapper.text()).toContain('No lots returned');
    const emptyTitle = wrapper.get('[data-slot="empty-title"]');
    expect(emptyTitle.text()).toBe('No lots returned');
    expect(emptyTitle.attributes('role')).toBe('heading');
    expect(emptyTitle.attributes('aria-level')).toBe('2');
    expect(wrapper.text()).toContain('Page 2 of 2');

    const previousPage = wrapper.get(
      'nav[aria-label="Tax lot API pages"] button[aria-label="Previous page"]',
    );
    expect((previousPage.element as HTMLButtonElement).disabled).toBe(false);
    await previousPage.trigger('click');
    await flushPromises();

    expect(
      fetcher.mock.calls.map(([input]) => requestUrl(input).searchParams.get('offset')),
    ).toEqual(['0', '100', '0']);
    expect(wrapper.text()).toContain('BROKER-LOT-0007');
    await wrapper
      .get('nav[aria-label="Tax lot API pages"] button[aria-label="Next page"]')
      .trigger('click');
    await flushPromises();
    await wrapper.get('input[type="search"]').setValue('search-reset');
    await wrapper.get('form[aria-label="Tax lot filters"]').trigger('submit');
    await flushPromises();
    expect(requestUrl(fetcher.mock.calls[4]![0]).searchParams.get('offset')).toBe('0');
    expect(requestUrl(fetcher.mock.calls[4]![0]).searchParams.get('search')).toBe('search-reset');
  });

  it('blocks paging while a filter draft is unapplied and refreshes with applied filters', async () => {
    const fetcher = vi.fn<typeof fetch>((input) => {
      const offset = Number(requestUrl(input).searchParams.get('offset') ?? '0');
      return Promise.resolve(jsonResponse(page([lot], offset, 201)));
    });
    vi.stubGlobal('fetch', fetcher);
    const wrapper = mount(TaxLotsPage);
    await flushPromises();

    const nextPage = wrapper.get(
      'nav[aria-label="Tax lot API pages"] button[aria-label="Next page"]',
    );
    expect((nextPage.element as HTMLButtonElement).disabled).toBe(false);
    const search = wrapper.get('input[type="search"]');
    await search.setValue(' draft-search ');
    expect((nextPage.element as HTMLButtonElement).disabled).toBe(true);
    await nextPage.trigger('click');
    await flushPromises();
    expect(fetcher).toHaveBeenCalledTimes(1);

    const refresh = wrapper
      .findAll('button')
      .find((button) => button.text().includes('Refresh lots'));
    expect(refresh).toBeDefined();
    await refresh!.trigger('click');
    await flushPromises();
    const refreshedRequest = requestUrl(fetcher.mock.calls[1]![0]);
    expect(refreshedRequest.searchParams.get('offset')).toBe('0');
    expect(refreshedRequest.searchParams.has('search')).toBe(false);
    expect((search.element as HTMLInputElement).value).toBe(' draft-search ');

    await wrapper.get('form[aria-label="Tax lot filters"]').trigger('submit');
    await flushPromises();
    const appliedRequest = requestUrl(fetcher.mock.calls[2]![0]);
    expect(appliedRequest.searchParams.get('offset')).toBe('0');
    expect(appliedRequest.searchParams.get('search')).toBe('draft-search');
  });

  it('preserves complete-set lot intent across API pages without submitting on checkbox changes', async () => {
    const runId = 'cross-page-intent-run';
    const store = mountWorkspaceHarness().workspace;
    seedCurrentRunForTest(store, recommendations(runId, []));
    store.currentRunView = 'current';
    const secondPageLot: LotResponse = {
      ...lot,
      ticker: 'ALT',
      broker_lot_id: 'BROKER-LOT-0101',
      unrealized_pl_usd: '900.0000',
    };
    const confirmedRun = recommendations(runId, ['BROKER-LOT-0007', 'BROKER-LOT-0101']);
    const fetcher = vi.fn<typeof fetch>((input, init) => {
      const url = requestUrl(input);
      if (url.pathname === '/api/v1/lots') {
        const offset = Number(url.searchParams.get('offset') ?? '0');
        return Promise.resolve(
          jsonResponse(offset === 100 ? page([secondPageLot], 100, 101) : page([lot], 0, 101)),
        );
      }
      if (url.pathname.endsWith('/lot-review-intent') && init?.method === 'POST') {
        return Promise.resolve(jsonResponse(confirmedRun));
      }
      return Promise.reject(new Error(`Unexpected request: ${init?.method} ${url.pathname}`));
    });
    vi.stubGlobal('fetch', fetcher);
    const wrapper = mount(TaxLotsPage);
    await flushPromises();

    await setCheckbox(wrapper, 'Request SYN lot BROKER-LOT-0007', true);
    expect(fetcher.mock.calls.some(([, init]) => init?.method === 'POST')).toBe(false);
    await wrapper
      .get('nav[aria-label="Tax lot API pages"] button[aria-label="Next page"]')
      .trigger('click');
    await flushPromises();
    expect(
      wrapper.get('[role="checkbox"][aria-label="Request ALT lot BROKER-LOT-0101"]'),
    ).toBeDefined();
    expect(wrapper.find('[aria-label="Request SYN lot BROKER-LOT-0007"]').exists()).toBe(false);
    await setCheckbox(wrapper, 'Request ALT lot BROKER-LOT-0101', true);
    expect(store.lotReviewIntent.map((entry) => entry.broker_lot_id)).toEqual([
      'BROKER-LOT-0007',
      'BROKER-LOT-0101',
    ]);
    expect(fetcher.mock.calls.some(([, init]) => init?.method === 'POST')).toBe(false);

    const applyButton = wrapper
      .findAll('button')
      .find((button) => button.text().includes('Apply complete set to current DEMO run'));
    expect(applyButton).toBeDefined();
    await applyButton!.trigger('click');
    await flushPromises();
    const mutation = fetcher.mock.calls.find(([, init]) => init?.method === 'POST');
    expect(requestBody(mutation?.[1])).toEqual({
      source_generation: 1,
      broker_lot_ids: ['BROKER-LOT-0007', 'BROKER-LOT-0101'],
    });
    expect(store.currentRun?.consolidated_legs[0]?.selected_lots).toHaveLength(2);
    expect(
      fetcher.mock.calls.some(([input]) => requestUrl(input).pathname.includes('/orders/')),
    ).toBe(false);
  });

  it('submits full intent and confirms only after API success', async () => {
    const runId = 'intent-run';
    const store = mountWorkspaceHarness().workspace;
    const originalRun = recommendations(runId, ['OLD-CONFIRMED-LOT']);
    seedCurrentRunForTest(store, originalRun);
    store.currentRunView = 'current';
    const confirmedRun = recommendations(runId, ['BROKER-LOT-0007']);
    const fetcher = vi.fn<typeof fetch>((input, init) => {
      const url = requestUrl(input);
      if (url.pathname === '/api/v1/lots') return Promise.resolve(jsonResponse(page([lot])));
      if (url.pathname.endsWith('/lot-review-intent') && init?.method === 'POST')
        return Promise.resolve(jsonResponse(confirmedRun));
      return Promise.reject(new Error(`Unexpected request: ${init?.method} ${url.pathname}`));
    });
    vi.stubGlobal('fetch', fetcher);
    const wrapper = mount(TaxLotsPage);
    await flushPromises();

    await setCheckbox(wrapper, 'Request SYN lot BROKER-LOT-0007', true);
    expect(currentRunForTest(store)).toBe(originalRun);
    const applyButton = wrapper
      .findAll('button')
      .find((button) => button.text().includes('Apply complete set to current DEMO run'));
    expect(applyButton).toBeDefined();
    await applyButton!.trigger('click');
    await flushPromises();

    const mutation = fetcher.mock.calls.find(([, init]) => init?.method === 'POST');
    expect(mutation).toBeDefined();
    expect(requestUrl(mutation![0]).pathname).toBe(
      `/api/v1/optimizer/runs/${runId}/lot-review-intent`,
    );
    expect(requestBody(mutation![1])).toEqual({
      source_generation: 1,
      broker_lot_ids: ['BROKER-LOT-0007'],
    });
    expect(store.currentRun?.consolidated_legs[0]?.selected_lots[0]?.broker_lot_id).toBe(
      'BROKER-LOT-0007',
    );
    expect(wrapper.text()).toContain(
      'The loaded DEMO run currently selects exactly this requested set',
    );
    expect(wrapper.text()).toContain('not order approval');
  });

  it('shows lot intent as re-applicable when a later basket response changes selection', async () => {
    const runId = 'reconcile-page-run';
    const changedSelection = recommendations(runId, ['OTHER-LOT']);
    const fetcher = vi.fn<typeof fetch>((input, init) => {
      const url = requestUrl(input);
      if (url.pathname === '/api/v1/lots') return Promise.resolve(jsonResponse(page([lot])));
      if (url.pathname.endsWith('/lot-review-intent') && init?.method === 'POST')
        return Promise.resolve(jsonResponse(recommendations(runId, ['BROKER-LOT-0007'])));
      if (url.pathname.endsWith('/selection') && init?.method === 'POST')
        return Promise.resolve(jsonResponse(changedSelection));
      return Promise.reject(new Error(`Unexpected request: ${init?.method} ${url.pathname}`));
    });
    vi.stubGlobal('fetch', fetcher);
    const store = mountWorkspaceHarness().workspace;
    seedCurrentRunForTest(store, recommendations(runId, []));
    store.currentRunView = 'current';
    const wrapper = mount(TaxLotsPage);
    await flushPromises();

    await setCheckbox(wrapper, 'Request SYN lot BROKER-LOT-0007', true);
    const applyButton = () =>
      wrapper
        .findAll('button')
        .find((button) => button.text().includes('Apply complete set to current DEMO run'));
    await applyButton()!.trigger('click');
    await flushPromises();
    expect(applyButton()!.element.disabled).toBe(true);

    await store.recalculateSelection({ selected_group_ids: [] });
    await flushPromises();
    expect(store.lotReviewIntentConfirmedRunId).toBeNull();
    expect(store.lotReviewIntentDirty).toBe(true);
    expect(wrapper.text()).not.toContain('currently selects exactly this requested set');
    expect(wrapper.text()).toContain('different SELL lots than the requested set');
    expect(applyButton()!.element.disabled).toBe(false);
  });

  it('requires an explicit empty set to clear confirmed selection', async () => {
    const runId = 'clear-run';
    const store = mountWorkspaceHarness().workspace;
    const originallyConfirmed = recommendations(runId, ['BROKER-LOT-0007']);
    seedCurrentRunForTest(store, originallyConfirmed);
    store.currentRunView = 'current';
    const responseRun = recommendations(runId, []);
    const fetcher = vi.fn<typeof fetch>((input, init) => {
      const url = requestUrl(input);
      if (url.pathname === '/api/v1/lots') return Promise.resolve(jsonResponse(page([lot])));
      if (url.pathname.endsWith('/lot-review-intent') && init?.method === 'POST')
        return Promise.resolve(jsonResponse(responseRun));
      return Promise.reject(new Error(`Unexpected request: ${init?.method} ${url.pathname}`));
    });
    vi.stubGlobal('fetch', fetcher);
    const wrapper = mount(TaxLotsPage);
    await flushPromises();

    await wrapper
      .findAll('button')
      .find((button) => button.text().includes('Explicitly request an empty set'))!
      .trigger('click');
    expect(store.lotReviewIntent).toEqual([]);
    expect(store.currentRun).toEqual(originallyConfirmed);
    const emptyApplyButton = wrapper
      .findAll('button')
      .find((button) => button.text().includes('Apply empty set and clear confirmed basket'));
    expect(emptyApplyButton).toBeDefined();

    await emptyApplyButton!.trigger('click');
    await flushPromises();
    const mutation = fetcher.mock.calls.find(([, init]) => init?.method === 'POST');
    expect(requestBody(mutation?.[1])).toEqual({ source_generation: 1, broker_lot_ids: [] });
    expect(store.currentRun?.consolidated_legs).toEqual([]);
    expect(wrapper.text()).toContain(
      'The loaded DEMO run currently selects exactly this requested set',
    );
    expect(wrapper.text()).toContain(
      'Backend-confirmed selected SELL lot IDs in the loaded run: none',
    );
  });

  it('preserves confirmed selection and shows reasons on atomic rejection', async () => {
    const runId = 'atomic-run';
    const store = mountWorkspaceHarness().workspace;
    const originalRun = recommendations(runId, ['OLD-CONFIRMED-LOT']);
    seedCurrentRunForTest(store, originalRun);
    store.currentRunView = 'current';
    const fetcher = vi.fn<typeof fetch>((input, init) => {
      const url = requestUrl(input);
      if (url.pathname === '/api/v1/lots') return Promise.resolve(jsonResponse(page([lot])));
      if (url.pathname.endsWith('/lot-review-intent') && init?.method === 'POST')
        return Promise.resolve(
          jsonResponse(
            {
              code: 'lot_review_intent_rejected',
              message: 'Requested lot is not a saved DEMO candidate; basket unchanged',
              details: {
                rejected_lots: [
                  { broker_lot_id: 'BROKER-LOT-0007', reason: 'outside_saved_demo_candidates' },
                ],
                basket_unchanged: true,
              },
              correlation_id: 'intent-rejection',
            },
            422,
          ),
        );
      return Promise.reject(new Error(`Unexpected request: ${init?.method} ${url.pathname}`));
    });
    vi.stubGlobal('fetch', fetcher);
    const wrapper = mount(TaxLotsPage);
    await flushPromises();

    await setCheckbox(wrapper, 'Request SYN lot BROKER-LOT-0007', true);
    await wrapper
      .findAll('button')
      .find((button) => button.text().includes('Apply complete set to current DEMO run'))!
      .trigger('click');
    await flushPromises();

    expect(currentRunForTest(store)).toBe(originalRun);
    expect(store.currentRun?.consolidated_legs[0]?.selected_lots[0]?.broker_lot_id).toBe(
      'OLD-CONFIRMED-LOT',
    );
    expect(store.lotReviewIntent.map((entry) => entry.broker_lot_id)).toEqual(['BROKER-LOT-0007']);
    expect(store.lotReviewIntentDirty).toBe(true);
    expect(wrapper.text()).toContain('lot_review_intent_rejected');
    expect(wrapper.text()).toContain('This lot is not represented by a saved DEMO candidate');
    expect(wrapper.text()).toContain('rejected the complete request atomically');
    expect(wrapper.text()).toContain(
      'Backend-confirmed selected SELL lot IDs in the loaded run: OLD-CONFIRMED-LOT',
    );
  });

  it('persists shared intent across remounts and invalidates on generation change', async () => {
    const fetcher = vi.fn<typeof fetch>(() => Promise.resolve(jsonResponse(page([lot]))));
    vi.stubGlobal('fetch', fetcher);
    const store = mountWorkspaceHarness().workspace;
    const firstMount = mount(TaxLotsPage);
    await flushPromises();
    await setCheckbox(firstMount, 'Request SYN lot BROKER-LOT-0007', true);
    firstMount.unmount();

    const secondMount = mount(TaxLotsPage);
    await flushPromises();
    expect(
      secondMount
        .get('[role="checkbox"][aria-label="Request SYN lot BROKER-LOT-0007"]')
        .attributes('aria-checked'),
    ).toBe('true');
    expect(store.lotReviewIntent).toHaveLength(1);

    store.observeSourceGeneration(2);
    await flushPromises();
    expect(store.lotReviewIntent).toEqual([]);
    expect(store.lotReviewIntentNotice).toContain('Source generation changed to 2');
    const lotCheckbox = secondMount.get(
      '[role="checkbox"][aria-label="Request SYN lot BROKER-LOT-0007"]',
    );
    expect(lotCheckbox.attributes('aria-checked')).toBe('false');
    expect(lotCheckbox.attributes('aria-disabled')).toBe('true');
    expect(secondMount.text()).toContain('Refresh lots before marking or submitting any set');
  });

  it('treats a null source generation as unvalidated and disables lot intent', async () => {
    const fetcher = vi.fn<typeof fetch>(() =>
      Promise.resolve(jsonResponse(page([lot], 0, 1, null))),
    );
    vi.stubGlobal('fetch', fetcher);
    const wrapper = mount(TaxLotsPage);
    await flushPromises();

    expect(
      wrapper
        .get('[role="checkbox"][aria-label="Request SYN lot BROKER-LOT-0007"]')
        .attributes('aria-disabled'),
    ).toBe('true');
    expect(wrapper.text()).toContain('It is unvalidated; lot intent cannot be submitted');
    expect(wrapper.text()).toContain('No current DEMO run is available');
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

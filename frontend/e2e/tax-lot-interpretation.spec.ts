import { expect, test } from './fixtures';

const lot = {
  ticker: 'SYN',
  asset_type: 'EQUITY',
  broker_lot_id: 'BROWSER-LOSS-LOT',
  acquired_date: '2025-02-03',
  remaining_shares: '1.0000',
  available_shares: '1.0000',
  adjusted_unit_basis_usd: '123.4500',
  adjusted_total_basis_usd: '123.4500',
  current_price_usd: '123.0000',
  unrealized_pl_usd: '-0.4500',
  unrealized_pl_pct: '-0.3645',
  source: 'synthetic-browser-source',
  as_of: '2025-02-04T12:00:00Z',
  term: 'LT',
  sleeve_key: 'synthetic-sleeve',
  sub_sleeve_key: null,
  quality_flags: [],
  small_lot_cleanup_candidate: false,
  position_cleanup_candidate: false,
  whole_shares_available: '1',
  fractional_shares: '0',
  fractional_cleanup_unsupported: false,
};

test('Tax Lots interpretation is readable and Wash Sales link is keyboard accessible', async ({
  emptyApp,
  page,
}) => {
  await page.route('**/api/v1/lots**', (route) =>
    route.fulfill({
      json: { items: [lot], total: 1, offset: 0, limit: 100, source_generation: 1 },
    }),
  );
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto(new URL('/#/lots', emptyApp.baseUrl).toString());
  await expect(page.getByRole('heading', { name: 'How to interpret these lots' })).toBeVisible();
  await expect(page.getByText('Loss opportunity · eligibility unknown')).toBeVisible();
  await expect(page.getByText('Requested lot intent is a complete-set request')).toBeVisible();
  await expect(page.getByText('neither request nor selection approves an order')).toBeVisible();

  const washSalesLink = page.getByRole('link', { name: 'Wash Sales', exact: true });
  await washSalesLink.focus();
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/#\/wash-sales$/);
  await expect(page.getByRole('heading', { name: 'Wash Sales', exact: true })).toBeVisible();

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(new URL('/#/lots', emptyApp.baseUrl).toString());
  const interpretation = page.locator('[aria-labelledby="lot-interpretation-title"]');
  await expect(interpretation).toBeVisible();
  await expect(
    interpretation.getByText(/Wash-sale restrictions can apply across the account/),
  ).toBeVisible();
  await expect(
    page.evaluate(() => document.documentElement.scrollWidth),
  ).resolves.toBeLessThanOrEqual(390);
});

import { mkdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { expect, test } from './fixtures';

const washSalesResponse = {
  demo: true,
  source: 'synthetic-browser-source',
  history: [
    {
      broker_transaction_key: 'BROWSER-BUY-1',
      ticker: 'SYN',
      transaction_kind: 'BUY',
      trade_date: '2025-01-04',
      transaction_time: '2025-01-04T14:30:00Z',
      shares: '1.2500',
      source: 'synthetic-history',
      is_acquisition: true,
    },
    {
      broker_transaction_key: 'BROWSER-SELL-2',
      ticker: 'SYN',
      transaction_kind: 'SELL',
      trade_date: '2025-02-10',
      transaction_time: '2025-02-10T14:30:00Z',
      shares: '0.5000',
      source: 'synthetic-history',
      is_acquisition: false,
    },
    {
      broker_transaction_key: 'BROWSER-DIV-3',
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
      broker_transaction_key: 'BROWSER-BUY-1',
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

const desktopScreenshot = resolve(process.cwd(), '../test-results/wash-sales-desktop.png');
const mobileScreenshot = resolve(process.cwd(), '../test-results/wash-sales-mobile.png');

mkdirSync(dirname(desktopScreenshot), { recursive: true });

test('Wash Sales responsive controls and table behavior', async ({ page, seededApp }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.route('**/api/v1/wash-sales', (route) => route.fulfill({ json: washSalesResponse }));
  await page.goto(new URL('/#/wash-sales', seededApp.baseUrl).toString());
  await expect(page.getByRole('heading', { name: 'Wash Sales', exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'API coverage', exact: true })).toBeVisible();
  await expect(page.getByText('Source: synthetic-browser-source')).toBeVisible();
  await page.screenshot({ path: desktopScreenshot, fullPage: true });

  const refreshButton = page.getByRole('button', { name: 'Refresh wash data' });
  const buttonStyles = await refreshButton.evaluate((element) => {
    const styles = getComputedStyle(element);
    return {
      appearance: styles.appearance,
      fontFamily: styles.fontFamily,
      fontSize: styles.fontSize,
    };
  });
  const bodyFontFamily = await page
    .locator('body')
    .evaluate((element) => getComputedStyle(element).fontFamily);
  expect(buttonStyles.appearance).toBe('none');
  expect(buttonStyles.fontFamily).toBe(bodyFontFamily);
  expect(buttonStyles.fontSize).toBe('14px');

  const coverageTitle = page
    .locator('[data-slot="card-title"]')
    .filter({ hasText: 'API coverage' });
  const coverageDescription = page
    .locator('[data-slot="card-description"]')
    .filter({ hasText: 'Source: synthetic-browser-source' });
  expect(await coverageTitle.evaluate((element) => getComputedStyle(element).fontSize)).toBe(
    '16px',
  );
  expect(await coverageDescription.evaluate((element) => getComputedStyle(element).fontSize)).toBe(
    '14px',
  );
  const coverageNote = page
    .locator('[data-wash-sales-root] p')
    .filter({ hasText: 'Overall API coverage is unknown beyond returned rows.' });
  expect(await coverageNote.evaluate((element) => getComputedStyle(element).margin)).toBe('0px');

  const kindSelect = page.getByRole('combobox', { name: 'Transaction kind' });
  await kindSelect.focus();
  await kindSelect.press('ArrowDown');
  const listbox = page.getByRole('listbox');
  await expect(listbox).toBeVisible();
  await expect(page.getByRole('option')).toHaveCount(5);
  const selectContent = page.locator('[data-slot="select-content"]');
  await expect(selectContent).toBeVisible();
  const popupStyles = await selectContent.evaluate((element) => ({
    isTeleported: !document.querySelector('[data-wash-sales-root]')?.contains(element),
    className: element.className,
    fontFamily: getComputedStyle(element).fontFamily,
    fontSize: getComputedStyle(element).fontSize,
  }));
  expect(popupStyles.isTeleported).toBe(true);
  expect(popupStyles.className).toContain('wash-sales-select-content');
  expect(popupStyles.fontFamily).toBe(bodyFontFamily);
  expect(popupStyles.fontSize).toBe('14px');

  await page.keyboard.press('Escape');
  await expect(listbox).not.toBeVisible();
  await expect(kindSelect).toBeFocused();

  await kindSelect.press('ArrowDown');
  await expect(listbox).toBeVisible();
  await page.keyboard.press('d');
  await page.keyboard.press('Enter');
  await expect(kindSelect).toContainText('DIVIDEND');
  await expect(page.getByText('BROWSER-DIV-3')).toBeVisible();
  await expect(page.getByText('BROWSER-BUY-1')).not.toBeVisible();
  const restrictionsAfterKind = page.getByRole('region', {
    name: 'Wash-sale purchase restrictions',
  });
  await expect(restrictionsAfterKind.getByText('synthetic-current-loss')).toBeVisible();
  await expect(restrictionsAfterKind.getByText('synthetic-proposed-loss')).toBeVisible();

  await kindSelect.press('ArrowDown');
  await expect(listbox).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(kindSelect).toBeFocused();
  await expect(kindSelect).toContainText('DIVIDEND');

  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Wash Sales', exact: true })).toBeVisible();
  await page.screenshot({ path: mobileScreenshot, fullPage: true });
  const search = page.getByRole('searchbox', { name: 'Filter records' });
  await search.fill('synthetic-proposed-loss');
  const restrictionTable = page
    .getByRole('region', { name: 'Wash-sale purchase restrictions' })
    .getByRole('table');
  await expect(restrictionTable.getByText('synthetic-proposed-loss')).toBeVisible();
  await expect(restrictionTable.getByText('synthetic-current-loss')).not.toBeVisible();
  await search.fill('');

  const historyRegion = page.getByRole('region', { name: 'Wash-sale transaction history' });
  const scrollMetrics = await historyRegion.evaluate((element) => ({
    clientWidth: element.clientWidth,
    scrollWidth: element.scrollWidth,
  }));
  expect(scrollMetrics.scrollWidth).toBeGreaterThan(scrollMetrics.clientWidth);
  await historyRegion.focus();
  await expect(historyRegion).toBeFocused();
  await historyRegion.press('ArrowRight');
  await expect
    .poll(() => historyRegion.evaluate((element) => element.scrollLeft))
    .toBeGreaterThan(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test('Wash-sale guidance journey stays explicit and usable across keyboard and mobile', async ({
  page,
  seededApp,
}) => {
  await page.route('**/api/v1/wash-sales', (route) => route.fulfill({ json: washSalesResponse }));
  await page.goto(new URL('/#/wash-sales', seededApp.baseUrl).toString());

  const restrictions = page.getByRole('region', { name: 'Wash-sale purchase restrictions' });
  await expect(restrictions.getByRole('rowheader', { name: 'Current' })).toBeVisible();
  await expect(restrictions.getByRole('rowheader', { name: 'Proposed' })).toBeVisible();
  await expect(restrictions.getByText('synthetic-proposed-loss')).toBeVisible();
  await expect(page.getByText(/not represented as executed sales/i)).toBeVisible();
  await expect(page.locator('[aria-label="Wash-sale coverage limitations"]')).toContainText(
    'missing required managed-account history must block affected recommendations',
  );
  await expect(page.getByRole('heading', { name: 'API coverage' })).toBeVisible();
  expect(
    await page.evaluate(() => {
      const restriction = document.querySelector('[aria-label="Wash-sale purchase restrictions"]');
      const coverage = document.querySelector('section[aria-labelledby="coverage-title"]');
      if (restriction && coverage && coverage.contains(restriction)) return false;
      return Boolean(
        restriction &&
        coverage &&
        restriction.compareDocumentPosition(coverage) & Node.DOCUMENT_POSITION_FOLLOWING,
      );
    }),
  ).toBe(true);

  const replacementLink = page.getByRole('link', {
    name: 'Review configured replacement-set assumptions in Policy',
  });
  await replacementLink.focus();
  await expect(replacementLink).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/#\/policy#replacement-sets/);
  const replacementHeading = page.getByRole('heading', { name: 'Replacement sets' });
  await expect(replacementHeading).toBeFocused();

  await page.goto(new URL('/#/wash-sales', seededApp.baseUrl).toString());
  const search = page.getByRole('searchbox', { name: 'Filter records' });
  await search.fill('BROWSER-BUY-1');
  const history = page.getByRole('region', { name: 'Wash-sale transaction history' });
  await expect(history.getByText('BROWSER-BUY-1')).toBeVisible();
  await expect(history.getByText('BROWSER-SELL-2')).not.toBeVisible();

  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Wash Sales', exact: true })).toBeVisible();
  const mobile = await page.evaluate(() => ({
    viewportWidth: document.documentElement.clientWidth,
    documentWidth: document.documentElement.scrollWidth,
    assumptionFontSize: getComputedStyle(document.querySelector('[data-wash-sales-root] p')!)
      .fontSize,
  }));
  expect(mobile.documentWidth).toBeLessThanOrEqual(mobile.viewportWidth);
  expect(Number.parseFloat(mobile.assumptionFontSize)).toBeGreaterThanOrEqual(14);
  await expect(page.getByText(/prior 30 calendar days/)).toBeVisible();
});

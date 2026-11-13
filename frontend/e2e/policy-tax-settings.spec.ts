import { expect, test } from './fixtures';
import type { Page } from '@playwright/test';

async function expectNoPageOverflow(page: Page, context: string): Promise<void> {
  const dimensions = await page.evaluate(() => ({
    viewport: window.innerWidth,
    document: document.documentElement.scrollWidth,
  }));
  expect(
    dimensions.document,
    `${context}: document width ${dimensions.document} exceeds viewport ${dimensions.viewport}`,
  ).toBeLessThanOrEqual(dimensions.viewport + 1);
}

test('tax and batch settings remain accessible and responsive', async ({
  page,
  seededApp,
}, testInfo) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto(new URL('/#/policy', seededApp.baseUrl).toString(), {
    waitUntil: 'domcontentloaded',
  });
  await expect(page.getByRole('heading', { name: 'Allocation Policy', exact: true })).toBeVisible();

  const overview = page.locator('[aria-labelledby="policy-overview-title"]');
  await expect(overview).toContainText('Enabled allocations');
  await expect(overview).toContainText('Configured drift bands');
  await expect(overview).toContainText('Maximum per-batch SELL tickers / lots / total orders');
  await expect(page.locator('[aria-labelledby="current-allocation-title"]')).toBeVisible();
  const taxSettings = page.locator('[data-policy-tax-settings-root]');
  await expect(taxSettings).toBeVisible();
  const taxHeading = taxSettings.getByRole('heading', { name: 'Tax & Batch Settings', level: 2 });
  await expect(taxHeading).toBeVisible();
  const shortTermRate = page.getByRole('textbox', {
    name: 'Short-term marginal tax rate (fraction, nullable)',
  });
  const preferEtfBuys = page.getByRole('combobox', { name: 'Prefer ETF buys' });
  const preferEtfBuysControl = taxSettings.locator('[id$="-prefer-etf-buys"]');
  await expect(shortTermRate).toBeVisible();
  await expect(preferEtfBuys).toBeVisible();
  for (const name of [
    'Allow appreciated-gain sales',
    'Permit ETF harvesting',
    'Permit municipal-bond exit',
  ]) {
    await expect(taxSettings.getByRole('combobox', { name })).toBeVisible();
  }
  await expect(taxSettings).toContainText(
    'preferred ETF buys, appreciated-gain sales, ETF harvesting, and municipal-bond exits',
  );
  await expect(taxSettings).toContainText('each order requires individual user approval');
  await expectNoPageOverflow(page, 'desktop policy page');

  await taxSettings.screenshot({ path: testInfo.outputPath('policy-tax-settings-desktop.png') });
  await testInfo.attach('policy tax settings desktop', {
    path: testInfo.outputPath('policy-tax-settings-desktop.png'),
    contentType: 'image/png',
  });

  await shortTermRate.focus();
  await expect(shortTermRate).toBeFocused();
  await shortTermRate.press('Control+A');
  await shortTermRate.pressSequentially('0.2500000000000000001');
  await expect(shortTermRate).toHaveValue('0.2500000000000000001');

  await preferEtfBuys.focus();
  await expect(preferEtfBuys).toBeFocused();
  await preferEtfBuys.press('Space');
  await expect(page.getByRole('option', { name: 'Disabled', exact: true })).toBeVisible();
  await page.keyboard.press('End');
  await expect(page.getByRole('option', { name: 'Disabled', exact: true })).toHaveAttribute(
    'data-highlighted',
    '',
  );
  await page.keyboard.press('Enter');
  await expect(preferEtfBuysControl).toContainText('Disabled');

  await page.setViewportSize({ width: 390, height: 844 });
  await expectNoPageOverflow(page, 'mobile policy page');
  await shortTermRate.focus();
  await expect(shortTermRate).toBeFocused();
  await expect(shortTermRate).toHaveAttribute('id', /.+/);
  await taxSettings.screenshot({ path: testInfo.outputPath('policy-tax-settings-mobile.png') });
  await testInfo.attach('policy tax settings mobile', {
    path: testInfo.outputPath('policy-tax-settings-mobile.png'),
    contentType: 'image/png',
  });
});

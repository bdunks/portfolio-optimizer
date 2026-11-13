import type { Locator, Page } from '@playwright/test';
import { expect, test } from './fixtures';

async function expectNoDocumentOverflow(page: Page, context: string): Promise<void> {
  const dimensions = await page.evaluate(() => ({
    viewport: window.innerWidth,
    document: document.documentElement.scrollWidth,
  }));
  expect(
    dimensions.document,
    `${context}: document width ${dimensions.document} exceeds viewport ${dimensions.viewport}`,
  ).toBeLessThanOrEqual(dimensions.viewport + 1);
}

async function expectKeyboardFocusable(region: Locator): Promise<void> {
  await expect(region).toHaveAttribute('tabindex', '0');
  await region.focus();
  await expect(region).toBeFocused();
  await region.press('Tab');
  await expect(region).not.toBeFocused();
}

test('US transition comparison is readable and keyboard-focusable on desktop and tablet', async ({
  page,
  seededApp,
}, testInfo) => {
  test.setTimeout(120_000);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto(new URL('/', seededApp.baseUrl).toString(), { waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('heading', { name: 'Overview', exact: true })).toBeVisible();

  const transition = page.locator('.transition-panel').first();
  const comparison = transition.getByRole('region', {
    name: 'US allocation transition comparison',
  });
  await expect(transition).toBeVisible();
  await expect(
    transition
      .getByText('No trades selected. Proposed values are not shown.', { exact: true })
      .first(),
  ).toBeVisible();
  await expect(
    comparison.getByRole('columnheader', { name: 'Current', exact: true }),
  ).toBeVisible();
  await expect(
    comparison.getByRole('columnheader', { name: 'After selected trades', exact: true }),
  ).toBeVisible();
  await expect(comparison.getByRole('columnheader', { name: 'Target', exact: true })).toBeVisible();
  const proposedSummary = transition
    .locator('.whole-portfolio-summary > div')
    .filter({ hasText: 'After selected trades' });
  await expect(proposedSummary).toContainText('No trades selected. Proposed values are not shown.');
  await expectKeyboardFocusable(comparison);
  await expectNoDocumentOverflow(page, 'desktop US transition');

  const desktopScreenshot = testInfo.outputPath('us-allocation-transition-desktop.png');
  await transition.screenshot({ path: desktopScreenshot });
  await testInfo.attach('US transition desktop', {
    path: desktopScreenshot,
    contentType: 'image/png',
  });

  await page.setViewportSize({ width: 768, height: 1024 });
  await expect(transition).toBeVisible();
  await expect(comparison).toBeVisible();
  await expectNoDocumentOverflow(page, 'tablet US transition');
  await expectKeyboardFocusable(comparison);

  const tabletScreenshot = testInfo.outputPath('us-allocation-transition-tablet.png');
  await transition.screenshot({ path: tabletScreenshot });
  await testInfo.attach('US transition tablet', {
    path: tabletScreenshot,
    contentType: 'image/png',
  });
});

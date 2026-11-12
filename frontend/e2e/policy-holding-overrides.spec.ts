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

test('holding overrides stay responsive, accessible, and keyboard-selectable', async ({
  page,
  seededApp,
}, testInfo) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto(new URL('/#/policy', seededApp.baseUrl).toString(), {
    waitUntil: 'domcontentloaded',
  });
  await expect(page.getByRole('heading', { name: 'Allocation Policy', exact: true })).toBeVisible();

  const editor = page.locator('[data-policy-holding-overrides-root]');
  await expect(
    editor.getByRole('heading', { name: 'Explicit holding overrides', level: 2 }),
  ).toBeVisible();
  const region = editor.getByRole('region', { name: 'Holding sleeve overrides' });
  await expect(region).toHaveAttribute('tabindex', '0');
  const selectors = editor.getByRole('combobox', { name: /^Explicit override for / });
  await expect(selectors.first()).toBeVisible();
  await expectNoPageOverflow(page, 'desktop policy page');

  const controlIds = await selectors.evaluateAll((controls) =>
    controls.map((control) => control.id),
  );
  expect(new Set(controlIds).size).toBe(controlIds.length);
  expect(controlIds.every((id) => id.length > 0)).toBe(true);
  await editor.screenshot({ path: testInfo.outputPath('policy-holding-overrides-desktop.png') });
  await testInfo.attach('policy holding overrides desktop', {
    path: testInfo.outputPath('policy-holding-overrides-desktop.png'),
    contentType: 'image/png',
  });

  const firstSelector = selectors.first();
  await firstSelector.focus();
  await expect(firstSelector).toBeFocused();
  await firstSelector.press('Space');
  const defaultOption = page.getByRole('option', { name: 'Use default resolution', exact: true });
  await expect(defaultOption).toBeVisible();
  await page.keyboard.press('Home');
  await page.keyboard.press('ArrowDown');
  const highlightedOption = page.locator('[role="option"][data-highlighted]');
  await expect(highlightedOption).toBeVisible();
  const selectedTargetLabel = (await highlightedOption.innerText()).trim();
  expect(selectedTargetLabel).not.toBe('Use default resolution');
  expect(selectedTargetLabel).not.toContain('Current assignment');
  await page.keyboard.press('Enter');
  await expect(firstSelector).toContainText(selectedTargetLabel);
  await expect(page.getByRole('option')).toHaveCount(0);

  await firstSelector.press('Space');
  await expect(
    page.getByRole('option', { name: 'Use default resolution', exact: true }),
  ).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('option')).toHaveCount(0);
  await expect(firstSelector).toBeFocused();

  await page.setViewportSize({ width: 390, height: 844 });
  await expectNoPageOverflow(page, 'mobile policy page');
  await expect(region).toBeVisible();
  const scrollable = await region.evaluate((element) => ({
    clientWidth: element.clientWidth,
    scrollWidth: element.scrollWidth,
  }));
  expect(scrollable.scrollWidth).toBeGreaterThan(scrollable.clientWidth);
  await editor.screenshot({ path: testInfo.outputPath('policy-holding-overrides-mobile.png') });
  await testInfo.attach('policy holding overrides mobile', {
    path: testInfo.outputPath('policy-holding-overrides-mobile.png'),
    contentType: 'image/png',
  });

  await region.focus();
  await expect(region).toBeFocused();
  await region.press('ArrowRight');
  await expect.poll(() => region.evaluate((element) => element.scrollLeft)).toBeGreaterThan(0);
  await expectNoPageOverflow(page, 'mobile policy page after table keyboard scrolling');
});

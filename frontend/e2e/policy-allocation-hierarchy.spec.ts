import { expect, test } from './fixtures';
import type { Locator, Page } from '@playwright/test';

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

async function expectReadableAllocationNames(region: Locator, context: string): Promise<void> {
  const widths = await region
    .locator('tbody input[aria-label^="Sleeve display name for "]')
    .evaluateAll((inputs) => inputs.map((input) => input.getBoundingClientRect().width));
  expect(widths.length, `${context}: allocation name inputs are present`).toBeGreaterThan(0);
  expect(
    widths.every((width) => width >= 180),
    `${context}: allocation name input widths are ${widths.join(', ')}px`,
  ).toBe(true);
}

test('allocation hierarchy supports keyboard controls and contextual settings', async ({
  page,
  seededApp,
}, testInfo) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto(new URL('/#/policy', seededApp.baseUrl).toString(), {
    waitUntil: 'domcontentloaded',
  });
  await expect(page.getByRole('heading', { name: 'Allocation Policy', exact: true })).toBeVisible();

  const editor = page.locator('[data-policy-sleeves-root]');
  const region = editor.getByRole('region', { name: 'Sleeve allocation policy settings' });
  await expect(region).toBeVisible();
  await expect(region).toHaveAttribute('tabindex', '0');
  await expect(region.getByRole('columnheader', { name: 'Parent', exact: true })).toHaveCount(0);
  await expect(region.getByRole('columnheader', { name: 'Designations', exact: true })).toHaveCount(
    0,
  );
  await expectNoPageOverflow(page, 'desktop allocation policy');

  await expectReadableAllocationNames(region, 'desktop allocation policy');
  await editor.screenshot({ path: testInfo.outputPath('policy-allocation-hierarchy-desktop.png') });
  await testInfo.attach('policy allocation hierarchy desktop', {
    path: testInfo.outputPath('policy-allocation-hierarchy-desktop.png'),
    contentType: 'image/png',
  });

  const rootRows = region.locator('tbody tr[data-hierarchy-depth="0"]');
  await expect.poll(() => rootRows.count()).toBeGreaterThanOrEqual(2);
  const sourceRow = rootRows.nth(0);
  const destinationRow = rootRows.nth(1);
  const sourceKey = (await sourceRow.locator('.sleeve-key').textContent())?.trim();
  const destinationKey = (await destinationRow.locator('.sleeve-key').textContent())?.trim();
  const sourceDisplayName = await sourceRow
    .locator('input[aria-label^="Sleeve display name for "]')
    .inputValue();
  const destinationDisplayName = await destinationRow
    .locator('input[aria-label^="Sleeve display name for "]')
    .inputValue();
  if (!sourceKey || !destinationKey || !sourceDisplayName || !destinationDisplayName) {
    throw new Error('The seeded policy must expose two named top-level allocations');
  }

  const childRows = region.locator(`tbody tr[data-parent-sleeve-key="${sourceKey}"]`);
  const originalChildCount = await childRows.count();
  const sourceActions = sourceRow.getByRole('button', { name: `Actions for ${sourceDisplayName}` });
  await sourceActions.focus();
  await expect(sourceActions).toBeFocused();
  await page.keyboard.press('Enter');
  const addChildAction = page.getByRole('menuitem', { name: 'Add sub-sleeve' });
  await expect(addChildAction).toBeVisible();
  await expect(addChildAction).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(childRows).toHaveCount(originalChildCount + 1);
  const childRow = childRows.last();
  const childKey = (await childRow.locator('.sleeve-key').textContent())?.trim();
  if (!childKey) throw new Error('The new sub-sleeve key is missing');
  await expect(childRow).toHaveAttribute('data-hierarchy-depth', '1');
  await expect(childRow.locator('input[aria-label^="Target percent within "]')).toHaveAttribute(
    'aria-label',
    `Target percent within ${sourceDisplayName} for ${childKey}`,
  );

  const expansionToggle = sourceRow.locator('button[aria-expanded]:not([aria-haspopup="menu"])');
  const collapseButton = sourceRow.getByRole('button', {
    name: `Collapse children of ${sourceDisplayName}`,
  });
  await collapseButton.focus();
  await page.keyboard.press('Enter');
  await expect(expansionToggle).toHaveAttribute('aria-expanded', 'false');
  await expect(childRow).toHaveCount(0);
  const expandButton = sourceRow.getByRole('button', {
    name: `Expand children of ${sourceDisplayName}`,
  });
  await expandButton.focus();
  await page.keyboard.press('Enter');
  await expect(expansionToggle).toHaveAttribute('aria-expanded', 'true');
  await expect(childRow).toBeVisible();

  const childActions = childRow.getByRole('button', { name: `Actions for ${childKey}` });
  await childActions.focus();
  await page.keyboard.press('Enter');
  const allocationSettingsAction = page.getByRole('menuitem', { name: 'Allocation settings' });
  await expect(allocationSettingsAction).toBeVisible();
  await page.keyboard.press('ArrowDown');
  await expect(allocationSettingsAction).toBeFocused();
  await page.keyboard.press('Enter');
  const settingsDialog = page.getByRole('dialog', { name: `Settings for ${childKey}` });
  await expect(settingsDialog).toBeVisible();

  const parentSelector = settingsDialog.getByRole('combobox', {
    name: `Parent sleeve for ${childKey}`,
  });
  await parentSelector.focus();
  await expect(parentSelector).toBeFocused();
  await page.keyboard.press('Enter');
  const destinationOption = page.getByRole('option', {
    name: destinationDisplayName,
    exact: true,
  });
  await expect(destinationOption).toBeVisible();
  await destinationOption.click();

  await expect(parentSelector).toContainText(destinationDisplayName);

  const cashControl = settingsDialog.getByRole('checkbox', { name: `Cash sleeve for ${childKey}` });
  await cashControl.focus();
  await page.keyboard.press('Space');
  await expect(cashControl).toHaveAttribute('aria-checked', 'true');
  await page.keyboard.press('Space');
  await expect(cashControl).toHaveAttribute('aria-checked', 'false');
  await page.keyboard.press('Escape');
  await expect(settingsDialog).toBeHidden();

  const reparentedChildRow = region.locator(`tbody tr[data-sleeve-key="${childKey}"]`);
  await expect(reparentedChildRow).toHaveAttribute('data-parent-sleeve-key', destinationKey);
  const reparentedActions = reparentedChildRow.getByRole('button', {
    name: `Actions for ${childKey}`,
  });
  await expect(reparentedActions).toBeFocused();

  await expect(
    reparentedChildRow.locator('input[aria-label^="Target percent within "]'),
  ).toHaveAttribute(
    'aria-label',
    `Target percent within ${destinationDisplayName} for ${childKey}`,
  );

  await reparentedActions.focus();
  await page.keyboard.press('Enter');
  await expect(addChildAction).toBeFocused();
  await page.keyboard.press('ArrowDown');
  await expect(allocationSettingsAction).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(settingsDialog).toBeVisible();
  await settingsDialog.getByRole('button', { name: 'Close' }).click();
  await expect(settingsDialog).toBeHidden();
  await expect(reparentedActions).toBeFocused();

  await page.setViewportSize({ width: 1024, height: 768 });
  await expectNoPageOverflow(page, 'tablet allocation policy');

  await expectReadableAllocationNames(region, 'tablet allocation policy');
  const tableContainer = editor.locator('[data-slot="table-container"]');
  const hasInternalHorizontalScroll = await tableContainer.evaluate(
    (element) => element.scrollWidth > element.clientWidth,
  );
  expect(hasInternalHorizontalScroll, 'tablet allocation table scrolls internally').toBe(true);
  await expect(region).toBeVisible();
  await expect(region).toHaveAttribute('tabindex', '0');
  await editor.screenshot({ path: testInfo.outputPath('policy-allocation-hierarchy-tablet.png') });
  await testInfo.attach('policy allocation hierarchy tablet', {
    path: testInfo.outputPath('policy-allocation-hierarchy-tablet.png'),
    contentType: 'image/png',
  });
});

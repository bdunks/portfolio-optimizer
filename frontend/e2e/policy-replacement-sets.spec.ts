import { expect, test } from './fixtures';
import type { Page } from '@playwright/test';

async function expectNoPageOverflow(page: Page, context: string): Promise<void> {
  const dimensions = await page.evaluate(() => ({
    viewport: window.innerWidth,
    document: document.documentElement.scrollWidth,
    body: document.body.scrollWidth,
  }));
  expect(
    dimensions.document,
    `${context}: document width ${dimensions.document} exceeds viewport ${dimensions.viewport}`,
  ).toBeLessThanOrEqual(dimensions.viewport + 1);
  expect(
    dimensions.body,
    `${context}: body width ${dimensions.body} exceeds viewport ${dimensions.viewport}`,
  ).toBeLessThanOrEqual(dimensions.viewport + 1);
}

test('replacement-set fragment navigation moves keyboard focus to its heading', async ({
  page,
  seededApp,
}) => {
  await page.goto(new URL('/#/policy', seededApp.baseUrl).toString(), {
    waitUntil: 'domcontentloaded',
  });
  const heading = page.getByRole('heading', { name: 'Replacement sets', exact: true });
  await expect(heading).toBeVisible();

  await page.goto(new URL('/#/policy#replacement-sets', seededApp.baseUrl).toString(), {
    waitUntil: 'domcontentloaded',
  });

  await expect(heading).toBeFocused();
});

test('replacement candidates are accessible, keyboard-usable, and responsive', async ({
  page,
  seededApp,
}, testInfo) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto(new URL('/#/policy', seededApp.baseUrl).toString(), {
    waitUntil: 'domcontentloaded',
  });
  await expect(page.getByRole('heading', { name: 'Allocation Policy', exact: true })).toBeVisible();

  await page.getByRole('button', { name: 'All configured replacement sets' }).click();
  const editor = page.locator('[data-policy-replacement-sets-root]');
  await expect(
    editor.getByRole('heading', { name: 'All configured replacement sets', level: 2 }),
  ).toBeVisible();
  const table = editor.getByRole('table');
  await expect(table.getByRole('columnheader')).toHaveText([
    'Order',
    'Ticker',
    'Replacement set ID',
    'Priority',
    'Parent sleeve',
    'Sub-sleeve',
    'Exposure suitability (API note)',
    'Enabled',
    'Actions',
  ]);
  await expect(
    editor.getByText(
      /Distinct investments are a user-entered wash-sale assumption, not a guarantee or automated exposure-equivalence check/,
    ),
  ).toBeVisible();
  const region = editor.getByRole('region', { name: 'Replacement security candidates' });
  await expect(region).toHaveAttribute('tabindex', '0');
  await expectNoPageOverflow(page, 'desktop policy page');
  const desktopScrollSizes = await region.evaluate((element) => ({
    clientWidth: element.clientWidth,
    scrollWidth: element.scrollWidth,
  }));

  const desktopHeaderLayout = await editor.evaluate((element) => {
    const description = element.querySelector<HTMLElement>('.replacement-editor-description');
    const addButton = element.querySelector<HTMLButtonElement>('button[id$="-add-candidate"]');
    const textColumn = description?.parentElement;
    const headerContainer = textColumn?.parentElement;
    if (!description || !addButton || !textColumn || !headerContainer) return null;
    const descriptionRect = description.getBoundingClientRect();
    const textColumnRect = textColumn.getBoundingClientRect();
    const headerRect = headerContainer.getBoundingClientRect();
    const addButtonRect = addButton.getBoundingClientRect();
    return {
      descriptionRight: descriptionRect.right,
      textColumnTop: textColumnRect.top,
      textColumnRight: textColumnRect.right,
      headerRight: headerRect.right,
      addButtonTop: addButtonRect.top,
      addButtonLeft: addButtonRect.left,
      addButtonRight: addButtonRect.right,
    };
  });
  expect(desktopHeaderLayout).not.toBeNull();
  expect(
    Math.abs(desktopHeaderLayout!.textColumnTop - desktopHeaderLayout!.addButtonTop),
  ).toBeLessThanOrEqual(1);
  expect(desktopHeaderLayout!.addButtonLeft).toBeGreaterThanOrEqual(
    desktopHeaderLayout!.textColumnRight,
  );
  expect(desktopHeaderLayout!.descriptionRight).toBeLessThanOrEqual(
    desktopHeaderLayout!.addButtonLeft,
  );
  expect(desktopHeaderLayout!.addButtonRight).toBeLessThanOrEqual(
    desktopHeaderLayout!.headerRight + 1,
  );
  expect(desktopScrollSizes.scrollWidth).toBeGreaterThan(desktopScrollSizes.clientWidth);

  await editor.screenshot({
    path: testInfo.outputPath('policy-replacement-sets-desktop.png'),
  });
  await testInfo.attach('policy replacement sets desktop', {
    path: testInfo.outputPath('policy-replacement-sets-desktop.png'),
    contentType: 'image/png',
  });

  const parentSelect = editor.getByRole('combobox', { name: 'Candidate parent sleeve' }).first();
  await parentSelect.focus();
  await expect(parentSelect).toBeFocused();
  await parentSelect.press('Space');
  await expect(page.getByRole('option').first()).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('option')).toHaveCount(0);
  await expect(parentSelect).toBeFocused();

  const enabledCheckbox = editor.getByRole('checkbox').first();
  await expect(enabledCheckbox).toBeChecked();
  await enabledCheckbox.click();
  await expect(enabledCheckbox).not.toBeChecked();
  await enabledCheckbox.click();
  await expect(enabledCheckbox).toBeChecked();

  await editor.getByRole('button', { name: 'Move ITOT up' }).click();
  await expect(editor.getByRole('textbox', { name: 'Security ticker' }).first()).toHaveValue(
    'ITOT',
  );
  await expect(editor.getByRole('button', { name: 'Move ITOT up' })).toBeDisabled();
  await expect(editor.getByRole('button', { name: 'Remove ITOT' })).toBeFocused();

  const addButton = editor.getByRole('button', { name: 'Add security' });
  await addButton.click();
  const newTicker = editor.getByRole('textbox', { name: 'Security ticker' }).last();
  await expect(newTicker).toBeFocused();
  await editor.getByRole('button', { name: 'Remove candidate' }).click();
  await expect(editor.getByRole('button', { name: 'Remove VTI' })).toBeFocused();

  const allConfiguredTrigger = page.locator('[data-all-replacement-sets-trigger]');
  await page.locator('[data-slot="sheet-close"]').click();
  await expect(editor).toHaveCount(0);
  await expect(allConfiguredTrigger).toBeFocused();

  const usTrigger = page.locator('[data-transition-replacement-trigger="us_equities"]');
  await usTrigger.click();
  await expect(
    editor.getByRole('heading', { name: 'Replacement sets for DEMO US Equities' }),
  ).toBeVisible();
  const usTickers = editor.getByRole('textbox', { name: 'Security ticker' });
  await expect(usTickers).toHaveCount(2);
  await usTickers.nth(1).fill('ITOTX');
  await page.locator('[data-slot="sheet-close"]').click();
  await expect(usTrigger).toBeFocused();
  await expect(page.locator('[data-us-transition-settings-root]')).toContainText('ITOTX');

  await page.setViewportSize({ width: 820, height: 1024 });
  await expectNoPageOverflow(page, 'tablet policy page');
  await usTrigger.click();
  await expect(
    editor.getByRole('heading', { name: 'Replacement sets for DEMO US Equities' }),
  ).toBeVisible();
  await expect(editor.getByRole('textbox', { name: 'Security ticker' }).nth(1)).toHaveValue(
    'ITOTX',
  );
  await page.locator('[data-slot="sheet-close"]').click();
  await expect(usTrigger).toBeFocused();
  await expectNoPageOverflow(page, 'tablet policy page after contextual editor');

  await page.locator('[data-all-replacement-sets-trigger]').click();
  await expect(
    editor.getByRole('heading', { name: 'All configured replacement sets', level: 2 }),
  ).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await expectNoPageOverflow(page, 'mobile policy page');
  const mobileHeaderLayout = await editor.evaluate((element) => {
    const description = element.querySelector<HTMLElement>('.replacement-editor-description');
    const addButton = element.querySelector<HTMLButtonElement>('button[id$="-add-candidate"]');
    const headerContainer = description?.parentElement?.parentElement;
    if (!description || !addButton || !headerContainer) return null;
    const descriptionRect = description.getBoundingClientRect();
    const headerRect = headerContainer.getBoundingClientRect();
    const addButtonRect = addButton.getBoundingClientRect();
    return {
      descriptionWidth: descriptionRect.width,
      availableHeaderWidth: headerRect.width,
      descriptionBottom: descriptionRect.bottom,
      addButtonTop: addButtonRect.top,
    };
  });
  expect(mobileHeaderLayout).not.toBeNull();
  expect(
    Math.abs(mobileHeaderLayout!.descriptionWidth - mobileHeaderLayout!.availableHeaderWidth),
  ).toBeLessThanOrEqual(2);
  expect(mobileHeaderLayout!.addButtonTop).toBeGreaterThanOrEqual(
    mobileHeaderLayout!.descriptionBottom,
  );
  const scrollSizes = await region.evaluate((element) => ({
    clientWidth: element.clientWidth,
    scrollWidth: element.scrollWidth,
  }));
  expect(scrollSizes.scrollWidth).toBeGreaterThan(scrollSizes.clientWidth);
  await editor.screenshot({
    path: testInfo.outputPath('policy-replacement-sets-mobile.png'),
  });
  await testInfo.attach('policy replacement sets mobile', {
    path: testInfo.outputPath('policy-replacement-sets-mobile.png'),
    contentType: 'image/png',
  });

  await region.focus();
  await expect(region).toBeFocused();
  await region.press('ArrowRight');
  await expect.poll(() => region.evaluate((element) => element.scrollLeft)).toBeGreaterThan(0);
  await expectNoPageOverflow(page, 'mobile policy page after table keyboard scrolling');
});

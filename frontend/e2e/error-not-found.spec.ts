import { expect, test } from './fixtures';

test('catch-all 404 is keyboard navigable and returns home on desktop and mobile', async ({
  emptyApp,
  page,
}, testInfo) => {
  for (const viewport of [
    { name: 'desktop', width: 1440, height: 1000 },
    { name: 'mobile', width: 390, height: 844 },
  ]) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await page.goto(new URL('/#/not-a-workspace-route', emptyApp.baseUrl).toString(), {
      waitUntil: 'domcontentloaded',
    });

    const main = page.getByRole('main');
    const goHome = page.getByRole('link', { name: 'Go Home', exact: true });
    await expect(main).toBeVisible();
    await expect(page.getByRole('heading', { name: '404', level: 1, exact: true })).toBeVisible();
    await expect(
      page.getByRole('heading', { name: 'Oops. Nothing here...', level: 2, exact: true }),
    ).toBeVisible();
    await expect(goHome).toHaveAttribute('data-slot', 'button');
    await expect(page.locator('main')).toHaveCount(1);

    const screenshotPath = testInfo.outputPath(`not-found-${viewport.name}.png`);
    await page.screenshot({ path: screenshotPath });
    await testInfo.attach(`404 ${viewport.name}`, {
      path: screenshotPath,
      contentType: 'image/png',
    });

    await page.keyboard.press('Tab');
    await expect(goHome).toBeFocused();
    await page.keyboard.press('Enter');
    await expect(page.getByRole('heading', { name: 'Overview', exact: true })).toBeVisible();
  }
});

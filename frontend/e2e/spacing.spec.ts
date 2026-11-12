import { expect, test } from './fixtures';

test('workspace routes keep responsive layout', async ({ page, seededApp }) => {
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 844 });
    for (const route of ['/', '/recommendations', '/lots', '/policy', '/wash-sales', '/activity']) {
      await page.goto(new URL(`/#${route}`, seededApp.baseUrl).toString());
      await expect(page.locator('.workspace-page')).toBeVisible();
      await expect(page.locator('main')).toBeVisible();
      await expect(page.locator('.workspace-page')).toHaveCSS('display', 'grid');
      await expect(page.locator('.workspace-page')).toHaveCSS('padding', '16px');
      await expect(page.locator('.workspace-page')).toHaveCSS('gap', '16px');
      await expect(page.locator('.page-header')).toHaveCSS('gap', '16px');
      if (route === '/') {
        await expect(page.locator('.page-actions')).toHaveCSS(
          'flex-wrap',
          width <= 760 ? 'wrap' : 'nowrap',
        );
      }
      await expect(page.locator('.page-header')).toHaveCSS(
        'flex-direction',
        width < 760 ? 'column' : 'row',
      );
      await expect(page.locator('.page-header > .page-heading')).toHaveCSS('margin-left', '0px');
      const pageOverflows = await page.evaluate(
        () => document.documentElement.scrollWidth > window.innerWidth + 1,
      );
      expect(pageOverflows, `${width}px ${route}`).toBe(false);
    }
  }
});

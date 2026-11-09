import { expect, test } from './fixtures';

test('Quasar spacing defaults survive the application cascade', async ({ page, seededApp }) => {
  for (const width of [1440, 768]) {
    await page.setViewportSize({ width, height: 1024 });
    for (const route of ['/', '/recommendations', '/lots', '/policy', '/wash-sales', '/activity']) {
      await page.goto(new URL(`/#${route}`, seededApp.baseUrl).toString());
      await expect(page.locator('.workspace-page')).toBeVisible();
      await expect(page.locator('.workspace-page')).toHaveCSS('padding', '16px');
      await expect(page.locator('.workspace-page')).toHaveCSS('gap', '16px');
      await expect(page.locator('.page-header > .page-heading')).toHaveCSS('margin-left', '16px');
      const mismatches = await page.evaluate(() => {
        const failures: string[] = [];
        for (const element of document.querySelectorAll<HTMLElement>(
          '.q-btn, .q-card__section--vert, .q-banner',
        )) {
          const computed = getComputedStyle(element);
          const reference = document.createElement(element.tagName);
          reference.className = [...element.classList]
            .filter((name) => name.startsWith('q-'))
            .join(' ');
          reference.style.fontSize = computed.fontSize;
          reference.style.position = 'fixed';
          reference.style.visibility = 'hidden';
          element.parentElement!.append(reference);
          const defaults = getComputedStyle(reference);
          for (const property of [
            'paddingTop',
            'paddingRight',
            'paddingBottom',
            'paddingLeft',
          ] as const) {
            if (computed[property] !== defaults[property]) {
              failures.push(
                `${element.className}: ${property} ${computed[property]} != ${defaults[property]}`,
              );
            }
          }
          if (element.matches('.workspace-page .q-btn')) {
            reference.className = [...element.classList]
              .filter((name) => /^(q-|bg-|text-)/.test(name) || name === 'disabled')
              .join(' ');
            reference.toggleAttribute('disabled', element.hasAttribute('disabled'));
            for (const property of [
              'backgroundColor',
              'color',
              'borderWidth',
              'borderRadius',
              'fontWeight',
              'opacity',
              'cursor',
            ] as const) {
              if (computed[property] !== defaults[property]) {
                failures.push(
                  `${element.className}: ${property} ${computed[property]} != ${defaults[property]}`,
                );
              }
            }
          }
          reference.remove();
        }
        if (document.documentElement.scrollWidth > innerWidth + 1) failures.push('Page overflow');
        return failures;
      });
      expect(mismatches, `${width}px ${route}`).toEqual([]);
    }
  }
});

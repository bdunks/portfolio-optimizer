import { expect, test } from './fixtures';

test('selected basket review shares a read-only route from Recommendations and navigation', async ({
  emptyApp,
  page,
}) => {
  await page.goto(new URL('/#/recommendations', emptyApp.baseUrl).toString(), {
    waitUntil: 'domcontentloaded',
  });
  await expect(page.getByRole('heading', { name: 'Recommendations', exact: true })).toBeVisible();

  const reviewEntry = page.getByRole('link', { name: 'Review selected trades', exact: true });
  await reviewEntry.focus();
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/#\/review$/);
  await expect(page.getByRole('heading', { name: 'Selected trades', exact: true })).toBeVisible();
  await expect(page.getByText('No recommendation run is loaded', { exact: false })).toBeVisible();
  await expect(
    page.getByText('does not automatically analyze a portfolio', { exact: false }),
  ).toBeVisible();
  await expect(page.locator('#selected-basket-review-title')).toBeFocused();
  await expect(page.locator('.workspace-page').getByRole('button')).toHaveCount(0);
  await expect(page.getByRole('button', { name: /preview|approve|submit order/i })).toHaveCount(0);

  await page.goBack();
  await expect(page).toHaveURL(/#\/recommendations$/);
  await expect(page.getByRole('heading', { name: 'Recommendations', exact: true })).toBeVisible();

  const sidebarReviewLink = page.getByRole('link', { name: /Selected basket/ });
  await sidebarReviewLink.focus();
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/#\/review$/);
  await expect(page.getByRole('heading', { name: 'Selected trades', exact: true })).toBeVisible();
  await expect(
    page.getByRole('link', { name: 'Back to Recommendations to edit the selection' }),
  ).toBeVisible();
  await expect(page.getByText('All analysis is non-actionable', { exact: false })).toBeVisible();
});

import { expect, test, type BrowserDemoApp } from './fixtures';
import type { Page } from '@playwright/test';

type PolicyRevision = {
  id: string;
  status: string;
  sleeves: Array<{ sleeve_key: string; display_name: string }>;
};

type PolicyResponse = {
  active: PolicyRevision | null;
  drafts: PolicyRevision[];
};

type RecommendationResponse = {
  groups: Array<{
    group_id: string;
    selected: boolean;
    rejected: boolean;
    note: string | null;
    rejection_reason: string | null;
  }>;
  consolidated_legs: Array<{
    side: string;
    selected_lots: Array<{ broker_lot_id: string; selected: boolean }>;
  }>;
};

async function expectNoHorizontalOverflow(page: Page, label: string): Promise<void> {
  const dimensions = await page.evaluate(() => ({
    viewport: window.innerWidth,
    document: document.documentElement.scrollWidth,
    body: document.body.scrollWidth,
  }));
  expect(dimensions.document, `${label} document width`).toBeLessThanOrEqual(
    dimensions.viewport + 1,
  );
  expect(dimensions.body, `${label} body width`).toBeLessThanOrEqual(dimensions.viewport + 1);
}

async function readPolicy(page: Page, app: BrowserDemoApp): Promise<PolicyResponse> {
  const response = await page.request.get(`${app.apiBaseUrl}/api/v1/policy`);
  expect(response.ok()).toBe(true);
  return (await response.json()) as PolicyResponse;
}

async function readRecommendations(
  page: Page,
  app: BrowserDemoApp,
  runId: string,
): Promise<RecommendationResponse> {
  const response = await page.request.get(
    `${app.apiBaseUrl}/api/v1/optimizer/runs/${runId}/recommendations`,
  );
  expect(response.ok()).toBe(true);
  return (await response.json()) as RecommendationResponse;
}

async function readGroup(
  page: Page,
  app: BrowserDemoApp,
  runId: string,
  groupId: string,
): Promise<RecommendationResponse['groups'][number] | undefined> {
  const recommendations = await readRecommendations(page, app, runId);
  return recommendations.groups.find((group) => group.group_id === groupId);
}

test('desktop/tablet Quasar routes and keyboard states', async ({ emptyApp, page, browser }) => {
  test.setTimeout(120_000);
  console.log(`Playwright-managed Chromium version: ${browser.version()}`);
  await page.setViewportSize({ width: 1440, height: 1000 });

  let releaseLots!: () => void;
  let signalLotsRequest!: () => void;
  let heldLots = false;
  const initialLotsRequest = new Promise<void>((resolveRequest) => {
    signalLotsRequest = resolveRequest;
  });
  const releaseInitialLots = new Promise<void>((resolveRelease) => {
    releaseLots = resolveRelease;
  });
  await page.route('**/api/v1/lots**', async (route) => {
    if (!heldLots && route.request().method() === 'GET') {
      heldLots = true;
      signalLotsRequest();
      await releaseInitialLots;
    }
    await route.continue();
  });

  try {
    await page.goto(new URL('/#/lots', emptyApp.baseUrl).toString(), {
      waitUntil: 'domcontentloaded',
    });
    await initialLotsRequest;
    await expect(
      page.getByRole('status').filter({ hasText: 'Loading tax lots from the local API' }),
    ).toBeVisible();
    releaseLots();
    await expect(page.getByRole('heading', { name: 'No lots returned' })).toBeVisible();
  } finally {
    releaseLots();
    await page.unroute('**/api/v1/lots**');
  }

  let failNextLotsRead = true;
  await page.route('**/api/v1/lots**', async (route) => {
    if (failNextLotsRead && route.request().method() === 'GET') {
      failNextLotsRead = false;
      await route.abort('failed');
      return;
    }
    await route.continue();
  });
  await page.getByRole('button', { name: 'Refresh lots' }).click();
  await expect(
    page.getByRole('alert').filter({ hasText: 'Tax lots could not be loaded' }),
  ).toBeVisible();
  await expect(page.getByRole('heading', { name: 'No lots returned' })).toBeVisible();
  await page.unroute('**/api/v1/lots**');

  await page.goto(new URL('/', emptyApp.baseUrl).toString(), { waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('heading', { name: 'Overview', exact: true })).toBeVisible();

  const nav = page.getByRole('navigation', { name: 'Primary navigation' });
  const desktopRoutes = [
    { path: '/', link: /Overview/, heading: 'Overview' },
    { path: '/recommendations', link: /Recommendations/, heading: 'Recommendations' },
    { path: '/lots', link: /Tax Lots/, heading: 'Tax Lots' },
    { path: '/policy', link: /Allocation Policy/, heading: 'Allocation Policy' },
    { path: '/wash-sales', link: /Wash Sales/, heading: 'Wash Sales' },
    { path: '/activity', link: /Activity/, heading: 'Activity' },
  ];

  await page.keyboard.press('Tab');
  await expect(page.getByRole('link', { name: 'Skip to main content' })).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.locator('#main-content')).toBeFocused();

  for (const route of [...desktopRoutes].reverse()) {
    const link = nav.getByRole('link', { name: route.link });
    await page.keyboard.press('Shift+Tab');
    await expect(link).toBeFocused();
    await page.keyboard.press('Enter');
    await expect(page.getByRole('heading', { name: route.heading, exact: true })).toBeVisible();
    await expectNoHorizontalOverflow(page, `${route.path} at desktop`);

    if (route.path === '/') {
      await expect(page.getByText(/No current matching recommendation run/)).toBeVisible();
    } else if (route.path === '/recommendations') {
      await expect(page.getByText('No recommendation run loaded')).toBeVisible();
    } else if (route.path === '/lots') {
      await expect(page.getByRole('heading', { name: 'No lots returned' })).toBeVisible();
    } else if (route.path === '/policy') {
      await expect(page.getByRole('heading', { name: 'Policy revision' })).toBeVisible();
    } else if (route.path === '/wash-sales') {
      await expect(
        page.getByRole('alert').filter({ hasText: 'Wash-sale data could not be loaded' }),
      ).toBeVisible();
      await expect(page.getByRole('heading', { name: 'No wash-sale data loaded' })).toBeVisible();
    } else if (route.path === '/activity') {
      await expect(
        page.getByRole('heading', { name: 'No activity events returned' }),
      ).toBeVisible();
    }
  }

  const tabletPage = await browser.newPage({ viewport: { width: 768, height: 1024 } });
  try {
    await tabletPage.goto(new URL('/', emptyApp.baseUrl).toString(), {
      waitUntil: 'domcontentloaded',
    });
    await expect(tabletPage.getByRole('heading', { name: 'Overview', exact: true })).toBeVisible();
    await tabletPage.keyboard.press('Tab');
    await expect(tabletPage.getByRole('link', { name: 'Skip to main content' })).toBeFocused();
    await tabletPage.keyboard.press('Enter');
    await expect(tabletPage.locator('#main-content')).toBeFocused();
    const menuButton = tabletPage.getByRole('button', { name: 'Toggle workspace navigation' });
    await tabletPage.keyboard.press('Shift+Tab');
    await expect(menuButton).toBeVisible();
    await expect(menuButton).toBeFocused();
    await tabletPage.keyboard.press('Enter');
    await expect(menuButton).toHaveAttribute('aria-expanded', 'true');
    const tabletNav = tabletPage.getByRole('navigation', { name: 'Primary navigation' });
    const tabletOverviewLink = tabletNav.getByRole('link', { name: /Overview/ });
    await tabletPage.keyboard.press('Tab');
    await expect(tabletOverviewLink).toBeFocused();
    await tabletPage.keyboard.press('Tab');
    await expect(tabletNav.getByRole('link', { name: /Recommendations/ })).toBeFocused();
    await tabletPage.keyboard.press('Tab');
    const tabletLotsLink = tabletNav.getByRole('link', { name: /Tax Lots/ });
    await expect(tabletLotsLink).toBeFocused();
    await tabletPage.keyboard.press('Enter');
    await expect(tabletPage.getByRole('heading', { name: 'Tax Lots', exact: true })).toBeVisible();

    for (const route of desktopRoutes) {
      await menuButton.click();
      await tabletNav.getByRole('link', { name: route.link }).click();
      await expect(
        tabletPage.getByRole('heading', { name: route.heading, exact: true }),
      ).toBeVisible();
      await expectNoHorizontalOverflow(tabletPage, `${route.path} at tablet`);
    }
  } finally {
    await tabletPage.close();
  }
});

test('FakeBroker policy, review, and lot workflows', async ({ seededApp, page, browser }) => {
  test.setTimeout(180_000);
  console.log(`Playwright-managed Chromium version: ${browser.version()}`);
  await page.setViewportSize({ width: 1440, height: 1000 });
  const initialPolicy = await readPolicy(page, seededApp);
  expect(initialPolicy.active).not.toBeNull();
  const originalPolicyId = initialPolicy.active!.id;
  const originalUsLabel = initialPolicy.active!.sleeves.find(
    (sleeve) => sleeve.sleeve_key === 'us_equities',
  )!.display_name;

  await page.goto(new URL('/', seededApp.baseUrl).toString(), { waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('heading', { name: 'Overview', exact: true })).toBeVisible();
  await expect(page.getByText('DEMO — Hypothetical Account')).toBeVisible();
  const startRun = page.getByRole('button', { name: 'Run DEMO recommendations' });
  await expect(startRun).toBeEnabled();
  const firstRunResponse = page.waitForResponse(
    (response) =>
      response.request().method() === 'POST' &&
      new URL(response.url()).pathname === '/api/v1/optimizer/runs',
  );
  await startRun.click();
  const firstRun = (await (await firstRunResponse).json()) as {
    run_id: string;
    policy_revision_id: string;
  };
  expect(firstRun.policy_revision_id).toBe(originalPolicyId);

  await page.getByRole('link', { name: /Recommendations/ }).click();
  await expect(page.getByRole('heading', { name: 'Ranked trade groups' })).toBeVisible();
  const firstFrozenContext = page.getByRole('region', { name: 'Frozen run display context' });
  await expect(firstFrozenContext).toContainText(originalUsLabel);

  await page.getByRole('link', { name: /Allocation Policy/ }).click();
  await expect(page.getByRole('heading', { name: 'Policy revision' })).toBeVisible();
  const retainedLoss = page.getByLabel('Target retained net loss (USD)');
  const sleeveName = page.getByLabel('Sleeve display name').first();
  await retainedLoss.fill('3456.78');
  await sleeveName.fill('Browser renamed US equities');
  await page.getByRole('link', { name: /Activity/ }).click();
  await expect(page.getByRole('heading', { name: 'Activity', exact: true })).toBeVisible();
  await page.getByRole('link', { name: /Allocation Policy/ }).click();
  await expect(retainedLoss).toHaveValue('3456.78');
  await expect(sleeveName).toHaveValue('Browser renamed US equities');
  await page.getByRole('button', { name: 'Refresh policy list' }).click();
  await expect(retainedLoss).toHaveValue('3456.78');

  await page.getByRole('button', { name: 'Save new draft revision' }).click();
  await expect(page.getByText(/Current form matches saved revision/)).toBeVisible();
  const draftPolicy = await readPolicy(page, seededApp);
  const savedDraft = draftPolicy.drafts.find((revision) => revision.status === 'DRAFT');
  expect(savedDraft).toBeDefined();
  await retainedLoss.fill('4567.89');
  await page.getByRole('combobox', { name: 'Select policy source revision' }).click();
  await page.getByRole('option').filter({ hasText: originalPolicyId }).click();
  await expect(
    page.getByText('There are unsaved edits. Loading another revision will discard them.'),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Discard edits and load' }).click();
  await expect(retainedLoss).toHaveValue('3000');
  await expect(sleeveName).toHaveValue(originalUsLabel);

  await page.getByRole('combobox', { name: 'Select policy source revision' }).click();
  await page.getByRole('option').filter({ hasText: savedDraft!.id }).click();
  await expect(retainedLoss).toHaveValue('3456.78');
  await expect(sleeveName).toHaveValue('Browser renamed US equities');
  const activateDraft = page.getByRole('button', { name: 'Activate saved revision' });
  await expect(activateDraft).toBeEnabled();
  await activateDraft.click();
  await expect(page.getByText(/Current form matches saved revision/)).toBeVisible();
  const activatedPolicy = await readPolicy(page, seededApp);
  expect(activatedPolicy.active?.id).toBe(savedDraft!.id);
  const renamedUsSleeve = activatedPolicy.active?.sleeves.find(
    (sleeve) => sleeve.sleeve_key === 'us_equities',
  )?.display_name;
  expect(renamedUsSleeve).toBe('Browser renamed US equities');

  await page.getByRole('link', { name: /Recommendations/ }).click();
  await expect(page.getByRole('heading', { name: 'Ranked trade groups' })).toBeVisible();
  const frozenContext = page.getByRole('region', { name: 'Frozen run display context' });
  await expect(frozenContext).toContainText(originalUsLabel);
  await expect(frozenContext).not.toContainText('Browser renamed US equities');
  expect(firstRun.run_id).toBeTruthy();

  const rerun = page.getByRole('button', { name: 'Run DEMO recommendations' });
  await expect(rerun).toBeEnabled();
  const currentRunResponse = page.waitForResponse(
    (response) =>
      response.request().method() === 'POST' &&
      new URL(response.url()).pathname === '/api/v1/optimizer/runs',
  );
  await rerun.click();
  const currentRun = (await (await currentRunResponse).json()) as { run_id: string };
  await expect(page.getByRole('heading', { name: 'Ranked trade groups' })).toBeVisible();

  await expect(page.getByRole('status').filter({ hasText: currentRun.run_id })).toBeVisible();

  await page.getByRole('link', { name: /Tax Lots/ }).click();
  const lotSearch = page.getByLabel('Search all account lots');
  await lotSearch.fill('DEMO-VB-LOT-1');
  await page.getByRole('button', { name: 'Apply API filters' }).click();
  const vbLot = page.getByRole('checkbox', { name: 'Request VB lot DEMO-VB-LOT-1' });
  await expect(vbLot).toBeVisible();
  await vbLot.check();
  await expect(page.getByRole('heading', { name: /Requested lot intent/ })).toContainText('1');
  await expect(
    page.getByText('The loaded DEMO run currently selects exactly this requested set.'),
  ).not.toBeVisible();
  await expect(page.getByRole('button', { name: /Approve|Order preview/i })).toHaveCount(0);
  await page.getByRole('button', { name: 'Apply complete set to current DEMO run' }).click();
  await expect(
    page.getByText(/The loaded DEMO run currently selects exactly this requested set/),
  ).toBeVisible();
  const confirmedLots = await readRecommendations(page, seededApp, currentRun.run_id);
  const selectedSellLots = confirmedLots.consolidated_legs
    .filter((leg) => leg.side === 'SELL')
    .flatMap((leg) =>
      leg.selected_lots.filter((lot) => lot.selected).map((lot) => lot.broker_lot_id),
    );
  expect(selectedSellLots).toEqual(['DEMO-VB-LOT-1']);

  await page.getByRole('link', { name: /Recommendations/ }).click();
  await expect(page.getByRole('heading', { name: 'Ranked trade groups' })).toBeVisible();
  const groupCard = page.locator('.q-expansion-item.group-card').first();
  const groupLabel = await groupCard.getAttribute('aria-label');
  const groupId = groupLabel?.replace('Recommendation group ', '');
  if (!groupId) throw new Error('The first recommendation group has no identifier');
  if ((await groupCard.locator('.group-header').getAttribute('aria-expanded')) !== 'true') {
    await groupCard.locator('.group-header').click();
  }
  const groupCheckbox = groupCard.getByRole('checkbox', {
    name: `Select recommendation group ${groupId}`,
  });
  if (!(await groupCheckbox.isChecked())) {
    await groupCheckbox.check();
    await expect(groupCheckbox).toBeChecked();
  }

  let releasePendingAnnotation!: () => void;
  let signalPendingAnnotation!: () => void;
  const pendingAnnotation = new Promise<void>((resolvePending) => {
    signalPendingAnnotation = resolvePending;
  });
  const continueAnnotation = new Promise<void>((resolveContinue) => {
    releasePendingAnnotation = resolveContinue;
  });
  let holdNextAnnotation = true;
  await page.route('**/api/v1/optimizer/runs/**/recommendations/**', async (route) => {
    if (route.request().method() === 'PATCH' && holdNextAnnotation) {
      holdNextAnnotation = false;
      signalPendingAnnotation();
      await continueAnnotation;
    }
    await route.continue();
  });

  try {
    const noteField = groupCard.locator('textarea');
    await noteField.fill('E2E note across route remount');
    await groupCard.getByRole('button', { name: 'Save note' }).click();
    await pendingAnnotation;
    await expect(
      page.getByText(/The requested selection or annotation is being saved or re-solved/),
    ).toBeVisible();
    await page.getByRole('link', { name: /Activity/ }).click();
    await expect(page.getByRole('heading', { name: 'Activity', exact: true })).toBeVisible();
    await page.getByRole('link', { name: /Recommendations/ }).click();
    await expect(
      page.getByText(/The requested selection or annotation is being saved or re-solved/),
    ).toBeVisible();
    releasePendingAnnotation();
    await expect(
      page.getByText(/The requested selection or annotation is being saved or re-solved/),
    ).not.toBeVisible();
    await expect
      .poll(async () => (await readGroup(page, seededApp, currentRun.run_id, groupId))?.note)
      .toBe('E2E note across route remount');
  } finally {
    releasePendingAnnotation();
    await page.unroute('**/api/v1/optimizer/runs/**/recommendations/**');
  }
  if ((await groupCard.locator('.group-header').getAttribute('aria-expanded')) !== 'true') {
    await groupCard.locator('.group-header').click();
  }
  const restoredNoteField = groupCard.locator('textarea');
  await restoredNoteField.fill('');
  await groupCard.getByRole('button', { name: 'Save note' }).click();
  await expect(restoredNoteField).toHaveValue('');
  await expect
    .poll(async () => (await readGroup(page, seededApp, currentRun.run_id, groupId))?.note)
    .toBeNull();

  let failNextRejection = true;
  await page.route('**/api/v1/optimizer/runs/**/recommendations/**', async (route) => {
    if (route.request().method() === 'PATCH' && failNextRejection) {
      failNextRejection = false;
      await route.abort('failed');
      return;
    }
    await route.continue();
  });
  try {
    const rejectionReason = groupCard.getByLabel('Rejection reason (up to 500 characters)');

    if ((await groupCard.locator('.group-header').getAttribute('aria-expanded')) !== 'true') {
      await groupCard.locator('.group-header').click();
    }
    await expect(rejectionReason).toBeVisible();
    await rejectionReason.fill('Controlled E2E rejection rollback');
    await groupCard
      .getByRole('button', { name: 'Reject group (does not approve any order)' })
      .click();
    await expect(
      page.getByRole('alert').filter({ hasText: 'Group note or rejection was not saved' }),
    ).toBeVisible();
    if ((await groupCard.locator('.group-header').getAttribute('aria-expanded')) !== 'true') {
      await groupCard.locator('.group-header').click();
    }
    await expect(groupCheckbox).toBeChecked();
    await expect
      .poll(async () => {
        const group = await readGroup(page, seededApp, currentRun.run_id, groupId);
        return { selected: group?.selected, rejected: group?.rejected, note: group?.note };
      })
      .toEqual({ selected: true, rejected: false, note: null });

    await groupCard
      .getByRole('button', { name: 'Reject group (does not approve any order)' })
      .click();
    await expect
      .poll(async () => {
        const group = await readGroup(page, seededApp, currentRun.run_id, groupId);
        return {
          selected: group?.selected,
          rejected: group?.rejected,
          reason: group?.rejection_reason,
        };
      })
      .toEqual({ selected: false, rejected: true, reason: 'Controlled E2E rejection rollback' });
    if ((await groupCard.locator('.group-header').getAttribute('aria-expanded')) !== 'true') {
      await groupCard.locator('.group-header').click();
    }
    await expect(
      page.getByText('Saved rejection reason: Controlled E2E rejection rollback'),
    ).toBeVisible();
  } finally {
    await page.unroute('**/api/v1/optimizer/runs/**/recommendations/**');
  }
});

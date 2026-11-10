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

async function expectDrawerSettled(page: Page, open: boolean): Promise<void> {
  const drawer = page.locator('aside.q-drawer');
  await expect
    .poll(() =>
      drawer.evaluate((element, shouldBeOpen) => {
        const rect = element.getBoundingClientRect();
        const fullyVisible = rect.left >= 0 && rect.right <= window.innerWidth && rect.width > 0;
        const fullyHidden = rect.right <= 0;
        const transitioning = element
          .getAnimations({ subtree: true })
          .some((animation) => animation.playState === 'running');
        return !transitioning && (shouldBeOpen ? fullyVisible : fullyHidden);
      }, open),
    )
    .toBe(true);
}

type ContrastSample = {
  foreground: string;
  background: string;
  visible: boolean;
};

type NavigationContrastSnapshot = {
  header: ContrastSample;
  brandTitle: ContrastSample;
  brandSubtitle: ContrastSample;
  footerTitle: ContrastSample;
  footerBody: ContrastSample;
  links: Array<{
    path: string | null;
    active: boolean;
    primary: ContrastSample;
    caption: ContrastSample;
    icon: ContrastSample;
  }>;
};

async function readNavigationContrast(page: Page): Promise<NavigationContrastSnapshot> {
  const screenshotBase64 = (await page.screenshot()).toString('base64');
  return page.evaluate(async (encodedScreenshot) => {
    const drawer = document.querySelector<HTMLElement>('aside.q-drawer');
    const navigation = drawer?.querySelector<HTMLElement>('nav[aria-label="Primary navigation"]');
    const header = navigation?.querySelector<HTMLElement>('.q-item__label--header');
    if (!drawer || !navigation || !header) {
      throw new Error('Workspace drawer navigation is missing');
    }

    const brand = drawer.querySelector<HTMLElement>('.drawer-brand');
    const brandTitle = brand?.querySelector<HTMLElement>('strong');
    const brandSubtitle = brand?.querySelector<HTMLElement>('small');
    const footer = drawer.querySelector<HTMLElement>('.drawer-footer');
    const footerTitle = footer?.querySelector<HTMLElement>('strong');
    const footerBody = footer?.querySelector<HTMLElement>('span');
    if (!brand || !brandTitle || !brandSubtitle || !footer || !footerTitle || !footerBody) {
      throw new Error('Workspace drawer branding or footer is missing');
    }

    const image = new Image();
    image.src = `data:image/png;base64,${encodedScreenshot}`;
    await image.decode();
    const canvas = document.createElement('canvas');
    canvas.width = image.naturalWidth;
    canvas.height = image.naturalHeight;
    const context = canvas.getContext('2d', { willReadFrequently: true });
    if (!context) throw new Error('Unable to sample the rendered drawer screenshot');
    context.drawImage(image, 0, 0);

    const scaleX = canvas.width / window.innerWidth;
    const scaleY = canvas.height / window.innerHeight;
    const drawerRect = drawer.getBoundingClientRect();
    const drawerOnScreen =
      drawerRect.left >= 0 && drawerRect.right <= window.innerWidth && drawerRect.width > 0;

    function isFullyOpaqueAndVisible(element: HTMLElement): boolean {
      let opacity = 1;
      for (
        let ancestor: HTMLElement | null = element;
        ancestor;
        ancestor = ancestor.parentElement
      ) {
        const style = getComputedStyle(ancestor);
        if (
          style.display === 'none' ||
          style.visibility === 'hidden' ||
          style.visibility === 'collapse'
        ) {
          return false;
        }
        const ancestorOpacity = Number(style.opacity);
        if (!Number.isFinite(ancestorOpacity)) return false;
        opacity *= ancestorOpacity;
      }
      return opacity === 1;
    }

    function sample(element: HTMLElement, backgroundBox: HTMLElement): ContrastSample {
      const elementRect = element.getBoundingClientRect();
      const backgroundRect = backgroundBox.getBoundingClientRect();
      const visible =
        drawerOnScreen &&
        isFullyOpaqueAndVisible(element) &&
        element.getClientRects().length > 0 &&
        elementRect.width > 0 &&
        elementRect.height > 0 &&
        elementRect.top >= 0 &&
        elementRect.bottom <= window.innerHeight &&
        backgroundRect.right - 24 >= 0 &&
        backgroundRect.right - 24 < window.innerWidth;
      if (!visible) return { foreground: '', background: '', visible: false };

      // Sample inside the painted row, away from glyphs and the drawer scrollbar.
      const x = Math.floor((backgroundRect.right - 24) * scaleX);
      const y = Math.floor((elementRect.top + elementRect.height / 2) * scaleY);
      const pixel = context!.getImageData(x, y, 1, 1).data;
      return {
        foreground: getComputedStyle(element).color,
        background: `rgb(${pixel[0]}, ${pixel[1]}, ${pixel[2]})`,
        visible: true,
      };
    }

    const links = Array.from(navigation.querySelectorAll<HTMLElement>('.q-item')).map((item) => {
      const primary = item.querySelector<HTMLElement>(
        '.q-item__label:not(.q-item__label--caption)',
      );
      const caption = item.querySelector<HTMLElement>('.q-item__label--caption');
      const icon = item.querySelector<HTMLElement>('.q-icon');
      if (!primary || !caption || !icon) throw new Error('Navigation item is incomplete');
      return {
        path: item.getAttribute('href'),
        active: item.getAttribute('aria-current') === 'page',
        primary: sample(primary, item),
        caption: sample(caption, item),
        icon: sample(icon, item),
      };
    });
    const headerBackground = header.parentElement;
    if (!headerBackground) throw new Error('Workspace heading has no painted background');
    return {
      header: sample(header, headerBackground),
      brandTitle: sample(brandTitle, brand),
      brandSubtitle: sample(brandSubtitle, brand),
      footerTitle: sample(footerTitle, footer),
      footerBody: sample(footerBody, footer),
      links,
    };
  }, screenshotBase64);
}

function contrastRatio(foreground: string, background: string): number {
  const channels = (color: string): [number, number, number] => {
    const values = color.match(/[\d.]+/g)?.map(Number);
    if (!values || values.length < 3) throw new Error(`Unsupported computed color: ${color}`);
    return [values[0]!, values[1]!, values[2]!].map((value) => {
      const linear = value / 255;
      return linear <= 0.04045 ? linear / 12.92 : ((linear + 0.055) / 1.055) ** 2.4;
    }) as [number, number, number];
  };
  const luminance = (color: string): number => {
    const [red, green, blue] = channels(color);
    return red * 0.2126 + green * 0.7152 + blue * 0.0722;
  };
  const first = luminance(foreground);
  const second = luminance(background);
  return (Math.max(first, second) + 0.05) / (Math.min(first, second) + 0.05);
}

async function expectReadableNavigation(page: Page, viewport: string): Promise<void> {
  const snapshot = await readNavigationContrast(page);
  expect(snapshot.links).toHaveLength(6);
  expect(snapshot.links.filter((link) => link.active)).toHaveLength(1);
  for (const [label, sample] of [
    ['Workspace heading', snapshot.header],
    ['Drawer branding', snapshot.brandTitle],
    ['Brand subtitle', snapshot.brandSubtitle],
    ['Footer title', snapshot.footerTitle],
    ['Footer text', snapshot.footerBody],
  ] as const) {
    expect(sample.visible, `${viewport} ${label} is painted`).toBe(true);
    const ratio = contrastRatio(sample.foreground, sample.background);
    expect(
      ratio,
      `${viewport} ${label} contrast: ${sample.foreground} on ${sample.background}`,
    ).toBeGreaterThanOrEqual(4.5);
    console.log(
      `${viewport} ${label}: ${sample.foreground} on ${sample.background} (${ratio.toFixed(2)}:1)`,
    );
  }

  for (const link of snapshot.links) {
    const label = `${viewport} ${link.path ?? 'navigation link'}${link.active ? ' (active)' : ''}`;
    for (const [part, sample, minimum] of [
      ['label', link.primary, 4.5],
      ['caption', link.caption, 4.5],
      ['icon', link.icon, 3],
    ] as const) {
      expect(sample.visible, `${label} ${part} is painted in the open drawer`).toBe(true);
      const ratio = contrastRatio(sample.foreground, sample.background);
      expect(
        ratio,
        `${label} ${part} contrast: ${sample.foreground} on ${sample.background}`,
      ).toBeGreaterThanOrEqual(minimum);
      console.log(
        `${label} ${part}: ${sample.foreground} on ${sample.background} (${ratio.toFixed(2)}:1)`,
      );
    }
  }
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

test('workspace navigation contrast uses the painted drawer surface on desktop and tablet', async ({
  emptyApp,
  page,
  browser,
}) => {
  test.setTimeout(120_000);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto(new URL('/', emptyApp.baseUrl).toString(), { waitUntil: 'domcontentloaded' });

  const navigation = page.getByRole('navigation', { name: 'Primary navigation' });
  const overviewLink = navigation.getByRole('link', { name: /Overview/ });
  const recommendationsLink = navigation.getByRole('link', { name: /Recommendations/ });
  await expect(overviewLink).toHaveAttribute('aria-current', 'page');
  await expectReadableNavigation(page, 'desktop overview');

  const probeItem = navigation.locator('.q-item').nth(1);
  const probeText = probeItem.locator('.q-item__label:not(.q-item__label--caption)');
  const originalItemStyle = await probeItem.getAttribute('style');
  const originalTextStyle = await probeText.getAttribute('style');
  const expectProbeRejected = async (reason: string): Promise<void> => {
    const sample = (await readNavigationContrast(page)).links.find((link) =>
      link.path?.endsWith('/recommendations'),
    )?.primary;
    expect(sample?.visible, reason).toBe(false);
  };
  try {
    await probeText.evaluate((element) => (element.style.visibility = 'hidden'));
    await expectProbeRejected('visibility:hidden target must be rejected');
    await probeText.evaluate((element) => element.style.removeProperty('visibility'));

    await probeText.evaluate((element) => (element.style.display = 'none'));
    await expectProbeRejected('display:none target must be rejected');
    await probeText.evaluate((element) => element.style.removeProperty('display'));

    await probeText.evaluate((element) => (element.style.opacity = '0'));
    await expectProbeRejected('opacity:0 target must be rejected');
    await probeText.evaluate((element) => element.style.removeProperty('opacity'));

    await probeItem.evaluate((element) => (element.style.opacity = '0.5'));
    await expectProbeRejected('partially transparent ancestor must be rejected');
  } finally {
    await probeText.evaluate((element, style) => {
      if (style === null) element.removeAttribute('style');
      else element.setAttribute('style', style);
    }, originalTextStyle);
    await probeItem.evaluate((element, style) => {
      if (style === null) element.removeAttribute('style');
      else element.setAttribute('style', style);
    }, originalItemStyle);
  }

  await recommendationsLink.click();
  await expect(page.getByRole('heading', { name: 'No recommendation run loaded' })).toBeVisible();
  await expect(recommendationsLink).toHaveAttribute('aria-current', 'page');
  await expect(overviewLink).not.toHaveAttribute('aria-current', 'page');
  await expectDrawerSettled(page, true);
  await expectReadableNavigation(page, 'desktop recommendations');

  const tabletPage = await browser.newPage({ viewport: { width: 768, height: 1024 } });
  try {
    await tabletPage.goto(new URL('/#/recommendations', emptyApp.baseUrl).toString(), {
      waitUntil: 'domcontentloaded',
    });
    await expect(
      tabletPage.getByRole('heading', { name: 'No recommendation run loaded' }),
    ).toBeVisible();
    const menuButton = tabletPage.getByRole('button', { name: 'Toggle workspace navigation' });
    await expect(menuButton).toHaveAttribute('aria-expanded', 'false');
    await expectDrawerSettled(tabletPage, false);
    await menuButton.click();
    await expect(menuButton).toHaveAttribute('aria-expanded', 'true');
    await expectDrawerSettled(tabletPage, true);
    await expectReadableNavigation(tabletPage, 'tablet overlay recommendations');

    const tabletNavigation = tabletPage.getByRole('navigation', { name: 'Primary navigation' });
    const taxLotsLink = tabletNavigation.getByRole('link', { name: /Tax Lots/ });
    await taxLotsLink.click();
    await expect(tabletPage.getByRole('heading', { name: 'Tax Lots', exact: true })).toBeVisible();
    await expect(menuButton).toHaveAttribute('aria-expanded', 'false');
    await expectDrawerSettled(tabletPage, false);
    await menuButton.click();
    await expect(menuButton).toHaveAttribute('aria-expanded', 'true');
    await expectDrawerSettled(tabletPage, true);
    await expect(taxLotsLink).toHaveAttribute('aria-current', 'page');
    await expectReadableNavigation(tabletPage, 'tablet overlay tax lots');
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
  await page.setViewportSize({ width: 768, height: 1024 });
  const sleeveRegion = page.getByRole('region', { name: 'Sleeve allocation policy settings' });
  await expect(sleeveRegion).toHaveAttribute('tabindex', '0');
  await expect(sleeveRegion.locator('.q-markup-table table')).toHaveCount(1);
  await expect(sleeveRegion.locator('thead th:not([scope="col"])')).toHaveCount(0);
  await expect
    .poll(() => sleeveRegion.evaluate((element) => element.scrollWidth > element.clientWidth))
    .toBe(true);
  await expectNoHorizontalOverflow(page, 'policy table at tablet');
  const retainedLoss = page.getByLabel('Target retained net loss (USD)');
  const sleeveName = page.getByLabel('Sleeve display name').first();
  await retainedLoss.fill('3456.78');
  await sleeveName.fill('Browser renamed US equities');
  await page.setViewportSize({ width: 1440, height: 1000 });
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
  await page.setViewportSize({ width: 768, height: 1024 });
  const lotRegion = page.locator('[role="region"][aria-label^="Tax lots for "]').first();
  await expect(lotRegion).toBeVisible();
  await expect(lotRegion).toHaveAttribute('tabindex', '0');
  await expect(lotRegion.locator('.q-markup-table table')).toHaveCount(1);
  await expect(lotRegion.locator('thead th:not([scope="col"])')).toHaveCount(0);
  await expect
    .poll(() => lotRegion.evaluate((element) => element.scrollWidth > element.clientWidth))
    .toBe(true);
  await expectNoHorizontalOverflow(page, 'tax-lot table at tablet');
  await lotRegion.focus();
  await expect(lotRegion).toBeFocused();
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
  await page.setViewportSize({ width: 1440, height: 1000 });
  const confirmedLots = await readRecommendations(page, seededApp, currentRun.run_id);
  const selectedSellLots = confirmedLots.consolidated_legs
    .filter((leg) => leg.side === 'SELL')
    .flatMap((leg) =>
      leg.selected_lots.filter((lot) => lot.selected).map((lot) => lot.broker_lot_id),
    );
  expect(selectedSellLots).toEqual(['DEMO-VB-LOT-1']);

  await page.getByRole('link', { name: /Recommendations/ }).click();
  await expect(page.getByRole('heading', { name: 'Ranked trade groups' })).toBeVisible();
  const groupCard = page.getByLabel(/^Recommendation group /).first();
  const groupLabel = await groupCard.getAttribute('aria-label');
  const groupId = groupLabel?.replace('Recommendation group ', '');
  if (!groupId) throw new Error('The first recommendation group has no identifier');
  const groupHeader = groupCard.locator('.group-header');
  if ((await groupHeader.getAttribute('aria-expanded')) !== 'true') {
    await groupHeader.click();
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
  if ((await groupHeader.getAttribute('aria-expanded')) !== 'true') {
    await groupHeader.click();
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

    if ((await groupHeader.getAttribute('aria-expanded')) !== 'true') {
      await groupHeader.click();
    }
    await expect(rejectionReason).toBeVisible();
    await rejectionReason.fill('Controlled E2E rejection rollback');
    await groupCard
      .getByRole('button', { name: 'Reject group (does not approve any order)' })
      .click();
    await expect(
      page.getByRole('alert').filter({ hasText: 'Group note or rejection was not saved' }),
    ).toBeVisible();
    if ((await groupHeader.getAttribute('aria-expanded')) !== 'true') {
      await groupHeader.click();
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
    if ((await groupHeader.getAttribute('aria-expanded')) !== 'true') {
      await groupHeader.click();
    }
    await expect(
      page.getByText('Saved rejection reason: Controlled E2E rejection rollback'),
    ).toBeVisible();
  } finally {
    await page.unroute('**/api/v1/optimizer/runs/**/recommendations/**');
  }
});

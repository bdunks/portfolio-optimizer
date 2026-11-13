import { expect, test, type BrowserDemoApp } from './fixtures';
import type { Locator, Page, Route } from '@playwright/test';

type PolicyRevision = {
  id: string;
  revision_number: number;
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
    rank: number;
    group_type: string;
    rationale: string;
    impact: { selected_sell_lots_count: number; realized_st_usd: string; realized_lt_usd: string };
    leg_ids: string[];
    selected: boolean;
    rejected: boolean;
    note: string | null;
    rejection_reason: string | null;
  }>;
  consolidated_legs: Array<{
    leg_id: string;
    sequence: number;
    group_ids: string[];
    side: string;
    shares: string;
    selected: boolean;
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

test('prefixed Tailwind radius tokens resolve on workspace controls', async ({
  emptyApp,
  page,
}) => {
  const baseUrl = emptyApp.baseUrl;
  const readControlStyle = async (locator: Locator) =>
    locator.evaluate((element) => ({
      className: element.getAttribute('class') ?? '',
      borderRadius: getComputedStyle(element).borderRadius,
    }));

  await page.goto(new URL('/#/', baseUrl).toString(), { waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('heading', { name: 'Overview', exact: true })).toBeVisible();
  const defaultButton = await readControlStyle(
    page.getByRole('button', { name: 'Sync portfolio', exact: true }),
  );
  const radiusTokens = await page.evaluate(() => {
    const style = getComputedStyle(document.documentElement);
    return {
      semantic: style.getPropertyValue('--radius-md').trim(),
      prefixed: style.getPropertyValue('--tw-radius-md').trim(),
    };
  });

  await page.goto(new URL('/#/recommendations', baseUrl).toString(), {
    waitUntil: 'domcontentloaded',
  });
  await expect(page.getByRole('heading', { name: 'Recommendations', exact: true })).toBeVisible();
  const demoButton = await readControlStyle(
    page.getByRole('button', { name: 'Run DEMO recommendations' }),
  );
  const recommendationsMaxWidth = await page
    .locator('.workspace-page')
    .evaluate((element) => getComputedStyle(element).maxWidth);

  await page.goto(new URL('/#/lots', baseUrl).toString(), { waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('heading', { name: 'Tax Lots', exact: true })).toBeVisible();
  const searchInput = await readControlStyle(page.locator('#tax-lot-search'));
  const refreshButton = await readControlStyle(
    page.getByRole('button', { name: 'Refresh lots', exact: true }),
  );
  expect(radiusTokens.semantic).toBe('calc(0.625rem * 0.8)');
  expect(radiusTokens.prefixed).toBe(radiusTokens.semantic);
  expect(defaultButton.className).toContain('tw:rounded-lg');
  expect(defaultButton.borderRadius).toBe('10px');
  expect(demoButton.className).toContain('tw:rounded-[min(var(--radius-md),12px)]');
  expect(demoButton.borderRadius).toBe('8px');
  expect(searchInput.className).toContain('tw:rounded-lg');
  expect(searchInput.borderRadius).toBe('8px');
  expect(refreshButton.className).toContain('tw:rounded-[min(var(--radius-md),12px)]');
  expect(refreshButton.borderRadius).toBe('8px');
  expect(recommendationsMaxWidth).toBe('1600px');
});
async function expectOverviewSummaryGrid(
  page: Page,
  viewport: string,
  columns: number,
): Promise<void> {
  const cards = page.locator('.overview-summary-grid [data-slot="card"]');
  await expect(cards).toHaveCount(4);
  const cardColumns = await cards.evaluateAll(
    (elements) =>
      new Set(elements.map((element) => Math.round(element.getBoundingClientRect().x))).size,
  );
  expect(cardColumns, `${viewport} overview summary card columns`).toBe(columns);
}

async function expectOverviewContentGrid(
  page: Page,
  viewport: string,
  columns: number,
): Promise<void> {
  const grid = page.locator('.overview-page .content-grid');
  const columnXs = await grid
    .locator(':scope > *')
    .evaluateAll((elements) => elements.map((element) => element.getBoundingClientRect().x));
  const columnCount = new Set(columnXs.map((x) => Math.round(x))).size;
  const message = `${viewport} overview content grid columns`;
  expect(columnCount, message).toBe(columns);
}

async function expectOverviewHeadingTypography(page: Page, viewport: string): Promise<void> {
  const headings = [
    { name: 'Portfolio data', level: 2, size: 18 },
    { name: 'Data coverage', level: 3, size: 14 },
    { name: 'Latest recommendations', level: 2, size: 18 },
    { name: 'Active allocation policy', level: 2, size: 18 },
    { name: 'Active allocation targets', level: 3, size: 14, lineHeightRatio: 1.43 },
    { name: 'Active replacement sets', level: 3, size: 14, lineHeightRatio: 1.43 },
  ];

  for (const expected of headings) {
    const heading = page.getByRole('heading', {
      name: expected.name,
      level: expected.level,
      exact: true,
    });
    await expect(heading, `${viewport} ${expected.name} heading`).toBeVisible();
    const typography = await heading.evaluate((element) => {
      const style = getComputedStyle(element);
      return {
        fontSize: style.fontSize,
        fontWeight: style.fontWeight,
        lineHeight: style.lineHeight,
      };
    });
    expect(typography.fontSize, `${viewport} ${expected.name} font-size`).toBe(
      `${expected.size}px`,
    );
    expect(typography.fontWeight, `${viewport} ${expected.name} font-weight`).toBe('600');
    const lineHeightRatio = typography.lineHeight.endsWith('px')
      ? Number.parseFloat(typography.lineHeight) / expected.size
      : Number.parseFloat(typography.lineHeight);
    expect(lineHeightRatio, `${viewport} ${expected.name} line-height`).toBeCloseTo(
      expected.lineHeightRatio ?? 1.25,
    );
  }
}

async function expectOverviewActionsInViewport(page: Page, viewport: string): Promise<void> {
  const actions = page.locator('.overview-page .page-actions button');
  await expect(actions).toHaveCount(2);
  const dimensions = await actions.evaluateAll((elements) =>
    elements.map((element) => {
      const rect = element.getBoundingClientRect();
      return {
        left: rect.left,
        right: rect.right,
        top: rect.top,
        bottom: rect.bottom,
        width: rect.width,
        height: rect.height,
      };
    }),
  );
  const viewportWidth = await page.evaluate(() => window.innerWidth);
  const viewportHeight = await page.evaluate(() => window.innerHeight);
  for (const [index, action] of dimensions.entries()) {
    expect(action.width, `${viewport} overview action ${index + 1} width`).toBeGreaterThan(0);
    expect(action.height, `${viewport} overview action ${index + 1} height`).toBeGreaterThan(0);
    expect(action.top, `${viewport} overview action ${index + 1} top edge`).toBeGreaterThanOrEqual(
      0,
    );
    expect(
      action.bottom,
      `${viewport} overview action ${index + 1} bottom edge`,
    ).toBeLessThanOrEqual(viewportHeight);
    expect(
      action.left,
      `${viewport} overview action ${index + 1} left edge`,
    ).toBeGreaterThanOrEqual(0);
    expect(action.right, `${viewport} overview action ${index + 1} right edge`).toBeLessThanOrEqual(
      viewportWidth + 1,
    );
  }
}

async function scrollOverviewToTop(page: Page, viewport: string): Promise<void> {
  await page.evaluate(() => window.scrollTo(0, 0));
  await expect
    .poll(() => page.evaluate(() => window.scrollY), `${viewport} overview scroll position`)
    .toBe(0);
}

async function expectAllocationHeadingFontSize(page: Page, viewport: string): Promise<void> {
  const heading = page.getByRole('heading', {
    name: 'Portfolio Allocation',
    level: 2,
    exact: true,
  });
  await expect(heading).toBeVisible();
  const fontSize = await heading.evaluate((element) => getComputedStyle(element).fontSize);
  expect(fontSize, `${viewport} allocation heading computed font-size`).toBe('18px');
}

async function expectTransitionLayout(
  root: Locator,
  viewport: string,
  wide: boolean,
  provenanceLabel: string,
): Promise<void> {
  await expect(root).toBeVisible();
  await expect(root.getByText(provenanceLabel, { exact: true })).toBeVisible();

  const comparison = root.getByRole('region', {
    name: 'US allocation transition comparison',
  });
  await expect(comparison).toBeVisible();
  const table = comparison.getByRole('table');
  await expect(table).toBeVisible();
  await expect(table.getByRole('caption')).toHaveText(
    'Current, after selected trades, and configured target percentages within the US sleeve',
  );

  const columnLabels = await table.getByRole('columnheader').allTextContents();
  expect(
    columnLabels.map((label) => label.trim()),
    `${viewport} transition state columns`,
  ).toEqual(['Allocation sleeve', 'Current', 'After selected trades', 'Target']);
  const summaryLabels = await root
    .locator('.whole-portfolio-summary .summary-label')
    .allTextContents();
  expect(
    summaryLabels.map((label) => label.trim()),
    `${viewport} whole-portfolio states`,
  ).toEqual([
    'Current US sleeve · of whole portfolio',
    'After selected trades · of whole portfolio',
    'Target US sleeve · of whole portfolio',
  ]);
  await expect(root.locator('.whole-portfolio-summary strong')).toHaveCount(3);

  const bodyRows = await table.locator('tbody tr').evaluateAll((rows) =>
    rows.map((row) => ({
      rowHeaders: row.querySelectorAll('th[scope="row"]').length,
      stateCellColspans: Array.from(row.querySelectorAll('td')).map((cell) => cell.colSpan),
    })),
  );
  expect(bodyRows.length, `${viewport} transition component rows`).toBeGreaterThan(0);
  for (const [index, row] of bodyRows.entries()) {
    expect(row.rowHeaders, `${viewport} transition row ${index + 1} label`).toBe(1);
    const hasThreeStateValues =
      row.stateCellColspans.length === 3 && row.stateCellColspans.every((colspan) => colspan === 1);
    const hasUnavailableStatePlaceholder =
      row.stateCellColspans.length === 1 && row.stateCellColspans[0] === 3;
    expect(
      hasThreeStateValues || hasUnavailableStatePlaceholder,
      `${viewport} transition row ${index + 1} has current, proposed, and target cells`,
    ).toBe(true);
  }

  const comparisonLayout = await comparison.evaluate((element) => ({
    clientWidth: element.clientWidth,
    scrollWidth: element.scrollWidth,
  }));
  expect(comparisonLayout.clientWidth, `${viewport} comparison region width`).toBeGreaterThan(0);
  if (wide) {
    expect(
      comparisonLayout.scrollWidth,
      `${viewport} transition table fits without horizontal scrolling`,
    ).toBeLessThanOrEqual(comparisonLayout.clientWidth + 1);
  } else {
    expect(
      comparisonLayout.scrollWidth,
      `${viewport} transition table remains horizontally scrollable in its region`,
    ).toBeGreaterThan(comparisonLayout.clientWidth);
  }

  const titleSize = await root
    .getByRole('heading', {
      name: 'US Equities Transition Policy',
      level: 2,
      exact: true,
    })
    .evaluate((element) => getComputedStyle(element).fontSize);
  expect(titleSize, `${viewport} transition heading computed font-size`).toBe('18px');
}

async function expectRunSummaryHeadingSizes(root: Locator, viewport: string): Promise<void> {
  const headings = await root.locator('h2, h3, h4').evaluateAll((elements) =>
    elements.map((element) => ({
      tagName: element.tagName,
      fontSize: getComputedStyle(element).fontSize,
      text: element.textContent?.trim() ?? '',
    })),
  );
  expect(headings.length, `${viewport} run summary has semantic headings`).toBeGreaterThan(0);
  for (const heading of headings) {
    const expectedSize =
      heading.tagName === 'H2' ? '18px' : heading.tagName === 'H3' ? '16px' : '14px';
    expect(
      heading.fontSize,
      `${viewport} ${heading.tagName.toLowerCase()} “${heading.text}” computed font-size`,
    ).toBe(expectedSize);
  }
}

async function expectRunSummaryGrid(
  root: Locator,
  viewport: string,
  desktop: boolean,
): Promise<void> {
  const grids = await root.locator('.run-metrics, .overview-metrics').evaluateAll((elements) =>
    elements.map((element) => {
      const style = getComputedStyle(element);
      return {
        template: style.gridTemplateColumns,
        columns: style.gridTemplateColumns.split(/\s+/).filter(Boolean).length,
        clientWidth: element.clientWidth,
        scrollWidth: element.scrollWidth,
      };
    }),
  );
  expect(grids.length, `${viewport} run summary has a metrics grid`).toBeGreaterThan(0);
  for (const grid of grids) {
    if (desktop) {
      expect(grid.columns, `${viewport} grid tracks (${grid.template})`).toBeGreaterThanOrEqual(2);
    } else {
      expect(grid.columns, `${viewport} mobile grid tracks (${grid.template})`).toBe(1);
      expect(
        grid.scrollWidth,
        `${viewport} metrics grid fits its available width`,
      ).toBeLessThanOrEqual(grid.clientWidth + 1);
    }
  }
}

async function expectComputedTokenColor(
  element: Locator,
  property: 'background-color' | 'color',
  token: string,
  label: string,
): Promise<void> {
  const colors = await element.evaluate(
    (node, args) => {
      const probe = document.createElement('span');
      probe.style.setProperty(args.property, `var(${args.token})`);
      document.body.append(probe);
      const expected = getComputedStyle(probe).getPropertyValue(args.property);
      const actual = getComputedStyle(node).getPropertyValue(args.property);
      probe.remove();
      return { actual, expected };
    },
    { property, token },
  );
  expect(colors.actual, `${label} computed ${property}`).toBe(colors.expected);
}

async function expectDrawerSettled(page: Page, open: boolean): Promise<void> {
  const drawer = page.locator('[data-mobile="true"]');
  if (open) await expect(drawer).toBeVisible();
  else await expect(drawer).toBeHidden();
}

type ContrastSample = {
  foreground: string;
  background: string;
  visible: boolean;
};

type NavigationContrastSnapshot = {
  heading: ContrastSample;
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
    const sidebar = document.querySelector<HTMLElement>('[data-sidebar="sidebar"]');
    const navigation = sidebar?.querySelector<HTMLElement>('nav[aria-label="Primary navigation"]');
    const heading = navigation?.querySelector<HTMLElement>('[data-sidebar="group-label"]');
    const brand = sidebar?.querySelector<HTMLElement>('.workspace-brand');
    const brandTitle = brand?.querySelector<HTMLElement>('p:first-of-type');
    const brandSubtitle = brand?.querySelector<HTMLElement>('p:last-of-type');
    const footer = sidebar?.querySelector<HTMLElement>('.workspace-sidebar-footer');
    const footerTitle = footer?.querySelector<HTMLElement>('[data-slot="badge"]');
    const footerBody = footer?.querySelector<HTMLElement>('p');
    if (
      !sidebar ||
      !navigation ||
      !heading ||
      !brand ||
      !brandTitle ||
      !brandSubtitle ||
      !footer ||
      !footerTitle ||
      !footerBody
    ) {
      throw new Error('Workspace sidebar navigation, branding, or footer is missing');
    }

    const image = new Image();
    image.src = `data:image/png;base64,${encodedScreenshot}`;
    await image.decode();
    const canvas = document.createElement('canvas');
    canvas.width = image.naturalWidth;
    canvas.height = image.naturalHeight;
    const context = canvas.getContext('2d', { willReadFrequently: true });
    if (!context) throw new Error('Unable to sample the rendered sidebar screenshot');
    context.drawImage(image, 0, 0);

    const scaleX = canvas.width / window.innerWidth;
    const scaleY = canvas.height / window.innerHeight;
    const sidebarRect = sidebar.getBoundingClientRect();
    const sidebarOnScreen =
      sidebarRect.left >= 0 && sidebarRect.right <= window.innerWidth && sidebarRect.width > 0;

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

    const colorCanvas = document.createElement('canvas');
    colorCanvas.width = 1;
    colorCanvas.height = 1;
    const colorContext = colorCanvas.getContext('2d', { willReadFrequently: true });
    if (!colorContext) throw new Error('Unable to normalize computed text colors');

    function toSrgbColor(color: string): string {
      colorContext!.fillStyle = color;
      colorContext!.clearRect(0, 0, 1, 1);
      colorContext!.fillRect(0, 0, 1, 1);
      const [red, green, blue] = colorContext!.getImageData(0, 0, 1, 1).data;
      return `rgb(${red}, ${green}, ${blue})`;
    }

    function sample(element: HTMLElement, backgroundBox: HTMLElement): ContrastSample {
      const elementRect = element.getBoundingClientRect();
      const backgroundRect = backgroundBox.getBoundingClientRect();
      const visible =
        sidebarOnScreen &&
        isFullyOpaqueAndVisible(element) &&
        element.getClientRects().length > 0 &&
        elementRect.width > 0 &&
        elementRect.height > 0 &&
        elementRect.top >= 0 &&
        elementRect.bottom <= window.innerHeight &&
        backgroundRect.right - 24 >= 0 &&
        backgroundRect.right - 24 < window.innerWidth;
      if (!visible) return { foreground: '', background: '', visible: false };

      // Sample inside the painted row, away from glyphs and the sidebar scrollbar.
      const x = Math.floor((backgroundRect.right - 24) * scaleX);
      const y = Math.floor((elementRect.top + elementRect.height / 2) * scaleY);
      const pixel = context!.getImageData(x, y, 1, 1).data;
      return {
        foreground: toSrgbColor(getComputedStyle(element).color),
        background: `rgb(${pixel[0]}, ${pixel[1]}, ${pixel[2]})`,
        visible: true,
      };
    }

    const links = Array.from(navigation.querySelectorAll<HTMLElement>('a')).map((link) => {
      const primary = link.querySelector<HTMLElement>('span > span:first-child');
      const caption = link.querySelector<HTMLElement>('span > span:last-child');
      const icon = link.querySelector<HTMLElement>('svg');
      if (!primary || !caption || !icon) throw new Error('Navigation item is incomplete');
      return {
        path: link.getAttribute('href'),
        active: link.getAttribute('aria-current') === 'page',
        primary: sample(primary, link),
        caption: sample(caption, link),
        icon: sample(icon, link),
      };
    });

    return {
      heading: sample(heading, sidebar),
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
  expect(snapshot.links).toHaveLength(7);
  expect(snapshot.links.filter((link) => link.active)).toHaveLength(1);
  for (const [label, sample] of [
    ['Workspace heading', snapshot.heading],
    ['Sidebar branding', snapshot.brandTitle],
    ['Brand subtitle', snapshot.brandSubtitle],
    ['Footer title', snapshot.footerTitle],
    ['Footer text', snapshot.footerBody],
  ] as const) {
    expect(sample.visible, `${viewport} ${label} is painted`).toBe(true);
    expect(sample.foreground).toMatch(/^rgb\(/);
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
      expect(sample.visible, `${label} ${part} is painted in the open sidebar`).toBe(true);
      expect(sample.foreground).toMatch(/^rgb\(/);
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
  const menuRows = await page
    .getByRole('navigation', { name: 'Primary navigation' })
    .getByRole('link')
    .evaluateAll((links) =>
      links.map((link) => {
        const row = link.getBoundingClientRect();
        const textStack = link
          .querySelector<HTMLElement>('[class*="flex-col"]')
          ?.getBoundingClientRect();
        return {
          height: row.height,
          textFits: Boolean(textStack && textStack.height <= row.height),
        };
      }),
    );
  expect(menuRows).toHaveLength(7);
  for (const [index, row] of menuRows.entries()) {
    expect(row.height, `${viewport} navigation item ${index + 1} height`).toBeGreaterThanOrEqual(
      48,
    );
    expect(row.textFits, `${viewport} navigation item ${index + 1} text fits`).toBe(true);
  }

  const activeLink = snapshot.links.find((link) => link.active)!;
  expect(activeLink.caption.foreground).toBe(activeLink.primary.foreground);
}

async function expectGhostTriggerBaseline(page: Page, viewport: string): Promise<void> {
  const trigger = page.locator('button[data-sidebar="trigger"]');
  await expect(trigger).toBeVisible();
  await expect(trigger, `${viewport} sidebar trigger background`).toHaveCSS(
    'background-color',
    'rgba(0, 0, 0, 0)',
  );
  const inheritedColor = await trigger.evaluate((element) => {
    if (!element.parentElement) throw new Error('Sidebar trigger has no parent');
    return getComputedStyle(element.parentElement).color;
  });
  await expect(trigger, `${viewport} sidebar trigger color`).toHaveCSS('color', inheritedColor);
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

test('desktop and tablet workspace routes with keyboard access', async ({
  emptyApp,
  page,
  browser,
}) => {
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
    { path: '/review', link: /Selected basket/, heading: 'Selected trades' },
    { path: '/lots', link: /Tax Lots/, heading: 'Tax Lots' },
    { path: '/policy', link: /Allocation Policy/, heading: 'Allocation Policy' },
    { path: '/wash-sales', link: /Wash Sales/, heading: 'Wash Sales' },
    { path: '/activity', link: /Activity/, heading: 'Activity' },
  ];

  await page.keyboard.press('Tab');
  await expect(page.getByRole('link', { name: 'Skip to main content' })).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.locator('#main-content')).toBeFocused();
  await page.keyboard.press('Tab');
  const firstMainAction = page.getByRole('button', { name: 'Sync portfolio', exact: true });
  await expect(firstMainAction).toBeFocused();

  await page.keyboard.press('Shift+Tab');
  await page.keyboard.press('Shift+Tab');
  let firstKeyboardRoute = true;
  let previousRouteLink: Locator | null = null;
  for (const route of [...desktopRoutes].reverse()) {
    const link = nav.getByRole('link', { name: route.link });
    if (!firstKeyboardRoute) {
      await previousRouteLink?.focus();
      await page.keyboard.press('Shift+Tab');
    }
    firstKeyboardRoute = false;
    await expect(link).toBeFocused();
    previousRouteLink = link;
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
    await expect(menuButton).toHaveAttribute('aria-expanded', 'true');
    await tabletPage.keyboard.press('Shift+Tab');
    await expect(menuButton).toBeFocused();
    await tabletPage.keyboard.press('Enter');
    await expect(menuButton).toHaveAttribute('aria-expanded', 'false');
    await tabletPage.keyboard.press('Enter');
    await expect(menuButton).toHaveAttribute('aria-expanded', 'true');

    const tabletNav = tabletPage.getByRole('navigation', { name: 'Primary navigation' });
    for (const route of desktopRoutes) {
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

test('workspace navigation contrast is readable on desktop and mobile', async ({
  emptyApp,
  page,
  browser,
}, testInfo) => {
  test.setTimeout(120_000);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto(new URL('/', emptyApp.baseUrl).toString(), { waitUntil: 'domcontentloaded' });

  const navigation = page.getByRole('navigation', { name: 'Primary navigation' });
  const overviewLink = navigation.getByRole('link', { name: /Overview/ });
  const recommendationsLink = navigation.getByRole('link', { name: /Recommendations/ });
  await expect(overviewLink).toHaveAttribute('aria-current', 'page');
  await page.mouse.move(1200, 900);
  const desktopOverviewPath = testInfo.outputPath('desktop-overview.png');
  await page.screenshot({ path: desktopOverviewPath });
  await testInfo.attach('desktop overview', {
    path: desktopOverviewPath,
    contentType: 'image/png',
  });
  await expectReadableNavigation(page, 'desktop overview');

  await recommendationsLink.hover();
  const hoveredNavigation = await readNavigationContrast(page);
  const hoveredRecommendations = hoveredNavigation.links.find((link) =>
    link.path?.endsWith('/recommendations'),
  );
  if (!hoveredRecommendations) throw new Error('Hovered Recommendations link is missing');
  expect(hoveredRecommendations.active).toBe(false);
  expect(hoveredRecommendations.caption.visible).toBe(true);
  const hoveredCaptionContrast = contrastRatio(
    hoveredRecommendations.caption.foreground,
    hoveredRecommendations.caption.background,
  );
  expect(
    hoveredCaptionContrast,
    'desktop inactive Recommendations caption hover contrast',
  ).toBeGreaterThanOrEqual(4.5);
  await page.mouse.move(1200, 900);

  const probeItem = navigation.locator('a').nth(1);
  const probeText = probeItem.locator('span > span:first-child');
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
  await expectReadableNavigation(page, 'desktop recommendations');

  const mobilePage = await browser.newPage({ viewport: { width: 390, height: 844 } });
  try {
    await mobilePage.goto(new URL('/', emptyApp.baseUrl).toString(), {
      waitUntil: 'domcontentloaded',
    });
    await expect(mobilePage.getByRole('heading', { name: 'Overview', exact: true })).toBeVisible();
    await mobilePage.mouse.move(380, 830);
    await expectGhostTriggerBaseline(mobilePage, 'mobile');
    const mobileOverviewPath = testInfo.outputPath('mobile-overview.png');
    await mobilePage.screenshot({ path: mobileOverviewPath });
    await testInfo.attach('mobile overview', {
      path: mobileOverviewPath,
      contentType: 'image/png',
    });
    await mobilePage.goto(new URL('/#/recommendations', emptyApp.baseUrl).toString(), {
      waitUntil: 'domcontentloaded',
    });
    await expect(
      mobilePage.getByRole('heading', { name: 'No recommendation run loaded' }),
    ).toBeVisible();
    const menuButton = mobilePage.getByRole('button', { name: 'Toggle workspace navigation' });
    const menuButtonDom = mobilePage.locator('[data-sidebar="trigger"]');
    await expect(menuButton).toHaveAttribute('aria-expanded', 'false');
    await expectDrawerSettled(mobilePage, false);

    await menuButton.focus();
    await mobilePage.keyboard.press('Enter');
    await expect(menuButtonDom).toHaveAttribute('aria-expanded', 'true');
    await expectDrawerSettled(mobilePage, true);
    const mobileSheet = mobilePage.locator('[data-mobile="true"]');
    await expect(mobileSheet).toBeVisible();
    const mobileSheetPath = testInfo.outputPath('mobile-navigation-sheet.png');
    await mobilePage.screenshot({ path: mobileSheetPath });
    await testInfo.attach('mobile navigation sheet', {
      path: mobileSheetPath,
      contentType: 'image/png',
    });
    expect(await mobileSheet.evaluate((element) => getComputedStyle(element).boxSizing)).toBe(
      'border-box',
    );
    await mobileSheet.focus();
    await mobilePage.keyboard.press('Escape');
    await expectDrawerSettled(mobilePage, false);
    await expect(menuButton).toHaveAttribute('aria-expanded', 'false');

    await expect(menuButton).toBeFocused();
    await menuButton.click();
    await expect(menuButtonDom).toHaveAttribute('aria-expanded', 'true');
    await expectDrawerSettled(mobilePage, true);
    await expectReadableNavigation(mobilePage, 'mobile recommendations');

    const mobileNavigation = mobilePage.getByRole('navigation', { name: 'Primary navigation' });
    const taxLotsLink = mobileNavigation.getByRole('link', { name: /Tax Lots/ });
    await taxLotsLink.click();
    await expect(mobilePage.getByRole('heading', { name: 'Tax Lots', exact: true })).toBeVisible();
    await expect(menuButton).toHaveAttribute('aria-expanded', 'false');
    await expectDrawerSettled(mobilePage, false);
    await expect(mobilePage.locator('#main-content')).toBeFocused();
    await menuButton.click();
    await expect(menuButtonDom).toHaveAttribute('aria-expanded', 'true');
    await expectDrawerSettled(mobilePage, true);
    await expect(taxLotsLink).toHaveAttribute('aria-current', 'page');
    await expectReadableNavigation(mobilePage, 'mobile tax lots');
  } finally {
    await mobilePage.close();
  }
});

test('shared canonical leg links preserve the hash route and keyboard focus', async ({
  seededApp,
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  let sharedLegId: string | null = null;
  let sharedGroupId: string | null = null;

  await page.route('**/api/v1/optimizer/runs', async (route) => {
    if (route.request().method() !== 'POST') {
      await route.continue();
      return;
    }
    const response = await route.fetch();
    if (!response.ok()) {
      await route.fulfill({ response });
      return;
    }
    const run = (await response.json()) as RecommendationResponse;
    const sharedLeg =
      run.consolidated_legs.find((leg) => leg.side === 'BUY') ?? run.consolidated_legs[0];
    const sourceGroup = sharedLeg
      ? (run.groups.find((group) => sharedLeg.group_ids.includes(group.group_id)) ?? run.groups[0])
      : undefined;
    if (!sharedLeg || !sourceGroup) {
      throw new Error('FakeBroker did not return a canonical leg and recommendation group');
    }

    const originalLegId = sharedLeg.leg_id;
    const encodedTestLegId = `shared/${originalLegId}`;
    sharedLeg.leg_id = encodedTestLegId;
    for (const group of run.groups) {
      group.leg_ids = group.leg_ids.map((legId) =>
        legId === originalLegId ? encodedTestLegId : legId,
      );
    }

    let linkedGroup = run.groups.find((group) => group.group_id !== sourceGroup.group_id);
    if (!linkedGroup) {
      linkedGroup = {
        ...sourceGroup,
        group_id: 'e2e-shared-canonical-group',
        rank: sourceGroup.rank + 1,
        leg_ids: [encodedTestLegId],
        selected: false,
        rejected: false,
        note: null,
        rejection_reason: null,
      };
      run.groups.push(linkedGroup);
    }
    sharedLeg.group_ids = [
      ...new Set([...sharedLeg.group_ids, sourceGroup.group_id, linkedGroup.group_id]),
    ];
    for (const group of run.groups) {
      const referencesSharedLeg = sharedLeg.group_ids.includes(group.group_id);
      const currentlyReferencesLeg = group.leg_ids.includes(encodedTestLegId);
      if (referencesSharedLeg && !currentlyReferencesLeg) group.leg_ids.push(encodedTestLegId);
      if (!referencesSharedLeg && currentlyReferencesLeg) {
        group.leg_ids = group.leg_ids.filter((legId) => legId !== encodedTestLegId);
      }
    }

    sharedLegId = encodedTestLegId;
    sharedGroupId = sourceGroup.group_id;
    await route.fulfill({ response, json: run });
  });

  await page.goto(new URL('/', seededApp.baseUrl).toString(), { waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('heading', { name: 'Overview', exact: true })).toBeVisible();
  const startRun = page.getByRole('button', { name: 'Run DEMO recommendations' });
  await expect(startRun).toBeEnabled();
  const runResponse = page.waitForResponse(
    (response) =>
      response.request().method() === 'POST' &&
      new URL(response.url()).pathname === '/api/v1/optimizer/runs',
  );
  await startRun.click();
  await runResponse;
  await expect(page).toHaveURL((url) => url.hash.startsWith('#/recommendations'));
  await expect(page.getByRole('heading', { name: 'Ranked trade groups' })).toBeVisible();
  if (!sharedLegId || !sharedGroupId) {
    throw new Error('The browser FakeBroker response was not prepared with a shared canonical leg');
  }

  const groupHeader = page.getByRole('button', {
    name: `Tax-loss harvest Group ID ${sharedGroupId}`,
    exact: true,
  });
  await expect(groupHeader).toHaveAccessibleName(`Tax-loss harvest Group ID ${sharedGroupId}`);
  await expect(groupHeader).toHaveAccessibleDescription(/SELL .*API realized ST \/ LT:/);
  if ((await groupHeader.getAttribute('aria-expanded')) !== 'true') await groupHeader.click();
  const groupCard = page.locator('.group-card').filter({ has: groupHeader });
  const sharedLink = groupCard
    .locator('.shared-note')
    .first()
    .locator('xpath=..')
    .getByRole('link');
  const encodedAnchor = `leg-${encodeURIComponent(sharedLegId)}`;
  const canonicalLeg = page.locator(`[id="${encodedAnchor}"]`);
  await expect(sharedLink).toBeVisible();
  await expect(sharedLink).toHaveAttribute(
    'href',
    `#/recommendations#${encodeURIComponent(encodedAnchor)}`,
  );
  await expect(canonicalLeg).toHaveCount(1);
  await sharedLink.focus();
  await expect(sharedLink).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(
    (url) => url.hash === `#/recommendations#${encodeURIComponent(encodedAnchor)}`,
  );
  await expect(canonicalLeg).toBeInViewport();
  await expect(canonicalLeg).toBeFocused();
});

test('FakeBroker policy, review, and lot workflows', async ({
  seededApp,
  page,
  browser,
}, testInfo) => {
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
  await expectOverviewSummaryGrid(page, 'Overview desktop', 4);
  await expectOverviewContentGrid(page, 'Overview desktop', 2);
  await expectOverviewHeadingTypography(page, 'Overview desktop');
  await expectNoHorizontalOverflow(page, 'Overview at desktop');
  const overviewChart = page.locator('.allocation-comparison-chart').first();
  await expect(overviewChart).toBeVisible();
  await expect(overviewChart.locator('.ts-chart-host svg')).toBeVisible();
  const overviewChartNode = await overviewChart.elementHandle();
  if (!overviewChartNode) throw new Error('Overview allocation chart is missing');
  const desktopOverviewChartWidth = await overviewChart.evaluate(
    (element) => element.getBoundingClientRect().width,
  );
  const desktopOverviewSvgWidth = await overviewChart
    .locator('.ts-chart-host svg')
    .evaluate((element) => element.getBoundingClientRect().width);
  const overviewDesktopScreenshot = testInfo.outputPath('overview-allocation-desktop.png');
  await expectAllocationHeadingFontSize(page, 'Overview desktop');
  const overviewTransition = page.locator('.transition-panel').first();
  await expectTransitionLayout(
    overviewTransition,
    'Overview desktop',
    true,
    'Current portfolio API context',
  );
  const overviewTransitionDesktopScreenshot = testInfo.outputPath(
    'overview-us-transition-desktop.png',
  );
  await overviewTransition.screenshot({ path: overviewTransitionDesktopScreenshot });
  await testInfo.attach('overview US transition desktop', {
    path: overviewTransitionDesktopScreenshot,
    contentType: 'image/png',
  });
  const overviewDesktopViewport = testInfo.outputPath('overview-desktop-viewport.png');
  await scrollOverviewToTop(page, 'desktop');
  await expectOverviewActionsInViewport(page, 'desktop');
  await page.screenshot({ path: overviewDesktopViewport });
  await testInfo.attach('overview desktop viewport', {
    path: overviewDesktopViewport,
    contentType: 'image/png',
  });
  await page.screenshot({ path: overviewDesktopScreenshot, fullPage: true });
  await testInfo.attach('overview allocation desktop', {
    path: overviewDesktopScreenshot,
    contentType: 'image/png',
  });
  const overviewPolicyCard = page.locator('.overview-page .policy-card');
  await overviewPolicyCard.evaluate((element) => element.scrollIntoView({ block: 'start' }));
  await expect(
    page.getByRole('heading', { name: 'Active allocation policy', level: 2, exact: true }),
  ).toBeInViewport();
  await expect(
    page.getByRole('heading', { name: 'Active allocation targets', level: 3, exact: true }),
  ).toBeInViewport();
  await expectOverviewHeadingTypography(page, 'Overview desktop policy section');
  const overviewPolicyDesktopViewport = testInfo.outputPath('overview-policy-desktop-viewport.png');
  await page.screenshot({ path: overviewPolicyDesktopViewport });
  await testInfo.attach('overview policy section desktop viewport', {
    path: overviewPolicyDesktopViewport,
    contentType: 'image/png',
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await expectOverviewSummaryGrid(page, 'Overview mobile', 1);
  await expectOverviewContentGrid(page, 'Overview mobile', 1);
  await expectOverviewHeadingTypography(page, 'Overview mobile');
  await expect
    .poll(() => overviewChart.evaluate((element) => element.getBoundingClientRect().width))
    .toBeLessThan(desktopOverviewChartWidth);
  await expect
    .poll(() =>
      overviewChart
        .locator('.ts-chart-host svg')
        .evaluate((element) => element.getBoundingClientRect().width),
    )
    .toBeLessThan(desktopOverviewSvgWidth);
  await expectNoHorizontalOverflow(page, 'Overview allocation chart at mobile');
  await expectTransitionLayout(
    overviewTransition,
    'Overview mobile',
    false,
    'Current portfolio API context',
  );
  const overviewTransitionMobileScreenshot = testInfo.outputPath(
    'overview-us-transition-mobile.png',
  );
  await overviewTransition.screenshot({
    path: overviewTransitionMobileScreenshot,
    style: '.skip-link { visibility: hidden !important; }',
  });
  await testInfo.attach('overview US transition mobile', {
    path: overviewTransitionMobileScreenshot,
    contentType: 'image/png',
  });
  const overviewMobileScreenshot = testInfo.outputPath('overview-allocation-mobile.png');
  await expectAllocationHeadingFontSize(page, 'Overview mobile');
  const overviewMobileViewport = testInfo.outputPath('overview-mobile-viewport.png');
  await expectNoHorizontalOverflow(page, 'Overview at mobile');
  await scrollOverviewToTop(page, 'mobile');
  await expectOverviewActionsInViewport(page, 'mobile');
  await page.screenshot({ path: overviewMobileViewport });
  await testInfo.attach('overview mobile viewport', {
    path: overviewMobileViewport,
    contentType: 'image/png',
  });
  await page.screenshot({ path: overviewMobileScreenshot, fullPage: true });
  await testInfo.attach('overview allocation mobile', {
    path: overviewMobileScreenshot,
    contentType: 'image/png',
  });
  await overviewPolicyCard.evaluate((element) => element.scrollIntoView({ block: 'start' }));
  await expect(
    page.getByRole('heading', { name: 'Active allocation policy', level: 2, exact: true }),
  ).toBeInViewport();
  await expect(
    page.getByRole('heading', { name: 'Active allocation targets', level: 3, exact: true }),
  ).toBeInViewport();
  await expectOverviewHeadingTypography(page, 'Overview mobile policy section');
  const overviewPolicyMobileViewport = testInfo.outputPath('overview-policy-mobile-viewport.png');
  await page.screenshot({ path: overviewPolicyMobileViewport });
  await testInfo.attach('overview policy section mobile viewport', {
    path: overviewPolicyMobileViewport,
    contentType: 'image/png',
  });
  await page.setViewportSize({ width: 1440, height: 1000 });
  const firstRunResponse = page.waitForResponse(
    (response) =>
      response.request().method() === 'POST' &&
      new URL(response.url()).pathname === '/api/v1/optimizer/runs',
  );
  await startRun.focus();
  await page.keyboard.press('Enter');
  const firstRun = (await (await firstRunResponse).json()) as {
    run_id: string;
    policy_revision_id: string;
  };
  expect(firstRun.policy_revision_id).toBe(originalPolicyId);

  await expect(page).toHaveURL(/#\/recommendations(?:[?#]|$)/);
  await expect(page.getByRole('heading', { name: 'Ranked trade groups' })).toBeVisible();
  const recommendationsHeading = page.getByRole('heading', {
    name: 'Recommendations',
    exact: true,
  });
  const runRecommendationsButton = page.getByRole('button', { name: 'Run DEMO recommendations' });
  await page.evaluate(() => window.scrollTo(0, 0));
  await expect(recommendationsHeading).toBeInViewport();
  await expect(runRecommendationsButton).toBeInViewport();
  const runRecommendationsHeading = page.getByRole('heading', {
    name: 'Run recommendations',
    exact: true,
  });
  await expect(runRecommendationsHeading).toBeVisible();
  await expect(runRecommendationsHeading).toHaveCSS('font-size', '16px');
  const recommendationsHeaderDesktop = testInfo.outputPath('recommendations-header-desktop.png');
  await page.screenshot({ path: recommendationsHeaderDesktop });
  await testInfo.attach('recommendations header desktop viewport', {
    path: recommendationsHeaderDesktop,
    contentType: 'image/png',
  });
  const firstFrozenContext = page.getByRole('region', { name: 'Frozen run display context' });
  await expect(firstFrozenContext).toContainText(originalUsLabel);
  const reviewRunSummary = page.locator('.run-summary');
  const actionFilter = page.getByRole('combobox', { name: 'Action' });
  await actionFilter.focus();
  await expect(actionFilter).toBeFocused();
  await page.keyboard.press('Enter');
  const sellOption = page.getByRole('option', { name: 'SELL', exact: true });
  await expect(sellOption).toBeVisible();
  await page.keyboard.press('ArrowDown');
  await expect(sellOption).toHaveAttribute('data-highlighted', '');
  await page.keyboard.press('Enter');
  await expect(actionFilter).toContainText('SELL');
  const recommendationsFilterPanel = page.locator('.filter-panel');
  await recommendationsFilterPanel.scrollIntoViewIfNeeded();
  await expect(recommendationsFilterPanel).toBeInViewport();
  const recommendationsFiltersDesktop = testInfo.outputPath('recommendations-filters-desktop.png');
  await page.screenshot({ path: recommendationsFiltersDesktop });
  await testInfo.attach('recommendations filters desktop viewport', {
    path: recommendationsFiltersDesktop,
    contentType: 'image/png',
  });
  const recommendationsSelectionTools = page.locator('.selection-tools');
  await recommendationsSelectionTools.scrollIntoViewIfNeeded();
  await expect(recommendationsSelectionTools).toBeInViewport();
  const recommendationsSelectionDesktop = testInfo.outputPath(
    'recommendations-selection-tools-desktop.png',
  );
  await page.screenshot({ path: recommendationsSelectionDesktop });
  await testInfo.attach('recommendations selection controls desktop viewport', {
    path: recommendationsSelectionDesktop,
    contentType: 'image/png',
  });
  await expect(reviewRunSummary).toBeVisible();
  await expectRunSummaryHeadingSizes(reviewRunSummary, 'review desktop');
  await expectRunSummaryHeadingSizes(firstFrozenContext, 'review frozen context desktop');
  await expectRunSummaryGrid(reviewRunSummary, 'review desktop', true);
  const reviewStatusBadge = reviewRunSummary.locator('[data-slot="badge"]');
  await expectComputedTokenColor(
    reviewStatusBadge,
    'background-color',
    '--secondary',
    'review status badge',
  );
  await expectComputedTokenColor(
    reviewStatusBadge,
    'color',
    '--secondary-foreground',
    'review status badge',
  );
  const demoNotice = reviewRunSummary.getByRole('group', { name: 'DEMO solver output notice' });
  await expectComputedTokenColor(demoNotice, 'background-color', '--card', 'DEMO notice');
  await expectComputedTokenColor(demoNotice, 'color', '--card-foreground', 'DEMO notice');
  const taxEstimateNotice = reviewRunSummary.getByRole('group', {
    name: 'Tax estimate availability notice',
  });
  if (await taxEstimateNotice.count()) {
    await expectComputedTokenColor(
      taxEstimateNotice,
      'background-color',
      '--card',
      'tax estimate notice',
    );
    await expectComputedTokenColor(
      taxEstimateNotice,
      'color',
      '--destructive',
      'tax estimate notice',
    );
  }
  const reviewSummaryDesktop = testInfo.outputPath('run-summary-review-desktop.png');
  await reviewRunSummary.screenshot({ path: reviewSummaryDesktop });
  await testInfo.attach('run summary review desktop', {
    path: reviewSummaryDesktop,
    contentType: 'image/png',
  });
  await expect.poll(() => overviewChartNode.evaluate((element) => element.isConnected)).toBe(false);
  const recommendationChart = page.locator('.allocation-panel .allocation-comparison-chart');
  await expect(recommendationChart).toBeVisible();
  await expect(recommendationChart.locator('.ts-chart-host svg')).toBeVisible();
  const recommendationsTransition = page.locator('.transition-panel').first();
  await expectTransitionLayout(
    recommendationsTransition,
    'Recommendations desktop',
    true,
    'Current selected-basket API context',
  );
  const recommendationsTransitionDesktopScreenshot = testInfo.outputPath(
    'recommendations-us-transition-desktop.png',
  );
  await recommendationsTransition.screenshot({ path: recommendationsTransitionDesktopScreenshot });
  await testInfo.attach('recommendations US transition desktop', {
    path: recommendationsTransitionDesktopScreenshot,
    contentType: 'image/png',
  });
  const recommendationDesktopScreenshot = testInfo.outputPath(
    'recommendations-allocation-desktop.png',
  );
  await expectAllocationHeadingFontSize(page, 'Recommendations desktop');
  await page.screenshot({ path: recommendationDesktopScreenshot, fullPage: true });
  await testInfo.attach('recommendations allocation desktop', {
    path: recommendationDesktopScreenshot,
    contentType: 'image/png',
  });
  const desktopRecommendationsChartWidth = await recommendationChart.evaluate(
    (element) => element.getBoundingClientRect().width,
  );
  const desktopRecommendationsSvgWidth = await recommendationChart
    .locator('.ts-chart-host svg')
    .evaluate((element) => element.getBoundingClientRect().width);
  await page.setViewportSize({ width: 390, height: 844 });
  await expect
    .poll(() => recommendationChart.evaluate((element) => element.getBoundingClientRect().width))
    .toBeLessThan(desktopRecommendationsChartWidth);
  await expect
    .poll(() =>
      recommendationChart
        .locator('.ts-chart-host svg')
        .evaluate((element) => element.getBoundingClientRect().width),
    )
    .toBeLessThan(desktopRecommendationsSvgWidth);
  await expectNoHorizontalOverflow(page, 'Recommendations allocation chart at mobile');
  await expectNoHorizontalOverflow(page, 'Recommendations page at mobile');
  await expectTransitionLayout(
    recommendationsTransition,
    'Recommendations mobile',
    false,
    'Current selected-basket API context',
  );
  await page.evaluate(() => window.scrollTo(0, 0));
  await expect(recommendationsHeading).toBeInViewport();
  await expect(runRecommendationsButton).toBeInViewport();
  const recommendationsHeaderMobile = testInfo.outputPath('recommendations-header-mobile.png');
  await page.screenshot({ path: recommendationsHeaderMobile });
  await testInfo.attach('recommendations header mobile viewport', {
    path: recommendationsHeaderMobile,
    contentType: 'image/png',
  });
  const recommendationsTransitionMobileScreenshot = testInfo.outputPath(
    'recommendations-us-transition-mobile.png',
  );
  await recommendationsTransition.screenshot({
    path: recommendationsTransitionMobileScreenshot,
    style: '.skip-link { visibility: hidden !important; }',
  });
  await testInfo.attach('recommendations US transition mobile', {
    path: recommendationsTransitionMobileScreenshot,
    contentType: 'image/png',
  });
  await expectRunSummaryHeadingSizes(reviewRunSummary, 'review mobile');
  await expectRunSummaryHeadingSizes(firstFrozenContext, 'review frozen context mobile');
  await expectRunSummaryGrid(reviewRunSummary, 'review mobile', false);
  const reviewSummaryMobile = testInfo.outputPath('run-summary-review-mobile.png');
  await reviewRunSummary.screenshot({ path: reviewSummaryMobile });
  await testInfo.attach('run summary review mobile', {
    path: reviewSummaryMobile,
    contentType: 'image/png',
  });
  const recommendationsMobileScreenshot = testInfo.outputPath(
    'recommendations-allocation-mobile.png',
  );
  await expectAllocationHeadingFontSize(page, 'Recommendations mobile');
  await page.screenshot({ path: recommendationsMobileScreenshot, fullPage: true });
  await testInfo.attach('recommendations allocation mobile', {
    path: recommendationsMobileScreenshot,
    contentType: 'image/png',
  });
  await recommendationsFilterPanel.scrollIntoViewIfNeeded();
  await expect(recommendationsFilterPanel).toBeInViewport();
  const recommendationsFiltersMobile = testInfo.outputPath('recommendations-filters-mobile.png');
  await page.screenshot({ path: recommendationsFiltersMobile });
  await testInfo.attach('recommendations filters mobile viewport', {
    path: recommendationsFiltersMobile,
    contentType: 'image/png',
  });
  await recommendationsSelectionTools.scrollIntoViewIfNeeded();
  await expect(recommendationsSelectionTools).toBeInViewport();
  const recommendationsSelectionMobile = testInfo.outputPath(
    'recommendations-selection-tools-mobile.png',
  );
  await page.screenshot({ path: recommendationsSelectionMobile });
  await testInfo.attach('recommendations selection controls mobile viewport', {
    path: recommendationsSelectionMobile,
    contentType: 'image/png',
  });
  await page.setViewportSize({ width: 1440, height: 1000 });
  const sharedLegsRegion = page.locator('.shared-legs');
  if (await sharedLegsRegion.count()) {
    await sharedLegsRegion.scrollIntoViewIfNeeded();
    const sharedLegsDesktop = testInfo.outputPath('recommendations-shared-legs-desktop.png');
    await page.screenshot({ path: sharedLegsDesktop });
    await testInfo.attach('recommendations shared consolidated legs desktop viewport', {
      path: sharedLegsDesktop,
      contentType: 'image/png',
    });
  }
  const unlinkedLegsRegion = page.getByRole('region', { name: 'Unlinked API legs' });
  if (await unlinkedLegsRegion.count()) {
    await unlinkedLegsRegion.scrollIntoViewIfNeeded();
    const unlinkedLegsDesktop = testInfo.outputPath('recommendations-unlinked-legs-desktop.png');
    await page.screenshot({ path: unlinkedLegsDesktop });
    await testInfo.attach('recommendations unlinked API legs desktop viewport', {
      path: unlinkedLegsDesktop,
      contentType: 'image/png',
    });
  }
  const recommendationExportRegion = page.getByRole('region', { name: 'Recommendation export' });
  await expect(recommendationExportRegion).toBeVisible();
  await expect(
    recommendationExportRegion.getByRole('button', { name: 'Export CSV' }),
  ).toBeVisible();
  await expect(
    recommendationExportRegion.getByRole('button', { name: 'Export JSON' }),
  ).toBeVisible();
  await recommendationExportRegion.scrollIntoViewIfNeeded();
  await expect(recommendationExportRegion).toBeInViewport();
  const recommendationsExportDesktop = testInfo.outputPath('recommendations-export-desktop.png');
  await page.screenshot({ path: recommendationsExportDesktop });
  await testInfo.attach('recommendations export desktop viewport', {
    path: recommendationsExportDesktop,
    contentType: 'image/png',
  });
  await page.getByRole('link', { name: /Overview/ }).click();
  const overviewRunSummary = page.locator('.overview-run-summary');
  await expect(overviewRunSummary).toBeVisible();
  const frozenAssumptions = overviewRunSummary.locator('details');
  const frozenAssumptionsToggle = frozenAssumptions.locator('summary');
  await frozenAssumptionsToggle.focus();
  await expect(frozenAssumptionsToggle).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(frozenAssumptions).toHaveAttribute('open', '');
  await page.keyboard.press('Enter');
  await expect(frozenAssumptions).not.toHaveAttribute('open', '');
  const overviewFrozenContext = overviewRunSummary.getByRole('region', {
    name: 'Overview frozen run context',
  });
  await expectRunSummaryHeadingSizes(overviewRunSummary, 'overview desktop');
  await expectRunSummaryHeadingSizes(overviewFrozenContext, 'overview frozen context desktop');
  await expectRunSummaryGrid(overviewRunSummary, 'overview desktop', true);
  const overviewSummaryDesktop = testInfo.outputPath('run-summary-overview-desktop.png');
  await overviewRunSummary.screenshot({ path: overviewSummaryDesktop });
  await testInfo.attach('run summary overview desktop', {
    path: overviewSummaryDesktop,
    contentType: 'image/png',
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await expectNoHorizontalOverflow(page, 'Overview run summary at mobile');
  await expectRunSummaryHeadingSizes(overviewRunSummary, 'overview mobile');
  await expectRunSummaryHeadingSizes(overviewFrozenContext, 'overview frozen context mobile');
  await expectRunSummaryGrid(overviewRunSummary, 'overview mobile', false);
  const overviewSummaryMobile = testInfo.outputPath('run-summary-overview-mobile.png');
  await overviewRunSummary.screenshot({ path: overviewSummaryMobile });
  await testInfo.attach('run summary overview mobile', {
    path: overviewSummaryMobile,
    contentType: 'image/png',
  });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.getByRole('link', { name: /Recommendations/ }).click();
  await expect(page.getByRole('heading', { name: 'Ranked trade groups' })).toBeVisible();

  await page.getByRole('link', { name: /Allocation Policy/ }).click();
  await expect(page.getByRole('heading', { name: 'Policy revision' })).toBeVisible();
  await expect(page.locator('.allocation-comparison-chart')).toHaveCount(0);
  await expect(page.getByRole('heading', { name: 'Allocation Policy' })).toBeVisible();
  const policyRevisionSelect = page.getByRole('combobox', {
    name: 'Select policy source revision',
  });
  await policyRevisionSelect.focus();
  await expect(policyRevisionSelect).toBeFocused();
  await page.setViewportSize({ width: 1440, height: 1000 });
  const sleeveRegion = page.getByRole('region', { name: 'Sleeve allocation policy settings' });
  await expect(sleeveRegion).toHaveAttribute('tabindex', '0');
  await expect(sleeveRegion.locator('table')).toHaveCount(1);
  await expect(sleeveRegion.locator('thead th:not([scope="col"])')).toHaveCount(0);
  await expectNoHorizontalOverflow(page, 'policy page at desktop');
  const policyDesktopScreenshot = testInfo.outputPath('policy-page-desktop.png');
  await page.screenshot({ path: policyDesktopScreenshot, fullPage: true });
  await testInfo.attach('policy page desktop', {
    path: policyDesktopScreenshot,
    contentType: 'image/png',
  });
  const sleevesDesktopScreenshot = testInfo.outputPath('policy-sleeves-desktop.png');
  await page.screenshot({ path: sleevesDesktopScreenshot, fullPage: true });
  await testInfo.attach('policy sleeves desktop', {
    path: sleevesDesktopScreenshot,
    contentType: 'image/png',
  });

  await page.setViewportSize({ width: 1024, height: 768 });
  await expectNoHorizontalOverflow(page, 'policy page at tablet');
  await expect(sleeveRegion).toBeVisible();
  await expect(sleeveRegion).toHaveAttribute('tabindex', '0');
  const policyTabletScreenshot = testInfo.outputPath('policy-page-tablet.png');
  await page.screenshot({ path: policyTabletScreenshot, fullPage: true });
  await testInfo.attach('policy page tablet', {
    path: policyTabletScreenshot,
    contentType: 'image/png',
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await policyRevisionSelect.focus();
  await expect(policyRevisionSelect).toBeFocused();
  const policyMobileScreenshot = testInfo.outputPath('policy-page-mobile.png');
  await page.screenshot({ path: policyMobileScreenshot, fullPage: true });
  await testInfo.attach('policy page mobile', {
    path: policyMobileScreenshot,
    contentType: 'image/png',
  });
  await expectNoHorizontalOverflow(page, 'policy page at mobile');
  await expect
    .poll(() => sleeveRegion.evaluate((element) => element.scrollWidth > element.clientWidth))
    .toBe(true);
  await expectNoHorizontalOverflow(page, 'policy sleeves at mobile');
  const sleevesMobileScreenshot = testInfo.outputPath('policy-sleeves-mobile.png');
  await page.screenshot({ path: sleevesMobileScreenshot, fullPage: true });
  await testInfo.attach('policy sleeves mobile', {
    path: sleevesMobileScreenshot,
    contentType: 'image/png',
  });

  await sleeveRegion.focus();
  await expect(sleeveRegion).toBeFocused();
  await sleeveRegion.evaluate((element) => {
    element.scrollLeft = element.scrollWidth;
  });
  await expect
    .poll(() => sleeveRegion.evaluate((element) => element.scrollLeft))
    .toBeGreaterThan(0);
  await sleeveRegion.evaluate((element) => {
    element.scrollLeft = 0;
  });

  await page.getByRole('button', { name: 'Add allocation' }).click();
  await expect(page.getByText('Target check — activation is not valid yet')).toBeVisible();
  const newSleeveKey = (
    await sleeveRegion.locator('tbody .sleeve-key').last().textContent()
  )?.trim();
  if (!newSleeveKey) throw new Error('The newly added sleeve key is missing');

  const settingsTrigger = page.getByRole('button', { name: `Actions for ${newSleeveKey}` });
  await settingsTrigger.focus();
  await expect(settingsTrigger).toBeFocused();
  await page.keyboard.press('Enter');
  const settingsAction = page.getByRole('menuitem', { name: 'Allocation settings' });
  await expect(settingsAction).toBeVisible();
  await page.keyboard.press('ArrowDown');
  await expect(settingsAction).toBeFocused();
  await page.keyboard.press('Enter');
  const settingsDialog = page.getByRole('dialog', { name: `Settings for ${newSleeveKey}` });
  await expect(settingsDialog).toBeVisible();
  const parentSelect = settingsDialog.getByRole('combobox', {
    name: `Parent sleeve for ${newSleeveKey}`,
  });
  await parentSelect.focus();
  await expect(parentSelect).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('option').first()).toBeVisible();
  await page.keyboard.press('Escape');
  await settingsDialog.getByRole('button', { name: 'Close' }).click();

  const enabledCheckbox = page.getByRole('checkbox', { name: `Enabled ${newSleeveKey}` });
  await enabledCheckbox.focus();
  await expect(enabledCheckbox).toBeFocused();
  await page.keyboard.press('Space');
  const disabledCheckbox = page.getByRole('checkbox', { name: `Disabled ${newSleeveKey}` });
  await expect(disabledCheckbox).toHaveAttribute('aria-checked', 'false');
  await disabledCheckbox.focus();
  await page.keyboard.press('Space');
  await expect(enabledCheckbox).toHaveAttribute('aria-checked', 'true');

  const deleteButton = page.getByRole('button', { name: `Actions for ${newSleeveKey}` });
  await deleteButton.focus();
  await page.keyboard.press('Enter');
  const deleteAction = page.getByRole('menuitem', { name: 'Delete allocation' });
  await expect(deleteAction).toBeVisible();
  await deleteAction.focus();
  await page.keyboard.press('Enter');
  const deletionPanel = page
    .locator('[role="group"]')
    .filter({ hasText: `Delete ${newSleeveKey}` });
  await expect(deletionPanel).toBeVisible();
  const cancelButton = deletionPanel.getByRole('button', { name: 'Cancel' });
  await cancelButton.focus();
  await page.keyboard.press('Enter');
  await expect(deletionPanel).toHaveCount(0);

  await deleteButton.focus();
  await page.keyboard.press('Enter');
  await expect(deleteAction).toBeVisible();
  await deleteAction.focus();
  await page.keyboard.press('Enter');
  await expect(deletionPanel).toBeVisible();
  const confirmDeleteButton = deletionPanel.getByRole('button', { name: 'Confirm delete' });
  await confirmDeleteButton.focus();
  await page.keyboard.press('Enter');
  await expect(deletionPanel).toHaveCount(0);
  await expect(
    sleeveRegion.locator('tbody .sleeve-key').filter({ hasText: newSleeveKey }),
  ).toHaveCount(0);

  const retainedLoss = page.getByLabel('Target retained net loss (USD)');
  const sleeveName = page.locator(
    '[data-policy-sleeves-root] input[id$="-sleeve-us_equities-name"]',
  );
  await retainedLoss.fill('3456.78');
  await sleeveName.fill('Browser renamed US equities');
  await page.setViewportSize({ width: 1440, height: 1000 });
  const activityPresentationItems = Array.from({ length: 26 }, (_, index) => ({
    id: `presentation-event-${index + 1}`,
    created_at: `2025-01-${String((index % 28) + 1).padStart(2, '0')}T00:00:00Z`,
    event_type: index === 0 ? 'optimizer_run' : 'presentation_event',
    status: 'completed',
    correlation_id: `presentation-correlation-${index + 1}`,
    details: index === 0 ? { run_id: firstRun.run_id } : { ordinal: index + 1 },
  }));
  const activityPresentationRoute = async (route: Route) => {
    if (route.request().method() !== 'GET') {
      await route.continue();
      return;
    }
    const requestUrl = new URL(route.request().url());
    const offset = Number(requestUrl.searchParams.get('offset') ?? 0);
    const limit = Number(requestUrl.searchParams.get('limit') ?? 25);
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        items: activityPresentationItems.slice(offset, offset + limit),
        total: activityPresentationItems.length,
        offset,
        limit,
      }),
    });
  };
  await page.route('**/api/v1/activity**', activityPresentationRoute);
  try {
    await page.getByRole('link', { name: /Activity/ }).click();
    const activityRoot = page.locator('[data-activity-root]');
    await expect(page.getByRole('heading', { name: 'Activity', exact: true })).toBeVisible();
    const eventTypeFilter = page.getByLabel('Event type');
    const statusFilter = page.getByLabel('Status');
    const correlationFilter = page.getByLabel('Correlation ID');
    const sinceFilter = page.getByLabel('Since (UTC)');
    const untilFilter = page.getByLabel('Until (UTC)');
    await expect(eventTypeFilter).toBeVisible();
    await expect(statusFilter).toBeVisible();
    await expect(correlationFilter).toBeVisible();
    await expect(sinceFilter).toHaveAttribute('step', 'any');
    await expect(untilFilter).toHaveAttribute('step', 'any');

    const desktopActivityLayout = await activityRoot.evaluate((root) => {
      const filterGrid = root.querySelector<HTMLElement>('[data-activity-filter-grid]');
      const title = root.querySelector<HTMLElement>('#activity-title');
      const eventTitle = root.querySelector<HTMLElement>('.event-card h2');
      if (!filterGrid || !title || !eventTitle)
        throw new Error('Activity responsive elements are missing');
      return {
        filterColumns: getComputedStyle(filterGrid).gridTemplateColumns,
        titleFontSize: getComputedStyle(title).fontSize,
        eventTitleFontSize: getComputedStyle(eventTitle).fontSize,
      };
    });
    expect(desktopActivityLayout.filterColumns.split(/\s+/).filter(Boolean)).toHaveLength(3);
    expect(desktopActivityLayout.titleFontSize).toBe('32px');
    expect(desktopActivityLayout.eventTitleFontSize).toBe('16px');

    const rowsPerPage = page.getByRole('combobox', { name: 'Rows per page' });
    await rowsPerPage.focus();
    await expect(rowsPerPage).toBeFocused();
    await page.keyboard.press('Enter');
    const fiftyRowsOption = page.getByRole('option', { name: '50', exact: true });
    await expect(fiftyRowsOption).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(fiftyRowsOption).toBeHidden();
    await expect(rowsPerPage).toBeFocused();
    await page.keyboard.press('Enter');
    await page.keyboard.press('ArrowDown');
    await expect(fiftyRowsOption).toBeFocused();
    await page.keyboard.press('Enter');
    await expect(rowsPerPage).toContainText('50');
    await page.keyboard.press('Enter');
    const twentyFiveRowsOption = page.getByRole('option', { name: '25', exact: true });
    await page.keyboard.press('Home');
    await expect(twentyFiveRowsOption).toBeFocused();
    await page.keyboard.press('Enter');
    await expect(rowsPerPage).toContainText('25');

    await eventTypeFilter.fill(' presentation_event ');
    await statusFilter.fill(' completed ');
    await correlationFilter.fill(' presentation-correlation-2 ');
    await sinceFilter.fill('2025-01-10T00:00');
    await untilFilter.fill('2025-01-20T00:00');
    const activityFilterRequest = page.waitForRequest((request) => {
      const requestUrl = new URL(request.url());
      return (
        requestUrl.pathname === '/api/v1/activity' && requestUrl.searchParams.get('since') !== null
      );
    });
    await page.getByRole('button', { name: 'Apply filters' }).click();
    const filteredActivityRequest = new URL((await activityFilterRequest).url());
    expect(filteredActivityRequest.searchParams.get('event_type')).toBe('presentation_event');
    expect(filteredActivityRequest.searchParams.get('status')).toBe('completed');
    expect(filteredActivityRequest.searchParams.get('correlation_id')).toBe(
      'presentation-correlation-2',
    );
    expect(filteredActivityRequest.searchParams.get('since')).toBe('2025-01-10T00:00:00Z');
    expect(filteredActivityRequest.searchParams.get('until')).toBe('2025-01-20T00:00:00Z');
    expect(filteredActivityRequest.searchParams.get('limit')).toBe('25');

    const activityPagination = page.getByRole('navigation', { name: 'Activity pages' });
    const paginationStatus = activityPagination.locator('.workspace-pagination__status');
    await expect(paginationStatus).toHaveText('Page 1 of 2');
    await expect(page.locator('.event-card')).toHaveCount(25);
    await expect(page.getByText('presentation-event-1', { exact: true })).toBeVisible();
    const firstEventCard = page.locator('.event-card').first();
    await expect(firstEventCard.locator('h2')).toHaveText('optimizer_run');
    const eventDetails = firstEventCard.locator('details');
    await eventDetails.locator('summary').click();
    await expect(eventDetails).toHaveAttribute('open', '');
    await expect(eventDetails).toContainText(firstRun.run_id);
    await expect(page.getByRole('button', { name: /order preview|submit order/i })).toHaveCount(0);

    await page.evaluate(() => window.scrollTo(0, 0));
    const activityDesktopScreenshot = testInfo.outputPath('activity-page-desktop-viewport.png');
    await page.screenshot({ path: activityDesktopScreenshot, fullPage: false });
    await testInfo.attach('activity desktop viewport with filters and first event', {
      path: activityDesktopScreenshot,
      contentType: 'image/png',
    });
    const activityDesktopEventScreenshot = testInfo.outputPath('activity-first-event-desktop.png');
    await firstEventCard.screenshot({ path: activityDesktopEventScreenshot });
    await testInfo.attach('activity desktop first event with expanded JSON', {
      path: activityDesktopEventScreenshot,
      contentType: 'image/png',
    });
    const activityDesktopPaginationScreenshot = testInfo.outputPath(
      'activity-pagination-desktop.png',
    );
    await activityPagination.screenshot({ path: activityDesktopPaginationScreenshot });
    await testInfo.attach('activity desktop pagination', {
      path: activityDesktopPaginationScreenshot,
      contentType: 'image/png',
    });
    const nextActivityPage = activityPagination.getByRole('button', { name: 'Next page' });
    await nextActivityPage.focus();
    await page.keyboard.press('Enter');
    await expect(paginationStatus).toHaveText('Page 2 of 2');
    await expect(page.locator('.event-card')).toHaveCount(1);
    await expect(page.getByText('presentation-event-26', { exact: true })).toBeVisible();
    const previousActivityPage = activityPagination.getByRole('button', { name: 'Previous page' });
    await previousActivityPage.focus();
    await page.keyboard.press('Enter');
    await expect(paginationStatus).toHaveText('Page 1 of 2');
    await expect(page.locator('.event-card')).toHaveCount(25);

    await page.setViewportSize({ width: 390, height: 844 });
    if (!(await eventDetails.evaluate((element) => element.hasAttribute('open')))) {
      await eventDetails.locator('summary').click();
    }
    await expect(eventDetails).toHaveAttribute('open', '');
    await expect(eventDetails.locator('pre')).toBeVisible();
    const mobileActivityLayout = await activityRoot.evaluate((root) => {
      const filterGrid = root.querySelector<HTMLElement>('[data-activity-filter-grid]');
      const title = root.querySelector<HTMLElement>('#activity-title');
      if (!filterGrid || !title) throw new Error('Activity mobile responsive elements are missing');
      return {
        filterColumns: getComputedStyle(filterGrid).gridTemplateColumns,
        filterWidth: filterGrid.getBoundingClientRect().width,
        fieldWidths: Array.from(
          filterGrid.querySelectorAll<HTMLElement>('[data-slot="field"]'),
        ).map((field) => field.getBoundingClientRect().width),
        titleFontSize: getComputedStyle(title).fontSize,
      };
    });
    expect(mobileActivityLayout.filterColumns.split(/\s+/).filter(Boolean)).toHaveLength(1);
    expect(mobileActivityLayout.fieldWidths).toHaveLength(6);
    for (const width of mobileActivityLayout.fieldWidths) {
      expect(Math.abs(width - mobileActivityLayout.filterWidth)).toBeLessThanOrEqual(1);
    }
    expect(parseFloat(mobileActivityLayout.titleFontSize)).toBeGreaterThan(26);
    expect(parseFloat(mobileActivityLayout.titleFontSize)).toBeLessThan(28);
    expect(parseFloat(mobileActivityLayout.titleFontSize)).toBeLessThan(
      parseFloat(desktopActivityLayout.titleFontSize),
    );
    await expectNoHorizontalOverflow(
      page,
      'Activity filters, event details, and pagination at mobile',
    );

    await page.evaluate(() => window.scrollTo(0, 0));
    const activityMobileScreenshot = testInfo.outputPath('activity-page-mobile-viewport.png');
    await page.screenshot({ path: activityMobileScreenshot, fullPage: false });
    await testInfo.attach('activity mobile viewport with filters and first event', {
      path: activityMobileScreenshot,
      contentType: 'image/png',
    });
    const activityMobileEventScreenshot = testInfo.outputPath('activity-first-event-mobile.png');
    await eventDetails.screenshot({ path: activityMobileEventScreenshot });
    await testInfo.attach('activity mobile first event with expanded JSON', {
      path: activityMobileEventScreenshot,
      contentType: 'image/png',
    });
    const activityMobilePaginationScreenshot = testInfo.outputPath(
      'activity-pagination-mobile.png',
    );
    await activityPagination.screenshot({ path: activityMobilePaginationScreenshot });
    await testInfo.attach('activity mobile pagination', {
      path: activityMobilePaginationScreenshot,
      contentType: 'image/png',
    });

    await page.setViewportSize({ width: 1440, height: 1000 });
    await firstEventCard.getByRole('button', { name: 'Reopen saved optimizer run' }).click();
    await expect(page.getByRole('heading', { name: 'Ranked trade groups' })).toBeVisible();
    const reopenedRunContext = page.getByRole('region', { name: 'Frozen run display context' });
    await expect(reopenedRunContext).toContainText(firstRun.policy_revision_id);
    const reopenedRunSummary = page.locator('.run-summary');
    await expect(reopenedRunSummary).toBeVisible();
    const reopenedRunScreenshot = testInfo.outputPath('activity-saved-run-reopened.png');
    await reopenedRunSummary.screenshot({ path: reopenedRunScreenshot });
    await testInfo.attach('activity reopened saved run', {
      path: reopenedRunScreenshot,
      contentType: 'image/png',
    });
  } finally {
    await page.unroute('**/api/v1/activity**', activityPresentationRoute);
  }
  await page.getByRole('link', { name: /Allocation Policy/ }).click();
  await expect(retainedLoss).toHaveValue('3456.78');
  await expect(sleeveName).toHaveValue('Browser renamed US equities');
  await page.getByRole('button', { name: 'Refresh policy list' }).click();
  await expect(retainedLoss).toHaveValue('3456.78');
  let releasePendingSave!: () => void;
  const pendingSaveGate = new Promise<void>((resolve) => {
    releasePendingSave = resolve;
  });
  const policyDraftPostRoute = async (route: Route) => {
    if (route.request().method() === 'POST') {
      const response = await route.fetch();
      await pendingSaveGate;
      await route.fulfill({ response });
      return;
    }
    await route.continue();
  };
  await page.route('**/api/v1/policy/drafts', policyDraftPostRoute);
  try {
    const saveDraftButton = page.getByRole('button', { name: /Saving|Save new draft revision/ });
    await saveDraftButton.click();
    await expect(page.locator('.policy-page')).toHaveAttribute('aria-busy', 'true');
    await expect(page.locator('.policy-page')).toHaveAttribute('inert', '');
    await expect(saveDraftButton).toBeDisabled();
    releasePendingSave();
    await expect(page.getByText(/Current form matches saved revision/)).toBeVisible();
  } finally {
    releasePendingSave();
    await page.unroute('**/api/v1/policy/drafts', policyDraftPostRoute);
  }
  const draftPolicy = await readPolicy(page, seededApp);
  const savedDraft = draftPolicy.drafts.find((revision) => revision.status === 'DRAFT');
  expect(savedDraft).toBeDefined();
  await retainedLoss.fill('4567.89');
  await policyRevisionSelect.focus();
  await page.keyboard.press('Enter');
  const originalRevisionOption = page.getByRole('option', {
    name: `Revision ${initialPolicy.active!.revision_number} · ${initialPolicy.active!.status} · ${originalPolicyId}`,
    exact: true,
  });
  await expect(originalRevisionOption).toBeVisible();
  await page.keyboard.press('Home');
  const firstRevisionOption = page.getByRole('option', {
    name: 'New policy (no source revision)',
    exact: true,
  });
  await expect(firstRevisionOption).toBeFocused();
  await page.keyboard.press('ArrowDown');
  await expect(originalRevisionOption).toBeFocused();
  await page.keyboard.press('Enter');
  const pendingRevisionNotice = page.getByText(
    'There are unsaved edits. Loading another revision will discard them.',
  );
  await expect(pendingRevisionNotice).toBeVisible();
  await page.getByRole('button', { name: 'Keep editing' }).click();
  await expect(pendingRevisionNotice).toHaveCount(0);
  await expect(retainedLoss).toHaveValue('4567.89');

  await policyRevisionSelect.click();
  await originalRevisionOption.click();
  await expect(pendingRevisionNotice).toBeVisible();
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
  await expect(page.getByRole('heading', { name: 'Tax Lots', exact: true })).toBeVisible();
  await expect(lotSearch).toHaveValue('DEMO-VB-LOT-1');
  await page.evaluate(() => window.scrollTo(0, 0));
  const desktopPageTopPath = testInfo.outputPath('tax-lots-desktop-page-top.png');
  await page.screenshot({ path: desktopPageTopPath });
  await testInfo.attach('tax lots desktop page viewport with heading and filters', {
    path: desktopPageTopPath,
    contentType: 'image/png',
  });
  await expectNoHorizontalOverflow(page, 'tax-lot table at desktop');
  const lotRegion = page.locator('[role="region"][aria-label^="Tax lots for "]').first();
  await expect(lotRegion).toBeVisible();
  await expect(lotRegion).toHaveAttribute('tabindex', '0');
  await expect(lotRegion.locator('table[data-slot="table"]')).toHaveCount(1);
  await expect(lotRegion.locator('thead th:not([scope="col"])')).toHaveCount(0);
  const desktopTablePath = testInfo.outputPath('tax-lots-desktop-table-viewport.png');
  await lotRegion.screenshot({ path: desktopTablePath });
  await testInfo.attach('tax lots desktop table viewport', {
    path: desktopTablePath,
    contentType: 'image/png',
  });
  const desktopFirstTableHeader = lotRegion.locator('thead');
  await desktopFirstTableHeader.evaluate((element) => element.scrollIntoView({ block: 'start' }));
  await expect(desktopFirstTableHeader).toBeInViewport();
  const desktopFirstTablePagePath = testInfo.outputPath(
    'tax-lots-desktop-first-table-page-viewport.png',
  );
  await page.screenshot({ path: desktopFirstTablePagePath });
  await testInfo.attach('tax lots desktop page viewport scrolled to first table', {
    path: desktopFirstTablePagePath,
    contentType: 'image/png',
  });
  const desktopPaginationPath = testInfo.outputPath('tax-lots-desktop-pagination.png');
  const taxLotPagination = page.getByRole('navigation', { name: 'Tax lot API pages' });
  await taxLotPagination.screenshot({ path: desktopPaginationPath });
  await testInfo.attach('tax lots desktop pagination', {
    path: desktopPaginationPath,
    contentType: 'image/png',
  });
  const sortTrigger = page.getByRole('combobox', { name: 'Sort API results by' });
  await sortTrigger.focus();
  await expect(sortTrigger).toBeFocused();
  await sortTrigger.press('ArrowDown');
  const sortOption = page.getByRole('option', { name: 'Broker lot ID', exact: true });
  await expect(sortOption).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(sortOption).not.toBeVisible();
  await expect(sortTrigger).toBeFocused();

  await page.setViewportSize({ width: 768, height: 1024 });
  await expect(lotRegion).toBeVisible();
  await expect
    .poll(() => lotRegion.evaluate((element) => element.scrollWidth > element.clientWidth))
    .toBe(true);
  await expectNoHorizontalOverflow(page, 'tax-lot table at tablet');
  await page.setViewportSize({ width: 375, height: 812 });
  await expectNoHorizontalOverflow(page, 'tax-lot table at mobile');
  await expect
    .poll(() => lotRegion.evaluate((element) => element.scrollWidth > element.clientWidth))
    .toBe(true);
  await expect(page.getByRole('heading', { name: 'Tax Lots', exact: true })).toBeVisible();
  await expect(lotSearch).toHaveValue('DEMO-VB-LOT-1');
  await page.evaluate(() => window.scrollTo(0, 0));
  const mobilePageTopPath = testInfo.outputPath('tax-lots-mobile-page-top.png');
  await page.screenshot({ path: mobilePageTopPath });
  await testInfo.attach('tax lots mobile page viewport with heading and filters', {
    path: mobilePageTopPath,
    contentType: 'image/png',
  });
  const mobileTablePath = testInfo.outputPath('tax-lots-mobile-table-viewport.png');
  await lotRegion.screenshot({ path: mobileTablePath });
  await testInfo.attach('tax lots mobile table viewport', {
    path: mobileTablePath,
    contentType: 'image/png',
  });
  const mobileFirstTableHeader = lotRegion.locator('thead');
  await mobileFirstTableHeader.evaluate((element) => element.scrollIntoView({ block: 'start' }));
  await expect(mobileFirstTableHeader).toBeInViewport();
  const mobileFirstTablePagePath = testInfo.outputPath(
    'tax-lots-mobile-first-table-page-viewport.png',
  );
  await page.screenshot({ path: mobileFirstTablePagePath });
  await testInfo.attach('tax lots mobile page viewport scrolled to first table', {
    path: mobileFirstTablePagePath,
    contentType: 'image/png',
  });
  const mobilePaginationPath = testInfo.outputPath('tax-lots-mobile-pagination.png');
  await taxLotPagination.screenshot({ path: mobilePaginationPath });
  await testInfo.attach('tax lots mobile pagination', {
    path: mobilePaginationPath,
    contentType: 'image/png',
  });
  await lotRegion.evaluate((element) => {
    element.scrollLeft = element.scrollWidth;
  });
  const horizontalScroll = await lotRegion.evaluate((element) => element.scrollLeft);
  expect(horizontalScroll).toBeGreaterThan(0);
  await lotRegion.evaluate((element) => {
    element.scrollLeft = 0;
  });
  await lotRegion.focus();
  await expect(lotRegion).toBeFocused();
  const vbLot = page.getByRole('checkbox', { name: 'Request VB lot DEMO-VB-LOT-1' });
  await expect(vbLot).toBeVisible();
  await vbLot.focus();
  await expect(vbLot).toBeFocused();
  await vbLot.press('Space');
  await expect(vbLot).toBeChecked();
  await expect(page.getByRole('heading', { name: /Requested lot intent/ })).toContainText('1');
  const lotIntentPanelPath = testInfo.outputPath('tax-lots-mobile-intent-panel.png');
  await page.locator('.review-summary').screenshot({ path: lotIntentPanelPath });
  await testInfo.attach('tax lots mobile intent panel', {
    path: lotIntentPanelPath,
    contentType: 'image/png',
  });
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

  const selectedSellLeg = confirmedLots.consolidated_legs.find(
    (leg) =>
      leg.side === 'SELL' &&
      leg.selected_lots.some((lot) => lot.broker_lot_id === 'DEMO-VB-LOT-1' && lot.selected),
  );
  if (!selectedSellLeg) {
    throw new Error('The confirmed FakeBroker response has no selected SELL leg');
  }
  const sellGroupId = selectedSellLeg.group_ids.find((candidate) =>
    confirmedLots.groups.some((group) => group.group_id === candidate),
  );
  if (!sellGroupId) {
    throw new Error(`SELL leg ${selectedSellLeg.leg_id} has no linked recommendation group`);
  }

  await page.getByRole('link', { name: /Recommendations/ }).click();
  await expect(page.getByRole('heading', { name: 'Ranked trade groups' })).toBeVisible();
  const sellGroupHeader = page.getByRole('button', {
    name: `Tax-loss harvest Group ID ${sellGroupId}`,
    exact: true,
  });
  await expect(sellGroupHeader).toHaveAccessibleName(`Tax-loss harvest Group ID ${sellGroupId}`);
  const sellGroupCard = page.locator('.group-card').filter({ has: sellGroupHeader });
  await expect(sellGroupCard).toBeVisible();
  await expect(sellGroupHeader).toHaveAttribute('aria-expanded', 'false');
  await sellGroupHeader.focus();
  await sellGroupHeader.press('Enter');
  await expect(sellGroupHeader).toHaveAttribute('aria-expanded', 'true');
  await sellGroupHeader.press('Space');
  await expect(sellGroupHeader).toHaveAttribute('aria-expanded', 'false');
  await sellGroupHeader.click();
  await expect(sellGroupHeader).toHaveAttribute('aria-expanded', 'true');

  const groupFacts = sellGroupCard.locator('.group-facts');
  const annotationPanel = sellGroupCard.locator('.annotation-panel');
  const groupNoteField = annotationPanel.locator('textarea');
  const rejectionField = annotationPanel.getByRole('textbox', {
    name: 'Rejection reason (up to 500 characters)',
  });
  await expect(groupFacts).toBeVisible();
  await expect(annotationPanel).toBeVisible();
  await expect(groupNoteField).toBeVisible();
  await expect(rejectionField).toBeVisible();
  await expectNoHorizontalOverflow(page, 'recommendation group at desktop');
  expect(await sellGroupHeader.evaluate((element) => getComputedStyle(element).flexDirection)).toBe(
    'row',
  );

  const desktopGroupHeaderPath = testInfo.outputPath('fakebroker-trade-group-header-desktop.png');
  await sellGroupHeader.screenshot({ path: desktopGroupHeaderPath });
  await testInfo.attach('FakeBroker trade-group header desktop', {
    path: desktopGroupHeaderPath,
    contentType: 'image/png',
  });
  const desktopGroupFactsPath = testInfo.outputPath('fakebroker-trade-group-facts-desktop.png');
  await groupFacts.screenshot({ path: desktopGroupFactsPath });
  await testInfo.attach('FakeBroker trade-group financial facts desktop', {
    path: desktopGroupFactsPath,
    contentType: 'image/png',
  });
  const desktopAnnotationPath = testInfo.outputPath(
    'fakebroker-trade-group-annotations-desktop.png',
  );
  await annotationPanel.screenshot({ path: desktopAnnotationPath });
  await testInfo.attach('FakeBroker trade-group annotation controls desktop', {
    path: desktopAnnotationPath,
    contentType: 'image/png',
  });
  await groupNoteField.focus();
  await expect(groupNoteField).toBeFocused();
  const sellLegAnchor = `leg-${encodeURIComponent(selectedSellLeg.leg_id)}`;
  const sellLegArticle = sellGroupCard.locator(`[id="${sellLegAnchor}"]`);
  await expect(sellLegArticle).toHaveCount(1);
  await expect(sellLegArticle).toHaveAttribute('id', sellLegAnchor);
  const legFacts = sellLegArticle.locator('.leg-facts');
  await expect(legFacts.getByText('Leg ID', { exact: true })).toBeVisible();
  await expect(legFacts).toContainText(selectedSellLeg.leg_id);
  await expect(legFacts.getByText('API-proposed whole shares', { exact: true })).toBeVisible();
  await expect(legFacts).toContainText(selectedSellLeg.shares);
  const desktopFactColumns = await legFacts.evaluate(
    (element) => getComputedStyle(element).gridTemplateColumns.trim().split(/\s+/).length,
  );
  expect(desktopFactColumns, 'desktop SELL-leg facts grid columns').toBeGreaterThan(1);

  const legHeading = sellLegArticle.locator('h3');
  const dependencyNote = sellLegArticle.locator('.dependency-note');
  const selectionStatus = sellLegArticle.locator('.leg-status');
  await expect(legHeading).toBeVisible();
  await expect(dependencyNote).toBeVisible();
  await expect(selectionStatus).toBeVisible();
  await expect(selectionStatus).toContainText(/(?:Selected|Not selected) in this API basket/);
  await sellLegArticle.scrollIntoViewIfNeeded();
  await expect(legHeading).toBeInViewport();
  await expect(legFacts).toBeInViewport();
  await expect(dependencyNote).toBeInViewport();
  await expect(selectionStatus).toBeInViewport();
  const desktopLegDetailsPath = testInfo.outputPath('fakebroker-sell-leg-details-desktop.png');
  await page.screenshot({ path: desktopLegDetailsPath });
  await testInfo.attach('FakeBroker SELL leg details desktop page viewport', {
    path: desktopLegDetailsPath,
    contentType: 'image/png',
  });
  const sellLotRegion = sellGroupCard.getByRole('region', {
    name: `SELL broker-lot attribution for leg ${selectedSellLeg.leg_id}`,
  });
  await expect(sellLotRegion).toBeVisible();
  await expect(sellLotRegion.locator('thead th[scope="col"]')).toHaveCount(8);
  const desktopSellAttributionPath = testInfo.outputPath(
    'fakebroker-sell-lot-attribution-desktop.png',
  );
  await sellLotRegion.screenshot({ path: desktopSellAttributionPath });
  await testInfo.attach('FakeBroker SELL-lot attribution desktop', {
    path: desktopSellAttributionPath,
    contentType: 'image/png',
  });

  await page.setViewportSize({ width: 375, height: 812 });
  await expectNoHorizontalOverflow(page, 'SELL lot attribution at mobile');
  await expect(sellGroupHeader).toBeVisible();
  expect(await sellGroupHeader.evaluate((element) => getComputedStyle(element).flexDirection)).toBe(
    'column',
  );

  const mobileHeaderTextLayout = await sellGroupHeader
    .locator('.group-header-text')
    .evaluate((element) => {
      const title = element.querySelector<HTMLElement>('.group-title');
      const description = element.querySelector<HTMLElement>('.group-description');
      if (!title || !description) throw new Error('Trade-group header text nodes are missing');
      return {
        blockClientWidth: element.clientWidth,
        blockScrollWidth: element.scrollWidth,
        titleText: title.textContent ?? '',
        titleClientWidth: title.clientWidth,
        titleScrollWidth: title.scrollWidth,
        descriptionText: description.textContent ?? '',
        descriptionClientWidth: description.clientWidth,
        descriptionScrollWidth: description.scrollWidth,
      };
    });
  expect(mobileHeaderTextLayout.titleText).toContain('Tax-loss harvest');
  expect(mobileHeaderTextLayout.descriptionText.trim()).toContain('·');
  expect(
    mobileHeaderTextLayout.blockScrollWidth,
    'mobile header text block fits its card width',
  ).toBeLessThanOrEqual(mobileHeaderTextLayout.blockClientWidth);
  expect(
    mobileHeaderTextLayout.titleScrollWidth,
    'mobile economic-intent title fits its text block',
  ).toBeLessThanOrEqual(mobileHeaderTextLayout.titleClientWidth);
  expect(
    mobileHeaderTextLayout.descriptionScrollWidth,
    'mobile group and sleeve description fits',
  ).toBeLessThanOrEqual(mobileHeaderTextLayout.descriptionClientWidth);
  if ((await sellGroupHeader.getAttribute('aria-expanded')) === 'true') {
    await sellGroupHeader.focus();
    await sellGroupHeader.press('Enter');
  }
  await expect(sellGroupHeader).toHaveAttribute('aria-expanded', 'false');
  await sellGroupHeader.focus();
  await sellGroupHeader.press('Enter');
  await expect(sellGroupHeader).toHaveAttribute('aria-expanded', 'true');
  const mobileGroupHeaderPath = testInfo.outputPath('fakebroker-trade-group-header-mobile.png');
  await sellGroupHeader.screenshot({ path: mobileGroupHeaderPath });
  await testInfo.attach('FakeBroker trade-group header mobile', {
    path: mobileGroupHeaderPath,
    contentType: 'image/png',
  });
  const mobileGroupFactsPath = testInfo.outputPath('fakebroker-trade-group-facts-mobile.png');
  await groupFacts.screenshot({ path: mobileGroupFactsPath });
  await testInfo.attach('FakeBroker trade-group financial facts mobile', {
    path: mobileGroupFactsPath,
    contentType: 'image/png',
  });
  const mobileAnnotationPath = testInfo.outputPath('fakebroker-trade-group-annotations-mobile.png');
  await annotationPanel.screenshot({ path: mobileAnnotationPath });
  await testInfo.attach('FakeBroker trade-group annotation controls mobile', {
    path: mobileAnnotationPath,
    contentType: 'image/png',
  });
  await groupNoteField.focus();
  await expect(groupNoteField).toBeFocused();
  const mobileFactColumns = await legFacts.evaluate(
    (element) => getComputedStyle(element).gridTemplateColumns.trim().split(/\s+/).length,
  );
  expect(mobileFactColumns, 'mobile SELL-leg facts grid columns').toBe(1);

  await sellLegArticle.scrollIntoViewIfNeeded();
  await expect(legHeading).toBeInViewport();
  await expect(legFacts).toBeInViewport();
  await expect(dependencyNote).toBeInViewport();
  await expect(selectionStatus).toBeInViewport();
  const mobileLegDetailsPath = testInfo.outputPath('fakebroker-sell-leg-details-mobile.png');
  await page.screenshot({ path: mobileLegDetailsPath });
  await testInfo.attach('FakeBroker SELL leg details mobile page viewport', {
    path: mobileLegDetailsPath,
    contentType: 'image/png',
  });
  const sellLotTableScroller = sellLotRegion.locator('[data-slot="table-container"]');
  await expect
    .poll(() =>
      sellLotTableScroller.evaluate((element) => element.scrollWidth > element.clientWidth),
    )
    .toBe(true);
  await expect
    .poll(() => sellLotRegion.evaluate((element) => element.scrollWidth > element.clientWidth))
    .toBe(true);
  expect(
    await sellLotTableScroller.evaluate((element) => getComputedStyle(element).overflowX),
  ).toBe('visible');
  await expect.poll(() => sellLotRegion.evaluate((element) => element.scrollLeft)).toBe(0);
  await sellLotRegion.focus();
  await expect(sellLotRegion).toBeFocused();
  await sellLotRegion.press('ArrowRight');
  await expect
    .poll(() => sellLotRegion.evaluate((element) => element.scrollLeft))
    .toBeGreaterThan(0);
  const mobileSellAttributionPath = testInfo.outputPath(
    'fakebroker-sell-lot-attribution-mobile.png',
  );
  await sellLotRegion.screenshot({ path: mobileSellAttributionPath });
  await testInfo.attach('FakeBroker SELL-lot attribution mobile', {
    path: mobileSellAttributionPath,
    contentType: 'image/png',
  });

  const sellLotCheckbox = sellLotRegion.getByRole('checkbox', {
    name: `Select SELL lot DEMO-VB-LOT-1 in group ${sellGroupId}`,
  });
  await sellLotCheckbox.focus();
  await expect(sellLotCheckbox).toBeFocused();
  const deselectResponsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === 'POST' &&
      response.url().includes('/optimizer/runs/') &&
      response.url().endsWith('/selection'),
  );
  await sellLotCheckbox.press('Space');
  const deselectResponse = await deselectResponsePromise;
  expect(deselectResponse.ok(), 'FakeBroker accepted keyboard SELL-lot selection').toBe(true);
  const deselectedRecommendations = await readRecommendations(page, seededApp, currentRun.run_id);
  const deselectedSellLotIds = deselectedRecommendations.consolidated_legs
    .filter((leg) => leg.side === 'SELL')
    .flatMap((leg) =>
      leg.selected_lots.filter((lot) => lot.selected).map((lot) => lot.broker_lot_id),
    );
  expect(deselectedSellLotIds).toEqual([]);

  const navigationToggle = page.getByRole('button', { name: 'Toggle workspace navigation' });
  if ((await navigationToggle.getAttribute('aria-expanded')) !== 'true') {
    await navigationToggle.click();
  }
  await page.getByRole('link', { name: /Tax Lots/ }).click();
  const applyCompleteSetButton = page.getByRole('button', {
    name: 'Apply complete set to current DEMO run',
  });
  await expect(applyCompleteSetButton).toBeEnabled();
  const restoreResponsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === 'POST' &&
      response.url().includes('/optimizer/runs/') &&
      response.url().endsWith('/lot-review-intent'),
  );
  await applyCompleteSetButton.click();
  const restoreResponse = await restoreResponsePromise;
  expect(restoreResponse.ok(), 'FakeBroker accepted restoration of the complete lot intent').toBe(
    true,
  );
  await expect(
    page.getByText(/The loaded DEMO run currently selects exactly this requested set/),
  ).toBeVisible();
  const restoredRecommendations = await readRecommendations(page, seededApp, currentRun.run_id);
  const restoredSellLotIds = restoredRecommendations.consolidated_legs
    .filter((leg) => leg.side === 'SELL')
    .flatMap((leg) =>
      leg.selected_lots.filter((lot) => lot.selected).map((lot) => lot.broker_lot_id),
    );
  expect(restoredSellLotIds).toEqual(['DEMO-VB-LOT-1']);
  if ((await navigationToggle.getAttribute('aria-expanded')) !== 'true') {
    await navigationToggle.click();
  }
  await page.getByRole('link', { name: /Recommendations/ }).click();
  await expect(page.getByRole('heading', { name: 'Ranked trade groups' })).toBeVisible();
  const groupHeader = page.getByRole('button', { name: /^Tax-loss harvest Group ID / }).first();
  const groupId = await groupHeader.getAttribute('data-group-id');
  if (!groupId) throw new Error('The first recommendation group has no identifier');
  const groupCard = page.locator('.group-card').filter({ has: groupHeader });
  const initialRecommendations = await readRecommendations(page, seededApp, currentRun.run_id);
  const initialGroup = initialRecommendations.groups.find((group) => group.group_id === groupId);
  if (!initialGroup) throw new Error(`Recommendation group ${groupId} is missing from the API`);
  await expect(groupHeader).toHaveAttribute('aria-expanded', 'false');
  await expect(groupHeader).toContainText(`Priority ${initialGroup.rank}`);
  await expect(groupHeader).toContainText('Tax-loss harvest');
  await expect(groupHeader).toContainText(initialGroup.rationale);
  await expect(groupHeader).toContainText('API realized ST / LT:');
  await expect(groupHeader).toContainText(
    `${initialGroup.impact.selected_sell_lots_count} sell lots`,
  );
  if ((await groupHeader.getAttribute('aria-expanded')) !== 'true') {
    await groupHeader.focus();
    await expect(groupHeader).toBeFocused();
    await groupHeader.press('Enter');
  }
  await expect(groupHeader).toHaveAttribute('aria-expanded', 'true');
  const groupCheckbox = groupCard.getByRole('checkbox', {
    name: `Select recommendation group ${groupId}`,
  });
  const selectionTools = page.locator('.selection-tools');
  const clearGroups = selectionTools.getByRole('button', {
    name: 'Clear selected groups and re-solve',
  });
  const clearResponsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === 'POST' &&
      response.url().includes('/optimizer/runs/') &&
      response.url().endsWith('/selection'),
  );
  await clearGroups.click();
  const clearResponse = await clearResponsePromise;
  expect(clearResponse.ok(), 'FakeBroker accepted clearing selected groups').toBe(true);
  const emptyBasket = page.locator('.selected-basket-summary');
  await expect(emptyBasket).toContainText('0 / 0 / 0');
  await expect(emptyBasket).not.toContainText('Realized ST P/L');
  await expect(emptyBasket).not.toContainText('Realized LT P/L');
  if ((await groupHeader.getAttribute('aria-expanded')) !== 'true') await groupHeader.click();
  await expect(groupHeader).toHaveAttribute('aria-expanded', 'true');
  await expect(groupCheckbox).not.toBeChecked();

  await groupCheckbox.focus();
  await expect(groupCheckbox).toBeFocused();
  const selectGroupResponsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === 'POST' &&
      response.url().includes('/optimizer/runs/') &&
      response.url().endsWith('/selection'),
  );
  await groupCheckbox.press('Space');
  const selectGroupResponse = await selectGroupResponsePromise;
  expect(
    selectGroupResponse.ok(),
    'FakeBroker accepted keyboard group selection and re-solve',
  ).toBe(true);

  const selectedRecommendations = await readRecommendations(page, seededApp, currentRun.run_id);
  const selectedGroupCount = selectedRecommendations.groups.filter(
    (group) => group.selected && !group.rejected,
  ).length;
  const selectedBasketLotCount = new Set(
    selectedRecommendations.consolidated_legs
      .filter((leg) => leg.side === 'SELL' && leg.selected)
      .flatMap((leg) =>
        leg.selected_lots.filter((lot) => lot.selected).map((lot) => lot.broker_lot_id),
      ),
  ).size;
  const selectedBasketOrderCount = selectedRecommendations.consolidated_legs.filter(
    (leg) => leg.selected,
  ).length;
  await expect(emptyBasket).toContainText(
    `${selectedGroupCount} / ${selectedBasketLotCount} / ${selectedBasketOrderCount}`,
  );
  expect(selectedGroupCount).toBeGreaterThan(0);
  await expect(emptyBasket.getByText('Realized ST P/L', { exact: true })).toBeVisible();
  await expect(emptyBasket.getByText('Realized LT P/L', { exact: true })).toBeVisible();
  await expect(emptyBasket.getByText('Net realized P/L (ST + LT)', { exact: true })).toBeVisible();
  const expectedSelectedLegs = selectedRecommendations.consolidated_legs
    .filter((leg) => leg.selected)
    .sort((left, right) => left.sequence - right.sequence);
  const expectedSelectedSellLots = expectedSelectedLegs
    .filter((leg) => leg.side === 'SELL')
    .flatMap((leg) => leg.selected_lots.filter((lot) => lot.selected));
  const expectedUnselectedSellLots = selectedRecommendations.consolidated_legs
    .filter((leg) => leg.side === 'SELL' && leg.selected)
    .flatMap((leg) => leg.selected_lots.filter((lot) => !lot.selected));
  const reviewFromSummary = page.getByRole('link', { name: 'Review selected trades', exact: true });
  await reviewFromSummary.focus();
  await expect(reviewFromSummary).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/#\/review$/);
  await expect(page.getByRole('heading', { name: 'Selected trades', exact: true })).toBeFocused();
  await expect(page.locator('[data-review-state="current"]')).toContainText(
    'Current run and selection are confirmed by the API',
  );
  await expect(page.locator('article.leg-card')).toHaveCount(expectedSelectedLegs.length);
  await expect(page.locator('#selected-basket-financials-title')).toBeVisible();
  await expect(
    page.getByText('Gross losses (selected SELL lots only)', { exact: true }),
  ).toBeVisible();
  await expect(page.getByText('Signed net realized P/L (ST + LT)', { exact: true })).toBeVisible();
  for (const lot of expectedSelectedSellLots) {
    await expect(page.getByText(lot.broker_lot_id, { exact: true })).toBeVisible();
  }
  for (const lot of expectedUnselectedSellLots) {
    await expect(page.getByText(lot.broker_lot_id, { exact: true })).toHaveCount(0);
  }
  for (const leg of expectedSelectedLegs.filter((candidate) => candidate.side === 'BUY')) {
    await expect(page.getByText(leg.leg_id, { exact: true })).toHaveCount(1);
  }
  await page.goBack();
  await expect(page.getByRole('heading', { name: 'Ranked trade groups' })).toBeVisible();
  if ((await navigationToggle.getAttribute('aria-expanded')) !== 'true') {
    await navigationToggle.click();
  }
  const reviewFromSidebar = page.getByRole('link', { name: 'Selected basket' });
  await reviewFromSidebar.focus();
  await expect(reviewFromSidebar).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/#\/review$/);
  await expect(page.getByRole('heading', { name: 'Selected trades', exact: true })).toBeFocused();
  await expect(page.locator('article.leg-card')).toHaveCount(expectedSelectedLegs.length);
  for (const lot of expectedSelectedSellLots) {
    await expect(page.getByText(lot.broker_lot_id, { exact: true })).toBeVisible();
  }
  await page.goBack();
  await expect(page.getByRole('heading', { name: 'Ranked trade groups' })).toBeVisible();
  if ((await groupHeader.getAttribute('aria-expanded')) !== 'true') {
    await groupHeader.click();
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
    await pendingAnnotation;
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
    await expect(groupHeader).toBeVisible();
    if ((await groupHeader.getAttribute('aria-expanded')) !== 'true') {
      await groupHeader.click();
    }
    await expect(noteField).toHaveValue('E2E note across route remount');

    if ((await navigationToggle.getAttribute('aria-expanded')) !== 'true') {
      await navigationToggle.click();
    }
    await page.getByRole('link', { name: /Activity/ }).click();
    await expect(page.getByRole('heading', { name: 'Activity', exact: true })).toBeVisible();
    if ((await navigationToggle.getAttribute('aria-expanded')) !== 'true') {
      await navigationToggle.click();
    }
    await page.getByRole('link', { name: /Recommendations/ }).click();
    await expect(page.getByRole('heading', { name: 'Ranked trade groups' })).toBeVisible();
    await expect(groupHeader).toBeVisible();
    if ((await groupHeader.getAttribute('aria-expanded')) !== 'true') {
      await groupHeader.click();
    }
    await expect(groupCard.locator('textarea')).toHaveValue('E2E note across route remount');
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
  await expect
    .poll(async () => (await readGroup(page, seededApp, currentRun.run_id, groupId))?.note)
    .toBeNull();
  await expect(groupHeader).toBeVisible();
  if ((await groupHeader.getAttribute('aria-expanded')) !== 'true') {
    await groupHeader.click();
  }
  await expect(restoredNoteField).toHaveValue('');

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

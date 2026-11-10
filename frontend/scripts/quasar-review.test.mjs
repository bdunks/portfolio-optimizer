import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { after, afterEach, before, beforeEach, test } from 'node:test';
import { chromium, expect } from '@playwright/test';

const { validateDispositions } = await import(new URL('./quasar-audit.mts', import.meta.url).href);
const viewer = new URL('../../docs/quasar-audit/review.html', import.meta.url).href;
const inventoryPath = fileURLToPath(
  new URL('../../docs/quasar-audit/inventory.json', import.meta.url),
);
const finding = (id, file, rule, confidence) => ({
  id,
  file,
  rule,
  confidence,
  line: 12,
  column: 3,
  evidence: '<button :disabled="busy">Save</button>',
  context: 'template <button>',
  suggestion: 'QBtn',
  caution: 'Preserve submit and decimal-string values.',
});
const inventory = {
  schemaVersion: 1,
  scope: 'frontend/src',
  limitations: ['Candidates, not defects.'],
  findings: [
    finding('z1', 'frontend/src/A.vue', 'template.native-control', 'high'),
    finding('a2', 'frontend/src/A.vue', 'css.surface', 'medium'),
    finding('m3', 'frontend/src/B.vue', 'template.native-control', 'high'),
    finding('h4', 'frontend/src/B.vue', 'css.layout-spacing', 'low'),
  ],
};
let browser, context, page, errors, requests;
before(async () => {
  browser = await chromium.launch();
});
after(async () => {
  await browser?.close();
});
beforeEach(async () => {
  context = await browser.newContext({
    acceptDownloads: true,
    viewport: { width: 1280, height: 900 },
  });
  page = await context.newPage();
  errors = [];
  requests = [];
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('request', (request) => {
    if (/^https?:/.test(request.url())) requests.push(request.url());
  });
  await page.goto(viewer);
});
afterEach(async () => {
  await context.close();
  assert.deepEqual(errors, [], 'No page JavaScript errors');
  assert.deepEqual(requests, [], 'Viewer must not send network requests');
});
async function upload(selector, value, name = 'input.json') {
  await page.locator(selector).setInputFiles({
    name,
    mimeType: 'application/json',
    buffer: Buffer.from(typeof value === 'string' ? value : JSON.stringify(value)),
  });
  await expect(page.locator('#inventory-file')).toBeEnabled();
}
async function load() {
  await upload('#inventory-file', inventory);
  await expect(page.locator('#counts')).toContainText('4 findings');
}
async function openGroup(file = 'A.vue') {
  const group = page
    .locator('.group')
    .filter({ has: page.locator(':scope > summary', { hasText: file }) });
  await group.locator(':scope > summary').click();
  return group;
}
async function confirmBulk() {
  await page.locator('#confirm').click();
  await expect(page.locator('#review-dialog')).not.toBeVisible();
}
async function exported() {
  const downloaded = page.waitForEvent('download');
  await page.locator('#export').click();
  const download = await downloaded;
  assert.equal(download.suggestedFilename(), 'dispositions.json');
  const text = await readFile(await download.path(), 'utf8');
  const values = JSON.parse(text);
  validateDispositions(values, inventory.findings);
  for (const entry of values)
    assert.deepEqual(Object.keys(entry).sort(), ['disposition', 'findingId']);
  assert.equal(text, JSON.stringify(values, null, 2) + '\n');
  return values;
}

test('loads full real inventory locally and groups/filters it', async () => {
  await expect(page.locator('#export')).toBeDisabled();
  await page.locator('#inventory-file').setInputFiles(inventoryPath);
  const actual = JSON.parse(await readFile(inventoryPath, 'utf8'));
  await expect(page.locator('#counts')).toContainText(`${actual.findings.length} findings`);
  await expect(page.locator('.group')).toHaveCount(
    new Set(actual.findings.map((f) => f.file)).size,
  );
  await page.locator('#group-by').selectOption('rule');
  await expect(page.locator('.group')).toHaveCount(
    new Set(actual.findings.map((f) => f.rule)).size,
  );

  const query = actual.findings[0].id.toLowerCase();
  const matches = actual.findings.filter((f) =>
    [f.file, f.rule, f.evidence, f.context, f.suggestion, f.caution, f.id, 'unreviewed']
      .join(' ')
      .toLowerCase()
      .includes(query),
  );
  assert.ok(matches.length > 0, 'Search query comes from a real finding ID.');
  assert.ok(matches.length < actual.findings.length, 'Search must filter out findings.');
  await page.locator('#search').fill(query);
  await expect(page.locator('#counts')).toContainText(`${matches.length} visible`);
  await expect(page.locator('.group')).toHaveCount(new Set(matches.map((f) => f.rule)).size);
  await expect(page.locator('article')).toHaveCount(matches.length);

  const target = matches[0];
  const visibleInGroup = matches.filter((f) => f.rule === target.rule).length;
  const totalInGroup = actual.findings.filter((f) => f.rule === target.rule).length;
  const group = page.locator('.group').filter({
    has: page.locator(':scope > summary', {
      hasText: `${target.rule} — ${visibleInGroup} visible / ${totalInGroup} total`,
    }),
  });
  await expect(group).toHaveCount(1);
  await group.locator(':scope > summary').click();
  const targetArticle = page.locator(`[id="finding-${target.id}"]`);
  await expect(targetArticle).toBeVisible();
  await expect(targetArticle).toContainText(target.file);
});

test('current context/evidence and suggested equivalent are visible without expanding caution', async () => {
  await load();
  await openGroup();
  const card = page.locator('#finding-z1');
  await expect(card.locator('.current')).toContainText('Current');
  await expect(card.locator('.current .muted')).toHaveText('template <button>');
  await expect(card.locator('.current pre')).toBeVisible();
  await expect(card.locator('.current pre')).toHaveText(inventory.findings[0].evidence);
  await expect(card.locator('.suggested')).toContainText('Suggested equivalent');
  await expect(card.locator('.suggested p')).toBeVisible();
  await expect(card.locator('.suggested p')).toHaveText('QBtn');
  await expect(card.locator('.finding-head .status-badge')).toHaveText('unreviewed');
  await expect(card.locator('details')).not.toHaveAttribute('open');
  await expect(card.locator('details p').first()).not.toBeVisible();
  await expect(card.getByRole('button')).toHaveCount(2);
  await expect(page.locator('#reason, #decision, textarea')).toHaveCount(0);
});

test('Approve/Reject act immediately, update a badge, and allow changing the same decision again', async () => {
  await load();
  await openGroup();
  const card = page.locator('#finding-z1');
  const approve = card.getByRole('button', { name: 'Approve', exact: true });
  const reject = card.getByRole('button', { name: 'Reject', exact: true });
  for (const [button, state] of [
    [approve, 'approved'],
    [reject, 'rejected'],
    [approve, 'approved'],
  ]) {
    await button.click();
    await expect(page.locator('#review-dialog')).not.toBeVisible();
    await expect(card.locator('.status-badge')).toHaveText(state);
    await expect(button).toHaveAttribute('aria-pressed', 'true');
    await expect(button).toBeFocused();
    await expect(page.locator('#counts')).toContainText('1 reviewed');
    assert.deepEqual(await exported(), [{ findingId: 'z1', disposition: state }]);
  }
});

test('visible-group and entire-group bulk actions preview distinct targets; cancel/Escape are safe', async () => {
  await load();
  await page.locator('#confidence').selectOption('high');
  const group = await openGroup();
  await group.getByRole('button', { name: 'Approve visible in group (1)', exact: true }).click();
  await expect(page.locator('#target-summary')).toContainText('1 finding(s)');
  await expect(page.locator('#confirm')).toHaveText('Approve');
  await page.locator('#cancel').click();
  await group.getByRole('button', { name: 'Reject entire group (2)', exact: true }).click();
  await expect(page.locator('#target-summary')).toContainText(
    'including hidden findings: 2 finding(s)',
  );
  await page.keyboard.press('Escape');
  await expect(page.locator('#counts')).toContainText('0 reviewed');
  await group.getByRole('button', { name: 'Reject entire group (2)', exact: true }).click();
  assert.equal(await page.locator('#targets li').count(), 2);
  await expect(page.locator('#confirm')).toHaveText('Reject');
  await confirmBulk();
  assert.deepEqual(await exported(), [
    { findingId: 'a2', disposition: 'rejected' },
    { findingId: 'z1', disposition: 'rejected' },
  ]);
  await page.locator('#disposition-filter').selectOption('unreviewed');
  await expect(page.locator('#counts')).toContainText('1 visible');
});

test('hidden selections and all-filtered actions only affect their explicit targets', async () => {
  await load();
  await openGroup();
  await page.getByRole('checkbox', { name: 'Select a2', exact: true }).check();
  await page.locator('#search').fill('B.vue');
  await expect(page.locator('#counts')).toContainText('1 selected (1 hidden)');
  await page.locator('#approve-selected').click();
  await expect(page.locator('#target-summary')).toContainText(
    'including hidden selections): 1 finding(s)',
  );
  await confirmBulk();
  assert.deepEqual(await exported(), [{ findingId: 'a2', disposition: 'approved' }]);
  await page.locator('#reject-filtered').click();
  await expect(page.locator('#target-summary')).toContainText(
    'All currently filtered findings: 2 finding(s)',
  );
  await confirmBulk();
  assert.deepEqual(await exported(), [
    { findingId: 'a2', disposition: 'approved' },
    { findingId: 'h4', disposition: 'rejected' },
    { findingId: 'm3', disposition: 'rejected' },
  ]);
});

test('imports exclude stale IDs and atomically reject malformed or legacy decisions without requiring reasons', async () => {
  await load();
  const valid = { findingId: 'z1', disposition: 'approved' };
  await upload('#decisions-file', [valid, { ...valid, findingId: 'old-id' }]);
  await expect(page.locator('#status')).toContainText('1 stale ID(s) excluded');
  await expect(page.locator('#stale-summary')).toContainText('1 stale disposition(s)');
  assert.deepEqual(await exported(), [valid]);
  for (const invalid of [
    [valid, valid],
    [{ ...valid, disposition: 'unreviewed' }],
    ...['normalize', 'retain intentionally', 'investigate'].map((disposition) => [
      { ...valid, disposition, reason: 'Legacy reason.' },
    ]),
    '{}',
    '{broken',
  ]) {
    await upload('#decisions-file', invalid);
    await expect(page.locator('#error')).not.toBeEmpty();
    assert.deepEqual(await exported(), [valid]);
  }
  page.once('dialog', (dialog) => dialog.dismiss());
  await upload('#decisions-file', []);
  assert.deepEqual(await exported(), [valid]);
  page.once('dialog', (dialog) => dialog.accept());
  await upload('#decisions-file', []);
  assert.deepEqual(await exported(), []);
});

test('invalid/replacement inventory never silently destroys current decisions', async () => {
  await load();
  await upload('#decisions-file', [{ findingId: 'a2', disposition: 'rejected' }]);
  for (const invalid of [
    { ...inventory, schemaVersion: 2 },
    { ...inventory, findings: [inventory.findings[0], inventory.findings[0]] },
    { ...inventory, findings: [{ ...inventory.findings[0], line: -1 }] },
  ]) {
    await upload('#inventory-file', invalid);
    await expect(page.locator('#error')).not.toBeEmpty();
    await expect(page.locator('#counts')).toContainText('1 reviewed');
  }
  page.once('dialog', (dialog) => dialog.dismiss());
  await upload('#inventory-file', { ...inventory, findings: [] });
  await expect(page.locator('#counts')).toContainText('4 findings');
  page.once('dialog', (dialog) => dialog.accept());
  await upload('#inventory-file', { ...inventory, findings: [] });
  await expect(page.locator('#counts')).toContainText('0 findings');
  await expect(page.locator('#approve-filtered')).toBeDisabled();
  await expect(page.locator('#reject-filtered')).toBeDisabled();
  assert.deepEqual(await exported(), []);
});

test('current and suggested evidence renders as text, with no HTML execution or retained reasons', async () => {
  const attack = '<img src="https://example.invalid/leak" onerror="window.injected=true">';
  await upload('#inventory-file', {
    ...inventory,
    findings: [
      {
        ...inventory.findings[0],
        evidence: attack,
        context: attack,
        suggestion: attack,
        caution: attack,
      },
    ],
  });
  await upload('#decisions-file', [{ findingId: 'z1', disposition: 'approved', reason: attack }]);
  const group = await openGroup();
  await expect(group.locator('.current pre')).toHaveText(attack);
  await expect(group.locator('.current .muted')).toHaveText(attack);
  await expect(group.locator('.suggested p')).toHaveText(attack);
  await expect(group.locator('.current pre')).toBeVisible();
  assert.equal(await page.locator('img').count(), 0);
  assert.equal(await page.evaluate(() => window.injected), undefined);
  assert.deepEqual(await exported(), [{ findingId: 'z1', disposition: 'approved' }]);
});

test('rule-group bulk actions span files and can replace prior approvals with rejections', async () => {
  await load();
  await upload('#decisions-file', [{ findingId: 'z1', disposition: 'approved' }]);
  await page.locator('#group-by').selectOption('rule');
  await page.locator('#search').fill('B.vue');
  const group = await openGroup('template.native-control');
  await group.getByRole('button', { name: 'Reject entire group (2)', exact: true }).click();
  await expect(page.locator('#target-summary')).toContainText(
    'including hidden findings: 2 finding(s)',
  );
  await expect(page.locator('#overwrite-summary')).toContainText(
    '1 existing decision(s) will be replaced',
  );
  await confirmBulk();
  assert.deepEqual(await exported(), [
    { findingId: 'm3', disposition: 'rejected' },
    { findingId: 'z1', disposition: 'rejected' },
  ]);
});

test('decision filters update immediately and move focus to counts when a changed finding disappears', async () => {
  await load();
  await upload('#decisions-file', [{ findingId: 'z1', disposition: 'approved' }]);
  await page.locator('#disposition-filter').selectOption('approved');
  await openGroup();
  await page.locator('#finding-z1').getByRole('button', { name: 'Reject', exact: true }).click();
  await expect(page.locator('#counts')).toContainText('0 visible');
  await expect(page.locator('#counts')).toBeFocused();
  await page.locator('#disposition-filter').selectOption('rejected');
  await openGroup();
  await expect(page.locator('#finding-z1 .status-badge')).toHaveText('rejected');
});

test('suggested-equivalent groups span files and preserve visible versus whole-group targets', async () => {
  await load();
  await page.locator('#group-by').selectOption('suggestion');
  await expect(page.locator('.group')).toHaveCount(1);
  await page.locator('#confidence').selectOption('high');
  await page.locator('#search').fill('A.vue');
  const group = await openGroup('QBtn');
  await expect(group.locator(':scope > summary')).toHaveText('QBtn — 1 visible / 4 total');
  await group.getByRole('button', { name: 'Approve visible in group (1)', exact: true }).click();
  await expect(page.locator('#targets li')).toHaveCount(1);
  await page.locator('#cancel').click();
  await group.getByRole('button', { name: 'Approve entire group (4)', exact: true }).click();
  await expect(page.locator('#targets li')).toHaveCount(4);
  await confirmBulk();
  assert.deepEqual(
    (await exported()).map((d) => d.findingId),
    ['a2', 'h4', 'm3', 'z1'],
  );
});

test('unexported direct decisions warn before reload and can be kept by cancelling navigation', async () => {
  await load();
  await openGroup();
  await page.locator('#finding-z1').getByRole('button', { name: 'Approve', exact: true }).click();
  const warning = page.waitForEvent('dialog');
  const navigation = page.evaluate(() => window.location.reload());
  const dialog = await warning;
  assert.equal(dialog.type(), 'beforeunload');
  await dialog.dismiss();
  await navigation;
  await expect(page.locator('#counts')).toContainText('1 reviewed');
  assert.equal((await exported()).length, 1);
});

test('keyboard can approve then reject at tablet width, with visible comparisons and no overflow', async () => {
  await page.setViewportSize({ width: 768, height: 1024 });
  await load();
  const summary = page.locator('.group > summary').first();
  await expect(summary).toBeVisible();
  await summary.focus();
  await expect(summary).toBeFocused();
  await page.keyboard.press('Enter');
  const card = page.locator('#finding-z1');
  await expect(card).toBeVisible();
  const approve = card.getByRole('button', { name: 'Approve', exact: true });
  const reject = card.getByRole('button', { name: 'Reject', exact: true });
  await approve.focus();
  await expect(approve).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(card.locator('.status-badge')).toHaveText('approved');
  await expect(approve).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(reject).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(card.locator('.status-badge')).toHaveText('rejected');
  await expect(reject).toBeFocused();
  await expect(page.locator('#review-dialog')).not.toBeVisible();
  await expect(card.locator('.current pre')).toBeVisible();
  await expect(card.locator('.suggested p')).toBeVisible();
  await expect(page.locator('#status')).toContainText('Not saved');
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  assert.deepEqual(await exported(), [{ findingId: 'z1', disposition: 'rejected' }]);
});

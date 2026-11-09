import assert from 'node:assert/strict';
import { once } from 'node:events';
import { request } from 'node:http';
import { mkdir, mkdtemp, readFile, writeFile, readdir, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { before, after, test } from 'node:test';
import { chromium, expect } from '@playwright/test';
import { createReviewServer } from './quasar-review-server.mjs';

const sample = {
  schemaVersion: 1,
  scope: 'test',
  limitations: ['Candidates only.'],
  findings: ['b', 'a'].map((id) => ({
    id,
    file: 'A.vue',
    line: 1,
    column: 1,
    rule: 'template.native-control',
    confidence: 'high',
    context: 'template',
    evidence: '<button>Go</button>',
    suggestion: 'QBtn',
    caution: 'Preserve semantics.',
  })),
};
let browser;
before(async () => {
  browser = await chromium.launch();
});
after(async () => {
  await browser?.close();
});
async function fixture(check, initial = []) {
  const directory = await mkdtemp(path.join(tmpdir(), 'quasar-review-server-'));
  const file = (name) => path.join(directory, name);
  const server = createReviewServer(directory, directory);
  let context;
  try {
    await writeFile(file('inventory.json'), JSON.stringify(sample));
    await writeFile(file('dispositions.json'), JSON.stringify(initial) + '\n');
    await writeFile(
      file('review.html'),
      await readFile(new URL('../../docs/quasar-audit/review.html', import.meta.url), 'utf8'),
    );
    server.listen(0, '127.0.0.1');
    await once(server, 'listening');
    const origin = `http://127.0.0.1:${server.address().port}`;
    assert.equal(server.address().address, '127.0.0.1');
    const inventory = await fetch(origin + '/inventory.json');
    const decisions = await fetch(origin + '/dispositions.json');
    const headers = {
      Origin: origin,
      'Content-Type': 'application/json',
      'If-Match': decisions.headers.get('etag'),
      'X-Inventory-Version': inventory.headers.get('etag'),
    };
    context = await browser.newContext({ acceptDownloads: true });
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await check({ directory, file, origin, headers, page, server });
    assert.deepEqual(errors, []);
  } finally {
    await context?.close();
    server.closeAllConnections();
    await new Promise((resolve) => server.close(resolve));
    await rm(directory, { recursive: true, force: true });
  }
}
const put = (origin, headers, body) =>
  fetch(origin + '/dispositions.json', {
    method: 'PUT',
    headers,
    body: typeof body === 'string' ? body : JSON.stringify(body),
  });

test('helper exposes only fixed read routes and guards host, origin, method, versions and body size', async () => {
  await fixture(async ({ origin, headers, file }) => {
    assert.equal((await fetch(origin + '/')).status, 200);
    assert.equal((await fetch(origin + '/README.md')).status, 404);
    const wrongHost = await new Promise((resolve, reject) => {
      const outgoing = request(
        origin + '/inventory.json',
        { headers: { Host: 'evil.test' } },
        (response) => {
          response.resume();
          resolve(response.statusCode);
        },
      );
      outgoing.on('error', reject);
      outgoing.end();
    });
    assert.equal(wrongHost, 403);
    assert.equal(
      (await fetch(origin + '/inventory.json', { headers: { Origin: 'https://evil.test' } }))
        .status,
      403,
    );
    assert.equal((await put(origin, { ...headers, Origin: 'https://evil.test' }, [])).status, 403);
    const { Origin, ...noOrigin } = headers;
    assert.equal((await put(origin, noOrigin, [])).status, 403);
    assert.equal(
      (await put(origin, { Origin, 'Content-Type': 'application/json' }, [])).status,
      428,
    );
    assert.equal((await fetch(origin + '/dispositions.json', { method: 'POST' })).status, 405);
    assert.equal((await put(origin, headers, 'x'.repeat(1024 * 1024 + 1))).status, 413);
    const chunkedStatus = await new Promise((resolve, reject) => {
      const outgoing = request(
        origin + '/dispositions.json',
        { method: 'PUT', headers },
        (response) => {
          response.resume();
          resolve(response.statusCode);
        },
      );
      outgoing.on('error', reject);
      outgoing.write('x'.repeat(1024 * 1024 + 1));
      outgoing.end();
    });
    assert.equal(chunkedStatus, 413);
    assert.equal(await readFile(file('dispositions.json'), 'utf8'), '[]\n');
  });
});

test('helper validates writes, saves canonical sorted decisions atomically, and leaves inventory alone', async () => {
  await fixture(async ({ origin, headers, file, directory }) => {
    const original = await readFile(file('inventory.json'), 'utf8');
    for (const body of [
      '{broken',
      [{ findingId: 'missing', disposition: 'approved' }],
      [{ findingId: 'a', disposition: 'normalize', reason: 'old' }],
      [
        { findingId: 'a', disposition: 'approved' },
        { findingId: 'a', disposition: 'rejected' },
      ],
    ]) {
      assert.ok([400, 422].includes((await put(origin, headers, body)).status));
      assert.equal(await readFile(file('dispositions.json'), 'utf8'), '[]\n');
    }
    const response = await put(origin, headers, [
      { findingId: 'b', disposition: 'rejected' },
      { findingId: 'a', disposition: 'approved' },
    ]);
    assert.equal(response.status, 200);
    const values = await response.json();
    assert.deepEqual(
      values.map((d) => d.findingId),
      ['a', 'b'],
    );
    assert.equal(
      await readFile(file('dispositions.json'), 'utf8'),
      JSON.stringify(values, null, 2) + '\n',
    );
    assert.equal(await readFile(file('inventory.json'), 'utf8'), original);
    assert.deepEqual((await readdir(directory)).sort(), [
      'dispositions.json',
      'inventory.json',
      'review.html',
    ]);
  });
});

test('competing saves and external inventory/decision edits are detected, not blindly overwritten', async () => {
  await fixture(async ({ origin, headers, file }) => {
    const results = await Promise.all([
      put(origin, headers, [{ findingId: 'a', disposition: 'approved' }]),
      put(origin, headers, [{ findingId: 'a', disposition: 'rejected' }]),
    ]);
    assert.deepEqual(results.map((r) => r.status).sort(), [200, 409]);
    const current = await fetch(origin + '/dispositions.json');
    const nextHeaders = { ...headers, 'If-Match': current.headers.get('etag') };
    await writeFile(file('inventory.json'), JSON.stringify({ ...sample, scope: 'changed' }));
    assert.equal((await put(origin, nextHeaders, [])).status, 409);
    await writeFile(file('inventory.json'), JSON.stringify(sample));
    await writeFile(file('dispositions.json'), '[]');
    assert.equal((await put(origin, nextHeaders, [])).status, 409);
    assert.equal(await readFile(file('dispositions.json'), 'utf8'), '[]');
  });
});

test('rerun button refreshes source inventory without changing saved decisions and guards its endpoint', async () => {
  await fixture(async ({ page, origin, file, headers }) => {
    await mkdir(file('frontend/src'), { recursive: true });
    await writeFile(file('frontend/src/New.vue'), '<template><button>New audit finding</button></template>');
    const previous = await readFile(file('dispositions.json'), 'utf8');
    assert.equal((await fetch(origin + '/rerun-audit')).status, 405);
    assert.equal((await fetch(origin + '/rerun-audit', { method: 'POST' })).status, 403);
    await page.goto(origin);
    await expect(page.locator('#counts')).toContainText('2 findings');
    await page.locator('#rerun-audit').click();
    await expect(page.locator('#status')).toContainText('Auto-save ready.');
    await expect(page.locator('#groups')).toContainText('New.vue');
    assert.equal(await readFile(file('dispositions.json'), 'utf8'), previous);
    const report = JSON.parse(await readFile(file('inventory.json'), 'utf8'));
    assert.ok(report.findings.some((f) => f.file.endsWith('New.vue')));
    assert.ok((await readFile(file('inventory.md'), 'utf8')).includes('New.vue'));
    assert.equal((await put(origin, headers, [])).status, 409);
  }, [{ findingId: 'a', disposition: 'approved' }]);
});

test('page automatically loads saved decisions, auto-saves reversals, and restores them on reload', async () => {
  await fixture(
    async ({ origin, page, file }) => {
      await page.goto(origin);
      await expect(page.locator('#status')).toContainText('Auto-save ready');
      await expect(page.locator('#counts')).toContainText('2 findings');
      await expect(page.locator('#inventory-file')).not.toBeVisible();
      await page.locator('.group > summary').click();
      await expect(page.locator('#finding-a .status-badge')).toHaveText('approved');
      await page.locator('#finding-a').getByRole('button', { name: 'Reject', exact: true }).click();
      await expect(page.locator('#status')).toContainText('Saved to dispositions.json');
      assert.deepEqual(JSON.parse(await readFile(file('dispositions.json'), 'utf8')), [
        { findingId: 'a', disposition: 'rejected' },
      ]);
      await page.reload();
      await expect(page.locator('#status')).toContainText('Auto-save ready');
      await page.locator('.group > summary').click();
      await expect(page.locator('#finding-a .status-badge')).toHaveText('rejected');
    },
    [{ findingId: 'a', disposition: 'approved' }],
  );
});

test('rapid edits during an in-flight save persist the newest state, not the older snapshot', async () => {
  await fixture(async ({ origin, page, file }) => {
    await page.goto(origin);
    await expect(page.locator('#status')).toContainText('Auto-save ready');
    await page.locator('.group > summary').click();
    let release;
    const gate = new Promise((resolve) => {
      release = resolve;
    });
    let entered;
    const intercepted = new Promise((resolve) => {
      entered = resolve;
    });
    let held = false;
    await page.route('**/dispositions.json', async (route) => {
      if (route.request().method() === 'PUT' && !held) {
        held = true;
        entered();
        await gate;
      }
      await route.continue();
    });
    await page.locator('#finding-a').getByRole('button', { name: 'Approve', exact: true }).click();
    await intercepted;
    await page.locator('#finding-a').getByRole('button', { name: 'Reject', exact: true }).click();
    await expect(page.locator('#finding-a .status-badge')).toHaveText('rejected');
    release();
    await expect(page.locator('#status')).toContainText('Saved to dispositions.json');
    assert.deepEqual(JSON.parse(await readFile(file('dispositions.json'), 'utf8')), [
      { findingId: 'a', disposition: 'rejected' },
    ]);
  });
});

test('failed auto-save retains pending decisions, supports backup export, warns on leave and can retry', async () => {
  await fixture(async ({ origin, page, file }) => {
    await page.goto(origin);
    await expect(page.locator('#status')).toContainText('Auto-save ready');
    await page.locator('.group > summary').click();
    const external = [{ findingId: 'b', disposition: 'rejected' }];
    await writeFile(file('dispositions.json'), JSON.stringify(external));
    await page.locator('#finding-a').getByRole('button', { name: 'Approve', exact: true }).click();
    await expect(page.locator('#error')).toContainText('Not saved');
    await expect(page.locator('#retry-save')).toBeVisible();
    assert.deepEqual(JSON.parse(await readFile(file('dispositions.json'), 'utf8')), external);
    const download = page.waitForEvent('download');
    await page.locator('#export').click();
    assert.deepEqual(JSON.parse(await readFile(await (await download).path(), 'utf8')), [
      { findingId: 'a', disposition: 'approved' },
    ]);
    await expect(page.locator('#error')).toContainText('Not saved');
    const warning = page.waitForEvent('dialog');
    const navigation = page.evaluate(() => window.location.reload());
    const dialog = await warning;
    assert.equal(dialog.type(), 'beforeunload');
    await dialog.dismiss();
    await navigation;
    await writeFile(file('dispositions.json'), '[]\n');
    await page.locator('#retry-save').click();
    await expect(page.locator('#status')).toContainText('Saved to dispositions.json');
    assert.deepEqual(JSON.parse(await readFile(file('dispositions.json'), 'utf8')), [
      { findingId: 'a', disposition: 'approved' },
    ]);
  });
});

test('legacy decisions fail auto-load visibly without enabling accidental overwrite', async () => {
  await fixture(
    async ({ origin, page, file }) => {
      const previous = await readFile(file('dispositions.json'), 'utf8');
      await page.goto(origin);
      await expect(page.locator('#error')).toContainText('Could not auto-load');
      await expect(page.locator('#workspace')).not.toBeVisible();
      await expect(page.locator('#export')).toBeDisabled();
      assert.equal(await readFile(file('dispositions.json'), 'utf8'), previous);
    },
    [{ findingId: 'a', disposition: 'normalize', reason: 'Old manual decision.' }],
  );
});

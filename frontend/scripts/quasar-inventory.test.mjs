import assert from 'node:assert/strict';
import { execFileSync, spawnSync } from 'node:child_process';
import { mkdtemp, mkdir, readFile, rm, symlink, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import { formatReport, scan } from './quasar-inventory.mjs';

const script = fileURLToPath(new URL('./quasar-inventory.mjs', import.meta.url));

async function fixture(t) {
  const root = await mkdtemp(path.join(os.tmpdir(), 'quasar-inventory-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  return root;
}

test('reports categories, relative files and exact CRLF line numbers without modifying input', async (t) => {
  const root = await fixture(t);
  const source =
    '<q-btn v-close-popup />\r\nconst q = useQuasar(); $q.notify({});\r\n<div class="q-pa-md row col-md-6 text-caption lt-md" />\r\nimport "@quasar/extras/material-icons";\r\nimport config from "#q-app";\r\n';
  await writeFile(path.join(root, 'view.vue'), source);
  const findings = await scan(root);
  for (const [category, line] of [
    ['Components and directives', 1],
    ['Imports and runtime APIs', 2],
    ['Styles and layout utilities', 3],
    ['Icons and fonts', 4],
    ['Build and generated dependencies', 5],
  ])
    assert.ok(
      findings.some(
        (finding) =>
          finding.category === category && finding.file === 'view.vue' && finding.line === line,
      ),
    );
  assert.equal(await readFile(path.join(root, 'view.vue'), 'utf8'), source);
  assert.match(formatReport(root, findings), /view\.vue:3:/);
  assert.deepEqual(await scan(root), findings);
});

test('skips generated/vendor files, lockfiles, scanner fixtures and symlinks; includes tests and docs', async (t) => {
  const root = await fixture(t);
  for (const name of ['node_modules', '.quasar', 'dist', 'test-results']) {
    await mkdir(path.join(root, name));
    await writeFile(path.join(root, name, 'hidden.vue'), '<q-btn />');
  }
  for (const name of ['package-lock.json', 'quasar-inventory.mjs', 'quasar-inventory.test.mjs'])
    await writeFile(path.join(root, name), 'quasar');
  await writeFile(path.join(root, 'notes.md'), 'quasar');
  await writeFile(path.join(root, 'view.spec.ts'), 'const component = QBtn;');
  await symlink(root, path.join(root, 'loop'));
  assert.deepEqual(
    [...new Set((await scan(root)).map((finding) => finding.file))],
    ['notes.md', 'view.spec.ts'],
  );
});

test('CLI succeeds for findings and empty scans, supports help, and fails on unreadable roots/invalid arguments', async (t) => {
  const root = await fixture(t);
  assert.match(execFileSync(process.execPath, [script, root], { encoding: 'utf8' }), /Total: 0/);
  await writeFile(path.join(root, 'app.vue'), '<q-btn />');
  assert.match(execFileSync(process.execPath, [script, root], { encoding: 'utf8' }), /app\.vue:1:/);
  assert.match(execFileSync(process.execPath, [script, '--help'], { encoding: 'utf8' }), /Usage:/);
  for (const args of [[path.join(root, 'missing')], ['--unknown'], [root, root]]) {
    const result = spawnSync(process.execPath, [script, ...args], { encoding: 'utf8' });
    assert.equal(result.status, 1);
    assert.ok(result.stderr.length);
  }
});

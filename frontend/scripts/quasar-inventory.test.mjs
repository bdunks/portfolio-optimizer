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

test('detects real mixed Quasar usage with exact CRLF locations and no source changes', async (t) => {
  const root = await fixture(t);
  const source = [
    '<script setup lang="ts">',
    'import { QBtn as LegacyButton, useQuasar as getQuasar } from',
    '  "quasar";',
    'const q = getQuasar();',
    'import("@quasar/extras/material-icons");',
    '</script>',
    '<template>',
    '  <LegacyButton v-close-popup class="q-pa-md tw:flex" />',
    '  <q-card :class="[\'q-mt-sm\', {\'q-gutter-md\': true}]" />',
    '  <div class="row" />',
    '</template>',
    '<style lang="scss">',
    '@use "quasar/src/css/variables";',
    '.q-pa-md { color: $primary; }',
    '</style>',
  ].join('\r\n');
  await writeFile(path.join(root, 'view.vue'), source);
  const findings = await scan(root);
  for (const [category, line] of [
    ['Direct Quasar dependencies', 2],
    ['Direct Quasar dependencies', 5],
    ['Direct Quasar dependencies', 8],
    ['Quasar-specific styling', 8],
    ['Quasar-specific styling', 9],
    ['Ambiguous legacy styling', 10],
    ['Quasar-specific styling', 13],
  ]) assert.ok(findings.some((f) => f.category === category && f.line === line), `${category}:${line}`);
  assert.ok(!findings.some((f) => f.category === 'Analysis limitations'));
  assert.match(formatReport(root, findings), /view\.vue:8:/);
  assert.equal(await readFile(path.join(root, 'view.vue'), 'utf8'), source);
  assert.deepEqual(await scan(root), findings);
});

test('ignores TanStack variables, accessibility, prefixed Tailwind, Lucide and ordinary CSS', async (t) => {
  const root = await fixture(t);
  await writeFile(path.join(root, 'migrated.vue'), `<script setup lang="ts">
import { ArrowDown } from '@lucide/vue';
const cell = ({ row }) => formatPercent(row.original.current);
const classes = cn('tw:flex tw:md:hidden tw:text-primary', 'tw:items-center');
</script>
<template><Button class="tw:flex tw:items-center" :class="['tw:hidden', { 'tw:row': true }]">
<ArrowDown aria-hidden="true" /></Button></template>
<style>.panel { display: flex; flex-direction: column; visibility: hidden; }</style>`);
  assert.deepEqual(await scan(root), []);
});

test('exempts primitives/vendor/lockfiles/symlinks and separates historical references', async (t) => {
  const root = await fixture(t);
  for (const name of ['node_modules', '.quasar', 'dist', 'test-results', 'src/components/ui/button', 'scripts/nested']) {
    await mkdir(path.join(root, name), { recursive: true });
    await writeFile(path.join(root, name, 'hidden.vue'), '<template><q-btn /></template>');
  }
  for (const name of ['package-lock.json', 'quasar-inventory.mjs', 'quasar-inventory.test.mjs']) await writeFile(path.join(root, name), 'quasar');
  await writeFile(path.join(root, 'notes.md'), 'quasar');
  await writeFile(path.join(root, 'view.spec.ts'), 'const component = QBtn;');
  await symlink(root, path.join(root, 'loop'));
  const findings = await scan(root);
  assert.deepEqual(findings.map((f) => f.file), ['notes.md', 'view.spec.ts']);
  assert.ok(findings.every((f) => f.category === 'References and tooling'));
});

test('distinguishes manifest dependencies, metadata, comments, runtime calls and parse errors', async (t) => {
  const root = await fixture(t);
  await writeFile(path.join(root, 'package.json'), JSON.stringify({ description: 'Quasar project', dependencies: { quasar: '2', 'quasar-like': '1' }, scripts: { build: 'quasar build' } }, null, 2));
  await writeFile(path.join(root, 'runtime.ts'), '// useQuasar() quasar\n$q.notify({});\nconst x = ;');
  const findings = await scan(root);
  assert.equal(findings.filter((f) => f.file === 'package.json' && f.category === 'Direct Quasar dependencies').length, 2);
  assert.ok(findings.some((f) => f.file === 'runtime.ts' && f.line === 1 && f.category === 'References and tooling'));
  assert.ok(findings.some((f) => f.file === 'runtime.ts' && f.line === 2 && f.category === 'Direct Quasar dependencies'));
  assert.ok(findings.some((f) => f.category === 'Analysis limitations'));
});

test('CLI preserves success/help/error behavior', async (t) => {
  const root = await fixture(t);
  assert.match(execFileSync(process.execPath, [script, root], { encoding: 'utf8' }), /Total: 0/);
  await writeFile(path.join(root, 'app.vue'), '<template><q-btn /></template>');
  assert.match(execFileSync(process.execPath, [script, root], { encoding: 'utf8' }), /app\.vue:1:/);
  assert.match(execFileSync(process.execPath, [script, '--help'], { encoding: 'utf8' }), /Usage:/);
  for (const args of [[path.join(root, 'missing')], ['--unknown'], [root, root]]) {
    const result = spawnSync(process.execPath, [script, ...args], { encoding: 'utf8' });
    assert.equal(result.status, 1);
    assert.ok(result.stderr.length);
  }
});


test('Markdown report groups context once and deduplicates source lines without hiding errors', () => {
  const reference = { category: 'References and tooling', file: 'notes.md', line: 3, source: 'quasar', reason: 'Quasar reference; not proven executable' };
  const report = formatReport('/fixture', [reference, { ...reference, reason: 'another reason' }, {
    category: 'Analysis limitations', file: 'bad.vue', line: 2, source: '<div>', reason: 'Missing end tag',
  }]);
  assert.match(report, /^# Quasar inventory:/);
  assert.match(report, /## References and tooling \(1 lines, 1 files\)/);
  assert.match(report, /### notes\.md\n- notes\.md:3: quasar/);
  assert.equal(report.split('- notes.md:3:').length - 1, 1);
  assert.doesNotMatch(report, /Quasar reference; not proven executable|another reason/);
  assert.match(report, /  - Missing end tag/);
  assert.match(report, /## Total: 2 category\/line findings/);
});

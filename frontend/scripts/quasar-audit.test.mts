import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, readFile, rm, symlink } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { test } from 'node:test';
// Native Node loads .mts; the app typechecker resolves .mjs to .mts for types.
const { audit, markdown, validateDispositions } = (await import(
  new URL('./quasar-audit.mts', import.meta.url).href
)) as typeof import('./quasar-audit.mjs');

async function fixture(files: Record<string, string>, check: (root: string) => Promise<void>) {
  const root = await mkdtemp(path.join(tmpdir(), 'quasar-audit-'));
  try {
    await mkdir(path.join(root, 'frontend/src'), { recursive: true });
    for (const [file, code] of Object.entries(files)) {
      const target = path.join(root, file);
      await mkdir(path.dirname(target), { recursive: true });
      await writeFile(target, code);
    }
    await check(root);
    for (const [file, code] of Object.entries(files))
      assert.equal(
        await readFile(path.join(root, file), 'utf8'),
        code,
        'audit must not modify input',
      );
  } finally {
    await rm(root, { recursive: true, force: true });
  }
}
const sfc = 'frontend/src/A.vue';

test('both Vue tag spellings are detected and reported as kebab-case Quasar components', async () => {
  await fixture(
    {
      [sfc]:
        '<template><q-btn/><QBtn/><q-card/><QCard/><q-markup-table/><QMarkupTable/><button/><div class="notice"/></template>',
    },
    async (root) => {
      const result = await audit(root);
      assert.deepEqual(
        result.quasarUsage.map((usage) => usage.component),
        ['q-btn', 'q-btn', 'q-card', 'q-card', 'q-markup-table', 'q-markup-table'],
      );
      assert.equal(result.findings.filter((f) => f.rule === 'template.custom-surface').length, 1);
      assert.ok(result.findings.every((f) => !/\bQ[A-Z]/.test(f.suggestion + f.caution)));
      const output = markdown(result);
      assert.match(output, /q-btn/);
      assert.match(output, /q-markup-table/);
      assert.doesNotMatch(output, /QBtn|QCard|QMarkupTable/);
    },
  );
});

test('native controls have exact locations; existing Quasar and semantic sections are not defects', async () => {
  await fixture(
    {
      [sfc]: `<template>\n  <button type="submit" :disabled="busy">Save</button>\n  <input v-model="money" inputmode="decimal" />\n  <input type="checkbox" />\n  <select/><textarea/><table/><section/><q-card/><QBtn/>\n</template>\n<script setup lang="ts">const busy: boolean = false; const money = '0.10';</script>`,
    },
    async (root) => {
      const result = await audit(root);
      const controls = result.findings.filter((f) => f.rule === 'template.native-control');
      assert.equal(controls.length, 6);
      assert.equal(controls[0]!.line, 2);
      assert.equal(controls[0]!.column, 3);
      assert.match(controls[0]!.evidence, /type="submit"/);
      assert.match(controls[1]!.caution, /decimal-string/);
      assert.equal(controls[1]!.suggestion, 'q-input type=text inputmode=decimal');
      assert.equal(controls[2]!.suggestion, 'q-checkbox');
      assert.equal(result.quasarUsage.length, 2);
      assert.deepEqual(
        result.quasarUsage.map((usage) => usage.component),
        ['q-btn', 'q-card'],
      );
      assert.equal(
        result.findings.some((f) => f.rule === 'coverage.unresolved'),
        false,
        JSON.stringify(result.findings.filter((f) => f.rule === 'coverage.unresolved')),
      );
    },
  );
});

test('input suggestions name one component and preserve each field type and keyboard hint', async () => {
  await fixture(
    {
      [sfc]: `<template>
        <input/><input type="text"/><input type="search"/><input type="number"/>
        <input type="date"/><input type="datetime-local"/>
        <input inputmode="decimal"/><input inputmode="numeric"/>
        <input type="checkbox"/><input type="radio"/><input type="file"/>
      </template>`,
    },
    async (root) => {
      const result = await audit(root);
      const controls = result.findings.filter((f) => f.rule === 'template.native-control');
      assert.deepEqual(
        controls.map((f) => f.suggestion),
        [
          'q-input type=text',
          'q-input type=text',
          'q-input type=search',
          'q-input type=number',
          'q-input type=date',
          'q-input type=datetime-local',
          'q-input type=text inputmode=decimal',
          'q-input type=text inputmode=numeric',
          'q-checkbox',
          'q-radio',
          'q-file',
        ],
      );
      assert.ok(controls.every((f) => !f.suggestion.includes('according to type')));
    },
  );
});

test('notices suggest q-banner, badges q-badge, tables q-markup-table; bound literal classes count', async () => {
  await fixture(
    {
      [sfc]: `<template><div class="notice-card" role="status"/><span :class="['status-badge', ready ? 'ok' : 'bad']"/><article class="security-card"/><table/></template>`,
    },
    async (root) => {
      const result = await audit(root);
      const surfaces = result.findings.filter((f) => f.rule === 'template.custom-surface');
      assert.equal(surfaces.length, 3);
      assert.match(surfaces[0]!.suggestion, /q-banner/);
      assert.match(surfaces[1]!.suggestion, /q-badge/);
      assert.match(surfaces[2]!.suggestion, /q-card/);
      assert.match(
        result.findings.find((f) => f.rule === 'template.native-control')!.suggestion,
        /q-markup-table/,
      );
    },
  );
});

test('inline, bound, scoped, global, media and Quasar override evidence is retained', async () => {
  await fixture(
    {
      [sfc]: `<template><div style="padding: 7px" :style="{ gap: size }"/></template>\n<style scoped>\n@media (max-width: 700px) {\n  .panel :deep(.q-btn) { display: flex; padding: 7px; color: red; }\n}\n</style>\n<style>\n.notice { background: white; }\n</style>`,
    },
    async (root) => {
      const result = await audit(root);
      assert.ok(result.findings.some((f) => f.rule === 'template.inline-style'));
      assert.ok(
        result.findings.some(
          (f) => f.rule === 'coverage.unresolved' && /bound inline/.test(f.context),
        ),
      );
      const override = result.findings.find((f) => f.rule === 'css.quasar-override')!;
      assert.equal(override.line, 4);
      assert.equal(override.column, 3);
      assert.match(override.context, /scoped.*@media/);
      assert.equal(result.styles.length, 2);
      assert.match(result.styles[1]!.context, /global/);
      assert.match(
        result.findings.find((f) => f.rule === 'css.layout-spacing')!.caution,
        /do not assume token equivalence/,
      );
    },
  );
});

test('shared external styles parsed once, every scoped owner recorded, cyclic imports terminate', async () => {
  await fixture(
    {
      [sfc]: '<template><div/></template>\n<style scoped src="./shared.css"></style>',
      'frontend/src/B.vue':
        '<template><div/></template>\n<style scoped src="./shared.css"></style>',
      'frontend/src/shared.css':
        '@import "./other.css";\n.primary-button { padding: 1rem; color: red; border: 0; }',
      'frontend/src/other.css':
        '@import "./shared.css";\n.other { padding: 1rem; color: red; border: 0; }',
    },
    async (root) => {
      const result = await audit(root);
      assert.equal(result.styles.filter((s) => s.context.includes('src=')).length, 2);
      assert.equal(
        result.findings.filter((f) => f.file.endsWith('shared.css') && f.rule === 'css.control')
          .length,
        1,
      );
      assert.equal(result.findings.filter((f) => f.rule === 'css.duplicate-block').length, 2);
      assert.equal(result.files.length, 4);
    },
  );
});

test('duplication excludes shorter, reordered and important-different declaration blocks', async () => {
  await fixture(
    {
      'frontend/src/a.css':
        '.a {color:red;padding:0;border:0}.b {color:red;padding:0;border:0}.c {color:red!important;padding:0;border:0}.d {padding:0;color:red;border:0}.e {color:red;padding:0}.f {color:red;padding:0}',
    },
    async (root) => {
      const result = await audit(root);
      assert.equal(result.findings.filter((f) => f.rule === 'css.duplicate-block').length, 2);
    },
  );
});

test('CSS-compatible SCSS global styles keep coordinates; real preprocessors disclose gaps', async () => {
  await fixture(
    {
      'frontend/src/app.scss': '// comment\n.page { display: grid; gap: 0.55rem; }',
      'frontend/src/variables.scss': '$primary: red;',
      'frontend/src/theme.less': '@color: red;',
      [sfc]:
        '<template><div/></template>\n<style lang="scss">\n// comment\n.panel { padding: 2rem; }\n</style>',
    },
    async (root) => {
      const result = await audit(root);
      assert.equal(
        result.findings.filter((f) => f.rule === 'coverage.unresolved').length,
        2,
        JSON.stringify(result.findings.filter((f) => f.rule === 'coverage.unresolved')),
      );
      assert.equal(result.findings.find((f) => f.file.endsWith('app.scss'))!.line, 2);
      assert.ok(
        result.findings.some(
          (f) => f.file === sfc && f.rule === 'css.layout-spacing' && f.line === 4,
        ),
      );
    },
  );
});

test('unresolved aliases, missing/remote/escaping references and dynamic bindings are disclosed', async () => {
  await fixture(
    {
      [sfc]:
        '<template><component :is="view" :style="styles" v-bind="props" :[name]="value"/></template>\n<style src="@/theme.css"></style>\n<style src="./missing.css"></style>\n<style src="../../../outside.css"></style>',
      'frontend/src/imports.css': '@import url(https://example.com/a.css);',
    },
    async (root) => {
      const result = await audit(root);
      assert.ok(result.findings.filter((f) => f.rule === 'coverage.unresolved').length >= 7);
      assert.equal(result.files.length, 2);
    },
  );
});

test('local CSS imports outside src included, symlinks not followed', async () => {
  await fixture(
    {
      [sfc]: '<template><div/></template>\n<style src="../theme.css"></style>',
      'frontend/theme.css': '.panel { padding: 1rem; }',
    },
    async (root) => {
      await symlink(
        path.join(root, 'frontend/theme.css'),
        path.join(root, 'frontend/src/link.css'),
      );
      const result = await audit(root);
      assert.ok(result.files.some((f) => f.file === 'frontend/theme.css'));
      assert.ok(!result.files.some((f) => f.file.endsWith('link.css')));
    },
  );
});

test('SCSS nesting is disclosed rather than claimed as resolved selectors', async () => {
  await fixture(
    { 'frontend/src/nested.scss': '.parent { .child { padding: 1rem; } }' },
    async (root) => {
      const result = await audit(root);
      assert.ok(
        result.findings.some(
          (f) => f.rule === 'coverage.unresolved' && /nesting not compiled/.test(f.context),
        ),
      );
    },
  );
});

test('parser errors become coverage findings instead of disappearing', async () => {
  await fixture(
    {
      [sfc]: '<template><button/></template><script>const = ;</script>',
      'frontend/src/bad.css': '.panel { color:',
    },
    async (root) => {
      const result = await audit(root);
      assert.equal(result.findings.filter((f) => f.rule === 'coverage.unresolved').length, 2);
      assert.ok(!JSON.stringify(result).includes(root));
    },
  );
});

test('JSON/Markdown independent of root and creation order; Markdown safely escapes evidence', async () => {
  const files = {
    [sfc]: '<template><button :disabled="a || b">Save</button></template>',
    'frontend/src/z.css': '.panel { padding: 7px; }',
  };
  await fixture(files, async (root) => {
    const first = await audit(root);
    assert.deepEqual(first, await audit(root));
    await fixture(Object.fromEntries(Object.entries(files).reverse()), async (other) => {
      assert.deepEqual(first, await audit(other));
      assert.equal(markdown(first), markdown(await audit(other)));
    });
    assert.match(markdown(first), /&#124;&#124;/);
    assert.match(markdown(first), /&lt;button/);
    assert.equal(new Set(first.findings.map((f) => f.id)).size, first.findings.length);
  });
});

test('manual dispositions require current unique IDs and approved/rejected, without reasons', async () => {
  await fixture({ [sfc]: '<template><button/></template>' }, async (root) => {
    const result = await audit(root);
    const item = { findingId: result.findings[0]!.id, disposition: 'approved' };
    assert.doesNotThrow(() => validateDispositions([item], result.findings));
    assert.doesNotThrow(() =>
      validateDispositions([{ ...item, disposition: 'rejected' }], result.findings),
    );
    assert.doesNotThrow(() => validateDispositions([], result.findings));
    for (const bad of [
      [{ ...item, disposition: 'unreviewed' }],
      [{ ...item, disposition: 'normalize', reason: 'Legacy choice.' }],
      [{ ...item, disposition: 'retain intentionally' }],
      [{ ...item, disposition: 'investigate' }],
      [{ ...item, findingId: 'stale' }],
      [item, item],
      {},
    ])
      assert.throws(() => validateDispositions(bad, result.findings));
  });
});

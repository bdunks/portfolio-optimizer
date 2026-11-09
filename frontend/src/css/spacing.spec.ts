import { readFileSync, readdirSync } from 'node:fs';
import { join, resolve } from 'node:path';
import postcss from 'postcss';
import { describe, expect, it } from 'vitest';

const sourceDirectory = resolve('src');
function styles(directory: string): Array<{ file: string; css: string }> {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const file = join(directory, entry.name);
    if (entry.isDirectory()) return styles(file);
    if (!/\.(vue|css|scss)$/.test(file) || file.endsWith('quasar.variables.scss')) return [];
    const source = readFileSync(file, 'utf8');
    const blocks = file.endsWith('.vue')
      ? [...source.matchAll(/<style\b[^>]*>([\s\S]*?)<\/style>/g)].map((match) => match[1]!)
      : [source.replace(/^\/\/.*$/gm, '')];
    return blocks.map((css) => ({ file, css }));
  });
}

describe('Quasar-first spacing', () => {
  it('uses utilities instead of custom margins and padding, except accessible hidden content', () => {
    for (const { file, css } of styles(sourceDirectory)) {
      postcss.parse(css).walkDecls(/^(margin|padding)(-|$)/, (declaration) => {
        const parent = declaration.parent;
        expect(parent?.type, file).toBe('rule');
        if (parent?.type !== 'rule') return;
        expect(['.sr-only', '.visually-hidden'], `${file}: ${parent.selector}`).toContain(
          parent.selector,
        );
        expect(['0', '-1px'], file).toContain(declaration.value);
      });
    }
  });

  it('keeps justified grid gaps on the unmodified Quasar spacing scale', () => {
    for (const { file, css } of styles(sourceDirectory)) {
      postcss.parse(css).walkDecls(/^(gap|row-gap|column-gap)$/, (declaration) => {
        expect(css, file).toContain('negative-margin gutters distort grid tracks');
        for (const value of declaration.value.split(/\s+/)) {
          expect(['0px', '4px', '8px', '16px', '24px', '48px'], file).toContain(value);
        }
      });
    }
    const variables = readFileSync(join(sourceDirectory, 'css/quasar.variables.scss'), 'utf8');
    expect(variables).not.toMatch(/\$(space(?:-[\w-]+)?|spaces|flex-gutter(?:-[\w-]+)?)\s*:/);
  });
});

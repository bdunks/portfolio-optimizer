import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const workspaceStyles = readFileSync(resolve(process.cwd(), 'src/css/app.scss'), 'utf8');

describe('shared workspace styles', () => {
  it('keeps page grids shrinkable and workspace titles standardized', () => {
    expect(workspaceStyles).toMatch(
      /\.workspace-page\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\);/s,
    );
    expect(workspaceStyles).toMatch(/\.workspace-page\s*\{[^}]*min-width:\s*0;/s);
    expect(workspaceStyles).toMatch(
      /\.workspace-page \.page-header h1\s*\{[^}]*font-size:\s*clamp\(1\.7rem,\s*3vw,\s*2rem\);/s,
    );
  });

  it('avoids a fixed basis that becomes excess height in column headers', () => {
    expect(workspaceStyles).toContain(
      '.workspace-page .page-header > :first-child {\n  flex: 1 1 auto;\n}',
    );
    expect(workspaceStyles).not.toContain('flex: 1 1 20rem;');
  });
});

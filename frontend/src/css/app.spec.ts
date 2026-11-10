import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const workspaceStyles = readFileSync(resolve(process.cwd(), 'src/css/app.scss'), 'utf8');

const pageHeaderStyles = readFileSync(
  resolve(process.cwd(), 'src/components/WorkspacePageHeader.vue'),
  'utf8',
);
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

  it('keeps page-heading flex sizing in its owning component', () => {
    expect(workspaceStyles).not.toContain('.workspace-page .page-header > :first-child');
    expect(pageHeaderStyles).toMatch(/\.page-heading\s*\{[^}]*flex:\s*1 1 auto;/s);
    expect(workspaceStyles).not.toContain('flex: 1 1 20rem;');
  });
});

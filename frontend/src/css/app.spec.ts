import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const workspaceStyles = readFileSync(resolve(process.cwd(), 'src/styles/globals.css'), 'utf8');

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
    expect(pageHeaderStyles).toContain('tw:text-[clamp(1.7rem,3vw,2rem)]');
  });

  it('keeps header layout in its owning component and uses semantic color tokens', () => {
    expect(workspaceStyles).not.toContain('.workspace-page .page-header > :first-child');
    expect(pageHeaderStyles).toContain('tw:gap-4');
    expect(pageHeaderStyles).toContain('tw:flex-[1_1_auto]');
    expect(pageHeaderStyles).toContain('tw:text-muted-foreground');
    expect(workspaceStyles).not.toContain('flex: 1 1 20rem;');
    expect(workspaceStyles).not.toContain('color: #637b8a;');
  });
});

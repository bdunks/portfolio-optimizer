import { describe, expect, it } from 'vitest';
import { workspaceLinks } from '@/navigation/workspace-navigation';
import routes from './routes';

describe('workspace routes and navigation', () => {
  it('provides the six intended local workspace destinations', () => {
    const root = routes.find((route) => route.path === '/');
    const children = root?.children ?? [];
    const routePaths = children.map((route) => (route.path === '' ? '/' : `/${route.path}`));

    expect(routePaths).toEqual([
      '/',
      '/recommendations',
      '/lots',
      '/policy',
      '/wash-sales',
      '/activity',
    ]);
    expect(workspaceLinks.map((link) => link.to)).toEqual(routePaths);
    expect(workspaceLinks.every((link) => !link.to.startsWith('http'))).toBe(true);
    expect(routes.at(-1)?.path).toBe('/:catchAll(.*)*');
  });

  it('loads the API-backed Recommendations, Tax Lots, Wash Sales, and Activity screens', async () => {
    const children = routes.find((route) => route.path === '/')?.children ?? [];
    const expected = [
      ['recommendations', 'RecommendationsPage'],
      ['lots', 'TaxLotsPage'],
      ['policy', 'PolicyPage'],
      ['wash-sales', 'WashSalesPage'],
      ['activity', 'ActivityPage'],
    ] as const;

    for (const [path, pageName] of expected) {
      const route = children.find((child) => child.path === path);
      expect(typeof route?.component).toBe('function');
      const loader = route?.component as () => Promise<{ default: { __name?: string } }>;
      const page = await loader();
      expect(page.default.__name).toBe(pageName);
    }
  });
});

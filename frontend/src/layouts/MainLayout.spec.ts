// @vitest-environment jsdom

import { createPinia } from 'pinia';
import { createMemoryHistory, createRouter } from 'vue-router';
import { afterEach, describe, expect, it } from 'vitest';
import { useUiStore } from '@/stores/ui-store';
import { mountWithWorkspace } from '@/test-utils/workspace-mount';
import MainLayout from './MainLayout.vue';

const workspaceRoutes = [
  '/',
  '/recommendations',
  '/review',
  '/lots',
  '/policy',
  '/wash-sales',
  '/activity',
].map((path) => ({ path, component: { template: '<div />' } }));

let mountedWrapper: ReturnType<typeof mountWithWorkspace> | undefined;

afterEach(() => {
  mountedWrapper?.unmount();
  mountedWrapper = undefined;
  document.body.innerHTML = '';
});

async function mountLayout() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: workspaceRoutes,
  });
  await router.push('/');
  await router.isReady();

  const pinia = createPinia();
  const wrapper = mountWithWorkspace(MainLayout, {
    attachTo: document.body,
    global: { plugins: [router, pinia] },
  });
  mountedWrapper = wrapper;
  return { pinia, router, wrapper };
}

describe('MainLayout', () => {
  it('uses a native themed root and main landmark', async () => {
    const { wrapper } = await mountLayout();

    expect(wrapper.element.tagName).toBe('DIV');
    expect(wrapper.classes()).toEqual(
      expect.arrayContaining(['tw:min-h-svh', 'tw:bg-background', 'tw:text-foreground']),
    );
    expect(wrapper.findAll('main')).toHaveLength(1);
    expect(wrapper.get('#main-content').element.tagName).toBe('DIV');
    expect(wrapper.get('#main-content').attributes('tabindex')).toBe('-1');
  });
  it('keeps the application-wide demo notice polite and non-actionable', async () => {
    const { wrapper } = await mountLayout();

    const notice = wrapper.get('[role="status"]');
    expect(notice.attributes('aria-label')).toBe('Demo-only application notice');
    expect(notice.text()).toContain('DEMO ONLY');
    expect(notice.text()).toContain('All analysis is non-actionable.');
    expect(notice.text()).toContain('No broker connection, OAuth, live writes, or trading.');
    expect(wrapper.find('[role="alert"]').exists()).toBe(false);
    expect(wrapper.text()).toContain('Local demo mode');
    const context = wrapper.get('[aria-label="Portfolio structure context"]');
    expect(context.text()).toContain('Active configuration unavailable.');
    expect(context.text()).toContain('Current position counts and holdings allocation unavailable');
    expect(context.text()).toContain('Account-wide tax-lot count unavailable');
    expect(context.findAll('a, button')).toHaveLength(0);
    expect(wrapper.text()).toContain('No broker connection or order submission');
  });

  it('preserves all workspace routes and exposes the active route accessibly', async () => {
    const { wrapper } = await mountLayout();

    const links = wrapper.findAll('nav[aria-label="Primary navigation"] a');
    expect(links.map((link) => link.attributes('href'))).toEqual([
      '/',
      '/recommendations',
      '/review',
      '/lots',
      '/policy',
      '/wash-sales',
      '/activity',
    ]);
    const activeLink = wrapper.get('a[aria-current="page"]');
    expect(activeLink.text()).toContain('Overview');
    expect(activeLink.text()).toContain('Account snapshot');
    expect(activeLink.attributes('data-active')).toBe('true');
    expect(
      wrapper.get('button[aria-label="Toggle workspace navigation"]').attributes('aria-expanded'),
    ).toBe('true');
  });

  it('keeps the sidebar trigger state in Pinia and the skip link focused on main content', async () => {
    const { pinia, wrapper } = await mountLayout();
    const sidebarTrigger = wrapper.get('button[aria-label="Toggle workspace navigation"]');

    expect(useUiStore(pinia).sidebarOpen).toBe(true);
    await sidebarTrigger.trigger('click');
    expect(sidebarTrigger.attributes('aria-expanded')).toBe('false');
    expect(useUiStore(pinia).sidebarOpen).toBe(false);

    await wrapper.get('.skip-link').trigger('click');
    expect(document.activeElement).toBe(wrapper.get('#main-content').element);
  });
});

// @vitest-environment jsdom

import { QBanner } from 'quasar';
import { createMemoryHistory, createRouter } from 'vue-router';
import { describe, expect, it } from 'vitest';
import { mountWithQuasar } from '@/test-utils/quasar-mount';
import MainLayout from './MainLayout.vue';

describe('MainLayout message banner', () => {
  it('keeps the application-wide demo notice polite and non-actionable', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/', component: { template: '<div />' } }],
    });
    await router.push('/');
    await router.isReady();
    const wrapper = mountWithQuasar(MainLayout, { global: { plugins: [router] } });

    const banner = wrapper.getComponent(QBanner);
    expect(banner.attributes('role')).toBe('status');
    expect(banner.attributes('aria-label')).toBe('Demo-only application notice');
    expect(banner.text()).toContain('DEMO ONLY');
    expect(banner.text()).toContain('All analysis is non-actionable.');
    expect(wrapper.find('[role="alert"]').exists()).toBe(false);

    const activeItem = wrapper.get('[aria-current="page"]');
    expect(activeItem.classes()).toEqual(
      expect.arrayContaining(['rounded-borders', 'workspace-nav-active', 'text-white']),
    );
    const activeCaption = wrapper.get('[aria-current="page"] .q-item__label--caption');
    expect(activeCaption.classes()).toContain('text-white');
    const workspaceLabel = wrapper.get('.q-item__label--header');
    expect(workspaceLabel.classes()).toEqual(
      expect.arrayContaining(['text-overline', 'text-weight-bold', 'text-blue-grey-8']),
    );
    expect(wrapper.get('.q-drawer__content').classes()).toContain('bg-white');
    const inactiveItem = wrapper.get('nav a.q-item[href="/recommendations"]');
    expect(inactiveItem.classes()).toContain('text-blue-grey-9');
    expect(inactiveItem.get('.q-item__label--caption').classes()).toContain('text-blue-grey-7');
    expect(wrapper.findAll('.brand-mark')).toHaveLength(2);
    for (const brand of wrapper.findAll('.brand-mark')) {
      expect(brand.classes()).toEqual(
        expect.arrayContaining(['row', 'inline', 'no-wrap', 'flex-center']),
      );
    }
    expect(wrapper.get('.drawer-brand > div').classes()).toEqual(
      expect.arrayContaining(['column', 'no-wrap']),
    );
  });
});

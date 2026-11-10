// @vitest-environment jsdom
import { mount } from '@vue/test-utils';
import { createPinia, setActivePinia } from 'pinia';
import { QBanner } from 'quasar';
import { beforeEach, describe, expect, it } from 'vitest';
import ResourceFreshnessNotice from './ResourceFreshnessNotice.vue';
import WorkspaceCapabilityNotice from './WorkspaceCapabilityNotice.vue';
import WorkspaceEmptyState from './WorkspaceEmptyState.vue';
import { useWorkspaceStore } from '@/stores/workspace-store';

beforeEach(() => setActivePinia(createPinia()));

describe('shared message banners', () => {
  it('keeps capability and empty-state messages polite and preserves their content', () => {
    const capability = mount(WorkspaceCapabilityNotice, {
      props: { label: 'DEMO ONLY.' },
      slots: { default: 'No broker calls or order submission are available.' },
    });
    const capabilityBanner = capability.getComponent(QBanner);
    expect(capabilityBanner.attributes('role')).toBe('status');
    expect(capabilityBanner.attributes('aria-live')).toBe('polite');
    expect(capabilityBanner.text()).toContain('DEMO ONLY.');
    expect(capabilityBanner.text()).toContain('No broker calls or order submission are available.');

    const emptyState = mount(WorkspaceEmptyState, {
      props: { title: 'No activity events returned' },
      slots: { default: 'The API returned no events for these filters.' },
    });
    const emptyBanner = emptyState.getComponent(QBanner);
    expect(emptyBanner.attributes('role')).toBe('status');
    expect(emptyBanner.attributes('aria-live')).toBe('polite');
    expect(emptyBanner.get('h2').text()).toBe('No activity events returned');
    expect(emptyBanner.text()).toContain('The API returned no events for these filters.');
  });

  it('shows only selected stale-resource notices as polite banners', () => {
    const store = useWorkspaceStore();
    store.resourceFreshness.activity = {
      status: 'stale',
      confirmedAt: '2026-11-09T10:00:00Z',
    };

    const activity = mount(ResourceFreshnessNotice, { props: { resources: ['activity'] } });
    const banner = activity.getComponent(QBanner);
    expect(banner.attributes('role')).toBe('status');
    expect(banner.attributes('aria-live')).toBe('polite');
    expect(banner.text()).toContain(
      'The latest activity request failed; cached data is being shown.',
    );
    expect(banner.text()).toContain('2026-11-09T10:00:00Z');

    const unrelated = mount(ResourceFreshnessNotice, { props: { resources: ['health'] } });
    expect(unrelated.findAllComponents(QBanner)).toHaveLength(0);
  });
});

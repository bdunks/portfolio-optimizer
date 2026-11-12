// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils';
import { createPinia, setActivePinia } from 'pinia';
import { beforeEach, describe, expect, it } from 'vitest';
import ResourceFreshnessNotice from './ResourceFreshnessNotice.vue';
import WorkspaceCapabilityNotice from './WorkspaceCapabilityNotice.vue';
import WorkspaceEmptyState from './WorkspaceEmptyState.vue';
import { workspaceQueryKeys } from '@/composables/queries/workspace-queries';
import { getTestQueryClient, mountWithWorkspace } from '@/test-utils/workspace-mount';

beforeEach(() => setActivePinia(createPinia()));

describe('shared message notices', () => {
  it('keeps capability and empty-state messages polite and preserves their content', () => {
    const capability = mount(WorkspaceCapabilityNotice, {
      props: { label: 'DEMO ONLY.' },
      slots: { default: 'No broker calls or order submission are available.' },
    });
    const capabilityAlert = capability.get('[role="status"]');
    expect(capabilityAlert.attributes('aria-live')).toBe('polite');
    expect(capabilityAlert.get('[data-slot="alert-title"]').text()).toBe('DEMO ONLY.');
    expect(capabilityAlert.text()).toContain('No broker calls or order submission are available.');

    const emptyState = mount(WorkspaceEmptyState, {
      props: { title: 'No activity events returned' },
      slots: {
        default: 'The API returned no events for these filters.',
        details: '<p>Details remain available.</p>',
        action: '<button type="button">Retry</button>',
      },
    });
    const emptyAlert = emptyState.get('[role="status"]');
    expect(emptyAlert.attributes('aria-live')).toBe('polite');
    expect(emptyAlert.get('[role="heading"]').attributes('aria-level')).toBe('2');
    expect(emptyAlert.get('[role="heading"]').text()).toBe('No activity events returned');
    expect(emptyAlert.text()).toContain('The API returned no events for these filters.');
    expect(emptyAlert.get('button').text()).toBe('Retry');
  });

  it('shows only selected stale-resource notices as polite alerts', async () => {
    const wrapper = mountWithWorkspace(ResourceFreshnessNotice, {
      props: { resources: ['activity'] },
    });
    const queryClient = getTestQueryClient(wrapper);
    queryClient.setQueryData(
      workspaceQueryKeys.activity({}),
      {
        items: [],
        total: 0,
        offset: 0,
        limit: 50,
      },
      { updatedAt: Date.parse('2026-11-09T10:00:00Z') },
    );
    await queryClient
      .fetchQuery({
        queryKey: workspaceQueryKeys.activity({}),
        queryFn: () => Promise.reject(new Error('activity transport failed')),
        staleTime: 0,
        retry: false,
      })
      .catch(() => undefined);
    await flushPromises();
    const alert = wrapper.get('[role="status"]');
    expect(alert.attributes('aria-live')).toBe('polite');
    expect(alert.text()).toContain(
      'The latest activity request failed; cached data is being shown.',
    );
    expect(alert.text()).toContain('2026-11-09T10:00:00.000Z');
    wrapper.unmount();

    const unrelated = mountWithWorkspace(ResourceFreshnessNotice, {
      props: { resources: ['health'] },
    });
    expect(unrelated.findAll('[role="status"]')).toHaveLength(0);
    unrelated.unmount();
  });
});

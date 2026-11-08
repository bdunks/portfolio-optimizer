// @vitest-environment jsdom
import { mount } from '@vue/test-utils';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';
import { createMemoryHistory, createRouter } from 'vue-router';
import { useWorkspaceStore } from '@/stores/workspace-store';
import IndexPage from './IndexPage.vue';

afterEach(() => {
  vi.restoreAllMocks();
});

describe('IndexPage', () => {
  it('uses the shared workspace root for the overview screen', () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    const store = useWorkspaceStore();
    store.health = { status: 'ok', schema_ready: false } as never;
    store.portfolio = {
      status: 'not_synced',
      positions: [],
      coverage: {},
      sync: {
        generation: 0,
        complete: false,
        started_at: null,
        completed_at: null,
        last_error_code: null,
        last_error_summary: null,
      },
    } as never;
    store.policy = { active: null, drafts: [], superseded: [] };
    const router = createRouter({ history: createMemoryHistory(), routes: [] });
    const wrapper = mount(IndexPage, { global: { plugins: [pinia, router] } });

    expect(wrapper.get('.workspace-page').classes()).toContain('overview-page');
    expect(wrapper.get('h1').text()).toBe('Overview');

    wrapper.unmount();
  });
});

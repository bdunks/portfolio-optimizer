// @vitest-environment jsdom
import { config } from '@vue/test-utils';
import { createPinia } from 'pinia';
import { defineComponent } from 'vue';
import { afterEach, describe, expect, it } from 'vitest';
import {
  getTestQueryClient,
  getTestQueryClientForPinia,
  installWorkspaceTestPlugin,
  mountWithWorkspace,
} from './workspace-mount';

const emptyComponent = defineComponent({ template: '<div />' });
const mountedWrappers: Array<ReturnType<typeof mountWithWorkspace>> = [];

afterEach(() => {
  for (const wrapper of mountedWrappers.splice(0)) wrapper.unmount();
});

describe('workspace test mounts', () => {
  it('fails when an application component is unresolved', () => {
    const pageWithMissingWidget = defineComponent({
      template: '<PortfolioApplicationWidget />',
    });

    expect(() => mountWithWorkspace(pageWithMissingWidget)).toThrow(
      /Unresolved component warning: Failed to resolve component: PortfolioApplicationWidget/,
    );
  });

  it('installs the Vue Query test plugin only once', () => {
    const initialPluginCount = config.global.plugins?.length ?? 0;

    installWorkspaceTestPlugin();
    installWorkspaceTestPlugin();

    expect(config.global.plugins).toHaveLength(initialPluginCount);
  });

  it('isolates QueryClients per mounted app and reuses the per-Pinia client', () => {
    const firstPinia = createPinia();
    const secondPinia = createPinia();
    const firstPiniaClient = getTestQueryClientForPinia(firstPinia);

    expect(getTestQueryClientForPinia(firstPinia)).toBe(firstPiniaClient);
    expect(getTestQueryClientForPinia(secondPinia)).not.toBe(firstPiniaClient);

    const firstWrapper = mountWithWorkspace(emptyComponent);
    const secondWrapper = mountWithWorkspace(emptyComponent);
    mountedWrappers.push(firstWrapper, secondWrapper);
    expect(getTestQueryClient(firstWrapper)).not.toBe(getTestQueryClient(secondWrapper));
  });

  it('merges locally registered components and directives into mount options', () => {
    const localComponent = defineComponent({ template: '<span>Local component</span>' });
    const localDirective = {
      mounted(element: HTMLElement) {
        element.setAttribute('data-local-directive', 'mounted');
      },
    };
    const component = defineComponent({ template: '<div v-local><LocalWidget /></div>' });
    const wrapper = mountWithWorkspace(component, {
      global: {
        components: { LocalWidget: localComponent },
        directives: { local: localDirective },
      },
    });
    mountedWrappers.push(wrapper);

    expect(wrapper.get('span').text()).toBe('Local component');
    expect(wrapper.get('div').attributes('data-local-directive')).toBe('mounted');
  });
});

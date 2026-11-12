import { config, mount, type GlobalMountOptions, type VueWrapper } from '@vue/test-utils';
import { getActivePinia, type Pinia } from 'pinia';
import type { Component, Plugin } from 'vue';
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query';

const queryClientsByAppContext = new WeakMap<object, QueryClient>();
const queryClientsByPinia = new WeakMap<Pinia, QueryClient>();

function createTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        refetchOnWindowFocus: false,
        refetchOnReconnect: false,
      },
    },
  });
}

export function getTestQueryClientForPinia(pinia: Pinia): QueryClient {
  let queryClient = queryClientsByPinia.get(pinia);
  if (!queryClient) {
    queryClient = createTestQueryClient();
    queryClientsByPinia.set(pinia, queryClient);
  }
  return queryClient;
}

const vueQueryTestPlugin: Plugin = {
  install(app) {
    const pinia = getActivePinia();
    const queryClient = pinia ? getTestQueryClientForPinia(pinia) : createTestQueryClient();
    queryClientsByAppContext.set(app._context, queryClient);
    app.use(VueQueryPlugin, { queryClient });
  },
};

function pluginKey(plugin: Plugin | [Plugin, ...unknown[]]): Plugin {
  return Array.isArray(plugin) ? plugin[0] : plugin;
}

function warnOnUnresolvedComponents(message: string, _instance: unknown, trace: string): void {
  if (message.startsWith('Failed to resolve component:')) {
    throw new Error(`Unresolved component warning: ${message}${trace}`);
  }
  console.warn(message, trace);
}

export function workspaceMountGlobal(options: GlobalMountOptions = {}): GlobalMountOptions {
  return {
    ...options,
    components: { ...options.components },
    directives: { ...options.directives },
    config: { ...options.config, warnHandler: warnOnUnresolvedComponents },
  };
}

export function installWorkspaceTestPlugin(): void {
  const globalPlugins = config.global.plugins ?? (config.global.plugins = []);
  if (!globalPlugins.some((plugin) => pluginKey(plugin) === vueQueryTestPlugin)) {
    globalPlugins.push(vueQueryTestPlugin);
  }
  config.global.config = {
    ...config.global.config,
    warnHandler: warnOnUnresolvedComponents,
  };
}

export function mountWithWorkspace(
  component: Component,
  options: Parameters<typeof mount>[1] = {},
): ReturnType<typeof mount> {
  return mount(component, {
    ...options,
    global: workspaceMountGlobal(options.global),
  });
}

export function getTestQueryClient(wrapper: VueWrapper): QueryClient {
  const vm = wrapper.vm as unknown as { $: { appContext: object } };
  const queryClient = queryClientsByAppContext.get(vm.$.appContext);
  if (!queryClient) throw new Error('The mounted Vue app has no isolated QueryClient');
  return queryClient;
}

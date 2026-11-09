import { config, mount, type GlobalMountOptions } from '@vue/test-utils';
import { defineComponent, h, type Component, type Plugin } from 'vue';
import {
  QBadge,
  QBanner,
  QBtn,
  QCard,
  QCardSection,
  QDrawer,
  QHeader,
  QIcon,
  QItem,
  QItemLabel,
  QItemSection,
  QList,
  QLayout,
  QPage,
  QPageContainer,
  QToolbar,
  QToolbarTitle,
  Quasar,
} from 'quasar';

const quasarComponents = {
  QBadge,
  QBanner,
  QBtn,
  QCard,
  QCardSection,
  QDrawer,
  QHeader,
  QIcon,
  QItem,
  QItemLabel,
  QItemSection,
  QList,
  QLayout,
  QPage,
  QPageContainer,
  QToolbar,
  QToolbarTitle,
};

const quasarPlugin: Plugin | [Plugin, ...unknown[]] = [Quasar, { config: {} }];

function pluginKey(plugin: Plugin | [Plugin, ...unknown[]]): Plugin {
  return Array.isArray(plugin) ? plugin[0] : plugin;
}

function warnOnUnresolvedComponents(message: string, _instance: unknown, trace: string): void {
  if (message.startsWith('Failed to resolve component:')) {
    throw new Error(`Unresolved component warning: ${message}${trace}`);
  }
  console.warn(message, trace);
}

export function quasarMountGlobal(options: GlobalMountOptions = {}): GlobalMountOptions {
  return {
    ...options,
    components: { ...quasarComponents, ...options.components },
    directives: { ...options.directives },
    config: { ...options.config, warnHandler: warnOnUnresolvedComponents },
  };
}

export function installQuasarForTests(): void {
  if (!(config.global.plugins ?? []).some((plugin) => pluginKey(plugin) === Quasar)) {
    config.global.plugins.push(quasarPlugin);
  }
  config.global.components = { ...config.global.components, ...quasarComponents };
  config.global.config = {
    ...config.global.config,
    warnHandler: warnOnUnresolvedComponents,
  };
}

export function mountWithQuasar(
  component: Component,
  options: Parameters<typeof mount>[1] = {},
): ReturnType<typeof mount> {
  return mount(component, {
    ...options,
    global: quasarMountGlobal(options.global),
  });
}

export function mountWorkspacePageWithQuasar(
  component: Component,
  options: Parameters<typeof mount>[1] = {},
): ReturnType<typeof mount> {
  const workspacePageHost = defineComponent({
    name: 'QuasarWorkspacePageTestHarness',
    setup() {
      return () =>
        h(QLayout, { view: 'lHh Lpr lFf' }, () => h(QPageContainer, null, () => h(component)));
    },
  });
  return mountWithQuasar(workspacePageHost, options);
}

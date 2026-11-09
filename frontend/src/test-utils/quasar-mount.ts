import { config, mount, type GlobalMountOptions, type VueWrapper } from '@vue/test-utils';
import { defineComponent, h, nextTick, type Component, type Plugin } from 'vue';
import {
  QBadge,
  QBanner,
  QBtn,
  QCheckbox,
  QInput,
  QSelect,
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
  QCheckbox,
  QInput,
  QSelect,
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

export function findQuasarComponent(
  wrapper: VueWrapper,
  component: Component,
  label: string,
): VueWrapper {
  const found = wrapper.findAllComponents(component).find((candidate) => {
    const root = candidate.element;
    const props = candidate.props() as Record<string, unknown>;
    const attrs = candidate.vm.$attrs as Record<string, unknown>;
    const labels = root.querySelectorAll('[aria-label]');
    let ariaLabelMatches =
      root.getAttribute('aria-label') === label || attrs['aria-label'] === label;
    for (let index = 0; !ariaLabelMatches && index < labels.length; index += 1) {
      ariaLabelMatches = labels.item(index)?.getAttribute('aria-label') === label;
    }
    return props.label === label || ariaLabelMatches;
  });
  if (!found) throw new Error(`Quasar control not found: ${label}`);
  return found;
}

export async function setQuasarModelValue(
  wrapper: VueWrapper,
  component: Component,
  label: string,
  value: unknown,
): Promise<void> {
  findQuasarComponent(wrapper, component, label).vm.$emit('update:modelValue', value);
  await nextTick();
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

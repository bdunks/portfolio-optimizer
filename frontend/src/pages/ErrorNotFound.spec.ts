// @vitest-environment jsdom
import { flushPromises } from '@vue/test-utils';
import { createMemoryHistory, createRouter } from 'vue-router';
import { afterEach, describe, expect, it } from 'vitest';
import { mountWithWorkspace } from '@/test-utils/workspace-mount';
import ErrorNotFound from './ErrorNotFound.vue';

let mountedWrapper: ReturnType<typeof mountWithWorkspace> | undefined;

afterEach(() => {
  mountedWrapper?.unmount();
  mountedWrapper = undefined;
});

async function mountNotFound() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: { template: '<h1>Overview</h1>' } },
      { path: '/:catchAll(.*)*', component: ErrorNotFound },
    ],
  });
  await router.push('/missing-page');
  await router.isReady();
  const wrapper = mountWithWorkspace(ErrorNotFound, { global: { plugins: [router] } });
  mountedWrapper = wrapper;
  return { router, wrapper };
}

describe('ErrorNotFound', () => {
  it('renders a semantic 404 page and routes the Go Home link to the overview', async () => {
    const { router, wrapper } = await mountNotFound();

    expect(wrapper.get('main').element.tagName).toBe('MAIN');
    expect(wrapper.get('h1').text()).toBe('404');
    expect(wrapper.get('h2').text()).toBe('Oops. Nothing here...');

    const goHome = wrapper.get('a');
    expect(goHome.text()).toBe('Go Home');
    expect(goHome.attributes('href')).toBe('/');
    await goHome.trigger('click');
    await flushPromises();
    expect(router.currentRoute.value.fullPath).toBe('/');
  });
});

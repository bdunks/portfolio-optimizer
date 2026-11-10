// @vitest-environment jsdom
import { mountWorkspacePageWithQuasar } from '@/test-utils/quasar-mount';
import { QCard, QCardSection } from 'quasar';
import { createMemoryHistory, createRouter } from 'vue-router';
import { describe, expect, it } from 'vitest';
import DevelopmentPendingPage from './DevelopmentPendingPage.vue';

describe('DevelopmentPendingPage', () => {
  it('renders the pending message as a Quasar card while preserving its route title', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        {
          path: '/development',
          component: DevelopmentPendingPage,
          meta: { title: 'Tax lots' },
        },
      ],
    });
    await router.push('/development');
    await router.isReady();

    const wrapper = mountWorkspacePageWithQuasar(DevelopmentPendingPage, {
      global: { plugins: [router] },
    });
    const card = wrapper.findComponent(QCard);

    expect(card.exists()).toBe(true);
    expect(card.classes()).toContain('pending-card');
    expect(wrapper.findComponent(QCardSection).exists()).toBe(true);
    expect(wrapper.get('h1').text()).toBe('Tax lots');
    expect(wrapper.text()).toContain('No sample holdings, recommendations, or policy data');
    expect(wrapper.get('.pending-card').element.tagName).toBe('DIV');

    wrapper.unmount();
  });
});

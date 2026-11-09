// @vitest-environment jsdom
import { mount } from '@vue/test-utils';
import { QBanner } from 'quasar';
import { describe, expect, it } from 'vitest';
import WorkspaceCapabilityNotice from './WorkspaceCapabilityNotice.vue';
import WorkspaceEmptyState from './WorkspaceEmptyState.vue';
import WorkspaceFilterPanel from './WorkspaceFilterPanel.vue';
import WorkspaceTableFrame from './WorkspaceTableFrame.vue';

describe('shared workspace presentation', () => {
  it('renders capability notices through real Quasar banners with independent accessible content', () => {
    const wrapper = mount({
      components: { WorkspaceCapabilityNotice },
      template: `
        <div>
          <WorkspaceCapabilityNotice label="DEMO ONLY.">No broker connection.</WorkspaceCapabilityNotice>
          <WorkspaceCapabilityNotice label="Local policy only.">No order submission.</WorkspaceCapabilityNotice>
        </div>
      `,
    });

    expect(wrapper.findAllComponents(QBanner)).toHaveLength(2);
    expect(wrapper.findAll('[role="status"]')).toHaveLength(2);
    expect(wrapper.text()).toContain('DEMO ONLY. No broker connection.');
    expect(wrapper.text()).toContain('Local policy only. No order submission.');
  });

  it('provides an announced empty state with a titled recovery action slot', () => {
    const wrapper = mount(WorkspaceEmptyState, {
      props: { title: 'No activity page loaded' },
      slots: {
        default: 'Retry to request current activity.',
        action: '<button type="button">Retry loading activity</button>',
      },
    });

    expect(wrapper.get('[role="status"]').attributes('aria-live')).toBe('polite');
    expect(wrapper.get('h2').text()).toBe('No activity page loaded');
    expect(wrapper.get('button').text()).toBe('Retry loading activity');
  });

  it('labels keyboard-scrollable table frames and keeps filter submission page-owned', async () => {
    const frame = mount(WorkspaceTableFrame, {
      props: { label: 'Synthetic tax lots' },
      slots: { default: '<table><caption>Synthetic tax lots</caption></table>' },
    });
    expect(frame.get('[role="region"]').attributes('aria-label')).toBe('Synthetic tax lots');
    expect(frame.get('[role="region"]').attributes('tabindex')).toBe('0');
    expect(frame.get('table caption').text()).toBe('Synthetic tax lots');

    const filter = mount(WorkspaceFilterPanel, {
      props: { label: 'Activity filters' },
      slots: { default: '<button type="submit">Apply filters</button>' },
    });
    const event = new Event('submit', { bubbles: true, cancelable: true });
    filter.element.dispatchEvent(event);
    await filter.vm.$nextTick();

    expect(filter.get('form').attributes('aria-label')).toBe('Activity filters');
    expect(event.defaultPrevented).toBe(true);
    expect(filter.emitted('submit')).toHaveLength(1);
  });
});

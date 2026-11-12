// @vitest-environment jsdom
import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';
import WorkspaceCapabilityNotice from './WorkspaceCapabilityNotice.vue';
import WorkspaceEmptyState from './WorkspaceEmptyState.vue';
import WorkspaceFilterPanel from './WorkspaceFilterPanel.vue';
import WorkspaceTableFrame from './WorkspaceTableFrame.vue';
import { Table } from './ui/table';

describe('shared workspace presentation', () => {
  it('renders accessible capability alerts with independent content', () => {
    const wrapper = mount({
      components: { WorkspaceCapabilityNotice },
      template: `
        <div>
          <WorkspaceCapabilityNotice label="DEMO ONLY.">No broker connection.</WorkspaceCapabilityNotice>
          <WorkspaceCapabilityNotice label="Local policy only.">No order submission.</WorkspaceCapabilityNotice>
        </div>
      `,
    });

    const alerts = wrapper.findAll('[data-slot="alert"]');
    expect(alerts).toHaveLength(2);
    expect(wrapper.findAll('[role="status"]')).toHaveLength(2);
    const [capabilityAlert, policyAlert] = alerts;
    if (!capabilityAlert || !policyAlert) {
      throw new Error('Expected capability alerts to render');
    }
    expect(capabilityAlert.text()).toContain('DEMO ONLY.');
    expect(capabilityAlert.text()).toContain('No broker connection.');
    expect(policyAlert.text()).toContain('Local policy only.');
    expect(policyAlert.text()).toContain('No order submission.');
  });

  it('provides an announced empty state with details and recovery action slots', () => {
    const wrapper = mount(WorkspaceEmptyState, {
      props: { title: 'No activity page loaded' },
      slots: {
        default: 'Retry to request current activity.',
        details: '<p>Activity details are unavailable.</p>',
        action: '<button type="button">Retry loading activity</button>',
      },
    });

    const emptyState = wrapper.get('[role="status"]');
    expect(emptyState.attributes('aria-live')).toBe('polite');
    expect(emptyState.get('[role="heading"]').text()).toBe('No activity page loaded');
    expect(emptyState.get('[role="heading"]').attributes('aria-level')).toBe('2');
    expect(emptyState.text()).toContain('Retry to request current activity.');
    expect(emptyState.text()).toContain('Activity details are unavailable.');
    expect(emptyState.get('button').text()).toBe('Retry loading activity');
  });

  it('labels keyboard-scrollable table frames and keeps filter submission page-owned', async () => {
    const frame = mount({
      components: { WorkspaceTableFrame, Table },
      template: `
        <WorkspaceTableFrame label="Synthetic tax lots">
          <Table class="tw:min-w-[64rem]">
            <caption>Synthetic tax lots</caption>
          </Table>
        </WorkspaceTableFrame>
      `,
    });
    const region = frame.get('[role="region"]');
    expect(region.attributes('aria-label')).toBe('Synthetic tax lots');
    expect(region.attributes('tabindex')).toBe('0');
    expect(region.classes()).toContain('tw:focus-visible:ring-ring');
    expect(frame.get('[data-slot="table-container"]').element.parentElement).toBe(region.element);
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

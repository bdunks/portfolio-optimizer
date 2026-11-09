import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';
import WorkspacePageHeader from './WorkspacePageHeader.vue';

describe('WorkspacePageHeader', () => {
  it('keeps route titles labelled and exposes actions through the shared slot contract', () => {
    const wrapper = mount({
      components: { WorkspacePageHeader },
      template: `
        <div>
          <WorkspacePageHeader
            eyebrow="Review"
            title="Recommendations"
            title-id="recommendations-title"
            subtitle="Review proposed trades."
          >
            <template #actions><button type="button">Run DEMO</button></template>
          </WorkspacePageHeader>
          <WorkspacePageHeader
            eyebrow="History"
            title="Activity"
            title-id="activity-title"
            subtitle="Review saved runs."
          >
            <template #actions><button type="button">Refresh</button></template>
          </WorkspacePageHeader>
        </div>
      `,
    });

    const headings = wrapper.findAll('h1');
    expect(headings.map((heading) => heading.attributes('id'))).toEqual([
      'recommendations-title',
      'activity-title',
    ]);
    expect(headings.map((heading) => heading.text())).toEqual(['Recommendations', 'Activity']);
    expect(wrapper.findAll('[aria-label="Page actions"]')).toHaveLength(2);
    expect(wrapper.text()).toContain('Review proposed trades.');
    expect(wrapper.text()).toContain('Run DEMO');
    expect(wrapper.text()).toContain('Refresh');
  });
});

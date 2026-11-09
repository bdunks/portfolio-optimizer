// @vitest-environment jsdom
import { mount } from '@vue/test-utils';
import { QBtn } from 'quasar';
import { describe, expect, it } from 'vitest';
import WorkspacePagination from './WorkspacePagination.vue';

describe('WorkspacePagination', () => {
  it('uses Quasar buttons and emits page offsets with accessible page context', async () => {
    const wrapper = mount(WorkspacePagination, {
      props: { offset: 10, limit: 10, total: 25, label: 'Activity pages' },
    });
    const buttons = wrapper.findAllComponents(QBtn);

    expect(wrapper.get('nav').attributes('aria-label')).toBe('Activity pages');
    expect(wrapper.text()).toContain('Page 2 of 3');
    expect(buttons).toHaveLength(2);
    expect(wrapper.findAll('button').map((button) => button.attributes('type'))).toEqual([
      'button',
      'button',
    ]);
    expect(buttons[0]?.props('disable')).toBe(false);
    expect(buttons[1]?.props('disable')).toBe(false);

    await buttons[0]?.trigger('click');
    await buttons[1]?.trigger('click');
    expect(wrapper.emitted('page')).toEqual([[0], [20]]);
  });

  it('keeps backward navigation available on an empty non-first page', () => {
    const wrapper = mount(WorkspacePagination, {
      props: { offset: 10, limit: 10, total: 25, label: 'Tax lot API pages' },
    });
    const buttons = wrapper.findAllComponents(QBtn);

    expect(buttons[0]?.props('disable')).toBe(false);
    expect(buttons[1]?.props('disable')).toBe(false);
    expect(wrapper.text()).toContain('Page 2 of 3');
  });

  it('disables pending and out-of-range actions but permits recovery from an empty result', async () => {
    const wrapper = mount(WorkspacePagination, {
      props: { offset: 0, limit: 10, total: 20, label: 'Activity pages', pending: true },
    });
    let buttons = wrapper.findAllComponents(QBtn);
    expect(buttons.every((button) => button.props('disable'))).toBe(true);
    await buttons[1]?.trigger('click');
    expect(wrapper.emitted('page')).toBeUndefined();

    await wrapper.setProps({ offset: 20, total: 0, pending: false });
    buttons = wrapper.findAllComponents(QBtn);
    expect(buttons[0]?.props('disable')).toBe(false);
    expect(buttons[1]?.props('disable')).toBe(true);
    await buttons[0]?.trigger('click');
    expect(wrapper.emitted('page')).toEqual([[10]]);
  });
});

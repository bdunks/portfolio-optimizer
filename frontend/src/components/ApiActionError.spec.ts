// @vitest-environment jsdom
import { mount } from '@vue/test-utils';
import { QBanner } from 'quasar';
import { describe, expect, it } from 'vitest';
import { ApiError } from '@/services/api';
import ApiActionError from './ApiActionError.vue';

describe('ApiActionError', () => {
  it('uses an accessible Quasar alert banner for structured failures', () => {
    const wrapper = mount(ApiActionError, {
      props: {
        error: new ApiError('synthetic_error', 'Synthetic request failure', {}, 'corr-synthetic'),
        title: 'Activity could not be loaded',
      },
    });

    expect(wrapper.findComponent(QBanner).exists()).toBe(true);
    expect(wrapper.get('[role="alert"]').attributes('aria-live')).toBe('assertive');
    expect(wrapper.text()).toContain('Activity could not be loaded');
    expect(wrapper.text()).toContain('synthetic_error: Synthetic request failure');
    expect(wrapper.text()).toContain('Correlation ID: corr-synthetic');
  });

  it('renders nothing without an error', () => {
    const wrapper = mount(ApiActionError, { props: { error: null, title: 'Failed' } });
    expect(wrapper.findComponent(QBanner).exists()).toBe(false);
    expect(wrapper.text()).toBe('');
  });
});

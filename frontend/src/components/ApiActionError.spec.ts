// @vitest-environment jsdom
import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';
import { ApiError } from '@/services/api';
import ApiActionError from './ApiActionError.vue';

describe('ApiActionError', () => {
  it('uses a destructive accessible alert for structured failures', () => {
    const wrapper = mount(ApiActionError, {
      props: {
        error: new ApiError('synthetic_error', 'Synthetic request failure', {}, 'corr-synthetic'),
        title: 'Activity could not be loaded',
      },
    });

    const alert = wrapper.get('[role="alert"]');
    expect(alert.attributes('aria-live')).toBe('assertive');
    expect(alert.attributes('data-slot')).toBe('alert');
    expect(alert.classes()).toContain('tw:text-destructive');
    expect(alert.get('[data-slot="alert-title"]').text()).toBe('Activity could not be loaded');
    expect(alert.get('[data-slot="alert-description"]').text()).toContain(
      'synthetic_error: Synthetic request failure',
    );
    expect(alert.text()).toContain('Correlation ID: corr-synthetic');
  });

  it('preserves long unbroken error codes, messages, and correlation IDs', () => {
    const code = `error-${'x'.repeat(160)}`;
    const message = `request-failed-${'y'.repeat(400)}`;
    const correlationId = `correlation-${'z'.repeat(160)}`;
    const wrapper = mount(ApiActionError, {
      props: {
        error: new ApiError(code, message, {}, correlationId),
        title: 'Request failed',
      },
    });

    const alert = wrapper.get('[role="alert"]');
    expect(alert.classes()).toContain('api-error');
    expect(alert.get('code').text()).toBe(code);
    expect(alert.get('[data-slot="alert-description"]').text()).toContain(message);
    expect(alert.text()).toContain(correlationId);
  });

  it('renders nothing without an error', () => {
    const wrapper = mount(ApiActionError, { props: { error: null, title: 'Failed' } });
    expect(wrapper.find('[data-slot="alert"]').exists()).toBe(false);
    expect(wrapper.text()).toBe('');
  });
});

// @vitest-environment jsdom
import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';
import USAllocationTransition from './USAllocationTransition.vue';
import type { USTransitionResponse } from '@/types/api';

// Synthetic typed response for component presentation tests; not account or product demo data.
const transition = {
  sleeve_key: 'test-us-sleeve',
  label: 'Synthetic US sleeve',
  current: {
    us_sleeve_value_usd: '101.0100',
    us_sleeve_whole_portfolio_pct: '51.5100',
    etf_progress_pct: '11.1100',
    children: {
      fund: {
        value_usd: '12.1200',
        within_us_sleeve_pct: '12.1200',
        whole_portfolio_pct: '6.0600',
      },
      stocks: {
        value_usd: '88.8900',
        within_us_sleeve_pct: '87.8800',
        whole_portfolio_pct: '45.4500',
      },
    },
  },
  proposed_basket: {
    us_sleeve_value_usd: '102.0200',
    us_sleeve_whole_portfolio_pct: '52.5200',
    etf_progress_pct: '13.1300',
    children: {
      fund: {
        value_usd: '13.1300',
        within_us_sleeve_pct: '13.1300',
        whole_portfolio_pct: '6.5650',
      },
      stocks: {
        value_usd: '88.8900',
        within_us_sleeve_pct: '86.8700',
        whole_portfolio_pct: '45.9550',
      },
    },
  },
  target: {
    us_sleeve_whole_portfolio_pct: '53.5300',
    children: {
      fund: { within_us_sleeve_pct: '20.2000', whole_portfolio_pct: '10.6060' },
      stocks: { within_us_sleeve_pct: '79.8000', whole_portfolio_pct: '42.7240' },
    },
  },
} satisfies USTransitionResponse;

describe('USAllocationTransition', () => {
  it('renders distinct current, proposed, and policy target states with explicit units', () => {
    const wrapper = mount(USAllocationTransition, {
      props: { transition, labels: { fund: 'Synthetic fund', stocks: 'Synthetic equities' } },
    });

    expect(wrapper.findAll('.state-card')).toHaveLength(3);
    expect(wrapper.get('[data-state="current"]').text()).toContain('101.0100 USD');
    expect(wrapper.get('[data-state="proposed"]').text()).toContain('102.0200 USD');
    expect(wrapper.get('[data-state="target"]').text()).toContain('Policy target');
    expect(wrapper.text()).toContain('Within US sleeve + whole portfolio');
    expect(wrapper.get('[data-state="current"]').text()).toContain(
      'ETF progress within US sleeve11.1100%',
    );
    expect(wrapper.get('[data-state="current"]').text()).toContain('12.1200% within US sleeve');
    expect(wrapper.get('[data-state="proposed"]').text()).toContain('13.1300% within US sleeve');
    expect(wrapper.text()).toContain('6.0600% of whole portfolio');
    expect(wrapper.get('[data-state="target"]').text()).toContain('20.2000% within US sleeve');
  });

  it('states missing transition data as unavailable instead of substituting zero', () => {
    const wrapper = mount(USAllocationTransition, { props: { transition: null } });

    expect(wrapper.text()).toContain('US transition data is unavailable');
    expect(wrapper.text()).not.toContain('0 USD');
    expect(wrapper.findAll('.state-card')).toHaveLength(0);
  });
});

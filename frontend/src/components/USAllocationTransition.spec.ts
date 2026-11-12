// @vitest-environment jsdom
import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';

import USAllocationTransition from './USAllocationTransition.vue';
import type { USTransitionResponse } from '@/types/api';

// Synthetic typed response for component presentation tests; not account or product demo data.
const transition = {
  sleeve_key: 'test-us-sleeve',
  transition_destination_sleeve_key: 'fund',
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
    const cards = wrapper.findAll('article[data-state]');
    expect(cards).toHaveLength(3);
    expect(cards.map((card) => card.attributes('data-state'))).toEqual([
      'current',
      'proposed',
      'target',
    ]);
    expect(wrapper.findAll('[data-slot="card"]')).toHaveLength(3);
    expect(wrapper.find('section.transition-panel').exists()).toBe(true);

    const current = wrapper.get('[data-state="current"]');
    const proposed = wrapper.get('[data-state="proposed"]');
    const target = wrapper.get('[data-state="target"]');
    expect(current.findAll('dd').map((item) => item.text())).toEqual([
      '101.0100 USD',
      '51.5100%',
      '11.1100%',
    ]);
    expect(proposed.findAll('dd').map((item) => item.text())).toEqual([
      '102.0200 USD',
      '52.5200%',
      '13.1300%',
    ]);
    expect(target.text()).toContain('Policy target');
    expect(target.findAll('dd').map((item) => item.text())).toEqual([
      'Unavailable',
      '53.5300%',
      'Unavailable',
    ]);
    expect(target.text()).toContain(
      'Policy target percentages; dollar values and progress are unavailable.',
    );
    expect(wrapper.text()).toContain('Within US sleeve + whole portfolio');
    expect(current.text()).toContain('12.1200% within US sleeve');
    expect(proposed.text()).toContain('13.1300% within US sleeve');
    expect(wrapper.text()).toContain('6.0600% of whole portfolio');
    expect(target.text()).toContain('20.2000% within US sleeve');

    const unitBadge = wrapper.get('[data-slot="badge"]');
    expect(unitBadge.text()).toBe('Within US sleeve + whole portfolio');
    expect(unitBadge.attributes('role')).toBeUndefined();
    expect(unitBadge.attributes('tabindex')).toBeUndefined();
  });

  it('keeps component keys in first API appearance order and falls back to raw keys', () => {
    const snapshotChild = {
      value_usd: '1.00',
      within_us_sleeve_pct: '1.0000',
      whole_portfolio_pct: '0.5000',
    };
    const targetChild = { within_us_sleeve_pct: '1.0000', whole_portfolio_pct: '0.5000' };
    const unionTransition: USTransitionResponse = {
      ...transition,
      current: {
        ...transition.current,
        children: { current_key: snapshotChild, shared_key: snapshotChild },
      },
      proposed_basket: {
        ...transition.proposed_basket,
        children: { proposed_key: snapshotChild, shared_key: snapshotChild },
      },
      target: {
        ...transition.target,
        children: { target_key: targetChild, current_key: targetChild },
      },
    };
    const wrapper = mount(USAllocationTransition, {
      props: {
        transition: unionTransition,
        labels: { current_key: 'Current child', shared_key: 'Shared child' },
      },
    });

    expect(
      wrapper
        .get('[data-state="current"]')
        .findAll('.component-list strong')
        .map((item) => item.text()),
    ).toEqual(['Current child', 'Shared child', 'proposed_key', 'target_key']);
  });

  it('shows unavailable destination progress without inferring a security set', () => {
    const unconfigured: USTransitionResponse = {
      ...transition,
      transition_destination_sleeve_key: null,
      current: { ...transition.current, etf_progress_pct: null },
      proposed_basket: { ...transition.proposed_basket, etf_progress_pct: null },
    };
    const wrapper = mount(USAllocationTransition, { props: { transition: unconfigured } });

    const notice = wrapper.get('[data-slot="alert"]');
    expect(notice.attributes('role')).toBe('status');
    expect(notice.attributes('aria-live')).toBe('polite');
    expect(notice.text()).toContain('No transition destination is designated in this policy');
    expect(wrapper.get('[data-state="current"]').text()).toContain(
      'Transition destination progress within US sleeveUnavailable',
    );
    expect(
      wrapper
        .get('[data-state="target"]')
        .findAll('dd')
        .map((item) => item.text())[2],
    ).toBe('Unavailable');
    expect(wrapper.text()).not.toContain('11.1100%');
    expect(wrapper.text()).not.toContain('ETF ticker');
  });

  it('states missing transition data as unavailable instead of substituting zero', () => {
    const wrapper = mount(USAllocationTransition, { props: { transition: null } });

    expect(wrapper.text()).toContain('US transition data is unavailable');
    expect(wrapper.text()).not.toContain('0 USD');
    expect(wrapper.findAll('.state-card')).toHaveLength(0);
    expect(wrapper.get('[data-slot="empty"]').attributes('role')).toBe('status');
  });

  it('keeps empty API component children as an explicit state', () => {
    const noChildren: USTransitionResponse = {
      ...transition,
      current: { ...transition.current, children: {} },
      proposed_basket: { ...transition.proposed_basket, children: {} },
      target: { ...transition.target, children: {} },
    };
    const wrapper = mount(USAllocationTransition, { props: { transition: noChildren } });

    expect(wrapper.findAll('[data-state]')).toHaveLength(3);
    expect(wrapper.findAll('.component-empty')).toHaveLength(3);
    expect(wrapper.text()).toContain('No US sleeve component values were returned.');
  });

  it('shows the current-basket comparison notice only when requested and keeps it polite', () => {
    const wrapper = mount(USAllocationTransition, {
      props: { transition, showNoCurrentBasket: true },
    });
    const notice = wrapper.get('[data-slot="alert"]');
    expect(notice.attributes('role')).toBe('status');
    expect(notice.attributes('aria-live')).toBe('polite');
    expect(notice.text()).toContain(
      'No current proposed basket from a matching current optimizer run.',
    );

    const withoutNotice = mount(USAllocationTransition, { props: { transition } });
    expect(withoutNotice.findAll('[data-slot="alert"]')).toHaveLength(0);
  });
});

// @vitest-environment jsdom
import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';
import { QBanner, QCard, QChip } from 'quasar';
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
    const cards = wrapper.findAllComponents(QCard);
    expect(cards).toHaveLength(3);
    expect(cards.map((card) => card.element.tagName.toLowerCase())).toEqual([
      'article',
      'article',
      'article',
    ]);
    expect(cards.every((card) => card.classes().includes('q-pa-md'))).toBe(true);
    expect(wrapper.find('section.transition-panel').exists()).toBe(true);

    expect(wrapper.findAll('.state-card')).toHaveLength(3);
    expect(wrapper.get('[data-state="current"]').text()).toContain('101.0100 USD');
    expect(wrapper.get('[data-state="proposed"]').text()).toContain('102.0200 USD');
    expect(wrapper.get('[data-state="target"]').text()).toContain('Policy target');
    expect(wrapper.text()).toContain('Within US sleeve + whole portfolio');
    expect(wrapper.get('[data-state="current"]').text()).toContain(
      'Transition destination progress within US sleeve11.1100%',
    );
    const unitChip = wrapper.findComponent(QChip);
    expect(unitChip.text()).toBe('Within US sleeve + whole portfolio');
    expect(unitChip.props('clickable')).toBe(false);
    expect(unitChip.attributes('role')).toBeUndefined();
    expect(wrapper.get('[data-state="current"]').text()).toContain('12.1200% within US sleeve');
    expect(wrapper.get('[data-state="proposed"]').text()).toContain('13.1300% within US sleeve');
    expect(wrapper.text()).toContain('6.0600% of whole portfolio');
    expect(wrapper.get('[data-state="target"]').text()).toContain('20.2000% within US sleeve');
  });

  it('shows unavailable destination progress without inferring a security set', () => {
    const unconfigured: USTransitionResponse = {
      ...transition,
      transition_destination_sleeve_key: null,
      current: { ...transition.current, etf_progress_pct: null },
      proposed_basket: { ...transition.proposed_basket, etf_progress_pct: null },
    };
    const wrapper = mount(USAllocationTransition, { props: { transition: unconfigured } });

    expect(wrapper.text()).toContain('No transition destination is designated in this policy');
    expect(wrapper.get('[data-state="current"]').text()).toContain(
      'Transition destination progress within US sleeveUnavailable',
    );
    expect(wrapper.text()).not.toContain('11.1100%');
  });

  it('states missing transition data as unavailable instead of substituting zero', () => {
    const wrapper = mount(USAllocationTransition, { props: { transition: null } });

    expect(wrapper.text()).toContain('US transition data is unavailable');
    expect(wrapper.text()).not.toContain('0 USD');
    expect(wrapper.findAll('.state-card')).toHaveLength(0);
  });
  it('shows the current-basket comparison notice only when requested and keeps it polite', () => {
    const wrapper = mount(USAllocationTransition, {
      props: { transition, showNoCurrentBasket: true },
    });
    const banner = wrapper.getComponent(QBanner);
    expect(banner.attributes('role')).toBe('status');
    expect(banner.text()).toContain(
      'No current proposed basket from a matching current optimizer run.',
    );

    const withoutNotice = mount(USAllocationTransition, { props: { transition } });
    expect(withoutNotice.findAllComponents(QBanner)).toHaveLength(0);
  });
});

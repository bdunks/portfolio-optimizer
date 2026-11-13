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

const roleIdentity = {
  containerKey: 'test-us-sleeve',
  legacyKey: 'stocks',
  destinationKey: 'fund',
};

describe('USAllocationTransition', () => {
  it('compares API current, selected-basket, and target percentages without converting decimal strings', () => {
    const wrapper = mount(USAllocationTransition, {
      props: {
        transition,
        labels: { fund: 'Synthetic fund', stocks: 'Synthetic equities' },
        roleIdentity,
        snapshotStatus: 'confirmed',
        basketStatus: 'confirmed',
      },
    });

    expect(wrapper.text()).toContain('Current');
    expect(wrapper.text()).toContain('After selected trades');
    expect(wrapper.text()).toContain('Target');
    expect(wrapper.text()).toContain('Current portfolio API context');
    expect(wrapper.text()).toContain('101.0100 USD · 51.5100%');
    expect(wrapper.text()).toContain('102.0200 USD · 52.5200%');
    expect(wrapper.text()).toContain('53.5300% · dollar value unavailable');
    expect(wrapper.text()).toContain('Currently in new holdings');
    expect(wrapper.text()).toContain('11.1100% within US sleeve');
    expect(wrapper.text()).toContain('12.1200%');
    expect(wrapper.text()).toContain('13.1300%');
    expect(wrapper.text()).toContain('20.2000%');
    expect(wrapper.text()).toContain('Legacy holdings');
    expect(wrapper.text()).toContain('New holdings');
    expect(wrapper.text()).toContain('whole portfolio');
    expect(wrapper.text()).toContain('within US sleeve');
    expect(wrapper.text()).toContain('gradual, tax-constrained transition');
    expect(wrapper.text()).not.toContain('immediate liquidation');
  });

  it('does not show proposed values when a matching run has no selected trades', () => {
    const wrapper = mount(USAllocationTransition, {
      props: { transition, basketStatus: 'no-selection' },
    });

    expect(wrapper.text()).toContain('No trades selected. Proposed values are not shown.');
    expect(wrapper.get('.whole-portfolio-summary').text()).toContain('No trades selected');
    expect(wrapper.get('tbody').text()).not.toContain('13.1300%');
    expect(wrapper.get('tbody').text()).not.toContain('86.8700%');
    expect(wrapper.get('tbody').text()).toContain('20.2000%');
  });

  it.each([
    ['pending', 'Pending'],
    ['stale', 'Unavailable (stale data)'],
    ['unverified', 'Unavailable (unverified data)'],
    ['unavailable', 'Unavailable'],
  ] as const)('withholds current values when portfolio provenance is %s', (status, expected) => {
    const wrapper = mount(USAllocationTransition, {
      props: { transition, snapshotStatus: status, basketStatus: 'pending' },
    });

    expect(wrapper.get('[aria-labelledby="transition-title"]').text()).toContain(expected);
    expect(wrapper.get('.whole-portfolio-summary').text()).not.toContain('101.0100 USD');
    expect(wrapper.get('.whole-portfolio-summary').text()).not.toContain('102.0200 USD');
    expect(wrapper.text()).not.toContain('11.1100%');
    expect(wrapper.text()).not.toContain('13.1300%');
    expect(wrapper.text()).toContain('prior proposed values are withheld');
  });

  it.each([
    ['pending', 'Pending'],
    ['stale', 'Unavailable (stale effects)'],
    ['unverified', 'Unavailable (unverified effects)'],
    ['unavailable', 'Unavailable'],
  ] as const)(
    'withholds proposed values when selected-basket evidence is %s',
    (status, expected) => {
      const wrapper = mount(USAllocationTransition, {
        props: { transition, snapshotStatus: 'confirmed', basketStatus: status },
      });

      expect(wrapper.get('.whole-portfolio-summary').text()).not.toContain('102.0200 USD');
      expect(wrapper.get('tbody').text()).toContain(expected);
      expect(wrapper.get('tbody').text()).not.toContain('13.1300%');
      expect(wrapper.get('tbody').text()).toContain('20.2000%');
    },
  );

  it('labels a saved run as frozen and read-only while preserving its saved values', () => {
    const wrapper = mount(USAllocationTransition, {
      props: {
        transition,
        labels: { fund: 'Frozen fund label', stocks: 'Frozen legacy label' },
        snapshotStatus: 'saved',
        basketStatus: 'saved',
        roleIdentity,
        provenance: 'saved_run',
      },
    });

    expect(wrapper.text()).toContain('Saved run · frozen context · read-only');
    expect(wrapper.text()).toContain('Frozen fund label');
    expect(wrapper.text()).toContain('Frozen legacy label');
    expect(wrapper.text()).toContain('102.0200 USD · 52.5200%');
    expect(wrapper.text()).toContain('20.2000%');
    expect(wrapper.text()).not.toContain('Current portfolio API context');
  });

  it('does not infer destination identity from security details when no destination is configured', () => {
    const unconfigured: USTransitionResponse = {
      ...transition,
      transition_destination_sleeve_key: null,
      current: { ...transition.current, etf_progress_pct: null },
      proposed_basket: { ...transition.proposed_basket, etf_progress_pct: null },
    };
    const wrapper = mount(USAllocationTransition, {
      props: { transition: unconfigured, basketStatus: 'confirmed', roleIdentity },
    });

    expect(wrapper.text()).toContain('Set up US transition');
    expect(wrapper.text()).toContain('No transition destination is designated');
    expect(wrapper.text()).not.toContain('Currently in new holdings');
    expect(wrapper.text()).not.toContain('11.1100%');
    expect(wrapper.get('.transition-headline').text()).not.toContain('13.1300%');
    expect(wrapper.text()).toContain('Legacy holdings');
  });

  it('does not treat an unverified null destination as an active setup instruction', () => {
    const wrapper = mount(USAllocationTransition, {
      props: {
        transition: { ...transition, transition_destination_sleeve_key: null },
        snapshotStatus: 'unverified',
        basketStatus: 'unverified',
      },
    });

    expect(wrapper.text()).toContain(
      'Current US transition provenance is unverified; values are withheld.',
    );
    expect(wrapper.get('.transition-headline').text()).toContain('Destination status unverified');
    expect(wrapper.text()).not.toContain('Set up US transition');
    expect(wrapper.text()).not.toContain('No transition destination is designated');
    expect(wrapper.text()).not.toContain('11.1100%');
  });

  it('keeps an absent API response unavailable rather than substituting zero', () => {
    const wrapper = mount(USAllocationTransition, {
      props: { transition: null, snapshotStatus: 'unavailable', basketStatus: 'unavailable' },
    });

    expect(wrapper.text()).toContain('US transition data is unavailable from the API.');
    expect(wrapper.text()).toContain('US transition data unavailable.');
    expect(wrapper.text()).not.toContain('0 USD');
    expect(wrapper.text()).not.toContain('0%');
  });
});

import { mount } from '@vue/test-utils';
import { QCard } from 'quasar';
import { describe, expect, it } from 'vitest';
import RecommendationLegDetails from './RecommendationLegDetails.vue';
import type { RecommendationLegResponse } from '@/types/api';

function leg(legId: string, sequence: number): RecommendationLegResponse {
  return {
    leg_id: legId,
    side: 'BUY',
    ticker: 'VTI',
    shares: '3',
    estimated_unit_price_usd: '251.2500',
    estimated_notional_usd: '753.7500',
    net_st_realized_usd: '0.0000',
    net_lt_realized_usd: '0.0000',
    selected: true,
    group_ids: ['group-a'],
    sequence,
    dependencies: [],
    selected_lots: [],
    details: {},
  };
}

describe('RecommendationLegDetails', () => {
  it('uses unique accessible heading IDs and preserves exact API decimal strings', () => {
    const wrapper = mount({
      components: { RecommendationLegDetails },
      data: () => ({ legs: [leg('leg-a', 1), leg('leg-b', 2)] }),
      template: `
        <div>
          <RecommendationLegDetails v-for="item in legs" :key="item.leg_id" :leg="item" />
        </div>
      `,
    });

    const cards = wrapper.findAll('article.leg-card');
    const quasarCards = wrapper.findAllComponents(QCard);
    expect(quasarCards).toHaveLength(2);
    expect(quasarCards.map((card) => card.element.tagName.toLowerCase())).toEqual([
      'article',
      'article',
    ]);
    expect(quasarCards.every((card) => card.classes().includes('q-pa-md'))).toBe(true);
    const headingIds = cards.map((card) => card.find('h3').attributes('id'));
    expect(new Set(headingIds).size).toBe(2);
    expect(cards.map((card) => card.attributes('aria-labelledby'))).toEqual(headingIds);
    expect(wrapper.text()).toContain('251.2500 USD');
    expect(wrapper.text()).toContain('753.7500 USD');
    expect(wrapper.text()).toContain('API-proposed whole shares');
    expect(wrapper.text()).not.toContain('remaining shares');
  });
});

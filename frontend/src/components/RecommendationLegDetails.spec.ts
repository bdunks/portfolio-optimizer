import { mount } from '@vue/test-utils';
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
  it('keeps a semantic article, unique headings, and exact API values and wording', () => {
    const secondLeg = {
      ...leg('leg-b', 2),
      side: 'SELL' as const,
      ticker: null,
      shares: '1.0000',
      selected: false,
      dependencies: ['leg-a'],
    };
    const wrapper = mount({
      components: { RecommendationLegDetails },
      data: () => ({ legs: [leg('leg-a', 1), secondLeg] }),
      template: `
        <div>
          <RecommendationLegDetails
            v-for="item in legs"
            :key="item.leg_id"
            :leg="item"
            :id="'anchor-' + item.leg_id"
          />
        </div>
      `,
    });

    const articles = wrapper.findAll('article.leg-card');
    expect(articles).toHaveLength(2);
    expect(articles.map((article) => article.attributes('id'))).toEqual([
      'anchor-leg-a',
      'anchor-leg-b',
    ]);
    const headingIds = articles.map((article) => article.find('h3').attributes('id'));
    expect(new Set(headingIds).size).toBe(2);
    expect(articles.map((article) => article.attributes('aria-labelledby'))).toEqual(headingIds);
    expect(articles.map((article) => article.find('h3').text())).toEqual([
      'Sequence 1 · BUY VTI',
      'Sequence 2 · SELL ticker unavailable',
    ]);
    expect(articles[0]?.text()).toContain('leg-a');
    expect(articles[0]?.text()).toContain('API-proposed whole shares');
    expect(articles[0]?.text()).toContain('3');
    expect(articles[0]?.text()).toContain('251.2500 USD');
    expect(articles[0]?.text()).toContain('753.7500 USD');
    expect(articles[0]?.text()).toContain('0.0000 USD / 0.0000 USD');
    expect(articles[0]?.text()).toContain('No leg dependency was returned by the API.');
    expect(articles[0]?.text()).toContain('Selected in this API basket');
    expect(articles[1]?.text()).toContain('Requires API leg(s): leg-a');
    expect(articles[1]?.text()).toContain('Not selected in this API basket');
    expect(wrapper.text()).not.toContain('remaining shares');
  });
});

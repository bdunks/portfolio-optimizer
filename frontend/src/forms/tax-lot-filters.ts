import { z } from 'zod';
import type { LotQuery } from '@/services/api';

export const TAX_LOT_PAGE_LIMITS = [50, 100, 250, 500] as const;

export const TAX_LOT_SORT_FIELDS = [
  'ticker',
  'broker_lot_id',
  'acquired_date',
  'remaining_shares',
  'available_shares',
  'adjusted_unit_basis_usd',
  'adjusted_total_basis_usd',
  'current_price_usd',
  'unrealized_pl_usd',
  'unrealized_pl_pct',
  'term',
  'sleeve_key',
  'sub_sleeve_key',
] as const satisfies readonly NonNullable<LotQuery['sort_by']>[];

export const taxLotFilterSchema = z.object({
  search: z.string(),
  term: z.union([z.literal(''), z.literal('ST'), z.literal('LT')]),
  fractional: z.union([z.literal(''), z.literal('true'), z.literal('false')]),
  limit: z.union([z.literal(50), z.literal(100), z.literal(250), z.literal(500)]),
  sortBy: z.enum(TAX_LOT_SORT_FIELDS),
  sortDirection: z.enum(['asc', 'desc']),
});

export type TaxLotFilterValues = z.infer<typeof taxLotFilterSchema>;

export function isTaxLotPageLimit(value: unknown): value is TaxLotFilterValues['limit'] {
  return TAX_LOT_PAGE_LIMITS.some((limit) => limit === value);
}

export function isTaxLotSortField(value: string): value is TaxLotFilterValues['sortBy'] {
  return TAX_LOT_SORT_FIELDS.some((field) => field === value);
}

export function taxLotFilterDefaults(filters: LotQuery): TaxLotFilterValues {
  return {
    search: filters.search ?? '',
    term: filters.term === 'ST' || filters.term === 'LT' ? filters.term : '',
    fractional:
      filters.fractional === undefined || filters.fractional === null
        ? ''
        : String(filters.fractional) === 'true'
          ? 'true'
          : 'false',
    limit: isTaxLotPageLimit(filters.limit) ? filters.limit : 100,
    sortBy: filters.sort_by ?? 'ticker',
    sortDirection: filters.sort_direction ?? 'asc',
  };
}

import { z } from 'zod';

const recommendationDatePattern = /^(\d{4})-(\d{2})-(\d{2})$/;

function isCalendarDate(value: string): boolean {
  const match = recommendationDatePattern.exec(value);
  if (!match) return false;

  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const date = new Date(0);
  date.setUTCHours(0, 0, 0, 0);
  date.setUTCFullYear(year, month - 1, day);
  return (
    date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 && date.getUTCDate() === day
  );
}

export const proposedTradeDateSchema = z
  .string()
  .refine((value) => value === '' || isCalendarDate(value), 'Enter a valid calendar date.');

export const recommendationRunFormSchema = z.object({
  proposedTradeDate: proposedTradeDateSchema,
});

export const savedRunIdSchema = z.string().refine((value) => value.trim().length > 0, {
  message: 'Enter a saved run ID.',
});

export const savedRunFormSchema = z.object({
  savedRunId: savedRunIdSchema,
});

export const recommendationFilterFormSchema = z.object({
  sleeve: z.string(),
  action: z.union([z.literal(''), z.enum(['BUY', 'SELL'])]),
  term: z.union([z.literal(''), z.enum(['ST', 'LT'])]),
  benefit: z.union([z.literal(''), z.literal('unavailable')]),
  warning: z.union([z.literal(''), z.literal('with'), z.literal('without')]),
  groupType: z.string(),
  sortOrder: z.enum(['rank-ascending', 'rank-descending']),
});

export const recommendationFilterDefaults: z.input<typeof recommendationFilterFormSchema> = {
  sleeve: '',
  action: '',
  term: '',
  benefit: '',
  warning: '',
  groupType: '',
  sortOrder: 'rank-ascending',
};

export const recommendationTopNFormSchema = z.object({
  // Keep raw text as well as numbers so the existing Number(value) || 0 behavior is preserved.
  topN: z.union([z.number(), z.string()]),
});

export type RecommendationFilterFormValues = z.infer<typeof recommendationFilterFormSchema>;
export type RecommendationTopNFormValues = z.infer<typeof recommendationTopNFormSchema>;

export const recommendationTopNDefaults: RecommendationTopNFormValues = { topN: 3 };

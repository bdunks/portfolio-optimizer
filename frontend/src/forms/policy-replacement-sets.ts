import { z } from 'zod';

const replacementSecuritySchema = z.object({
  ticker: z.string(),
  sleeve_key: z.string(),
  sub_sleeve_key: z.string().nullable().optional(),
  replacement_set_id: z.string().optional(),
  priority: z.number().int({ error: 'Priority must be a whole number.' }).optional(),
  enabled: z.boolean().optional(),
  exposure_suitability: z.string().nullable().optional(),
});

export const policyReplacementSetsSchema = z.object({
  rows: z.array(
    z.object({
      rowId: z.string(),
      security: replacementSecuritySchema,
    }),
  ),
});

export type PolicyReplacementSetsFormValues = z.infer<typeof policyReplacementSetsSchema>;
